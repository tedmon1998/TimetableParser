import csv
import json
import re
import os
import glob
from collections import defaultdict

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None

# Маппинг дней недели
DAYS_MAPPING = {
    3: 'понедельник',
    5: 'вторник',
    7: 'среда',
    9: 'четверг',
    11: 'пятница',
    13: 'суббота'
}

# Маппинг столбцов аудиторий
AUDIENCE_COLUMNS = {
    3: 4,   # понедельник -> аудитория
    5: 6,   # вторник -> аудитория.
    7: 8,   # среда -> аудитория..
    9: 10,  # четверг -> аудитория_
    11: 12, # пятница -> аудитория_
    13: 14  # суббота -> аудитория…
}

# Маппинг недель на русский
WEEK_MAPPING = {
    'both': 'обе недели',
    'numerator': 'числитель',
    'denominator': 'знаменатель'
}


def _normalize_list_delimiter(s):
    """Нормализует разделители списка: точка, точка с запятой, Unicode-запятые → обычная запятая.
    "502-21.502-22" или "403-41.407-41" → разбиваются как разные записи."""
    if not s:
        return s
    s = str(s)
    for char in ('.', ';', '\uFF0C', '\u201A', '，', '\u060C', '\u3001', '\uFE50', '\uFE51'):
        s = s.replace(char, ',')
    return s


def parse_week_split_string(s):
    """
    Парсит строку с числителем/знаменателем/обе недели. Подходит и для групп, и для аудиторий.
    Возвращает список кортежей (значение, week_type), где week_type: 'numerator'|'denominator'|'both'.
    Запятая или точка с запятой без слэша даёт несколько записей: "501-33,501-34,501-35" → три записи.

    Примеры:
    - "А515/А436" -> [('А515', 'numerator'), ('А436', 'denominator')]
    - "605-41/" -> [('605-41', 'numerator')]  только числитель
    - "601-31" -> [('601-31', 'both')]  одна запись, обе недели
    - "501-33,501-34,501-35" -> [('501-33', 'both'), ('501-34', 'both'), ('501-35', 'both')]  три записи
    - "301-51/607-51,607-52" -> [('301-51', 'numerator'), ('607-51', 'denominator'), ('607-52', 'both')]
    - "501-51б/501-54б" -> [('501-51б', 'numerator'), ('501-54б', 'denominator')]
    - "/601-51м" -> [('601-51м', 'denominator')]
    """
    if not s or not s.strip():
        return []
    s = _normalize_list_delimiter(s.strip())
    # Только слэш в конце: "X/" → числитель
    if s.endswith('/'):
        val = s[:-1].strip()
        return [(val, 'numerator')] if val else []
    # Только слэш в начале: "/X" → знаменатель
    if s.startswith('/'):
        val = s[1:].strip()
        return [(val, 'denominator')] if val else []
    # Слэш в середине: "A/B", "A,B/C,D", "A,B/C,D,E" и т.д.
    if '/' in s:
        left, right = s.split('/', 1)
        left = left.strip()
        right = right.strip()
        if not left:
            # "/B,C,D" → первый знаменатель, остальные обе недели
            right_parts = [p.strip() for p in right.split(',') if p.strip()]
            if not right_parts:
                return []
            result = [(right_parts[0], 'denominator')]
            for p in right_parts[1:]:
                result.append((p, 'both'))
            return result
        if not right:
            # "A,B/" или "A,B" без правой части — все слева числитель
            left_parts = [p.strip() for p in left.split(',') if p.strip()]
            return [(p, 'numerator') for p in left_parts]
        left_parts = [p.strip() for p in left.split(',') if p.strip()]
        right_parts = [p.strip() for p in right.split(',') if p.strip()]
        if not right_parts:
            return [(p, 'numerator') for p in left_parts]
        if len(right_parts) == 1:
            # "A/B" или "A,B/C" → слева числитель(и), справа знаменатель
            result = [(p, 'numerator') for p in left_parts]
            result.append((right_parts[0], 'denominator'))
            return result
        # "A,B/C,D,E" → A,B=числитель, C=знаменатель, D,E=обе недели
        result = [(p, 'numerator') for p in left_parts]
        result.append((right_parts[0], 'denominator'))
        for p in right_parts[1:]:
            result.append((p, 'both'))
        return result
    # Без слэша: "X" или "X,Y,Z" → все обе недели
    parts = [p.strip() for p in s.split(',') if p.strip()]
    return [(p, 'both') for p in parts]


def parse_group_string(group_str):
    """
    Парсит строку с группами и возвращает список словарей {group, week, subgroup}.
    Использует parse_week_split_string для числитель/знаменатель/обе недели, затем
    раскрывает подгруппы (а, б, в...) в конце номера группы.

    Примеры:
    - "601-31" -> [{group: "601-31", week: "both", subgroup: None}]
    - "501-53,501-54" -> две записи: 501-53 в обе недели, 501-54 в обе недели
    - "605-41/" -> [{group: "605-41", week: "numerator", subgroup: None}]
    - "/601-51м" -> [{group: "601-51м", week: "denominator", subgroup: None}]
    - "301-51/607-51,607-52" -> числитель 301-51, знаменатель 607-51, обе 607-52 (три строки)
    - "501-51б/501-54б" -> числитель 501-51б, знаменатель 501-54б
    """
    if not group_str or group_str.strip() == '':
        return []
    parsed = parse_week_split_string(group_str)
    if not parsed:
        return []
    subgroup_letters = set('абвгдежзиклнопрстуфхцчшщэюя')
    groups = []
    for group_value, week_type in parsed:
        if not group_value:
            continue
        # Если внутри значения осталась запятая или точка (502-21.502-22, Unicode и т.п.) — разбиваем вручную
        if ',' in group_value or '.' in group_value or '\uFF0C' in group_value or '，' in group_value:
            group_value = _normalize_list_delimiter(group_value)
            parts = [p.strip() for p in group_value.split(',') if p.strip()]
        else:
            parts = [group_value]
        for part in parts:
            if not part:
                continue
            base_group = part
            subgroups = []
            match = re.search(r'^(.+?)([абвгдежзиклнопрстуфхцчшщэюя]+)$', part, re.IGNORECASE)
            if match:
                potential_base = match.group(1)
                potential_subgroups = match.group(2).lower()
                valid_subgroups = [c for c in potential_subgroups if c in subgroup_letters]
                if valid_subgroups and len(valid_subgroups) == len(potential_subgroups):
                    base_group = potential_base
                    subgroups = valid_subgroups
            if subgroups:
                for subgroup in subgroups:
                    groups.append({'group': base_group, 'week': week_type, 'subgroup': subgroup})
            else:
                groups.append({'group': base_group, 'week': week_type, 'subgroup': None})
    return groups

def count_subgroups(groups_list):
    """Подсчитывает количество уникальных подгрупп"""
    subgroups = set()
    for group_info in groups_list:
        if group_info['subgroup']:
            subgroups.add(group_info['subgroup'])
    return len(subgroups) if subgroups else 0

def normalize_short_fio(short_fio):
    """Нормализует короткое ФИО для сопоставления"""
    if not short_fio:
        return short_fio
    
    # Убираем лишние пробелы
    short_fio = ' '.join(short_fio.split())
    # Запятую в инициалах — на точку; несколько точек подряд — в одну
    short_fio = short_fio.replace(',', '.')
    short_fio = re.sub(r'\.+', '.', short_fio)
    # Склеенные "ФамилияИ.О." → "Фамилия И.О." (пробел перед инициалом)
    short_fio = re.sub(r'([а-яё])([А-ЯЁ]\.)', r'\1 \2', short_fio)
    
    # Приводим к стандартному формату: "Фамилия И.О."
    # Убираем пробелы между инициалами и точками
    short_fio = re.sub(r'([А-ЯЁ])\.\s*([А-ЯЁ])\.', r'\1.\2.', short_fio)
    short_fio = re.sub(r'([А-ЯЁ])\s+([А-ЯЁ])\.', r'\1.\2.', short_fio)
    
    return short_fio

def load_teacher_names(teacher_file='info/teacher_all.json'):
    """Загружает полные ФИО преподавателей из JSON файла и создает маппинг"""
    if not os.path.exists(teacher_file):
        print(f"Файл {teacher_file} не найден. Будет использоваться короткое ФИО.")
        return {}
    
    try:
        with open(teacher_file, 'r', encoding='utf-8') as f:
            teachers = json.load(f)
    except Exception as e:
        print(f"Ошибка при загрузке {teacher_file}: {e}. Будет использоваться короткое ФИО.")
        return {}
    
    # Создаем маппинг короткого ФИО на полное
    name_mapping = {}
    
    for teacher in teachers:
        full_fio = teacher.get('fio', '').strip()
        if not full_fio:
            continue
        
        # Парсим полное ФИО: "Галкин Владимир Александрович", "Вагидова Анжела Хажи-Мусаевна"
        parts = full_fio.split()
        if len(parts) >= 3:
            last_name = parts[0]
            first_name = parts[1]
            middle_name = parts[2]
            
            # Создаем различные варианты короткого ФИО
            variants = [
                f"{last_name} {first_name[0]}.{middle_name[0]}.",  # "Галкин В.А."
                f"{last_name} {first_name[0]}. {middle_name[0]}.",  # "Галкин В. А."
                f"{last_name} {first_name[0]}.{middle_name[0]}",    # "Галкин В.А" (без последней точки)
            ]
            # Составное отчество через дефис (Хажи-Мусаевна → Х.-М.)
            if '-' in middle_name:
                left, _, right = middle_name.partition('-')
                if left and right:
                    mid_abbrev = f"{left[0]}.-{right[0]}."
                    variants.extend([
                        f"{last_name} {first_name[0]}.{mid_abbrev}",   # "Вагидова А.Х.-М."
                        f"{last_name} {first_name[0]}. {mid_abbrev}",  # "Вагидова А. Х.-М."
                    ])
            
            for variant in variants:
                normalized = normalize_short_fio(variant)
                name_mapping[normalized] = full_fio
    
    # Варианты с "е" вместо "ё" в фамилии (Самакалев С.С. → Самакалёв Степан Сергеевич)
    for key in list(name_mapping):
        if 'ё' in key:
            name_mapping[key.replace('ё', 'е')] = name_mapping[key]
    
    return name_mapping

def _iter_rows_from_excel(path, min_cols=17):
    """Читает Excel-файл и выдаёт строки как списки строк (как csv.reader). Первая строка — заголовок."""
    if load_workbook is None:
        raise ImportError("Для чтения Excel установите openpyxl: pip install openpyxl")
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    for row in ws.iter_rows(values_only=True):
        cells = [str(c).strip() if c is not None else '' for c in (row or [])]
        if len(cells) < min_cols:
            cells.extend([''] * (min_cols - len(cells)))
        yield cells
    wb.close()


def _iter_rows_from_csv(path):
    """Читает CSV-файл и выдаёт строки. Первая строка — заголовок."""
    with open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        for row in reader:
            yield row


def _iter_data_rows(input_file):
    """Возвращает итератор по строкам данных (без заголовка). Каждая строка — list строк. Поддерживает .xlsx, .xls, .csv."""
    path_lower = input_file.lower()
    if path_lower.endswith('.xlsx') or path_lower.endswith('.xls'):
        it = _iter_rows_from_excel(input_file)
    else:
        it = _iter_rows_from_csv(input_file)
    header = next(it, None)
    return it


def count_data_rows(input_file):
    """Подсчитывает количество строк данных (без заголовка) во входном файле."""
    n = 0
    for _ in _iter_data_rows(input_file):
        n += 1
    return n


def process_timetable_file(input_file, teacher_name_mapping=None, total_rows=None, on_progress=None):
    """Обрабатывает файл с занятостью преподавателей (Excel .xlsx/.xls или CSV) и создает структурированные данные.
    total_rows: всего строк (для прогресса). on_progress(current, total) вызывается при обработке каждой строки."""
    if teacher_name_mapping is None:
        teacher_name_mapping = {}
    
    results = []
    external_teachers = {}
    missing_teachers = set()
    
    def row_iter():
        return _iter_data_rows(input_file)
    
    # Первый проход: собираем внешних преподавателей
    for row in row_iter():
        if len(row) < 17:
            continue
        teacher_fio = (row[0] or '').strip()
        if not teacher_fio or teacher_fio == 'вакансия':
            continue
        is_external = 'внешний' in (row[16].lower() if row[16] else '')
        if is_external:
            external_teachers[teacher_fio] = True
    
    # Второй проход: создаём записи
    current_row = 0
    for row in row_iter():
        current_row += 1
        if on_progress and total_rows is not None and total_rows > 0:
            on_progress(current_row, total_rows)
        if len(row) < 16:
            continue
        teacher_fio = (row[0] or '').strip()
        department = (row[1] or '').strip()
        pair_number = (row[2] or '').strip()
        is_external = external_teachers.get(teacher_fio, False)
        if not teacher_fio or teacher_fio == 'вакансия':
            continue
        for day_col, day_name in DAYS_MAPPING.items():
            if day_col >= len(row):
                continue
            groups_str = _normalize_list_delimiter((row[day_col] or '').strip())
            audience_col = AUDIENCE_COLUMNS[day_col]
            audience_str = (row[audience_col] or '').strip() if audience_col < len(row) else ''
            if not groups_str:
                continue
            audiences_parsed = parse_week_split_string(audience_str)
            # Список аудиторий по типу недели: каждая "501-33,501-34,501-35" → отдельная запись
            audience_list_by_week = {}
            first_audience = ''
            for val, wtype in audiences_parsed:
                if wtype not in audience_list_by_week:
                    audience_list_by_week[wtype] = []
                audience_list_by_week[wtype].append(val)
                if not first_audience:
                    first_audience = val
            groups_list = parse_group_string(groups_str)
            if not groups_list:
                continue
            num_subgroups = count_subgroups(groups_list)
            # Индекс в рамках одной недели для сопоставления группа ↔ аудитория
            index_by_week = {}
            for group_info in groups_list:
                w = group_info['week']
                idx = index_by_week.get(w, 0)
                index_by_week[w] = idx + 1
                aud_list = audience_list_by_week.get(w) or audience_list_by_week.get('both') or []
                audience_value = (aud_list[idx] if idx < len(aud_list) else (aud_list[-1] if aud_list else first_audience or ''))
                normalized_short_fio = normalize_short_fio(teacher_fio)
                full_fio = teacher_name_mapping.get(normalized_short_fio, teacher_fio)
                if full_fio == teacher_fio and teacher_name_mapping:
                    missing_teachers.add(teacher_fio)
                week_ru = WEEK_MAPPING.get(group_info['week'], group_info['week'])
                is_remote = audience_value.lower() == 'эоидот' if audience_value else False
                result_entry = {
                    'fio': full_fio,
                    'pair_number': pair_number,
                    'day_of_week': day_name,
                    'group': group_info['group'],
                    'audience': audience_value,
                    'department': department,
                    'week': week_ru,
                    'subgroup': group_info['subgroup'] or '',
                    'num_subgroups': num_subgroups,
                    'is_external': is_external,
                    'is_remote': is_remote,
                    'subject_name': ''
                }
                results.append(result_entry)
    return results, missing_teachers

def save_to_csv(data, output_file):
    """Сохраняет данные в CSV файл с UTF-8 BOM для корректного отображения в Excel"""
    if not data:
        return
    
    fieldnames = [
        'fio', 'pair_number', 'day_of_week', 'group', 'audience', 'department',
        'week', 'subgroup', 'num_subgroups', 'is_external', 'is_remote', 'subject_name'
    ]
    
    with open(output_file, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

def save_to_json(data, output_file):
    """Сохраняет данные в JSON файл"""
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_to_excel(data, output_file):
    """Сохраняет данные в Excel файл"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment
    except ImportError:
        print("Библиотека openpyxl не установлена. Установите её командой: pip install openpyxl")
        return
    
    if not data:
        return
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Расписание"
    
    # Заголовки
    headers = [
        'ФИО', 'Номер пары', 'День недели', 'Группа', 'Аудитория', 'Кафедра',
        'Неделя', 'Подгруппа', 'Кол-во подгрупп', 'Внешний', 'Дистанционно', 'Название предмета'
    ]
    
    # Записываем заголовки
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # Записываем данные
    fieldnames = [
        'fio', 'pair_number', 'day_of_week', 'group', 'audience', 'department',
        'week', 'subgroup', 'num_subgroups', 'is_external', 'is_remote', 'subject_name'
    ]
    
    for row_num, row_data in enumerate(data, 2):
        for col_num, field in enumerate(fieldnames, 1):
            value = row_data.get(field, '')
            # Преобразуем булевы значения в текст
            if isinstance(value, bool):
                value = 'Да' if value else 'Нет'
            ws.cell(row=row_num, column=col_num, value=value)
    
    # Автоподбор ширины столбцов
    for col in ws.columns:
        max_length = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[col_letter].width = adjusted_width
    
    # Замораживаем первую строку
    ws.freeze_panes = 'A2'
    
    wb.save(output_file)

def save_missing_teachers(missing_teachers, output_file='missing_teachers.csv'):
    """Сохраняет список преподавателей без полного ФИО в CSV файл с UTF-8 BOM"""
    if not missing_teachers:
        return
    
    # Сортируем для удобства
    sorted_teachers = sorted(missing_teachers)
    
    with open(output_file, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['short_fio'])  # Заголовок
        for teacher in sorted_teachers:
            writer.writerow([teacher])
    
    print(f"Сохранено {len(missing_teachers)} преподавателей без полного ФИО в {output_file}")

def save_missing_teachers_json(missing_teachers, output_file='error/missing_teachers.json'):
    """Сохраняет список ФИО, не найденных в справочнике, в JSON (папка error)."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    sorted_teachers = sorted(missing_teachers)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(sorted_teachers, f, ensure_ascii=False, indent=2)
    if missing_teachers:
        print(f"Сохранено {len(missing_teachers)} нераспознанных ФИО в {output_file}")


def main():
    # Создаем папки, если их нет
    os.makedirs('input', exist_ok=True)
    os.makedirs('output', exist_ok=True)
    os.makedirs('error', exist_ok=True)
    
    # Ищем файл занятости: сначала Excel, затем CSV
    xlsx_files = glob.glob("input/Zanyatost prepodavateley*.xlsx")
    if not xlsx_files:
        xlsx_files = glob.glob("input/Zanyatost prepodavateley*.xls")
    if xlsx_files:
        input_file = xlsx_files[0]
        print(f"Обрабатываем файл (Excel): {input_file}")
    else:
        csv_files = glob.glob("input/Zanyatost prepodavateley*.csv")
        if not csv_files:
            print("Не найден файл с расписанием. Ожидается 'input/Zanyatost prepodavateley*.xlsx' или 'input/Zanyatost prepodavateley*.csv'")
            return
        input_file = csv_files[0]
        print(f"Обрабатываем файл (CSV): {input_file}")
    
    # Загружаем маппинг ФИО преподавателей
    teacher_name_mapping = load_teacher_names()
    if teacher_name_mapping:
        print(f"Загружено {len(teacher_name_mapping)} полных ФИО преподавателей")
    
    # Подсчёт строк для прогресса (вывод PROGRESS: current total для бэкенда)
    total_rows = count_data_rows(input_file)
    print(f"PROGRESS: 0 {total_rows}", flush=True)  # Сразу показываем "0 из N"
    def on_progress(current, total):
        print(f"PROGRESS: {current} {total}", flush=True)
    
    # Обрабатываем файл (Excel или CSV)
    results, missing_teachers = process_timetable_file(
        input_file, teacher_name_mapping, total_rows=total_rows, on_progress=on_progress
    )
    
    print(f"Обработано записей: {len(results)}")
    
    # Сохраняем результаты в папку output
    csv_output = 'output/timetable_teacher.csv'
    json_output = 'output/timetable_teacher.json'
    excel_output = 'output/timetable_teacher.xlsx'
    
    save_to_csv(results, csv_output)
    print(f"Данные сохранены в CSV: {csv_output}")
    
    save_to_json(results, json_output)
    print(f"Данные сохранены в JSON: {json_output}")
    
    save_to_excel(results, excel_output)
    print(f"Данные сохранены в Excel: {excel_output}")
    
    # Сохраняем список нераспознанных ФИО: JSON в error/ (всегда), CSV в output/ (если есть)
    save_missing_teachers_json(missing_teachers, 'error/missing_teachers.json')
    if missing_teachers:
        save_missing_teachers(missing_teachers, 'output/missing_teachers.csv')

if __name__ == '__main__':
    main()
