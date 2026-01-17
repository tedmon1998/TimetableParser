#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для массового парсинга всех PDF расписаний
Парсит все файлы из папки schedules_pdf и сохраняет JSON в schedules_json
"""

import os
from pathlib import Path
from parse_timetable import parse_pdf
import json

def main():
    pdfs_dir = 'schedules_pdf'
    jsons_dir = 'schedules_json'
    
    # Создаем папку для JSON, если её нет
    Path(jsons_dir).mkdir(exist_ok=True)
    
    if not os.path.exists(pdfs_dir):
        print(f"Ошибка: папка {pdfs_dir} не найдена")
        print("Сначала запустите download_schedules.py для скачивания расписаний")
        return
    
    # Находим все PDF файлы
    pdf_files = sorted(Path(pdfs_dir).glob('*.pdf'))
    
    if not pdf_files:
        print(f"В папке {pdfs_dir} не найдено PDF файлов")
        return
    
    print(f"Найдено PDF файлов: {len(pdf_files)}")
    print(f"Начинаем парсинг...\n")
    
    total_records = 0
    success_count = 0
    error_count = 0
    
    for i, pdf_file in enumerate(pdf_files, 1):
        print(f"[{i}/{len(pdf_files)}] Парсинг: {pdf_file.name}")
        print("-" * 60)
        
        try:
            results = parse_pdf(str(pdf_file))
            
            # Создаем имя JSON файла на основе имени PDF
            json_name = pdf_file.stem + '.json'
            output_path = os.path.join(jsons_dir, json_name)
            
            # Сохраняем в JSON
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            
            print(f"✓ Найдено записей: {len(results)}")
            print(f"✓ Сохранено в: {output_path}\n")
            
            total_records += len(results)
            success_count += 1
            
        except Exception as e:
            print(f"✗ Ошибка при парсинге {pdf_file.name}: {e}\n")
            error_count += 1
    
    print("=" * 60)
    print(f"Парсинг завершен!")
    print(f"  Успешно обработано: {success_count}")
    print(f"  Ошибок: {error_count}")
    print(f"  Всего записей: {total_records}")
    print(f"\nJSON файлы сохранены в папку: {jsons_dir}/")

if __name__ == '__main__':
    main()

