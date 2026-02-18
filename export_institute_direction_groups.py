#!/usr/bin/env python3
"""
Скрипт для экспорта из БД JSON-файла со структурой:
институт -> направление -> группы с расписанием.

Использует таблицу schedule, при её пустоте — intermediate_timetable.
"""

import json
import os
import sys

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("Ошибка: установите psycopg2-binary: pip install psycopg2-binary")
    sys.exit(1)

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'edro.su'),
    'port': int(os.environ.get('DB_PORT', '50003')),
    'user': os.environ.get('DB_USER', 'edro'),
    'password': os.environ.get('DB_PASSWORD', 'Pg123!'),
    'database': os.environ.get('DB_NAME', 'test_sursu_timetable'),
}


def _normalize(s):
    """Нормализует строку для использования как ключ."""
    if s is None:
        return ''
    return str(s).strip() or ''


def _row_to_lesson(row):
    """Преобразует строку БД в словарь занятия (без institute/direction/group_name в каждом)."""
    return {
        'day_of_week': _normalize(row.get('day_of_week')),
        'pair_number': row.get('pair_number'),
        'subject_name': _normalize(row.get('subject_name')),
        'lecture_type': _normalize(row.get('lecture_type')),
        'audience': _normalize(row.get('audience')),
        'week_type': _normalize(row.get('week_type')),
        'subgroup': row.get('subgroup'),
        'fio': _normalize(row.get('fio')),
    }


def _get_source_table(conn):
    """Возвращает таблицу-источник: schedule или intermediate_timetable."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM schedule")
    count = cur.fetchone()[0]
    cur.close()
    return 'schedule' if count > 0 else 'intermediate_timetable'


def export_institute_direction_groups(output_path: str) -> dict:
    """
    Достаёт из БД расписание, формирует структуру:
    {
      "институт": {
        "направление": {
          "groups": ["501-11", "501-12"],
          "501-11": { "schedule": [...] },
          "501-12": { "schedule": [...] }
        }
      }
    }
    """
    conn = psycopg2.connect(**DB_CONFIG)

    table = _get_source_table(conn)
    cols = (
        'day_of_week', 'pair_number', 'subject_name', 'lecture_type', 'audience',
        'group_name', 'week_type', 'subgroup', 'institute', 'course', 'direction',
        'department', 'is_external', 'is_remote', 'num_subgroups', 'fio'
    )
    col_str = ', '.join(cols)

    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(f"""
        SELECT {col_str}
        FROM {table}
        WHERE NULLIF(TRIM(COALESCE(institute, '')), '') IS NOT NULL
          AND NULLIF(TRIM(COALESCE(direction, '')), '') IS NOT NULL
          AND NULLIF(TRIM(COALESCE(group_name, '')), '') IS NOT NULL
        ORDER BY institute, direction, group_name, day_of_week, pair_number
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    # Структура: institute -> direction -> { groups: [...], group_name: { schedule: [...] } }
    result = {}
    for row in rows:
        inst = _normalize(row.get('institute'))
        direc = _normalize(row.get('direction'))
        grp = _normalize(row.get('group_name'))
        if not inst or not direc or not grp:
            continue

        if inst not in result:
            result[inst] = {}
        if direc not in result[inst]:
            result[inst][direc] = {'groups': []}

        dd = result[inst][direc]
        if grp not in dd['groups']:
            dd['groups'].append(grp)
        if grp not in dd:
            dd[grp] = {'schedule': []}
        dd[grp]['schedule'].append(_row_to_lesson(row))

    # Сортируем группы в каждом направлении
    for inst_data in result.values():
        for direc_data in inst_data.values():
            direc_data['groups'] = sorted(direc_data['groups'])

    # Сохраняем в файл
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_output = os.path.join(script_dir, 'output', 'institute_direction_groups.json')
    output = sys.argv[1] if len(sys.argv) > 1 else default_output

    print(f"Экспорт в {output}...")
    data = export_institute_direction_groups(output)
    institutes = len(data)
    directions = sum(len(d) for d in data.values())
    groups = sum(
        len(dd.get('groups', []))
        for d in data.values()
        for dd in d.values()
        if isinstance(dd, dict)
    )
    print(f"Готово: {institutes} институтов, {directions} направлений, {groups} групп.")


if __name__ == '__main__':
    main()
