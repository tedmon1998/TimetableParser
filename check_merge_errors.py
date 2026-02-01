# -*- coding: utf-8 -*-
"""Проверка корректности week_error/audience_error для записи в слитой БД."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'web_app', 'backend'))
import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    'host': 'edro.su',
    'port': 50003,
    'user': 'edro',
    'password': 'Pg123!',
    'database': 'test_sursu_timetable'
}

def main():
    intermediate_id = 50
    cleaned_id = 76280
    teacher_id = 66581

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT * FROM intermediate_timetable WHERE id = %s", (intermediate_id,))
    row_int = cur.fetchone()
    cur.execute("SELECT id, day_of_week, pair_number, group_name, week_type, audience, subject_name FROM timetable_cleaned WHERE id = %s", (cleaned_id,))
    row_cleaned = cur.fetchone()
    cur.execute("SELECT id, day_of_week, pair_number, group_name, week_type, audience, subject_name FROM timetable_teacher WHERE id = %s", (teacher_id,))
    row_teacher = cur.fetchone()
    # Слитая запись привязана к teacher_id из самой записи (может быть не 66581!)
    teacher_id_actual = row_int.get('teacher_id') if row_int else None
    row_teacher_actual = None
    if teacher_id_actual:
        cur.execute("SELECT id, day_of_week, pair_number, group_name, week_type, audience, subject_name FROM timetable_teacher WHERE id = %s", (teacher_id_actual,))
        row_teacher_actual = cur.fetchone()

    cur.close()
    conn.close()

    print("=== intermediate_timetable id =", intermediate_id, "===")
    if row_int:
        for k, v in row_int.items():
            print(f"  {k}: {repr(v)}")
        print("  week_error:", row_int.get('week_error'))
        print("  audience_error:", row_int.get('audience_error'))
    else:
        print("  Запись не найдена")

    print("\n=== timetable_cleaned id =", cleaned_id, "===")
    if row_cleaned:
        for k, v in row_cleaned.items():
            print(f"  {k}: {repr(v)}")
        wt_c = row_cleaned.get('week_type')
        print("  week_type repr:", repr(wt_c), "len:", len(wt_c) if wt_c else 0)
    else:
        print("  Запись не найдена")

    print("\n=== timetable_teacher id =", teacher_id, "(который вы указали) ===")
    if row_teacher:
        for k, v in row_teacher.items():
            print(f"  {k}: {repr(v)}")
        wt_t = row_teacher.get('week_type')
        print("  week_type repr:", repr(wt_t), "len:", len(wt_t) if wt_t else 0)
    else:
        print("  Запись не найдена")

    print("\n=== timetable_teacher id =", teacher_id_actual, "(к которому реально привязана слитая запись) ===")
    if row_teacher_actual:
        for k, v in row_teacher_actual.items():
            print(f"  {k}: {repr(v)}")
        wt_ta = row_teacher_actual.get('week_type')
        print("  week_type repr:", repr(wt_ta), "len:", len(wt_ta) if wt_ta else 0)
    else:
        print("  Запись не найдена")

    if row_cleaned and row_teacher_actual:
        wt_c = row_cleaned.get('week_type')
        wt_t = row_teacher_actual.get('week_type')
        print("\n=== Сравнение week_type (cleaned vs фактический teacher", teacher_id_actual, ") ===")
        print("  cleaned week_type:", repr(wt_c))
        print("  teacher (факт.) week_type:", repr(wt_t))
        print("  equal (==):", wt_c == wt_t)
        print("  stripped equal:", (wt_c or '').strip() == (wt_t or '').strip())
        if wt_c != wt_t:
            print("  ПРИЧИНА ОШИБКИ: значения различаются (возможно пробелы/кодировка)")

if __name__ == '__main__':
    main()
