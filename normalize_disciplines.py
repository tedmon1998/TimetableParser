#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для нормализации названий дисциплин в JSON файле
Приводит сокращения к полным формам для единообразия
"""

import json
import re
from typing import Dict, List

# Словарь сокращений для нормализации
ABBREVIATIONS = {
    # Медицинские термины
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
    input_file = 'timetable.json'
    output_file = 'timetable_normalized.json'
    
    normalize_timetable(input_file, output_file)
    
    # Опционально: можно заменить исходный файл
    # import shutil
    # shutil.move(output_file, input_file)
    # print(f"\nИсходный файл {input_file} заменен нормализованной версией")

if __name__ == '__main__':
    main()

