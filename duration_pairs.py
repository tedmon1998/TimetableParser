# -*- coding: utf-8 -*-
"""
Обработка маркеров «полторы пары» в расписании.

Если в ячейке вместо дисциплины стоит ----- и есть аудитория (напр. "A25'-----" или "СОКБ-----"):
смотрим колонку выше и колонку ниже; если находим запись с такой же аудиторией — ставим там полторы пары,
маркерную запись удаляем.
"""

import re


def is_duration_marker(subject_name):
    """Проверяет, является ли subject_name маркером (больше двух '-' в строке)."""
    if not subject_name or not isinstance(subject_name, str):
        return False
    text = subject_name.replace("'", "").strip()
    if not text:
        return False
    return text.count('-') > 2


def extract_audiences_from_marker(subject_name):
    """
    Извлекает аудитории из маркера.
    "А25'-----" -> ["А25"], "СОКБ-----" -> ["СОКБ"], "----" -> []
    """
    if not subject_name or not isinstance(subject_name, str):
        return []
    text = subject_name.replace("'", "").strip()
    parts = [p.strip() for p in re.split(r'-+', text) if p and p.strip()]
    audiences = []
    for p in parts:
        if re.match(r'^[А-ЯЁа-яёA-Za-z0-9/]+$', p) and len(p) >= 2:
            audiences.append(p)
    return audiences


def _audience_matches(result_audience, target_audience):
    """Проверяет, совпадает ли аудитория в записи с целевой."""
    if not result_audience or not target_audience:
        return False
    aud_str = str(result_audience).strip()
    target = str(target_audience).strip()
    if aud_str == target:
        return True
    for part in aud_str.replace(';', ',').split(','):
        if part.strip() == target:
            return True
    if target in aud_str:
        return True
    return False


def _slot(rec):
    """Номер колонки дисциплины (0, 1, ...)."""
    v = rec.get('_discipline_slot')
    return v if isinstance(v, int) else 0


def apply_duration_pairs(results):
    """
    Если ячейка: дисциплина = "-----" и есть аудитория в маркере —
    смотрим выше и ниже в той же колонке; у записи с такой же аудиторией ставим duration_pairs=1.5,
    маркер удаляем.
    """
    if not results:
        return []
    results = list(results)
    indices_to_remove = []
    indices_to_mark = set()

    for i, rec in enumerate(results):
        subj = rec.get('subject_name') or ''
        if not is_duration_marker(subj):
            continue
        audiences = extract_audiences_from_marker(subj)
        if not audiences:
            # Чистый "----" без аудитории — просто удаляем
            indices_to_remove.append(i)
            continue
        indices_to_remove.append(i)
        day = rec.get('day_of_week', '')
        pair = rec.get('pair_number')
        slot = _slot(rec)
        try:
            pair = int(pair) if pair is not None else None
        except (TypeError, ValueError):
            pair = None
        if pair is None:
            continue
        # Ячейка выше (K12): тот же день, тот же slot, pair_number = pair - 1
        # Ячейка ниже (K14): тот же день, тот же slot, pair_number = pair + 1
        marked_any = False
        for j, other in enumerate(results):
            if j == i or (other.get('day_of_week') or '') != day:
                continue
            if _slot(other) != slot:
                continue
            try:
                op = other.get('pair_number')
                op = int(op) if op is not None else None
            except (TypeError, ValueError):
                op = None
            if op is None or op not in (pair - 1, pair + 1):
                continue
            for aud in audiences:
                if _audience_matches(other.get('audience'), aud):
                    indices_to_mark.add(j)
                    marked_any = True
                    break
        # Если по аудитории никого не нашли — помечаем все записи в ячейках выше и ниже (та же колонка)
        if not marked_any:
            for j, other in enumerate(results):
                if j == i or (other.get('day_of_week') or '') != day:
                    continue
                if _slot(other) != slot:
                    continue
                try:
                    op = other.get('pair_number')
                    op = int(op) if op is not None else None
                except (TypeError, ValueError):
                    op = None
                if op is not None and op in (pair - 1, pair + 1):
                    indices_to_mark.add(j)

    out = []
    for i, rec in enumerate(results):
        if i in indices_to_remove:
            continue
        rec_copy = dict(rec)
        if i in indices_to_mark:
            rec_copy['duration_pairs'] = 1.5
        elif 'duration_pairs' not in rec_copy:
            rec_copy['duration_pairs'] = 1
        out.append(rec_copy)
    return out
