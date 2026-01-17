#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для нормализации названий дисциплин в JSON файле
Приводит сокращения к полным формам для единообразия
"""

import json
import re
import os
from typing import Dict, List

def load_abbreviations(abbrev_file: str = 'abbreviations.json') -> Dict[str, str]:
    """
    Загружает сокращения из JSON файла
    Если файл не найден, возвращает пустой словарь
    """
    try:
        with open(abbrev_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Объединяем все сокращения из разных категорий
            abbreviations = {}
            if 'abbreviations' in data:
                for category in data['abbreviations'].values():
                    abbreviations.update(category)
            return abbreviations
    except FileNotFoundError:
        print(f"Предупреждение: файл {abbrev_file} не найден. Используются встроенные сокращения.")
        return get_default_abbreviations()
    except json.JSONDecodeError as e:
        print(f"Ошибка при чтении {abbrev_file}: {e}. Используются встроенные сокращения.")
        return get_default_abbreviations()

def get_default_abbreviations() -> Dict[str, str]:
    """Возвращает сокращения по умолчанию, если файл не найден"""
    return {
        r'\bМедиц\.': 'Медицинская',
        r'\bмедиц\.': 'медицинская',
        r'\bэмбр\.': 'эмбриология',
        r'\bЭмбр\.': 'Эмбриология',
        r'\bцитол\.': 'цитология',
        r'\bЦитол\.': 'Цитология',
        r'\bцит\.': 'цитология',
        r'\bЦит\.': 'Цитология',
        r'\bвирусол\.': 'вирусология',
        r'\bВирусол\.': 'Вирусология',
        r'\bвирус\.': 'вирусология',
        r'\bВирус\.': 'Вирусология',
        r'\bанат\.': 'анатомия',
        r'\bАнат\.': 'Анатомия',
        r'\bфизиол\.': 'физиология',
        r'\bФизиол\.': 'Физиология',
        r'\bпат\.': 'патологическая',
        r'\bПат\.': 'Патологическая',
        r'\bнормальн\.': 'нормальная',
        r'\bНормальн\.': 'Нормальная',
        r'\bвозр\.': 'возрастная ',
        r'\bВозр\.': 'Возрастная ',
        r'\bопер\.': 'оперативная ',
        r'\bОпер\.': 'Оперативная ',
        r'\bадап\.': 'адаптационная ',
        r'\bАдап\.': 'Адаптационная ',
        r'\bхир\.': 'хирургия',
        r'\bХир\.': 'Хирургия',
        r'\bтоп\.': 'топографическая',
        r'\bТоп\.': 'Топографическая',
        r'\bпроф\.': 'профессиональной',
        r'\bПроф\.': 'Профессиональной',
        r'\bсфере': 'сфере',
        r'\bИн\.': 'Иностранный',
        r'\bин\.': 'иностранный',
        r'\bГЧ': 'генетики человека',
        r'\bгч': 'генетики человека',
    }

# Загружаем сокращения при импорте модуля
ABBREVIATIONS = load_abbreviations()

# Дополнительные правила нормализации для полных названий
NORMALIZATION_RULES = [
    # Убираем лишние пробелы
    (r'\s+', ' '),
    # Убираем пробелы перед запятыми
    (r'\s+,', ','),
    # Добавляем пробелы после запятых
    (r',([^\s])', r', \1'),
    # Нормализуем скобки
    (r'\(', '('),
    (r'\)', ')'),
    # Нормализуем п/г (подгруппа)
    (r'п/г\s*(\d+)', r'п/г \1'),
    (r'п/г(\d+)', r'п/г \1'),
]

def normalize_discipline_name(name: str) -> str:
    """
    Нормализует название дисциплины:
    - Расшифровывает сокращения
    - Приводит к единому формату
    """
    if not name:
        return name
    
    result = name
    
    # Применяем замену сокращений
    for pattern, replacement in ABBREVIATIONS.items():
        result = re.sub(pattern, replacement, result)
    
    # Исправляем случаи, когда после замены сокращения нет пробела перед следующим словом
    # Например: "возрастнаяфизиология" -> "возрастная физиология"
    result = re.sub(r'([а-яёА-ЯЁ])([А-ЯЁ][а-яё]+)', r'\1 \2', result)
    
    # Применяем дополнительные правила нормализации
    for pattern, replacement in NORMALIZATION_RULES:
        result = re.sub(pattern, replacement, result)
    
    # Убираем лишние пробелы в начале и конце
    result = result.strip()
    
    # Убираем множественные пробелы
    result = re.sub(r'\s+', ' ', result)
    
    return result

def normalize_timetable(input_file: str, output_file: str = None):
    """
    Нормализует названия дисциплин в JSON файле расписания
    """
    if output_file is None:
        output_file = input_file.replace('.json', '_normalized.json')
    
    print(f"Чтение файла {input_file}...")
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Найдено записей: {len(data)}")
    
    # Собираем статистику изменений
    changes = {}
    normalized_count = 0
    
    # Нормализуем каждую запись
    for entry in data:
        if 'discipline' in entry and entry['discipline']:
            original = entry['discipline']
            normalized = normalize_discipline_name(original)
            
            if original != normalized:
                if original not in changes:
                    changes[original] = normalized
                entry['discipline'] = normalized
                normalized_count += 1
    
    print(f"\nНормализовано записей: {normalized_count}")
    print(f"Уникальных изменений: {len(changes)}")
    
    if changes:
        print("\nПримеры изменений:")
        for i, (original, normalized) in enumerate(list(changes.items())[:10]):
            print(f"  {i+1}. '{original}' -> '{normalized}'")
        if len(changes) > 10:
            print(f"  ... и еще {len(changes) - 10} изменений")
    
    # Сохраняем результат
    print(f"\nСохранение в {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"Готово! Результат сохранен в {output_file}")
    
    # Выводим статистику по уникальным дисциплинам
    unique_disciplines = set([entry.get('discipline', '') for entry in data if entry.get('discipline')])
    print(f"\nУникальных дисциплин после нормализации: {len(unique_disciplines)}")
    
    return data, changes

def main():
    import sys
    from pathlib import Path
    
    # Можно указать файл с сокращениями как аргумент
    if len(sys.argv) > 1 and not sys.argv[1].endswith('.json'):
        abbrev_file = sys.argv[1]
    else:
        abbrev_file = 'abbreviations.json'
    
    # Перезагружаем сокращения
    global ABBREVIATIONS
    ABBREVIATIONS = load_abbreviations(abbrev_file)
    print(f"Загружено сокращений: {len(ABBREVIATIONS)}")
    
    # Определяем входные файлы
    jsons_dir = 'schedules_json'
    
    # Если указан конкретный файл
    if len(sys.argv) > 1 and sys.argv[1].endswith('.json') and os.path.exists(sys.argv[1]):
        input_files = [sys.argv[1]]
    elif os.path.exists(jsons_dir):
        # Ищем все JSON файлы в папке
        input_files = list(Path(jsons_dir).glob('*.json'))
        if not input_files:
            # Пробуем текущую директорию
            input_files = list(Path('.').glob('timetable*.json'))
    else:
        # Используем файл по умолчанию
        input_files = ['timetable.json'] if os.path.exists('timetable.json') else []
    
    if not input_files:
        print("Не найдено JSON файлов для нормализации")
        print("Использование: python3 normalize_disciplines.py [файл.json]")
        print("Или поместите JSON файлы в папку schedules_json/")
        return
    
    print(f"Найдено JSON файлов: {len(input_files)}")
    
    # Нормализуем каждый файл
    for input_file in input_files:
        input_file = str(input_file)
        print(f"\n{'='*60}")
        print(f"Обработка: {input_file}")
        print(f"{'='*60}")
        
        # Создаем имя выходного файла в папке schedules_parsed/
        parsed_dir = 'schedules_parsed'
        Path(parsed_dir).mkdir(exist_ok=True)
        
        # Берем только имя файла без пути
        base_name = os.path.basename(input_file)
        # Убираем расширение и добавляем _normalized
        if base_name.endswith('.json'):
            base_name = base_name[:-5]  # Убираем .json
        output_file = os.path.join(parsed_dir, base_name + '_normalized.json')
        
        normalize_timetable(input_file, output_file)
    
    # Опционально: можно заменить исходный файл
    # import shutil
    # shutil.move(output_file, input_file)
    # print(f"\nИсходный файл {input_file} заменен нормализованной версией")

if __name__ == '__main__':
    main()

