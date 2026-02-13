import os
import re
import sys
import json
import csv
from openpyxl import load_workbook, Workbook
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter

# Вывод в консоль в UTF-8 (для кириллицы на Windows)
_reconfigure = getattr(sys.stdout, 'reconfigure', None)
if _reconfigure is not None:
    try:
        _reconfigure(encoding='utf-8')
    except Exception:
        pass

def load_audiences():
    """Загружает список валидных аудиторий из info/aud.json"""
    try:
        with open('info/aud.json', 'r', encoding='utf-8') as f:
            audiences = json.load(f)
        return set(audiences)
    except Exception as e:
        print(f"Ошибка при загрузке аудиторий: {e}")
        return set()

def extract_audiences_from_text(text, valid_audiences):
    """Извлекает аудитории из текста дисциплины.
    Не считаем букву «с» предлогом (с курсом, с основами) аудиторией «С»."""
    if not text:
        return []
    
    text = str(text)
    found_audiences = []
    
    # Ищем все возможные аудитории в тексте
    # Паттерны: А539, У708, К506, Г201, СОКБ, ЭОиДОТ и т.д.
    for aud in valid_audiences:
        pattern = r'\b' + re.escape(aud) + r'\b'
        for m in re.finditer(pattern, text, re.IGNORECASE):
            # Однобуквенная «С»: не считать предлог «с» (с курсом, с основами) аудиторией
            if aud == 'С' and m.group(0) == 'с' and m.end() < len(text):
                rest = text[m.end():m.end() + 2]
                if len(rest) >= 2 and rest[0] in ' \t' and rest[1].isalpha():
                    continue
            if aud not in found_audiences:
                found_audiences.append(aud)
            break
    
    # Если не нашли по списку, пытаемся найти по паттернам
    if not found_audiences:
        # Паттерны для аудиторий: буква + цифры (А539, У708, К506)
        patterns = [
            r'\b([А-ЯЁ][А-ЯЁ]?\d{2,4})\b',  # А539, У708, К506
            r'\b(СОКБ|СОКЦОМиД|ЭОиДОТ|ЭБЦ|ЦАС|УЦ)\b',  # Специальные аудитории
            r'\b(бассейн|зал\s+2|зал\s+гимн)\b',  # Специальные залы
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                # Проверяем, что это валидная аудитория
                for aud in valid_audiences:
                    if aud.upper() == match.upper():
                        if aud not in found_audiences:
                            found_audiences.append(aud)
                        break
    
    return found_audiences


def normalize_audience_week_separator(audience):
    """Нормализация аудитории: 'К504//, К429' -> 'К504//К429', без запятых вокруг '//'."""
    if not audience or not isinstance(audience, str):
        return audience or ''
    return re.sub(r',?\s*//\s*,?', '//', audience.strip()).strip(',').strip()


def normalize_type_slash_for_weeks(text):
    """Если одна группа ходит по числителю один тип, по знаменателю другой (запись через "/"),
    приводим к формату "//": "Название (лек)/(пр), К511" -> "Название (лек), К511 // Название (пр), К511".
    Вызывать до обработки "//". Если в тексте уже есть "//", текст не меняем."""
    if not text or '//' in text:
        return text
    text = str(text).strip()
    type_pattern = r'(лек|пр|л|п|практика|лекция)'
    m = re.search(
        r'^(.+?)\s*\(' + type_pattern + r'\)\s*/\s*\(' + type_pattern + r'\)\s*(.*)$',
        text,
        re.IGNORECASE
    )
    if not m:
        return text
    prefix, type1, type2, suffix = m.group(1).strip(), m.group(2), m.group(3), m.group(4).strip()
    suffix_clean = suffix.lstrip(',').strip()  # ", К511" -> "К511"
    part1 = f"{prefix} ({type1})"
    part2 = f"{prefix} ({type2})"
    if suffix_clean:
        part1 += ", " + suffix_clean
        part2 += ", " + suffix_clean
    return part1 + " // " + part2


def parse_week_division(text):
    """Определяет разделение по числителю/знаменателю (// или /)"""
    if not text:
        return None, None
    
    text = str(text)
    
    # Ищем разделитель "//" (числитель/знаменатель)
    if '//' in text:
        parts = text.split('//', 1)
        numerator = parts[0].strip()
        denominator = parts[1].strip() if len(parts) > 1 else ''
        return numerator, denominator
    
    # Ищем разделитель "/" (может быть числитель/знаменатель или просто разделитель)
    if '/' in text:
        # Проверяем, не является ли это частью аудитории (например, "п/г")
        if 'п/г' in text.lower() or 'подгруппа' in text.lower():
            return None, None
        
        parts = text.split('/', 1)
        numerator = parts[0].strip()
        denominator = parts[1].strip() if len(parts) > 1 else ''
        # Если обе части не пустые, это может быть числитель/знаменатель
        if numerator and denominator:
            return numerator, denominator
    
    return None, None

def extract_lecture_type(text):
    """Определяет тип занятия: лекция, практика или лабораторная.
    Лабораторную проверяем до практики, чтобы «лабораторная практика» давала лабораторная.
    Учитываем варианты: (пр). А603, ( пр ), (лек) и т.д."""
    if not text:
        return None
    
    text_lower = str(text).lower()
    
    # Проверяем наличие подгрупп - если есть, то это практика
    if 'п/г' in text_lower or 'подгруппа' in text_lower:
        return 'практика'
    
    # Маркеры в скобках с возможными пробелами: (лек), ( пр ). А603
    if re.search(r'\(\s*лек\s*\)', text_lower) or re.search(r'\bлек\b', text_lower) or 'лекция' in text_lower:
        return 'лекция'
    if re.search(r'\(\s*лаб\s*\)', text_lower) or 'лабораторная' in text_lower or 'лабораторные' in text_lower or re.search(r'\bлаб\b', text_lower):
        return 'лабораторная'
    if re.search(r'\(\s*пр\s*\)', text_lower) or 'практика' in text_lower:
        return 'практика'
    
    # Если есть разделение по подгруппам (п/г 1, п/г 2), это практика
    if re.search(r'п/г\s*\d+', text_lower, re.IGNORECASE):
        return 'практика'
    
    return None

def split_multiple_disciplines(text, valid_audiences):
    """Разбивает текст на несколько дисциплин, если они есть.
    Разделение происходит, если после аудитории есть текст (начало следующей дисциплины)"""
    if not text:
        return [text]
    
    text = str(text)
    disciplines = []
    
    # Создаем паттерн из всех валидных аудиторий (сортируем по длине в обратном порядке для более точного совпадения)
    aud_pattern = '|'.join([re.escape(aud) for aud in sorted(valid_audiences, key=len, reverse=True)])
    
    # Находим все позиции аудиторий в тексте
    # Паттерн: граница слова + аудитория + граница слова
    pattern = rf'\b({aud_pattern})\b'
    aud_matches = list(re.finditer(pattern, text, re.IGNORECASE))
    
    if len(aud_matches) <= 1:
        # Если одна или нет аудиторий, возвращаем весь текст как одну дисциплину
        return [text]
    
    # Проверяем каждую аудиторию (кроме последней) - есть ли после неё текст
    split_positions = []
    for i, match in enumerate(aud_matches[:-1]):  # Все кроме последней
        aud_end_pos = match.end()  # Позиция после аудитории
        
        # Проверяем, что после аудитории есть текст (не конец строки)
        if aud_end_pos < len(text):
            # Берем текст после аудитории (до следующей аудитории или до конца)
            text_after = text[aud_end_pos:].strip()
            
            # Если после аудитории есть текст, который начинается с заглавной буквы или содержит название дисциплины
            # Это означает, что начинается новая дисциплина
            if text_after:
                # Проверяем, что следующий символ - это пробел и затем заглавная буква или начало нового слова
                # Или что после аудитории идет текст, который не является частью текущей дисциплины
                next_char_pos = aud_end_pos
                # Пропускаем пробелы и запятые
                while next_char_pos < len(text) and text[next_char_pos] in ' ,':
                    next_char_pos += 1
                
                if next_char_pos < len(text):
                    # Если следующий символ - заглавная буква (начало нового слова/дисциплины)
                    # Или если до следующей аудитории есть достаточно текста (больше 3 символов)
                    next_aud_pos = aud_matches[i + 1].start() if i + 1 < len(aud_matches) else len(text)
                    text_between = text[aud_end_pos:next_aud_pos].strip()
                    
                    # Если между аудиториями есть текст, начинающийся с заглавной буквы - это новая дисциплина
                    if text_between and len(text_between) > 3:
                        # Проверяем, что это не просто продолжение текущей дисциплины
                        # Если текст начинается с заглавной буквы после пробела/запятой - это новая дисциплина
                        if re.match(r'^[,\s]*[А-ЯЁ]', text_between):
                            split_positions.append(aud_end_pos)
    
    # Если не нашли позиций разделения, возвращаем весь текст
    if not split_positions:
        return [text]
    
    # Разбиваем текст по найденным позициям
    last_pos = 0
    for split_pos in split_positions:
        part = text[last_pos:split_pos].strip()
        if part:
            disciplines.append(part)
        last_pos = split_pos
    
    # Добавляем оставшуюся часть
    if last_pos < len(text):
        remaining = text[last_pos:].strip()
        if remaining:
            disciplines.append(remaining)
    
    # Если получили только одну часть, возвращаем исходный текст
    if len(disciplines) <= 1:
        return [text]
    
    return disciplines

def clean_discipline_name(text, audience_to_remove=None):
    """Очищает название дисциплины от аудитории, оставляя только название и подгруппу"""
    if not text:
        return text
    
    text = str(text)
    
    # Если указана аудитория для удаления, убираем её
    if audience_to_remove:
        # Аудитория «С»: убираем только заглавную С, не предлог «с»
        if audience_to_remove == 'С':
            text = re.sub(r'\bС\b', '', text)
        else:
            pattern = r'\b' + re.escape(audience_to_remove) + r'\b'
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # Убираем все валидные аудитории из текста (на случай, если остались другие)
    # Но только если они не являются частью названия дисциплины
    # Сначала убираем паттерны типа ", А539", ", У708" и т.д.
    text = re.sub(r',\s*([А-ЯЁ][А-ЯЁ]?\d{2,4}|СОКБ|СОКЦОМиД|ЭОиДОТ|ЭБЦ|ЦАС|УЦ|бассейн|зал\s+2|зал\s+гимн)\b', '', text, flags=re.IGNORECASE)
    
    # Убираем разделители "//" в середине текста (но не в начале/конце, они важны)
    text = re.sub(r'\s*//\s*', ' ', text)
    
    # Убираем лишние пробелы и запятые
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r',\s*,', ',', text)  # Двойные запятые
    text = re.sub(r',\s*$', '', text)  # Запятая в конце
    text = text.strip(', ').strip()
    
    return text

def clean_subject_name_final(text, valid_audiences=None):
    """Очищает название предмета от лишних символов: (лек), (пр), п/г, аудитории и т.д."""
    if not text:
        return text
    
    text = str(text)
    
    # Убираем "(лек)", "(пр)" и подобные
    text = re.sub(r'\(лек\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\(пр\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\(лек\s*\d+\s*ч\)', '', text, flags=re.IGNORECASE)  # (лек 8 ч)
    text = re.sub(r'\(практика\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\(лекция\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\(лекция\s*\d+\s*ч\)', '', text, flags=re.IGNORECASE)  # (лекция 8 ч)
    text = re.sub(r'\(лекция\s+\d+\s+ч\)', '', text, flags=re.IGNORECASE)  # (лекция 8 ч) с пробелами
    text = re.sub(r'\(24\s*ч\)', '', text, flags=re.IGNORECASE)  # (24 ч)
    
    # Убираем подгруппы: п/г 1, п/г 2, п/г1, п/г2 и т.д. (более агрессивно)
    # Сначала убираем с запятой, потом любые вхождения (включая без пробела после запятой)
    text = re.sub(r',\s*п/г\s*\d+', '', text, flags=re.IGNORECASE)
    text = re.sub(r',п/г\s*\d+', '', text, flags=re.IGNORECASE)  # Без пробела после запятой
    text = re.sub(r'\s+п/г\s*\d+', '', text, flags=re.IGNORECASE)  # С пробелом перед
    text = re.sub(r'п/г\s*\d+', '', text, flags=re.IGNORECASE)  # Любое вхождение п/г
    text = re.sub(r',\s*подгруппа\s*\d+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+подгруппа\s*\d+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'подгруппа\s*\d+', '', text, flags=re.IGNORECASE)  # Любое вхождение подгруппа
    
    # Убираем все валидные аудитории из текста
    if valid_audiences:
        for aud in valid_audiences:
            # Аудитория «С»: убираем только заглавную С, не предлог «с» (с курсом, с основами)
            if aud == 'С':
                text = re.sub(r'[, ]\s*С\b', ' ', text)
                text = re.sub(r'\bС\b', '', text)
            else:
                pattern = r'[, ]\s*' + re.escape(aud) + r'\b'
                text = re.sub(pattern, '', text, flags=re.IGNORECASE)
                pattern = r'\b' + re.escape(aud) + r'\b'
                text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # Убираем разделители "//" в середине текста
    text = re.sub(r'\s*//\s*', ' ', text)
    # Убираем апостроф из названия дисциплины
    text = text.replace("'", '')
    # Убираем лишние пробелы и запятые
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r',\s*,', ',', text)  # Двойные запятые
    text = re.sub(r',\s*$', '', text)  # Запятая в конце
    text = text.strip(', ').strip()
    
    return text

def split_teachers(teacher_text):
    """Разделяет преподавателей по '/' - первый для числителя, второй для знаменателя"""
    if not teacher_text:
        return None, None
    
    teacher_text = str(teacher_text).strip()
    if '/' in teacher_text:
        parts = teacher_text.split('/', 1)  # Разделяем только по первому '/'
        numerator_teacher = parts[0].strip() if parts[0] else None
        denominator_teacher = parts[1].strip() if len(parts) > 1 and parts[1] else None
        return numerator_teacher, denominator_teacher
    
    # Если нет '/', то один преподаватель для обеих недель
    return teacher_text, teacher_text

def split_teachers_by_subgroups(teacher_text):
    """Разделяет преподавателей по ';' - каждый для своей подгруппы"""
    if not teacher_text:
        return []
    
    teacher_text = str(teacher_text).strip()
    if ';' in teacher_text:
        teachers = [t.strip() for t in teacher_text.split(';') if t.strip()]
        return teachers
    
    # Если нет ';', то один преподаватель для всех подгрупп
    return [teacher_text] if teacher_text else []

def extract_subgroups_from_text(text):
    """Извлекает номера подгрупп из текста (п/г 1, п/г 2 и т.д.)"""
    if not text:
        return []
    
    text = str(text)
    subgroups = []
    
    # Ищем паттерны: п/г 1, п/г 2, п/г1, п/г2 и т.д.
    pattern = r'п/г\s*(\d+)'
    matches = re.findall(pattern, text, re.IGNORECASE)
    for match in matches:
        subgroup_num = int(match)
        if subgroup_num not in subgroups:
            subgroups.append(subgroup_num)
    
    # Ищем паттерны: подгруппа 1, подгруппа 2 и т.д.
    pattern = r'подгруппа\s*(\d+)'
    matches = re.findall(pattern, text, re.IGNORECASE)
    for match in matches:
        subgroup_num = int(match)
        if subgroup_num not in subgroups:
            subgroups.append(subgroup_num)
    
    return sorted(subgroups)

def extract_audience_for_subgroup(text, subgroup_num, valid_audiences):
    """Извлекает аудиторию для конкретной подгруппы из текста"""
    if not text or not subgroup_num:
        return None
    
    text = str(text)
    # Ищем паттерн: п/г N, АУДИТОРИЯ или п/г N АУДИТОРИЯ
    # Ищем участок текста, связанный с этой подгруппой
    pattern = rf'п/г\s*{subgroup_num}[,\s]+([А-ЯЁ][А-ЯЁ]?\d{{2,4}}|СОКБ|СОКЦОМиД|ЭОиДОТ|ЭБЦ|ЦАС|УЦ|бассейн|зал\s+2|зал\s+гимн)'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        potential_aud = match.group(1)
        # Проверяем, что это валидная аудитория
        if potential_aud in valid_audiences:
            return potential_aud
    
    # Альтернативный паттерн: подгруппа N, АУДИТОРИЯ
    pattern = rf'подгруппа\s*{subgroup_num}[,\s]+([А-ЯЁ][А-ЯЁ]?\d{{2,4}}|СОКБ|СОКЦОМиД|ЭОиДОТ|ЭБЦ|ЦАС|УЦ|бассейн|зал\s+2|зал\s+гимн)'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        potential_aud = match.group(1)
        if potential_aud in valid_audiences:
            return potential_aud
    
    return None

def process_discipline_text(text, valid_audiences, teacher_text=None, existing_week_type=None, existing_lecture_type=None):
    """Обрабатывает текст дисциплины и возвращает список записей (по одной на каждую дисциплину/неделю)
    
    Args:
        text: Текст дисциплины
        valid_audiences: Список валидных аудиторий
        teacher_text: Текст с преподавателями
        existing_week_type: Если указан, обрабатываем только эту неделю (числитель/знаменатель)
        existing_lecture_type: Тип из парсера (напр. "лекция // лабораторная"); при разбиении по // берём части отсюда, т.к. в text маркеры (лек)/(лаб) уже убраны
    """
    if not text:
        return []
    
    text = str(text)
    # Одна группа: числитель — один тип, знаменатель — другой: "(лек)/(пр), К511" -> "...(лек), К511 // ...(пр), К511"
    text = normalize_type_slash_for_weeks(text)
    results = []
    lecture_type = extract_lecture_type(text)  # для ветки «нет //» и fallback «if not results»
    
    # СНАЧАЛА проверяем разделение по неделям (//) - это приоритетнее всего
    # Если есть разделение по //, обрабатываем его сразу
    if '//' in text:
        # Разделение по числителю/знаменателю обрабатывается ниже (строка 451)
        # Пропускаем обработку подгрупп и множественных дисциплин
        pass
    else:
        # Если нет разделения по //, проверяем множественные дисциплины
        multiple_disciplines = split_multiple_disciplines(text, valid_audiences)
        
        # Если нашли несколько дисциплин, обрабатываем каждую отдельно
        if len(multiple_disciplines) > 1:
            # Разделяем преподавателей по ';' если они есть
            teachers_list = split_teachers_by_subgroups(teacher_text) if teacher_text else []
            
            # Обрабатываем каждую дисциплину с соответствующим преподавателем
            for disc_idx, disc_text in enumerate(multiple_disciplines):
                # Сопоставляем преподавателя с дисциплиной по порядку
                if disc_idx < len(teachers_list):
                    # Есть преподаватель для этой дисциплины
                    disc_teacher = teachers_list[disc_idx]
                elif len(teachers_list) > 0:
                    # Если преподавателей меньше, чем дисциплин, используем последнего
                    disc_teacher = teachers_list[-1]
                else:
                    # Нет преподавателей
                    disc_teacher = None
                
                # Рекурсивно обрабатываем каждую дисциплину с её преподавателем
                disc_results = process_discipline_text(disc_text, valid_audiences, disc_teacher)
                results.extend(disc_results)
            
            # Если создали записи, возвращаем их
            if results:
                return results
        
        # Если нет множественных дисциплин, проверяем подгруппы
        # Проверяем, есть ли разделение преподавателей по ';' (для подгрупп)
        teachers_by_subgroups = split_teachers_by_subgroups(teacher_text) if teacher_text else []
        subgroups_in_text = extract_subgroups_from_text(text)
        
        # Если есть подгруппы в тексте, обрабатываем отдельно
        # Если есть несколько преподавателей - сопоставляем по порядку
        # Если один преподаватель - он для всех подгрупп
        if len(subgroups_in_text) > 0:
            # Определяем тип занятия
            lecture_type = extract_lecture_type(text)
            if not lecture_type:
                lecture_type = 'практика'  # Если есть подгруппы, это практика
            
            # Очищаем название дисциплины
            clean_name = clean_subject_name_final(text, valid_audiences)
            
            # Сопоставляем преподавателей с подгруппами
            for i, subgroup_num in enumerate(subgroups_in_text):
                # Если есть несколько преподавателей, сопоставляем по порядку
                # Если один преподаватель или их нет, используем первого/единственного
                if len(teachers_by_subgroups) > 1:
                    teacher_for_subgroup = teachers_by_subgroups[i] if i < len(teachers_by_subgroups) else teachers_by_subgroups[-1]
                elif len(teachers_by_subgroups) == 1:
                    teacher_for_subgroup = teachers_by_subgroups[0]
                else:
                    teacher_for_subgroup = None
                
                # Извлекаем аудиторию для этой конкретной подгруппы
                aud_for_subgroup = extract_audience_for_subgroup(text, subgroup_num, valid_audiences)
                
                # Если не нашли специфичную аудиторию, берем все аудитории из текста
                if not aud_for_subgroup:
                    all_audiences = extract_audiences_from_text(text, valid_audiences)
                    aud_for_subgroup = all_audiences[0] if all_audiences else ''
                
                result_entry = {
                    'audience': aud_for_subgroup,
                    'subject_name': clean_name,
                    'lecture_type': lecture_type or '',
                    'subgroup': subgroup_num
                }
                # Добавляем преподавателя только если он есть
                if teacher_for_subgroup:
                    result_entry['teacher'] = teacher_for_subgroup
                
                results.append(result_entry)
            
            # Если создали записи для подгрупп, возвращаем их
            if results:
                return results
    
    # Иначе обрабатываем как обычно (разделение по '/' для числителя/знаменателя)
    # Разделяем преподавателей, если они есть
    numerator_teacher, denominator_teacher = split_teachers(teacher_text) if teacher_text else (None, None)
    
    # Проверяем, есть ли разделение по неделям (//) во всем тексте
    if '//' in text:
        # Есть разделение по числителю/знаменателю
        # Разбиваем на части по "//"
        parts = text.split('//')
        
        # Числитель - первая часть (до "//")
        numerator_text = parts[0].strip() if parts else ''
        # Знаменатель - вторая часть (после "//"); при нескольких "//" — всё после первого "//"
        denominator_text = (' // '.join(parts[1:]).strip() if len(parts) > 1 else '').strip()
        
        # Если в исходной строке уже указан week_type, обрабатываем только соответствующую часть
        if existing_week_type and existing_week_type.strip() and existing_week_type not in ('обе недели', 'обе'):
            if existing_week_type.strip() == 'числитель':
                denominator_text = ''
            elif existing_week_type.strip() == 'знаменатель':
                numerator_text = ''
        
        # Тип занятия: если в строке уже пришёл тип "лекция // лабораторная" (из парсера), берём части оттуда —
        # в text маркеры (лек)/(лаб) уже убраны, и extract_lecture_type по тексту даст практика
        if existing_lecture_type and ' // ' in str(existing_lecture_type).strip():
            type_parts = [p.strip() for p in str(existing_lecture_type).split('//') if p.strip()]
            if len(type_parts) >= 2:
                numerator_lecture_type = type_parts[0] if numerator_text else ''
                denominator_lecture_type = type_parts[1] if denominator_text else ''
            else:
                numerator_lecture_type = extract_lecture_type(numerator_text) if numerator_text else ''
                denominator_lecture_type = extract_lecture_type(denominator_text) if denominator_text else ''
        else:
            numerator_lecture_type = extract_lecture_type(numerator_text) if numerator_text else ''
            denominator_lecture_type = extract_lecture_type(denominator_text) if denominator_text else ''
        if not numerator_lecture_type and ('п/г' in (numerator_text or '').lower() or 'подгруппа' in (numerator_text or '').lower()):
            numerator_lecture_type = 'практика'
        if not denominator_lecture_type and ('п/г' in (denominator_text or '').lower() or 'подгруппа' in (denominator_text or '').lower()):
            denominator_lecture_type = 'практика'
        
        # Извлекаем подгруппы из числителя и знаменателя
        numerator_subgroups = extract_subgroups_from_text(numerator_text) if numerator_text else []
        denominator_subgroups = extract_subgroups_from_text(denominator_text) if denominator_text else []
        
        # Извлекаем аудитории из числителя (убираем дубликаты)
        numerator_audiences_unique = []
        if numerator_text:
            numerator_audiences = extract_audiences_from_text(numerator_text, valid_audiences)
            for aud in numerator_audiences:
                if aud not in numerator_audiences_unique:
                    numerator_audiences_unique.append(aud)
        
        # Извлекаем аудитории из знаменателя (убираем дубликаты)
        denominator_audiences_unique = []
        if denominator_text:
            denominator_audiences = extract_audiences_from_text(denominator_text, valid_audiences)
            for aud in denominator_audiences:
                if aud not in denominator_audiences_unique:
                    denominator_audiences_unique.append(aud)
        
        # Когда после "//" только одна часть непуста (напр. "СОКЦОМиД//"): сохраняем week_type из источника
        only_numerator = numerator_text and not denominator_text
        only_denominator = denominator_text and not numerator_text
        existing_is_both = existing_week_type and str(existing_week_type).strip() in ('обе недели', 'обе')
        effective_numerator_week = 'обе недели' if (only_numerator and existing_is_both) else 'числитель'
        effective_denominator_week = 'обе недели' if (only_denominator and existing_is_both) else 'знаменатель'
        
        # Создаем отдельные строки для числителя
        if numerator_text:
            if numerator_subgroups:
                for subgroup_num in numerator_subgroups:
                    aud_for_subgroup = extract_audience_for_subgroup(numerator_text, subgroup_num, valid_audiences)
                    if not aud_for_subgroup and numerator_audiences_unique:
                        aud_for_subgroup = numerator_audiences_unique[0]
                    clean_name = clean_subject_name_final(numerator_text, valid_audiences)
                    result_entry = {
                        'audience': aud_for_subgroup or '',
                        'subject_name': clean_name,
                        'lecture_type': numerator_lecture_type or 'практика',
                        'week_type': effective_numerator_week,
                        'subgroup': subgroup_num
                    }
                    if numerator_teacher:
                        result_entry['teacher'] = numerator_teacher
                    results.append(result_entry)
            else:
                # Одна запись для числителя (без подгрупп)
                if numerator_audiences_unique:
                    for aud in numerator_audiences_unique:
                        clean_name = clean_subject_name_final(numerator_text, valid_audiences)
                        result_entry = {
                            'audience': aud,
                            'subject_name': clean_name,
                            'lecture_type': numerator_lecture_type or 'практика',
                            'week_type': effective_numerator_week
                        }
                        if numerator_teacher:
                            result_entry['teacher'] = numerator_teacher
                        results.append(result_entry)
                else:
                    clean_name = clean_subject_name_final(numerator_text, valid_audiences)
                    result_entry = {
                        'audience': '',
                        'subject_name': clean_name,
                        'lecture_type': numerator_lecture_type or 'практика',
                        'week_type': effective_numerator_week
                    }
                    if numerator_teacher:
                        result_entry['teacher'] = numerator_teacher
                    results.append(result_entry)
        
        # Создаем отдельные строки для знаменателя
        if denominator_text:
            if denominator_subgroups:
                for subgroup_num in denominator_subgroups:
                    aud_for_subgroup = extract_audience_for_subgroup(denominator_text, subgroup_num, valid_audiences)
                    if not aud_for_subgroup and denominator_audiences_unique:
                        aud_for_subgroup = denominator_audiences_unique[0]
                    clean_name = clean_subject_name_final(denominator_text, valid_audiences)
                    result_entry = {
                        'audience': aud_for_subgroup or '',
                        'subject_name': clean_name,
                        'lecture_type': denominator_lecture_type or 'практика',
                        'week_type': effective_denominator_week,
                        'subgroup': subgroup_num
                    }
                    if denominator_teacher:
                        result_entry['teacher'] = denominator_teacher
                    results.append(result_entry)
            else:
                # Одна запись для знаменателя (без подгрупп)
                if denominator_audiences_unique:
                    for aud in denominator_audiences_unique:
                        clean_name = clean_subject_name_final(denominator_text, valid_audiences)
                        result_entry = {
                            'audience': aud,
                            'subject_name': clean_name,
                            'lecture_type': denominator_lecture_type or 'практика',
                            'week_type': effective_denominator_week
                        }
                        if denominator_teacher:
                            result_entry['teacher'] = denominator_teacher
                        results.append(result_entry)
                else:
                    clean_name = clean_subject_name_final(denominator_text, valid_audiences)
                    result_entry = {
                        'audience': '',
                        'subject_name': clean_name,
                        'lecture_type': denominator_lecture_type or 'практика',
                        'week_type': effective_denominator_week
                    }
                    if denominator_teacher:
                        result_entry['teacher'] = denominator_teacher
                    results.append(result_entry)
    else:
        # Нет разделения по неделям - это одна дисциплина (уже проверили множественные выше)
        # Обрабатываем как одну дисциплину (обе недели)
        lecture_type = extract_lecture_type(text)
        if not lecture_type and ('п/г' in text.lower() or 'подгруппа' in text.lower()):
            lecture_type = 'практика'
        disc_text = text
        audiences = extract_audiences_from_text(disc_text, valid_audiences)
        # Убираем дубликаты, сохраняя порядок
        audiences_unique = []
        for aud in audiences:
            if aud not in audiences_unique:
                audiences_unique.append(aud)
        
        # Создаем одну строку для каждой уникальной аудитории
        for aud in audiences_unique:
            # Очищаем название дисциплины от аудитории, оставляя только название и подгруппу
            clean_name = clean_discipline_name(disc_text, aud)
            # Финальная очистка от (лек), (пр), п/г и т.д.
            clean_name = clean_subject_name_final(clean_name, valid_audiences)
            result_entry = {
                'audience': aud,
                'subject_name': clean_name,
                'lecture_type': lecture_type or ''
            }
            # Если есть преподаватель (без разделения), добавляем его для обеих недель
            if numerator_teacher and numerator_teacher == denominator_teacher:
                result_entry['teacher'] = numerator_teacher
                result_entry['week_type'] = 'обе недели'
            results.append(result_entry)
    
    # Если не нашли ни одной аудитории, создаем запись без аудитории
    if not results:
        # Финальная очистка от (лек), (пр), п/г и т.д.
        clean_name = clean_subject_name_final(text, valid_audiences)
        result_entry = {
            'audience': '',
            'subject_name': clean_name,
            'lecture_type': lecture_type or ''
        }
        # Если есть преподаватель (без разделения), добавляем его
        if numerator_teacher and numerator_teacher == denominator_teacher:
            result_entry['teacher'] = numerator_teacher
            result_entry['week_type'] = 'обе недели'
        results.append(result_entry)
    
    return results

def _split_group_value(group_str):
    """Разбивает '501-33,501-34,501-35' или '502-21.502-22', '403-41.407-41' на отдельные группы. Возвращает список строк."""
    if not group_str or not str(group_str).strip():
        return ['']
    s = str(group_str).replace('.', ',').replace(';', ',').replace('\uFF0C', ',').strip()
    parts = [p.strip() for p in s.split(',') if p.strip()]
    return parts if parts else [s]


def _write_results_to_excel(results, new_headers, path):
    """Записывает список словарей в Excel файл."""
    out_dir = os.path.dirname(path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    wb_new = Workbook()
    ws_new = wb_new.active
    if ws_new is None:
        raise RuntimeError("Workbook has no active sheet")
    for col_idx, header in enumerate(new_headers, 1):
        cell = ws_new.cell(1, col_idx, value=header)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center', vertical='center')
    for row_idx, row_data in enumerate(results, 2):
        for col_idx, header in enumerate(new_headers, 1):
            value = row_data.get(header, '')
            ws_new.cell(row_idx, col_idx, value=value)
    for col_idx, col in enumerate(ws_new.columns, 1):
        max_length = 0
        for cell in col:
            try:
                if cell.value and (length := len(str(cell.value))) > max_length:
                    max_length = length
            except Exception:
                pass
        col_letter = get_column_letter(col_idx)
        ws_new.column_dimensions[col_letter].width = min(max_length + 2, 50)
    ws_new.freeze_panes = 'A2'
    wb_new.save(path)


def process_csv_file(input_file, output_file, valid_audiences):
    """Обрабатывает CSV файл и создает очищенную версию (только в Excel)."""
    results = []
    
    with open(input_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        for row in reader:
            group_raw = row.get('group_name', '') or row.get('group', '') or ''
            group_parts = _split_group_value(group_raw)
            subject_name = row.get('subject_name', '')
            teacher_fio = row.get('fio', '') or row.get('teacher', '')
            existing_week_type = row.get('week_type', '') or row.get('week', '')
            existing_lecture_type = row.get('lecture_type', '') or ''
            existing_audience = (row.get('audience') or '').strip()
            # Строки, уже разбитые парсером (числитель/знаменатель с аудиторией), не переразбирать
            if existing_week_type in ('числитель', 'знаменатель') and existing_audience:
                processed_list = [{
                    'audience': existing_audience,
                    'subject_name': clean_subject_name_final(subject_name, valid_audiences),
                    'lecture_type': existing_lecture_type or '',
                    'week_type': existing_week_type
                }]
                if teacher_fio:
                    processed_list[0]['teacher'] = teacher_fio
            else:
                processed_list = process_discipline_text(subject_name, valid_audiences, teacher_fio, existing_week_type, existing_lecture_type)
            
            # Для каждой группы — отдельные записи (501-33,501-34,501-35 -> три записи)
            for group_val in group_parts:
                row_with_group = row.copy()
                row_with_group['group'] = group_val
                row_with_group['group_name'] = group_val
                
                for processed in processed_list:
                    new_row = row_with_group.copy()
                    new_row['audience'] = normalize_audience_week_separator(processed['audience'])
                    new_row['subject_name'] = processed['subject_name']
                    new_row['lecture_type'] = processed['lecture_type']
                    if 'teacher' in processed:
                        new_row['fio'] = processed['teacher']
                        if 'teacher' in new_row:
                            new_row['teacher'] = processed['teacher']
                    if 'week_type' in processed:
                        new_row['week_type'] = processed['week_type']
                    elif 'week' in new_row and not new_row.get('week_type'):
                        new_row['week_type'] = new_row.get('week', '')
                    if 'subgroup' in processed:
                        new_row['subgroup'] = processed['subgroup']
                    if 'group' in new_row and not new_row.get('group_name'):
                        new_row['group_name'] = new_row.get('group', '')
                    new_row.pop('audience_numerator', None)
                    new_row.pop('audience_denominator', None)
                    results.append(new_row)
    
    # Определяем новые заголовки
    new_fieldnames = []
    # Порядок: day_of_week, pair_number, subject_name, lecture_type, audience
    priority_fields = ['day_of_week', 'pair_number', 'subject_name', 'lecture_type', 'audience']
    
    # Добавляем приоритетные поля
    for field in priority_fields:
        if field in fieldnames:
            new_fieldnames.append(field)
    
    # Добавляем остальные поля (кроме старых audience_numerator, audience_denominator)
    for field in fieldnames:
        if field not in new_fieldnames and field not in ['audience_numerator', 'audience_denominator']:
            new_fieldnames.append(field)
    
    # Убеждаемся, что audience есть в заголовках
    if 'audience' not in new_fieldnames:
        # Вставляем после subject_name или в конец
        if 'subject_name' in new_fieldnames:
            idx = new_fieldnames.index('subject_name') + 1
            new_fieldnames.insert(idx, 'audience')
        else:
            new_fieldnames.append('audience')
    
    # Убеждаемся, что lecture_type есть в заголовках
    if 'lecture_type' not in new_fieldnames:
        # Вставляем после subject_name или в конец
        if 'subject_name' in new_fieldnames:
            idx = new_fieldnames.index('subject_name') + 1
            new_fieldnames.insert(idx, 'lecture_type')
        else:
            new_fieldnames.append('lecture_type')
    
    # Убеждаемся, что fio, week_type, subgroup и group_name есть в заголовках, если они используются
    if 'fio' not in new_fieldnames:
        # Проверяем, используется ли fio в результатах
        for result in results:
            if 'fio' in result and result.get('fio'):
                new_fieldnames.append('fio')
                break
    if 'teacher' not in new_fieldnames:
        # Проверяем, используется ли teacher в результатах
        for result in results:
            if 'teacher' in result and result.get('teacher'):
                new_fieldnames.append('teacher')
                break
    if 'week_type' not in new_fieldnames:
        # Проверяем, используется ли week_type в результатах
        for result in results:
            if 'week_type' in result and result.get('week_type'):
                new_fieldnames.append('week_type')
                break
    if 'group_name' not in new_fieldnames:
        # Проверяем, используется ли group_name в результатах
        for result in results:
            if 'group_name' in result and result.get('group_name'):
                new_fieldnames.append('group_name')
                break
        # Если group_name не найден, но есть group, добавляем group_name
        if 'group_name' not in new_fieldnames:
            for result in results:
                if 'group' in result and result.get('group'):
                    new_fieldnames.append('group_name')
                    break
    if 'subgroup' not in new_fieldnames:
        # Проверяем, используется ли subgroup в результатах
        for result in results:
            if 'subgroup' in result and result.get('subgroup'):
                new_fieldnames.append('subgroup')
                break
    
    # Убеждаемся, что все важные поля присутствуют в заголовках
    important_fields = ['fio', 'teacher', 'group_name', 'week_type']
    for field in important_fields:
        if field not in new_fieldnames:
            # Проверяем, есть ли это поле хотя бы в одной записи
            for result in results:
                if field in result:
                    new_fieldnames.append(field)
                    break
    
    # Логируем финальные заголовки для отладки
    print(f"DEBUG: Финальные заголовки: {new_fieldnames}")
    if results:
        print(f"DEBUG: Первая запись результата: {list(results[0].keys())}")
        print(f"DEBUG: Значения первой записи - fio: {results[0].get('fio')}, teacher: {results[0].get('teacher')}, group_name: {results[0].get('group_name')}, week_type: {results[0].get('week_type')}")
    
    # Сохраняем результат в Excel и в CSV
    _write_results_to_excel(results, new_fieldnames, output_file)
    csv_path = output_file.replace('.xlsx', '.csv')
    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=new_fieldnames)
        writer.writeheader()
        writer.writerows(results)
    return len(results)

def process_excel_file(input_file, output_file, valid_audiences):
    """Обрабатывает Excel файл и создает очищенную версию"""
    wb = load_workbook(input_file, data_only=True)
    ws = wb.active
    if ws is None:
        raise RuntimeError("Workbook has no active sheet")
    
    # Читаем заголовки
    headers = []
    for col in range(1, ws.max_column + 1):
        cell = ws.cell(1, col)
        if cell.value:
            headers.append(str(cell.value))
        else:
            headers.append(f'Column{col}')
    
    # Находим индексы нужных колонок
    subject_idx = None
    for i, header in enumerate(headers):
        if 'subject_name' in header.lower() or 'дисциплина' in header.lower():
            subject_idx = i
            break
    
    if subject_idx is None:
        print("Не найдена колонка с дисциплиной!")
        return 0
    
    # Добавляем новые колонки после subject_name
    new_headers = headers.copy()
    insert_idx = subject_idx + 1
    if 'audience_numerator' not in new_headers:
        new_headers.insert(insert_idx, 'audience_numerator')
        insert_idx += 1
    if 'audience_denominator' not in new_headers:
        new_headers.insert(insert_idx, 'audience_denominator')
        insert_idx += 1
    if 'lecture_type' not in new_headers:
        new_headers.insert(insert_idx, 'lecture_type')
    
    # Обрабатываем данные
    results = []
    for row_idx in range(2, ws.max_row + 1):
        row_data = {}
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row_idx, col_idx)
            row_data[header] = cell.value if cell.value else ''
        
        subject_name = row_data.get(headers[subject_idx], '')
        
        # Находим колонку с преподавателем
        teacher_idx = None
        for i, header in enumerate(headers):
            if 'fio' in header.lower() or 'teacher' in header.lower() or 'преподаватель' in header.lower():
                teacher_idx = i
                break
        
        teacher_fio = row_data.get(headers[teacher_idx], '') if teacher_idx is not None else ''
        existing_week_type = row_data.get('week_type', '') or row_data.get('week', '') or ''
        existing_lecture_type = row_data.get('lecture_type', '') or ''
        existing_audience = str(row_data.get('audience', '') or '').strip()
        # Строки, уже разбитые парсером (числитель/знаменатель с аудиторией), не переразбирать
        if existing_week_type in ('числитель', 'знаменатель') and existing_audience:
            processed_list = [{
                'audience': existing_audience,
                'subject_name': clean_subject_name_final(subject_name, valid_audiences),
                'lecture_type': existing_lecture_type or '',
                'week_type': existing_week_type
            }]
            if teacher_fio:
                processed_list[0]['teacher'] = teacher_fio
        else:
            processed_list = process_discipline_text(subject_name, valid_audiences, teacher_fio, existing_week_type, existing_lecture_type)
        
        # Создаем отдельную запись для каждой дисциплины/аудитории
        for processed in processed_list:
            new_row = row_data.copy()
            new_row['audience'] = normalize_audience_week_separator(processed['audience'])
            new_row['subject_name'] = processed['subject_name']
            new_row['lecture_type'] = processed['lecture_type']
            # Добавляем преподавателя и тип недели, если они есть
            if 'teacher' in processed:
                # Обновляем существующую колонку fio или teacher
                if teacher_idx is not None:
                    new_row[headers[teacher_idx]] = processed['teacher']
                elif 'fio' in new_row:
                    new_row['fio'] = processed['teacher']
            if 'week_type' in processed:
                new_row['week_type'] = processed['week_type']
            if 'subgroup' in processed:
                new_row['subgroup'] = processed['subgroup']
            # Удаляем старые поля, если они есть
            new_row.pop('audience_numerator', None)
            new_row.pop('audience_denominator', None)
            
            results.append(new_row)
    
    # Определяем новые заголовки (аналогично CSV)
    new_headers = []
    priority_fields = ['day_of_week', 'pair_number', 'subject_name', 'lecture_type', 'audience']
    
    # Добавляем приоритетные поля
    for field in priority_fields:
        if field in headers:
            new_headers.append(field)
    
    # Добавляем остальные поля (кроме старых audience_numerator, audience_denominator)
    for field in headers:
        if field not in new_headers and field not in ['audience_numerator', 'audience_denominator']:
            new_headers.append(field)
    
    # Убеждаемся, что audience и lecture_type есть в заголовках
    if 'audience' not in new_headers:
        if 'subject_name' in new_headers:
            idx = new_headers.index('subject_name') + 1
            new_headers.insert(idx, 'audience')
        else:
            new_headers.append('audience')
    
    if 'lecture_type' not in new_headers:
        if 'subject_name' in new_headers:
            idx = new_headers.index('subject_name') + 1
            new_headers.insert(idx, 'lecture_type')
        else:
            new_headers.append('lecture_type')
    
    # Убеждаемся, что week_type и subgroup есть в заголовках, если они используются
    if 'week_type' not in new_headers:
        for result in results:
            if 'week_type' in result and result.get('week_type'):
                new_headers.append('week_type')
                break
    if 'subgroup' not in new_headers:
        for result in results:
            if 'subgroup' in result and result.get('subgroup'):
                new_headers.append('subgroup')
                break
    
    # Создаем новый файл
    wb_new = Workbook()
    ws_new = wb_new.active
    if ws_new is None:
        raise RuntimeError("Workbook has no active sheet")
    
    # Записываем заголовки
    for col_idx, header in enumerate(new_headers, 1):
        cell = ws_new.cell(1, col_idx, value=header)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # Записываем данные
    for row_idx, row_data in enumerate(results, 2):
        for col_idx, header in enumerate(new_headers, 1):
            value = row_data.get(header, '')
            ws_new.cell(row_idx, col_idx, value=value)
    
    # Автоподбор ширины столбцов
    for col_idx, col in enumerate(ws_new.columns, 1):
        max_length = 0
        for cell in col:
            try:
                if cell.value:
                    length = len(str(cell.value))
                    if max_length < length:
                        max_length = length
            except Exception:
                pass
        adjusted_width = min(max_length + 2, 50)
        col_letter = get_column_letter(col_idx)
        ws_new.column_dimensions[col_letter].width = adjusted_width
    
    # Замораживаем первую строку
    ws_new.freeze_panes = 'A2'
    
    wb_new.save(output_file)
    return len(results)


def _to_int(value):
    if not value or value == '':
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _to_bool(value):
    if not value or value == '':
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', '1', 'yes', 't')
    return bool(value)


def _to_duration_pairs(val):
    """Преобразует значение в duration_pairs: 1, 1.5 или None."""
    if val is None or val == '':
        return None
    if isinstance(val, (int, float)):
        return float(val) if val else None
    s = str(val).strip().replace(',', '.')
    if not s:
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _row_dict_to_insert_tuple(row, valid_audiences, last_good_subject_name):
    """Преобразует одну строку (dict) в кортеж для INSERT в timetable_cleaned."""
    week_type_value = (row.get('week_type', '') or row.get('week', '') or row.get('week_ru', '') or None)
    group_name_value = (row.get('group_name', '') or row.get('group', '') or None)
    fio_value = (row.get('fio', '') or row.get('teacher', '') or None)
    teacher_value = (row.get('teacher', '') or row.get('fio', '') or None)
    subject_name_val = (row.get('subject_name', '') or '').strip() or None
    if subject_name_val and (subject_name_val == 'м зал' or subject_name_val in valid_audiences):
        subject_name_val = last_good_subject_name
    elif subject_name_val:
        last_good_subject_name = subject_name_val
    values = (
        row.get('day_of_week', '') or None,
        _to_int(row.get('pair_number', '')),
        subject_name_val,
        row.get('lecture_type', '') or None,
        row.get('audience', '') or None,
        fio_value,
        teacher_value,
        group_name_value,
        week_type_value,
        _to_int(row.get('subgroup', '')),
        row.get('institute', '') or None,
        row.get('course', '') or None,
        row.get('direction', '') or None,
        row.get('department', '') or None,
        _to_bool(row.get('is_external', '')),
        _to_bool(row.get('is_remote', '')),
        _to_int(row.get('num_subgroups', '')),
        _to_duration_pairs(row.get('duration_pairs', ''))
    )
    return values, last_good_subject_name


def read_excel_to_rows(excel_path):
    """Читает Excel в список словарей (учёт объединённых ячеек)."""
    wb = load_workbook(excel_path, data_only=True)
    ws = wb.active
    if ws is None:
        raise RuntimeError("Workbook has no active sheet")
    headers = []
    for col in range(1, ws.max_column + 1):
        cell = ws.cell(1, col)
        if cell.value:
            headers.append(str(cell.value))
    merged_ranges = list(ws.merged_cells.ranges) if getattr(ws, 'merged_cells', None) and ws.merged_cells else []

    def cell_value(row_idx, col_idx, header):
        cell = ws.cell(row=row_idx, column=col_idx)
        val = cell.value
        if val is not None and str(val).strip() != '':
            return val
        for mrange in merged_ranges:
            if mrange.min_row <= row_idx <= mrange.max_row and mrange.min_col <= col_idx <= mrange.max_col:
                top = ws.cell(row=mrange.min_row, column=mrange.min_col).value
                if header == 'pair_number' and mrange.max_row > mrange.min_row and row_idx > mrange.min_row:
                    base = 1
                    if top is not None:
                        try:
                            base = int(str(top))
                        except (TypeError, ValueError):
                            pass
                    return base + (row_idx - mrange.min_row)
                return top if top is not None else ''
        return ''

    rows_data = []
    for row_idx in range(2, ws.max_row + 1):
        row_data = {}
        for col_idx, header in enumerate(headers, 1):
            row_data[header] = cell_value(row_idx, col_idx, header)
        rows_data.append(row_data)
    return rows_data


def save_to_database(csv_file=None, rows_data=None):
    """Сохраняет данные в PostgreSQL. Либо rows_data (список dict), либо чтение из csv_file (устаревший путь)."""
    if rows_data is None and csv_file is None:
        return False
    try:
        import psycopg2  # type: ignore[import-untyped]
        from psycopg2.extras import execute_values  # type: ignore[import-untyped]
    except ImportError:
        print("Ошибка: библиотека psycopg2 не установлена. Установите её командой: pip install psycopg2-binary")
        return False

    db_config = {
        'host': os.environ.get('DB_HOST', 'edro.su'),
        'port': int(os.environ.get('DB_PORT', '50003')),
        'user': os.environ.get('DB_USER', 'edro'),
        'password': os.environ.get('DB_PASSWORD', 'Pg123!'),
        'database': os.environ.get('DB_NAME', 'test_sursu_timetable')
    }

    valid_audiences = load_audiences()
    last_good_subject_name = None
    rows_to_insert = []

    if rows_data is not None:
        for row in rows_data:
            values, last_good_subject_name = _row_dict_to_insert_tuple(row, valid_audiences, last_good_subject_name)
            rows_to_insert.append(values)
    else:
        if csv_file is None:
            return False
        with open(csv_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                values, last_good_subject_name = _row_dict_to_insert_tuple(row, valid_audiences, last_good_subject_name)
                rows_to_insert.append(values)

    if not rows_to_insert:
        print("Нет данных для загрузки в БД (пустой файл или 0 строк). Таблица не изменена.")
        return False

    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()

        create_table_query = """
        CREATE TABLE IF NOT EXISTS timetable_cleaned (
            id SERIAL PRIMARY KEY,
            day_of_week VARCHAR(50),
            pair_number INTEGER,
            subject_name TEXT,
            lecture_type VARCHAR(50),
            audience VARCHAR(50),
            fio TEXT,
            teacher TEXT,
            group_name VARCHAR(50),
            week_type VARCHAR(50),
            subgroup INTEGER,
            institute TEXT,
            course VARCHAR(10),
            direction TEXT,
            department TEXT,
            is_external BOOLEAN,
            is_remote BOOLEAN,
            num_subgroups INTEGER,
            duration_pairs NUMERIC(3,1),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        cursor.execute(create_table_query)
        conn.commit()
        print("Таблица timetable_cleaned создана или уже существует")
        cursor.execute("ALTER TABLE timetable_cleaned ADD COLUMN IF NOT EXISTS duration_pairs NUMERIC(3,1)")
        conn.commit()

        cursor.execute("TRUNCATE TABLE timetable_cleaned")
        conn.commit()
        print("Таблица timetable_cleaned очищена")

        if rows_to_insert:
            insert_query = """
            INSERT INTO timetable_cleaned (
                day_of_week, pair_number, subject_name, lecture_type, audience,
                fio, teacher, group_name, week_type, subgroup,
                institute, course, direction, department,
                is_external, is_remote, num_subgroups, duration_pairs
            ) VALUES %s
            """
            col_names = ('day_of_week', 'pair_number', 'subject_name', 'lecture_type', 'audience',
                        'fio', 'teacher', 'group_name', 'week_type', 'subgroup',
                        'institute', 'course', 'direction', 'department',
                        'is_external', 'is_remote', 'num_subgroups', 'duration_pairs')
            log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output', 'timetable')
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, 'load_to_db_log.jsonl')
            with open(log_path, 'w', encoding='utf-8') as log_f:
                for i, row_vals in enumerate(rows_to_insert):
                    row_dict = {col_names[j]: row_vals[j] for j in range(len(col_names))}
                    log_obj = {"insert_index": i + 1, "table": "timetable_cleaned", "row": row_dict}
                    log_f.write(json.dumps(log_obj, ensure_ascii=False) + '\n')
            print(f"Лог вставок записан в {log_path} ({len(rows_to_insert)} записей)")
            execute_values(cursor, insert_query, rows_to_insert)
            conn.commit()
            print(f"Успешно сохранено {len(rows_to_insert)} записей в базу данных")

        cursor.close()
        conn.close()
        return True

    except psycopg2.Error as e:
        print(f"Ошибка при работе с базой данных: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"Ошибка при сохранении в базу данных: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    import argparse
    import glob

    parser = argparse.ArgumentParser(description='Очистка аудиторий в расписании')
    parser.add_argument('--no-db', action='store_true', help='Только обработка файлов, без загрузки в БД')
    parser.add_argument('--db-only', action='store_true', help='Только загрузить timetable_processed_cleaned.xlsx в БД (без обработки)')
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.abspath(__file__))
    csv_output = os.path.join(project_root, 'output', 'timetable', 'timetable_processed_cleaned.csv')
    excel_output = os.path.join(project_root, 'output', 'timetable', 'timetable_processed_cleaned.xlsx')

    # Режим: только загрузка в БД (из Excel или CSV)
    if args.db_only:
        if os.path.exists(csv_output):
            print("Загрузка данных в базу данных из CSV...")
            try:
                with open(csv_output, 'r', encoding='utf-8-sig') as f:
                    n_csv_rows = sum(1 for _ in csv.DictReader(f))
                print(f"Строк в CSV для загрузки: {n_csv_rows}")
                if save_to_database(csv_file=csv_output):
                    print("Данные успешно сохранены в базу данных")
                else:
                    print("Не удалось сохранить данные в базу данных")
            except Exception as e:
                print(f"Ошибка: {e}")
                import traceback
                traceback.print_exc()
        elif os.path.exists(excel_output):
            print("Загрузка данных в базу данных из Excel...")
            try:
                rows_data = read_excel_to_rows(excel_output)
                print(f"Прочитано строк из Excel: {len(rows_data)}")
                if save_to_database(rows_data=rows_data):
                    print("Данные успешно сохранены в базу данных")
                else:
                    print("Не удалось сохранить данные в базу данных")
            except Exception as e:
                print(f"Ошибка: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"Не найден файл {excel_output} или {csv_output}. Сначала выполните обработку (clean_audiences).")
        return

    # Загружаем валидные аудитории (скрипт должен запускаться из корня проекта)
    os.chdir(project_root)
    valid_audiences = load_audiences()
    print(f"Загружено {len(valid_audiences)} валидных аудиторий")

    # Ищем исходные файлы (без _cleaned)
    csv_input = None
    excel_input = None

    csv_files = glob.glob(os.path.join(project_root, 'output', 'timetable', 'timetable_processed.csv'))
    if csv_files:
        csv_input = csv_files[0]

    excel_files = [f for f in glob.glob(os.path.join(project_root, 'output', 'timetable', 'timetable_processed.xlsx'))
                   if not os.path.basename(f).startswith('~$')]
    if excel_files:
        excel_input = excel_files[0]

    if not csv_input and not excel_input:
        print("Не найдены файлы timetable_processed.csv или timetable_processed.xlsx в output/timetable/")
        return

    # Гарантируем, что каталог для очищенных файлов существует
    os.makedirs(os.path.dirname(excel_output), exist_ok=True)

    # Обрабатываем CSV (результат в Excel и CSV)
    if csv_input:
        print(f"\nОбрабатываем CSV файл: {csv_input}")
        try:
            count = process_csv_file(csv_input, excel_output, valid_audiences)
            print(f"Обработано записей: {count}")
            print(f"Результат сохранен в: {csv_output}, {excel_output}")
        except Exception as e:
            print(f"Ошибка при обработке CSV файла: {e}")
            import traceback
            traceback.print_exc()

    # Обрабатываем Excel
    if excel_input:
        print(f"\nОбрабатываем Excel файл: {excel_input}")
        try:
            count = process_excel_file(excel_input, excel_output, valid_audiences)
            print(f"Обработано записей: {count}")
            print(f"Результат сохранен в: {excel_output}")
        except Exception as e:
            print(f"Ошибка при обработке Excel файла: {e}")
            import traceback
            traceback.print_exc()

    # Сохраняем в базу данных только если не указан --no-db
    if not args.no_db:
        if os.path.exists(csv_output):
            print(f"\nСохраняем данные в базу данных из CSV...")
            try:
                if save_to_database(csv_file=csv_output):
                    print("Данные успешно сохранены в базу данных")
                else:
                    print("Не удалось сохранить данные в базу данных")
            except Exception as e:
                print(f"Ошибка при сохранении в базу данных: {e}")
                import traceback
                traceback.print_exc()
        elif os.path.exists(excel_output):
            print(f"\nСохраняем данные в базу данных из Excel...")
            try:
                rows_data = read_excel_to_rows(excel_output)
                if save_to_database(rows_data=rows_data):
                    print("Данные успешно сохранены в базу данных")
                else:
                    print("Не удалось сохранить данные в базу данных")
            except Exception as e:
                print(f"Ошибка при сохранении в базу данных: {e}")
                import traceback
                traceback.print_exc()


if __name__ == '__main__':
    main()
