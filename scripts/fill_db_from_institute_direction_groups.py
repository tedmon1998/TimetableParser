#!/usr/bin/env python3
"""
Очистка данных и заполнение справочников и timeslot.
Ничего не дропает — только TRUNCATE (очистка строк) и вставка. Таблицы и БД не трогаем.

  Очищает (TRUNCATE): semester, institute, direction, teacher, room, subject и связанные.
  timeslot не очищаем — только вставляем/обновляем пары.

  Заполняет:
  timeslot   — расписание пар (как в scripts/asd.ts PAIR_TIMES)
  semester   — одна запись по умолчанию
  institute, direction — из output/institute_direction_groups.json
  teacher    — из info/teacher_all.json
  room       — из info/aud.json (building = первая буква названия)
  subject    — из info/discipline.json
"""

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
    from psycopg2.extras import RealDictCursor
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

# Как в scripts/asd.ts PAIR_TIMES (корпуса А, Г, К, У)
TIMESLOT_DEFAULT = [
    (1, "08:30", "09:50"),
    (2, "10:00", "11:20"),
    (3, "11:30", "12:50"),
    (4, "13:20", "14:40"),
    (5, "14:50", "16:10"),
    (6, "16:20", "17:40"),
    (7, "18:00", "19:20"),
    (8, "19:30", "20:50"),
    (9, "21:00", "22:20"),
]


def _n(s):
    return (s or "").strip() or None


def _direction_code_name(direction_key: str) -> tuple[str | None, str]:
    s = (direction_key or "").strip()
    if not s:
        return None, "—"
    m = re.match(r"^(\d+\.\d+\.\d+)\s+(.+)$", s)
    if m:
        return m.group(1), (m.group(2) or s).strip() or s
    return None, s


def main():
    paths = {
        "institute_direction": PROJECT_ROOT / "output" / "institute_direction_groups.json",
        "teacher": PROJECT_ROOT / "info" / "teacher_all.json",
        "aud": PROJECT_ROOT / "info" / "aud.json",
        "discipline": PROJECT_ROOT / "info" / "discipline.json",
    }
    for name, p in paths.items():
        if not p.exists():
            print(f"Файл не найден: {p}")
            sys.exit(1)

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False

    try:
        # Загрузка JSON
        with open(paths["institute_direction"], "r", encoding="utf-8") as f:
            data_idg = json.load(f)
        with open(paths["teacher"], "r", encoding="utf-8") as f:
            teachers_raw = json.load(f)
        with open(paths["aud"], "r", encoding="utf-8") as f:
            rooms_raw = json.load(f)
        with open(paths["discipline"], "r", encoding="utf-8") as f:
            subjects_raw = json.load(f)

        institute_names = set()
        direction_keys = set()
        for inst_name, dirs in data_idg.items():
            if not isinstance(dirs, dict):
                continue
            inst_name = _n(inst_name) or "—"
            institute_names.add(inst_name)
            for dir_key in dirs.keys():
                if dir_key == "groups":
                    continue
                code, dname = _direction_code_name(dir_key)
                if code is not None:
                    dname = dname or "—"
                    direction_keys.add((code, dname))

        teacher_fios = set()
        for t in teachers_raw:
            if isinstance(t, dict):
                fio = _n(t.get("fio"))
                if fio:
                    teacher_fios.add(fio)
            elif isinstance(t, str) and _n(t):
                teacher_fios.add(_n(t))

        room_names = set()
        for r in rooms_raw:
            if isinstance(r, str):
                name = _n(r)
                if name:
                    room_names.add(name)
            elif isinstance(r, dict) and r.get("name"):
                room_names.add(_n(r["name"]))

        subject_names = set()
        for s in subjects_raw:
            if isinstance(s, str):
                name = _n(s)
                if name:
                    subject_names.add(name)
            elif isinstance(s, dict) and s.get("name"):
                subject_names.add(_n(s["name"]))

        # Очистить все справочники и связанные таблицы, кроме timeslot (слоты времени не трогаем)
        with conn.cursor() as c:
            c.execute("""
                TRUNCATE
                    schedule_override,
                    schedule_pattern_item,
                    student_group,
                    department,
                    institute,
                    direction,
                    subject,
                    teacher,
                    room,
                    semester
                RESTART IDENTITY CASCADE
            """)
        conn.commit()
        print("Очищены строки (TRUNCATE): semester, institute, direction, teacher, room, subject и связанные. Таблицы и БД не трогаем. timeslot не очищаем.")

        # ——— timeslot (только вставка/обновление, не очищаем) ———
        with conn.cursor() as c:
            for pn, start, end in TIMESLOT_DEFAULT:
                c.execute("""
                    INSERT INTO timeslot (pair_number, time_start, time_end)
                    VALUES (%s, %s::time, %s::time)
                    ON CONFLICT (pair_number) DO UPDATE SET
                        time_start = EXCLUDED.time_start,
                        time_end = EXCLUDED.time_end
                """, (pn, start, end))
        conn.commit()
        print(f"timeslot: {len(TIMESLOT_DEFAULT)} пар (как asd.ts PAIR_TIMES)")

        # ——— semester (одна запись) ———
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("SELECT id FROM semester LIMIT 1")
            if not c.fetchone():
                c.execute("""
                    INSERT INTO semester (name, date_start, date_end)
                    VALUES ('Осенний 2024', '2024-09-01', '2025-01-31')
                """)
        conn.commit()
        print("semester: одна запись по умолчанию")

        # ——— institute ———
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("SELECT id, name FROM institute")
            existing = {r["name"]: r["id"] for r in c.fetchall()}
        with conn.cursor() as c:
            for name in sorted(institute_names):
                if name in existing:
                    continue
                c.execute("INSERT INTO institute (name) VALUES (%s) RETURNING id", (name,))
        conn.commit()
        print(f"institute: из institute_direction_groups.json")

        # ——— direction ———
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("SELECT id, code, name FROM direction")
            existing = {(r["code"], r["name"]): r["id"] for r in c.fetchall()}
        with conn.cursor() as c:
            for (code, dname) in sorted(direction_keys, key=lambda x: (x[0] or "", x[1])):
                if (code, dname) in existing:
                    continue
                c.execute(
                    "INSERT INTO direction (code, name) VALUES (%s, %s) RETURNING id",
                    (code, dname),
                )
        conn.commit()
        print("direction: из institute_direction_groups.json")

        # ——— teacher ———
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("SELECT id, fio FROM teacher")
            existing = {r["fio"]: r["id"] for r in c.fetchall()}
        added = 0
        with conn.cursor() as c:
            for fio in sorted(teacher_fios):
                if fio in existing:
                    continue
                c.execute("INSERT INTO teacher (fio, is_external) VALUES (%s, FALSE) RETURNING id", (fio,))
                added += 1
        conn.commit()
        print(f"teacher: +{added} из info/teacher_all.json")

        # ——— room (building = первая буква) ———
        with conn.cursor() as c:
            c.execute("ALTER TABLE room ADD COLUMN IF NOT EXISTS building VARCHAR(16)")
        conn.commit()
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("SELECT id, name FROM room")
            existing = {r["name"]: r["id"] for r in c.fetchall()}
        added = 0
        with conn.cursor() as c:
            for name in sorted(room_names):
                if name in existing:
                    continue
                remote = "дистант" in (name or "").lower()
                building = (name[0:1] or None) if name else None
                c.execute(
                    "INSERT INTO room (name, building, is_remote_room) VALUES (%s, %s, %s) RETURNING id",
                    (name, building, remote),
                )
                added += 1
        with conn.cursor() as c:
            c.execute("""
                UPDATE room
                SET building = SUBSTRING(TRIM(COALESCE(name, '')) FROM 1 FOR 1)
                WHERE LENGTH(TRIM(COALESCE(name, ''))) > 0
            """)
            updated = c.rowcount
        conn.commit()
        print(f"room: +{added} из info/aud.json, building обновлён у {updated} записей")

        # ——— subject ———
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("SELECT id, name FROM subject")
            existing = {r["name"]: r["id"] for r in c.fetchall()}
        added = 0
        with conn.cursor() as c:
            for name in sorted(subject_names):
                if name in existing:
                    continue
                c.execute("INSERT INTO subject (name) VALUES (%s) RETURNING id", (name,))
                added += 1
        conn.commit()
        print(f"subject: +{added} из info/discipline.json")

        print("Готово: timeslot, semester, institute, direction, teacher, room, subject.")
    except Exception as e:
        conn.rollback()
        print(f"Ошибка: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
