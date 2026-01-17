#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для скачивания расписаний с сайта СурГУ
Скачивает PDF файлы и организует их по папкам
"""

import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote
import time
from pathlib import Path
import urllib3

# Отключаем предупреждения о SSL (для тестирования)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = 'https://www.surgu.ru'
SCHEDULE_URL = 'https://www.surgu.ru/ucheba/raspisanie/ochnaya-forma-obucheniya'

# Папки для организации файлов
PDFS_DIR = 'schedules_pdf'
JSONS_DIR = 'schedules_json'
PARSED_DIR = 'schedules_parsed'

def create_directories():
    """Создает необходимые директории"""
    for directory in [PDFS_DIR, JSONS_DIR, PARSED_DIR]:
        Path(directory).mkdir(exist_ok=True)
        print(f"Создана/проверена папка: {directory}")

def clean_filename(filename: str) -> str:
    """Очищает имя файла от недопустимых символов"""
    # Декодируем URL-encoded символы
    filename = unquote(filename)
    
    # Убираем недопустимые символы для имен файлов
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Заменяем множественные подчеркивания на одно
    filename = re.sub(r'_+', '_', filename)
    
    # Убираем лишние пробелы
    filename = re.sub(r'\s+', ' ', filename)
    filename = filename.strip()
    
    # Убираем подчеркивания в начале и конце
    filename = filename.strip('_')
    
    # Ограничиваем длину
    if len(filename) > 200:
        filename = filename[:200]
    
    return filename

def extract_institute_name(link_text: str, url: str) -> str:
    """Извлекает название института из текста ссылки или URL"""
    # Маппинг названий институтов
    institutes = {
        'медицинск': 'medical',
        'политехническ': 'polytechnic',
        'экономик': 'economics',
        'гуманитарн': 'humanities',
        'государств': 'state_law',
        'естественн': 'natural_sciences',
        'средн': 'secondary_medical',
        'лечебн': 'medical',
        'педагог': 'pedagogy',
        'юриспруденц': 'law',
        'менеджмент': 'management',
        'информатик': 'informatics',
        'строительств': 'construction',
        'физик': 'physics',
        'математик': 'mathematics',
    }
    
    text_lower = link_text.lower()
    url_lower = url.lower()
    combined = f"{text_lower} {url_lower}"
    
    # Ищем совпадения
    for key, value in institutes.items():
        if key in combined:
            return value
    
    # Если не нашли, пытаемся извлечь из текста ссылки
    # Ищем паттерны типа "Институт X" или специальность
    match = re.search(r'институт\s+([а-яё]+)', text_lower)
    if match:
        inst_word = match.group(1)
        for key, value in institutes.items():
            if key in inst_word:
                return value
    
    # Если все еще не нашли, создаем имя из текста
    name = link_text.strip()
    # Убираем скобки и их содержимое
    name = re.sub(r'\([^)]*\)', '', name)
    # Берем первые слова (до запятой или скобки)
    name = name.split(',')[0].split('(')[0].strip()
    
    # Транслитерируем в латиницу для имени файла
    translit_map = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
    }
    
    result = ''
    for char in name.lower():
        if char in translit_map:
            result += translit_map[char]
        elif char.isalnum() or char in '_- ':
            result += char
        else:
            result += '_'
    
    result = re.sub(r'[_\s]+', '_', result)
    result = result.strip('_')
    
    # Ограничиваем длину
    if len(result) > 30:
        result = result[:30]
    
    return result if result else 'unknown'

def download_pdf(url: str, filename: str) -> bool:
    """Скачивает PDF файл"""
    try:
        print(f"  Скачивание: {filename}")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, timeout=30, stream=True, headers=headers)
        response.raise_for_status()
        
        # Проверяем, что это действительно PDF
        content_type = response.headers.get('Content-Type', '').lower()
        if 'pdf' not in content_type and not url.lower().endswith('.pdf'):
            # Проверяем первые байты файла
            first_bytes = response.content[:4]
            if first_bytes != b'%PDF':
                print(f"  ⚠ Предупреждение: файл может быть не PDF")
        
        filepath = os.path.join(PDFS_DIR, filename)
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        file_size = os.path.getsize(filepath)
        print(f"  ✓ Скачано: {filepath} ({file_size} байт)")
        return True
    except Exception as e:
        print(f"  ✗ Ошибка при скачивании {filename}: {e}")
        return False

def parse_schedule_page():
    """Парсит страницу с расписаниями и скачивает PDF файлы"""
    print(f"Загрузка страницы: {SCHEDULE_URL}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        # Пробуем с проверкой SSL
        response = requests.get(SCHEDULE_URL, timeout=30, headers=headers, verify=True)
        response.raise_for_status()
        response.encoding = 'utf-8'
    except requests.exceptions.SSLError:
        # Если ошибка SSL, пробуем без проверки (небезопасно, но для тестирования)
        print("Предупреждение: SSL ошибка, пробуем без проверки сертификата...")
        try:
            response = requests.get(SCHEDULE_URL, timeout=30, headers=headers, verify=False)
            response.raise_for_status()
            response.encoding = 'utf-8'
        except Exception as e:
            print(f"Ошибка при загрузке страницы: {e}")
            return []
    except Exception as e:
        print(f"Ошибка при загрузке страницы: {e}")
        return []
    
    # Пробуем разные парсеры
    try:
        soup = BeautifulSoup(response.text, 'lxml')
    except:
        soup = BeautifulSoup(response.text, 'html.parser')
    
    # Ищем все ссылки на PDF файлы
    pdf_links = []
    
    print(f"Размер страницы: {len(response.text)} символов")
    
    # Ищем ссылки с атрибутом download или содержащие .pdf
    # Также ищем ссылки в таблицах и списках
    all_links = soup.find_all('a', href=True)
    print(f"Найдено ссылок на странице: {len(all_links)}")
    
    for link in all_links:
        href = link.get('href', '')
        text = link.get_text(strip=True)
        
        # Пропускаем пустые ссылки
        if not href:
            continue
        
        # Проверяем, является ли это ссылкой на PDF
        href_lower = href.lower()
        if '.pdf' in href_lower or '/attachment/' in href_lower or '/download/' in href_lower:
            full_url = urljoin(BASE_URL, href)
            
            # Извлекаем название института/направления из текста или URL
            institute = extract_institute_name(text, full_url)
            
            # Создаем имя файла
            # Сначала пытаемся извлечь из URL
            url_path = urlparse(full_url).path
            url_filename = os.path.basename(url_path)
            if '?' in url_filename:
                url_filename = url_filename.split('?')[0]
            url_filename = unquote(url_filename)  # Декодируем URL
            
            # Если в URL есть имя файла с расширением, используем его
            if url_filename and url_filename.endswith('.pdf'):
                filename_base = url_filename
            else:
                # Используем текст ссылки
                filename_base = clean_filename(text)
                if not filename_base or len(filename_base) < 3:
                    # Если текст не подходит, генерируем из URL
                    if '/download/' in full_url:
                        parts = full_url.split('/download/')
                        if len(parts) > 1:
                            filename_base = unquote(parts[-1].split('?')[0])
                    
                    if not filename_base or len(filename_base) < 3:
                        # Генерируем имя из текста или хеша
                        if text and len(text) > 3:
                            filename_base = clean_filename(text)
                        else:
                            filename_base = f"schedule_{abs(hash(full_url)) % 10000}"
            
            # Убеждаемся, что есть расширение .pdf
            if not filename_base.endswith('.pdf'):
                filename_base += '.pdf'
            
            # Добавляем префикс института, если его еще нет в имени
            if institute and institute not in filename_base.lower():
                filename = f"{institute}_{filename_base}"
            else:
                filename = filename_base
            
            filename = clean_filename(filename)
            
            pdf_links.append({
                'url': full_url,
                'filename': filename,
                'institute': institute,
                'text': text
            })
    
    # Убираем дубликаты по URL
    seen_urls = set()
    unique_links = []
    for link in pdf_links:
        if link['url'] not in seen_urls:
            seen_urls.add(link['url'])
            unique_links.append(link)
    
    return unique_links

def main():
    print("=" * 60)
    print("Скачивание расписаний с сайта СурГУ")
    print("=" * 60)
    
    # Создаем директории
    create_directories()
    
    # Парсим страницу
    print(f"\nПарсинг страницы расписаний...")
    pdf_links = parse_schedule_page()
    
    if not pdf_links:
        print("Не найдено ссылок на PDF файлы")
        return
    
    print(f"\nНайдено ссылок на PDF: {len(pdf_links)}")
    
    # Группируем по институтам
    by_institute = {}
    for link in pdf_links:
        inst = link['institute']
        if inst not in by_institute:
            by_institute[inst] = []
        by_institute[inst].append(link)
    
    print(f"\nНайдено институтов/направлений: {len(by_institute)}")
    for inst, links in by_institute.items():
        print(f"  {inst}: {len(links)} файлов")
    
    # Скачиваем файлы
    print(f"\nНачинаем скачивание...")
    downloaded = 0
    failed = 0
    skipped = 0
    
    for i, link in enumerate(pdf_links, 1):
        filepath = os.path.join(PDFS_DIR, link['filename'])
        
        # Проверяем, не существует ли уже файл
        if os.path.exists(filepath):
            print(f"\n[{i}/{len(pdf_links)}] {link['text'][:50]}...")
            print(f"  ⊘ Файл уже существует, пропускаем: {link['filename']}")
            skipped += 1
            continue
        
        print(f"\n[{i}/{len(pdf_links)}] {link['text'][:50]}...")
        if download_pdf(link['url'], link['filename']):
            downloaded += 1
        else:
            failed += 1
        
        # Небольшая задержка между запросами
        time.sleep(0.5)
    
    print(f"\n" + "=" * 60)
    print(f"Скачивание завершено!")
    print(f"  Успешно скачано: {downloaded}")
    print(f"  Пропущено (уже существуют): {skipped}")
    print(f"  Ошибок: {failed}")
    print(f"  Всего обработано: {len(pdf_links)}")
    print(f"\nФайлы сохранены в папку: {PDFS_DIR}/")
    
    if downloaded > 0:
        print(f"\nДля парсинга скачанных файлов запустите:")
        print(f"  python3 parse_all_schedules.py")

if __name__ == '__main__':
    main()

