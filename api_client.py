"""Клиент Brawl Stars API с ротацией ключей, rate limiting и кэшем."""
import aiohttp
import asyncio
import itertools
import sys
import time
from typing import Optional, Dict, Any, List

from config import API_KEYS, API_CFG, PROXY_LIST, API_SERVER_URL
from utils.logger import setup_logger

logger = setup_logger(__name__)

# Актуальный базовый URL сервера BrawlNest
BASE_URL = API_SERVER_URL.rstrip("/") if API_SERVER_URL else "http://130.12.46.224"
TIMEOUT = API_CFG.get("request_timeout", 15)

# Simple in-memory cache
_cache: Dict[str, Any] = {}
_cache_ts: Dict[str, float] = {}


class BrawlAPIClient:
    """Клиент для работы с BrawlNest API и официальным Brawl Stars API."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_keys = API_KEYS
        self.api_key = api_key  # Ключ для BrawlNest REST API
        self._key_idx = 0
        self._session: Optional[aiohttp.ClientSession] = None
        self.last_status: Optional[int] = None
        self._requests: List[float] = []

    @property
    def has_keys(self) -> bool:
        return bool(self.api_keys) or bool(self.api_key)

    @staticmethod
    def normalize_tag(tag: str) -> str:
        return tag.strip().upper().replace("#", "")

    def _current_key(self) -> Optional[str]:
        if self.api_key:
            return self.api_key
        if not self.api_keys:
            return None
        return self.api_keys[self._key_idx % len(self.api_keys)]

    def _rotate_key(self):
        if self.api_keys:
            self._key_idx = (self._key_idx + 1) % len(self.api_keys)

    async def _wait_rate_limit(self):
        now = time.time()
        self._requests = [t for t in self._requests if now - t < 60]
        limit = API_CFG.get("rate_limit_per_key", 30) * max(len(self.api_keys), 1)
        if len(self._requests) >= limit:
            sleep = 60 - (now - self._requests[0]) + 0.1
            await asyncio.sleep(sleep)
        self._requests.append(time.time())

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session and not self._session.closed:
            return self._session
        connector = aiohttp.TCPConnector(limit=50)
        timeout = aiohttp.ClientTimeout(total=TIMEOUT)
        self._session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _request(self, endpoint: str, use_cache: bool = True,
                        cache_ttl: int = 300, method: str = "GET",
                        json_body: Optional[Dict] = None) -> Optional[Dict]:
        """Выполняет запрос к API с поддержкой разных методов и аутентификации."""
        if not self.has_keys:
            return None
        
        cache_key = f"bs:{method}:{endpoint}"
        if use_cache and cache_key in _cache:
            if time.time() - _cache_ts[cache_key] < cache_ttl:
                return _cache[cache_key]

        await self._wait_rate_limit()
        key = self._current_key()
        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        
        # Подготовка заголовков с поддержкой X-API-Key и fallback на Authorization
        headers = {}
        params = {}
        
        # Приоритет: X-API-Key заголовок
        if key:
            headers["X-API-Key"] = key
        
        # Fallback: query параметр api_key (если сервер требует)
        if key and endpoint.startswith("my_status"):
            params["api_key"] = key
        
        # Для официального Brawl Stars API используем Authorization header
        if self.api_keys and not self.api_key:
            headers["Authorization"] = f"Bearer {key}"
            headers.pop("X-API-Key", None)
        
        if json_body:
            headers["Content-Type"] = "application/json"
        
        session = await self._get_session()
        
        try:
            async with session.request(
                method, url, headers=headers, params=params,
                json=json_body if method in ("POST", "PUT", "PATCH") else None
            ) as resp:
                self.last_status = resp.status
                
                if resp.status == 200:
                    try:
                        data = await resp.json()
                        if use_cache:
                            _cache[cache_key] = data
                            _cache_ts[cache_key] = time.time()
                        return data
                    except Exception:
                        return {"status": "ok"}
                
                if resp.status == 404:
                    logger.debug(f"Resource not found: {url}")
                    return None
                
                if resp.status == 403:
                    logger.warning(f"Forbidden (403) for {url}, rotating key...")
                    self._rotate_key()
                    return None
                
                if resp.status == 401:
                    logger.error(f"Unauthorized (401) for {url}. Check API key.")
                    return None
                
                if resp.status == 429:
                    ra = int(resp.headers.get("Retry-After", 60))
                    logger.warning(f"Rate limited (429). Waiting {ra}s...")
                    await asyncio.sleep(ra)
                    return await self._request(endpoint, use_cache=False, cache_ttl=cache_ttl,
                                              method=method, json_body=json_body)
                
                if resp.status >= 500:
                    logger.error(f"Server error ({resp.status}) for {url}")
                    return None
                    
                return None
                
        except asyncio.TimeoutError:
            logger.error(f"Request timeout for {url}")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"Client error for {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error for {url}: {e}")
            return None

    async def generate_api_key(self, name: str = "CLI_User", daily_limit: int = 10000) -> Optional[str]:
        """Генерирует новый API ключ через эндпоинт /generate_key."""
        json_body = {"name": name, "daily_limit": daily_limit}
        result = await self._request("generate_key", use_cache=False, method="POST", json_body=json_body)
        if result:
            return result.get("key")
        return None

    async def get_my_status(self) -> Optional[Dict]:
        """Получает статус текущего API ключа."""
        return await self._request("my_status", use_cache=False)

    async def get_player(self, tag: str, force: bool = False) -> Optional[Dict]:
        t = self.normalize_tag(tag)
        return await self._request(f"player/{t}", use_cache=not force)

    async def get_battlelog(self, tag: str, force: bool = False) -> Optional[Dict]:
        t = self.normalize_tag(tag)
        return await self._request(f"player/{t}/battles", use_cache=not force, cache_ttl=60)

    async def get_club(self, tag: str, force: bool = False) -> Optional[Dict]:
        t = self.normalize_tag(tag)
        return await self._request(f"club/{t}", use_cache=not force)

    async def get_club_members(self, tag: str) -> Optional[Dict]:
        t = self.normalize_tag(tag)
        return await self._request(f"club/{t}/members", use_cache=False)

    async def get_brawlers(self) -> Optional[Dict]:
        return await self._request("brawlers", cache_ttl=3600)

    async def get_event_rotation(self) -> Optional[Dict]:
        return await self._request("events/rotation", cache_ttl=600)

    async def get_rankings_players(self, region: str = "global") -> Optional[Dict]:
        return await self._request(f"rankings/{region}/players", cache_ttl=120)

    async def get_rankings_clubs(self, region: str = "global") -> Optional[Dict]:
        return await self._request(f"rankings/{region}/clubs", cache_ttl=120)

    async def get_powerplay_seasons(self, region: str = "global") -> Optional[Dict]:
        return await self._request(f"rankings/{region}/powerplay/seasons", cache_ttl=3600)

    async def get_locations(self) -> Optional[Dict]:
        return await self._request("locations", cache_ttl=86400)

    async def get_player_history(self, tag: str, days: int = 30) -> Optional[Dict]:
        """Получает историю трофеев игрока."""
        t = self.normalize_tag(tag)
        return await self._request(f"player/{t}/history?days={days}", use_cache=False)

    async def generate_team_code(self, duration_seconds: int = 120) -> Optional[Dict]:
        """Генерирует код команды."""
        json_body = {"duration_seconds": duration_seconds}
        return await self._request("generate_team_code", use_cache=False, method="POST", json_body=json_body)

    async def check_team_code(self, code: str) -> Optional[Dict]:
        """Проверяет код команды."""
        return await self._request(f"team_code/{code}", use_cache=False)

    async def get_nodes(self) -> Optional[Dict]:
        """Получает список узлов сети."""
        return await self._request("nodes", use_cache=False)

    async def get_rating(self) -> Optional[Dict]:
        """Получает рейтинг текущего пользователя."""
        return await self._request("rating/my", use_cache=False)

    async def add_rating(self, action_type: str, object_id: Optional[str] = None) -> bool:
        """Добавляет очки рейтинга."""
        json_body = {"action_type": action_type, "object_id": object_id}
        result = await self._request("rating/add", use_cache=False, method="POST", json_body=json_body)
        return bool(result and result.get("success"))
