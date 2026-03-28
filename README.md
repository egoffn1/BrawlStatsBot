<!--
  Brawl Stats Bot — обновлённый README.md с системой рейтинга, расширенным API, PostgreSQL/Redis и новыми эндпоинтами
-->

<div align="center">
  <h1>🎮 Brawl Stats Bot v2</h1>
  <p><strong>Универсальный инструмент для анализа Brawl Stars</strong><br/>
  CLI, Telegram‑бот, REST API, синхронизация с GitHub, непрерывный сбор данных, система рейтинга, распределённый кэш и расширенная статистика</p>
  <p>
    <a href="#-быстрый-старт">Быстрый старт</a> •
    <a href="#-использование-api">Использование API</a> •
    <a href="#-документация-api">Документация API</a> •
    <a href="#-интеграция-с-github">GitHub Sync</a> •
    <a href="#-установка-на-сервер">Деплой</a>
  </p>
  <p>
    <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python">
    <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
    <img src="https://img.shields.io/badge/API-FastAPI-brightgreen" alt="FastAPI">
    <img src="https://img.shields.io/badge/Telegram-Bot-blue" alt="Telegram">
    <img src="https://img.shields.io/badge/CLI-Rich-orange" alt="CLI">
    <img src="https://img.shields.io/badge/Rating-Server%20Based-yellow" alt="Rating">
    <img src="https://img.shields.io/badge/Database-PostgreSQL-blueviolet" alt="PostgreSQL">
    <img src="https://img.shields.io/badge/Cache-Redis-red" alt="Redis">
  </p>
  <p>
    📦 Все данные (игроки, клубы, история) хранятся в отдельной ветке  
    <strong><a href="https://github.com/egoffn1/BrawlStatsBot/tree/brawl_data/brawl_data">brawl_data</a></strong>
  </p>
</div>

---

## ✨ Возможности

| Компонент | Описание |
|-----------|----------|
| **CLI** | Интерактивное меню на `rich` и `prompt_toolkit`, цветной вывод, поиск игроков, сохранение статистики в PNG. **Автоматическая генерация API‑ключа** при первом запуске. |
| **Telegram‑бот** | Freemium (10 запросов/день), Premium за Telegram Stars, поддержка прокси, команды: `/player`, `/battles`, `/club`, `/rank`, `/rotation`, `/search`, `/premium`, `/donate`, `/status`. |
| **REST API (v2)** | FastAPI, Swagger UI, аутентификация по API‑ключу с лимитами, кэширование в Redis, распределённая сеть узлов. **Публичная генерация ключей** через `/generate_key`. |
| **Расширенная статистика** | История трофеев игроков и клубов, детальные бои, статистика бойцов, рейтинги карт и режимов, командная аналитика, глобальные рейтинги. |
| **GitHub Sync** | Экспорт данных (игроки, клубы) в JSON, импорт из репозитория. |
| **Непрерывное заполнение** | Автоматическая генерация тегов, проверка существования, сбор данных с периодической выгрузкой в GitHub. |
| **Система рейтинга** | Начисление очков за полезные действия (просмотр профиля, поиск, сохранение PNG и т.д.). **Защита от накрутки**: одно и то же действие с одним объектом можно выполнить не чаще раза в 5 минут. Рейтинг хранится на сервере, подделать локально невозможно. |
| **Асинхронность** | Полностью асинхронный код на `aiohttp`, `asyncpg`, `redis`, высокая производительность. |
| **PostgreSQL + Redis** | Основное хранилище метаданных и расширенной статистики, Redis – кэш и распределённые блокировки. |

---

## 📦 Быстрый старт

### 1. Установка

```bash
git clone https://github.com/egoffn1/BrawlStatsBot.git
cd BrawlStatsBot
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

### 2. Настройка `.env`

Заполните основные переменные (ключи Brawl Stars не обязательны, без них работают функции, использующие GitHub-базу):

```ini
# GitHub
GITHUB_REPO=egoffn1/BrawlStatsBot
GITHUB_BRANCH=main
GITHUB_TOKEN=ваш_токен_github

# API
ADMIN_SECRET=ваш_секрет
DEFAULT_DAILY_LIMIT=10000
API_PORT=80

# PostgreSQL (обязательно)
POSTGRES_DSN=postgresql://user:pass@localhost:5432/brawlstats

# Redis (обязательно)
REDIS_URL=redis://localhost:6379

# Настройки узла (для распределённой сети)
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
| `python main.py bot` | Telegram‑бот |
| `python main.py api` | REST API |
| `python main.py all` | Бот + API вместе |

API доступен по адресу `http://130.12.46.224`. Swagger UI: `/docs`.

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

Пример ответа:

```json
{
  "key": "eyJhbGci...",
  "name": "My App",
  "daily_limit": 10000,
  "used_today": 3,
  "remaining": 9997,
  "created_at": "2025-03-27 14:30:00"
}
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
```

### Использование в браузере (Swagger UI)

Откройте `http://130.12.46.224/docs`, нажмите **Authorize**, вставьте ключ и пользуйтесь интерактивной документацией.

---

## 📚 Документация API

Полная документация API доступна в отдельном файле [API.md](API.md) и по адресу `http://130.12.46.224/docs`.

Основные эндпоинты (v2):

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/players` | Список тегов игроков (пагинация) |
| `GET` | `/player/{tag}` | Полная информация об игроке |
| `GET` | `/player/{tag}/history` | История трофеев игрока |
| `GET` | `/player/{tag}/battles` | Последние бои (если есть данные) |
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
| `POST` | `/rating/add` | Начислить рейтинг за действие |
| `GET` | `/rating/my` | Получить текущий рейтинг |

> 💡 **Лимиты:** по умолчанию **10000 запросов в сутки** на ключ. При превышении возвращается статус `429`.  
> 🗄️ **Базы данных:** PostgreSQL хранит историю, бои, рейтинги; Redis кэширует списки и индексы.  
> 🌐 **Распределённая сеть:** несколько узлов API могут обмениваться данными через внутренние эндпоинты, увеличивая отказоустойчивость.

---

## ⭐ Система рейтинга

Рейтинг мотивирует пользователей вносить вклад в базу данных.  
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
| Непрерывное заполнение (за каждого игрока) | 20 | 5 мин на игрока |
| Генерация кодов | 2 | 5 мин |
| Синхронизация с GitHub | 5 | 5 мин |

### Как посмотреть рейтинг

- **CLI**: выберите пункт меню **⭐ Мой рейтинг**.
- **API**: `GET /rating/my?api_key=ваш_ключ`.

---

## 🐙 Интеграция с GitHub

Данные автоматически синхронизируются с репозиторием GitHub в папке `brawl_data/`.  
Это позволяет:

- Совместно использовать базу данных между несколькими экземплярами приложения.
- Резервное копирование.
- Удобный экспорт в JSON.

### Настройка

В `.env` укажите `GITHUB_REPO`, `GITHUB_BRANCH`, `GITHUB_TOKEN`.  
В `config.yaml` можно настроить автосинхронизацию (опционально).

---

## 🚀 Установка на сервер

Для продакшн‑развёртывания рекомендуем использовать **Docker Compose** с PostgreSQL и Redis:

```yaml
# docker-compose.yml (упрощённый)
version: '3.8'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
      POSTGRES_DB: brawlstats
    volumes:
      - postgres_data:/var/lib/postgresql/data
  redis:
    image: redis:7
  api:
    build: .
    ports:
      - "80:80"
    depends_on:
      - postgres
      - redis
    environment:
      POSTGRES_DSN: postgresql://user:pass@postgres:5432/brawlstats
      REDIS_URL: redis://redis:6379
```

Затем:

```bash
docker-compose up -d
```

Подробная инструкция по ручной установке на Ubuntu описана в [DEPLOY.md](DEPLOY.md).

---

## 🤝 Вклад в проект

Мы приветствуем любые улучшения! Если вы хотите внести свой вклад:

1. Форкните репозиторий.
2. Создайте ветку для вашей фичи (`git checkout -b feature/amazing`).
3. Сделайте коммит (`git commit -m 'Add amazing feature'`).
4. Отправьте изменения (`git push origin feature/amazing`).
5. Откройте Pull Request.
6. Обычный донат тоже очень сильно поможет развитию.

---

<div align="center">
  <sub>Сделано с ❤️ для сообщества Brawl Stars</sub>
</div>
```
