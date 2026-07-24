# Ventoy ISO Updater v1.0.0

<img width="1175" height="758" alt="image" src="https://github.com/user-attachments/assets/abef847c-0237-4368-ad0f-9e5ec31cf8fc" />
<img width="1178" height="757" alt="image" src="https://github.com/user-attachments/assets/1a619866-57f6-48ac-9960-c4586043afb9" />



Профессиональное настольное приложение для автоматического обновления
ISO-образов на флешках Ventoy. **Подключаете источник — приложение само находит
последнюю версию, скачивает и записывает её на флешку.**

**Автор:** Rantol

[English below](#english)

---

## Русский

### Что нового в 1.0

- **Каталог дистрибутивов** — подключение в один клик: Ubuntu, Debian, Linux Mint,
  Fedora, Arch, Kali, openSUSE, Rocky, Pop!_OS. Не нужно вручную вписывать URL и regex.
- **Автоопределение последней версии** — под каждый дистрибутив свой надёжный
  способ (JSON API, `current`-каталог, индекс релизов), а не хрупкий парсинг ссылок.
- **Автопроверка** — по расписанию и при запуске; вкладка «Библиотека» показывает,
  что устарело. Обновление на флешку — только по вашему клику.
- **Проверка контрольной суммы (SHA-256)** там, где источник её предоставляет.
- **Новый интерфейс** — боковая навигация, карточки, статус-бейджи, тёмная/светлая тема.
- **Свои источники** — старый режим «URL + маска версии» сохранён как доп. вариант.

### Экраны

| Экран | Назначение |
|-------|-----------|
| **Библиотека** | Образы на флешке, их версии и статус (актуально / устарело / нет на флешке). Кнопка обновления. |
| **Источники** | Каталог дистрибутивов + подключённые источники. Кнопка «Подключить». |
| **Активность** | Журнал проверок, загрузок и записей. |
| **Настройки** | Кэш, тема, язык, метка Ventoy, интервал автопроверки. |

### Как это работает

```
Подключить источник  →  Проверить  →  (устарело?)  →  Скачать + проверить SHA  →  Записать на флешку
```

### Установка и запуск

```bash
pip install -r requirements.txt
python app.py
```

### Проверка источников (без GUI)

```bash
python -m updater --selftest          # проверить все источники в каталоге
python -m updater --selftest debian   # проверить один источник
```

### Горячие клавиши

| Клавиши | Действие |
|---------|----------|
| `Ctrl+R` | Пересканировать флешку |
| `Ctrl+Q` | Выход |

### Структура проекта

```
VentoyISOupdater/
├── app.py   # Главное окно и контроллер
├── views.py         # Экраны: Библиотека, Источники, Активность, Настройки
├── widgets.py       # Переиспользуемые виджеты (сайдбар, бейджи, карточки)
├── theme.py         # Дизайн-система: цвета и QSS (тёмная/светлая)
├── i18n.py          # Локализация RU/EN
├── catalog.py       # Каталог дистрибутивов + описания резолверов
├── updater.py       # Резолверы версий, воркеры загрузки/копирования, SHA-256
├── drive.py         # Поиск и сканирование флешки Ventoy (Windows)
├── config.py        # Настройки: загрузка/сохранение/миграция
├── iso_parser.py    # Разбор имён ISO-файлов
├── requirements.txt
└── settings.json    # Создаётся автоматически
```

### Как добавить свой дистрибутив в каталог

Каталог — это данные, а не код. Добавьте словарь в `CATALOG` (`catalog.py`),
указав `resolver` (`json_api` / `current_dir` / `release_index` / `arch_json` /
`popos_api`), `resolver_cfg` и список `editions`. Проверьте: `python -m updater --selftest <id>`.

---

## English

### What's new in 1.0

- **Distribution catalog** — one-click connect for Ubuntu, Debian, Linux Mint,
  Fedora, Arch, Kali, openSUSE, Rocky, Pop!_OS. No manual URL/regex.
- **Reliable latest-version detection** — a dedicated method per distro
  (JSON API, `current` directory, release index) instead of fragile link scraping.
- **Auto-check** on a schedule and at startup; the Library flags what's outdated.
  Writing to the USB always needs your click.
- **SHA-256 verification** when the source provides a checksum.
- **Redesigned UI** — sidebar navigation, cards, status badges, dark/light theme.
- **Custom sources** — the old "URL + version mask" mode is kept as an option.

### Install & run

```bash
pip install -r requirements.txt
python app.py
```

### Verify sources without the GUI

```bash
python -m updater --selftest          # check every catalog source
python -m updater --selftest debian   # check one source
```

### Notes

- Drive detection is Windows-first (volume label, default `Ventoy`). On other
  platforms the app still runs; drive functions return empty results.
- Windows ISOs have no stable public direct URL and are not in the catalog —
  add them via a custom source if you host your own mirror.
