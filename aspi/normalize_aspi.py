# -*- coding: utf-8 -*-
"""
Нормализация JSON расписания аспирантов (aspi/output):
- Замена сокращённых ФИО на полные (info/teacher_all.json)
- Дни недели: понедельник, вторник, среда, четверг, пятница, суббота
- Ключи как у бакалавров: day_of_week, pair_number, subject_name, audience, group_name, week_type, fio
- Из названия дисциплины извлекаются ЭОиДОТ, Ауд., Каб и т.д. в audience
"""
import json
import re
import sys
from pathlib import Path

if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Корень проекта (родитель папки aspi)
ASPI_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ASPI_DIR.parent
OUTPUT_DIR = ASPI_DIR / "output"

# Добавляем корень проекта в path для импорта process_timetable
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from process_timetable import load_teacher_names, normalize_short_fio
except ImportError:
    load_teacher_names = None
    normalize_short_fio = None

# Маппинг дней недели: любой вариант (ВТОРНИК, Вторник, вт) → понедельник, вторник, ...
DAY_NORMALIZE = {
    'понедельник': 'понедельник', 'пн': 'понедельник', '1': 'понедельник',
    'вторник': 'вторник', 'вт': 'вторник', '2': 'вторник',
    'среда': 'среда', 'ср': 'среда', '3': 'среда',
    'четверг': 'четверг', 'чт': 'четверг', '4': 'четверг',
    'пятница': 'пятница', 'пт': 'пятница', '5': 'пятница',
    'суббота': 'суббота', 'сб': 'суббота', '6': 'суббота',
    'воскресенье': 'воскресенье', 'вс': 'воскресенье', '7': 'воскресенье',
}


def normalize_day_of_week(day_raw: str) -> str:
    """Приводит день недели к виду: понедельник, вторник, среда, четверг, пятница, суббота."""
    if not day_raw or not isinstance(day_raw, str):
        return ''
    key = day_raw.strip().lower()
    if key in DAY_NORMALIZE:
        return DAY_NORMALIZE[key]
    # Проверяем начало строки (ВТОРНИК -> вторник)
    for canonical, result in DAY_NORMALIZE.items():
        if canonical != key and key.startswith(canonical):
            return result
    return day_raw.strip()


def extract_audience_from_discipline(text):
    """
    Извлекает из названия дисциплины маркеры аудитории: ЭОиДОТ, Ауд., Каб и т.д.
    Возвращает (очищенное название, строка audience через запятую).
    """
    if not text or not isinstance(text, str):
        return (text or '', '')
    text = text.strip()
    audiences = []

    # ЭОиДОТ (дистанционная) — убираем из названия, добавляем в audience
    if 'ЭОиДОТ' in text or 'эоидот' in text.lower():
        audiences.append('ЭОиДОТ')
        text = re.sub(r'\s*ЭОиДОТ\*?\s*', ' ', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*эоидот\*?\s*', ' ', text)

    # Паттерны: Ауд. 123, Ауд.123, ауд. 456, Каб. 789, Каб 789, каб. 101 — извлекаем в audience
    aud_pattern = re.compile(
        r'(?:ауд\.?|каб\.?)\s*([А-ЯЁа-яёA-Za-z0-9\-]*)',
        re.IGNORECASE
    )
    for m in aud_pattern.finditer(text):
        room = (m.group(1) or '').strip()
        label = 'Ауд.' if m.group(0).strip().lower().startswith('ауд') else 'Каб.'
        if room:
            audiences.append(f"{label} {room}".strip())
        else:
            audiences.append(label.strip())
    text = aud_pattern.sub(' ', text)

    # Убираем оставшиеся "Ауд.", "Каб." без номера
    text = re.sub(r'\s*ауд\.?\s*', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*каб\.?\s*', ' ', text, flags=re.IGNORECASE)

    # Нормализация названия: лишние пробелы
    text = re.sub(r'\s+', ' ', text).strip().strip(',')
    audience_str = ', '.join(audiences) if audiences else ''
    return (text, audience_str)


def normalize_record(rec: dict, teacher_mapping: dict) -> dict:
    """
    Одна запись из aspi JSON: ключи группа, научная_специальность, год_обучения,
    день_недели, пара, дисциплина, фио, предмет, неделя.
    Возвращает запись с ключами как у бакалавров + course, scientific_specialty.
    """
    day_raw = rec.get('день_недели') or ''
    para = rec.get('пара') or ''
    discipline_raw = (rec.get('дисциплина') or rec.get('предмет') or '').strip()
    short_fio = (rec.get('фио') or '').strip()
    group = (rec.get('группа') or '').strip()
    week_type = (rec.get('неделя') or 'обе недели').strip()

    day_of_week = normalize_day_of_week(day_raw)
    subject_name, audience = extract_audience_from_discipline(discipline_raw)

    # Номер пары: если "7" или "13:00" — оставляем как есть (число или строка)
    try:
        pair_number = int(para) if para and str(para).strip().isdigit() else para
    except (ValueError, TypeError):
        pair_number = para

    # Полное ФИО по справочнику; в одном поле может быть два ФИО (через /, ;, " и " или подряд: "Фамилия И.О. Фамилия И.О.")
    def one_fio_to_full(one):
        one = (one or '').strip()
        if not one:
            return one
        if teacher_mapping:
            norm = normalize_short_fio(one) if normalize_short_fio else one
            return teacher_mapping.get(norm) or teacher_mapping.get(one) or one
        return one

    # Разделители: / ; " и " или пробел перед следующим ФИО (Фамилия И.О. — паттерн: заглавная + строчные + пробел + И.О.)
    parts = re.split(
        r'\s*[/;]\s*|\s+и\s+|\s+(?=[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.[А-ЯЁ]?\.?)',
        short_fio
    )
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        full_fio = short_fio
    else:
        full_fio = ' | '.join(one_fio_to_full(p) for p in parts)

    out = {
        'day_of_week': day_of_week,
        'pair_number': pair_number,
        'subject_name': subject_name,
        'discipline_original': discipline_raw,  # оригинал для проверки
        'audience': audience,
        'group_name': group,
        'week_type': week_type,
        'fio': full_fio,
        'course': rec.get('год_обучения', ''),
        'scientific_specialty': rec.get('научная_специальность', ''),
    }
    return out


def load_teacher_mapping():
    """Загружает маппинг короткое ФИО → полное из info/teacher_all.json."""
    if load_teacher_names is None:
        return {}
    teacher_file = PROJECT_ROOT / 'info' / 'teacher_all.json'
    if not teacher_file.exists():
        return {}
    return load_teacher_names(str(teacher_file))


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    teacher_mapping = load_teacher_mapping()

    # Файлы по одному курсу/группе (не _all.json)
    json_files = [f for f in OUTPUT_DIR.glob("*.json") if f.name != "_all.json"]
    if not json_files:
        print("В папке aspi/output нет JSON-файлов (кроме _all.json). Сначала запустите парсер.")
        return

    all_normalized = {}
    for path in sorted(json_files):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                print(f"Пропуск {path.name}: ожидается список записей.")
                continue
            normalized = [normalize_record(rec, teacher_mapping) for rec in data]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(normalized, f, ensure_ascii=False, indent=2)
            name = path.stem
            all_normalized[name] = normalized
            print(f"Нормализован: {path.name} ({len(normalized)} записей)")
        except Exception as e:
            print(f"Ошибка при обработке {path}: {e}", file=sys.stderr)
            raise

    # Сводный _all.json
    summary_path = OUTPUT_DIR / "_all.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_normalized, f, ensure_ascii=False, indent=2)
    print(f"Сводный файл: {summary_path}")


if __name__ == "__main__":
    main()
