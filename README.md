# Notion Workout Tracker — 12 недель

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?style=flat-square&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Notion_API-v2-black?style=flat-square&logo=notion" />
  <img src="https://img.shields.io/badge/Built_with-Claude_Code-blueviolet?style=flat-square&logo=anthropic" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" />
</p>

<p align="center">
  Python-скрипт, который за минуту разворачивает полную систему трекинга силовых тренировок в Notion.<br/>
  <b>Весь код написан с помощью Claude Code (AI) — от идеи до готового продукта за один диалог.</b>
</p>

---

## Что создаётся

Скрипт автоматически генерирует в Notion:

- **Главная страница** — описание программы, целей и мезоциклов
- **БД «Тренировки»** (36 записей) — расписание на 12 недель, 3 тренировки/неделю
- **БД «Упражнения»** (252 записи) — план подходов, повторов, весов и RIR с прогрессией
- **БД «Прогресс тела»** — трекинг веса, замеров, % жира
- **БД «Личные рекорды»** — текущие и целевые 1ПМ с расчётом прироста

> Все базы данных связаны через relations — упражнения привязаны к тренировкам, прогрессия рассчитана автоматически.

## Быстрый старт

```bash
git clone https://github.com/EmilAxme/workout-notion.git
cd workout-notion
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python setup_notion_workout.py
```

Скрипт запросит:
1. **Notion Integration Token** — создай на [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. **Parent Page ID** — ID страницы, где будет создана система

> Не забудь подключить интеграцию к странице: **Share → Invite → выбери интеграцию**

Или задай через переменные окружения:
```bash
cp .env.example .env
# заполни .env своими ключами
python setup_notion_workout.py
```

## Программа тренировок

| Недели | Мезоцикл | Схема | RIR |
|--------|----------|-------|-----|
| 1–4 | Накопление | 4×8 | 3→2 |
| 5–8 | Интенсификация | 5×5 | 2→1 |
| 9–11 | Реализация | 5×3 | 1→0 |
| 12 | Разгрузка | 2×5 @ 50% | 4 |

**3 тренировки в неделю:**
- A — Ноги + Жим
- B — Спина + Плечи
- C — Жим + Ноги тяжёлые

## Как пользоваться

### После тренировки
1. Открой БД «Тренировки», найди сегодняшнюю
2. Поставь **Статус → Выполнено**, отметь самочувствие и сон
3. В связанных упражнениях заполни: `Подходы_факт`, `Повторы_факт`, `Вес_факт`, `RIR_факт`

### Прогрессия
- БД «Упражнения» → Фильтр по упражнению → Сортировка по дате
- Рост весов виден неделя за неделей

### Еженедельно
- Добавь запись в БД «Прогресс тела»

## AI-автоматизация

Этот проект — пример того, как с помощью AI-ассистента (Claude Code) можно:

- Спроектировать структуру данных и прогрессию тренировок
- Сгенерировать 250+ записей с корректными связями между БД
- Написать production-ready скрипт с обработкой rate-limits и retry-логикой
- Подготовить документацию и публичный репозиторий

**Всё — от идеи до деплоя — за один диалог с AI.**

## Структура проекта

```
workout-notion/
├── setup_notion_workout.py   # Основной скрипт
├── requirements.txt          # Зависимости
├── .env.example              # Шаблон переменных окружения
├── .gitignore                # Исключения (.env, venv/)
└── README.md
```

## Автор

**Emil** — [@EmilAxme](https://github.com/EmilAxme)

---

<p align="center">
  <i>Built with Claude Code — AI-powered development</i>
</p>
