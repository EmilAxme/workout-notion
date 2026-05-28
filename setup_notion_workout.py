#!/usr/bin/env python3
"""
Создаёт систему трекинга тренировок «Рекомпозиция — 12 недель» в Notion:
сплит на группы мышц, 4 дня/неделю, цель — удержать вес ~80 кг и минус 2-4 кг жира.

Перед созданием находит старую систему в том же родителе и предлагает
заархивировать её (archived=true — обратимо, через Trash в Notion UI).
"""

import os
import re
import sys
import time
import getpass
import httpx
from datetime import datetime, timedelta
from notion_client import Client, APIResponseError

# ─────────────────────────────────────────────
# КОНФИГ
# ─────────────────────────────────────────────

MAIN_PAGE_TITLE = "🏋️ Рекомпозиция — 12 недель"
WEEKS = 12
RATE_LIMIT_DELAY = 0.35
MAX_RETRIES = 5
BASE_RETRY_DELAY = 1

NOTION_BASE_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# Ключевые слова, по которым ищем старые системы тренировок в parent'е
OLD_SYSTEM_KEYWORDS = [
    "программа тренировок",
    "рекомпозиция",
    "workout",
    "тренировок — 12",
]

# ─────────────────────────────────────────────
# ПРОГРАММА
# ─────────────────────────────────────────────
# Пн=0, Вт=1, Чт=3, Пт=4
DAYS = {
    0: "Грудь+Трицепс",
    1: "Спина+Бицепс",
    3: "Ноги",
    4: "Плечи+Руки",
}

MUSCLE_GROUPS = ["Грудь", "Трицепс", "Спина", "Бицепс", "Ноги", "Плечи"]

# Шаблоны упражнений: (название, подходы, повторы, RIR, группа)
# В дефиците веса не растут по расписанию — план по неделям одинаковый,
# Вес_факт заполняется вручную. Прогрессия двойная по повторам.
WORKOUT_TEMPLATES = {
    0: [  # Пн — Грудь+Трицепс
        ("Жим штанги лёжа",                          4, "6-8",   2, "Грудь"),
        ("Жим гантелей на наклонной",                4, "8-10",  2, "Грудь"),
        ("Жим в тренажёре / брусья",                 3, "10-12", 1, "Грудь"),
        ("Сведения в кроссовере",                    3, "12-15", 1, "Грудь"),
        ("Трицепс на блоке (канат)",                 4, "10-12", 1, "Трицепс"),
        ("Французский жим / разгибания над головой", 3, "10-12", 1, "Трицепс"),
    ],
    1: [  # Вт — Спина+Бицепс
        ("Подтягивания (с весом если легко)",        4, "6-10",  2, "Спина"),
        ("Тяга штанги в наклоне",                    4, "8-10",  2, "Спина"),
        ("Тяга верхнего блока",                      3, "10-12", 1, "Спина"),
        ("Тяга гантели одной рукой",                 3, "10-12", 1, "Спина"),
        ("Подъём штанги на бицепс",                  4, "8-10",  1, "Бицепс"),
        ("Молотки с гантелями",                      3, "10-12", 1, "Бицепс"),
    ],
    3: [  # Чт — Ноги
        ("Присед со штангой",                        4, "8-10",       2, "Ноги"),
        ("Жим ногами",                               3, "12-15",      1, "Ноги"),
        ("Румынская тяга",                           3, "10-12",      2, "Ноги"),
        ("Болгарские выпады",                        3, "10-12 на ногу", 1, "Ноги"),
        ("Сгибания ног лёжа",                        3, "12-15",      1, "Ноги"),
        ("Икры стоя",                                4, "15-20",      1, "Ноги"),
    ],
    4: [  # Пт — Плечи+Руки
        ("Жим гантелей / штанги сидя",               4, "8-10",  2, "Плечи"),
        ("Махи в стороны",                           4, "12-15", 1, "Плечи"),
        ("Махи в наклоне",                           3, "15",    1, "Плечи"),
        ("Скамья Скотта / гантели на бицепс",        4, "10-12", 1, "Бицепс"),
        ("Трицепс на блоке обратным хватом",         4, "10-12", 1, "Трицепс"),
        ("Суперсет: молоток + подъём на бицепс",     3, "12",    0, "Бицепс"),
    ],
}

WEEK_7_NOTE = "Диета-брейк: калории на поддержке ~2790 ккал"

PERSONAL_RECORDS = [
    # (Упражнение, Рабочий_вес_кг, Лучшие_повторы)
    ("Жим штанги лёжа",          80, 5),
    ("Присед со штангой",        50, 10),
    ("Подтягивания (свой вес)",  None, 21),
    ("Подъём штанги на бицепс",  20, 10),
]


# ─────────────────────────────────────────────
# УТИЛИТЫ
# ─────────────────────────────────────────────

def api_call(fn, *args, **kwargs):
    """Вызов Notion SDK с rate-limit + retry на 429/5xx."""
    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(RATE_LIMIT_DELAY)
            return fn(*args, **kwargs)
        except APIResponseError as e:
            if e.status in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                delay = BASE_RETRY_DELAY * (2 ** attempt)
                print(f"\n⏳ {e.status}, повтор через {delay}с (попытка {attempt + 2}/{MAX_RETRIES})...")
                time.sleep(delay)
            else:
                raise
    raise RuntimeError("Не удалось выполнить запрос после всех попыток")


def raw_create_database(token, body):
    """Создаёт БД через прямой HTTP — обход бага SDK 2.7 с properties."""
    for attempt in range(MAX_RETRIES):
        time.sleep(RATE_LIMIT_DELAY)
        resp = httpx.post(
            f"{NOTION_BASE_URL}/databases",
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=30,
        )
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
            delay = BASE_RETRY_DELAY * (2 ** attempt)
            print(f"\n⏳ {resp.status_code}, повтор через {delay}с...")
            time.sleep(delay)
            continue
        if resp.status_code != 200:
            raise RuntimeError(f"Notion API {resp.status_code}: {resp.text}")
        return resp.json()
    raise RuntimeError("Не удалось создать БД после всех попыток")


def get_next_monday():
    """Возвращает ближайший понедельник (включая сегодня, если сегодня Пн)."""
    today = datetime.now().date()
    return today + timedelta(days=(-today.weekday()) % 7)


def page_url(page_id):
    return f"https://notion.so/{page_id.replace('-', '')}"


def normalize_parent_id(raw):
    """Извлекает 32-hex Notion ID из любого формата: чистый ID, ID с дефисами,
    или URL вида notion.so/.../<id>, notion.site/..., app.notion.com/p/<id>?..."""
    raw = raw.strip()
    m = re.findall(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        raw,
    )
    if m:
        return m[-1].replace("-", "")
    m = re.findall(r"[0-9a-fA-F]{32}", raw)
    if m:
        return m[-1]
    return raw.replace("-", "")


# ─────────────────────────────────────────────
# ШАГИ
# ─────────────────────────────────────────────

def get_credentials():
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        token = getpass.getpass("🔑 Notion Integration Token: ")
    parent_id = os.environ.get("NOTION_PARENT_PAGE_ID")
    if not parent_id:
        parent_id = input("📄 Parent Page ID (или URL страницы): ").strip()
    return token, normalize_parent_id(parent_id)


def check_connection(notion):
    print("🔍 Проверка подключения к Notion...", end=" ", flush=True)
    try:
        api_call(notion.users.me)
        print("✅")
        return True
    except Exception as e:
        print(f"❌\n   {e}")
        return False


def find_old_systems(notion, parent_id):
    """Возвращает список (title, page_id) дочерних страниц parent'а,
    у которых в названии есть ключевое слово старой системы."""
    found = []
    cursor = None
    while True:
        kwargs = {"block_id": parent_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        try:
            resp = api_call(notion.blocks.children.list, **kwargs)
        except APIResponseError as e:
            print(f"\n⚠️  Не удалось прочитать содержимое parent'а: {e.status} — {e.body}")
            return []
        for block in resp.get("results", []):
            if block.get("type") != "child_page":
                continue
            title = block.get("child_page", {}).get("title", "")
            tl = title.lower()
            if any(k in tl for k in OLD_SYSTEM_KEYWORDS):
                found.append((title, block["id"]))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return found


def maybe_archive_old(notion, parent_id):
    """Ищет похожие на старую систему страницы и предлагает архивировать каждую."""
    print("🔍 Поиск старых страниц программы тренировок в parent'е...", end=" ", flush=True)
    candidates = [(t, pid) for t, pid in find_old_systems(notion, parent_id)
                  if t != MAIN_PAGE_TITLE]
    print(f"найдено: {len(candidates)}")

    if not candidates:
        print("   Старых систем не найдено — продолжаем.")
        return

    print()
    print("   Найдены страницы (возможно — старая программа тренировок):")
    for i, (title, _pid) in enumerate(candidates, 1):
        print(f"   {i}. {title}")

    print()
    print("   Notion-архивация — это перемещение в Trash, восстанавливается через UI.")
    answer = input("   Архивировать перечисленные страницы? (y/N): ").strip().lower()
    if answer != "y":
        print("   Архивация пропущена.")
        return

    for title, pid in candidates:
        print(f"   📦 Архивирую: {title}...", end=" ", flush=True)
        try:
            api_call(notion.pages.update, page_id=pid, archived=True)
            print("✅")
        except APIResponseError as e:
            print(f"❌ {e.status} — {e.body}")


def create_main_page(notion, parent_id):
    print("📁 Создание главной страницы...", end=" ", flush=True)
    callout_text = (
        "Цель: РЕКОМПОЗИЦИЯ.\n"
        "• Вес ~80 кг (держим), жир −2-4 кг.\n"
        "• Приоритеты по объёму: грудь, руки, ноги.\n"
        "• Питание: ~2400 ккал, белок 180 г.\n"
        "• Прогрессия: двойная по повторам (добиваем верх диапазона → +вес/+подход).\n"
        "• Цель силы: УДЕРЖАТЬ в дефиците (рост маловероятен).\n\n"
        "Структура: 4 дня/неделю × 12 недель = 48 тренировок.\n"
        "Пн — Грудь+Трицепс\n"
        "Вт — Спина+Бицепс\n"
        "Чт — Ноги\n"
        "Пт — Плечи+Руки\n\n"
        "Неделя 7 — диета-брейк (калории на поддержке ~2790 ккал)."
    )
    page = api_call(
        notion.pages.create,
        parent={"page_id": parent_id},
        properties={"title": [{"text": {"content": MAIN_PAGE_TITLE}}]},
        icon={"type": "emoji", "emoji": "🏋️"},
        children=[
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "icon": {"type": "emoji", "emoji": "🎯"},
                    "rich_text": [{"type": "text", "text": {"content": callout_text}}],
                    "color": "blue_background",
                },
            },
            {"object": "block", "type": "divider", "divider": {}},
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "📋 Базы данных"}}],
                },
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{
                        "type": "text",
                        "text": {"content":
                            "Тренировки / Упражнения / Прогресс тела / Личные рекорды — все БД ниже на этой странице."},
                    }],
                },
            },
        ],
    )
    url = page_url(page["id"])
    print(f"✅\n   {url}")
    return page["id"]


def create_workouts_db(token, page_id):
    print("🗄️  БД «Тренировки»...", end=" ", flush=True)
    db = raw_create_database(token, {
        "parent": {"type": "page_id", "page_id": page_id},
        "title": [{"type": "text", "text": {"content": "Тренировки"}}],
        "icon": {"type": "emoji", "emoji": "📅"},
        "properties": {
            "Название": {"title": {}},
            "Дата": {"date": {}},
            "Неделя": {"number": {"format": "number"}},
            "День": {
                "select": {
                    "options": [
                        {"name": "Грудь+Трицепс", "color": "pink"},
                        {"name": "Спина+Бицепс", "color": "blue"},
                        {"name": "Ноги", "color": "green"},
                        {"name": "Плечи+Руки", "color": "orange"},
                    ]
                }
            },
            "Статус": {
                "select": {
                    "options": [
                        {"name": "Запланировано", "color": "default"},
                        {"name": "Выполнено", "color": "green"},
                        {"name": "Пропущено", "color": "red"},
                    ]
                }
            },
            "Самочувствие": {
                "select": {
                    "options": [
                        {"name": "😴 Усталый", "color": "red"},
                        {"name": "😐 Норм", "color": "yellow"},
                        {"name": "💪 Бодрый", "color": "green"},
                    ]
                }
            },
            "Сон_часов": {"number": {"format": "number"}},
            "Вес_утром_кг": {"number": {"format": "number"}},
            "Заметки": {"rich_text": {}},
        },
    })
    print("✅")
    return db["id"]


def create_exercises_db(token, page_id, workouts_db_id):
    print("🗄️  БД «Упражнения»...", end=" ", flush=True)
    db = raw_create_database(token, {
        "parent": {"type": "page_id", "page_id": page_id},
        "title": [{"type": "text", "text": {"content": "Упражнения"}}],
        "icon": {"type": "emoji", "emoji": "💪"},
        "properties": {
            "Упражнение": {"title": {}},
            "Тренировка": {
                "relation": {
                    "database_id": workouts_db_id,
                    "type": "dual_property",
                    "dual_property": {},
                }
            },
            "Дата": {"date": {}},
            "Группа": {
                "select": {
                    "options": [
                        {"name": "Грудь",   "color": "pink"},
                        {"name": "Трицепс", "color": "red"},
                        {"name": "Спина",   "color": "blue"},
                        {"name": "Бицепс",  "color": "purple"},
                        {"name": "Ноги",    "color": "green"},
                        {"name": "Плечи",   "color": "orange"},
                    ]
                }
            },
            "Подходы_план": {"number": {"format": "number"}},
            "Повторы_план": {"rich_text": {}},
            "RIR_план": {"number": {"format": "number"}},
            "Вес_факт": {"number": {"format": "number"}},
            "Повторы_факт": {"rich_text": {}},
            "Выполнено": {"checkbox": {}},
        },
    })
    print("✅")
    return db["id"]


def create_body_progress_db(token, page_id):
    print("🗄️  БД «Прогресс тела»...", end=" ", flush=True)
    db = raw_create_database(token, {
        "parent": {"type": "page_id", "page_id": page_id},
        "title": [{"type": "text", "text": {"content": "Прогресс тела"}}],
        "icon": {"type": "emoji", "emoji": "📊"},
        "properties": {
            "Дата": {"title": {}},
            "Вес_кг": {"number": {"format": "number"}},
            "Жир_%": {"number": {"format": "percent"}},
            "Талия_см": {"number": {"format": "number"}},
            "Грудь_см": {"number": {"format": "number"}},
            "Бицепс_см": {"number": {"format": "number"}},
            "Бедро_см": {"number": {"format": "number"}},
            "Заметки": {"rich_text": {}},
        },
    })
    print("✅")
    return db["id"]


def create_records_db(token, page_id):
    print("🗄️  БД «Личные рекорды»...", end=" ", flush=True)
    db = raw_create_database(token, {
        "parent": {"type": "page_id", "page_id": page_id},
        "title": [{"type": "text", "text": {"content": "Личные рекорды"}}],
        "icon": {"type": "emoji", "emoji": "🏆"},
        "properties": {
            "Упражнение": {"title": {}},
            "Рабочий_вес_кг": {"number": {"format": "number"}},
            "Лучшие_повторы": {"number": {"format": "number"}},
            "Дата": {"date": {}},
        },
    })
    print("✅")
    return db["id"]


def fill_workouts(notion, db_id):
    start_monday = get_next_monday()
    total = WEEKS * len(DAYS)
    print(f"📝 Тренировки: 0/{total}", end="", flush=True)

    workout_pages = {}  # (week, day_offset) -> page_id
    count = 0
    for week in range(1, WEEKS + 1):
        week_start = start_monday + timedelta(weeks=week - 1)
        for day_offset, day_name in DAYS.items():
            date = week_start + timedelta(days=day_offset)
            title = f"Нед {week} — {day_name}"

            properties = {
                "Название": {"title": [{"text": {"content": title}}]},
                "Дата": {"date": {"start": date.isoformat()}},
                "Неделя": {"number": week},
                "День": {"select": {"name": day_name}},
                "Статус": {"select": {"name": "Запланировано"}},
            }
            if week == 7:
                properties["Заметки"] = {
                    "rich_text": [{"text": {"content": WEEK_7_NOTE}}]
                }

            page = api_call(
                notion.pages.create,
                parent={"database_id": db_id},
                properties=properties,
            )
            workout_pages[(week, day_offset)] = page["id"]
            count += 1
            print(f"\r📝 Тренировки: {count}/{total}", end="", flush=True)
    print(" ✅")
    return workout_pages


def fill_exercises(notion, db_id, workout_pages):
    start_monday = get_next_monday()
    items = []
    for week in range(1, WEEKS + 1):
        week_start = start_monday + timedelta(weeks=week - 1)
        for day_offset, template in WORKOUT_TEMPLATES.items():
            date = week_start + timedelta(days=day_offset)
            workout_id = workout_pages[(week, day_offset)]
            for ex in template:
                items.append((ex, workout_id, date))

    total = len(items)
    print(f"💪 Упражнения: 0/{total}", end="", flush=True)
    for i, (ex, workout_id, date) in enumerate(items, 1):
        name, sets, reps, rir, group = ex
        properties = {
            "Упражнение": {"title": [{"text": {"content": name}}]},
            "Тренировка": {"relation": [{"id": workout_id}]},
            "Дата": {"date": {"start": date.isoformat()}},
            "Группа": {"select": {"name": group}},
            "Подходы_план": {"number": sets},
            "Повторы_план": {"rich_text": [{"text": {"content": reps}}]},
            "RIR_план": {"number": rir},
            "Выполнено": {"checkbox": False},
        }
        api_call(
            notion.pages.create,
            parent={"database_id": db_id},
            properties=properties,
        )
        print(f"\r💪 Упражнения: {i}/{total}", end="", flush=True)
    print(" ✅")


def fill_body_progress(notion, db_id):
    print("📊 Стартовая запись прогресса тела...", end=" ", flush=True)
    today = datetime.now().date().isoformat()
    api_call(
        notion.pages.create,
        parent={"database_id": db_id},
        properties={
            "Дата": {"title": [{"text": {"content": today}}]},
            "Вес_кг": {"number": 80},
            "Заметки": {"rich_text": [{"text": {"content": "Старт рекомпозиции"}}]},
        },
    )
    print("✅")


def fill_records(notion, db_id):
    print("🏆 Личные рекорды...", end=" ", flush=True)
    today = datetime.now().date().isoformat()
    for name, weight, reps in PERSONAL_RECORDS:
        properties = {
            "Упражнение": {"title": [{"text": {"content": name}}]},
            "Лучшие_повторы": {"number": reps},
            "Дата": {"date": {"start": today}},
        }
        if weight is not None:
            properties["Рабочий_вес_кг"] = {"number": weight}
        api_call(
            notion.pages.create,
            parent={"database_id": db_id},
            properties=properties,
        )
    print("✅")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 60)
    print("🏋️  NOTION WORKOUT TRACKER — РЕКОМПОЗИЦИЯ (12 недель × 4 дня)")
    print("=" * 60)
    print()

    token, parent_id = get_credentials()
    notion = Client(auth=token, notion_version=NOTION_VERSION)

    if not check_connection(notion):
        sys.exit(1)

    maybe_archive_old(notion, parent_id)

    print()
    confirm = input(
        "▶️  Сейчас будет создана новая система: 1 страница, 4 БД,\n"
        "    48 тренировок, 288 упражнений. Продолжить? (y/N): "
    ).strip().lower()
    if confirm != "y":
        print("🚫 Отменено.")
        sys.exit(0)

    try:
        main_page_id = create_main_page(notion, parent_id)
        workouts_db_id = create_workouts_db(token, main_page_id)
        exercises_db_id = create_exercises_db(token, main_page_id, workouts_db_id)
        body_db_id = create_body_progress_db(token, main_page_id)
        records_db_id = create_records_db(token, main_page_id)

        workout_pages = fill_workouts(notion, workouts_db_id)
        fill_exercises(notion, exercises_db_id, workout_pages)
        fill_body_progress(notion, body_db_id)
        fill_records(notion, records_db_id)

        url = page_url(main_page_id)
        print()
        print("=" * 60)
        print(f"✨ Готово! Открой: {url}")
        print("=" * 60)

    except APIResponseError as e:
        print(f"\n\n❌ Notion API: {e.status} — {e.body}")
        print("   Проверь:")
        print("   1. Токен корректен и интеграция активна")
        print("   2. Интеграция приглашена на parent-страницу (Share → Invite)")
        print("   3. Parent Page ID правильный")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Непредвиденная ошибка: {e}")
        raise


if __name__ == "__main__":
    main()
