#!/usr/bin/env python3
"""
Только schedule_override и (если есть таблица) schedule_override_teacher.

  Очищает: DELETE FROM schedule_override — каскад по FK (schedule_override_teacher,
  timeslot_link и т.д.). Справочники, группы, аудитории, семестр и прочее не изменяются.

  Заполняет колонки из JSON + id из существующей БД:
    subject_id, room_id, group_id, semester_id — по имени/ключу из JSON → id в БД;
    source_pattern_item_id — только если в JSON есть число и такой id есть в schedule_pattern_item;
    преподаватель — по ФИО из JSON → teacher.id, затем строка в schedule_override_teacher
    (если колонки teacher_id в schedule_override нет; иначе дополнительно UPDATE teacher_id для старой схемы).

Использование:
  python fill_db_from_institute_direction_groups.py [--semester-id ID] [--dedupe] [--strict]
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_env_path = PROJECT_ROOT / "web_app" / "backend" / ".env"
if _env_path.exists():
    with open(_env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor, execute_values
except ImportError:
    print("Ошибка: установите psycopg2-binary: pip install psycopg2-binary")
    sys.exit(1)

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "edro.su"),
    "port": int(os.environ.get("DB_PORT", "50003")),
    "user": os.environ.get("DB_USER", "edro"),
    "password": os.environ.get("DB_PASSWORD", "Pg123!"),
    "database": os.environ.get("DB_NAME", "test_sursu_timetable"),
}

WEEKDAY_MAP = {
    "понедельник": 1,
    "вторник": 2,
    "среда": 3,
    "четверг": 4,
    "пятница": 5,
    "суббота": 6,
    "воскресенье": 7,
}

WEEK_TYPE_VALUES = ("обе недели", "числитель", "знаменатель")
CLASS_TYPE_VALUES = (
    "лекция",
    "практика",
    "лабораторная",
    "консультация",
    "экзамен",
    "зачет",
    "зачет с оценкой",
    "пересдача",
)

BATCH_SIZE = 2000

INSERT_SQL = """
INSERT INTO schedule_override (
    weekday,
    subject_id,
    week_type,
    class_type,
    room_id,
    group_id,
    subgroup_count,
    subgroup_no,
    semester_id,
    duration_pairs,
    is_remote,
    timeslot_no,
    time_start_custom,
    time_end_custom,
    source_pattern_item_id,
    note
) VALUES %s RETURNING id
"""


def _n(s):
    return (s or "").strip() or None


def _nl(s):
    v = _n(s)
    return v.lower() if v else None


def weekday_to_int(day_text):
    if not day_text:
        return None
    key = _nl(day_text)
    if not key:
        return None
    return WEEKDAY_MAP.get(key)


def parse_week_type(s):
    v = _n(s)
    if not v:
        return None
    return v if v in WEEK_TYPE_VALUES else None


def parse_class_type(s):
    v = _n(s)
    if not v:
        return None
    return v if v in CLASS_TYPE_VALUES else None


def _positive_int_or_none(v):
    """Целое > 0 или None. 0 в num_subgroups не пишем в subgroup_count как «ноль п/г»."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, str) and not v.strip():
        return None
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def building_from_audience(audience):
    if not audience:
        return None
    s = (audience or "").strip()
    m = re.match(r"^([^\d]*)", s)
    if m and m.group(1):
        return m.group(1)
    return None


def iter_schedule_entries(data):
    for _inst_name, dirs in data.items():
        if not isinstance(dirs, dict):
            continue
        for key, val in dirs.items():
            if key == "groups":
                continue
            if isinstance(val, dict) and "schedule" in val:
                group_name = key
                for item in val.get("schedule") or []:
                    if isinstance(item, dict):
                        yield group_name, item


def table_exists(cur, name: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (name,),
    )
    return cur.fetchone() is not None


def column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    return cur.fetchone() is not None


def main():
    parser = argparse.ArgumentParser(
        description="Заполнение schedule_override из institute_direction_groups.json (id только из БД)"
    )
    parser.add_argument(
        "--semester-id",
        type=int,
        default=None,
        help="ID семестра (иначе первый из таблицы semester)",
    )
    parser.add_argument("--dedupe", action="store_true", help="Убрать точные дубликаты строк перед вставкой")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Пропускать строки, если нет timeslot для корпуса из audience",
    )
    args = parser.parse_args()

    path_json = PROJECT_ROOT / "output" / "institute_direction_groups.json"
    if not path_json.exists():
        print(f"Файл не найден: {path_json}")
        sys.exit(1)

    with open(path_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False

    stats = {"skipped": 0, "inserted": 0, "teachers_linked": 0}

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            has_junction = table_exists(c, "schedule_override_teacher")
            has_override_teacher_col = column_exists(c, "schedule_override", "teacher_id")

        with conn.cursor() as c:
            c.execute("DELETE FROM schedule_override")
            c.execute(
                "SELECT setval(pg_get_serial_sequence(%s, %s), 1, false)",
                ("schedule_override", "id"),
            )
        conn.commit()
        print("Очищена только таблица schedule_override (остальные данные БД не трогались).")

        semester_id = args.semester_id
        if semester_id is None:
            with conn.cursor(cursor_factory=RealDictCursor) as c:
                c.execute("SELECT id FROM semester ORDER BY id LIMIT 1")
                row = c.fetchone()
                if not row:
                    print("Ошибка: в таблице semester нет записей — укажите --semester-id.")
                    sys.exit(1)
                semester_id = row["id"]
        else:
            with conn.cursor() as c:
                c.execute("SELECT 1 FROM semester WHERE id = %s", (semester_id,))
                if not c.fetchone():
                    print(f"Ошибка: semester id={semester_id} не найден.")
                    sys.exit(1)

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, LOWER(TRIM(fio)) AS k FROM teacher")
            teacher_by_fio = {r["k"]: r["id"] for r in cur.fetchall() if r["k"]}

            cur.execute("SELECT id, LOWER(TRIM(name)) AS k FROM subject")
            subject_by_name = {r["k"]: r["id"] for r in cur.fetchall() if r["k"]}

            cur.execute("SELECT id, LOWER(TRIM(name)) AS k FROM room")
            room_by_name = {r["k"]: r["id"] for r in cur.fetchall() if r["k"]}

            cur.execute("SELECT id, pair_number, building FROM timeslot")
            timeslot_rows = cur.fetchall()
            timeslot_by_pair_building = {}
            buildings_in_timeslot = set()
            for t in timeslot_rows:
                b = t["building"] or ""
                buildings_in_timeslot.add(b)
                timeslot_by_pair_building[(t["pair_number"], b)] = t["id"]
            for t in timeslot_rows:
                if t["building"] is None:
                    timeslot_by_pair_building[(t["pair_number"], None)] = t["id"]

            cur.execute("SELECT id, name FROM student_group")
            group_by_name = {r["name"]: r["id"] for r in cur.fetchall()}

            pattern_item_ids = set()
            if table_exists(cur, "schedule_pattern_item"):
                cur.execute("SELECT id FROM schedule_pattern_item")
                pattern_item_ids = {r["id"] for r in cur.fetchall()}

        override_rows = []
        teacher_ids_parallel = []

        for group_name, row in iter_schedule_entries(data):
            weekday = weekday_to_int(row.get("day_of_week"))
            if weekday is None:
                stats["skipped"] += 1
                continue

            group_id = group_by_name.get(group_name) if group_name else None

            fio_n = _nl(row.get("fio"))
            teacher_id = teacher_by_fio.get(fio_n) if fio_n else None

            subject_id = None
            subj_n = _nl(row.get("subject_name"))
            if subj_n:
                subject_id = subject_by_name.get(subj_n)

            week_type = parse_week_type(row.get("week_type")) or "обе недели"
            class_type = parse_class_type(row.get("lecture_type")) or "лекция"

            room_id = None
            aud_n = _nl(row.get("audience"))
            if aud_n:
                room_id = room_by_name.get(aud_n)

            subgroup_count = _positive_int_or_none(row.get("num_subgroups"))
            subgroup_no = _positive_int_or_none(row.get("subgroup"))
            if subgroup_no is not None:
                base = subgroup_count if subgroup_count is not None else 0
                subgroup_count = max(base, subgroup_no, 2)

            duration_pairs = None
            if row.get("duration_pairs") is not None:
                try:
                    duration_pairs = float(row["duration_pairs"])
                    if not (1 <= duration_pairs <= 8):
                        duration_pairs = None
                except (ValueError, TypeError):
                    pass

            is_remote = row.get("is_remote")
            is_remote = bool(is_remote) if is_remote is not None else False

            pair_number = row.get("pair_number")
            if pair_number is None:
                stats["skipped"] += 1
                continue

            building = building_from_audience(row.get("audience"))
            building_str = (building or "").strip() or ""
            building_key = (pair_number, building_str) if building_str else (pair_number, "")

            timeslot_exists = timeslot_by_pair_building.get(building_key) is not None
            if not timeslot_exists and building_str:
                timeslot_exists = timeslot_by_pair_building.get((pair_number, "")) is not None

            if not timeslot_exists and building_str in buildings_in_timeslot:
                if args.strict:
                    stats["skipped"] += 1
                    continue
                stats["skipped"] += 1
                continue

            source_pattern_item_id = None
            if row.get("source_pattern_item_id") is not None:
                try:
                    spi = int(row["source_pattern_item_id"])
                    if spi in pattern_item_ids:
                        source_pattern_item_id = spi
                except (ValueError, TypeError):
                    pass

            note = _n(row.get("note"))

            time_start_custom = row.get("time_start_custom")
            time_end_custom = row.get("time_end_custom")

            override_rows.append(
                (
                    weekday,
                    subject_id,
                    week_type,
                    class_type,
                    room_id,
                    group_id,
                    subgroup_count,
                    subgroup_no,
                    semester_id,
                    duration_pairs,
                    is_remote,
                    pair_number,
                    time_start_custom,
                    time_end_custom,
                    source_pattern_item_id,
                    note,
                )
            )
            teacher_ids_parallel.append(teacher_id)

        if args.dedupe:
            seen = set()
            deduped_o = []
            deduped_t = []
            for r, tid in zip(override_rows, teacher_ids_parallel):
                if r in seen:
                    continue
                seen.add(r)
                deduped_o.append(r)
                deduped_t.append(tid)
            override_rows = deduped_o
            teacher_ids_parallel = deduped_t

        if not override_rows:
            print("Нет строк для вставки в schedule_override.")
            conn.commit()
            return

        all_ids = []
        with conn.cursor() as cur:
            for i in range(0, len(override_rows), BATCH_SIZE):
                batch = override_rows[i : i + BATCH_SIZE]
                execute_values(cur, INSERT_SQL, batch, page_size=len(batch))
                all_ids.extend(r[0] for r in cur.fetchall())

        stats["inserted"] = len(all_ids)

        if has_junction and len(all_ids) == len(teacher_ids_parallel):
            link_rows = [
                (oid, tid, 1)
                for oid, tid in zip(all_ids, teacher_ids_parallel)
                if tid is not None
            ]
            if link_rows:
                with conn.cursor() as cur:
                    execute_values(
                        cur,
                        """
                        INSERT INTO schedule_override_teacher
                            (schedule_override_id, teacher_id, sort_order)
                        VALUES %s
                        ON CONFLICT (schedule_override_id, teacher_id) DO NOTHING
                        """,
                        link_rows,
                        page_size=BATCH_SIZE,
                    )
                stats["teachers_linked"] = len(link_rows)

        if has_override_teacher_col:
            updates = [
                (teacher_ids_parallel[j], all_ids[j])
                for j in range(len(all_ids))
                if j < len(teacher_ids_parallel) and teacher_ids_parallel[j] is not None
            ]
            if updates:
                with conn.cursor() as cur:
                    cur.executemany(
                        "UPDATE schedule_override SET teacher_id = %s WHERE id = %s",
                        [(t, i) for t, i in updates],
                    )
                stats["teachers_linked"] = len(updates)

        conn.commit()

        print(f"schedule_override: вставлено {stats['inserted']} строк (semester_id={semester_id}).")
        if has_junction or has_override_teacher_col:
            print(f"Преподаватели привязаны: {stats['teachers_linked']} связей.")
        if stats["skipped"]:
            print(f"Пропущено строк: {stats['skipped']}")
    except Exception as e:
        conn.rollback()
        print(f"Ошибка: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
