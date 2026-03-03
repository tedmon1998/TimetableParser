#!/usr/bin/env python3
"""
Миграция данных из старой таблицы schedule в новую схему PostgreSQL.

Разрешено только:
  - INSERT в student_group (группы по sg.name UNIQUE);
  - INSERT в schedule_override;
  - UPDATE teacher.is_external.

Остальные справочники не создаются — ID ищутся по существующим данным.

Использование:
  python db_migration_old_db_to_new.py --semester-id 1 [--clean] [--dedupe] [--strict]
"""

import argparse
import logging
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

# День недели: текст -> 1..7 (понедельник=1, воскресенье=7)
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
CLASS_TYPE_VALUES = ("лекция", "практика", "лабораторная")

BATCH_SIZE = 2000


def _n(s):
    return (s or "").strip() or None


def _nl(s):
    """Normalize for lookup: trim + lower."""
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


def building_from_audience(audience):
    """Извлечь корпус: всё до первой цифры. 'А417' -> 'А', 'МК205' -> 'МК'."""
    if not audience:
        return None
    s = (audience or "").strip()
    m = re.match(r"^([^\d]*)", s)
    if m and m.group(1):
        return m.group(1)
    return None


def direction_code_from_string(s):
    """В s.direction строка 'код + название'. Код = первое слово до пробела."""
    v = _n(s)
    if not v:
        return None
    parts = v.split(None, 1)
    return parts[0] if parts else None


def course_to_int(s):
    if s is None:
        return None
    try:
        v = int(str(s).strip())
        return v if 1 <= v <= 6 else None
    except (ValueError, TypeError):
        return None


def run(conn, semester_id: int, clean: bool, dedupe: bool, strict: bool, has_duration_pairs: bool):
    stats = {
        "schedule_rows": 0,
        "student_group_inserted": 0,
        "schedule_override_inserted": 0,
        "teacher_updated": 0,
        "skipped": 0,
        "errors": [],
    }

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # ——— Очистка (опционально) ———
        if clean:
            cur.execute("DELETE FROM schedule_override")
            deleted_so = cur.rowcount
            cur.execute("DELETE FROM student_group")
            deleted_sg = cur.rowcount
            for table, col in (("schedule_override", "id"), ("student_group", "id")):
                cur.execute(
                    "SELECT setval(pg_get_serial_sequence(%s, %s), 1, false)",
                    (table, col),
                )
            conn.commit()
            logging.info("Очистка: удалено schedule_override=%s, student_group=%s", deleted_so, deleted_sg)

        # ——— Справочники: загрузить в память ———
        cur.execute("SELECT id, LOWER(TRIM(fio)) AS k FROM teacher")
        teacher_by_fio = {r["k"]: r["id"] for r in cur.fetchall() if r["k"]}

        cur.execute("SELECT id, LOWER(TRIM(name)) AS k FROM subject")
        subject_by_name = {r["k"]: r["id"] for r in cur.fetchall() if r["k"]}

        cur.execute("SELECT id, LOWER(TRIM(name)) AS k FROM room")
        room_by_name = {r["k"]: r["id"] for r in cur.fetchall() if r["k"]}

        cur.execute("SELECT id, LOWER(TRIM(name)) AS k FROM institute")
        institute_by_name = {r["k"]: r["id"] for r in cur.fetchall() if r["k"]}

        cur.execute("SELECT id, institute_id, LOWER(TRIM(name)) AS k FROM department")
        departments = cur.fetchall()
        department_by_name = {}
        department_by_name_and_institute = {}
        for d in departments:
            k = d["k"]
            if k:
                department_by_name[k] = d["id"]
                department_by_name_and_institute[(k, d["institute_id"])] = d["id"]

        cur.execute("SELECT id, TRIM(code) AS k FROM direction WHERE code IS NOT NULL")
        direction_by_code = {r["k"]: r["id"] for r in cur.fetchall() if r["k"]}

        cur.execute("SELECT id, pair_number, building FROM timeslot")
        timeslot_rows = cur.fetchall()
        timeslot_by_pair_building = {}
        buildings_in_timeslot = set()
        for t in timeslot_rows:
            b = t["building"] or ""
            buildings_in_timeslot.add(b)
            timeslot_by_pair_building[(t["pair_number"], b)] = t["id"]
        # также для NULL building: (pair_number, None) -> id (если один слот на пару)
        for t in timeslot_rows:
            if t["building"] is None:
                timeslot_by_pair_building[(t["pair_number"], None)] = t["id"]

        cur.execute("SELECT id, name FROM student_group")
        group_by_name = {r["name"]: r["id"] for r in cur.fetchall()}

    # ——— Читаем schedule батчами ———
    cols = [
        "day_of_week", "pair_number", "subject_name", "lecture_type", "audience",
        "group_name", "week_type", "subgroup", "institute", "course", "direction",
        "department", "is_external", "is_remote", "num_subgroups", "fio",
    ]
    if has_duration_pairs:
        cols.append("duration_pairs")
    cols_sql = ", ".join(cols)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(f"SELECT {cols_sql} FROM schedule")
        schedule_rows = cur.fetchall()

    stats["schedule_rows"] = len(schedule_rows)

    # ——— Обновления teacher.is_external (собираем уникальные (fio, is_external)) ———
    teacher_updates = {}
    for row in schedule_rows:
        fio_n = _nl(row.get("fio"))
        if not fio_n:
            continue
        is_ext = row.get("is_external")
        if is_ext is None:
            continue
        if fio_n not in teacher_by_fio:
            continue
        teacher_updates[fio_n] = bool(is_ext)

    if teacher_updates:
        teacher_update_list = [(bool(is_ext), teacher_by_fio[fio_n]) for fio_n, is_ext in teacher_updates.items()]
        with conn.cursor() as cur:
            cur.executemany("UPDATE teacher SET is_external = %s WHERE id = %s", teacher_update_list)
            stats["teacher_updated"] = len(teacher_update_list)
        conn.commit()

    # ——— Группы: уникальные по (name, institute_id, direction_id, department_id, course) ———
    groups_to_insert = []
    seen_group_key = set()

    for row in schedule_rows:
        name = _n(row.get("group_name"))
        if not name:
            continue
        if name in group_by_name:
            continue
        inst_id = None
        inst_n = _nl(row.get("institute"))
        if inst_n:
            inst_id = institute_by_name.get(inst_n)

        dept_id = None
        dept_n = _nl(row.get("department"))
        if dept_n:
            if inst_id is not None:
                dept_id = department_by_name_and_institute.get((dept_n, inst_id))
            if dept_id is None:
                dept_id = department_by_name.get(dept_n)

        dir_id = None
        code = direction_code_from_string(row.get("direction"))
        if code:
            dir_id = direction_by_code.get(code)

        course = course_to_int(row.get("course"))
        if course is None:
            course = 1

        key = (name, inst_id, dir_id, dept_id, course)
        if key in seen_group_key:
            continue
        seen_group_key.add(key)
        groups_to_insert.append((name, inst_id, dir_id, dept_id, course))

    if groups_to_insert:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """INSERT INTO student_group (name, institute_id, direction_id, department_id, course)
                   VALUES %s
                   ON CONFLICT (name) DO NOTHING""",
                groups_to_insert,
                page_size=len(groups_to_insert),
            )
            stats["student_group_inserted"] = cur.rowcount
        conn.commit()

    # Обновить кэш group_by_name для вставленных
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id, name FROM student_group")
        group_by_name = {r["name"]: r["id"] for r in cur.fetchall()}

    # ——— Строим строки schedule_override ———
    override_rows = []
    for row in schedule_rows:
        weekday = weekday_to_int(row.get("day_of_week"))
        if weekday is None:
            stats["skipped"] += 1
            stats["errors"].append("weekday: не распознан день недели")
            continue

        group_name = _n(row.get("group_name"))
        group_id = group_by_name.get(group_name) if group_name else None

        teacher_id = None
        fio_n = _nl(row.get("fio"))
        if fio_n:
            teacher_id = teacher_by_fio.get(fio_n)

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

        subgroup_count = None
        try:
            v = row.get("subgroup")
            if v is not None:
                subgroup_count = int(v)
        except (ValueError, TypeError):
            pass

        subgroup_no = None
        try:
            v = row.get("num_subgroups")
            if v is not None:
                subgroup_no = int(v)
        except (ValueError, TypeError):
            pass

        duration_pairs = None
        if has_duration_pairs and row.get("duration_pairs") is not None:
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
            stats["errors"].append("timeslot_no: не указан номер пары (pair_number)")
            continue

        building = building_from_audience(row.get("audience"))
        building_str = (building or "").strip() or ""
        building_key = (pair_number, building_str) if building_str else (pair_number, "")

        timeslot_exists = timeslot_by_pair_building.get(building_key) is not None
        if not timeslot_exists and building_str:
            timeslot_exists = timeslot_by_pair_building.get((pair_number, "")) is not None

        if not timeslot_exists and building_str in buildings_in_timeslot:
            # Здание известно в timeslot, но комбинация (здание, номер пары) не найдена
            if strict:
                stats["skipped"] += 1
                stats["errors"].append(
                    f"timeslot: корпус '{building_str}', пара {pair_number} не найден"
                )
                continue
            else:
                stats["skipped"] += 1
                continue

        override_rows.append(
            (
                group_id,
                weekday,
                week_type,
                class_type,
                pair_number,
                subgroup_count,
                subgroup_no,
                subject_id,
                semester_id,
                teacher_id,
                room_id,
                is_remote,
                duration_pairs,
            )
        )

    if dedupe:
        override_rows = list({r: None for r in override_rows}.keys())

    if not override_rows:
        logging.info("Нет строк для вставки в schedule_override")
        return stats

    with conn.cursor() as cur:
        execute_values(
            cur,
            """INSERT INTO schedule_override
               (group_id, weekday, week_type, class_type, timeslot_no, subgroup_count, subgroup_no,
                subject_id, semester_id, teacher_id, room_id, is_remote, duration_pairs)
               VALUES %s""",
            override_rows,
            page_size=BATCH_SIZE,
        )
        stats["schedule_override_inserted"] = len(override_rows)
    conn.commit()

    return stats


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Миграция schedule -> student_group, schedule_override, teacher.is_external")
    parser.add_argument("--semester-id", type=int, required=True, help="ID семестра для schedule_override.semester_id")
    parser.add_argument("--clean", action="store_true", help="Очистить schedule_override и student_group перед миграцией")
    parser.add_argument("--dedupe", action="store_true", help="Удалить точные дубликаты перед вставкой в schedule_override")
    parser.add_argument("--strict", action="store_true", help="Строгий режим: ошибка при отсутствии timeslot в известном корпусе")
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False

    has_duration_pairs = False
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'schedule' AND column_name = 'duration_pairs'
        """)
        has_duration_pairs = cur.fetchone() is not None

    try:
        stats = run(
            conn,
            semester_id=args.semester_id,
            clean=args.clean,
            dedupe=args.dedupe,
            strict=args.strict,
            has_duration_pairs=has_duration_pairs,
        )
        logging.info("Обработано строк в schedule: %s", stats["schedule_rows"])
        logging.info("Вставлено в student_group: %s", stats["student_group_inserted"])
        logging.info("Вставлено в schedule_override: %s", stats["schedule_override_inserted"])
        logging.info("Обновлено teacher.is_external: %s", stats["teacher_updated"])
        logging.info("Пропущено строк: %s", stats["skipped"])
        if stats["errors"]:
            for e in stats["errors"][:20]:
                logging.warning("  %s", e)
            if len(stats["errors"]) > 20:
                logging.warning("  ... и ещё %s", len(stats["errors"]) - 20)
        print("\nИтог: schedule=%s, student_group +%s, schedule_override +%s, teacher updated %s, skipped %s" % (
            stats["schedule_rows"],
            stats["student_group_inserted"],
            stats["schedule_override_inserted"],
            stats["teacher_updated"],
            stats["skipped"],
        ))
    except Exception as e:
        conn.rollback()
        logging.exception("%s", e)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
