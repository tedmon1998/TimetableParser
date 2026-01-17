#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для проверки достоверности данных расписания
Сравнивает timetable.json с данными из CSV файла занятости преподавателей
"""

import json
import csv
import re
from typing import Dict, List, Set, Tuple
from collections import defaultdict

# Маппинг дней недели
DAYS_MAP = {
    'monday': 'понедельник',
    'tuesday': 'вторник',
    'wednesday': 'среда',
    'thursday': 'четверг',
    'friday': 'пятница',
    'saturday': 'суббота',
    'sunday': 'воскресенье'
}

DAYS_MAP_REVERSE = {v: k for k, v in DAYS_MAP.items()}

def parse_group_string(group_str: str) -> Set[str]:
    """Парсит строку с группами (может быть несколько через запятую или дефис)"""
    if not group_str:
        return set()
    
    groups = set()
    # Разбиваем по запятым
    parts = group_str.split(',')
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        # Проверяем, есть ли дефис (диапазон)
        if '-' in part and not part.startswith('-'):
            # Может быть диапазон типа "501-21-501-24" или просто "501-51"
            if part.count('-') == 1:
                # Просто номер группы
                groups.add(part)
            else:
                # Сложный диапазон, оставляем как есть
                groups.add(part)
        else:
            groups.add(part)
    
    return groups

def normalize_room(room: str) -> str:
    """Нормализует название аудитории"""
    if not room:
        return ''
    return room.strip().upper()

def load_csv_data(csv_file: str) -> Dict:
    """
    Загружает данные из CSV файла занятости преподавателей
    Возвращает структуру: {группа: {день: {пара: {аудитория: [преподаватели]}}}}
    """
    csv_data = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list))))
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            teacher = row.get('ФИО преподавателя', '').strip()
            if not teacher:
                continue
            
            # Обрабатываем каждый день недели
            days = {
                'понедельник': ('понедельник', 'аудитория'),
                'вторник': ('вторник', 'аудитория.'),
                'среда': ('среда', 'аудитория..'),
                'четверг': ('четверг', 'аудитория_'),
                'пятница': ('пятница', 'аудитория_'),
                'суббота': ('суббота', 'аудитория…')
            }
            
            for day_name, (day_col, room_col) in days.items():
                groups_str = row.get(day_col, '').strip()
                room = row.get(room_col, '').strip()
                period = row.get('пара', '').strip()
                
                if not groups_str or not period or not period.isdigit():
                    continue
                
                period_num = int(period)
                groups = parse_group_string(groups_str)
                normalized_room = normalize_room(room)
                
                for group in groups:
                    csv_data[group][day_name][period_num][normalized_room].append(teacher)
    
    return dict(csv_data)

def load_json_data(json_file: str) -> List[Dict]:
    """Загружает данные из JSON файла расписания"""
    with open(json_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def validate_data(json_data: List[Dict], csv_data: Dict) -> List[Dict]:
    """
    Проверяет достоверность данных JSON по сравнению с CSV
    Возвращает список несоответствий
    """
    errors = []
    
    for entry in json_data:
        group = entry.get('group')
        day_of_week = entry.get('day_of_week')
        period = entry.get('period')
        room = entry.get('room')
        discipline = entry.get('discipline', '')
        
        # Пропускаем записи без группы или с пустой дисциплиной
        if not group or not discipline or discipline.strip() == '':
            continue
        
        # Пропускаем записи с дефисами (это служебные записи)
        if discipline.startswith('-') or discipline.startswith('СОКБ'):
            continue
        
        # Преобразуем день недели
        day_ru = DAYS_MAP.get(day_of_week)
        if not day_ru:
            errors.append({
                'type': 'unknown_day',
                'entry': entry,
                'message': f'Неизвестный день недели: {day_of_week}'
            })
            continue
        
        # Проверяем наличие группы в CSV
        if group not in csv_data:
            errors.append({
                'type': 'group_not_found',
                'entry': entry,
                'message': f'Группа {group} не найдена в CSV файле'
            })
            continue
        
        # Проверяем наличие дня недели для группы
        if day_ru not in csv_data[group]:
            errors.append({
                'type': 'day_not_found',
                'entry': entry,
                'message': f'Для группы {group} нет занятий в {day_ru}'
            })
            continue
        
        # Проверяем наличие пары
        if period not in csv_data[group][day_ru]:
            errors.append({
                'type': 'period_not_found',
                'entry': entry,
                'message': f'Для группы {group} в {day_ru} нет пары {period}'
            })
            continue
        
        # Проверяем аудиторию
        normalized_room = normalize_room(room) if room else ''
        rooms_in_csv = set(csv_data[group][day_ru][period].keys())
        
        if normalized_room and normalized_room not in rooms_in_csv:
            # Проверяем, есть ли вообще занятия в эту пару
            if rooms_in_csv:
                errors.append({
                    'type': 'room_mismatch',
                    'entry': entry,
                    'message': f'Аудитория {room} не совпадает с CSV. Ожидаемые: {", ".join(rooms_in_csv)}',
                    'expected_rooms': list(rooms_in_csv)
                })
            else:
                errors.append({
                    'type': 'no_room_in_csv',
                    'entry': entry,
                    'message': f'В CSV для группы {group} в {day_ru} пара {period} нет аудитории'
                })
        elif not normalized_room and rooms_in_csv:
            errors.append({
                'type': 'missing_room',
                'entry': entry,
                'message': f'В JSON нет аудитории, но в CSV есть: {", ".join(rooms_in_csv)}',
                'expected_rooms': list(rooms_in_csv)
            })
    
    return errors

def save_errors(errors: List[Dict], output_file: str):
    """Сохраняет ошибки в JSON файл"""
    # Группируем ошибки по типам
    errors_by_type = defaultdict(list)
    for error in errors:
        errors_by_type[error['type']].append(error)
    
    report = {
        'total_errors': len(errors),
        'errors_by_type': {k: len(v) for k, v in errors_by_type.items()},
        'errors': errors
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\nОтчет сохранен в {output_file}")
    print(f"\nСтатистика ошибок:")
    for error_type, count in errors_by_type.items():
        print(f"  {error_type}: {count}")

def main():
    json_file = 'timetable.json'
    csv_file = 'Zanyatost prepodavateley_ vesenniy semestr 2025-2026-14-01-26.csv'
    output_file = 'validation_errors.json'
    
    print(f"Загрузка данных из {json_file}...")
    json_data = load_json_data(json_file)
    print(f"Загружено {len(json_data)} записей из JSON")
    
    print(f"\nЗагрузка данных из {csv_file}...")
    csv_data = load_csv_data(csv_file)
    print(f"Загружено данных для {len(csv_data)} групп из CSV")
    
    print(f"\nПроверка достоверности данных...")
    errors = validate_data(json_data, csv_data)
    
    print(f"\nНайдено ошибок: {len(errors)}")
    
    if errors:
        save_errors(errors, output_file)
        
        # Выводим примеры ошибок
        print(f"\nПримеры ошибок:")
        for i, error in enumerate(errors[:10]):
            print(f"\n{i+1}. {error['type']}: {error['message']}")
            entry = error['entry']
            print(f"   Группа: {entry.get('group')}, День: {entry.get('day_of_week')}, Пара: {entry.get('period')}")
            print(f"   Дисциплина: {entry.get('discipline')}")
            print(f"   Аудитория: {entry.get('room')}")
        if len(errors) > 10:
            print(f"\n... и еще {len(errors) - 10} ошибок")
    else:
        print("\nОшибок не найдено! Все данные соответствуют CSV файлу.")

if __name__ == '__main__':
    main()

