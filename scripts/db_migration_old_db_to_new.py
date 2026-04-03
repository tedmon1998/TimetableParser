#!/usr/bin/env python3
"""
Миграция данных из старой таблицы schedule в новую схему PostgreSQL.

Разрешено только:
  - INSERT в student_group (группы по sg.name UNIQUE);
  - INSERT в schedule_override;
  - UPDATE teacher.is_external.

Остальные справочники не создаются — ID ищутся по существующим данным.

Использование:
  python db_migration_old_db_to_new.py --semester-id 1 [--clean] [--dedupe] [--strict] [--log-sample N] [--report-file PATH]
"""

import argparse
import json
import logging
import os
import re
import sys
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
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


class _FlushStreamHandler(logging.StreamHandler):
    """stdout + flush после каждой записи — логи сразу видны в терминале (без буфера)."""

    def emit(self, record):
        super().emit(record)
        self.flush()


def _configure_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    h = _FlushStreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(h)
    _stdout_rc = getattr(sys.stdout, "reconfigure", None)
    if callable(_stdout_rc):
        try:
            _stdout_rc(line_buffering=True)
        except (OSError, ValueError):
            pass
    _stderr_rc = getattr(sys.stderr, "reconfigure", None)
    if callable(_stderr_rc):
        try:
            _stderr_rc(line_buffering=True)
        except (OSError, ValueError):
            pass


def _diag_print(msg: str) -> None:
    """
    Прямой вывод в терминал через stderr (без буфера у TTY).
    Скрипт миграции не связан с npm/backend — запускайте: python scripts/db_migration_old_db_to_new.py
    """
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def _n(s):
    return (s or "").strip() or None


def _nl(s):
    """Normalize for lookup: trim + lower."""
    v = _n(s)
    return v.lower() if v else None


def _initials_key(s):
    """Нормализует ФИО к виду 'фамилия ио' для сопоставления кратких/полных вариантов."""
    v = _n(s)
    if not v:
        return None
    v = re.sub(r"[.,]", " ", v.lower())
    parts = [p for p in re.split(r"\s+", v) if p]
    if not parts:
        return None
    # Убираем служебный префикс вида "с." / "ст." перед ФИО, если он есть.
    while len(parts) > 1 and len(parts[0]) <= 2:
        parts.pop(0)
    if not parts:
        return None
    surname = parts[0]
    initials = "".join(p[0] for p in parts[1:] if p)
    return f"{surname} {initials}".strip()


def _resolve_teacher_detail(raw_fio, teacher_by_fio, teacher_by_initials):
    """
    Возвращает (teacher_id | None, reason).
    reason: exact | initials_unique | empty_fio | no_initials_key | ambiguous_initials | no_match
    """
    if not _n(raw_fio):
        return None, "empty_fio"
    fio_n = _nl(raw_fio)
    if fio_n in teacher_by_fio:
        return teacher_by_fio[fio_n], "exact"
    ik = _initials_key(raw_fio)
    if not ik:
        return None, "no_initials_key"
    ids = teacher_by_initials.get(ik) or []
    if len(ids) == 1:
        return ids[0], "initials_unique"
    if len(ids) > 1:
        return None, f"ambiguous_initials:{len(ids)}"
    return None, "no_match"


def _resolve_teacher_id(raw_fio, teacher_by_fio, teacher_by_initials):
    """Ищет teacher.id сначала по точному ФИО, затем по сокращению Фамилия+ИО (только если однозначно)."""
    tid, _ = _resolve_teacher_detail(raw_fio, teacher_by_fio, teacher_by_initials)
    return tid


def _resolve_subject_detail(subject_name, subject_by_name):
    """Возвращает (subject_id | None, reason): exact | empty | not_in_subject."""
    if not _n(subject_name):
        return None, "empty"
    sn = _nl(subject_name)
    if sn in subject_by_name:
        return subject_by_name[sn], "exact"
    return None, "not_in_subject"


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


def _table_exists(conn, table_name: str) -> bool:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table_name,),
        )
        return cur.fetchone() is not None


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
            """,
            (table_name, column_name),
        )
        return cur.fetchone() is not None


def _ordered_table_columns(conn, table_name: str) -> list[str]:
    """Все колонки таблицы в порядке ordinal_position (полная строка для отчёта)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table_name,),
        )
        return [r[0] for r in cur.fetchall()]


def _positive_int_or_none(v):
    """Целое > 0 или None. В schedule значение 0 у num_subgroups чаще значит «не заполнено», а не «0 п/г»."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, str) and not v.strip():
        return None
    try:
        if isinstance(v, Decimal):
            n = int(v)
        else:
            n = int(Decimal(str(v)))
    except (ArithmeticError, TypeError, ValueError):
        try:
            n = int(v)
        except (TypeError, ValueError):
            return None
    return n if n > 0 else None


def _fmt_report_cell(v) -> str:
    if v is None:
        return ""
    s = str(v).replace("\r", " ").replace("\n", " ")
    return s.replace("\t", " ")


def _json_cell(v):
    """Значение для JSON-отчёта (веб-таблица)."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, int) and not isinstance(v, bool):
        return v
    if isinstance(v, float):
        return v
    if isinstance(v, str):
        return v
    if isinstance(v, Decimal):
        return int(v) if v % 1 == 0 else float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return str(v)


def _build_migration_report_rows(
    row_meta: list[dict],
    inserted_override_ids: list,
    so_columns: list[str],
    override_rows: list[tuple],
    schedule_override_teacher_exists: bool,
    schedule_override_has_teacher: bool,
) -> list[dict]:
    """Плоские строки для веб-таблицы (как просмотр расписания в БД)."""
    rows_out = []
    n = len(row_meta)
    for i in range(n):
        meta = row_meta[i]
        soid = inserted_override_ids[i]
        ov = dict(zip(so_columns, override_rows[i]))
        snap = meta.get("schedule_snapshot") or {}
        tid = meta.get("teacher_id")
        row = {
            "schedule_id": _json_cell(snap.get("id")),
            "schedule_override_id": soid,
            "day_of_week": _json_cell(snap.get("day_of_week")),
            "pair_number": _json_cell(snap.get("pair_number")),
            "subject_name": _json_cell(snap.get("subject_name")),
            "lecture_type": _json_cell(snap.get("lecture_type")),
            "audience": _json_cell(snap.get("audience")),
            "duration_pairs": _json_cell(snap.get("duration_pairs")),
            "group_name": _json_cell(snap.get("group_name")),
            "week_type": _json_cell(snap.get("week_type")),
            "fio": _json_cell(snap.get("fio")),
            "subgroup": _json_cell(snap.get("subgroup")),
            "institute": _json_cell(snap.get("institute")),
            "course": _json_cell(snap.get("course")),
            "direction": _json_cell(snap.get("direction")),
            "department": _json_cell(snap.get("department")),
            "subject_id": _json_cell(meta.get("subject_id")),
            "teacher_id": _json_cell(tid),
            "teacher_fio_db": _json_cell(meta.get("resolved_teacher_fio")),
            "teacher_reason": meta.get("teacher_reason"),
            "subject_reason": meta.get("subject_reason"),
            "ov_group_id": _json_cell(ov.get("group_id")),
            "ov_weekday": _json_cell(ov.get("weekday")),
            "ov_week_type": _json_cell(ov.get("week_type")),
            "ov_class_type": _json_cell(ov.get("class_type")),
            "ov_timeslot_no": _json_cell(ov.get("timeslot_no")),
            "ov_subgroup_count": _json_cell(ov.get("subgroup_count")),
            "ov_subgroup_no": _json_cell(ov.get("subgroup_no")),
            "ov_subject_id": _json_cell(ov.get("subject_id")),
            "ov_teacher_id": _json_cell(ov.get("teacher_id")) if schedule_override_has_teacher else None,
            "sot_will_link": bool(
                tid is not None and schedule_override_teacher_exists
            ),
        }
        rows_out.append(row)
    return rows_out


def _write_migration_report_json(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def _write_migration_report_stream(
    path: Path,
    *,
    schedule_cols: list[str],
    row_meta: list[dict],
    inserted_override_ids: list,
    so_columns: list[str],
    override_rows: list[tuple],
    schedule_override_teacher_exists: bool,
) -> None:
    """Весь отчёт в файл — один проход; в терминал не пишет (не замедляет миграцию)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("=" * 80 + "\n")
        f.write("ОТЧЁТ: schedule -> schedule_override / schedule_override_teacher\n")
        f.write("\n")
        f.write("ФИО для teacher_id: только колонка schedule.fio -> сопоставление с таблицей teacher (id, fio).\n")
        f.write("Таблица timetable_teacher в этой миграции НЕ используется.\n")
        f.write("\n")
        n = len(row_meta)
        for i in range(n):
            meta = row_meta[i]
            soid = inserted_override_ids[i]
            ov = override_rows[i]
            ov = dict(zip(so_columns, ov))
            snap = meta.get("schedule_snapshot") or {}
            f.write("-" * 80 + "\n")
            f.write(f"Запись {i + 1} / {n}\n")
            f.write("\n")
            f.write("[schedule] исходная строка (колонки -> значения, табуляция):\n")
            f.write("\t".join(schedule_cols) + "\n")
            f.write("\t".join(_fmt_report_cell(snap.get(c)) for c in schedule_cols) + "\n")
            f.write("\n")
            f.write("[schedule_override] вставка:\n")
            for k in so_columns:
                f.write(f"  {k}: {ov.get(k)!r}\n")
            f.write(f"  (сгенерированный id) schedule_override.id = {soid!r}\n")
            f.write("\n")
            f.write("[schedule_override_teacher]:\n")
            tid = meta.get("teacher_id")
            if tid is not None and schedule_override_teacher_exists:
                f.write(f"  INSERT: (schedule_override_id={soid}, teacher_id={tid}, sort_order=1)\n")
            elif tid is None:
                f.write("  (нет строки: teacher_id не найден по schedule.fio)\n")
            else:
                f.write("  (таблица schedule_override_teacher отсутствует в схеме)\n")
            f.write("\n")
            f.write("[teacher] справочник (по schedule.fio) — не timetable_teacher:\n")
            f.write(f"  schedule.fio: {meta.get('fio')!r}\n")
            f.write(f"  teacher.id: {tid!r}\n")
            f.write(f"  teacher.fio в БД (как в справочнике): {meta.get('resolved_teacher_fio')!r}\n")
            f.write(f"  причина сопоставления: {meta.get('teacher_reason')}\n")
            f.write("\n")
            f.write("[subject]:\n")
            f.write(f"  schedule.subject_name: {meta.get('subject_name')!r}\n")
            f.write(f"  subject_id: {meta.get('subject_id')!r} ({meta.get('subject_reason')})\n")
            f.write("\n")


def run(
    conn,
    semester_id: int,
    clean: bool,
    dedupe: bool,
    strict: bool,
    clean_override_only: bool = False,
    log_sample: int = 30,
    log_all_teachers: bool = False,
    report_file: str | None = None,
):
    stats = {
        "schedule_rows": 0,
        "student_group_inserted": 0,
        "schedule_override_inserted": 0,
        "schedule_override_teacher_inserted": 0,
        "teacher_updated": 0,
        "skipped": 0,
        "errors": [],
        "report_file": None,
    }

    student_group_has_institute = _column_exists(conn, "student_group", "institute_id")
    student_group_has_department = _column_exists(conn, "student_group", "department_id")
    schedule_override_has_teacher = _column_exists(conn, "schedule_override", "teacher_id")
    schedule_override_teacher_exists = _table_exists(conn, "schedule_override_teacher")

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # ——— Очистка (опционально) ———
        if clean or clean_override_only:
            deleted_sot = 0
            deleted_so = 0
            deleted_sg = 0

            # для новой схемы: сначала явно очищаем связи преподавателей в override
            if schedule_override_teacher_exists:
                cur.execute("DELETE FROM schedule_override_teacher")
                deleted_sot = cur.rowcount
                cur.execute(
                    "SELECT setval(pg_get_serial_sequence(%s, %s), 1, false)",
                    ("schedule_override_teacher", "id"),
                )

            # всегда очищаем schedule_override, если включён любой режим очистки
            cur.execute("DELETE FROM schedule_override")
            deleted_so = cur.rowcount
            cur.execute(
                "SELECT setval(pg_get_serial_sequence(%s, %s), 1, false)",
                ("schedule_override", "id"),
            )

            # при полном clean дополнительно очищаем student_group
            if clean:
                cur.execute("DELETE FROM student_group")
                deleted_sg = cur.rowcount
                cur.execute(
                    "SELECT setval(pg_get_serial_sequence(%s, %s), 1, false)",
                    ("student_group", "id"),
                )

            conn.commit()
            logging.info(
                "Очистка: удалено schedule_override_teacher=%s, schedule_override=%s, student_group=%s",
                deleted_sot,
                deleted_so,
                deleted_sg,
            )

        # ——— Справочники: загрузить в память ———
        cur.execute("SELECT id, fio, LOWER(TRIM(fio)) AS k FROM teacher")
        teacher_rows = cur.fetchall()
        teacher_by_fio = {r["k"]: r["id"] for r in teacher_rows if r["k"]}
        teacher_by_initials = {}
        for r in teacher_rows:
            ik = _initials_key(r.get("fio"))
            if not ik:
                continue
            teacher_by_initials.setdefault(ik, [])
            teacher_by_initials[ik].append(r["id"])

        teacher_id_to_fio = {r["id"]: r.get("fio") for r in teacher_rows}

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

    # ——— Читаем источник для миграции (строго schedule) ———
    source_table = "schedule"
    if not _table_exists(conn, source_table):
        raise RuntimeError("Таблица schedule не найдена. Для этой миграции обязателен источник schedule.")

    logging.info("Источник миграции: %s", source_table)
    schedule_cols = _ordered_table_columns(conn, source_table)
    if not schedule_cols:
        raise RuntimeError(f"Таблица {source_table}: нет колонок в information_schema")
    select_sql = ", ".join(f'"{c}"' for c in schedule_cols)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(f"SELECT {select_sql} FROM {source_table}")
        schedule_rows = cur.fetchall()

    stats["schedule_rows"] = len(schedule_rows)
    _diag_print(f"[миграция] Источник: таблица {source_table!r}, загружено строк: {stats['schedule_rows']}")

    # ——— Обновления teacher.is_external (собираем уникальные (fio, is_external)) ———
    teacher_updates = {}
    for row in schedule_rows:
        fio_src = row.get("fio")
        fio_n = _nl(fio_src)
        if not fio_n:
            continue
        is_ext = row.get("is_external")
        if is_ext is None:
            continue
        teacher_id = _resolve_teacher_id(fio_src, teacher_by_fio, teacher_by_initials)
        if teacher_id is None:
            continue
        teacher_updates[teacher_id] = bool(is_ext)

    if teacher_updates:
        teacher_update_list = [(bool(is_ext), teacher_id) for teacher_id, is_ext in teacher_updates.items()]
        with conn.cursor() as cur:
            cur.executemany("UPDATE teacher SET is_external = %s WHERE id = %s", teacher_update_list)
            stats["teacher_updated"] = len(teacher_update_list)
        conn.commit()

    # ——— Группы: UNIQUE по name, остальные поля — если есть в текущей схеме ———
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

        key_parts = [name, dir_id, course]
        if student_group_has_institute:
            key_parts.append(inst_id)
        if student_group_has_department:
            key_parts.append(dept_id)
        key = tuple(key_parts)
        if key in seen_group_key:
            continue
        seen_group_key.add(key)
        row_values = [name]
        if student_group_has_institute:
            row_values.append(inst_id)
        row_values.append(dir_id)
        if student_group_has_department:
            row_values.append(dept_id)
        row_values.append(course)
        groups_to_insert.append(tuple(row_values))

    if groups_to_insert:
        sg_columns = ["name"]
        if student_group_has_institute:
            sg_columns.append("institute_id")
        sg_columns.append("direction_id")
        if student_group_has_department:
            sg_columns.append("department_id")
        sg_columns.append("course")
        cols_sql = ", ".join(sg_columns)
        with conn.cursor() as cur:
            execute_values(
                cur,
                f"""INSERT INTO student_group ({cols_sql})
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
    teacher_ids = []
    row_meta = []
    for row in schedule_rows:
        weekday = weekday_to_int(row.get("day_of_week"))
        if weekday is None:
            stats["skipped"] += 1
            stats["errors"].append("weekday: не распознан день недели")
            continue

        group_name = _n(row.get("group_name"))
        group_id = group_by_name.get(group_name) if group_name else None

        fio_src = row.get("fio")
        teacher_id, teacher_reason = _resolve_teacher_detail(fio_src, teacher_by_fio, teacher_by_initials)

        subject_id, subject_reason = _resolve_subject_detail(row.get("subject_name"), subject_by_name)

        week_type = parse_week_type(row.get("week_type")) or "обе недели"
        class_type = parse_class_type(row.get("lecture_type")) or "лекция"

        room_id = None
        aud_n = _nl(row.get("audience"))
        if aud_n:
            room_id = room_by_name.get(aud_n)

        # subgroup_count / subgroup_no из schedule (num_subgroups / subgroup)
        subgroup_count = _positive_int_or_none(row.get("num_subgroups"))
        subgroup_no = _positive_int_or_none(row.get("subgroup"))
        # Если задан номер п/г — в группе минимум две п/г (иначе номер «1» бессмысленен): count >= max(no, 2)
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
            tuple(
                [
                    group_id,
                    weekday,
                    week_type,
                    class_type,
                    pair_number,
                    subgroup_count,
                    subgroup_no,
                    subject_id,
                    semester_id,
                ]
                + ([teacher_id] if schedule_override_has_teacher else [])
                + [room_id, is_remote, duration_pairs]
            )
        )
        teacher_ids.append(teacher_id)
        row_meta.append(
            {
                "schedule_row_id": row.get("id"),
                "schedule_snapshot": dict(row),
                "fio": fio_src,
                "fio_source": "schedule.fio",
                "subject_name": row.get("subject_name"),
                "teacher_sched_col": row.get("teacher"),
                "teacher_reason": teacher_reason,
                "subject_reason": subject_reason,
                "teacher_id": teacher_id,
                "subject_id": subject_id,
                "resolved_teacher_fio": teacher_id_to_fio.get(teacher_id) if teacher_id is not None else None,
            }
        )

    if dedupe:
        seen = set()
        deduped_rows = []
        deduped_teacher_ids = []
        deduped_meta = []
        for r, tid, meta in zip(override_rows, teacher_ids, row_meta):
            if r in seen:
                continue
            seen.add(r)
            deduped_rows.append(r)
            deduped_teacher_ids.append(tid)
            deduped_meta.append(meta)
        override_rows = deduped_rows
        teacher_ids = deduped_teacher_ids
        row_meta = deduped_meta

    if not override_rows:
        logging.info("Нет строк для вставки в schedule_override")
        _diag_print(
            "[миграция] Нет строк для schedule_override (все отфильтрованы: weekday/timeslot/pair_number и т.д.). "
            "Смотрите stats['errors'] / skipped в конце."
        )
        return stats

    so_columns = [
        "group_id", "weekday", "week_type", "class_type", "timeslot_no", "subgroup_count", "subgroup_no",
        "subject_id", "semester_id"
    ]
    if schedule_override_has_teacher:
        so_columns.append("teacher_id")
    so_columns.extend(["room_id", "is_remote", "duration_pairs"])
    so_cols_sql = ", ".join(so_columns)

    insert_sql = f"""INSERT INTO schedule_override
                ({so_cols_sql})
               VALUES %s
               RETURNING id"""
    inserted_override_ids = []
    with conn.cursor() as cur:
        for i in range(0, len(override_rows), BATCH_SIZE):
            batch = override_rows[i : i + BATCH_SIZE]
            execute_values(cur, insert_sql, batch, page_size=len(batch))
            inserted_override_ids.extend(r[0] for r in cur.fetchall())
        stats["schedule_override_inserted"] = len(override_rows)

    if len(inserted_override_ids) != len(override_rows):
        logging.error(
            "КРИТИЧНО: RETURNING id (%s) != числу вставленных строк (%s) — связи schedule_override_teacher будут неверны.",
            len(inserted_override_ids),
            len(override_rows),
        )
    elif len(inserted_override_ids) != len(teacher_ids):
        logging.error(
            "КРИТИЧНО: teacher_ids (%s) != schedule_override строк (%s).",
            len(teacher_ids),
            len(override_rows),
        )

    tr_cnt = Counter(m["teacher_reason"] for m in row_meta)
    sr_cnt = Counter(m["subject_reason"] for m in row_meta)
    no_teacher_but_fio = sum(1 for m in row_meta if _n(m.get("fio")) and m["teacher_id"] is None)
    no_subject_but_name = sum(1 for m in row_meta if _n(m.get("subject_name")) and m["subject_id"] is None)
    logging.info("Сопоставление teacher (причины): %s", dict(tr_cnt))
    logging.info("Сопоставление subject (причины): %s", dict(sr_cnt))
    logging.info(
        "Строк с fio, но без teacher_id: %s; с subject_name, но без subject_id: %s",
        no_teacher_but_fio,
        no_subject_but_name,
    )

    if report_file:
        _diag_print(
            f"[миграция] Кратко: строк в отчёте {len(row_meta)}; "
            f"teacher: {dict(tr_cnt)}; subject: {dict(sr_cnt)}"
        )

    if not report_file:
        _diag_print("--- Сводка сопоставления (teacher / subject) ---")
        _diag_print(f"  teacher по причинам: {dict(tr_cnt)}")
        _diag_print(f"  subject по причинам: {dict(sr_cnt)}")
        _diag_print(
            f"  есть fio в schedule.fio, но teacher_id не найден: {no_teacher_but_fio}; "
            f"есть subject_name, но subject_id не найден: {no_subject_but_name}"
        )
        _diag_print(
            "  ФИО для teacher_id берётся только из колонки schedule.fio (не из названия дисциплины). "
            "Колонка schedule.teacher ниже — только для сравнения, в маппинг не идёт."
        )

    max_n = min(len(inserted_override_ids), len(row_meta))
    if log_all_teachers:
        n_stderr = max_n
    else:
        n_stderr = min(log_sample, max_n)
    if not report_file and n_stderr > 0:
        cap = f"все {n_stderr} строк" if log_all_teachers else f"первые {n_stderr} строк"
        _diag_print(f"--- {cap.capitalize()}: дисциплина -> ФИО (источник) -> teacher_id ---")
        logging.info("--- %s сопоставлений (schedule_row_id -> schedule_override_id): ---", cap)
        for i in range(n_stderr):
            m = row_meta[i]
            soid = inserted_override_ids[i]
            sn = (m.get("subject_name") or "")
            if len(sn) > 120:
                sn = sn[:120] + "…"
            t_sched = m.get("teacher_sched_col")
            t_sched_note = ""
            if t_sched is not None and _n(str(t_sched)):
                t_sched_note = f"\n  schedule.teacher (справочно, не для маппинга): {t_sched!r}"
            block = (
                f"[{i + 1}/{n_stderr}] schedule_row_id={m.get('schedule_row_id')} -> schedule_override_id={soid}\n"
                f"  дисциплина (schedule.subject_name): {sn!r}\n"
                f"  ФИО для маппинга из {m.get('fio_source')}: {m.get('fio')!r}{t_sched_note}\n"
                f"  -> teacher_id={m.get('teacher_id')} ({m.get('teacher_reason')}); "
                f"subject_id={m.get('subject_id')} ({m.get('subject_reason')})"
            )
            _diag_print(block)
            logging.info(
                "[%s] schedule_row_id=%s -> schedule_override_id=%s | fio=%r -> teacher_id=%s (%s) | subject=%r -> subject_id=%s (%s)",
                i + 1,
                m.get("schedule_row_id"),
                soid,
                m.get("fio"),
                m.get("teacher_id"),
                m.get("teacher_reason"),
                sn,
                m.get("subject_id"),
                m.get("subject_reason"),
            )

    if schedule_override_teacher_exists:
        teacher_links = [
            (so_id, t_id, 1)
            for so_id, t_id in zip(inserted_override_ids, teacher_ids)
            if t_id is not None
        ]
        if teacher_links:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO schedule_override_teacher (schedule_override_id, teacher_id, sort_order)
                       VALUES %s
                       ON CONFLICT (schedule_override_id, teacher_id) DO NOTHING""",
                    teacher_links,
                    page_size=BATCH_SIZE,
                )
            stats["schedule_override_teacher_inserted"] = len(teacher_links)
    conn.commit()

    if report_file and row_meta:
        rp = Path(report_file).expanduser()
        _write_migration_report_stream(
            rp,
            schedule_cols=schedule_cols,
            row_meta=row_meta,
            inserted_override_ids=inserted_override_ids,
            so_columns=so_columns,
            override_rows=override_rows,
            schedule_override_teacher_exists=schedule_override_teacher_exists,
        )
        stats["report_file"] = str(rp.resolve())
        report_rows = _build_migration_report_rows(
            row_meta,
            inserted_override_ids,
            so_columns,
            override_rows,
            schedule_override_teacher_exists,
            schedule_override_has_teacher,
        )
        json_path = rp.with_suffix(".json")
        _write_migration_report_json(json_path, report_rows)
        stats["report_json"] = str(json_path.resolve())

    return stats


def main():
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            _rc = getattr(stream, "reconfigure", None)
            if callable(_rc):
                try:
                    _rc(encoding="utf-8", errors="replace")
                except (OSError, ValueError):
                    pass
    _configure_logging()
    _diag_print(
        "Миграция БД: отдельный скрипт Python (не окно npm/backend). "
        "Запуск: python scripts/db_migration_old_db_to_new.py --semester-id N"
    )
    parser = argparse.ArgumentParser(description="Миграция schedule -> student_group, schedule_override, teacher.is_external")
    parser.add_argument("--semester-id", type=int, required=True, help="ID семестра для schedule_override.semester_id")
    parser.add_argument("--clean", action="store_true", help="Очистить schedule_override и student_group перед миграцией")
    parser.add_argument("--clean-override-only", action="store_true", help="Очистить только schedule_override перед миграцией")
    parser.add_argument("--dedupe", action="store_true", help="Удалить точные дубликаты перед вставкой в schedule_override")
    parser.add_argument("--strict", action="store_true", help="Строгий режим: ошибка при отсутствии timeslot в известном корпусе")
    _env_log = os.environ.get("MIGRATION_LOG_SAMPLE", "30")
    try:
        _default_log_sample = max(0, int(_env_log))
    except ValueError:
        _default_log_sample = 30
    parser.add_argument(
        "--log-sample",
        type=int,
        default=_default_log_sample,
        help="Сколько первых строк вывести в лог (fio/subject/ids); 0 — только сводки Counter. Env: MIGRATION_LOG_SAMPLE",
    )
    parser.add_argument(
        "--log-all-teachers",
        action="store_true",
        help="Вывести сопоставление fio->teacher_id для каждой строки schedule_override (очень много текста в stderr)",
    )
    parser.add_argument(
        "--report-file",
        type=str,
        default=None,
        metavar="PATH",
        help="Полный отчёт по всем строкам в UTF-8 файл (колонки schedule, override, teacher из справочника). Не дублирует объём в терминал.",
    )
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False

    try:
        stats = run(
            conn,
            semester_id=args.semester_id,
            clean=args.clean,
            dedupe=args.dedupe,
            strict=args.strict,
            clean_override_only=args.clean_override_only,
            log_sample=max(0, args.log_sample),
            log_all_teachers=args.log_all_teachers,
            report_file=args.report_file,
        )
        logging.info("Обработано строк в schedule: %s", stats["schedule_rows"])
        logging.info("Вставлено в student_group: %s", stats["student_group_inserted"])
        logging.info("Вставлено в schedule_override: %s", stats["schedule_override_inserted"])
        logging.info("Вставлено в schedule_override_teacher: %s", stats["schedule_override_teacher_inserted"])
        logging.info("Обновлено teacher.is_external: %s", stats["teacher_updated"])
        logging.info("Пропущено строк: %s", stats["skipped"])
        if stats["errors"]:
            for e in stats["errors"][:20]:
                logging.warning("  %s", e)
            if len(stats["errors"]) > 20:
                logging.warning("  ... и ещё %s", len(stats["errors"]) - 20)
        if stats.get("report_file"):
            _diag_print(f"Полный отчёт: {stats['report_file']}")
        print(
            "\nИтог: schedule=%s, student_group +%s, schedule_override +%s, schedule_override_teacher +%s, teacher updated %s, skipped %s"
            % (
                stats["schedule_rows"],
                stats["student_group_inserted"],
                stats["schedule_override_inserted"],
                stats["schedule_override_teacher_inserted"],
                stats["teacher_updated"],
                stats["skipped"],
            ),
            flush=True,
        )
    except Exception as e:
        conn.rollback()
        logging.exception("%s", e)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
