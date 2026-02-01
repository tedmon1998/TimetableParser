#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка: при «лаб» в названии lecture_type должен быть «лабораторная», не «практика»."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parse_timetable_excel import (
    parse_lecture_type,
    _strip_lecture_type_markers,
    normalize_type_slash_for_weeks,
)
from clean_audiences import extract_lecture_type as clean_extract_lecture_type

errors = []

# 1) Прямые вызовы parse_lecture_type
cases = [
    ("Моделирование бизнес-процессов (лаб), К511", "лабораторная"),
    ("Дисциплина (лаб), К511/К518", "лабораторная"),
    ("лаб. работа", "лабораторная"),
    ("лабораторная практика", "лабораторная"),
    ("Лаб работа", "лабораторная"),
    ("Название (лаб), К100", "лабораторная"),
]
for raw, expected in cases:
    got = parse_lecture_type(raw)
    if got != expected:
        errors.append("parse_lecture_type(%r) => %r, expected %r" % (raw, got, expected))

# 2) Как в коде при наличии // (нормализация + разбиение по частям)
raw_discipline = "Моделирование бизнес-процессов (лек)/(лаб), К511/К518"
raw_discipline = raw_discipline.replace("). ", "), ")
raw_discipline = normalize_type_slash_for_weeks(raw_discipline)
if "//" in raw_discipline:
    parts_for_type = [p.strip() for p in raw_discipline.split("//") if p.strip()]
    if len(parts_for_type) >= 2:
        lecture_type = " // ".join(parse_lecture_type(p) for p in parts_for_type)
    else:
        lecture_type = parse_lecture_type(raw_discipline)
else:
    lecture_type = parse_lecture_type(raw_discipline)
if lecture_type != "лекция // лабораторная":
    errors.append("Full pipeline (лек)/(лаб): got %r, expected 'лекция // лабораторная'" % lecture_type)

# 3) Одна часть без // — как в коде
raw_only_lab = "Моделирование бизнес-процессов (лаб), К511"
raw_only_lab = raw_only_lab.replace("). ", "), ")
raw_only_lab = normalize_type_slash_for_weeks(raw_only_lab)
if "//" in raw_only_lab:
    parts_for_type = [p.strip() for p in raw_only_lab.split("//") if p.strip()]
    lecture_type = " // ".join(parse_lecture_type(p) for p in parts_for_type) if len(parts_for_type) >= 2 else parse_lecture_type(raw_only_lab)
else:
    lecture_type = parse_lecture_type(raw_only_lab)
if lecture_type != "лабораторная":
    errors.append("Single part (лаб) pipeline: got %r, expected 'лабораторная'" % lecture_type)

# 4) Название без маркера (лаб)
name_stripped = _strip_lecture_type_markers("Моделирование бизнес-процессов (лаб), К511")
if "(лаб)" in name_stripped or "лаб)" in name_stripped:
    errors.append("_strip_lecture_type_markers should remove (лаб) from name, got: %r" % name_stripped)

# 5) clean_audiences.extract_lecture_type тоже должен возвращать лабораторная при (лаб)
for raw in ("Моделирование бизнес-процессов (лаб), К511", "лабораторная практика", "Дисциплина (лаб)"):
    got = clean_extract_lecture_type(raw)
    if got != "лабораторная":
        errors.append("clean_audiences.extract_lecture_type(%r) => %r, expected 'лабораторная'" % (raw, got))

# 6) clean_audiences: при разбиении по // тип берём из existing_lecture_type (парсер уже убрал (лек)/(лаб) из текста)
from clean_audiences import process_discipline_text
valid = ["К511", "К518"]
text_stripped = "Моделирование бизнес-процессов, К511/К518 // Моделирование бизнес-процессов, К511/К518"
existing_lecture_type = "лекция // лабораторная"
processed = process_discipline_text(text_stripped, valid, None, None, existing_lecture_type)
week_types = [p.get("week_type") for p in processed]
lecture_types = [p.get("lecture_type") for p in processed]
if "числитель" in week_types and "знаменатель" in week_types:
    num_idx = week_types.index("числитель")
    den_idx = week_types.index("знаменатель")
    if lecture_types[num_idx] != "лекция":
        errors.append("clean: numerator lecture_type expected 'лекция', got %r" % lecture_types[num_idx])
    if lecture_types[den_idx] != "лабораторная":
        errors.append("clean: denominator lecture_type expected 'лабораторная', got %r" % lecture_types[den_idx])
else:
    errors.append("clean: expected two rows (числитель + знаменатель), got week_types %r" % week_types)

if errors:
    for e in errors:
        print("FAIL:", e)
    sys.exit(1)
print("OK: all checks passed, lecture_type = laboratory when lab in name")
sys.exit(0)
