#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Парсер расписания занятий из PDF файла
Извлекает данные в формате JSON
"""

import re
import json
import pdfplumber
from typing import List, Dict, Optional, Tuple

# Словарь для преобразования дней недели
DAYS_MAP = {
    'ПН': 'monday',
    'ВТ': 'tuesday', 
    'СР': 'wednesday',
    'ЧТ': 'thursday',
    'ПТ': 'friday',
    'СБ': 'saturday',
    'ВС': 'sunday'
}

def extract_room(text: str) -> Optional[str]:
    """Извлекает номер аудитории из текста"""
    # Паттерны для аудиторий: А436, У606, A2Б, A417, A423, A24, A22, A532, A533, A515, A539, A304, A516, A517, A504, A603, A615, A636, С, ЭОиДОТ
    # Ищем аудитории в формате: буква(А/У/A) + цифры + опциональная буква
    # Или специальные: С, ЭОиДОТ
    room_patterns = [
        r'([АУA]\d+[А-ЯA-Z]?)',  # А436, У606, A2Б, A24, A22
        r'([АУA]\d+)',            # A417, A423 (если нет буквы в конце)
        r'(ЭОиДОТ)',              # ЭОиДОТ
        r'([СC](?=\s|,|$))'       # С (отдельно стоящая)
    ]
    
    for pattern in room_patterns:
        match = re.search(pattern, text)
        if match:
            room = match.group(1)
            # Проверяем, что это не часть слова
            if room and len(room) > 1:  # Игнорируем одиночные буквы, кроме С
                return room
            elif room == 'С' or room == 'C':
                return 'С'
    
    return None

def parse_subject_and_room(text: str) -> List[Dict]:
    """
    Парсит текст дисциплины и извлекает записи для четных/нечетных недель.
    Возвращает список записей (может быть 1 или 2 записи)
    """
    if not text or text.strip() == '':
        return []
    
    text = text.strip()
    results = []
    
    # Проверяем наличие разделителя //
    has_separator = '//' in text
    
    if has_separator:
        parts = text.split('//')
        even_part = parts[0].strip() if len(parts) > 0 else ''
        odd_part = parts[1].strip() if len(parts) > 1 else ''
        
        # Обрабатываем четную неделю (до //)
        if even_part:
            even_room = extract_room(even_part)
            even_subject = even_part
            if even_room:
                even_subject = even_part.replace(even_room, '').strip()
            # Убираем информацию о часах (например, "лекция 10 ч", "лек 8ч")
            even_subject = re.sub(r'\(?лекция?\s+\d+\s*ч\)?', '', even_subject, flags=re.IGNORECASE)
            even_subject = re.sub(r'\(?лек\s+\d+\s*ч\)?', '', even_subject, flags=re.IGNORECASE)
            even_subject = re.sub(r'[,\s]+$', '', even_subject)
            even_subject = clean_subject_name(even_subject)
            
            if even_subject:
                results.append({
                    'subject': even_subject,
                    'room': even_room,
                    'even_week': True,
                    'odd_week': False
                })
        
        # Обрабатываем нечетную неделю (после //)
        if odd_part:
            odd_room = extract_room(odd_part)
            odd_subject = odd_part
            if odd_room:
                odd_subject = odd_part.replace(odd_room, '').strip()
            # Убираем информацию о часах
            odd_subject = re.sub(r'\(?лекция?\s+\d+\s*ч\)?', '', odd_subject, flags=re.IGNORECASE)
            odd_subject = re.sub(r'\(?лек\s+\d+\s*ч\)?', '', odd_subject, flags=re.IGNORECASE)
            odd_subject = re.sub(r'[,\s]+$', '', odd_subject)
            odd_subject = clean_subject_name(odd_subject)
            
            if odd_subject:
                results.append({
                    'subject': odd_subject,
                    'room': odd_room,
                    'even_week': False,
                    'odd_week': True
                })
    else:
        # Нет разделителя - каждую неделю
        room = extract_room(text)
        subject = text
        if room:
            subject = text.replace(room, '').strip()
        # Убираем информацию о часах
        subject = re.sub(r'\(?лекция?\s+\d+\s*ч\)?', '', subject, flags=re.IGNORECASE)
        subject = re.sub(r'\(?лек\s+\d+\s*ч\)?', '', subject, flags=re.IGNORECASE)
        subject = re.sub(r'[,\s]+$', '', subject)
        subject = clean_subject_name(subject)
        
        if subject:
            results.append({
                'subject': subject,
                'room': room,
                'even_week': True,
                'odd_week': True
            })
    
    return results

def extract_subgroup_number(text: str) -> Optional[int]:
    """Извлекает номер подгруппы из текста (например, п/г1, п/г2)"""
    if not text:
        return None
    # Ищем паттерны: п/г1, п/г 1, п/г2, п/г 2 и т.д.
    match = re.search(r'п/г\s*(\d+)', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None

def clean_subject_name(subject: str) -> str:
    """Очищает название дисциплины от лишних символов"""
    if not subject:
        return ""
    # Убираем лишние пробелы
    subject = re.sub(r'\s+', ' ', subject)
    subject = subject.strip()
    # Убираем запятые в начале и конце
    subject = re.sub(r'^,\s*', '', subject)
    subject = re.sub(r',\s*$', '', subject)
    # Убираем лишние запятые между словами
    subject = re.sub(r',\s*,', ',', subject)
    return subject

def parse_pdf(pdf_path: str) -> List[Dict]:
    """Парсит PDF файл и извлекает расписание"""
    results = []
    
    with pdfplumber.open(pdf_path) as pdf:
        current_institute = None
        current_course = None
        current_specialty = None
        current_groups = None
        current_period = None
        
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue
            
            lines = text.split('\n')
            
            # Парсим заголовок для получения метаданных
            for i, line in enumerate(lines):
                # Ищем институт (например: "Институт медицинский")
                if 'Институт' in line and not current_institute:
                    match = re.search(r'Институт\s+(\w+)', line)
                    if match:
                        current_institute = match.group(1)
                
                # Ищем курс (например: "1 Курс" или "Курс 1")
                if 'Курс' in line and not current_course:
                    match = re.search(r'(\d+)\s+Курс|Курс\s+(\d+)', line)
                    if match:
                        current_course = match.group(1) or match.group(2)
                
                # Ищем специальность и группу в одной строке
                # Пример: "Специальность31.05.01 Лечебное дело 501-51 Группа"
                if 'Специальность' in line or re.search(r'\d+\.\d+\.\d+', line):
                    # Пытаемся извлечь специальность и группу
                    match = re.search(r'Специальность\s*(\d+\.\d+\.\d+)\s+(.+?)(?:\s+(\d+(?:-\d+)*(?:,\d+(?:-\d+)*)*))?\s*Группа', line)
                    if match:
                        if not current_specialty:
                            current_specialty = match.group(1) + ' ' + match.group(2).strip()
                        if match.group(3) and not current_groups:
                            groups_str = match.group(3)
                            groups = re.split(r',', groups_str)
                            current_groups = [g.strip() for g in groups if g.strip()]
                    else:
                        # Пытаемся извлечь только специальность
                        match = re.search(r'Специальность\s*(\d+\.\d+\.\d+)\s+(.+?)(?:\s+Группа)', line)
                        if match and not current_specialty:
                            current_specialty = match.group(1) + ' ' + match.group(2).strip()
                
                # Ищем группы отдельно
                if 'Группа' in line and not current_groups:
                    # Ищем группы перед словом "Группа"
                    match = re.search(r'(\d+(?:-\d+)*(?:,\d+(?:-\d+)*)*)\s+Группа', line)
                    if match:
                        groups_str = match.group(1).strip()
                        groups = re.split(r',', groups_str)
                        current_groups = [g.strip() for g in groups if g.strip()]
                
                # Ищем период
                if 'ТО' in line and not current_period:
                    match = re.search(r'ТО\s+(\d{2}\.\d{2}\.\d{4})-(\d{2}\.\d{2}\.\d{4})', line)
                    if match:
                        current_period = f"{match.group(1)}-{match.group(2)}"
            
            # Парсим таблицу
            tables = page.extract_tables()
            for table in tables:
                if not table:
                    continue
                
                # Парсим метаданные из первой строки таблицы (если они там есть)
                if len(table) > 0 and len(table[0]) > 2:
                    first_row_text = table[0][2] if table[0][2] else ''
                    if first_row_text:
                        # Парсим метаданные из текста первой строки
                        # Формат: "2025-2026 весенний\nмедицинский 1\n31.05.01 Лечебное дело 501-51\n02.02.2026-06.06.2026"
                        lines_meta = first_row_text.split('\n')
                        for meta_line in lines_meta:
                            meta_line = meta_line.strip()
                            # Парсим институт и курс (например: "медицинский 1")
                            if 'медицинский' in meta_line.lower():
                                match = re.search(r'медицинский\s+(\d+)', meta_line, re.IGNORECASE)
                                if match:
                                    if not current_institute:
                                        current_institute = 'медицинский'
                                    if not current_course:
                                        current_course = match.group(1)
                            # Парсим специальность и группу (например: "31.05.01 Лечебное дело 501-51")
                            if re.search(r'\d+\.\d+\.\d+', meta_line):
                                # Извлекаем специальность и группу
                                match = re.search(r'(\d+\.\d+\.\d+)\s+(.+?)(?:\s+(\d+(?:-\d+)*(?:,\d+(?:-\d+)*)*))?', meta_line)
                                if match:
                                    if not current_specialty:
                                        current_specialty = match.group(1) + ' ' + match.group(2).strip()
                                    if match.group(3) and not current_groups:
                                        # Разбиваем группы
                                        groups_str = match.group(3)
                                        groups = re.split(r',', groups_str)
                                        current_groups = [g.strip() for g in groups if g.strip()]
                            # Парсим период
                            if re.search(r'\d{2}\.\d{2}\.\d{4}', meta_line):
                                if not current_period:
                                    match = re.search(r'(\d{2}\.\d{2}\.\d{4})-(\d{2}\.\d{2}\.\d{4})', meta_line)
                                    if match:
                                        current_period = f"{match.group(1)}-{match.group(2)}"
                
                current_day = None
                current_period_num = None
                
                for row in table:
                    if not row or len(row) < 3:
                        continue
                    
                    # Структура таблицы:
                    # Колонка 0: день недели (ПН) или пусто
                    # Колонка 1: номер пары (1, 2, 3...)
                    # Колонка 2: дисциплина (может содержать несколько подгрупп через пробелы или разделители)
                    # Колонка 3: обычно None или дополнительная информация
                    
                    day_col = row[0] if row[0] else ''
                    day_col = day_col.strip() if day_col else ''
                    
                    period_col = row[1] if row[1] else ''
                    period_col = period_col.strip() if period_col else ''
                    
                    discipline_col = row[2] if row[2] else ''
                    discipline_col = discipline_col.strip() if discipline_col else ''
                    
                    # Проверяем, является ли первая колонка днем недели
                    if day_col in DAYS_MAP:
                        current_day = DAYS_MAP[day_col]
                        # Если во второй колонке есть номер пары, сохраняем его
                        if period_col.isdigit():
                            current_period_num = int(period_col)
                        continue
                    
                    # Если первая колонка пустая, но есть день недели из предыдущей строки
                    # Проверяем вторую колонку на номер пары
                    if period_col.isdigit():
                        current_period_num = int(period_col)
                    
                    # Если есть дисциплина и известны день и пара
                    if discipline_col and current_day and current_period_num:
                        # Дисциплина может содержать несколько подгрупп, разделенных пробелами
                        # Или может быть в разных колонках (колонка 2 и колонка 3)
                        subgroups = []
                        
                        # Проверяем, есть ли подгруппы в колонке 3
                        if len(row) > 3 and row[3]:
                            # Есть две колонки с дисциплинами - это две подгруппы
                            subgroups.append(discipline_col)
                            subgroups.append(row[3].strip() if row[3] else '')
                        else:
                            # Пытаемся разделить по пробелам (если есть несколько подгрупп в одной ячейке)
                            # Но обычно подгруппы разделены явно или находятся в разных колонках
                            # Для начала просто используем всю строку как одну подгруппу
                            subgroups.append(discipline_col)
                        
                        # Обрабатываем подгруппы
                        num_subgroups = len([s for s in subgroups if s and s.strip()])
                        
                        for subgroup_idx, subgroup_text in enumerate(subgroups):
                            # Если ячейка пустая, пропускаем (подгруппа не ходит в это время)
                            if not subgroup_text or subgroup_text.strip() == '':
                                continue
                            
                            # Парсим дисциплину и аудиторию (может вернуть несколько записей для четных/нечетных)
                            parsed_items = parse_subject_and_room(subgroup_text)
                            
                            # Определяем тип занятия (лек, пр, п/г)
                            lesson_type = None
                            if '(лек' in subgroup_text.lower() or 'лекция' in subgroup_text.lower():
                                lesson_type = 'lecture'
                            elif '(пр' in subgroup_text.lower() or 'практическое' in subgroup_text.lower():
                                lesson_type = 'practice'
                            elif 'п/г' in subgroup_text.lower() or 'п/г' in subgroup_text:
                                lesson_type = 'subgroup'
                            # Если тип не определен, пытаемся определить по контексту
                            if not lesson_type:
                                # Проверяем наличие сокращений
                                if re.search(r'\(лек', subgroup_text, re.IGNORECASE):
                                    lesson_type = 'lecture'
                                elif re.search(r'\(пр', subgroup_text, re.IGNORECASE):
                                    lesson_type = 'practice'
                            
                            # Определяем номер подгруппы
                            # Сначала пытаемся извлечь из текста (п/г1, п/г2 и т.д.)
                            subgroup_number = extract_subgroup_number(subgroup_text)
                            
                            # Если не нашли в тексте, используем индекс колонки (если несколько колонок)
                            if subgroup_number is None:
                                if num_subgroups > 1:
                                    subgroup_number = subgroup_idx + 1
                                else:
                                    subgroup_number = None
                            
                            # Создаем записи для каждой распарсенной части (четная/нечетная неделя)
                            for parsed_item in parsed_items:
                                # Создаем запись для каждой группы
                                if current_groups:
                                    for group in current_groups:
                                        entry = {
                                            'discipline': parsed_item['subject'],
                                            'group': group,
                                            'day_of_week': current_day,
                                            'room': parsed_item['room'],
                                            'period': current_period_num,
                                            'institute': current_institute,
                                            'specialty': current_specialty,
                                            'course': current_course,
                                            'even_week': parsed_item['even_week'],
                                            'odd_week': parsed_item['odd_week'],
                                            'subgroup': subgroup_number,
                                            'lesson_type': lesson_type,
                                            'period_dates': current_period
                                        }
                                        results.append(entry)
                                else:
                                    # Если группы не найдены, создаем запись без группы
                                    entry = {
                                        'discipline': parsed_item['subject'],
                                        'group': None,
                                        'day_of_week': current_day,
                                        'room': parsed_item['room'],
                                        'period': current_period_num,
                                        'institute': current_institute,
                                        'specialty': current_specialty,
                                        'course': current_course,
                                        'even_week': parsed_item['even_week'],
                                        'odd_week': parsed_item['odd_week'],
                                        'subgroup': subgroup_number,
                                        'lesson_type': lesson_type,
                                        'period_dates': current_period
                                    }
                                    results.append(entry)
    
    return results

def main():
    import sys
    import os
    from pathlib import Path
    
    # Определяем пути к папкам
    pdfs_dir = 'schedules_pdf'
    jsons_dir = 'schedules_json'
    
    # Создаем папку для JSON, если её нет
    Path(jsons_dir).mkdir(exist_ok=True)
    
    # Если указан файл как аргумент
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        if not os.path.exists(pdf_path):
            print(f"Ошибка: файл {pdf_path} не найден")
            return
    else:
        # Ищем PDF файлы в папке schedules_pdf или текущей директории
        if os.path.exists(pdfs_dir):
            pdf_files = list(Path(pdfs_dir).glob('*.pdf'))
            if pdf_files:
                print(f"Найдено PDF файлов в {pdfs_dir}: {len(pdf_files)}")
                # Парсим все файлы
                for pdf_file in pdf_files:
                    print(f"\n{'='*60}")
                    print(f"Парсинг файла: {pdf_file.name}")
                    print(f"{'='*60}")
                    results = parse_pdf(str(pdf_file))
                    
                    # Создаем имя JSON файла на основе имени PDF
                    json_name = pdf_file.stem + '.json'
                    output_path = os.path.join(jsons_dir, json_name)
                    
                    print(f"Найдено записей: {len(results)}")
                    
                    # Сохраняем в JSON
                    with open(output_path, 'w', encoding='utf-8') as f:
                        json.dump(results, f, ensure_ascii=False, indent=2)
                    
                    print(f"Результаты сохранены в {output_path}")
                return
            else:
                print(f"В папке {pdfs_dir} не найдено PDF файлов")
        
        # Пробуем найти в текущей директории
        pdf_files = list(Path('.').glob('*.pdf'))
        if pdf_files:
            print(f"Найдено PDF файлов в текущей директории: {len(pdf_files)}")
            for pdf_file in pdf_files:
                print(f"\n{'='*60}")
                print(f"Парсинг файла: {pdf_file.name}")
                print(f"{'='*60}")
                results = parse_pdf(str(pdf_file))
                
                json_name = pdf_file.stem + '.json'
                output_path = os.path.join(jsons_dir, json_name)
                
                print(f"Найдено записей: {len(results)}")
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
                
                print(f"Результаты сохранены в {output_path}")
            return
        
        # Если ничего не найдено, используем файл по умолчанию
        pdf_path = 'Lechebnoe delo-13-01-26.pdf'
        if not os.path.exists(pdf_path):
            print("Ошибка: не найдено PDF файлов для парсинга")
            print("Использование: python3 parse_timetable.py [путь_к_pdf_файлу]")
            print("Или поместите PDF файлы в папку schedules_pdf/")
            return
    
    # Парсим один файл
    output_name = Path(pdf_path).stem + '.json'
    output_path = os.path.join(jsons_dir, output_name)
    
    print(f"Парсинг файла {pdf_path}...")
    results = parse_pdf(pdf_path)
    
    print(f"Найдено записей: {len(results)}")
    
    # Сохраняем в JSON
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"Результаты сохранены в {output_path}")
    
    # Выводим примеры
    if results:
        print("\nПримеры записей:")
        for i, entry in enumerate(results[:3]):
            print(f"\n{i+1}. {json.dumps(entry, ensure_ascii=False, indent=2)}")

if __name__ == '__main__':
    main()

