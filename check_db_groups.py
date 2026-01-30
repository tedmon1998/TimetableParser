#!/usr/bin/env python3
"""
Проверяет, что группы 501-33, 501-34, 501-35 — отдельные записи (не одна "501-33,501-34,501-35").

  python check_db_groups.py          — проверка только по CSV (без БД)
  python check_db_groups.py --db    — загрузить CSV в БД и проверить в БД
"""
import os
import sys
import csv

# Корень проекта
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'web_app', 'backend'))

def check_csv_only():
    """Проверка по файлу output/timetable_teacher.csv без подключения к БД."""
    csv_path = os.path.join(PROJECT_ROOT, 'output', 'timetable_teacher.csv')
    if not os.path.isfile(csv_path):
        print(f'Файл не найден: {csv_path}. Сначала запустите process_timetable.py')
        return 1
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    # Колонка группы в CSV от process_timetable — "group"
    key = 'group' if rows and 'group' in rows[0] else 'group_name'
    total = len(rows)
    g33 = sum(1 for r in rows if (r.get(key) or '').strip() == '501-33')
    g34 = sum(1 for r in rows if (r.get(key) or '').strip() == '501-34')
    g35 = sum(1 for r in rows if (r.get(key) or '').strip() == '501-35')
    one_cell = sum(1 for r in rows if (r.get(key) or '').strip() == '501-33,501-34,501-35')
    with_comma = sum(1 for r in rows if ',' in (r.get(key) or ''))
    print('Проверка по CSV (output/timetable_teacher.csv):')
    print(f'  Всего записей: {total}')
    print(f'  Группа 501-33: {g33} записей')
    print(f'  Группа 501-34: {g34} записей')
    print(f'  Группа 501-35: {g35} записей')
    print(f'  Одна запись "501-33,501-34,501-35": {one_cell} (ожидаем 0)')
    print(f'  Записей с запятой в группе: {with_comma}')
    if one_cell == 0 and (g33 or g34 or g35):
        print('  Итог: 501-33, 501-34, 501-35 разнесены по отдельным записям — OK')
    return 0

def main():
    if '--db' not in sys.argv:
        return check_csv_only()

    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor, execute_values
    except ImportError:
        print('Установите psycopg2: pip install psycopg2-binary')
        return 1

    # Параметры из web_app/backend/app.py
    DB_CONFIG = {
        'host': 'edro.su',
        'port': 50003,
        'user': 'edro',
        'password': 'Pg123!',
        'database': 'test_sursu_timetable'
    }

    csv_path = os.path.join(PROJECT_ROOT, 'output', 'timetable_teacher.csv')
    if not os.path.isfile(csv_path):
        print(f'Сначала запустите process_timetable.py — файл не найден: {csv_path}')
        return 1

    def to_int(v):
        if v is None or str(v).strip() == '':
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

    def to_bool(v):
        if v is None or str(v).strip() == '':
            return False
        return str(v).lower() in ('true', '1', 'yes', 't')

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
    except Exception as e:
        print(f'Ошибка подключения к БД: {e}')
        return 1

    try:
        # Загрузка CSV
        rows_to_insert = []
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                group_val = (row.get('group_name') or row.get('group') or '').strip() or None
                rows_to_insert.append((
                    row.get('fio') or None,
                    to_int(row.get('pair_number')),
                    row.get('day_of_week') or None,
                    group_val,
                    row.get('audience') or None,
                    row.get('department') or None,
                    (row.get('week_type') or row.get('week') or '').strip() or None,
                    to_int(row.get('subgroup')),
                    to_int(row.get('num_subgroups')),
                    to_bool(row.get('is_external')),
                    to_bool(row.get('is_remote')),
                    row.get('subject_name') or None,
                ))

        cursor.execute('TRUNCATE TABLE timetable_teacher')
        conn.commit()

        insert_sql = """
        INSERT INTO timetable_teacher (
            fio, pair_number, day_of_week, group_name, audience, department,
            week_type, subgroup, num_subgroups, is_external, is_remote, subject_name
        ) VALUES %s
        """
        execute_values(cursor, insert_sql, rows_to_insert)
        conn.commit()
        print(f'Загружено записей в timetable_teacher: {len(rows_to_insert)}')

        # Проверка: группы 501-33, 501-34, 501-35 — отдельные записи
        cursor.execute("""
            SELECT group_name, COUNT(*) AS cnt
            FROM timetable_teacher
            WHERE group_name IN ('501-33', '501-34', '501-35')
            GROUP BY group_name
            ORDER BY group_name
        """)
        rows = cursor.fetchall()
        print('\nВ БД — количество записей по группе (должны быть отдельно):')
        for r in rows:
            print(f"  {r['group_name']}: {r['cnt']}")

        # Не должно быть одной записи с "501-33,501-34,501-35"
        cursor.execute("""
            SELECT COUNT(*) AS cnt FROM timetable_teacher
            WHERE group_name = '501-33,501-34,501-35'
        """)
        one_cell = cursor.fetchone()['cnt']
        if one_cell == 0:
            print('\n  Записи с одной ячейкой "501-33,501-34,501-35": 0 (ожидаем 0) — OK')
        else:
            print(f'\n  Внимание: записей с group_name = "501-33,501-34,501-35": {one_cell}')

        # Сколько всего записей с запятой в group_name
        cursor.execute("SELECT COUNT(*) AS cnt FROM timetable_teacher WHERE group_name LIKE '%,%'")
        with_comma = cursor.fetchone()['cnt']
        print(f'\nЗаписей с запятой в group_name (желательно 0): {with_comma}')

        cursor.close()
        conn.close()
        print('\nПроверка завершена.')
        return 0
    except Exception as e:
        print(f'Ошибка: {e}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
