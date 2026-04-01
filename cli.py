#!/usr/bin/env python3
"""
BrawlNest CLI — полный интерфейс (modern TUI).
Переработанный интерфейс меню: адаптивная сетка, равные колонки, навигация стрелками,
Tab/Shift+Tab циклически, сохранение позиции курсора, аккуратный header/footer.
"""
import sys
import asyncio
import json
import os
import time
import threading
import random
import aiohttp
import shutil
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from math import ceil

from rich.console import Console
from rich.table import Table
from rich import box
from rich.rule import Rule
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn
from rich.align import Align

from prompt_toolkit import Application as PTApp
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style as PTStyle

try:
    from config import (
        API_KEYS, SEARCH_CFG, APP_CFG, SYNC_CFG,
        GITHUB_REPO_URL, GITHUB_TOKEN, API_SERVER_URL, BRAWLNEST_API_KEY,
    )
except ImportError:
    API_KEYS = []
    SEARCH_CFG = {}
    APP_CFG = {}
    SYNC_CFG = {}
    GITHUB_REPO_URL = "https://github.com/egoffn1/BrawlNest"
    GITHUB_TOKEN = ""
    API_SERVER_URL = os.getenv("API_SERVER_URL", "http://130.12.46.224")
    BRAWLNEST_API_KEY = os.getenv("API_KEY", "")

from database import Database
from api_client import BrawlAPIClient
from collectors.player_collector import PlayerCollector
from collectors.club_collector import ClubCollector
from utils.logger import setup_logger
from utils.tag_generator import generate_tags
from sync_github import GitHubSync

PNG_AVAILABLE = False
try:
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image
    import io, numpy as np
    PNG_AVAILABLE = True
except ImportError:
    pass

console = Console(highlight=False)
logger  = setup_logger(__name__)

PT_STYLE = PTStyle.from_dict({
    "cursor":   "bold #f97316",
    "selected": "bold #ffffff",
    "item":     "#d1d5db",
    "dim":      "#4b5563",
    "prompt":   "bold #f97316",
})

MODE_NAMES = {
    "soloShowdown": "🌵 Соло-шоудаун", "duoShowdown": "👥 Дуо-шоудаун",
    "brawlBall": "⚽ Броулбол", "knockout": "🥊 Нокаут", "heist": "💰 Ограбление",
    "hotZone": "🔥 Горячая зона", "bounty": "🏆 Охота", "gemGrab": "💎 Кристаллы",
    "duels": "⚔️ Дуэли", "wipeout": "🧹 Зачистка", "basketBrawl": "🏀 Баскетбой",
    "roboRumble": "🤖 Роборамбо", "bossFight": "👾 Битва с боссом",
    "bigGame": "🐘 Большая игра", "siege": "🏰 Осада",
    "trioShowdown": "👥 Трио-шоудаун", "ranked": "🏆 Ранговый",
}
MAP_TRANS = {
    "Hard Rock Mine": "Хард-рок шахта", "Mushroom Meadow": "Грибная лощина",
    "Cavern Churn": "Штольня", "Snake Prairie": "Змеиные поля",
    "Feast or Famine": "Всё или ничего", "Out in the Open": "В чистом поле",
    "Center Stage": "Центровая площадка", "Crystal Cavern": "Кристальная пещера",
}

# ── Globals ───────────────────────────────────────────────────────────────────
db: Optional[Database] = None
api: Optional[BrawlAPIClient] = None
player_col: Optional[PlayerCollector] = None
club_col: Optional[ClubCollector] = None
search_mode = "offline"
HAS_BRAWL_KEYS = False
API_KEY = BRAWLNEST_API_KEY   # ключ для BrawlNest REST API
BASE_URL = API_SERVER_URL.rstrip("/")
SEARCH_MODE_FILE = "search_mode.txt"

# Menu position persistence file
MENU_POS_FILE = ".menu_pos"


def load_search_mode():
    global search_mode
    try:
        if os.path.exists(SEARCH_MODE_FILE):
            with open(SEARCH_MODE_FILE) as f:
                mode = f.read().strip()
                if mode in ("offline", "online"):
                    search_mode = mode
                    return
    except Exception:
        pass
    search_mode = APP_CFG.get("search_mode", "offline")


def save_search_mode(mode: str):
    global search_mode
    search_mode = mode
    try:
        with open(SEARCH_MODE_FILE, "w") as f:
            f.write(mode)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════
# BrawlNest REST API client
# ═══════════════════════════════════════════════════════════════════

async def _nest_get(path: str, params: Optional[Dict] = None) -> Optional[Any]:
    """GET к BrawlNest REST API."""
    if not API_KEY:
        return None
    url = f"{BASE_URL}{path}"
    headers = {"X-API-Key": API_KEY}
    if params is None:
        params = {}
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(url, headers=headers, params=params,
                                timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.debug(f"BrawlNest GET {path} → {resp.status}")
    except Exception as e:
        logger.debug(f"BrawlNest GET error {path}: {e}")
    return None


async def _nest_post(path: str, json_body: Optional[Dict] = None,
                     params: Optional[Dict] = None) -> Optional[Any]:
    """POST к BrawlNest REST API."""
    if not API_KEY:
        return None
    url = f"{BASE_URL}{path}"
    headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.post(url, headers=headers, json=json_body,
                                 params=params,
                                 timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status in (200, 201):
                    return await resp.json()
    except Exception as e:
        logger.debug(f"BrawlNest POST error {path}: {e}")
    return None


async def _nest_delete(path: str) -> bool:
    if not API_KEY:
        return False
    url = f"{BASE_URL}{path}"
    headers = {"X-API-Key": API_KEY}
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.delete(url, headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=10)) as resp:
                return resp.status in (200, 204)
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════
# Инициализация
# ═══════════════════════════════════════════════════════════════════

async def _init():
    global db, api, player_col, club_col, HAS_BRAWL_KEYS
    db = Database()
    try:
        await db.connect()
    except Exception as e:
        logger.warning(f"DB connect failed: {e}. Running without local DB.")
        db = None
    api = BrawlAPIClient()
    if db:
        player_col = PlayerCollector(api, db)
        club_col   = ClubCollector(api, db)
    HAS_BRAWL_KEYS = bool(API_KEYS)
    load_search_mode()


# ═══════════════════════════════════════════════════════════════════
# Output helpers
# ═══════════════════════════════════════════════════════════════════

def _hr(label: str = ""):
    console.print(Rule(f"  {label}  " if label else "", style="dim #374151"))

def _kv(key: str, val: str, ks: str = "dim", vs: str = "white"):
    console.print(f"  [bold {ks}]{key}[/bold {ks}]  [{vs}]{val}[/{vs}]")

def _ok(msg: str):  console.print(f"  [bold #22c55e]✓[/bold #22c55e]  {msg}")
def _err(msg: str): console.print(f"  [bold #ef4444]✗[/bold #ef4444]  {msg}")
def _info(msg: str): console.print(f"  [dim #9ca3af]{msg}[/dim #9ca3af]")

async def _press_enter_to_continue():
    """Показать подсказку и ждать нажатия Enter."""
    console.print("\n  [dim]Нажмите Enter, чтобы вернуться в меню...[/dim]")
    await asyncio.to_thread(input)


async def _ask(prompt: str, default: str = "") -> str:
    try:
        val = await asyncio.to_thread(input, f"  {prompt}: ")
        return (val.strip() or default).strip()
    except (KeyboardInterrupt, EOFError):
        return default


async def _ask_int(prompt: str, default: int) -> int:
    raw = await _ask(f"{prompt} [{default}]", str(default))
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


# ═══════════════════════════════════════════════════════════════════
# API Key management
# ═══════════════════════════════════════════════════════════════════

def _save_env_key(key: str):
    global API_KEY
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    content = ""
    if os.path.exists(env_path):
        with open(env_path) as f:
            content = f.read()
    lines = [l for l in content.splitlines() if not l.startswith("API_KEY=")]
    lines.append(f"API_KEY={key}")
    with open(env_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    API_KEY = key


async def ensure_api_key():
    global API_KEY
    if API_KEY:
        # validate
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(f"{BASE_URL}/ping",
                                    timeout=aiohttp.ClientTimeout(total=5)) as r:
                    if r.status == 200:
                        # Try validate key
                        async with sess.get(
                            f"{BASE_URL}/my_status",
                            params={"api_key": API_KEY},
                            timeout=aiohttp.ClientTimeout(total=5)
                        ) as r2:
                            if r2.status == 200:
                                return
        except Exception:
            pass

    console.print()
    _info(f"Подключение к BrawlNest API: {BASE_URL}")
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.post(
                f"{BASE_URL}/generate_key",
                json={"name": "CLI_User", "daily_limit": 10000},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    key = data.get("key", "")
                    if key:
                        _save_env_key(key)
                        _ok(f"API ключ создан и сохранён в .env")
                        return
        _err("Сервер BrawlNest недоступен. Некоторые функции будут ограничены.")
    except Exception as e:
        _err(f"Не удалось подключиться к {BASE_URL}: {e}")

    console.print()
    choice = await _ask("Введите API-ключ вручную (или Enter чтобы пропустить)", "")
    if choice:
        _save_env_key(choice)
        _ok("Ключ сохранён")


async def input_api_key_manual():
    key = await _ask("Введите BrawlNest API-ключ (или ключи Brawl Stars через запятую для прямого доступа)", "")
    if not key:
        return
    if len(key) > 20:  # BrawlNest key (long random string)
        _save_env_key(key)
        _ok("BrawlNest API ключ сохранён. Перезапустите программу.")
    else:
        # probably Brawl Stars key
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        content = ""
        if os.path.exists(env_path):
            with open(env_path) as f:
                content = f.read()
        lines = [l for l in content.splitlines() if not l.startswith("API_KEYS=")]
        lines.append(f"API_KEYS={key}")
        with open(env_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        _ok("Ключ Brawl Stars сохранён. Перезапустите программу.")


# ═══════════════════════════════════════════════════════════════════
# Rating helpers
# ═══════════════════════════════════════════════════════════════════

async def _add_rating(action_type: str, object_id: Optional[str] = None):
    if not API_KEY:
        return
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.post(
                f"{BASE_URL}/rating/add",
                headers={"X-API-Key": API_KEY},
                json={"action_type": action_type, "object_id": object_id},
                timeout=aiohttp.ClientTimeout(total=5)
            ) as r:
                pass
    except Exception:
        pass


async def _get_rating() -> int:
    data = await _nest_get("/rating/my")
    return (data or {}).get("rating", 0)


# ═══════════════════════════════════════════════════════════════════
# PLAYERS
# ═══════════════════════════════════════════════════════════════════

async def show_player(tag: str, force_update: bool = False):
    data = None
    tag_clean = tag.strip().upper().lstrip("#")

    # 1. BrawlNest REST API
    data = await _nest_get(f"/player/{tag_clean}")

    # 2. Direct Brawl API (if available and REST failed)
    if not data and HAS_BRAWL_KEYS and player_col:
        with console.status(f"[dim]Загрузка из Brawl API...[/dim]", spinner="dots"):
            data = await player_col.collect(tag_clean, force_update=force_update)

    if not data:
        _err(f"Игрок {tag_clean} не найден")
        await _press_enter_to_continue()
        return

    name     = data.get("name", "?")
    p_tag    = f"#{data.get('tag','').lstrip('#')}"
    trophies = data.get("trophies", 0)
    highest  = data.get("highestTrophies") or data.get("highest_trophies", "?")
    exp_lvl  = data.get("expLevel") or data.get("exp_level", "?")
    exp_pts  = data.get("expPoints") or data.get("exp_points", 0)
    w3       = data.get("3vs3Victories") or data.get("wins_3v3", 0)
    wsolo    = data.get("soloVictories") or data.get("wins_solo", 0)
    wduo     = data.get("duoVictories") or data.get("wins_duo", 0)
    club     = (data.get("club") or {})
    if isinstance(club, dict):
        club_tag = club.get("tag", "") or data.get("club_tag", "")
    else:
        club_tag = data.get("club_tag", "")
    club_disp = f"#{club_tag.lstrip('#')}" if club_tag else "[dim]—[/dim]"

    t = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
    t.add_column(style="bold #f97316", width=20)
    t.add_column(style="white")
    t.add_row("🏆 Трофеи",     f"{trophies} [dim](макс {highest})[/dim]")
    t.add_row("⭐ Уровень",    f"{exp_lvl} [dim]({exp_pts} XP)[/dim]")
    t.add_row("🥇 Победы 3x3", str(w3))
    t.add_row("🌵 Соло",       str(wsolo))
    t.add_row("👥 Дуо",        str(wduo))
    t.add_row("🏠 Клуб",       club_disp)
    console.print(Panel(t, title=f"[bold cyan]{name}[/bold cyan] [dim]{p_tag}[/dim]",
                         border_style="bright_blue", box=box.ROUNDED, padding=(0, 1)))
    console.print()
    await _add_rating("player_view", tag_clean)
    await _press_enter_to_continue()


async def show_player_history(tag: str, days: int = 30):
    tag_clean = tag.strip().upper().lstrip("#")
    data = await _nest_get(f"/player/{tag_clean}/history", {"days": days})
    if not data or not data.get("history"):
        _err("История трофеев не найдена")
        await _press_enter_to_continue()
        return
    console.print()
    _hr(f"📈 История трофеев · {tag_clean}")
    t = Table(box=box.MINIMAL, show_header=True, header_style="dim #9ca3af", padding=(0, 2))
    t.add_column("Дата", style="dim", min_width=12)
    t.add_column("Трофеи", justify="right", min_width=8)
    t.add_column("Изменение", justify="right", min_width=10)
    prev = None
    for entry in data["history"]:
        tr = entry.get("trophies", 0)
        delta = ""
        if prev is not None:
            diff = tr - prev
            delta = (f"[#4ade80]+{diff}[/#4ade80]" if diff > 0
                     else f"[#f87171]{diff}[/#f87171]" if diff < 0 else "[dim]0[/dim]")
        t.add_row(str(entry.get("date", "?")), f"[#4ade80]{tr}[/#4ade80]", delta)
        prev = tr
    console.print(t)
    _hr()
    console.print()
    await _press_enter_to_continue()


async def show_player_battles(tag: str, limit: int = 20):
    tag_clean = tag.strip().upper().lstrip("#")
    data = await _nest_get(f"/player/{tag_clean}/battles", {"limit": limit})
    if not data:
        _err("Бои не найдены")
        await _press_enter_to_continue()
        return
    battles = data.get("battles", [])
    if not battles:
        _info("Боевой лог пуст")
        await _press_enter_to_continue()
        return
    console.print()
    _hr(f"📜 Бои · {tag_clean}")
    t = Table(box=box.MINIMAL, show_header=True, header_style="dim #9ca3af", padding=(0, 2))
    t.add_column("Время", style="dim", min_width=16)
    t.add_column("Режим", min_width=22)
    t.add_column("Карта", style="dim", min_width=20)
    t.add_column("Результат", min_width=14)
    t.add_column("Δ", justify="right", min_width=5)
    for b in battles:
        bt   = str(b.get("battle_time", ""))[:16]
        mode = b.get("game_mode") or b.get("battle_type", "?")
        mname= MODE_NAMES.get(mode, mode)
        mmap = MAP_TRANS.get(b.get("map_name", ""), b.get("map_name", ""))
        res  = b.get("result", "?")
        tch  = b.get("trophies_change")
        res_s= ("[#4ade80]✔ Победа[/#4ade80]" if res == "victory"
                else "[#f87171]✘ Поражение[/#f87171]" if res == "defeat"
                else f"[dim]{res}[/dim]")
        tch_s= (f"[#4ade80]+{tch}[/#4ade80]" if tch and tch > 0
                else f"[#f87171]{tch}[/#f87171]" if tch and tch < 0 else "[dim]—[/dim]")
        t.add_row(bt, mname, mmap, res_s, tch_s)
    console.print(t)
    _hr()
    console.print()
    await _add_rating("battles_view", tag_clean)
    await _press_enter_to_continue()


async def show_player_battles_stats(tag: str):
    tag_clean = tag.strip().upper().lstrip("#")
    data = await _nest_get(f"/player/{tag_clean}/battles/stats")
    if not data:
        _err("Статистика боёв не найдена")
        await _press_enter_to_continue()
        return
    console.print()
    _hr(f"📊 Статистика боёв · {tag_clean}")
    _kv("Всего боёв", str(data.get("total_battles", 0)))
    _kv("Побед",      str(data.get("total_wins", 0)))
    total = data.get("total_battles", 1)
    wins  = data.get("total_wins", 0)
    wr    = round(wins / total * 100, 1) if total else 0
    _kv("Винрейт",    f"{wr}%")
    by_mode = data.get("by_mode", [])
    if by_mode:
        console.print()
        _hr("По режимам")
        t = Table(box=box.MINIMAL, header_style="dim #9ca3af", padding=(0, 2))
        t.add_column("Режим", min_width=22)
        t.add_column("Боёв", justify="right")
        t.add_column("Побед", justify="right")
        for m in by_mode:
            t.add_row(MODE_NAMES.get(m.get("game_mode", ""), m.get("game_mode", "?")),
                      str(m.get("total", 0)), str(m.get("wins", 0)))
        console.print(t)
    _hr()
    console.print()
    await _press_enter_to_continue()


async def show_player_brawlers(tag: str):
    tag_clean = tag.strip().upper().lstrip("#")
    data = await _nest_get(f"/player/{tag_clean}/brawlers")
    if not data:
        _err("Данные о бравлерах не найдены")
        await _press_enter_to_continue()
        return
    brawlers = data.get("brawlers", [])
    if not brawlers:
        _info("Список бравлеров пуст")
        await _press_enter_to_continue()
        return
    console.print()
    _hr(f"🤖 Бравлеры · {tag_clean}")
    t = Table(box=box.MINIMAL, header_style="dim #9ca3af", padding=(0, 2))
    t.add_column("Имя", min_width=18)
    t.add_column("Трофеи", justify="right")
    t.add_column("Макс", justify="right")
    t.add_column("Сила", justify="right")
    t.add_column("Ранг", justify="right")
    for b in sorted(brawlers, key=lambda x: x.get("trophies", 0), reverse=True):
        t.add_row(
            b.get("brawler_name", "?"),
            f"[#4ade80]{b.get('trophies', 0)}[/#4ade80]",
            str(b.get("highest_trophies", 0)),
            str(b.get("power", 1)),
            str(b.get("rank", 1)),
        )
    console.print(t)
    _hr()
    console.print()
    await _add_rating("brawlers_view", tag_clean)
    await _press_enter_to_continue()


async def show_player_mastery(tag: str):
    tag_clean = tag.strip().upper().lstrip("#")
    data = await _nest_get(f"/player/{tag_clean}/mastery")
    if not data:
        _err("Мастерство не найдено")
        await _press_enter_to_continue()
        return
    mastery = data.get("mastery", [])
    if not mastery:
        _info("Нет данных мастерства (требуется официальный API)")
        await _press_enter_to_continue()
        return
    console.print()
    _hr(f"⭐ Мастерство бравлеров · {tag_clean}")
    t = Table(box=box.MINIMAL, header_style="dim #9ca3af", padding=(0, 2))
    t.add_column("ID бравлера", style="dim")
    t.add_column("Уровень мастерства")
    t.add_column("Очки мастерства", justify="right")
    for m in mastery:
        t.add_row(str(m.get("brawler_id", "?")),
                  str(m.get("mastery_level", "?")),
                  f"[#facc15]{m.get('mastery_points', 0)}[/#facc15]")
    console.print(t)
    _hr()
    console.print()
    await _press_enter_to_continue()


async def compare_players():
    tags_raw = await _ask("Теги игроков через запятую (2-3 игрока)")
    if not tags_raw:
        return
    tags = [t.strip().upper().lstrip("#") for t in tags_raw.split(",") if t.strip()]
    if len(tags) < 2:
        _err("Нужно минимум 2 тега")
        await _press_enter_to_continue()
        return
    data = await _nest_get("/compare/players", {"tags": ",".join(tags)})
    if not data or not data.get("players"):
        _err("Не удалось сравнить игроков")
        await _press_enter_to_continue()
        return
    console.print()
    _hr("⚔️ Сравнение игроков")
    t = Table(box=box.MINIMAL, header_style="dim #9ca3af", padding=(0, 2))
    t.add_column("Показатель", style="dim", min_width=18)
    players = data["players"]
    for p in players:
        t.add_column(p.get("name", "?"), justify="right", min_width=12)
    fields = [
        ("trophies", "🏆 Трофеи"),
        ("highestTrophies", "📈 Макс трофеев"),
        ("expLevel", "⭐ Уровень"),
        ("3vs3Victories", "🥇 Победы 3x3"),
        ("soloVictories", "🌵 Победы соло"),
        ("duoVictories", "👥 Победы дуо"),
    ]
    for field, label in fields:
        row = [label]
        best = max((p.get(field, 0) or 0 for p in players), default=0)
        for p in players:
            val = p.get(field, 0) or 0
            row.append(f"[#4ade80]{val}[/#4ade80]" if val == best and best > 0 else str(val))
        t.add_row(*row)
    console.print(t)
    _hr()
    console.print()
    await _press_enter_to_continue()


# ═══════════════════════════════════════════════════════════════════
# CLUBS
# ═══════════════════════════════════════════════════════════════════

async def show_club(tag: str, show_members: bool = False):
    tag_clean = tag.strip().upper().lstrip("#")
    data = await _nest_get(f"/club/{tag_clean}")
    if not data and HAS_BRAWL_KEYS and club_col:
        with console.status("[dim]Загрузка клуба...[/dim]", spinner="dots"):
            data = await club_col.collect(tag_clean)
    if not data:
        _err(f"Клуб {tag_clean} не найден")
        await _press_enter_to_continue()
        return
    console.print()
    name = data.get("name", "?")
    ctag = f"#{data.get('tag','').lstrip('#')}"
    _hr(f"🏢 {name} {ctag}")
    _kv("🏆 Трофеи",      str(data.get("trophies", 0)), "dim", "#4ade80")
    _kv("📜 Треб. трофеев", str(data.get("requiredTrophies") or data.get("required_trophies", "?")))
    _kv("👥 Участников",   str(data.get("membersCount") or data.get("members_count", "?")))
    _kv("🏷️ Тип",          str(data.get("type", "?")))
    if data.get("description"):
        _kv("📝 Описание",  data["description"][:80])
    _hr()
    console.print()

    if show_members:
        members = data.get("members", [])
        if not members and db:
            members = await db.get_club_members(tag_clean)
        if members:
            _hr(f"👥 Участники ({len(members)})")
            t = Table(box=box.MINIMAL, header_style="dim #9ca3af", padding=(0, 2))
            t.add_column("#", justify="right", style="dim", min_width=3)
            t.add_column("Имя", min_width=18)
            t.add_column("Тег", style="#67e8f9", min_width=12)
            t.add_column("Роль", style="dim", min_width=12)
            t.add_column("🏆", justify="right", min_width=8)
            for i, m in enumerate(members, 1):
                mtag = m.get("tag") or m.get("player_tag", "?")
                t.add_row(str(i), m.get("name","?"), mtag,
                           m.get("role","—"), f"[#4ade80]{m.get('trophies',0)}[/#4ade80]")
            console.print(t)
            _hr()
            console.print()
    await _add_rating("club_view", tag_clean)
    await _press_enter_to_continue()


async def show_club_history(tag: str, days: int = 30):
    tag_clean = tag.strip().upper().lstrip("#")
    data = await _nest_get(f"/club/{tag_clean}/history", {"days": days})
    if not data or not data.get("history"):
        _err("История клуба не найдена")
        await _press_enter_to_continue()
        return
    console.print()
    _hr(f"📈 История клуба · {tag_clean}")
    t = Table(box=box.MINIMAL, header_style="dim #9ca3af", padding=(0, 2))
    t.add_column("Дата", style="dim")
    t.add_column("Трофеи", justify="right")
    t.add_column("Участников", justify="right")
    t.add_column("Треб.", justify="right")
    for e in data["history"]:
        t.add_row(str(e.get("date","?")),
                  f"[#4ade80]{e.get('trophies',0)}[/#4ade80]",
                  str(e.get("member_count","?")),
                  str(e.get("required_trophies","?")))
    console.print(t)
    _hr()
    console.print()
    await _press_enter_to_continue()


# ═══════════════════════════════════════════════════════════════════
# SEARCH
# ═══════════════════════════════════════════════════════════════════

async def search_players_by_name():
    name = await _ask("Имя игрока (часть)")
    if not name:
        return
    data = await _nest_get("/search/players", {"name": name, "limit": 50})
    results = (data or {}).get("results", [])
    if not results and db:
        results = await db.search_players_by_name(name, limit=50)
    if not results:
        _err(f"Игроки с именем '{name}' не найдены")
        await _press_enter_to_continue()
        return
    console.print()
    _hr(f"🔍 Поиск игроков: {name}")
    t = Table(box=box.MINIMAL, header_style="dim #9ca3af", padding=(0, 2))
    t.add_column("#", justify="right", style="dim", min_width=3)
    t.add_column("Тег", style="#67e8f9", min_width=12)
    t.add_column("Имя", min_width=20)
    t.add_column("Трофеи", justify="right")
    for i, p in enumerate(results[:30], 1):
        t.add_row(str(i), p.get("tag","?"), p.get("name","?"),
                   f"[#4ade80]{p.get('trophies',0)}[/#4ade80]")
    console.print(t)
    _hr()
    console.print()
    await _add_rating("search_name", name)
    await _press_enter_to_continue()


async def search_clubs_by_name():
    name = await _ask("Название клуба (часть)")
    if not name:
        return
    data = await _nest_get("/search/clubs", {"name": name, "limit": 30})
    results = (data or {}).get("results", [])
    if not results and db:
        results = await db.search_clubs_by_name(name, limit=30)
    if not results:
        _err(f"Клубы с названием '{name}' не найдены")
        await _press_enter_to_continue()
        return
    console.print()
    _hr(f"🔍 Поиск клубов: {name}")
    t = Table(box=box.MINIMAL, header_style="dim #9ca3af", padding=(0, 2))
    t.add_column("#", justify="right", style="dim", min_width=3)
    t.add_column("Тег", style="#67e8f9", min_width=12)
    t.add_column("Название", min_width=20)
    t.add_column("Трофеи", justify="right")
    t.add_column("Участников", justify="right")
    for i, c in enumerate(results, 1):
        t.add_row(str(i), c.get("tag","?"), c.get("name","?"),
                   f"[#4ade80]{c.get('trophies',0)}[/#4ade80]",
                   str(c.get("members_count", c.get("membersCount",0))))
    console.print(t)
    _hr()
    console.print()
    await _add_rating("search_club_name", name)
    await _press_enter_to_continue()


async def advanced_search_menu():
    query = await _ask("Поисковый запрос")
    if not query:
        return
    stype = await _ask("Тип поиска (players/clubs) [players]", "players")
    sort  = await _ask("Сортировать по (trophies/name) [trophies]", "trophies")
    order = await _ask("Порядок (asc/desc) [desc]", "desc")
    limit = await _ask_int("Количество результатов", 20)
    data  = await _nest_get("/search/advanced", {
        "query": query, "type": stype, "sort_by": sort, "order": order, "limit": limit
    })
    if not data or not data.get("results"):
        _err("Ничего не найдено")
        await _press_enter_to_continue()
        return
    console.print()
    _hr(f"🔍 Расширенный поиск: {query}")
    t = Table(box=box.MINIMAL, header_style="dim #9ca3af", padding=(0, 2))
    t.add_column("#", justify="right", style="dim")
    t.add_column("Тег", style="#67e8f9")
    t.add_column("Имя", min_width=20)
    t.add_column("Трофеи", justify="right")
    for i, r in enumerate(data["results"], 1):
        t.add_row(str(i), r.get("tag","?"), r.get("name","?"),
                   f"[#4ade80]{r.get('trophies',0)}[/#4ade80]")
    console.print(t)
    _hr()
    console.print()
    await _press_enter_to_continue()


# ═══════════════════════════════════════════════════════════════════
# MAPS & TEAMS
# ═══════════════════════════════════════════════════════════════════

async def show_maps(limit: int = 30):
    data = await _nest_get("/maps", {"limit": limit})
    if not data or not data.get("maps"):
        _err("Статистика карт недоступна (нужны данные о боях)")
        await _press_enter_to_continue()
        return
    console.print()
    _hr("🗺️ Статистика карт")
    t = Table(box=box.MINIMAL, header_style="dim #9ca3af", padding=(0, 2))
    t.add_column("Карта", min_width=22)
    t.add_column("Режим", min_width=18)
    t.add_column("Боёв", justify="right")
    t.add_column("Побед", justify="right")
    t.add_column("Винрейт", justify="right")
    for m in data["maps"]:
        wr = m.get("win_rate", 0)
        t.add_row(
            MAP_TRANS.get(m.get("map_name","?"), m.get("map_name","?")),
            m.get("game_mode","?"),
            str(m.get("total_battles",0)),
            str(m.get("total_wins",0)),
            f"[#4ade80]{wr:.1f}%[/#4ade80]" if wr >= 50 else f"[#f87171]{wr:.1f}%[/#f87171]",
        )
    console.print(t)
    _hr()
    console.print()
    await _add_rating("rotation_view")
    await _press_enter_to_continue()


async def show_map_stats():
    map_name = await _ask("Название карты (на английском)")
    if not map_name:
        return
    data = await _nest_get(f"/maps/{map_name}")
    if not data:
        _err(f"Статистика для '{map_name}' не найдена")
        await _press_enter_to_continue()
        return
    console.print()
    _hr(f"🗺️ {MAP_TRANS.get(map_name, map_name)}")
    stats = data.get("stats", data)
    _kv("Всего боёв",    str(stats.get("total_battles", 0)))
    _kv("Побед",         str(stats.get("total_wins", 0)))
    _kv("Винрейт",       f"{stats.get('win_rate', 0):.1f}%")
    _kv("Ср. изм. трофеев", f"{stats.get('avg_trophies_change', 0):.1f}")
    _hr()
    console.print()
    await _press_enter_to_continue()


async def show_team_stats():
    tags_raw = await _ask("Теги игроков через запятую (2-3)")
    if not tags_raw:
        return
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    if not (2 <= len(tags) <= 3):
        _err("Нужно 2-3 тега")
        await _press_enter_to_continue()
        return
    data = await _nest_get("/team/stats", {"tags": ",".join(tags)})
    if not data or data.get("total_battles", 0) == 0:
        _info("Нет данных о командной игре для этих игроков")
        await _press_enter_to_continue()
        return
    console.print()
    _hr("🎮 Статистика команды")
    _kv("Боёв вместе", str(data.get("total_battles", 0)))
    _kv("Побед",       str(data.get("total_wins", 0)))
    _kv("Винрейт",     f"{data.get('win_rate', 0):.1f}%")
    if data.get("last_updated"):
        _kv("Обновлено", str(data["last_updated"])[:19])
    _hr()
    console.print()
    await _add_rating("check_team")
    await _press_enter_to_continue()


# ═══════════════════════════════════════════════════════════════════
# RANKINGS
# ═══════════════════════════════════════════════════════════════════

async def show_rankings_players(limit: int = 20):
    data = await _nest_get("/rankings/players", {"limit": limit})
    if not data or not data.get("players"):
        # fallback to direct API
        if HAS_BRAWL_KEYS and api:
            data2 = await api.get_rankings_players()
            if data2 and "items" in data2:
                console.print()
                _hr("🏆 Топ игроков (Brawl Stars global)")
                t = Table(box=box.MINIMAL, header_style="dim #9ca3af", padding=(0, 2))
                t.add_column("#", justify="right", style="dim")
                t.add_column("Имя")
                t.add_column("Тег", style="#67e8f9")
                t.add_column("Трофеи", justify="right")
                for i, p in enumerate(data2["items"][:limit], 1):
                    t.add_row(str(i), p.get("name","?"), p.get("tag","?"),
                               f"[#4ade80]{p.get('trophies',0)}[/#4ade80]")
                console.print(t); _hr(); console.print()
                await _press_enter_to_continue()
                return
        _err("Данные рейтинга недоступны")
        await _press_enter_to_continue()
        return
    console.print()
    _hr("🏆 Топ игроков (BrawlNest)")
    t = Table(box=box.MINIMAL, header_style="dim #9ca3af", padding=(0, 2))
    t.add_column("#", justify="right", style="dim")
    t.add_column("Тег", style="#67e8f9")
    t.add_column("Трофеи", justify="right")
    t.add_column("Дата", style="dim")
    for i, p in enumerate(data["players"], 1):
        t.add_row(str(i), p.get("player_tag", p.get("tag", "?")),
                   f"[#4ade80]{p.get('trophies',0)}[/#4ade80]",
                   str(p.get("date", ""))[:10])
    console.print(t); _hr(); console.print()
    await _add_rating("rankings_view")
    await _press_enter_to_continue()


async def show_rankings_clubs(limit: int = 20):
    data = await _nest_get("/rankings/clubs", {"limit": limit})
    if not data or not data.get("clubs"):
        if HAS_BRAWL_KEYS and api:
            data2 = await api.get_rankings_clubs()
            if data2 and "items" in data2:
                console.print()
                _hr("🏅 Топ клубов (Brawl Stars global)")
                t = Table(box=box.MINIMAL, header_style="dim #9ca3af", padding=(0, 2))
                t.add_column("#", justify="right", style="dim")
                t.add_column("Название")
                t.add_column("Тег", style="#67e8f9")
                t.add_column("Трофеи", justify="right")
                t.add_column("Участников", justify="right")
                for i, c in enumerate(data2["items"][:limit], 1):
                    t.add_row(str(i), c.get("name","?"), c.get("tag","?"),
                               f"[#4ade80]{c.get('trophies',0)}[/#4ade80]",
                               str(c.get("memberCount", 0)))
                console.print(t); _hr(); console.print()
                await _press_enter_to_continue()
                return
        _err("Данные рейтинга клубов недоступны")
        await _press_enter_to_continue()
        return
    console.print()
    _hr("🏅 Топ клубов (BrawlNest)")
    t = Table(box=box.MINIMAL, header_style="dim #9ca3af", padding=(0, 2))
    t.add_column("#", justify="right", style="dim")
    t.add_column("Название")
    t.add_column("Тег", style="#67e8f9")
    t.add_column("Трофеи", justify="right")
    for i, c in enumerate(data["clubs"], 1):
        t.add_row(str(i), c.get("name","?"), c.get("tag","?"),
                   f"[#4ade80]{c.get('trophies',0)}[/#4ade80]")
    console.print(t); _hr(); console.print()
    await _add_rating("rankings_view")
    await _press_enter_to_continue()


# ═══════════════════════════════════════════════════════════════════
# BRAWLERS
# ═══════════════════════════════════════════════════════════════════

async def show_brawlers():
    data = await _nest_get("/brawlers")
    if not data or not data.get("brawlers"):
        if HAS_BRAWL_KEYS and api:
            data = await api.get_brawlers()
            if data and "items" in data:
                data = {"brawlers": [{"id": b["id"], "name": b["name"]} for b in data["items"]]}
    if not data or not data.get("brawlers"):
        _err("Список бравлеров недоступен")
        await _press_enter_to_continue()
        return
    console.print()
    _hr("🤖 Бравлеры")
    t = Table(box=box.MINIMAL, header_style="dim #9ca3af", padding=(0, 2))
    t.add_column("ID", justify="right", style="dim", min_width=10)
    t.add_column("Имя", min_width=20)
    for b in data["brawlers"]:
        t.add_row(str(b.get("id","?")), b.get("name","?"))
    console.print(t); _hr(); console.print()
    await _add_rating("brawlers_view")
    await _press_enter_to_continue()


async def show_brawler_rankings(brawler_id: Optional[int] = None):
    if brawler_id is None:
        brawler_id = await _ask_int("ID бравлера (например 16000000 = Shelly)", 16000000)
    data = await _nest_get(f"/brawlers/{brawler_id}/rankings", {"limit": 20})
    if not data or not data.get("rankings"):
        _err("Рейтинг по бравлеру не найден")
        await _press_enter_to_continue()
        return
    console.print()
    _hr(f"🏆 Топ по бравлеру {brawler_id}")
    t = Table(box=box.MINIMAL, header_style="dim #9ca3af", padding=(0, 2))
    t.add_column("#", justify="right", style="dim")
    t.add_column("Тег", style="#67e8f9")
    t.add_column("Трофеи", justify="right")
    for i, r in enumerate(data["rankings"], 1):
        t.add_row(str(i), r.get("player_tag","?"), f"[#4ade80]{r.get('trophies',0)}[/#4ade80]")
    console.print(t); _hr(); console.print()
    await _press_enter_to_continue()


# ═══════════════════════════════════════════════════════════════════
# GAME CONTENT (direct Brawl API)
# ═══════════════════════════════════════════════════════════════════

async def show_event_rotation():
    if not HAS_BRAWL_KEYS:
        _err("Нет ключей Brawl Stars API. Добавьте API_KEYS в .env")
        await _press_enter_to_continue()
        return
    if not api:
        _err("API клиент не инициализирован")
        await _press_enter_to_continue()
        return
    with console.status("[dim]Загрузка ротации...[/dim]", spinner="dots"):
        data = await api.get_event_rotation()
    if not data:
        _err("Не удалось загрузить ротацию")
        await _press_enter_to_continue()
        return
    events = data if isinstance(data, list) else data.get("active", data.get("items", []))
    if not events:
        _err("Нет активных событий")
        await _press_enter_to_continue()
        return
    console.print()
    _hr("🎡 Ротация событий")
    t = Table(box=box.MINIMAL, header_style="dim #9ca3af", padding=(0, 2))
    t.add_column("Слот", justify="right", style="dim")
    t.add_column("Режим", min_width=22)
    t.add_column("Карта", style="dim", min_width=20)
    t.add_column("До", style="dim")
    for ev in events:
        slot  = ev.get("slotId", ev.get("slot", "?"))
        evinfo= ev.get("event", ev)
        mode  = evinfo.get("mode", "?")
        mmap  = evinfo.get("map", "?")
        end   = ev.get("endTime", "")
        try:
            if "T" in end:
                dt = datetime.fromisoformat(end.replace("Z","+00:00"))
                end = dt.strftime("%d.%m %H:%M")
            else:
                end = end[:16]
        except Exception:
            end = end[:16]
        t.add_row(str(slot), MODE_NAMES.get(mode, mode), MAP_TRANS.get(mmap, mmap), end)
    console.print(t); _hr(); console.print()
    await _add_rating("rotation_view")
    await _press_enter_to_continue()


async def show_global_rankings(kind: str = "players"):
    if not HAS_BRAWL_KEYS:
        _err("Нет ключей Brawl Stars API")
        await _press_enter_to_continue()
        return
    if not api:
        _err("API клиент не инициализирован")
        await _press_enter_to_continue()
        return
    region = await _ask("Регион [global]", "global")
    fn = api.get_rankings_players if kind == "players" else api.get_rankings_clubs
    with console.status(f"[dim]Загрузка рейтинга...[/dim]", spinner="dots"):
        data = await fn(region)
    if not data or "items" not in data:
        _err("Не удалось загрузить рейтинг")
        await _press_enter_to_continue()
        return
    console.print()
    _hr(f"🏆 Топ {kind} · {region}")
    t = Table(box=box.MINIMAL, header_style="dim #9ca3af", padding=(0, 2))
    t.add_column("#", justify="right", style="dim")
    t.add_column("Имя")
    t.add_column("Тег", style="#67e8f9")
    t.add_column("Трофеи", justify="right")
    if kind == "clubs":
        t.add_column("Участников", justify="right")
    for i, item in enumerate(data["items"][:25], 1):
        row = [str(i), item.get("name","?"), item.get("tag","?"),
               f"[#4ade80]{item.get('trophies',0)}[/#4ade80]"]
        if kind == "clubs":
            row.append(str(item.get("memberCount",0)))
        t.add_row(*row)
    console.print(t); _hr(); console.print()
    await _add_rating("rankings_view", region)
    await _press_enter_to_continue()


async def show_powerplay_seasons():
    if not HAS_BRAWL_KEYS:
        _err("Нет ключей Brawl Stars API")
        await _press_enter_to_continue()
        return
    if not api:
        _err("API клиент не инициализирован")
        await _press_enter_to_continue()
        return
    region = await _ask("Регион [global]", "global")
    with console.status("[dim]Загрузка сезонов...[/dim]", spinner="dots"):
        data = await api.get_powerplay_seasons(region)
    if not data or "items" not in data:
        _err("Нет данных Power Play")
        await _press_enter_to_continue()
        return
    console.print()
    _hr(f"⚡ Сезоны Power Play · {region}")
    t = Table(box=box.MINIMAL, header_style="dim #9ca3af", padding=(0, 2))
    t.add_column("ID", style="dim")
    t.add_column("Название")
    t.add_column("Начало", style="dim")
    t.add_column("Конец", style="dim")
    for s in data["items"]:
        t.add_row(str(s.get("id","?")), s.get("name","?"),
                   str(s.get("startTime",""))[:10], str(s.get("endTime",""))[:10])
    console.print(t); _hr(); console.print()
    await _add_rating("powerplay_view", region)
    await _press_enter_to_continue()


async def show_locations():
    if not HAS_BRAWL_KEYS:
        _err("Нет ключей Brawl Stars API")
        await _press_enter_to_continue()
        return
    if not api:
        _err("API клиент не инициализирован")
        await _press_enter_to_continue()
        return
    with console.status("[dim]Загрузка локаций...[/dim]", spinner="dots"):
        data = await api.get_locations()
    if not data or "items" not in data:
        _err("Не удалось загрузить локации")
        await _press_enter_to_continue()
        return
    console.print()
    _hr("🌍 Список стран")
    t = Table(box=box.MINIMAL, header_style="dim #9ca3af", padding=(0, 2))
    t.add_column("Код", style="#67e8f9", min_width=8)
    t.add_column("Название")
    for loc in data["items"]:
        t.add_row(loc.get("id","?"), loc.get("name","?"))
    console.print(t); _hr(); console.print()
    await _add_rating("locations_view")
    await _press_enter_to_continue()


# ═══════════════════════════════════════════════════════════════════
# TEAM CODES
# ═══════════════════════════════════════════════════════════════════

async def generate_team_code():
    duration = await _ask_int("Время жизни кода в секундах (10-300)", 120)
    duration = max(10, min(300, duration))
    data = await _nest_post("/generate_team_code", {"duration_seconds": duration})
    if not data or not data.get("code"):
        _err("Не удалось сгенерировать код (API недоступен)")
        await _press_enter_to_continue()
        return
    console.print()
    _hr("🔑 Код команды создан")
    _kv("Код",        f"[bold #facc15]{data['code']}[/bold #facc15]", "dim", "#facc15")
    _kv("Истекает",   str(data.get("expires_at","?"))[:19])
    _kv("Длительность", f"{duration} сек")
    _hr()
    console.print()
    await _add_rating("generate_codes")
    await _press_enter_to_continue()


async def check_team_code():
    code = await _ask("Код команды (например XSJ2Z4T)")
    if not code:
        return
    code = code.upper().strip()
    data = await _nest_get(f"/team_code/{code}")
    if not data:
        _err("Не удалось проверить код")
        await _press_enter_to_continue()
        return
    console.print()
    _hr(f"🔑 Код {code}")
    if data.get("active"):
        _ok(f"Код [bold #facc15]{code}[/bold #facc15] активен")
        _kv("Истекает", str(data.get("expires_at","?"))[:19])
        _kv("Создан",   str(data.get("created_at","?"))[:19])
    else:
        _err(f"Код {code} неактивен или не существует")
    _hr()
    console.print()
    await _press_enter_to_continue()


# ═══════════════════════════════════════════════════════════════════
# TEAM CODES - Local Generation (Brawl Stars style)
# ═══════════════════════════════════════════════════════════════════

import random
import string
from datetime import timedelta

# Base25 charset: 0-9, A-Z excluding I and O
BASE25_CHARS = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"

def generate_brawl_code(length: int = 7) -> str:
    """Генерирует код команды в стиле Brawl Stars.
    
    Спецификация:
    - Префикс: XM
    - Символы: Base25 (0-9, A-Z, исключая I и O)
    - Длина: 7, 8 или 9 символов (без префикса)
    """
    length = max(7, min(9, length))  # Ограничиваем длину 7-9
    random_part = ''.join(random.choices(BASE25_CHARS, k=length))
    return f"XM{random_part}"

async def generate_team_codes_cli(count: int = None):
    """CLI команда для генерации кодов команды с сохранением в БД и Git."""
    from database import Database
    
    if count is None:
        count = await _ask_int("Количество кодов для генерации (1-20)", 5)
    count = max(1, min(20, count))
    
    db = Database()
    await db.connect()
    
    generated_codes = []
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(hours=10)).isoformat()  # Ровно 10 часов
    
    console.print()
    _hr(f"🔑 Генерация {count} кодов команды")
    
    with Progress(TextColumn("[progress.description]{task.description}"), 
                  BarColumn(), TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                  console=console, transient=True) as progress:
        task = progress.add_task("[cyan]Генерация кодов...", total=count)
        
        for i in range(count):
            # Пробуем сгенерировать уникальный код
            max_attempts = 10
            for attempt in range(max_attempts):
                code = generate_brawl_code(random.choice([7, 8, 9]))
                
                # Проверяем на дубликаты в БД
                if not await db.exists_active_team_code(code):
                    # Сохраняем в БД
                    await db.insert_team_code(code, expires_at, creator="cli")
                    generated_codes.append({
                        "code": code,
                        "created_at": now.isoformat(),
                        "expires_at": expires_at,
                        "is_used": False
                    })
                    break
                
            progress.advance(task)
    
    await db.close()
    
    if generated_codes:
        _ok(f"Сгенерировано {len(generated_codes)} кодов")
        console.print()
        
        # Выводим сгенерированные коды
        t = Table(box=box.MINIMAL, show_header=True, header_style="dim")
        t.add_column("#", style="dim")
        t.add_column("Код", style="bold #facc15")
        t.add_column("Истекает", style="dim")
        
        for idx, code_data in enumerate(generated_codes, 1):
            exp_str = code_data["expires_at"][:19].replace("T", " ")
            t.add_row(str(idx), code_data["code"], exp_str)
        
        console.print(t)
        console.print()
        
        # Экспорт в JSON для Git
        try:
            gh_sync = GitHubSync()
            await gh_sync.export_team_codes(generated_codes)
            gh_sync.commit_and_push(f"Add {len(generated_codes)} team codes")
            _info("Коды экспортированы в GitHub")
        except Exception as e:
            _info(f"Экспорт в GitHub: {e}")
        
        await _add_rating("generate_codes")
    else:
        _err("Не удалось сгенерировать коды (возможно все комбинации заняты)")
    
    _hr()
    console.print()
    await _press_enter_to_continue()

async def list_team_codes():
    """CLI команда для просмотра активных кодов."""
    from database import Database
    
    db = Database()
    await db.connect()
    
    codes = await db.get_active_team_codes()
    await db.close()
    
    console.print()
    _hr(f"📋 Активные коды команды ({len(codes)})")
    
    if not codes:
        _info("Нет активных кодов")
    else:
        t = Table(box=box.MINIMAL, show_header=True, header_style="dim")
        t.add_column("Код", style="bold #facc15")
        t.add_column("Создан", style="dim")
        t.add_column("Истекает", style="dim")
        t.add_column("Автор", style="dim")
        
        for code in codes:
            created = code.get("created_at", "?")[:19].replace("T", " ")
            expires = code.get("expires_at", "?")[:19].replace("T", " ")
            creator = code.get("creator", "-")
            t.add_row(code["code"], created, expires, creator or "-")
        
        console.print(t)
    
    _hr()
    console.print()
    await _press_enter_to_continue()

async def cleanup_expired_codes():
    """CLI команда для очистки истекших кодов."""
    from database import Database
    
    db = Database()
    await db.connect()
    
    deleted_count = await db.cleanup_expired_team_codes()
    await db.close()
    
    console.print()
    _hr("🧹 Очистка старых кодов")
    
    if deleted_count > 0:
        _ok(f"Удалено {deleted_count} истекших кодов")
        
        # Синхронизация с Git после очистки
        try:
            gh_sync = GitHubSync()
            # Обновляем exported файл
            active_codes = await db.get_active_team_codes()
            await gh_sync.export_team_codes(active_codes)
            gh_sync.commit_and_push(f"Cleanup expired team codes (-{deleted_count})")
            _info("Изменения отправлены в GitHub")
        except Exception as e:
            _info(f"Синхронизация с GitHub: {e}")
    else:
        _info("Нет истекших кодов для удаления")
    
    _hr()
    console.print()
    await _press_enter_to_continue()


# ═══════════════════════════════════════════════════════════════════
# NODES / NETWORK
# ═══════════════════════════════════════════════════════════════════

async def show_nodes():
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(f"{BASE_URL}/nodes",
                                timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                else:
                    data = None
    except Exception:
        data = None
    if not data:
        _err("Не удалось получить список узлов сети")
        await _press_enter_to_continue()
        return
    console.print()
    _hr("🌐 Активные узлы сети BrawlNest")
    _kv("Текущий узел", data.get("current_node","?"))
    nodes = data.get("nodes", [])
    if nodes:
        t = Table(box=box.MINIMAL, header_style="dim #9ca3af", padding=(0, 2))
        t.add_column("ID", style="dim")
        t.add_column("Адрес", style="#67e8f9")
        t.add_column("Пинг мс", justify="right")
        t.add_column("Последнее обновление", style="dim")
        for n in nodes:
            ts = n.get("last_updated", 0)
            ts_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "?"
            ping = n.get("ping_ms", 0)
            ping_s = (f"[#4ade80]{ping}[/#4ade80]" if ping < 50
                       else f"[#facc15]{ping}[/#facc15]" if ping < 200
                       else f"[#f87171]{ping}[/#f87171]")
            t.add_row(n.get("node_id","?"), n.get("address","?"), ping_s, ts_str)
        console.print(t)
    else:
        _info("Других активных узлов нет")
    _hr()
    console.print()
    await _press_enter_to_continue()


# ═══════════════════════════════════════════════════════════════════
# RATING
# ═══════════════════════════════════════════════════════════════════

async def show_my_rating():
    rating = await _get_rating()
    data = await _nest_get("/rating/leaderboard", {"limit": 5})
    console.print()
    _hr("⭐ Мой рейтинг")
    _kv("Очки", f"[bold #facc15]{rating}[/bold #facc15]")
    _info("Очки начисляются за просмотр игроков, поиск, создание PNG, сбор данных и т.д.")
    if data and data.get("leaderboard"):
        console.print()
        _hr("🏆 Топ-5 рейтинга")
        t = Table(box=box.MINIMAL, header_style="dim #9ca3af", padding=(0, 2))
        t.add_column("#", justify="right", style="dim")
        t.add_column("Ключ (первые 8)", style="dim")
        t.add_column("Очки", justify="right")
        for i, entry in enumerate(data["leaderboard"], 1):
            key_short = (entry.get("api_key","?") or "?")[:8] + "..."
            t.add_row(str(i), key_short, f"[#facc15]{entry.get('rating',0)}[/#facc15]")
        console.print(t)
    _hr()
    console.print()
    await _press_enter_to_continue()


async def show_rating_leaderboard():
    limit = await _ask_int("Количество записей", 10)
    data = await _nest_get("/rating/leaderboard", {"limit": limit})
    if not data or not data.get("leaderboard"):
        _err("Таблица рейтинга недоступна")
        await _press_enter_to_continue()
        return
    console.print()
    _hr("🏆 Таблица лидеров рейтинга")
    t = Table(box=box.MINIMAL, header_style="dim #9ca3af", padding=(0, 2))
    t.add_column("#", justify="right", style="dim")
    t.add_column("Ключ", style="dim")
    t.add_column("Очки", justify="right")
    t.add_column("Обновлено", style="dim")
    for i, entry in enumerate(data["leaderboard"], 1):
        key_short = (entry.get("api_key","?") or "?")[:12] + "..."
        t.add_row(str(i), key_short, f"[#facc15]{entry.get('rating',0)}[/#facc15]",
                   str(entry.get("last_updated","?"))[:19])
    console.print(t); _hr(); console.print()
    await _press_enter_to_continue()


# ═══════════════════════════════════════════════════════════════════
# API Key status
# ═══════════════════════════════════════════════════════════════════

async def show_api_status():
    console.print()
    _hr("🔑 Статус API")
    _kv("BrawlNest сервер", BASE_URL)
    _kv("BrawlNest API ключ", (API_KEY[:12] + "...") if API_KEY else "[dim]отсутствует[/dim]")
    _kv("Brawl Stars ключи", str(len(API_KEYS)))

    if API_KEY:
        data = await _nest_get("/my_status", {"api_key": API_KEY})
        if data:
            _kv("Лимит в сутки",  str(data.get("daily_limit", "?")))
            _kv("Использовано",   str(data.get("used_today", "?")))
            _kv("Осталось",       f"[#4ade80]{data.get('remaining','?')}[/#4ade80]")
            _kv("Создан",         str(data.get("created_at","?"))[:19])

    if HAS_BRAWL_KEYS and api:
        with console.status("[dim]Проверка ключей Brawl Stars...[/dim]", spinner="dots"):
            d = await api.get_brawlers()
        if d and "items" in d:
            _ok(f"Brawl Stars API работает ({len(d['items'])} бравлеров)")
        else:
            _err("Brawl Stars API: ошибка проверки")
    _hr()
    console.print()
    await _press_enter_to_continue()


# ═══════════════════════════════════════════════════════════════════
# PNG export
# ═══════════════════════════════════════════════════════════════════

async def save_player_png(tag: str):
    if not PNG_AVAILABLE:
        _err("Установите: pip install matplotlib pillow numpy")
        await _press_enter_to_continue()
        return
    # Импортируем matplotlib внутри функции, чтобы Pylance не ругался
    import matplotlib.pyplot as plt

    tag_clean = tag.strip().upper().lstrip("#")
    data = await _nest_get(f"/player/{tag_clean}")
    if not data and HAS_BRAWL_KEYS and player_col:
        data = await player_col.collect(tag_clean, force_update=False)
    if not data:
        _err(f"Игрок {tag_clean} не найден")
        await _press_enter_to_continue()
        return

    name    = data.get("name","?")
    p_tag   = f"#{data.get('tag','').lstrip('#')}"
    trophies= data.get("trophies", 0)
    highest = data.get("highestTrophies") or data.get("highest_trophies", trophies)
    exp_lvl = data.get("expLevel") or data.get("exp_level", "?")
    exp_pts = data.get("expPoints") or data.get("exp_points", 0)
    w3      = data.get("3vs3Victories") or data.get("wins_3v3", 0)
    wsolo   = data.get("soloVictories") or data.get("wins_solo", 0)
    wduo    = data.get("duoVictories") or data.get("wins_duo", 0)
    club    = (data.get("club") or {})
    club_tag= (club.get("tag","") if isinstance(club,dict) else "") or data.get("club_tag","")

    labels  = ["3x3", "Соло", "Дуо"]
    sizes   = [w3, wsolo, wduo]
    colors  = ["#3b82f6", "#ef4444", "#10b981"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 9), facecolor="#0f172a")
    fig.patch.set_facecolor("#0f172a")
    ax1.set_facecolor("#0f172a"); ax2.set_facecolor("#0f172a")

    if sum(sizes) > 0:
        ax1.pie(sizes, labels=labels, autopct=lambda p: f"{p:.1f}%" if p > 0 else "",
                colors=colors, startangle=90, explode=(0.05,0.05,0.05),
                wedgeprops={"edgecolor":"#ffffff","linewidth":1.5},
                textprops={"color":"white","fontsize":12,"weight":"bold"})
    ax1.set_title("Распределение побед", color="#facc15", fontsize=16, pad=20, weight="bold")

    stats_text = (
        f"🏆 {name}  {p_tag}\n\n"
        f"Трофеи: {trophies} (макс {highest})\n"
        f"Уровень: {exp_lvl} ({exp_pts} XP)\n"
        f"Победы 3x3: {w3}\n"
        f"Победы соло: {wsolo}\n"
        f"Победы дуо: {wduo}\n"
        f"Клуб: {club_tag or '—'}\n"
        f"Сгенерировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    ax2.text(0.05, 0.5, stats_text, transform=ax2.transAxes,
             fontsize=13, verticalalignment="center", linespacing=1.5,
             bbox=dict(boxstyle="round,pad=0.5", facecolor="#1e293b",
                        edgecolor="#facc15", linewidth=2, alpha=0.9),
             color="#e2e8f0")
    ax2.axis("off")
    fig.suptitle("BrawlNest Stats", color="#facc15", fontsize=18, weight="bold", y=0.98)

    filename = f"player_{tag_clean}.png"
    plt.tight_layout(pad=2.0)
    plt.savefig(filename, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    _ok(f"Сохранено: {filename}")
    console.print()
    await _add_rating("save_png", tag_clean)
    await _press_enter_to_continue()


# ═══════════════════════════════════════════════════════════════════
# SEARCH / FILL (direct Brawl API)
# ═══════════════════════════════════════════════════════════════════

def _listen_for_stop(stop_event: threading.Event):
    try:
        import termios, tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        tty.setcbreak(fd)
        try:
            while not stop_event.is_set():
                ch = sys.stdin.read(1)
                if ch in ("q","Q","\x03","\x04"):
                    stop_event.set()
                    break
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        pass


async def _run_search(endpoint: str, tags: List[str], existing: set,
                       output_file: str, label: str):
    if not HAS_BRAWL_KEYS:
        _err("Нет ключей Brawl Stars API. Добавьте API_KEYS в .env")
        return [], True
    found = []
    stop_event = threading.Event()
    threading.Thread(target=_listen_for_stop, args=(stop_event,), daemon=True).start()
    queue: asyncio.Queue[str] = asyncio.Queue()
    for t in tags:
        await queue.put(t)

    with Progress(TextColumn("[progress.description]{task.description}"), BarColumn(),
                   TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                   TimeElapsedColumn(), console=console, transient=True) as progress:
        task = progress.add_task(f"[cyan]{label}...", total=len(tags))

        async def worker(key: str):
            while not stop_event.is_set():
                try:
                    tag = await asyncio.wait_for(queue.get(), timeout=1.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    break
                url = f"https://api.brawlstars.com/v1/{endpoint}/%23{tag}"
                try:
                    async with aiohttp.ClientSession() as sess:
                        async with sess.get(url, headers={"Authorization": f"Bearer {key}"},
                                             timeout=aiohttp.ClientTimeout(total=10)) as resp:
                            if resp.status == 200:
                                found.append(tag)
                            elif resp.status == 429:
                                ra = int(resp.headers.get("Retry-After", 60))
                                await asyncio.sleep(ra)
                                await queue.put(tag)
                                queue.task_done()
                                continue
                except Exception:
                    pass
                progress.update(task, advance=1)
                queue.task_done()

        workers = [asyncio.create_task(worker(k)) for k in API_KEYS for _ in range(5)]
        try:
            await asyncio.wait_for(queue.join(), timeout=3600)
        except (asyncio.TimeoutError, asyncio.CancelledError, KeyboardInterrupt):
            stop_event.set()
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    all_tags = existing | set(found)
    with open(output_file, "w") as f:
        f.write("\n".join(sorted(all_tags)) + "\n")
    return found, stop_event.is_set()


async def search_existing_players():
    if not HAS_BRAWL_KEYS:
        _err("Нет ключей Brawl Stars API")
        await _press_enter_to_continue()
        return
    n   = await _ask_int("Количество запросов", 1000)
    out = await _ask("Файл для сохранения", "The_players.txt")
    out = out or "The_players.txt"
    existing = set()
    if os.path.exists(out):
        with open(out) as f:
            existing = {l.strip() for l in f if l.strip()}
        _info(f"Загружено {len(existing)} существующих тегов")
    tags   = generate_tags(n, SEARCH_CFG.get("tag_min_length",7), SEARCH_CFG.get("tag_max_length",9))
    found, interrupted = await _run_search("players", tags, existing, out, "Поиск игроков")
    status = "остановлен" if interrupted else "завершён"
    _ok(f"{status} · новых: {len(found)} · всего: {len(existing|set(found))} → {out}")
    console.print()
    await _add_rating("search_players", out)
    await _press_enter_to_continue()


async def search_existing_clubs():
    if not HAS_BRAWL_KEYS:
        _err("Нет ключей Brawl Stars API")
        await _press_enter_to_continue()
        return
    n   = await _ask_int("Количество запросов", 1000)
    out = await _ask("Файл для сохранения", "existing_clubs.txt")
    out = out or "existing_clubs.txt"
    existing = set()
    if os.path.exists(out):
        with open(out) as f:
            existing = {l.strip() for l in f if l.strip()}
    tags   = generate_tags(n, 7, 9)
    found, interrupted = await _run_search("clubs", tags, existing, out, "Поиск клубов")
    status = "остановлен" if interrupted else "завершён"
    _ok(f"{status} · новых: {len(found)} · всего: {len(existing|set(found))} → {out}")
    console.print()
    await _add_rating("search_existing_clubs", out)
    await _press_enter_to_continue()


async def check_players_from_file():
    path = await _ask("Путь к файлу с тегами")
    if not path or not os.path.exists(path):
        _err("Файл не найден")
        await _press_enter_to_continue()
        return
    with open(path) as f:
        tags = [l.strip() for l in f if l.strip()]
    base, ext = os.path.splitext(path)
    out = f"{base}_existing{ext}"
    existing = set()
    if os.path.exists(out):
        with open(out) as f:
            existing = {l.strip() for l in f if l.strip()}
    found, interrupted = await _run_search("players", tags, existing, out, "Проверка")
    _ok(f"Найдено {len(existing|set(found))} существующих → {out}")
    console.print()
    await _add_rating("check_players_file", path)
    await _press_enter_to_continue()


async def show_random_player():
    fname = SEARCH_CFG.get("output_file", "The_players.txt")
    if not os.path.exists(fname):
        _err(f"Файл {fname} не найден. Сначала выполните поиск игроков.")
        await _press_enter_to_continue()
        return
    with open(fname) as f:
        tags = [l.strip() for l in f if l.strip()]
    if not tags:
        _err("Файл пуст")
        await _press_enter_to_continue()
        return
    tag = random.choice(tags)
    _info(f"Случайный тег: #{tag}")
    await show_player(tag)  # show_player уже содержит _press_enter_to_continue


async def fill_database():
    if not HAS_BRAWL_KEYS:
        _err("Нет ключей Brawl Stars API")
        await _press_enter_to_continue()
        return
    n = await _ask_int("Количество запросов для поиска игроков", 1000)
    temp = "temp_fill_players.txt"
    tags = generate_tags(n, SEARCH_CFG.get("tag_min_length",7), SEARCH_CFG.get("tag_max_length",9))
    found, _ = await _run_search("players", tags, set(), temp, "Поиск игроков для заполнения")
    if not found:
        _err("Не найдено игроков")
        await _press_enter_to_continue()
        return
    _info(f"Найдено {len(found)} игроков. Загрузка данных...")
    loaded = 0
    with Progress(TextColumn("[progress.description]{task.description}"), BarColumn(),
                   TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                   TimeElapsedColumn(), console=console, transient=True) as prog:
        task = prog.add_task("[cyan]Загрузка...", total=len(found))
        for tag in found:
            if player_col:
                await player_col.collect(tag, force_update=True)
            loaded += 1
            prog.update(task, advance=1)
    _ok(f"Загружено {loaded} игроков")
    if os.path.exists(temp):
        os.remove(temp)
    console.print()
    await _add_rating("fill_db")
    await _press_enter_to_continue()


async def continuous_fill():
    if not HAS_BRAWL_KEYS:
        _err("Нет ключей Brawl Stars API")
        await _press_enter_to_continue()
        return
    console.print()
    console.print("[bold]Непрерывное заполнение базы[/bold]")
    _info("Нажмите q для остановки")
    stop_event = threading.Event()
    threading.Thread(target=_listen_for_stop, args=(stop_event,), daemon=True).start()
    saved = 0
    try:
        while not stop_event.is_set():
            tags = generate_tags(50, 7, 9)
            for tag in tags:
                if stop_event.is_set():
                    break
                if api:
                    p = await api.get_player(tag, force=True)
                    if p and player_col and db:
                        await player_col.collect(tag, force_update=True)
                        saved += 1
                        await _add_rating("continuous_fill", tag)
                await asyncio.sleep(0.15)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    _ok(f"Остановлено. Сохранено: {saved} игроков")
    if saved > 0 and SYNC_CFG.get("push_after_fill", False):
        await sync_push()
    console.print()
    await _press_enter_to_continue()


async def generate_random_codes():
    count  = await _ask_int("Количество кодов", 100)
    length = await _ask_int("Длина кода", 8)
    fname  = await _ask("Имя файла", "game_codes.txt")
    fname  = fname or "game_codes.txt"
    chars  = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    codes  = ["".join(random.choices(chars, k=length)) for _ in range(count)]
    with open(fname, "w") as f:
        f.write("\n".join(codes) + "\n")
    _ok(f"Сгенерировано {count} кодов → {fname}")
    console.print()
    await _add_rating("generate_codes")
    await _press_enter_to_continue()


# ═══════════════════════════════════════════════════════════════════
# SYNC
# ═══════════════════════════════════════════════════════════════════

async def sync_push():
    _info("Экспорт данных в GitHub...")
    try:
        ghs = GitHubSync()
        await ghs.export_and_push()
        _ok("Данные выгружены в GitHub")
        await _add_rating("sync_push")
    except Exception as e:
        _err(f"Ошибка синхронизации: {e}")
    # Убираем вызов _press_enter_to_continue() — чтобы меню показывалось сразу


async def sync_pull():
    _info("Загрузка данных из GitHub...")
    try:
        ghs = GitHubSync()
        await ghs.pull_and_import()
        _ok("Данные загружены из GitHub")
        await _add_rating("sync_pull")
    except Exception as e:
        _err(f"Ошибка загрузки: {e}")
    # Убираем вызов _press_enter_to_continue()


async def set_search_mode_menu():
    cur = "онлайн" if search_mode == "online" else "офлайн"
    mode = await _ask(f"Режим: 1-офлайн (локальная БД) / 2-онлайн (GitHub) [текущий: {cur}]", "1")
    if mode == "2":
        save_search_mode("online")
        _ok("Режим поиска: ОНЛАЙН")
    else:
        save_search_mode("offline")
        _ok("Режим поиска: ОФЛАЙН")
    console.print()
    await _press_enter_to_continue()


async def full_club_collect(tag: str):
    tag_clean = tag.strip().upper().lstrip("#")
    data = await _nest_get(f"/club/{tag_clean}")
    if not data and HAS_BRAWL_KEYS and club_col:
        data = await club_col.collect(tag_clean)
    if not data:
        _err("Клуб не найден")
        await _press_enter_to_continue()
        return
    members = data.get("members", [])
    if not members and db:
        members = await db.get_club_members(tag_clean)
    if not members:
        _err("Нет участников")
        await _press_enter_to_continue()
        return
    _info(f"Загрузка данных {len(members)} участников...")
    loaded = 0
    with Progress(TextColumn("[progress.description]{task.description}"), BarColumn(),
                   TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                   TimeElapsedColumn(), console=console, transient=True) as prog:
        task = prog.add_task("[cyan]Участники...", total=len(members))
        for m in members:
            mtag = (m.get("tag") or m.get("player_tag","")).lstrip("#")
            if mtag and player_col:
                await player_col.collect(mtag, force_update=False)
            loaded += 1
            prog.update(task, advance=1)
    _ok(f"Собрано данных участников: {loaded}")
    console.print()
    await _add_rating("full_club_collect", tag_clean)
    await _press_enter_to_continue()


async def check_team_game():
    tags_raw = await _ask("Теги игроков через запятую (2-3)")
    if not tags_raw:
        return
    tags = [t.strip().upper().lstrip("#") for t in tags_raw.split(",") if t.strip()]
    if len(tags) < 2:
        _err("Нужно минимум 2 тега")
        await _press_enter_to_continue()
        return
    data = await _nest_get("/team/stats", {"tags": ",".join(tags)})
    if data and data.get("total_battles", 0) > 0:
        _ok(f"Найдено {data['total_battles']} совместных боёв, победы: {data.get('total_wins',0)}")
    else:
        _info("Нет данных о совместных боях (нужны данные из официального API)")
    await _add_rating("check_team")
    await _press_enter_to_continue()


# ═══════════════════════════════════════════════════════════════════
# MENU (modernized)
# ═══════════════════════════════════════════════════════════════════

MENU_ITEMS = [
    ("player",            "👤 Профиль игрока"),
    ("player_history",    "📈 История трофеев игрока"),
    ("player_battles",    "📜 Последние бои игрока"),
    ("player_battles_stats","📊 Статистика боёв"),
    ("player_brawlers",   "🤖 Бравлеры игрока"),
    ("player_mastery",    "⭐ Мастерство игрока"),
    ("compare_players",   "⚔️  Сравнить игроков"),
    ("update_player",     "🔄 Принудительное обновление"),
    ("save_png",          "📸 Сохранить статистику в PNG"),
    ("random_player",     "🎲 Случайный игрок из базы"),
    ("club",              "🏢 Информация о клубе"),
    ("club_members",      "👥 Участники клуба"),
    ("club_history",      "📈 История клуба"),
    ("full_club",         "📊 Полный сбор данных клуба"),
    ("search_players",    "🔍 Поиск игроков по имени"),
    ("search_clubs_name", "🔍 Поиск клубов по названию"),
    ("advanced_search",   "🔍 Расширенный поиск"),
    ("search_existing",   "🔍 Поиск существующих игроков"),
    ("search_clubs",      "🔍 Поиск существующих клубов"),
    ("check_file",        "📁 Проверить теги из файла"),
    ("check_team",        "🎮 Командная игра по тегам"),
    ("maps",              "🗺️ Статистика карт"),
    ("map_detail",        "🗺️ Конкретная карта"),
    ("team_stats",        "🎮 Командная статистика"),
    ("rankings_players",  "🏆 Топ игроков (BrawlNest)"),
    ("rankings_clubs",    "🏅 Топ клубов (BrawlNest)"),
    ("brawlers",          "🤖 Список бравлеров"),
    ("brawler_rankings",  "🏆 Рейтинг по бравлеру"),
    ("rotation",          "🎡 Ротация событий"),
    ("rank_players_brawl","🏆 Топ игроков (глобальный)"),
    ("rank_clubs_brawl",  "🏅 Топ клубов (глобальный)"),
    ("locations",         "🌍 Список стран"),
    ("powerplay",         "⚡ Сезоны Power Play"),
    ("gen_codes",         "🔑 Генерация кодов команды"),
    ("list_codes",        "📋 Список активных кодов"),
    ("cleanup_codes",     "🧹 Очистить старые коды"),
    ("gen_team_code",     "🔐 Создать код команды (API)"),
    ("check_team_code",   "✅ Проверить код команды"),
    ("gen_random_codes",  "🎲 Генерация случайных кодов"),
    ("my_rating",         "⭐ Мой рейтинг"),
    ("rating_leaderboard","🏆 Таблица лидеров"),
    ("nodes",             "🌐 Активные узлы сети"),
    ("api_status",        "🔑 Статус API ключей"),
    ("input_key",         "🔑 Ввести API-ключ"),
    ("fill_db",           "📥 Заполнить базу данных"),
    ("continuous_fill",   "🔄 Непрерывное заполнение"),
    ("sync_push",         "⬆️ Выгрузить данные в GitHub"),
    ("sync_pull",         "⬇️ Загрузить данные из GitHub"),
    ("set_mode",          "🌐 Режим поиска (офлайн/онлайн)"),
    ("exit",              "🚪 Выход"),
]

_NAV = list(range(len(MENU_ITEMS)))


def load_menu_pos() -> int:
    try:
        if os.path.exists(MENU_POS_FILE):
            with open(MENU_POS_FILE, "r") as f:
                s = f.read().strip()
                if s:
                    v = int(s)
                    if 0 <= v < len(_NAV):
                        return v
    except Exception:
        pass
    return APP_CFG.get("last_menu_pos", 0)


def save_menu_pos(idx: int):
    try:
        with open(MENU_POS_FILE, "w") as f:
            f.write(str(int(idx)))
    except Exception:
        pass


def _build_grid_fragments(idx_ptr: List[int], term_width: int, columns: int = 3) -> List:
    """
    Build formatted text fragments for the grid menu.
    Uses column-major ordering for intuitive vertical navigation.
    """
    total_items = len(_NAV)
    if total_items == 0:
        return [("", "No menu items")]
    # adapt columns based on terminal width or fallback to 1
    min_col_width = 28  # minimal comfortable column width
    max_columns = max(1, term_width // min_col_width)
    columns = min(columns, max_columns)
    if columns < 1:
        columns = 1
    rows = ceil(total_items / columns)
    # compute equal width columns with safe padding
    col_padding = 2
    col_width = max(min_col_width, (term_width - (columns - 1) * col_padding) // columns)
    # inner width for label (reserve 3 for prefix and spacing)
    inner_width = max(8, col_width - 3)

    fragments = []
    cur = idx_ptr[0]
    # build row by row, each row contains columns
    for r in range(rows):
        for c in range(columns):
            idx = c * rows + r
            if idx < total_items:
                key, label = MENU_ITEMS[_NAV[idx]]
                # truncate label gracefully
                lab = label
                if len(lab) > inner_width:
                    lab = lab[:inner_width - 1] + "…"
                padding = inner_width - len(lab)
                prefix = "  "
                style = "class:item"
                if idx == cur:
                    prefix = "❯ "
                    style = "class:selected"
                    text = f"{prefix}{lab}{' ' * padding}"
                else:
                    text = f"  {lab}{' ' * padding}"
                fragments.append((style, text))
            else:
                fragments.append(("", " " * (col_width)))
            # spacing between columns
            if c != columns - 1:
                fragments.append(("", " " * col_padding))
        fragments.append(("", "\n"))
    return fragments


def _render_header_panel(rating: int, term_width: int) -> List:
    """
    Render a compact header (as formatted fragments) to show above the menu.
    """
    title = "BrawlNest"
    subtitle = f"Server: {BASE_URL}  |  Mode: {search_mode}  |  Keys: {len(API_KEYS)}  |  ⭐ {rating}"
    title_line = f" {title} "
    subtitle_line = f" {subtitle} "
    if len(subtitle_line) > term_width - 2:
        subtitle_line = subtitle_line[:term_width - 5] + "..."
    fragments = []
    fragments.append(("class:header.title", title_line.ljust(term_width)))
    fragments.append(("", "\n"))
    fragments.append(("class:header.meta", subtitle_line.ljust(term_width)))
    fragments.append(("", "\n\n"))
    return fragments


def _render_footer_help(term_width: int) -> List:
    hint = "↑↓ — перемещение  ←→ — колонка  Tab/Shift+Tab — циклически  Enter — выбор  q/Ctrl+C — выход"
    if len(hint) > term_width - 2:
        hint = "↑↓ Tab Enter ←→ q"
    return [("class:footer", hint[:term_width])]


def _run_menu() -> str:
    """
    Synchronous menu runner for use inside an executor.
    Returns the command key of the chosen menu item.
    """
    idx_ptr = [load_menu_pos()]
    result: List[Optional[str]] = [None]

    try:
        term_size = shutil.get_terminal_size()
        term_width = term_size.columns
    except Exception:
        term_width = 100

    columns = 3
    min_col_width = 28
    max_columns = max(1, term_width // min_col_width)
    columns = min(columns, max_columns)
    if columns < 1:
        columns = 1

    menu_ctrl = FormattedTextControl(text=lambda: _build_grid_fragments(idx_ptr, term_width, columns), focusable=True)
    footer_ctrl = FormattedTextControl(text=lambda: _render_footer_help(term_width), focusable=False)

    kb = KeyBindings()

    total_items = len(_NAV)
    rows = ceil(total_items / columns)

    def idx_to_row_col(idx: int):
        row = idx % rows
        col = idx // rows
        return row, col

    def row_col_to_idx(row: int, col: int):
        idx = col * rows + row
        if idx >= total_items:
            while idx >= total_items and col >= 0:
                col -= 1
                idx = col * rows + row
            if idx < 0:
                idx = 0
        return max(0, min(idx, total_items - 1))

    @kb.add("up")
    def _up(event):
        row, col = idx_to_row_col(idx_ptr[0])
        row = (row - 1) % rows
        idx_ptr[0] = row_col_to_idx(row, col)
        menu_ctrl.text = lambda: _build_grid_fragments(idx_ptr, term_width, columns)

    @kb.add("down")
    def _down(event):
        row, col = idx_to_row_col(idx_ptr[0])
        row = (row + 1) % rows
        idx_ptr[0] = row_col_to_idx(row, col)
        menu_ctrl.text = lambda: _build_grid_fragments(idx_ptr, term_width, columns)

    @kb.add("left")
    def _left(event):
        row, col = idx_to_row_col(idx_ptr[0])
        col = (col - 1) % columns
        idx_ptr[0] = row_col_to_idx(row, col)
        menu_ctrl.text = lambda: _build_grid_fragments(idx_ptr, term_width, columns)

    @kb.add("right")
    def _right(event):
        row, col = idx_to_row_col(idx_ptr[0])
        col = (col + 1) % columns
        idx_ptr[0] = row_col_to_idx(row, col)
        menu_ctrl.text = lambda: _build_grid_fragments(idx_ptr, term_width, columns)

    @kb.add("tab")
    def _tab(event):
        idx_ptr[0] = (idx_ptr[0] + 1) % total_items
        menu_ctrl.text = lambda: _build_grid_fragments(idx_ptr, term_width, columns)

    @kb.add("s-tab")
    def _stabb(event):
        idx_ptr[0] = (idx_ptr[0] - 1) % total_items
        menu_ctrl.text = lambda: _build_grid_fragments(idx_ptr, term_width, columns)

    @kb.add("enter")
    def _enter(event):
        result[0] = MENU_ITEMS[_NAV[idx_ptr[0]]][0]
        save_menu_pos(idx_ptr[0])
        event.app.exit()

    @kb.add("q")
    @kb.add("c-c")
    def _quit(event):
        result[0] = "exit"
        save_menu_pos(idx_ptr[0])
        event.app.exit()

    body = HSplit([
        Window(content=menu_ctrl, dont_extend_height=True, always_hide_cursor=False),
        Window(height=1, char="", style=""),
        Window(content=footer_ctrl, height=1, dont_extend_height=True),
    ])

    app = PTApp(layout=Layout(body), key_bindings=kb, style=PT_STYLE,
                full_screen=False, mouse_support=False)

    try:
        app.run()
    except Exception:
        pass

    return result[0] or "exit"


# ═══════════════════════════════════════════════════════════════════
# MAIN LOOP (modified to print rich header panel before menu)
# ═══════════════════════════════════════════════════════════════════

async def interactive_menu():
    await ensure_api_key()
    global search_mode
    console.print()
    while True:
        try:
            rating = await _get_rating()
        except Exception:
            rating = 0
        console.clear()
        header_table = Table.grid(expand=True)
        header_table.add_column(ratio=1)
        header_table.add_column(width=40, justify="right")
        header_table.add_row(
            Text("BrawlNest", style="bold cyan"),
            Text(f"⭐ {rating}", style="bold #facc15")
        )
        meta = Text(f"Server: {BASE_URL}  •  Mode: {search_mode}  •  Brawl keys: {len(API_KEYS)}", style="dim")
        panel = Panel.fit(
            Align.left(header_table) if header_table else Text("BrawlNest"),
            subtitle=meta,
            box=box.ROUNDED, border_style="bright_blue"
        )
        console.print(panel)
        console.print()  # spacing

        console.print("  [dim]↑↓/←→ — навигация   Tab/Shift+Tab — циклическая   Enter — выбор   q — выход[/dim]\n")
        loop = asyncio.get_event_loop()
        choice = await loop.run_in_executor(None, _run_menu)
        console.print()
        if not choice or choice == "exit":
            console.print("  [dim]До свидания![/dim]\n")
            break

        if choice == "player":
            tag = await _ask("Тег игрока (без #)")
            if tag: await show_player(tag)

        elif choice == "player_history":
            tag  = await _ask("Тег игрока")
            days = await _ask_int("Дней истории", 30)
            if tag: await show_player_history(tag, days)

        elif choice == "player_battles":
            tag   = await _ask("Тег игрока")
            limit = await _ask_int("Количество боёв", 20)
            if tag: await show_player_battles(tag, limit)

        elif choice == "player_battles_stats":
            tag = await _ask("Тег игрока")
            if tag: await show_player_battles_stats(tag)

        elif choice == "player_brawlers":
            tag = await _ask("Тег игрока")
            if tag: await show_player_brawlers(tag)

        elif choice == "player_mastery":
            tag = await _ask("Тег игрока")
            if tag: await show_player_mastery(tag)

        elif choice == "compare_players":
            await compare_players()

        elif choice == "update_player":
            tag = await _ask("Тег игрока")
            if tag: await show_player(tag, force_update=True)

        elif choice == "save_png":
            tag = await _ask("Тег игрока")
            if tag: await save_player_png(tag)

        elif choice == "random_player":
            await show_random_player()

        elif choice == "club":
            tag = await _ask("Тег клуба (без #)")
            if tag: await show_club(tag, False)

        elif choice == "club_members":
            tag = await _ask("Тег клуба (без #)")
            if tag: await show_club(tag, True)

        elif choice == "club_history":
            tag  = await _ask("Тег клуба")
            days = await _ask_int("Дней истории", 30)
            if tag: await show_club_history(tag, days)

        elif choice == "full_club":
            tag = await _ask("Тег клуба")
            if tag: await full_club_collect(tag)

        elif choice == "search_players":
            await search_players_by_name()

        elif choice == "search_clubs_name":
            await search_clubs_by_name()

        elif choice == "advanced_search":
            await advanced_search_menu()

        elif choice == "search_existing":
            await search_existing_players()

        elif choice == "search_clubs":
            await search_existing_clubs()

        elif choice == "check_file":
            await check_players_from_file()

        elif choice == "check_team":
            await check_team_game()

        elif choice == "maps":
            limit = await _ask_int("Количество карт", 30)
            await show_maps(limit)

        elif choice == "map_detail":
            await show_map_stats()

        elif choice == "team_stats":
            await show_team_stats()

        elif choice == "rankings_players":
            limit = await _ask_int("Количество", 20)
            await show_rankings_players(limit)

        elif choice == "rankings_clubs":
            limit = await _ask_int("Количество", 20)
            await show_rankings_clubs(limit)

        elif choice == "brawlers":
            await show_brawlers()

        elif choice == "brawler_rankings":
            await show_brawler_rankings()

        elif choice == "rotation":
            await show_event_rotation()

        elif choice == "rank_players_brawl":
            await show_global_rankings("players")

        elif choice == "rank_clubs_brawl":
            await show_global_rankings("clubs")

        elif choice == "locations":
            await show_locations()

        elif choice == "powerplay":
            await show_powerplay_seasons()

        elif choice == "gen_codes":
            await generate_team_codes_cli()

        elif choice == "list_codes":
            await list_team_codes()

        elif choice == "cleanup_codes":
            await cleanup_expired_codes()

        elif choice == "gen_team_code":
            await generate_team_code()

        elif choice == "check_team_code":
            await check_team_code()

        elif choice == "gen_random_codes":
            await generate_random_codes()

        elif choice == "my_rating":
            await show_my_rating()

        elif choice == "rating_leaderboard":
            await show_rating_leaderboard()

        elif choice == "nodes":
            await show_nodes()

        elif choice == "api_status":
            await show_api_status()

        elif choice == "input_key":
            await input_api_key_manual()

        elif choice == "fill_db":
            await fill_database()

        elif choice == "continuous_fill":
            await continuous_fill()

        elif choice == "sync_push":
            await sync_push()

        elif choice == "sync_pull":
            await sync_pull()

        elif choice == "set_mode":
            await set_search_mode_menu()


async def main():
    await _init()
    if SYNC_CFG.get("auto_pull_on_start", False):
        try:
            await sync_pull()
        except Exception:
            pass

    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        tag = sys.argv[2] if len(sys.argv) > 2 else ""
        await ensure_api_key()
        if cmd == "player" and tag:        await show_player(tag, True)
        elif cmd == "battles" and tag:     await show_player_battles(tag)
        elif cmd == "history" and tag:     await show_player_history(tag)
        elif cmd == "brawlers" and tag:    await show_player_brawlers(tag)
        elif cmd == "club" and tag:        await show_club(tag, True)
        elif cmd == "club_history" and tag:await show_club_history(tag)
        elif cmd == "maps":                await show_maps()
        elif cmd == "rankings":            await show_rankings_players()
        elif cmd == "nodes":               await show_nodes()
        elif cmd == "status":              await show_api_status()
        elif cmd == "rating":              await show_my_rating()
        elif cmd == "gen_code":            await generate_team_code()
        elif cmd == "search":              await search_players_by_name()
        elif cmd == "fill":                await fill_database()
        elif cmd == "syncpush":            await sync_push()
        elif cmd == "syncpull":            await sync_pull()
        else:
            console.print("Команды: player|battles|history|brawlers|club|maps|rankings|nodes|status|rating|gen_code|search|fill|syncpush|syncpull")
    else:
        await interactive_menu()

    if SYNC_CFG.get("auto_push_on_exit", False):
        try:
            await sync_push()
        except Exception:
            pass
    try:
        if api:
            await api.close()
        if db:
            await db.close()
    except Exception:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        console.print("\n  [dim]Прервано[/dim]\n")
        sys.exit(0)