"""
Async-совместимая обёртка над SQLite.
"""
import json
import asyncio
import aiosqlite
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from config import DB_PATH
from utils.logger import setup_logger

logger = setup_logger()


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def connect(self):
        if self._conn is None:
            self._conn = await aiosqlite.connect(self.db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA synchronous=NORMAL")
            await self._create_tables()

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def _conn_or_raise(self) -> aiosqlite.Connection:
        if self._conn is None:
            await self.connect()
        assert self._conn is not None
        return self._conn

    async def _create_tables(self):
        conn = self._conn
        assert conn is not None
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS players (
                tag TEXT PRIMARY KEY,
                name TEXT,
                name_color TEXT,
                icon_id INTEGER,
                trophies INTEGER,
                highest_trophies INTEGER,
                exp_level INTEGER,
                exp_points INTEGER,
                wins_3v3 INTEGER DEFAULT 0,
                wins_solo INTEGER DEFAULT 0,
                wins_duo INTEGER DEFAULT 0,
                best_robo_rumble_time INTEGER,
                best_time_as_big_brawler INTEGER,
                club_tag TEXT,
                last_updated TEXT
            );

            CREATE TABLE IF NOT EXISTS battles (
                id TEXT PRIMARY KEY,
                player_tag TEXT,
                battle_time TEXT,
                battle_mode TEXT,
                battle_type TEXT,
                result TEXT,
                duration INTEGER,
                brawler_id INTEGER,
                brawler_name TEXT,
                trophies_change INTEGER,
                stars INTEGER,
                raw_data TEXT,
                FOREIGN KEY(player_tag) REFERENCES players(tag)
            );

            CREATE TABLE IF NOT EXISTS clubs (
                tag TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                type TEXT,
                trophies INTEGER,
                required_trophies INTEGER,
                members_count INTEGER,
                last_updated TEXT
            );

            CREATE TABLE IF NOT EXISTS club_members (
                club_tag TEXT,
                player_tag TEXT,
                role TEXT,
                name TEXT,
                trophies INTEGER,
                PRIMARY KEY (club_tag, player_tag)
            );

            CREATE TABLE IF NOT EXISTS tg_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                plan TEXT DEFAULT 'free',
                premium_until TEXT,
                daily_requests INTEGER DEFAULT 0,
                daily_reset_date TEXT,
                total_requests INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                currency TEXT,
                plan TEXT,
                created_at TEXT,
                FOREIGN KEY(user_id) REFERENCES tg_users(user_id)
            );

            CREATE TABLE IF NOT EXISTS user_ratings (
                user_id TEXT PRIMARY KEY,
                rating INTEGER DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS team_codes (
                code TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                is_used INTEGER DEFAULT 0,
                creator TEXT
            );
        """)
        await conn.commit()

    # ─────────────────────────────────────────────────────────────────────────
    # Игроки
    # ─────────────────────────────────────────────────────────────────────────
    async def search_players_by_name(self, name: str, limit: int = 20) -> List[Dict]:
        conn = await self._conn_or_raise()
        name_like = f"%{name}%"
        async with conn.execute(
            "SELECT * FROM players WHERE name LIKE ? ORDER BY trophies DESC LIMIT ?",
            (name_like, limit)
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def upsert_player(self, data: Dict[str, Any]):
        conn = await self._conn_or_raise()
        now = datetime.now(timezone.utc).isoformat()
        tag = data["tag"].lstrip('#')
        club_tag = data.get("club_tag")
        if club_tag:
            club_tag = club_tag.lstrip('#')
        await conn.execute("""
            INSERT OR REPLACE INTO players (
                tag, name, name_color, icon_id, trophies, highest_trophies,
                exp_level, exp_points, wins_3v3, wins_solo, wins_duo,
                best_robo_rumble_time, best_time_as_big_brawler, club_tag, last_updated
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            tag,
            data.get("name"),
            data.get("name_color"),
            data.get("icon_id"),
            data.get("trophies"),
            data.get("highest_trophies"),
            data.get("exp_level"),
            data.get("exp_points"),
            data.get("wins_3v3", 0),
            data.get("wins_solo", 0),
            data.get("wins_duo", 0),
            data.get("best_robo_rumble_time"),
            data.get("best_time_as_big_brawler"),
            club_tag,
            now,
        ))
        await conn.commit()

    async def get_player(self, tag: str) -> Optional[Dict]:
        conn = await self._conn_or_raise()
        tag = tag.lstrip('#')
        async with conn.execute("SELECT * FROM players WHERE tag=?", (tag,)) as cur:
            row = await cur.fetchone()
        if row:
            player = dict(row)
            player["tag"] = f"#{player['tag']}"
            return player
        return None

    async def is_player_fresh(self, tag: str, ttl_seconds: int = 300) -> bool:
        player = await self.get_player(tag)
        if not player or not player.get("last_updated"):
            return False
        last = datetime.fromisoformat(player["last_updated"])
        age = (datetime.now(timezone.utc) - last).total_seconds()
        return age < ttl_seconds

    # ─────────────────────────────────────────────────────────────────────────
    # Бои
    # ─────────────────────────────────────────────────────────────────────────
    async def upsert_battle(self, player_tag: str, battle: Dict[str, Any]):
        conn = await self._conn_or_raise()
        bt = battle.get("battleTime", "")
        battle_id = f"{player_tag}_{bt}"
        await conn.execute("""
            INSERT OR IGNORE INTO battles (
                id, player_tag, battle_time, battle_mode, battle_type, result,
                duration, brawler_id, brawler_name, trophies_change, stars, raw_data
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            battle_id, player_tag, bt,
            battle.get("battle", {}).get("mode"),
            battle.get("battle", {}).get("type"),
            battle.get("battle", {}).get("result"),
            battle.get("battle", {}).get("duration"),
            battle.get("brawler", {}).get("id"),
            battle.get("brawler", {}).get("name"),
            battle.get("battle", {}).get("trophyChange"),
            1 if battle.get("battle", {}).get("starPlayer") else 0,
            json.dumps(battle),
        ))
        await conn.commit()

    async def get_battles(self, tag: str, limit: int = 10) -> List[Dict]:
        conn = await self._conn_or_raise()
        tag = tag.lstrip('#')
        async with conn.execute(
            "SELECT * FROM battles WHERE player_tag=? ORDER BY battle_time DESC LIMIT ?",
            (tag, limit)
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # ─────────────────────────────────────────────────────────────────────────
    # Клубы
    # ─────────────────────────────────────────────────────────────────────────

    async def search_clubs_by_name(self, name: str, limit: int = 20) -> List[Dict]:
        conn = await self._conn_or_raise()
        name_like = f"%{name}%"
        async with conn.execute(
            "SELECT * FROM clubs WHERE name LIKE ? ORDER BY trophies DESC LIMIT ?",
            (name_like, limit)
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]
    
    async def upsert_club(self, data: Dict[str, Any]):
        conn = await self._conn_or_raise()
        now = datetime.now(timezone.utc).isoformat()
        tag = data["tag"].lstrip('#')
        await conn.execute("""
            INSERT OR REPLACE INTO clubs (
                tag, name, description, type, trophies, required_trophies,
                members_count, last_updated
            ) VALUES (?,?,?,?,?,?,?,?)
        """, (
            tag,
            data.get("name"),
            data.get("description"),
            data.get("type"),
            data.get("trophies"),
            data.get("required_trophies"),
            len(data.get("members", [])) or data.get("members_count", 0),
            now,
        ))
        await conn.commit()

    async def upsert_club_members(self, club_tag: str, members: List[Dict]):
        conn = await self._conn_or_raise()
        club_tag = club_tag.lstrip('#')
        await conn.execute("DELETE FROM club_members WHERE club_tag=?", (club_tag,))
        await conn.executemany(
            "INSERT INTO club_members (club_tag, player_tag, role, name, trophies) VALUES (?,?,?,?,?)",
            [(club_tag, m["tag"].lstrip('#'), m.get("role"), m.get("name"), m.get("trophies")) for m in members]
        )
        await conn.commit()

    async def get_club(self, tag: str) -> Optional[Dict]:
        conn = await self._conn_or_raise()
        tag = tag.lstrip('#')
        async with conn.execute("SELECT * FROM clubs WHERE tag=?", (tag,)) as cur:
            row = await cur.fetchone()
        if row:
            club = dict(row)
            club["tag"] = f"#{club['tag']}"
            return club
        return None

    async def get_club_members(self, club_tag: str) -> List[Dict]:
        conn = await self._conn_or_raise()
        club_tag = club_tag.lstrip('#')
        async with conn.execute(
            "SELECT * FROM club_members WHERE club_tag=? ORDER BY trophies DESC",
            (club_tag,)
        ) as cur:
            rows = await cur.fetchall()
        members = []
        for r in rows:
            member = dict(r)
            member["player_tag"] = f"#{member['player_tag']}"
            members.append(member)
        return members

    # ─────────────────────────────────────────────────────────────────────────
    # Telegram-пользователи (без изменений)
    # ─────────────────────────────────────────────────────────────────────────
    async def get_or_create_user(
        self, user_id: int, username: str = "", first_name: str = ""
    ) -> Dict:
        conn = await self._conn_or_raise()
        now = datetime.now(timezone.utc).isoformat()
        today = now[:10]

        async with conn.execute("SELECT * FROM tg_users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()

        if row is not None:
            user = dict(row)
            if user.get("daily_reset_date") != today:
                await conn.execute(
                    "UPDATE tg_users SET daily_requests=0, daily_reset_date=?, updated_at=? WHERE user_id=?",
                    (today, now, user_id)
                )
                await conn.commit()
                user["daily_requests"] = 0
                user["daily_reset_date"] = today
            return user

        await conn.execute("""
            INSERT INTO tg_users (user_id, username, first_name, plan, daily_requests,
                                  daily_reset_date, total_requests, created_at, updated_at)
            VALUES (?,?,?,'free',0,?,0,?,?)
        """, (user_id, username, first_name, today, now, now))
        await conn.commit()

        async with conn.execute("SELECT * FROM tg_users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
        assert row is not None
        return dict(row)

    async def increment_user_requests(self, user_id: int):
        conn = await self._conn_or_raise()
        now = datetime.now(timezone.utc).isoformat()
        await conn.execute("""
            UPDATE tg_users
            SET daily_requests = daily_requests + 1,
                total_requests  = total_requests  + 1,
                updated_at      = ?
            WHERE user_id=?
        """, (now, user_id))
        await conn.commit()

    async def upgrade_to_premium(self, user_id: int, days: int = 30, amount: int = 0):
        conn = await self._conn_or_raise()
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        until = (now + timedelta(days=days)).isoformat()
        now_s = now.isoformat()

        await conn.execute("""
            UPDATE tg_users SET plan='premium', premium_until=?, updated_at=? WHERE user_id=?
        """, (until, now_s, user_id))
        await conn.execute("""
            INSERT INTO payments (user_id, amount, currency, plan, created_at)
            VALUES (?,?,?,?,?)
        """, (user_id, amount, "XTR", "premium", now_s))
        await conn.commit()

    async def check_premium(self, user_id: int) -> bool:
        conn = await self._conn_or_raise()
        async with conn.execute(
            "SELECT plan, premium_until FROM tg_users WHERE user_id=?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return False
        if row["plan"] == "premium":
            if row["premium_until"]:
                until = datetime.fromisoformat(row["premium_until"])
                if until > datetime.now(timezone.utc):
                    return True
                await conn.execute(
                    "UPDATE tg_users SET plan='free' WHERE user_id=?", (user_id,)
                )
                await conn.commit()
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # Рейтинг пользователей (CLI)
    # ─────────────────────────────────────────────────────────────────────────
    async def get_rating(self, user_id: str) -> int:
        """Возвращает текущий рейтинг пользователя."""
        conn = await self._conn_or_raise()
        async with conn.execute(
            "SELECT rating FROM user_ratings WHERE user_id=?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else 0

    async def add_rating(self, user_id: str, points: int):
        """Добавляет очки рейтинга пользователю (создаёт запись, если её нет)."""
        conn = await self._conn_or_raise()
        await conn.execute("""
            INSERT INTO user_ratings (user_id, rating) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET rating = rating + ?, last_updated = CURRENT_TIMESTAMP
        """, (user_id, points, points))
        await conn.commit()

    # ─────────────────────────────────────────────────────────────────────────
    # Универсальные методы execute/fetchone (для удобства)
    # ─────────────────────────────────────────────────────────────────────────
    async def execute(self, sql: str, params: tuple = ()):
        """Выполняет запрос (без выборки) и коммитит."""
        conn = await self._conn_or_raise()
        await conn.execute(sql, params)
        await conn.commit()

    async def fetchone(self, sql: str, params: tuple = ()):
        """Выполняет запрос и возвращает одну строку (как dict)."""
        conn = await self._conn_or_raise()
        async with conn.execute(sql, params) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def fetchall(self, sql: str, params: tuple = ()):
        """Выполняет запрос и возвращает список строк (как dict)."""
        conn = await self._conn_or_raise()
        async with conn.execute(sql, params) as cur:
            rows = await cur.fetchall()
        return [dict(row) for row in rows]

    # ─────────────────────────────────────────────────────────────────────────
    # Team Codes - управление кодами командной игры
    # ─────────────────────────────────────────────────────────────────────────
    
    async def insert_team_code(self, code: str, expires_at: str, creator: Optional[str] = None):
        """Сохраняет новый код команды в базу."""
        conn = await self._conn_or_raise()
        now = datetime.now(timezone.utc).isoformat()
        await conn.execute("""
            INSERT INTO team_codes (code, created_at, expires_at, is_used, creator)
            VALUES (?, ?, ?, 0, ?)
        """, (code, now, expires_at, creator))
        await conn.commit()

    async def get_team_code(self, code: str) -> Optional[Dict]:
        """Получает информацию о коде команды."""
        conn = await self._conn_or_raise()
        async with conn.execute(
            "SELECT * FROM team_codes WHERE code = ?", (code,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def get_active_team_codes(self) -> List[Dict]:
        """Возвращает все активные (неиспользованные и неистекшие) коды."""
        conn = await self._conn_or_raise()
        now = datetime.now(timezone.utc).isoformat()
        async with conn.execute("""
            SELECT * FROM team_codes 
            WHERE is_used = 0 AND expires_at > ?
            ORDER BY created_at DESC
        """, (now,)) as cur:
            rows = await cur.fetchall()
        return [dict(row) for row in rows]

    async def mark_team_code_used(self, code: str):
        """Отмечает код как использованный."""
        conn = await self._conn_or_raise()
        await conn.execute(
            "UPDATE team_codes SET is_used = 1 WHERE code = ?", (code,)
        )
        await conn.commit()

    async def cleanup_expired_team_codes(self) -> int:
        """Удаляет истекшие коды. Возвращает количество удалённых."""
        conn = await self._conn_or_raise()
        now = datetime.now(timezone.utc).isoformat()
        cursor = await conn.execute(
            "DELETE FROM team_codes WHERE expires_at <= ?", (now,)
        )
        await conn.commit()
        return cursor.rowcount

    async def exists_active_team_code(self, code: str) -> bool:
        """Проверяет, существует ли активный код."""
        conn = await self._conn_or_raise()
        now = datetime.now(timezone.utc).isoformat()
        async with conn.execute("""
            SELECT 1 FROM team_codes 
            WHERE code = ? AND is_used = 0 AND expires_at > ?
        """, (code, now)) as cur:
            row = await cur.fetchone()
        return row is not None