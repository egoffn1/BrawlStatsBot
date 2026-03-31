<div align="center">
  <h1>🎮 BrawlNest</h1>
  <p><strong>Распределённая сеть для анализа Brawl Stars</strong><br/>
  REST API, Telegram‑бот, CLI, синхронизация с GitHub, непрерывный сбор данных, система рейтинга, распределённый кэш и расширенная статистика</p>
  <p>
    <a href="#-быстрый-старт">Быстрый старт</a> •
    <a href="#-использование-api">Использование API</a> •
    <a href="#-документация-api">Документация API</a> •
    <a href="#-интеграция-с-github">GitHub Sync</a> •
    <a href="#-установка-на-сервер">Деплой</a>
  </p>
  <p>
    <img src="https://img.shields.io/badge/Python-3.11%2B-blue" alt="Python">
    <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
    <img src="https://img.shields.io/badge/API-FastAPI-brightgreen" alt="FastAPI">
    <img src="https://img.shields.io/badge/Telegram-Bot-blue" alt="Telegram">
    <img src="https://img.shields.io/badge/Distributed-Yes-orange" alt="Distributed">
    <img src="https://img.shields.io/badge/Cache-Redis-red" alt="Redis">
    <img src="https://img.shields.io/badge/Storage-PostgreSQL-blueviolet" alt="PostgreSQL">
  </p>
  <p>
    📦 Все основные данные (игроки, клубы, история, коды команд) хранятся в отдельной ветке  
    <strong><a href="https://github.com/egoffn1/BrawlNest/tree/brawl_data/brawl_data">brawl_data</a></strong>
  </p>
</div>

---

## ✨ Возможности

| Компонент | Описание |
|-----------|----------|
| **REST API (v2)** | FastAPI, Swagger UI, аутентификация по API‑ключу с лимитами, кэширование в Redis, **распределённая сеть** с автоматическим выбором самого быстрого узла по пингу. Генерация **кодов команд** (team codes) для быстрого объединения в игре. |
| **Распределённая сеть** | Несколько независимых узлов API, объединённых общим Redis. Каждый узел периодически измеряет пинг до других, клиентские запросы перенаправляются на самый быстрый активный узел (HTTP 307). Отказоустойчивость: при падении узла трафик автоматически переключается. |
| **Телеграм‑бот** | Freemium (10 запросов/день), Premium за Telegram Stars, поддержка прокси, команды: `/player`, `/battles`, `/club`, `/rank`, `/rotation`, `/search`, `/premium`, `/donate`, `/status`. |
| **CLI** | Интерактивное меню на `rich` и `prompt_toolkit`, цветной вывод, поиск игроков, сохранение статистики в PNG. **Автоматическая генерация API‑ключа** при первом запуске. |
| **Расширенная статистика** | История трофеев игроков и клубов, детальные бои, статистика бойцов, рейтинги карт и режимов, командная аналитика, глобальные рейтинги. |
| **GitHub Sync** | Все данные (игроки, клубы, история трофеев, бои, командная статистика, коды команд) синхронизируются с веткой `brawl_data` в JSON‑файлах. Это обеспечивает единое хранилище для всех узлов. |
| **Непрерывное заполнение** | Автоматическая генерация тегов, проверка существования, сбор данных с периодической выгрузкой в GitHub. |
| **Система рейтинга** | Начисление очков за полезные действия (просмотр профиля, поиск, сохранение PNG и т.д.). **Защита от накрутки**: одно и то же действие с одним объектом можно выполнить не чаще раза в 5 минут. Рейтинг хранится на сервере, подделать локально невозможно. |
| **PostgreSQL + Redis** | PostgreSQL — основное хранилище метаданных (API‑ключи, использование, рейтинги) и расширенной статистики (бои, командная статистика, карты). Redis — кэш (игроки, клубы, индексы имён) и распределённые блокировки для фоновых задач. |
| **Асинхронность** | Полностью асинхронный код на `aiohttp`, `asyncpg`, `redis`, высокая производительность. |

---

## 📦 Быстрый старт

### 1. Установка

```bash
git clone https://github.com/egoffn1/BrawlNest.git
cd BrawlNest
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

### 2. Настройка `.env`

Заполните основные переменные. **Ключ Brawl Stars обязателен** для получения актуальных данных из официального API (при отсутствии данных в GitHub).

```ini
# GitHub (обязательно, даже только для чтения)
GITHUB_REPO=egoffn1/BrawlNest
GITHUB_BRANCH=brawl_data
GITHUB_TOKEN=ваш_токен_github   # нужен для записи, можно оставить пустым, если только чтение

# Brawl Stars API (обязательно)
BRAWL_API_KEY=ваш_ключ_от_brawl_stars

# Админка и лимиты
ADMIN_SECRET=ваш_секрет
DEFAULT_DAILY_LIMIT=10000
API_PORT=80

# Базы данных (обязательны)
POSTGRES_DSN=postgresql://user:pass@postgres:5432/brawlnest
REDIS_URL=redis://redis:6379

# Настройки узла для распределённой сети
NODE_ADDRESS=http://localhost:80
NODE_SECRET=some_random_secret
PEER_REQUEST_TIMEOUT=2

# Интервалы фоновых задач (часы)
TROPHY_COLLECTION_INTERVAL_H=6
MAP_STATS_REFRESH_INTERVAL_H=1
NAME_INDEX_REFRESH_INTERVAL_H=2
```

### 3. Запуск

| Команда | Режим |
|---------|-------|
| `python cli.py` | Интерактивное CLI |
| `python bot.py` | Telegram‑бот |
| `uvicorn api.rest_api:app --host 0.0.0.0 --port 80` | REST API (ручной запуск) |
| `docker-compose up -d` | Запуск всех сервисов в контейнерах |

После запуска API доступен по адресу `http://130.12.46.224` (или вашему домену). Swagger UI: `/docs`.

---

## 🔑 Использование API

Все защищённые эндпоинты (кроме `/generate_key`) требуют передачи API‑ключа в заголовке `X-API-Key`.

### Получение ключа (публично)

```bash
curl -X POST http://130.12.46.224/generate_key \
  -H "Content-Type: application/json" \
  -d '{"name": "My App"}'
```

Ответ:

```json
{
  "key": "eyJhbGciOiJIUzI1NiIs...",
  "name": "My App",
  "daily_limit": 10000,
  "created_at": "now"
}
```

### Проверка статуса ключа

```bash
curl -H "X-API-Key: ваш_ключ" http://130.12.46.224/my_status
```

### Примеры запросов

```bash
# Список игроков (первые 10)
curl -H "X-API-Key: ваш_ключ" "http://130.12.46.224/players?limit=10"

# Данные игрока по тегу (без #)
curl -H "X-API-Key: ваш_ключ" "http://130.12.46.224/player/8UG9C0L"

# История трофеев игрока
curl -H "X-API-Key: ваш_ключ" "http://130.12.46.224/player/8UG9C0L/history?days=7"

# Статистика бойцов игрока
curl -H "X-API-Key: ваш_ключ" "http://130.12.46.224/player/8UG9C0L/brawlers"

# Поиск игроков по имени (быстрый индекс Redis)
curl -H "X-API-Key: ваш_ключ" "http://130.12.46.224/search/players?name=Carlos"

# Рейтинг игроков (топ)
curl -H "X-API-Key: ваш_ключ" "http://130.12.46.224/rankings/players?limit=10"

# Статистика по картам
curl -H "X-API-Key: ваш_ключ" "http://130.12.46.224/maps?limit=10"

# Генерация кода команды
curl -X POST http://130.12.46.224/generate_team_code \
  -H "X-API-Key: ваш_ключ" \
  -H "Content-Type: application/json" \
  -d '{"duration_seconds": 120}'
```

Ответ:

```json
{
  "code": "XSJ2Z4T",
  "expires_at": "2025-04-01T15:34:56Z",
  "duration_seconds": 120
}
```

### Использование в браузере (Swagger UI)

Откройте `http://130.12.46.224/docs`, нажмите **Authorize**, вставьте ключ и пользуйтесь интерактивной документацией.

---

## 📚 Документация API

Полная документация API BrawlNest доступна по адресу `http://130.12.46.224/docs` и в формате OpenAPI.

**Основные эндпоинты (v2):**

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/players` | Список тегов игроков (пагинация) |
| `GET` | `/player/{tag}` | Полная информация об игроке |
| `GET` | `/player/{tag}/history` | История трофеев игрока |
| `GET` | `/player/{tag}/battles` | Последние бои (из GitHub) |
| `GET` | `/player/{tag}/battles/stats` | Агрегированная статистика боёв |
| `GET` | `/player/{tag}/brawlers` | Статистика бойцов игрока |
| `GET` | `/clubs` | Список клубов |
| `GET` | `/club/{tag}` | Данные клуба |
| `GET` | `/club/{tag}/history` | История клуба (трофеи, состав) |
| `GET` | `/search/players?name=` | Быстрый поиск игроков по имени |
| `GET` | `/search/clubs?name=` | Быстрый поиск клубов по названию |
| `GET` | `/maps` | Статистика по картам (топ) |
| `GET` | `/maps/{map_name}` | Статистика конкретной карты |
| `GET` | `/team/stats?tags=` | Статистика команды (2–3 игрока) |
| `GET` | `/rankings/players` | Глобальный рейтинг игроков |
| `GET` | `/rankings/clubs` | Глобальный рейтинг клубов |
| `GET` | `/brawlers` | Список бойцов |
| `GET` | `/brawlers/{id}/rankings` | Топ игроков по бойцу |
| `GET` | `/my_status` | Статус вашего ключа (лимит, использовано) |
| `POST` | `/generate_key` | Публичная генерация нового API‑ключа |
| `POST` | `/generate_team_code` | Генерация кода команды (X + 6 символов) |
| `GET` | `/team_code/{code}` | Проверка активности кода команды |
| `POST` | `/rating/add` | Начислить рейтинг за действие |
| `GET` | `/rating/my` | Получить текущий рейтинг |
| `GET` | `/rating/leaderboard` | Топ рейтинга |

> 💡 **Лимиты:** по умолчанию **10000 запросов в сутки** на ключ. При превышении возвращается статус `429`.  
> 🌐 **Распределённая сеть:** несколько узлов API могут обмениваться данными через внутренние эндпоинты, а клиент автоматически перенаправляется на самый быстрый узел.

---

## ⭐ Система рейтинга

Рейтинг BrawlNest мотивирует пользователей вносить вклад в базу данных.  
Очки начисляются **только через сервер**, локальная подделка невозможна.

### Начисление очков

| Действие | Очки | Защита от накрутки (cooldown) |
|----------|------|-------------------------------|
| Просмотр профиля игрока | 1 | 5 мин на игрока |
| Просмотр боевого лога | 1 | 5 мин на игрока |
| Просмотр клуба | 1 | 5 мин на клуб |
| Поиск игрока по имени | 5 | 5 мин на запрос |
| Сохранение PNG | 5 | 5 мин на игрока |
| Полный сбор клуба | 10 | 5 мин на клуб |
| Обнаружение командной игры | 10 | 5 мин |
| Поиск существующих игроков | 2 | 5 мин |
| Заполнение БД (однократно) | 20 | 1 раз в день |
| Непрерывное заполнение (за игрока) | 20 | 5 мин на игрока |
| Генерация кодов | 2 | 5 мин |
| Синхронизация с GitHub | 5 | 5 мин |

---

## 🐙 Интеграция с GitHub

Все основные данные BrawlNest синхронизируются с репозиторием GitHub в ветке **`brawl_data`**:

- `players/` – JSON с данными игроков (тег как имя)
- `clubs/` – JSON с данными клубов
- `trophy_history/` – история трофеев по дням
- `club_history/` – история клубов
- `battles/` – бои игроков (если собраны)
- `player_brawler_stats/` – статистика бойцов по игрокам
- `team_stats/` – командная статистика (по хэшу тегов)
- `rankings/players/` и `rankings/clubs/` – ежедневные рейтинги
- `team_codes/` – активные коды команд (автоматически удаляются по истечении срока)
- `map_stats.json` – агрегированная статистика карт

### Настройка синхронизации

В `.env` укажите `GITHUB_REPO`, `GITHUB_BRANCH` (`brawl_data`), `GITHUB_TOKEN` (если нужна запись). При отсутствии токена данные будут только читаться из репозитория.

---

## 🚀 Установка на сервер (Docker Compose)

Для продакшн‑развёртывания используйте Docker Compose. Пример `docker-compose.yml`:

```yaml
version: "3.9"
services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
      POSTGRES_DB: brawlnest
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user -d brawlnest"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  api:
    build: .
    ports:
      - "80:80"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    env_file: .env
    environment:
      POSTGRES_DSN: postgresql://user:pass@postgres:5432/brawlnest
      REDIS_URL: redis://redis:6379
      NODE_ADDRESS: http://api:80
    restart: unless-stopped

volumes:
  pgdata:
  redisdata:
```

Затем выполните:

```bash
docker-compose up -d --build
```

После запуска API будет доступно по порту 80.

### Запуск нескольких узлов

Для создания распределённой сети запустите несколько экземпляров на разных машинах (или с разными портами), указав:

- Общий Redis (например, выделенный сервер Redis) в переменной `REDIS_URL`.
- Уникальные `NODE_ADDRESS` для каждого узла.
- Одинаковый `NODE_SECRET` для всех узлов.

Узлы автоматически обнаружат друг друга через Redis и будут измерять пинг. Клиентские запросы будут перенаправляться на самый быстрый активный узел.

---

## 🤝 Вклад в проект

Мы приветствуем любые улучшения BrawlNest! Если вы хотите внести свой вклад:

1. Форкните репозиторий.
2. Создайте ветку для вашей фичи (`git checkout -b feature/amazing`).
3. Сделайте коммит (`git commit -m 'Add amazing feature'`).
4. Отправьте изменения (`git push origin feature/amazing`).
5. Откройте Pull Request.

---

<div align="center">
  <sub>Сделано с ❤️ для сообщества Brawl Stars в рамках BrawlNest</sub>
</div>
```
