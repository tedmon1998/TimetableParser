# -*- coding: utf-8 -*-
"""Доп. обработка расписания: пропуск служебных строк, опечатки разделителя, составные аудитории, очистка названий."""

import re

SKIP_ROW_PHRASES = [
    'директор института',
    'зав. кафедрой',
    'заведующий кафедрой',
    'и.о. зав.кафедрой',
    'и.о. зав. кафедрой',
]


def should_skip_row(row_text):
    """Возвращает True, если строку таблицы нужно пропустить (админ-блок)."""
    if not row_text or not isinstance(row_text, str):
        return False
    text_lower = row_text.strip().lower()
    for phrase in SKIP_ROW_PHRASES:
        if phrase.lower() in text_lower:
            return True
    return False


def _normalize_week_separator_typos(text):
    """Нормализует опечатки разделителя недель: /// -> //, / / -> //, (лек)/(пр, и т.д."""
    if not text or not isinstance(text, str):
        return text
    text = text.strip()
    text = re.sub(r'//+', '//', text)
    text = re.sub(r'/\s+/', '//', text)
    text = re.sub(r'\s+/', '//', text)
    text = re.sub(r'\(лек\)\s*/\s*\(пр\s*,\s*', '(лек)/(пр), ', text, flags=re.IGNORECASE)
    text = re.sub(r'\(пр\)\s*/\s*\(лек\s*,\s*', '(пр)/(лек), ', text, flags=re.IGNORECASE)
    return text


def get_composite_audiences(valid_audiences, audience_prefixes):
    """Возвращает список «составных» аудиторий (содержащих '/') для подстановки при разборе по '/'."""
    composite = []
    if valid_audiences:
        for a in valid_audiences:
            if '/' in a and a not in composite:
                composite.append(a)
    if audience_prefixes:
        for p in audience_prefixes:
            if '/' in p and p not in composite:
                composite.append(p)
    composite.sort(key=lambda x: -len(x))
    return composite


def clean_subject_trailing_chars(text):
    """Лёгкая очистка названия дисциплины: пробелы, апостроф, лишние запятые в конце."""
    if text is None:
        return ''
    text = str(text).strip()
    text = text.replace("'", '')
    text = re.sub(r',\s*$', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()
