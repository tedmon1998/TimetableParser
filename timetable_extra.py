# -*- coding: utf-8 -*-
"""Доп. обработка расписания: пропуск служебных строк, опечатки разделителя, составные аудитории, очистка названий."""

import re
import os
import json

# Фразы для пропуска строк загружаются из info/skip_row_phrases.json
_SKIP_ROW_PHRASES_CACHE = None

SKIP_ROW_PHRASES = [
    'директор института',
    'зав. кафедрой',
    'заведующий кафедрой',
    'и.о. зав.кафедрой',
    'и.о. зав. кафедрой',
    'примечание:',
]


def _load_skip_row_phrases():
    """Загружает массив фраз для пропуска строк из info/skip_row_phrases.json."""
    global _SKIP_ROW_PHRASES_CACHE
    if _SKIP_ROW_PHRASES_CACHE is not None:
        return _SKIP_ROW_PHRASES_CACHE
    try:
        path = os.path.join(os.path.dirname(__file__), 'info', 'skip_row_phrases.json')
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                _SKIP_ROW_PHRASES_CACHE = [p for p in data if p and isinstance(p, str)]
        else:
            _SKIP_ROW_PHRASES_CACHE = SKIP_ROW_PHRASES  # fallback на дефолтный список
    except Exception:
        _SKIP_ROW_PHRASES_CACHE = SKIP_ROW_PHRASES
    return _SKIP_ROW_PHRASES_CACHE


def should_skip_row(row_text):
    """Возвращает True, если строку таблицы нужно пропустить (админ-блок)."""
    if not row_text or not isinstance(row_text, str):
        return False
    text_lower = row_text.strip().lower()
    for phrase in _load_skip_row_phrases():
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


# Фразы для точного удаления из названий дисциплин (загружаются из info/strip_from_subject.json)
_STRIP_PHRASES_CACHE = None


def _load_strip_phrases():
    """Загружает массив фраз для удаления из info/strip_from_subject.json (точное совпадение)."""
    global _STRIP_PHRASES_CACHE
    if _STRIP_PHRASES_CACHE is not None:
        return _STRIP_PHRASES_CACHE
    try:
        path = os.path.join(os.path.dirname(__file__), 'info', 'strip_from_subject.json')
        if os.path.isfile(path):
            import json
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                _STRIP_PHRASES_CACHE = [p for p in data if p and isinstance(p, str)]
        else:
            _STRIP_PHRASES_CACHE = []
    except Exception:
        _STRIP_PHRASES_CACHE = []
    return _STRIP_PHRASES_CACHE


def strip_phrases_from_text(text):
    """Удаляет из строки все фразы из info/strip_from_subject.json при точном совпадении (подстрока)."""
    if text is None or not isinstance(text, str):
        return text
    phrases = _load_strip_phrases()
    if not phrases:
        return text
    # Сортируем по длине (длинные первыми), чтобы « (с 12.30)» удалялось до «(с 12.30)» при наличии обоих
    for phrase in sorted(phrases, key=lambda x: -len(x)):
        if phrase in text:
            text = text.replace(phrase, '')
    text = re.sub(r'\s+', ' ', text).strip().strip(',')
    return text


# Правила замены: массив объектов { "from": "что заменять", "to": "на что" } (info/replace_in_subject.json)
_REPLACE_RULES_CACHE = None


def _load_replace_rules():
    """Загружает массив правил замены из info/replace_in_subject.json."""
    global _REPLACE_RULES_CACHE
    if _REPLACE_RULES_CACHE is not None:
        return _REPLACE_RULES_CACHE
    try:
        import json
        path = os.path.join(os.path.dirname(__file__), 'info', 'replace_in_subject.json')
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                _REPLACE_RULES_CACHE = []
                for item in data if isinstance(data, list) else []:
                    if isinstance(item, dict) and 'from' in item and 'to' in item:
                        _REPLACE_RULES_CACHE.append((str(item['from']), str(item['to'])))
        else:
            _REPLACE_RULES_CACHE = []
    except Exception:
        _REPLACE_RULES_CACHE = []
    return _REPLACE_RULES_CACHE


def apply_replace_in_subject(text):
    """Применяет замены из info/replace_in_subject.json. Замена только если до и после нет букв (целое слово)."""
    if text is None or not isinstance(text, str):
        return text
    rules = _load_replace_rules()
    # Замена только если до и после нет букв (целое совпадение, не часть слова)
    for from_str, to_str in rules:
        if not from_str:
            continue
        pattern = r'(?<![a-zA-Zа-яА-ЯёЁ])' + re.escape(from_str) + r'(?![a-zA-Zа-яА-ЯёЁ])'
        text = re.sub(pattern, to_str, text)
    return text


def clean_subject_trailing_chars(text):
    """Лёгкая очистка названия дисциплины: пробелы, апостроф; убираем точку, запятую, пробел в начале и конце."""
    if text is None:
        return ''
    text = str(text)
    text = text.replace("'", '')
    text = re.sub(r'\s+', ' ', text)
    return text.strip().strip('., \t\n\r')
