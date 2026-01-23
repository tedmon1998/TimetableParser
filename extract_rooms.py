#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для извлечения уникальных аудиторий из CSV файла.
"""

import csv
import re
import json
from pathlib import Path
from collections import OrderedDict

# Префиксы для аудиторий
ROOM_PREFIXES = ["У", "К", "А", "Г", "УЦ", "л/б", "п/б", "ЭБЦ", "ЦАС", "СОКЦОМиД", "СОКБ", "С"]

# Точные совпадения
EXACT_MATCHES = ["м/зал", "бассейн", "зал 2", "зал гимн"]

# Разделители для множественных аудиторий в одной ячейке
SPLIT_DELIMITERS = [',', ';', '/', '|', '\n']

# Заголовки колонок с аудиториями (варианты)
AUDITORIUM_HEADERS = ["аудитория", "кабинет", "место", "ауд.", "room", "аудитория/место"]


def normalize_room(room_str):
    """
    Нормализация аудитории:
    - обрезать пробелы по краям
    - заменить множественные пробелы на один
    - сохранить исходный регистр
    """
    if not room_str:
        return None
    
    # Обрезать пробелы
    room_str = room_str.strip()
    
    # Заменить множественные пробелы на один
    room_str = re.sub(r'\s+', ' ', room_str)
    
    # Убрать пустые строки
    if not room_str:
        return None
    
    return room_str


def is_room(value):
    """
    Проверяет, является ли значение аудиторией.
    """
    if not value:
        return False
    
    value = value.strip()
    
    # Проверка точных совпадений
    if value in EXACT_MATCHES:
        return True
    
    # Проверка на содержание "ЭОиДОТ"
    if "ЭОиДОТ" in value:
        return True
    
    # Проверка префиксов
    for prefix in ROOM_PREFIXES:
        if value.startswith(prefix):
            return True
    
    return False


def split_rooms(cell_value):
    """
    Разделяет значение ячейки на отдельные аудитории.
    """
    if not cell_value:
        return []
    
    # Сначала разделяем по основным разделителям
    parts = [cell_value]
    for delimiter in SPLIT_DELIMITERS:
        new_parts = []
        for part in parts:
            new_parts.extend(part.split(delimiter))
        parts = new_parts
    
    # Нормализуем и фильтруем
    rooms = []
    for part in parts:
        normalized = normalize_room(part)
        if normalized and is_room(normalized):
            rooms.append(normalized)
    
    return rooms


def find_auditorium_columns(headers):
    """
    Находит индексы колонок с аудиториями.
    """
    auditorium_indices = []
    
    for i, header in enumerate(headers):
        header_lower = header.lower().strip()
        # Проверяем, содержит ли заголовок ключевые слова
        for keyword in AUDITORIUM_HEADERS:
            if keyword in header_lower:
                auditorium_indices.append(i)
                break
    
    return auditorium_indices


def extract_rooms_from_csv(csv_path):
    """
    Извлекает все уникальные аудитории из CSV файла.
    """
    rooms_set = set()
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        # Определяем разделитель (пробуем запятую)
        sample = f.read(1024)
        f.seek(0)
        
        # Пробуем определить, есть ли кавычки и какой разделитель
        sniffer = csv.Sniffer()
        delimiter = sniffer.sniff(sample).delimiter
        
        reader = csv.reader(f, delimiter=delimiter)
        
        # Читаем заголовки
        headers = next(reader)
        
        # Находим колонки с аудиториями
        auditorium_indices = find_auditorium_columns(headers)
        
        if not auditorium_indices:
            # Если не нашли по заголовкам, ищем колонку с наибольшим количеством похожих на аудитории значений
            print("Не найдены колонки с заголовками 'аудитория'. Ищу колонку с наибольшим количеством аудиторий...")
            # Пробуем прочитать первые 100 строк для анализа
            f.seek(0)
            reader = csv.reader(f, delimiter=delimiter)
            next(reader)  # Пропускаем заголовок
            
            column_room_counts = {}
            for row_idx, row in enumerate(reader):
                if row_idx >= 100:
                    break
                for col_idx, cell in enumerate(row):
                    if col_idx not in column_room_counts:
                        column_room_counts[col_idx] = 0
                    rooms = split_rooms(cell)
                    if rooms:
                        column_room_counts[col_idx] += len(rooms)
            
            if column_room_counts:
                # Берем колонку с наибольшим количеством аудиторий
                best_col = max(column_room_counts.items(), key=lambda x: x[1])[0]
                auditorium_indices = [best_col]
                print(f"Выбрана колонка {best_col} (заголовок: '{headers[best_col] if best_col < len(headers) else 'N/A'}')")
        
        print(f"Найдены колонки с аудиториями: {auditorium_indices}")
        print(f"Заголовки: {[headers[i] if i < len(headers) else 'N/A' for i in auditorium_indices]}")
        
        # Читаем все строки и извлекаем аудитории
        f.seek(0)
        reader = csv.reader(f, delimiter=delimiter)
        next(reader)  # Пропускаем заголовок
        
        for row_idx, row in enumerate(reader):
            for col_idx in auditorium_indices:
                if col_idx < len(row):
                    cell_value = row[col_idx]
                    rooms = split_rooms(cell_value)
                    rooms_set.update(rooms)
    
    # Сортируем и возвращаем список
    return sorted(list(rooms_set))


def main():
    csv_path = Path("input/Zanyatost prepodavateley_ vesenniy semestr 2025-2026-14-01-26.csv")
    
    if not csv_path.exists():
        print(f"Файл не найден: {csv_path}")
        return
    
    print(f"Читаю файл: {csv_path}")
    rooms = extract_rooms_from_csv(csv_path)
    
    print(f"Найдено уникальных аудиторий: {len(rooms)}")
    
    # Определяем имя выходного файла
    csv_name = csv_path.stem  # Без расширения
    output_dir = Path("info")
    output_dir.mkdir(exist_ok=True)
    
    # Записываем в .json
    json_path = output_dir / f"{csv_name}.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(rooms, f, ensure_ascii=False, indent=2)
    print(f"Записано в: {json_path}")


if __name__ == "__main__":
    main()
