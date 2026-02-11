# -*- coding: utf-8 -*-
"""
Дополнительная обработка расписания: нормализация опечаток, пропуск служебных строк,
числитель/знаменатель по аудиториям, очистка названий дисциплин.
Используется из parse_timetable_excel.py.
"""
import re


# Фразы административного блока внизу листа — не парсить
SKIP_ROW_PHRASES = ('директор института', 'зав. кафедрой', 'заведующий кафедрой')


def should_skip_row(row_text, get_merged_cell_value=None, row_cells=None, ws=None):
    """Возвращает True, если строку нужно пропустить (директор института, зав. кафедрой)."""
    if not row_text and row_cells and ws and get_merged_cell_value:
        row_text = ' '.join(str(get_merged_cell_value(ws, c) or getattr(c, 'value', '') or '') for c in row_cells)
    if not row_text or not isinstance(row_text, str):
        return False
    return any(phrase in row_text.lower() for phrase in SKIP_ROW_PHRASES)


def _normalize_week_separator_typos(text):
    """Исправляет опечатки (тип1)/(тип2): ///, / /, пропущенные скобки.
    Поддерживает первый тип с доп. текстом: (лек 8 ч)/(пр).
    Не трогаем «п/г» (подгруппа) — после типа не должно быть «г»."""
    if not text or not isinstance(text, str):
        return text
    text = text.replace('/ /', '//')
    text = re.sub(r'/{3,}', '//', text)
    # Между ) первого типа и ( второго — убрать лишние ".", ",", пробелы: "(лек),/(пр)" -> "(лек)/(пр)"
    text = re.sub(r'\)\s*[.,\s]*/\s*[.,\s]*\(', r')/(', text)
    # Типы занятий (длинные первыми); первый тип может быть с " N ч": лек 8 ч
    tp = r'(лекция|лабораторная|практика|лек|пр|лаб|л|п)'
    tp_opt = tp + r'(?:\s*\d+\s*ч)?'  # первый тип: лек, лек 8 ч
    # 1. (лек/(пр) или (лек 8 ч/(пр) -> (лек)/(пр) или (лек 8 ч)/(пр)
    text = re.sub(r'\(' + tp_opt + r'/\(' + tp + r'\)', r'(\1)/(\2)', text, flags=re.IGNORECASE)
    # 2. лек)/(пр) или лек 8 ч)/(пр) -> (лек)/(пр), (лек 8 ч)/(пр)
    text = re.sub(r'(?<!\()' + tp_opt + r'\)/\(' + tp + r'\)', r'(\1)/(\2)', text, flags=re.IGNORECASE)
    # 3. (лек)/пр) или (лек 8 ч)/пр) -> (лек)/(пр)
    text = re.sub(r'\(' + tp_opt + r'\)/' + tp + r'\)', r'(\1)/(\2)', text, flags=re.IGNORECASE)
    # 4. (лек)/(пр, или (лек 8 ч)/(пр, -> (лек)/(пр),
    text = re.sub(r'\(' + tp_opt + r'\)\s*/\s*\(' + tp + r',\s*', r'(\1)/(\2), ', text, flags=re.IGNORECASE)
    # 5. (лек)/пр, или (лек 8 ч)/пр, -> (лек)/(пр),
    text = re.sub(r'\(' + tp_opt + r'\)/' + tp + r',\s*', r'(\1)/(\2), ', text, flags=re.IGNORECASE)
    # 6. (лек/пр, или (лек 8 ч/пр, -> (лек)/(пр),
    text = re.sub(r'\(' + tp_opt + r'/' + tp + r',\s*', r'(\1)/(\2), ', text, flags=re.IGNORECASE)
    # 7. лек/пр, или лек 8 ч/пр, -> (лек)/(пр),
    text = re.sub(r'(?<!\()' + tp_opt + r'/' + tp + r',\s*', r'(\1)/(\2), ', text, flags=re.IGNORECASE)
    # 8. Один слэш вместо двух между частями: "(лек), ЭОиДОТ/ Нейро-нечеткие" -> "(лек), ЭОиДОТ// Нейро..."
    # Пробелы вокруг слэша опциональны; после слэша — заглавная (начало след. дисциплины), чтобы не трогать "К625/ м/зал"
    text = re.sub(r'(\), [А-ЯЁа-яёA-Za-z0-9]+)\s*/\s*([А-ЯЁA-Z])', r'\1 // \2', text)
    # 9. "Дисциплина1/Дисциплина2, Аудитория" — один слэш между названиями (второе с заглавной) -> "//"
    # Слэш не должен быть частью "//" и после него — заглавная (м/зал не трогаем)
    text = re.sub(r'(?<!/)/(?!/)\s*([А-ЯЁA-Z])', r'// \1', text)
    return text


def normalize_type_slash_for_weeks(text):
    """(тип1)/(тип2) -> часть1 // часть2. Вызывать до обработки «//»."""
    if not text:
        return text
    text = _normalize_week_separator_typos(text)
    if '//' in text:
        return text
    type_pattern = r'(лек|пр|лаб|практика|лекция|лабораторная|л|п)'
    m = re.search(
        r'^(.+?)\s*\(' + type_pattern + r'\)\s*/\s*\(' + type_pattern + r'\)\s*(.*)$',
        text.strip(),
        re.IGNORECASE
    )
    if not m:
        return text
    prefix, type1, type2, suffix = m.group(1).strip(), m.group(2), m.group(3), m.group(4).strip()
    suffix_clean = suffix.lstrip(',').strip()
    part1 = f"{prefix} ({type1})"
    part2 = f"{prefix} ({type2})"
    if suffix_clean:
        part1 += ", " + suffix_clean
        part2 += ", " + suffix_clean
    return part1 + " // " + part2


def parse_week_type(text):
    """Определяет тип недели: числитель/знаменатель по «//» или « / »."""
    if not text or not isinstance(text, str):
        return ['обе недели']
    text = _normalize_week_separator_typos(text.strip())
    if '//' in text:
        parts = text.split('//')
        if len(parts) == 2:
            if parts[0].strip() and not parts[1].strip():
                return ['числитель']
            elif parts[1].strip() and not parts[0].strip():
                return ['знаменатель']
            elif parts[0].strip() and parts[1].strip():
                return ['числитель', 'знаменатель']
        return ['обе недели']
    if ' / ' in text:
        parts = text.split(' / ', 1)
        if len(parts) == 2:
            if parts[0].strip() and parts[1].strip():
                return ['числитель', 'знаменатель']
            elif parts[0].strip():
                return ['числитель']
            elif parts[1].strip():
                return ['знаменатель']
        return ['обе недели']
    return ['обе недели']


def clean_subject_trailing_chars(s):
    """Убирает лишние /, запятые и пробелы в конце и начале названия дисциплины."""
    if not s or not isinstance(s, str):
        return s
    s = re.sub(r'[,\s/]+$', '', s).strip()
    s = re.sub(r'^[,\s/]+', '', s).strip()
    return ' '.join(s.split())


def get_composite_audiences(valid_audiences_set, audience_prefixes):
    """Список аудиторий, в названии которых есть «/» (м/зал, п/б, л/б и т.д.)."""
    out = []
    if valid_audiences_set:
        out = sorted([a for a in valid_audiences_set if '/' in a], key=lambda x: -len(x))
    for p in (audience_prefixes or []):
        if '/' in p and p not in out:
            out.append(p)
    return out


def get_week_audience_lecture_triples(raw_discipline, parts, extract_audience_list_fn,
                                      parse_lecture_type_fn, extract_subject_name_fn, clean_subject_fn):
    """
    Для формата с «//» или «Subject (type), A/B» возвращает (subject_name, triples).
    triples = [(week_type, audience, lecture_type), ...] или None.
    """
    if not raw_discipline:
        return None, None
    # Формат с //
    if '//' in raw_discipline and len(parts) >= 2:
        aud_lists = [extract_audience_list_fn(p) for p in parts]
        chosen = []
        for i in range(len(parts)):
            if i < len(aud_lists[i]):
                chosen.append(aud_lists[i][i].strip())
            elif aud_lists[i]:
                chosen.append(aud_lists[i][0].strip())
            else:
                chosen.append('')
        clean_subject = clean_subject_fn(extract_subject_name_fn(parts[0]) or '') if parts else ''
        triples = [
            ('числитель', chosen[0] if len(chosen) > 0 else '', parse_lecture_type_fn(parts[0])),
            ('знаменатель', chosen[1] if len(chosen) > 1 else (chosen[0] if chosen else ''), parse_lecture_type_fn(parts[1])),
        ]
        return clean_subject or None, triples
    # Формат "Subject (type), м/зал/К625" — две аудитории без //
    aud_list = extract_audience_list_fn(raw_discipline)
    if len(aud_list) == 2:
        lecture_type = parse_lecture_type_fn(raw_discipline)
        triples = [
            ('числитель', aud_list[0], lecture_type),
            ('знаменатель', aud_list[1], lecture_type),
        ]
        return None, triples  # subject_name оставляем из основного файла
    return None, None
