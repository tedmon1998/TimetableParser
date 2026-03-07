#!/usr/bin/env python3
"""
Читает файл «Занятость преподавателей» (input/Zanyatost prepodavateley*.xlsx),
извлекает пары (группа, кафедра) и обновляет в таблице student_group поле department_id.
Кафедра в Excel может быть номером (id) или названием — сопоставление по department.id или department.name.
"""
import os
import re
import sys
import glob
import logging
import argparse

# Корень проекта для импорта process_timetable
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import psycopg2
from psycopg2.extras import RealDictCursor

# Столбцы с группами по дням (как в process_timetable)
DAYS_GROUP_COLS = (3, 5, 7, 9, 11, 13)
COL_DEPARTMENT = 1


def _normalize_list_delimiter(s):
    if not s:
        return s
    s = str(s)
    for char in ('.', ';', '\uFF0C', '\u201A', '，', '\u060C', '\u3001', '\uFE50', '\uFE51'):
        s = s.replace(char, ',')
    return s


def _iter_data_rows(input_file):
    """Строки данных из Excel (без заголовка). Используем логику process_timetable."""
    from process_timetable import _iter_rows_from_excel, _iter_rows_from_csv
    path_lower = input_file.lower()
    if path_lower.endswith('.xlsx') or path_lower.endswith('.xls'):
        it = _iter_rows_from_excel(input_file, min_cols=17)
    else:
        it = _iter_rows_from_csv(input_file)
    next(it, None)  # skip header
    return it


def collect_group_department_pairs(input_file):
    """
    Собирает из файла занятости пары (группа, кафедра).
    Кафедра — значение из столбца 1 (номер или название).
    Группы — из столбцов дней (3, 5, 7, 9, 11, 13) через parse_group_string.
    Возвращает dict: group_name -> department_value (последнее встреченное для группы).
    """
    from process_timetable import parse_group_string
    group_to_department = {}
    for row in _iter_data_rows(input_file):
        if len(row) < 14:
            continue
        department = (row[COL_DEPARTMENT] or '').strip()
        if not department:
            continue
        for col in DAYS_GROUP_COLS:
            if col >= len(row):
                continue
            groups_str = _normalize_list_delimiter((row[col] or '').strip())
            if not groups_str:
                continue
            for g in parse_group_string(groups_str):
                group_name = (g.get('group') or '').strip()
                if group_name:
                    group_to_department[group_name] = department
    return group_to_department


def resolve_department_id(cursor, department_value):
    """
    По значению из Excel (номер или название) возвращает department.id или None.
    - Если значение — целое число, ищем по id.
    - Иначе ищем по name (LOWER(TRIM(name))).
    """
    if not department_value:
        return None
    s = str(department_value).strip()
    # Попытка как число (id кафедры)
    if re.match(r'^\d+$', s):
        cursor.execute("SELECT id FROM department WHERE id = %s", (int(s),))
        row = cursor.fetchone()
        if row:
            return row['id']
    # По имени
    key = s.lower().strip()
    if not key:
        return None
    cursor.execute(
        "SELECT id FROM department WHERE LOWER(TRIM(name)) = %s",
        (key,)
    )
    row = cursor.fetchone()
    if row:
        return row['id']
    # Дополнительно: имя может быть "Кафедра № 5" — попробовать число
    m = re.search(r'(\d+)', s)
    if m:
        cursor.execute("SELECT id FROM department WHERE id = %s", (int(m.group(1)),))
        row = cursor.fetchone()
        if row:
            return row['id']
    return None


def main():
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    log = logging.getLogger(__name__)
    parser = argparse.ArgumentParser(description='Обновление кафедр у групп из файла занятости преподавателей')
    parser.add_argument(
        '--input',
        default=None,
        help='Путь к файлу .xlsx (по умолчанию: input/Zanyatost prepodavateley*.xlsx)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Только показать, что будет обновлено, без записи в БД'
    )
    args = parser.parse_args()

    project_root = _project_root
    if args.input:
        input_path = os.path.abspath(args.input)
    else:
        pattern = os.path.join(project_root, 'input', 'Zanyatost prepodavateley*.xlsx')
        files = glob.glob(pattern)
        if not files:
            pattern = os.path.join(project_root, 'input', 'Zanyatost prepodavateley*.xls')
            files = glob.glob(pattern)
        if not files:
            log.error("Не найден файл. Ожидается input/Zanyatost prepodavateley*.xlsx или --input <путь>")
            return 1
        input_path = files[0]
    if not os.path.isfile(input_path):
        log.error("Файл не найден: %s", input_path)
        return 1

    log.info("Чтение файла: %s", input_path)
    group_to_department = collect_group_department_pairs(input_path)
    log.info("Найдено пар (группа, кафедра): %s", len(group_to_department))

    db_host = os.environ.get('DB_HOST', 'edro.su')
    db_port = int(os.environ.get('DB_PORT', '50003'))
    db_user = os.environ.get('DB_USER', 'edro')
    db_password = os.environ.get('DB_PASSWORD', 'Pg123!')
    db_name = os.environ.get('DB_NAME', 'test_sursu_timetable')

    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        user=db_user,
        password=db_password,
        database=db_name
    )

    updated = 0
    skipped_no_dept = 0
    dept_resolved = {}

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for group_name, dept_value in group_to_department.items():
                dept_id = dept_resolved.get(dept_value)
                if dept_id is None:
                    dept_id = resolve_department_id(cur, dept_value)
                    dept_resolved[dept_value] = dept_id
                if dept_id is None:
                    skipped_no_dept += 1
                    continue
                if args.dry_run:
                    log.info("[dry-run] Группа %s -> кафедра id=%s (%s)", group_name, dept_id, dept_value)
                    updated += 1
                    continue
                cur.execute(
                    "UPDATE student_group SET department_id = %s WHERE name = %s",
                    (dept_id, group_name)
                )
                if cur.rowcount:
                    updated += 1
            if not args.dry_run:
                conn.commit()
    finally:
        conn.close()

    if skipped_no_dept:
        log.info("Пропущено (кафедра не найдена в БД): %s пар", skipped_no_dept)
    log.info("Обновлено записей student_group: %s", updated)
    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
