"""
Синхронизация локальной базы данных с GitHub.
Экспортирует SQLite в JSON-файлы, коммитит и пушит изменения.
Данные хранятся в ветке brawl_data в папке brawl_data/brawl_data/...
"""
import os
import json
import asyncio
import aiosqlite
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import git
from git.exc import InvalidGitRepositoryError, GitCommandError

from config import DB_PATH, GITHUB_REPO_URL, GITHUB_TOKEN, APP_CFG, GITHUB_BRANCH
from utils.logger import setup_logger

logger = setup_logger(__name__)


class GitHubSync:
    """Синхронизация данных с удаленным репозиторием GitHub."""
    
    def __init__(self, repo_url: Optional[str] = None, token: Optional[str] = None, branch: str = None):
        # Отключаем прокси для git
        os.environ["http_proxy"] = ""
        os.environ["https_proxy"] = ""
        os.environ["HTTP_PROXY"] = ""
        os.environ["HTTPS_PROXY"] = ""
        os.environ["all_proxy"] = ""
        os.environ["ALL_PROXY"] = ""

        self.repo_url = repo_url or GITHUB_REPO_URL
        self.token = token or GITHUB_TOKEN
        self.branch = branch or GITHUB_BRANCH or "brawl_data"
        
        # Структура: brawl_data/brawl_data/... (players, battles, clubs, team_codes)
        self.base_dir = Path("brawl_data")
        self.data_dir = self.base_dir / "brawl_data"
        
        self.local_path = Path(".").absolute()
        self.repo: Optional[git.Repo] = None

        if not self.repo_url:
            raise ValueError("GitHub repo URL not provided in .env (GITHUB_REPO_URL)")

        self.repo_url = self.repo_url.strip()
        if self.repo_url.endswith("/"):
            self.repo_url = self.repo_url.rstrip("/")

        # Создаем структуру папок
        self._ensure_data_structure()
        self._clear_git_proxy()

    def _ensure_data_structure(self):
        """Создает необходимую структуру папок для данных."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "players").mkdir(exist_ok=True)
        (self.data_dir / "clubs").mkdir(exist_ok=True)
        (self.data_dir / "battles").mkdir(exist_ok=True)
        (self.data_dir / "team_codes").mkdir(exist_ok=True)
        (self.data_dir / "maps").mkdir(exist_ok=True)
        (self.data_dir / "brawlers").mkdir(exist_ok=True)

    def _clear_git_proxy(self):
        try:
            subprocess.run(["git", "config", "--global", "--unset", "http.proxy"], stderr=subprocess.DEVNULL)
            subprocess.run(["git", "config", "--global", "--unset", "https.proxy"], stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def init_repo(self):
        """Инициализирует локальный репозиторий и настраивает remote."""
        try:
            self.repo = git.Repo(self.local_path)
            origin = self.repo.remotes.origin
            auth_url = self._get_auth_url()
            if origin.url != auth_url:
                origin.set_url(auth_url)
            
            # Проверяем и переключаемся на нужную ветку
            self._checkout_branch()
        except InvalidGitRepositoryError:
            logger.info(f"Initializing new git repository at {self.local_path}")
            self.repo = git.Repo.init(self.local_path)
            auth_url = self._get_auth_url()
            self.repo.create_remote("origin", auth_url)
            self._checkout_branch()
            
    def _get_auth_url(self) -> str:
        """Возвращает URL репозитория с токеном для аутентификации."""
        if self.token and self.repo_url.startswith("https://"):
            return self.repo_url.replace("https://", f"https://{self.token}@")
        return self.repo_url
    
    def _checkout_branch(self):
        """Переключается на целевую ветку или создает её."""
        if not self.repo:
            return
            
        # Проверяем существует ли ветка локально
        local_branches = [b.name for b in self.repo.branches]
        
        if self.branch not in local_branches:
            # Пытаемся найти удаленную ветку
            try:
                origin = self.repo.remotes.origin
                origin.fetch()
                
                # Проверяем существует ли удаленная ветка
                remote_branch_exists = any(
                    ref.name == f"origin/{self.branch}" 
                    for ref in self.repo.refs
                )
                
                if remote_branch_exists:
                    # Создаем локальную ветку из удаленной
                    self.repo.git.checkout('-b', self.branch, f'origin/{self.branch}')
                    logger.info(f"Checked out remote branch {self.branch}")
                else:
                    # Создаем новую ветку
                    self.repo.git.checkout('-b', self.branch)
                    logger.info(f"Created new branch {self.branch}")
            except GitCommandError as e:
                logger.warning(f"Could not checkout branch {self.branch}: {e}")
                # Создаем ветку если не удалось получить с remote
                if self.branch not in [b.name for b in self.repo.branches]:
                    self.repo.git.checkout('-b', self.branch)
        else:
            # Ветка существует локально - переключаемся
            self.repo.git.checkout(self.branch)
            
        logger.info(f"Current branch: {self.repo.active_branch.name}")

    def commit_and_push(self, message: str, files: Optional[List[str]] = None, force_initial: bool = False):
        """Коммитит и пушит изменения в удаленный репозиторий."""
        if not self.repo:
            self.init_repo()
        assert self.repo is not None

        # Если файлы не указаны, добавляем всю директорию data
        if files:
            self.repo.index.add(files)
        else:
            self.repo.index.add([str(self.data_dir)])
            
        if self.repo.is_dirty() or force_initial:
            self.repo.index.commit(message)
            origin = self.repo.remotes.origin
            try:
                origin.push(set_upstream=True)
                logger.info(f"Changes committed and pushed to {self.branch}: {message}")
                return True
            except GitCommandError as e:
                if "has no upstream branch" in str(e):
                    current = self.repo.active_branch
                    origin.push(refspec=f"{current.name}:{current.name}", set_upstream=True)
                    logger.info(f"Pushed new branch {current.name} to remote")
                    return True
                else:
                    logger.warning("Push failed, trying pull first...")
                    try:
                        origin.pull(rebase=True)
                        origin.push(set_upstream=True)
                        return True
                    except GitCommandError as pull_error:
                        logger.error(f"Pull/push failed: {pull_error}")
                        return False
        else:
            logger.debug("No changes to commit")
            return False

    async def export_data(self):
        """Экспортирует данные из SQLite в JSON файлы."""
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row

            # 1. Игроки
            async with conn.execute("SELECT * FROM players") as cur:
                players = await cur.fetchall()
                for player in players:
                    player_dict = dict(player)
                    player_dict["exported_at"] = datetime.now(timezone.utc).isoformat()
                    filename = self.data_dir / "players" / f"{player_dict['tag']}.json"
                    with open(filename, "w", encoding="utf-8") as f:
                        json.dump(player_dict, f, ensure_ascii=False, indent=2)

            # 2. Клубы
            async with conn.execute("SELECT * FROM clubs") as cur:
                clubs = await cur.fetchall()
                for club in clubs:
                    club_dict = dict(club)
                    club_dict["exported_at"] = datetime.now(timezone.utc).isoformat()
                    filename = self.data_dir / "clubs" / f"{club_dict['tag']}.json"
                    with open(filename, "w", encoding="utf-8") as f:
                        json.dump(club_dict, f, ensure_ascii=False, indent=2)

            # 3. Участники клубов
            async with conn.execute("SELECT * FROM club_members") as cur:
                members = await cur.fetchall()
                members_file = self.data_dir / "club_members.json"
                with open(members_file, "w", encoding="utf-8") as f:
                    json.dump([dict(m) for m in members], f, ensure_ascii=False, indent=2)

            # 4. Бои (по папкам игроков)
            async with conn.execute("SELECT player_tag, battle_time, raw_data FROM battles") as cur:
                battles = await cur.fetchall()
                for battle in battles:
                    player_tag = battle["player_tag"]
                    battle_time = battle["battle_time"]
                    raw_data = json.loads(battle["raw_data"])
                    player_battles_dir = self.data_dir / "battles" / player_tag
                    player_battles_dir.mkdir(exist_ok=True, parents=True)
                    safe_time = battle_time.replace(":", "-").replace("T", "_")
                    filename = player_battles_dir / f"{safe_time}.json"
                    with open(filename, "w", encoding="utf-8") as f:
                        json.dump(raw_data, f, ensure_ascii=False, indent=2)

            # 5. Сводный файл rooms.json (все бои, сгруппированные по времени)
            rooms = {}
            async with conn.execute("""
                SELECT 
                    battle_time, 
                    player_tag, 
                    battle_mode, 
                    result,
                    raw_data
                FROM battles
                ORDER BY battle_time
            """) as cur:
                rows = await cur.fetchall()
                for row in rows:
                    bt = row["battle_time"]
                    if bt not in rooms:
                        rooms[bt] = {
                            "battle_time": bt,
                            "mode": row["battle_mode"],
                            "players": [],
                            "results": {}
                        }
                    rooms[bt]["players"].append(row["player_tag"])
                    rooms[bt]["results"][row["player_tag"]] = row["result"]
                    if not rooms[bt].get("map"):
                        try:
                            raw = json.loads(row["raw_data"])
                            rooms[bt]["map"] = raw.get("event", {}).get("map")
                        except:
                            pass

            rooms_list = list(rooms.values())
            rooms_file = self.data_dir / "rooms.json"
            with open(rooms_file, "w", encoding="utf-8") as f:
                json.dump(rooms_list, f, ensure_ascii=False, indent=2)

        logger.info("Data exported to JSON files.")

    async def export_team_codes(self, codes: List[Dict]):
        """Экспортирует коды команд в JSON файл."""
        codes_file = self.data_dir / "team_codes" / "active_codes.json"
        codes_file.parent.mkdir(exist_ok=True)
        
        export_data = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "total_codes": len(codes),
            "codes": codes
        }
        
        with open(codes_file, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Exported {len(codes)} team codes to {codes_file}")

    async def import_data(self):
        """Импортирует данные из JSON файлов в SQLite."""
        async with aiosqlite.connect(DB_PATH) as conn:
            # 1. Импорт игроков
            players_dir = self.data_dir / "players"
            if players_dir.exists():
                for file in players_dir.glob("*.json"):
                    with open(file, "r", encoding="utf-8") as f:
                        player = json.load(f)
                    player.pop("exported_at", None)
                    await conn.execute("""
                        INSERT OR REPLACE INTO players (
                            tag, name, name_color, icon_id, trophies, highest_trophies,
                            exp_level, exp_points, wins_3v3, wins_solo, wins_duo,
                            best_robo_rumble_time, best_time_as_big_brawler, club_tag, last_updated
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        player.get("tag"), player.get("name"), player.get("name_color"),
                        player.get("icon_id"), player.get("trophies"), player.get("highest_trophies"),
                        player.get("exp_level"), player.get("exp_points"), player.get("wins_3v3", 0),
                        player.get("wins_solo", 0), player.get("wins_duo", 0),
                        player.get("best_robo_rumble_time"), player.get("best_time_as_big_brawler"),
                        player.get("club_tag"), player.get("last_updated")
                    ))
            # 2. Клубы
            clubs_dir = self.data_dir / "clubs"
            if clubs_dir.exists():
                for file in clubs_dir.glob("*.json"):
                    with open(file, "r", encoding="utf-8") as f:
                        club = json.load(f)
                    club.pop("exported_at", None)
                    await conn.execute("""
                        INSERT OR REPLACE INTO clubs (
                            tag, name, description, type, trophies, required_trophies,
                            members_count, last_updated
                        ) VALUES (?,?,?,?,?,?,?,?)
                    """, (
                        club.get("tag"), club.get("name"), club.get("description"),
                        club.get("type"), club.get("trophies"), club.get("required_trophies"),
                        club.get("members_count"), club.get("last_updated")
                    ))
            # 3. Участники клубов
            members_file = self.data_dir / "club_members.json"
            if members_file.exists():
                with open(members_file, "r", encoding="utf-8") as f:
                    members = json.load(f)
                await conn.execute("DELETE FROM club_members")
                for m in members:
                    await conn.execute("""
                        INSERT INTO club_members (club_tag, player_tag, role, name, trophies)
                        VALUES (?,?,?,?,?)
                    """, (m.get("club_tag"), m.get("player_tag"), m.get("role"), m.get("name"), m.get("trophies")))
            # 4. Бои
            battles_dir = self.data_dir / "battles"
            if battles_dir.exists():
                for player_dir in battles_dir.iterdir():
                    if not player_dir.is_dir():
                        continue
                    player_tag = player_dir.name
                    for file in player_dir.glob("*.json"):
                        with open(file, "r", encoding="utf-8") as f:
                            battle = json.load(f)
                        battle_time = battle.get("battleTime", "")
                        battle_id = f"{player_tag}_{battle_time}"
                        await conn.execute("""
                            INSERT OR IGNORE INTO battles (
                                id, player_tag, battle_time, battle_mode, battle_type, result,
                                duration, brawler_id, brawler_name, trophies_change, stars, raw_data
                            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (
                            battle_id, player_tag, battle_time,
                            battle.get("battle", {}).get("mode"),
                            battle.get("battle", {}).get("type"),
                            battle.get("battle", {}).get("result"),
                            battle.get("battle", {}).get("duration"),
                            battle.get("brawler", {}).get("id"),
                            battle.get("brawler", {}).get("name"),
                            battle.get("battle", {}).get("trophyChange"),
                            1 if battle.get("battle", {}).get("starPlayer") else 0,
                            json.dumps(battle)
                        ))
            await conn.commit()
        logger.info("Data imported from JSON files.")

    async def pull_and_import(self):
        """Pull из remote и импорт данных."""
        self.init_repo()
        assert self.repo is not None
        origin = self.repo.remotes.origin
        origin.pull()
        await self.import_data()
        logger.info("Pulled and imported from GitHub.")

    async def export_and_push(self, message: str = "Auto sync from CLI"):
        """Экспорт данных и push в remote."""
        self.init_repo()
        await self.export_data()
        self.commit_and_push(message)