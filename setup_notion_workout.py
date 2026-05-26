#!/usr/bin/env python3
"""
Создаёт полную систему трекинга силовых тренировок на 12 недель в Notion.
"""

import os
import sys
import time
import json
import getpass
import httpx
from datetime import datetime, timedelta
from notion_client import Client, APIResponseError

# ─────────────────────────────────────────────
# КОНФИГУРАЦИЯ
# ─────────────────────────────────────────────

MAIN_PAGE_TITLE = "🏋️ Программа тренировок — 12 недель"
RATE_LIMIT_DELAY = 0.35
MAX_RETRIES = 5
BASE_RETRY_DELAY = 1


# ─────────────────────────────────────────────
# ДАННЫЕ ПРОГРАММЫ
# ─────────────────────────────────────────────

MESOCYCLES = {
    1: "МЦ-1 Накопление 🟢",
    2: "МЦ-1 Накопление 🟢",
    3: "МЦ-1 Накопление 🟢",
    4: "МЦ-1 Накопление 🟢",
    5: "МЦ-2 Интенсификация 🟡",
    6: "МЦ-2 Интенсификация 🟡",
    7: "МЦ-2 Интенсификация 🟡",
    8: "МЦ-2 Интенсификация 🟡",
    9: "МЦ-3 Реализация 🔴",
    10: "МЦ-3 Реализация 🔴",
    11: "МЦ-3 Реализация 🔴",
    12: "Разгрузка 🔵",
}

WORKOUT_TYPES = {
    0: "A — Ноги+Жим",       # Понедельник
    2: "B — Спина+Плечи",    # Среда
    4: "C — Жим+Ноги тяжёлые",  # Пятница
}

# Прогрессия основных движений: (подходы, повторы, вес, rir)
BENCH_A = {
    1: (4, "8", 65, 3), 2: (4, "8", 67.5, 3), 3: (4, "8", 70, 2), 4: (4, "8", 72.5, 2),
    5: (5, "5", 75, 2), 6: (5, "5", 77.5, 2), 7: (5, "5", 80, 2), 8: (5, "5", 82.5, 1),
    9: (5, "3", 87.5, 1), 10: (5, "3", 90, 1), 11: (5, "3", 95, 0), 12: (2, "5", 45, 4),
}

SQUAT_A = {
    1: (4, "8", 50, 3), 2: (4, "8", 55, 3), 3: (4, "8", 60, 2), 4: (4, "8", 65, 2),
    5: (5, "5", 70, 2), 6: (5, "5", 75, 2), 7: (5, "5", 80, 2), 8: (5, "5", 85, 1),
    9: (5, "3", 92.5, 1), 10: (5, "3", 97.5, 1), 11: (5, "3", 105, 0), 12: (2, "5", 45, 4),
}

BENCH_C = {
    1: (4, "6", 70, 2), 2: (4, "6", 72.5, 2), 3: (4, "6", 75, 2), 4: (4, "6", 77.5, 2),
    5: (4, "4", 82.5, 1), 6: (4, "4", 85, 1), 7: (4, "4", 87.5, 1), 8: (4, "4", 90, 1),
    9: (4, "2-3", 92.5, 1), 10: (4, "2-3", 95, 0), 11: (4, "2-3", 97.5, 0), 12: (2, "5", 50, 4),
}

SQUAT_C = {
    1: (4, "10", 45, 3), 2: (4, "10", 47.5, 3), 3: (4, "10", 50, 3), 4: (4, "10", 52.5, 3),
    5: (4, "8", 60, 2), 6: (4, "8", 65, 2), 7: (4, "8", 70, 2), 8: (4, "8", 72.5, 2),
    9: (4, "5", 80, 1), 10: (4, "5", 82.5, 1), 11: (4, "5", 85, 1), 12: (2, "5", 25, 4),
}


def get_accessory_progression(week, base_sets, base_reps, base_rir, start_weight, weight_step):
    """Рассчитывает параметры подсобных упражнений с учётом мезоцикла."""
    w = start_weight + weight_step * (week - 1)
    if week == 12:
        return (2, "8", round(start_weight * 0.5, 1), 4)
    if week <= 4:
        return (base_sets, base_reps, round(w, 1), base_rir)
    if week <= 8:
        return (4, "6-8" if isinstance(base_reps, str) and int(base_reps.split("-")[0]) > 6 else "6-8", round(w, 1), 2)
    # 9-11
    return (3, "6-8", round(w, 1), 1)


def get_accessory_no_weight_progression(week, base_sets, base_reps, base_rir):
    """Для упражнений без жёсткой прогрессии веса."""
    if week == 12:
        return (2, "8", None, 4)
    if week <= 4:
        return (base_sets, base_reps, None, base_rir)
    if week <= 8:
        return (4, "6-8", None, 2)
    return (3, "6-8", None, 1)


def build_workout_a(week):
    """Строит список упражнений для тренировки A."""
    sq = SQUAT_A[week]
    bn = BENCH_A[week]
    rdl = get_accessory_progression(week, 3, "10", 3, 60, 2.5)
    row_db = get_accessory_no_weight_progression(week, 3, "10", 2)
    press_db = get_accessory_no_weight_progression(week, 3, "12", 2)
    curl = get_accessory_progression(week, 3, "12", 2, 25, 0)
    if week == 12:
        plank = (2, "30 сек", None, 4)
    else:
        plank = (3, "45 сек", None, None)

    return [
        ("Присед со штангой", *sq),
        ("Жим лёжа", *bn),
        ("Румынская тяга", *rdl),
        ("Тяга гантели в наклоне", *row_db),
        ("Жим гантелей сидя", *press_db),
        ("Подъём на бицепс штанга", *curl),
        ("Планка", *plank),
    ]


def build_workout_b(week):
    """Строит список упражнений для тренировки B."""
    ohp = get_accessory_progression(week, 4, "8", 3, 30, 1.25)
    pullup = get_accessory_progression(week, 4, "6-8", 3, 5, 1.25)
    leg_press = get_accessory_no_weight_progression(week, 3, "12", 2)
    lat_pull = get_accessory_no_weight_progression(week, 3, "10", 2)
    french = get_accessory_no_weight_progression(week, 3, "12", 2)
    lateral = get_accessory_no_weight_progression(week, 3, "15", 1)
    calf = get_accessory_no_weight_progression(week, 4, "15", 2)

    return [
        ("Жим стоя со штангой", *ohp),
        ("Подтягивания с весом", *pullup),
        ("Жим ногами", *leg_press),
        ("Тяга верхнего блока узким хватом", *lat_pull),
        ("Французский жим лёжа", *french),
        ("Махи гантелей в стороны", *lateral),
        ("Подъём на носки стоя", *calf),
    ]


def build_workout_c(week):
    """Строит список упражнений для тренировки C."""
    bn = BENCH_C[week]
    sq = SQUAT_C[week]
    row = get_accessory_progression(week, 4, "8", 3, 60, 2.5)
    bulgarian = get_accessory_no_weight_progression(week, 3, "10 на ногу", 3)
    incline_db = get_accessory_no_weight_progression(week, 3, "10", 2)
    hammer = get_accessory_no_weight_progression(week, 3, "12", 2)
    crunch = get_accessory_no_weight_progression(week, 3, "15", 2)

    return [
        ("Жим лёжа", *bn),
        ("Присед", *sq),
        ("Тяга штанги в наклоне", *row),
        ("Болгарские выпады с гантелями", *bulgarian),
        ("Жим гантелей на наклонной", *incline_db),
        ("Молотки на бицепс", *hammer),
        ("Скручивания на пресс", *crunch),
    ]


PERSONAL_RECORDS = [
    ("Жим лёжа", 92, 100),
    ("Присед", 67, 105),
    ("Подтягивания с весом ×5", 22, 30),
    ("Подъём на бицепс ×8", 20, 25),
]


# ─────────────────────────────────────────────
# УТИЛИТЫ
# ─────────────────────────────────────────────

NOTION_BASE_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def api_call(fn, *args, **kwargs):
    """Обёртка для вызовов Notion API с retry и rate limiting."""
    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(RATE_LIMIT_DELAY)
            return fn(*args, **kwargs)
        except APIResponseError as e:
            if e.status in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                delay = BASE_RETRY_DELAY * (2 ** attempt)
                print(f"\n⏳ Ошибка {e.status}, повтор через {delay}с (попытка {attempt + 2}/{MAX_RETRIES})...")
                time.sleep(delay)
            else:
                raise
    raise RuntimeError("Не удалось выполнить запрос после всех попыток")


def raw_create_database(token, body):
    """Создаёт БД через прямой HTTP-вызов (обход бага SDK v2.7 с properties)."""
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
            print(f"\n⏳ Ошибка {resp.status_code}, повтор через {delay}с...")
            time.sleep(delay)
            continue
        if resp.status_code != 200:
            raise RuntimeError(f"Notion API error {resp.status_code}: {resp.text}")
        return resp.json()
    raise RuntimeError("Не удалось создать БД после всех попыток")


def get_next_monday():
    """Возвращает дату ближайшего понедельника (включая сегодня, если сегодня Пн)."""
    today = datetime.now().date()
    days_ahead = (7 - today.weekday()) % 7
    if days_ahead == 0 and today.weekday() == 0:
        return today
    if today.weekday() == 0:
        return today
    return today + timedelta(days=(7 - today.weekday()) % 7)


def page_url(page_id):
    """Формирует URL страницы Notion."""
    return f"https://notion.so/{page_id.replace('-', '')}"


# ─────────────────────────────────────────────
# ОСНОВНАЯ ЛОГИКА
# ─────────────────────────────────────────────

def get_credentials():
    """Получает токен и parent page ID."""
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        token = getpass.getpass("🔑 Введи Notion Integration Token: ")
    parent_id = os.environ.get("NOTION_PARENT_PAGE_ID")
    if not parent_id:
        parent_id = input("📄 Введи Parent Page ID: ").strip()
    # Очистка ID от дефисов и URL
    parent_id = parent_id.replace("-", "")
    if "notion.so" in parent_id or "notion.site" in parent_id:
        parent_id = parent_id.split("/")[-1].split("?")[0].split("#")[0]
        # Убираем название страницы (всё до последнего блока из 32 символов)
        if len(parent_id) > 32:
            parent_id = parent_id[-32:]
    return token, parent_id


def check_connection(notion):
    """Проверяет подключение к Notion."""
    print("🔍 Проверка подключения к Notion...", end=" ", flush=True)
    try:
        api_call(notion.users.me)
        print("✅")
        return True
    except Exception as e:
        print(f"❌\n   Ошибка: {e}")
        return False


def check_existing(notion, parent_id):
    """Проверяет, существует ли уже система."""
    try:
        children = api_call(notion.blocks.children.list, block_id=parent_id)
        for block in children.get("results", []):
            if block.get("type") == "child_page":
                title = block.get("child_page", {}).get("title", "")
                if "Программа тренировок" in title:
                    answer = input(
                        f"\n⚠️  Найдена существующая страница: «{title}»\n"
                        "   Создать новую рядом? (y/n): "
                    ).strip().lower()
                    if answer != "y":
                        print("🚫 Отменено.")
                        sys.exit(0)
                    return
    except Exception:
        pass


def create_main_page(notion, parent_id):
    """Создаёт главную страницу с описанием."""
    print("📁 Создание главной страницы...", end=" ", flush=True)
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
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": (
                                    "Цели программы:\n"
                                    "• Набор мышечной массы\n"
                                    "• Жим лёжа: 95–100 кг\n"
                                    "• Присед: 100–110 кг\n\n"
                                    "Структура: 3 мезоцикла + разгрузка\n"
                                    "МЦ-1 (нед 1-4): Накопление — 4×8, RIR 3→2\n"
                                    "МЦ-2 (нед 5-8): Интенсификация — 5×5, RIR 2→1\n"
                                    "МЦ-3 (нед 9-11): Реализация — 5×3, RIR 1→0\n"
                                    "Нед 12: Разгрузка — 2×5 @ 50%"
                                ),
                            },
                        }
                    ],
                    "color": "blue_background",
                },
            },
            {
                "object": "block",
                "type": "divider",
                "divider": {},
            },
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
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": "Все базы данных созданы ниже на этой странице. Используй фильтры и сортировку для навигации."},
                        }
                    ],
                },
            },
        ],
    )
    url = page_url(page["id"])
    print(f"✅ (URL: {url})")
    return page["id"]


def create_workouts_db(token, page_id):
    """Создаёт БД «Тренировки»."""
    print("🗄️  Создание БД «Тренировки»...", end=" ", flush=True)
    db = raw_create_database(token, {
        "parent": {"type": "page_id", "page_id": page_id},
        "title": [{"type": "text", "text": {"content": "Тренировки"}}],
        "icon": {"type": "emoji", "emoji": "📅"},
        "properties": {
            "Название": {"title": {}},
            "Дата": {"date": {}},
            "Неделя": {"number": {"format": "number"}},
            "Мезоцикл": {
                "select": {
                    "options": [
                        {"name": "МЦ-1 Накопление 🟢", "color": "green"},
                        {"name": "МЦ-2 Интенсификация 🟡", "color": "yellow"},
                        {"name": "МЦ-3 Реализация 🔴", "color": "red"},
                        {"name": "Разгрузка 🔵", "color": "blue"},
                    ]
                }
            },
            "Тип": {
                "select": {
                    "options": [
                        {"name": "A — Ноги+Жим", "color": "purple"},
                        {"name": "B — Спина+Плечи", "color": "orange"},
                        {"name": "C — Жим+Ноги тяжёлые", "color": "pink"},
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
            "Заметки": {"rich_text": {}},
        },
    })
    print("✅")
    return db["id"]


def create_exercises_db(token, page_id, workouts_db_id):
    """Создаёт БД «Упражнения» с relation к Тренировкам."""
    print("🗄️  Создание БД «Упражнения»...", end=" ", flush=True)
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
            "Подходы_план": {"number": {"format": "number"}},
            "Повторы_план": {"rich_text": {}},
            "Вес_план": {"number": {"format": "number"}},
            "RIR_план": {"number": {"format": "number"}},
            "Подходы_факт": {"number": {"format": "number"}},
            "Повторы_факт": {"rich_text": {}},
            "Вес_факт": {"number": {"format": "number"}},
            "RIR_факт": {"number": {"format": "number"}},
            "Выполнено": {"checkbox": {}},
        },
    })
    print("✅")
    return db["id"]


def create_body_progress_db(token, page_id):
    """Создаёт БД «Прогресс тела»."""
    print("🗄️  Создание БД «Прогресс тела»...", end=" ", flush=True)
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
    """Создаёт БД «Личные рекорды»."""
    print("🗄️  Создание БД «Личные рекорды»...", end=" ", flush=True)
    db = raw_create_database(token, {
        "parent": {"type": "page_id", "page_id": page_id},
        "title": [{"type": "text", "text": {"content": "Личные рекорды"}}],
        "icon": {"type": "emoji", "emoji": "🏆"},
        "properties": {
            "Упражнение": {"title": {}},
            "1ПМ_текущий_кг": {"number": {"format": "number"}},
            "1ПМ_цель_кг": {"number": {"format": "number"}},
            "Прирост_%": {
                "formula": {
                    "expression": "round(prop(\"1ПМ_цель_кг\") / prop(\"1ПМ_текущий_кг\") * 100 - 100)",
                }
            },
            "Дата_обновления": {"date": {}},
        },
    })
    print("✅")
    return db["id"]


def fill_workouts(notion, db_id):
    """Создаёт 36 записей тренировок."""
    start_monday = get_next_monday()
    total = 36
    print(f"📝 Заполнение тренировок: 0/{total}", end="", flush=True)

    workout_pages = {}  # (week, day_offset) -> page_id
    count = 0

    for week in range(1, 13):
        week_start = start_monday + timedelta(weeks=week - 1)
        for day_offset, workout_type in WORKOUT_TYPES.items():
            date = week_start + timedelta(days=day_offset)
            day_letter = workout_type[0]  # A, B, or C
            title = f"Нед {week} — Тренировка {day_letter}"

            page = api_call(
                notion.pages.create,
                parent={"database_id": db_id},
                properties={
                    "Название": {"title": [{"text": {"content": title}}]},
                    "Дата": {"date": {"start": date.isoformat()}},
                    "Неделя": {"number": week},
                    "Мезоцикл": {"select": {"name": MESOCYCLES[week]}},
                    "Тип": {"select": {"name": workout_type}},
                },
            )
            workout_pages[(week, day_offset)] = page["id"]
            count += 1
            print(f"\r📝 Заполнение тренировок: {count}/{total}", end="", flush=True)

    print(" ✅")
    return workout_pages


def fill_exercises(notion, db_id, workout_pages):
    """Создаёт записи упражнений для каждой тренировки."""
    # Собираем все упражнения
    all_exercises = []
    start_monday = get_next_monday()

    for week in range(1, 13):
        week_start = start_monday + timedelta(weeks=week - 1)

        # Тренировка A — Понедельник
        date_a = week_start
        workout_id_a = workout_pages[(week, 0)]
        for ex in build_workout_a(week):
            all_exercises.append((ex, workout_id_a, date_a))

        # Тренировка B — Среда
        date_b = week_start + timedelta(days=2)
        workout_id_b = workout_pages[(week, 2)]
        for ex in build_workout_b(week):
            all_exercises.append((ex, workout_id_b, date_b))

        # Тренировка C — Пятница
        date_c = week_start + timedelta(days=4)
        workout_id_c = workout_pages[(week, 4)]
        for ex in build_workout_c(week):
            all_exercises.append((ex, workout_id_c, date_c))

    total = len(all_exercises)
    print(f"💪 Заполнение упражнений: 0/{total}", end="", flush=True)

    for i, (ex, workout_id, date) in enumerate(all_exercises):
        name, sets, reps, weight, rir = ex

        properties = {
            "Упражнение": {"title": [{"text": {"content": name}}]},
            "Тренировка": {"relation": [{"id": workout_id}]},
            "Дата": {"date": {"start": date.isoformat()}},
            "Подходы_план": {"number": sets},
            "Повторы_план": {"rich_text": [{"text": {"content": str(reps)}}]},
        }
        if weight is not None:
            properties["Вес_план"] = {"number": weight}
        if rir is not None:
            properties["RIR_план"] = {"number": rir}

        api_call(
            notion.pages.create,
            parent={"database_id": db_id},
            properties=properties,
        )
        print(f"\r💪 Заполнение упражнений: {i + 1}/{total}", end="", flush=True)

    print(" ✅")


def fill_body_progress(notion, db_id):
    """Создаёт стартовую запись прогресса тела."""
    print("📊 Создание стартовой записи прогресса...", end=" ", flush=True)
    today = datetime.now().date().isoformat()
    api_call(
        notion.pages.create,
        parent={"database_id": db_id},
        properties={
            "Дата": {"title": [{"text": {"content": today}}]},
            "Вес_кг": {"number": 80},
            "Заметки": {"rich_text": [{"text": {"content": "Старт программы"}}]},
        },
    )
    print("✅")


def fill_records(notion, db_id):
    """Создаёт записи личных рекордов."""
    print("🏆 Создание личных рекордов...", end=" ", flush=True)
    today = datetime.now().date().isoformat()
    for name, current, goal in PERSONAL_RECORDS:
        api_call(
            notion.pages.create,
            parent={"database_id": db_id},
            properties={
                "Упражнение": {"title": [{"text": {"content": name}}]},
                "1ПМ_текущий_кг": {"number": current},
                "1ПМ_цель_кг": {"number": goal},
                "Дата_обновления": {"date": {"start": today}},
            },
        )
    print("✅")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 50)
    print("🏋️  SETUP NOTION WORKOUT TRACKER")
    print("=" * 50)
    print()

    # Получение учётных данных
    token, parent_id = get_credentials()
    notion = Client(auth=token, notion_version="2022-06-28")

    # Шаг 1: Проверка подключения
    if not check_connection(notion):
        sys.exit(1)

    # Шаг 2: Проверка существующей системы
    check_existing(notion, parent_id)

    try:
        # Шаг 3: Главная страница
        main_page_id = create_main_page(notion, parent_id)

        # Шаг 4: Базы данных
        workouts_db_id = create_workouts_db(token, main_page_id)
        exercises_db_id = create_exercises_db(token, main_page_id, workouts_db_id)
        body_db_id = create_body_progress_db(token, main_page_id)
        records_db_id = create_records_db(token, main_page_id)

        # Шаг 5: Заполнение данных
        workout_pages = fill_workouts(notion, workouts_db_id)
        fill_exercises(notion, exercises_db_id, workout_pages)
        fill_body_progress(notion, body_db_id)
        fill_records(notion, records_db_id)

        # Готово!
        url = page_url(main_page_id)
        print()
        print("=" * 50)
        print(f"✨ Готово! Открой: {url}")
        print("=" * 50)

    except APIResponseError as e:
        print(f"\n\n❌ Ошибка Notion API: {e.status} — {e.body}")
        print("   Проверь:")
        print("   1. Токен интеграции корректен")
        print("   2. Интеграция добавлена на родительскую страницу (Share → Invite)")
        print("   3. Parent Page ID корректен")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Непредвиденная ошибка: {e}")
        raise


if __name__ == "__main__":
    main()
