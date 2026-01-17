#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для автоматического извлечения сокращений из файлов расписаний
Анализирует все JSON файлы расписаний и находит новые сокращения
"""

import json
import re
import glob
from collections import defaultdict
from typing import Dict, Set, List

def load_existing_abbreviations(abbrev_file: str = None) -> Dict[str, str]:
    """
    Загружает существующие сокращения из JSON файла или всех файлов abbreviations*.json
    """
    abbreviations = {}
    
    if abbrev_file:
        # Загружаем конкретный файл
        files_to_load = [abbrev_file]
    else:
        # Ищем все файлы abbreviations*.json
        files_to_load = glob.glob('abbreviations*.json')
    
    for file_path in files_to_load:
        try:
            file_abbrev = {}
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Объединяем все сокращения из разных категорий
                if 'abbreviations' in data:
                    for category in data['abbreviations'].values():
                        file_abbrev.update(category)
            
            # Объединяем с общим словарем
            before_count = len(abbreviations)
            abbreviations.update(file_abbrev)
            added_count = len(abbreviations) - before_count
            print(f"  Загружено из {file_path}: {added_count} сокращений (всего в файле: {len(file_abbrev)})")
        except FileNotFoundError:
            continue
        except json.JSONDecodeError as e:
            print(f"Ошибка при чтении {file_path}: {e}")
            continue
    
    return abbreviations

def extract_disciplines_from_json(json_file: str) -> Set[str]:
    """Извлекает все уникальные названия дисциплин из JSON файла"""
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            disciplines = set()
            for entry in data:
                discipline = entry.get('discipline', '')
                if discipline and discipline.strip():
                    disciplines.add(discipline.strip())
            return disciplines
    except Exception as e:
        print(f"Ошибка при чтении {json_file}: {e}")
        return set()

def get_known_abbrev_patterns() -> Dict[str, str]:
    """Возвращает словарь известных паттернов сокращений"""
    return {
        'медиц': 'медицинская',
        'эмбр': 'эмбриология',
        'цитол': 'цитология',
        'цит': 'цитология',
        'вирусол': 'вирусология',
        'вирус': 'вирусология',
        'анат': 'анатомия',
        'физиол': 'физиология',
        'пат': 'патологическая',
        'нормальн': 'нормальная',
        'возр': 'возрастная',
        'опер': 'оперативная',
        'адап': 'адаптационная',
        'хир': 'хирургия',
        'топ': 'топографическая',
        'проф': 'профессиональной',
        'ин': 'иностранный',
        'гч': 'генетики человека',
    }

def add_known_patterns_to_existing(existing: Dict[str, str], add_all: bool = False) -> Dict[str, str]:
    """
    Добавляет известные паттерны сокращений в существующий словарь
    Если add_all=True, добавляет все известные паттерны, даже если их нет в existing
    """
    known_patterns = get_known_abbrev_patterns()
    added = {}
    
    for abbrev, full_form in known_patterns.items():
        # Создаем паттерны для разных регистров
        patterns = [
            (f"\\b{abbrev.capitalize()}\\.", full_form.capitalize()),
            (f"\\b{abbrev.lower()}\\.", full_form.lower()),
        ]
        
        # Для аббревиатур без точки (ГЧ)
        if len(abbrev) <= 4:
            patterns.extend([
                (f"\\b{abbrev.upper()}\\b", full_form),
                (f"\\b{abbrev.lower()}\\b", full_form),
            ])
        
        for pattern, replacement in patterns:
            if pattern not in existing:
                existing[pattern] = replacement
                added[pattern] = replacement
            elif add_all and existing[pattern] != replacement:
                # Обновляем, если add_all=True
                existing[pattern] = replacement
                added[pattern] = replacement
    
    return added

def find_abbreviations(disciplines: Set[str], existing: Dict[str, str]) -> Dict[str, str]:
    """
    Находит потенциальные сокращения в названиях дисциплин
    Использует известные паттерны и анализирует текст
    """
    known_abbrev_patterns = get_known_abbrev_patterns()
    
    found_abbrev = {}
    potential_expansions = defaultdict(list)
    
    # Паттерны для поиска сокращений в тексте
    abbreviation_patterns = [
        r'\b([А-ЯЁ][а-яё]{0,4})\.',  # Сокращения типа "Медиц.", "эмбр."
        r'\b([А-ЯЁ]{1,4})\b',        # Аббревиатуры типа "ГЧ", "ПВБ" (без точки)
    ]
    
    for discipline in disciplines:
        # Ищем сокращения с точкой
        for match in re.finditer(r'\b([А-ЯЁ][а-яё]{0,4})\.', discipline):
            abbrev = match.group(1)
            abbrev_lower = abbrev.lower()
            
            # Проверяем, есть ли уже такое сокращение
            pattern_key = f"\\b{re.escape(abbrev)}\\."
            if pattern_key in existing:
                continue
            
            # Используем известные паттерны
            if abbrev_lower in known_abbrev_patterns:
                full_form = known_abbrev_patterns[abbrev_lower]
                # Определяем регистр первой буквы
                if abbrev[0].isupper():
                    full_form = full_form.capitalize()
                found_abbrev[pattern_key] = full_form
                continue
            
            # Собираем контекст для анализа
            potential_expansions[abbrev].append(discipline)
        
        # Ищем аббревиатуры без точки (типа "ГЧ")
        for match in re.finditer(r'\b([А-ЯЁ]{2,4})\b', discipline):
            abbrev = match.group(1)
            abbrev_lower = abbrev.lower()
            
            # Пропускаем слишком короткие или длинные
            if len(abbrev) < 2 or len(abbrev) > 4:
                continue
            
            # Проверяем известные аббревиатуры
            pattern_key = f"\\b{re.escape(abbrev)}\\b"
            if pattern_key in existing:
                continue
            
            if abbrev_lower in known_abbrev_patterns:
                full_form = known_abbrev_patterns[abbrev_lower]
                found_abbrev[pattern_key] = full_form
                continue
    
    # Анализируем найденные сокращения, для которых не нашли известный паттерн
    for abbrev, contexts in potential_expansions.items():
        if abbrev.lower() in known_abbrev_patterns:
            continue  # Уже обработали
        
        if len(contexts) >= 2:  # Если встречается минимум 2 раза
            # Пытаемся найти полную форму в других дисциплинах
            full_form = find_full_form(abbrev, disciplines)
            if full_form:
                pattern_key = f"\\b{re.escape(abbrev)}\\."
                found_abbrev[pattern_key] = full_form
    
    return found_abbrev

def find_full_form(abbrev: str, disciplines: Set[str]) -> str:
    """
    Пытается найти полную форму сокращения, анализируя другие дисциплины
    """
    # Ищем дисциплины, которые могут содержать полную форму
    abbrev_lower = abbrev.lower()
    
    for discipline in disciplines:
        # Ищем слова, начинающиеся с тех же букв
        words = re.findall(r'\b[А-ЯЁа-яё]+', discipline)
        for word in words:
            if word.lower().startswith(abbrev_lower) and len(word) > len(abbrev):
                # Проверяем, не является ли это частью известного слова
                if is_likely_expansion(abbrev, word):
                    return word
    
    return None

def is_likely_expansion(abbrev: str, word: str) -> bool:
    """Проверяет, является ли слово вероятным расширением сокращения"""
    abbrev_lower = abbrev.lower()
    word_lower = word.lower()
    
    # Проверяем, что слово начинается с тех же букв
    if not word_lower.startswith(abbrev_lower):
        return False
    
    # Проверяем длину (расширение должно быть длиннее)
    if len(word) <= len(abbrev):
        return False
    
    # Известные паттерны
    known_patterns = {
        'медиц': 'медицинская',
        'эмбр': 'эмбриология',
        'цитол': 'цитология',
        'цит': 'цитология',
        'вирусол': 'вирусология',
        'вирус': 'вирусология',
        'анат': 'анатомия',
        'физиол': 'физиология',
        'пат': 'патологическая',
        'нормальн': 'нормальная',
        'возр': 'возрастная',
        'опер': 'оперативная',
        'адап': 'адаптационная',
        'хир': 'хирургия',
        'топ': 'топографическая',
        'проф': 'профессиональной',
        'ин': 'иностранный',
    }
    
    if abbrev_lower in known_patterns:
        return word_lower.startswith(known_patterns[abbrev_lower])
    
    return True

def merge_abbreviations(existing: Dict[str, str], new: Dict[str, str]) -> Dict[str, str]:
    """Объединяет существующие и новые сокращения"""
    merged = existing.copy()
    
    for pattern, replacement in new.items():
        if pattern not in merged:
            merged[pattern] = replacement
        elif merged[pattern] != replacement:
            # Если есть конфликт, оставляем существующее, но выводим предупреждение
            print(f"Предупреждение: конфликт для {pattern}")
            print(f"  Существующее: {merged[pattern]}")
            print(f"  Новое: {replacement}")
    
    return merged

def save_abbreviations(abbreviations: Dict[str, str], output_file: str):
    """Сохраняет сокращения в JSON файл"""
    # Группируем по категориям (можно улучшить логику группировки)
    categorized = {
        "Медицинские термины": {},
        "Другие": {}
    }
    
    medical_keywords = ['медиц', 'эмбр', 'цит', 'вирус', 'анат', 'физиол', 'пат', 'хир', 'топ']
    
    for pattern, replacement in abbreviations.items():
        pattern_lower = pattern.lower()
        is_medical = any(keyword in pattern_lower for keyword in medical_keywords)
        
        if is_medical:
            categorized["Медицинские термины"][pattern] = replacement
        else:
            categorized["Другие"][pattern] = replacement
    
    data = {
        "abbreviations": categorized,
        "metadata": {
            "version": "1.0",
            "last_updated": "2026-01-26",
            "description": "Словарь сокращений для нормализации названий дисциплин"
        }
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"Сокращения сохранены в {output_file}")

def main():
    import sys
    
    abbrev_file = 'abbreviations.json'
    
    # Если указаны файлы как аргументы, используем их
    if len(sys.argv) > 1:
        json_files = sys.argv[1:]
    else:
        # Ищем все файлы расписаний
        json_files = glob.glob('timetable*.json')
        # Также ищем normalized версии
        json_files.extend(glob.glob('*_normalized.json'))
        json_files = list(set(json_files))  # Убираем дубликаты
    
    if not json_files:
        print("Не найдено файлов расписаний")
        print("Использование: python3 extract_abbreviations.py [файл1.json] [файл2.json] ...")
        print("Или поместите файлы timetable*.json в текущую директорию")
        return
    
    print(f"Найдено файлов расписаний: {len(json_files)}")
    
    # Загружаем существующие сокращения из всех файлов abbreviations*.json
    print("\nЗагрузка существующих сокращений...")
    existing_abbrev = load_existing_abbreviations()
    print(f"Всего загружено существующих сокращений: {len(existing_abbrev)}")
    
    # Добавляем известные паттерны, которых еще нет
    print("\nДобавление известных паттернов...")
    added_patterns = add_known_patterns_to_existing(existing_abbrev, add_all=False)
    if added_patterns:
        print(f"Добавлено известных паттернов: {len(added_patterns)}")
    else:
        print("Все известные паттерны уже присутствуют")
    
    # Собираем все дисциплины из всех файлов
    all_disciplines = set()
    for json_file in json_files:
        print(f"Обработка {json_file}...")
        disciplines = extract_disciplines_from_json(json_file)
        all_disciplines.update(disciplines)
        print(f"  Найдено дисциплин: {len(disciplines)}")
    
    print(f"\nВсего уникальных дисциплин: {len(all_disciplines)}")
    
    # Ищем новые сокращения
    print("\nПоиск новых сокращений...")
    new_abbrev = find_abbreviations(all_disciplines, existing_abbrev)
    print(f"Найдено новых сокращений: {len(new_abbrev)}")
    
    if new_abbrev:
        print("\nНовые сокращения:")
        for pattern, replacement in new_abbrev.items():
            print(f"  {pattern} -> {replacement}")
    
    # Объединяем и сохраняем
    merged_abbrev = merge_abbreviations(existing_abbrev, new_abbrev)
    
    print(f"\nСтатистика:")
    print(f"  Существующих: {len(existing_abbrev)}")
    print(f"  Найдено новых: {len(new_abbrev)}")
    print(f"  Всего будет сохранено: {len(merged_abbrev)}")
    
    # Спрашиваем, сохранять ли (или можно добавить флаг --force)
    save_abbreviations(merged_abbrev, abbrev_file)
    
    print(f"\nВсего сокращений сохранено: {len(merged_abbrev)}")

if __name__ == '__main__':
    main()

