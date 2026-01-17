# Система парсинга расписаний СурГУ

Полная система для скачивания, парсинга и обработки расписаний с сайта СурГУ.

## Структура проекта

```
timetable/
├── schedules_pdf/          # Скачанные PDF файлы расписаний
├── schedules_json/         # Распарсенные JSON файлы
├── schedules_parsed/        # Обработанные данные (опционально)
├── abbreviations.json      # Словарь сокращений
├── download_schedules.py   # Скрипт скачивания расписаний
├── parse_timetable.py      # Парсер PDF в JSON
├── parse_all_schedules.py  # Массовый парсинг всех PDF
├── normalize_disciplines.py # Нормализация названий дисциплин
├── extract_abbreviations.py # Извлечение сокращений
└── validate_timetable.py   # Валидация данных
```

## Установка

```bash
pip install -r requirements.txt
```

Зависимости:
- `pdfplumber` - парсинг PDF
- `requests` - HTTP запросы
- `beautifulsoup4` - парсинг HTML
- `lxml` - парсер для BeautifulSoup

## Использование

### 1. Скачивание расписаний

```bash
python3 download_schedules.py
```

**Что делает:**
- Парсит страницу https://www.surgu.ru/ucheba/raspisanie/ochnaya-forma-obucheniya
- Находит все ссылки на PDF файлы
- Определяет институт/направление по тексту ссылки
- Скачивает файлы в `schedules_pdf/`
- Называет файлы: `{институт}_{название}.pdf`

**Примеры имен:**
- `medical_Лечебное_дело-13-01-26.pdf`
- `polytechnic_Информатика-26-12-25.pdf`
- `economics_Экономика-26-12-25.pdf`

### 2. Парсинг расписаний

#### Парсинг одного файла:
```bash
python3 parse_timetable.py schedules_pdf/medical_Лечебное_дело-13-01-26.pdf
```

#### Массовый парсинг всех PDF:
```bash
python3 parse_all_schedules.py
```

**Результат:** JSON файлы в `schedules_json/` с тем же именем, но расширением `.json`

### 3. Нормализация названий дисциплин

```bash
# Нормализует все JSON в schedules_json/
python3 normalize_disciplines.py

# Или конкретный файл
python3 normalize_disciplines.py schedules_json/medical_Лечебное_дело-13-01-26.json
```

**Результат:** Файлы `*_normalized.json` в той же папке

### 4. Извлечение сокращений

```bash
# Анализирует все JSON и находит новые сокращения
python3 extract_abbreviations.py schedules_json/*.json

# Или автоматически найдет все timetable*.json
python3 extract_abbreviations.py
```

**Результат:** Обновляет `abbreviations.json` с новыми сокращениями

### 5. Валидация данных

```bash
python3 validate_timetable.py
```

**Результат:** `validation_errors.json` с найденными ошибками

## Полный цикл работы

```bash
# 1. Скачать все расписания с сайта
python3 download_schedules.py

# 2. Распарсить все PDF в JSON
python3 parse_all_schedules.py

# 3. Извлечь новые сокращения
python3 extract_abbreviations.py schedules_json/*.json

# 4. Нормализовать названия дисциплин
python3 normalize_disciplines.py

# 5. Валидировать данные (если есть CSV для сравнения)
python3 validate_timetable.py
```

## Определение институтов

Скрипт автоматически определяет институт по ключевым словам:

| Ключевое слово | Код института |
|---------------|---------------|
| медицинск | medical |
| политехническ | polytechnic |
| экономик | economics |
| гуманитарн | humanities |
| государств | state_law |
| естественн | natural_sciences |
| средн | secondary_medical |

Если институт не определен, используется транслитерация названия.

## Формат JSON

Каждая запись в JSON содержит:

```json
{
  "discipline": "Анатомия человека (лек)",
  "group": "501-51",
  "day_of_week": "monday",
  "room": "А436",
  "period": 2,
  "institute": "медицинский",
  "specialty": "31.05.01 Лечебное дело",
  "course": "1",
  "even_week": true,
  "odd_week": false,
  "subgroup": null,
  "lesson_type": "lecture",
  "period_dates": "02.02.2026-06.06.2026"
}
```

## Примечания

- Скрипт скачивания делает задержку 0.5 сек между запросами
- Если файл уже существует, он будет пропущен (можно удалить для перескачивания)
- Все файлы сохраняются с UTF-8 кодировкой
- Имена файлов очищаются от недопустимых символов
- URL-encoded символы декодируются автоматически

## Устранение проблем

### Ошибка SSL при скачивании
Скрипт автоматически пробует без проверки SSL сертификата (небезопасно, но работает)

### Файлы не скачиваются
- Проверьте интернет-соединение
- Убедитесь, что сайт доступен
- Проверьте права доступа к папке `schedules_pdf/`

### Ошибки парсинга PDF
- Убедитесь, что PDF не поврежден
- Проверьте, что файл действительно является расписанием
- Некоторые PDF могут иметь нестандартную структуру

