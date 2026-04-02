# Brawl Stats Bot – Данные (ветка `brawl_data`)

Эта ветка содержит все данные, используемые API Brawl Stats Bot. Данные организованы в папке `brawl_data`.

## 📁 Структура папок

```
brawl_data/
├── players/               # JSON-файлы игроков
├── clubs/                 # JSON-файлы клубов
├── trophy_history/        # История трофеев игроков
├── club_history/          # История клубов
├── battles/               # Данные о боях
├── player_brawler_stats/  # Статистика бойцов по игрокам
├── team_stats/            # Командная статистика
├── rankings/              # Ежедневные рейтинги
├── team_codes/            # Активные коды команд
└── map_stats.json         # Агрегированная статистика карт
```

## 📄 Форматы данных

### `players/{tag}.json`
Полный объект игрока из официального API Brawl Stars.

### `clubs/{tag}.json`
Полный объект клуба.

### `trophy_history/{tag}.json`
```json
[
  { "date": "2025-03-28", "trophies": 32000 },
  { "date": "2025-03-27", "trophies": 31850 }
]
```

### `club_history/{tag}.json`
```json
[
  {
    "date": "2025-03-28",
    "trophies": 950000,
    "member_count": 30,
    "required_trophies": 10000
  }
]
```

### `battles/{tag}.json`
```json
[
  {
    "battle_time": "2025-03-28T14:23:00Z",
    "battle_type": "solo",
    "result": "victory",
    "trophies_change": 8,
    "brawler_id": 16000002,
    "map_name": "Canyon",
    "game_mode": "Showdown",
    "teammates": [],
    "opponents": ["#ABC123"]
  }
]
```

### `player_brawler_stats/{tag}.json`
```json
[
  {
    "brawler_id": 16000000,
    "brawler_name": "Shelly",
    "trophies": 750,
    "highest_trophies": 780,
    "power": 11,
    "rank": 24
  }
]
```

### `team_stats/{hash}.json`
```json
{
  "player_tags": ["#8UG9C0L", "#2YCCU"],
  "total_battles": 42,
  "total_wins": 28,
  "last_updated": "2025-03-28T12:00:00Z"
}
```

### `rankings/players/{date}.json`
```json
{
  "date": "2025-03-28",
  "players": [
    { "tag": "#8UG9C0L", "trophies": 32000 }
  ]
}
```

### `rankings/clubs/{date}.json`
Аналогично с полями `tag`, `name`, `trophies`.

### `team_codes/{code}.json`
```json
{
  "code": "XSJ2Z4T",
  "created_at": "2025-04-01T12:34:56Z",
  "expires_at": "2025-04-01T12:36:56Z",
  "creator_api_key": "wRs7Bm_N...",
  "duration_seconds": 120
}
```
Коды команд генерируются API и автоматически удаляются после истечения срока действия.

### `map_stats.json`
```json
[
  {
    "map_name": "Canyon",
    "game_mode": "Showdown",
    "total_battles": 1240,
    "total_wins": 620,
    "avg_trophies_change": 5.2,
    "win_rate": 50.0
  }
]
```

## 🔄 Обновление данных

Данные в этой ветке обновляются автоматически фоновыми задачами API. Ручное редактирование не рекомендуется – изменения могут быть перезаписаны.

## 🛠️ Утилиты

### Валидация данных

Для проверки корректности данных используйте скрипт валидации:

```bash
# Запустить валидацию всех данных
python scripts/validate_data.py

# Запустить тесты валидатора
python tests/test_validator.py
```

Валидатор проверяет:
- ✅ Формат тегов игроков и клубов (начинаются с #)
- ✅ Форматы дат (YYYY-MM-DD) и datetime (ISO 8601)
- ✅ Диапазоны значений (трофеи ≥ 0, сила бойцов 1-11, и т.д.)
- ✅ Допустимые игровые режимы и типы боёв
- ✅ Структуру JSON файлов

### Тестирование

Тестовый набор включает 41 тест, покрывающих все аспекты валидации:

```bash
python tests/test_validator.py
```

Все тесты должны проходить успешно перед публикацией изменений.

## 📋 Схемы данных

Все типы данных описаны в JSON Schema формате в папке `schemas/`:

| Схема | Описание |
|-------|----------|
| `player.schema.json` | Данные игрока |
| `club.schema.json` | Данные клуба |
| `battle.schema.json` | Записи о боях |
| `trophy_history.schema.json` | История трофеев игрока |
| `club_history.schema.json` | История клуба |
| `player_rankings.schema.json` | Ежедневный рейтинг игроков |
| `club_rankings.schema.json` | Ежедневный рейтинг клубов |
| `team_stats.schema.json` | Командная статистика |
| `team_code.schema.json` | Коды командных приглашений |
| `map_stats.schema.json` | Статистика карт |

---

**Связанные репозитории:**  
- Основной проект: [ветка main](https://github.com/egoffn1/BrawlNest/tree/main)  
- Данные: [ветка brawl_data](https://github.com/egoffn1/BrawlNest/tree/brawl_data)
```
