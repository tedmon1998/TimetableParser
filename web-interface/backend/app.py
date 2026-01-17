#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backend API для веб-интерфейса управления расписаниями
"""

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import json
import os
import re
import subprocess
import sys
import threading
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional
from werkzeug.serving import WSGIRequestHandler

# Определяем системный Python для запуска скриптов
# Используем системный Python, так как там установлены все зависимости
def get_system_python():
    """Получить путь к системному Python с установленными зависимостями"""
    print(f"[DEBUG] get_system_python: sys.executable = {sys.executable}")
    
    # Список известных путей к системному Python (не venv)
    system_python_paths = [
        '/Library/Frameworks/Python.framework/Versions/3.11/bin/python3',
        '/Library/Frameworks/Python.framework/Versions/3.10/bin/python3',
        '/Library/Frameworks/Python.framework/Versions/3.9/bin/python3',
        '/usr/local/bin/python3',
        '/usr/bin/python3',
    ]
    
    # Сначала проверяем текущий Python (может быть системный, если не venv)
    is_venv = 'venv' in sys.executable or 'virtualenv' in sys.executable
    if not is_venv:
        try:
            print(f"[DEBUG] Проверяю текущий Python (не venv): {sys.executable}")
            result = subprocess.run(
                [sys.executable, '-c', 'import requests'],
                capture_output=True,
                timeout=2,
                text=True
            )
            if result.returncode == 0:
                print(f"[DEBUG] ✅ Текущий Python имеет requests: {sys.executable}")
                return sys.executable
            else:
                print(f"[DEBUG] ❌ Текущий Python НЕ имеет requests. stderr: {result.stderr}")
        except Exception as e:
            print(f"[DEBUG] ❌ Ошибка при проверке текущего Python: {e}")
    
    # Проверяем известные пути к системному Python
    for python_path in system_python_paths:
        if os.path.exists(python_path):
            try:
                print(f"[DEBUG] Проверяю системный Python: {python_path}")
                result = subprocess.run(
                    [python_path, '-c', 'import requests'],
                    capture_output=True,
                    timeout=2,
                    text=True
                )
                if result.returncode == 0:
                    print(f"[DEBUG] ✅ Найден системный Python с requests: {python_path}")
                    return python_path
                else:
                    print(f"[DEBUG] ❌ {python_path} НЕ имеет requests. stderr: {result.stderr}")
            except Exception as e:
                print(f"[DEBUG] ❌ Ошибка при проверке {python_path}: {e}")
    
    # Если ничего не подошло, пробуем найти через which, но проверяем что это не venv
    system_python = shutil.which('python3')
    print(f"[DEBUG] shutil.which('python3') = {system_python}")
    
    if system_python and system_python != sys.executable:
        # Проверяем, что это не venv
        is_venv_path = 'venv' in system_python or 'virtualenv' in system_python
        if not is_venv_path:
            try:
                print(f"[DEBUG] Проверяю найденный Python (не venv): {system_python}")
                result = subprocess.run(
                    [system_python, '-c', 'import requests'],
                    capture_output=True,
                    timeout=2,
                    text=True
                )
                if result.returncode == 0:
                    print(f"[DEBUG] ✅ Найденный Python имеет requests: {system_python}")
                    return system_python
                else:
                    print(f"[DEBUG] ❌ Найденный Python НЕ имеет requests. stderr: {result.stderr}")
            except Exception as e:
                print(f"[DEBUG] ❌ Ошибка при проверке найденного Python: {e}")
        else:
            print(f"[DEBUG] ⚠️ Найденный Python - это venv, пропускаю")
    
    # Если ничего не найдено, возвращаем первый существующий системный путь (даже без проверки)
    for python_path in system_python_paths:
        if os.path.exists(python_path):
            print(f"[DEBUG] ⚠️ Использую системный Python без проверки: {python_path}")
            return python_path
    
    # Последний fallback
    print(f"[DEBUG] ⚠️ Использую sys.executable как fallback: {sys.executable}")
    return sys.executable

# Настраиваем логирование - отключаем для статусных запросов
class QuietStatusHandler(WSGIRequestHandler):
    """Кастомный обработчик запросов, который не логирует статусные запросы"""
    def log_request(self, code='-', size='-'):
        # Не логируем статусные запросы (200 OK для /api/status и /api/tasks/*/status)
        is_status_endpoint = (
            self.path == '/api/status' or 
            (self.path.startswith('/api/tasks/') and self.path.endswith('/status'))
        )
        if is_status_endpoint and code == 200:
            return  # Пропускаем логирование успешных статусных запросов
        super().log_request(code, size)

app = Flask(__name__)
# Настраиваем CORS для работы с frontend
# Разрешаем все origins для разработки (можно ограничить в production)
CORS(app, 
     resources={
         r"/api/*": {
             "origins": [
                 "http://localhost:3000", 
                 "http://127.0.0.1:3000",
                 "http://localhost:5001",
                 "http://127.0.0.1:5001"
             ],
             "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
             "allow_headers": ["Content-Type", "Authorization"],
             "supports_credentials": True
         }
     })

# Добавляем CORS заголовки ко всем ответам
@app.after_request
def after_request(response):
    """Добавляет CORS заголовки ко всем ответам"""
    origin = request.headers.get('Origin', '')
    # Разрешаем только известные origins
    allowed_origins = ['http://localhost:3000', 'http://127.0.0.1:3000']
    if origin in allowed_origins:
        response.headers['Access-Control-Allow-Origin'] = origin
    elif not origin:  # Если нет Origin (например, прямой запрос), разрешаем localhost
        response.headers['Access-Control-Allow-Origin'] = 'http://localhost:3000'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response

# Обработчик ошибок для CORS
@app.errorhandler(Exception)
def handle_error(e):
    """Обработчик ошибок с CORS заголовками"""
    import traceback
    print(f"[ERROR] Exception: {e}")
    print(f"[ERROR] Traceback: {traceback.format_exc()}")
    response = jsonify({'error': str(e)})
    response.status_code = 500
    return response

# Пути к папкам
# Определяем BASE_DIR относительно расположения этого файла
# app.py находится в web-interface/backend/, поэтому нужно подняться на 2 уровня вверх
import os
# Используем os.path для более надежного определения пути
try:
    _current_file = os.path.abspath(os.path.dirname(__file__))
    BASE_DIR = Path(_current_file).parent.parent  # backend/ -> web-interface/ -> timetable/
except NameError:
    # Fallback если __file__ не определен
    BASE_DIR = Path.cwd().parent.parent if 'web-interface' in str(Path.cwd()) else Path.cwd().parent

PDFS_DIR = BASE_DIR / 'schedules_pdf'
JSONS_DIR = BASE_DIR / 'schedules_json'
PARSED_DIR = BASE_DIR / 'schedules_parsed'
ABBREV_FILE = BASE_DIR / 'abbreviations.json'

# Создаем папки если их нет
PDFS_DIR.mkdir(exist_ok=True)
JSONS_DIR.mkdir(exist_ok=True)
PARSED_DIR.mkdir(exist_ok=True)

# Статус выполнения задач
task_status = {
    'download': {'running': False, 'progress': 0, 'message': '', 'process': None, 'total_files': None},
    'parse': {'running': False, 'progress': 0, 'message': '', 'process': None},
    'normalize': {'running': False, 'progress': 0, 'message': '', 'process': None}
}

@app.route('/')
def index():
    """Корневой маршрут - информация о API"""
    return jsonify({
        'message': 'Timetable API Server',
        'version': '1.0.0',
        'endpoints': {
            'status': '/api/status',
            'files': '/api/files?type=json|parsed|pdf',
            'file': '/api/file/<filename>?type=json|parsed|pdf',
            'abbreviations': '/api/abbreviations',
            'tasks': {
                'download': '/api/tasks/download',
                'parse': '/api/tasks/parse',
                'normalize': '/api/tasks/normalize',
                'status': '/api/tasks/<task_name>/status'
            }
        }
    })

@app.route('/api/status')
def status():
    """Получить статус сервера"""
    # Убираем объекты process из task_status перед сериализацией
    tasks_serializable = {}
    for task_name, task_data in task_status.items():
        task_dict = {
            'running': task_data['running'],
            'progress': task_data['progress'],
            'message': task_data['message']
        }
        # Добавляем total_files если есть
        if 'total_files' in task_data and task_data['total_files'] is not None:
            task_dict['total_files'] = task_data['total_files']
        tasks_serializable[task_name] = task_dict
    
    return jsonify({
        'status': 'ok',
        'pdfs_count': len(list(PDFS_DIR.glob('*.pdf'))) if PDFS_DIR.exists() else 0,
        'jsons_count': len(list(JSONS_DIR.glob('*.json'))) if JSONS_DIR.exists() else 0,
        'parsed_count': len(list(PARSED_DIR.glob('*.json'))) if PARSED_DIR.exists() else 0,
        'tasks': tasks_serializable
    })

@app.route('/api/files')
def list_files():
    """Список всех файлов"""
    file_type = request.args.get('type', 'json')  # json, parsed, pdf
    
    if file_type == 'pdf':
        dir_path = PDFS_DIR
        ext = '.pdf'
    elif file_type == 'parsed':
        dir_path = PARSED_DIR
        ext = '.json'
    else:
        dir_path = JSONS_DIR
        ext = '.json'
    
    if not dir_path.exists():
        return jsonify([])
    
    files = []
    for file_path in sorted(dir_path.glob(f'*{ext}')):
        stat = file_path.stat()
        files.append({
            'name': file_path.name,
            'size': stat.st_size,
            'modified': stat.st_mtime
        })
    
    return jsonify(files)

@app.route('/api/file/<path:filename>')
def get_file(filename):
    """Получить содержимое файла"""
    file_type = request.args.get('type', 'json')
    
    if file_type == 'pdf':
        file_path = PDFS_DIR / filename
    elif file_type == 'parsed':
        file_path = PARSED_DIR / filename
    else:
        file_path = JSONS_DIR / filename
    
    if not file_path.exists():
        return jsonify({'error': 'File not found'}), 404
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/abbreviations', methods=['GET'])
def get_abbreviations():
    """Получить словарь сокращений"""
    if not ABBREV_FILE.exists():
        return jsonify({'abbreviations': {}, 'metadata': {}})
    
    try:
        with open(ABBREV_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/abbreviations', methods=['POST'])
def save_abbreviations():
    """Сохранить словарь сокращений"""
    try:
        data = request.json
        with open(ABBREV_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/tasks/download', methods=['POST'])
def start_download():
    """Запустить скачивание расписаний"""
    if task_status['download']['running']:
        return jsonify({'error': 'Task already running'}), 400
    
    def run_download():
        task_status['download']['running'] = True
        task_status['download']['progress'] = 0
        task_status['download']['message'] = 'Запуск скачивания...'
        
        try:
            script_path = BASE_DIR / 'download_schedules.py'
            if not script_path.exists():
                raise FileNotFoundError(f"Script not found: {script_path}")
            
            initial_count = len(list(PDFS_DIR.glob('*.pdf'))) if PDFS_DIR.exists() else 0
            task_status['download']['total_files'] = None  # Будет определено из вывода скрипта
            
            # Настраиваем окружение
            env = os.environ.copy()
            # Добавляем путь к проекту в PYTHONPATH
            pythonpath = str(BASE_DIR)
            if 'PYTHONPATH' in env:
                env['PYTHONPATH'] = f"{pythonpath}:{env['PYTHONPATH']}"
            else:
                env['PYTHONPATH'] = pythonpath
            
            # Используем системный Python для запуска скриптов
            # (там установлены все зависимости: requests, beautifulsoup4 и т.д.)
            print(f"[DEBUG] Запуск download: script_path = {script_path}")
            print(f"[DEBUG] Запуск download: BASE_DIR = {BASE_DIR}")
            print(f"[DEBUG] Запуск download: sys.executable = {sys.executable}")
            
            python_executable = get_system_python()
            
            print(f"[DEBUG] Выбранный Python для скрипта: {python_executable}")
            print(f"[DEBUG] Команда: [{python_executable}, {script_path}]")
            print(f"[DEBUG] CWD: {BASE_DIR}")
            print(f"[DEBUG] PYTHONPATH: {env.get('PYTHONPATH', 'не установлен')}")
            
            # Добавляем отладочную информацию
            debug_info = f"Flask Python: {sys.executable}\n"
            debug_info += f"Script Python: {python_executable}\n"
            debug_info += f"Script path: {script_path}\n"
            task_status['download']['message'] = debug_info
            
            # Запускаем процесс с чтением вывода в реальном времени
            print(f"[DEBUG] Запускаю subprocess.Popen...")
            process = subprocess.Popen(
                [python_executable, str(script_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                cwd=str(BASE_DIR),
                env=env
            )
            print(f"[DEBUG] Process запущен, PID: {process.pid}")
            
            # Сохраняем процесс для возможности остановки
            task_status['download']['process'] = process
            
            output_lines = []
            print(f"[DEBUG] Начинаю читать вывод процесса...")
            line_count = 0
            last_progress_check = 0
            
            for line in process.stdout:
                # Проверяем, не была ли задача остановлена
                if not task_status['download']['running']:
                    print(f"[DEBUG] Задача остановлена, прерываю чтение вывода")
                    break
                
                print(f"[DEBUG] Получена строка: {line.rstrip()}")
                output_lines.append(line)
                line_count += 1
                
                # Пытаемся определить общее количество файлов из вывода
                # Ищем строку "Найдено ссылок на PDF: X"
                total_match = re.search(r'Найдено ссылок на PDF:\s*(\d+)', line)
                if total_match and task_status['download']['total_files'] is None:
                    task_status['download']['total_files'] = int(total_match.group(1))
                    print(f"[DEBUG] ✅ Определено общее количество файлов: {task_status['download']['total_files']}")
                
                # Показываем отладочную информацию + последние 14 строк вывода скрипта
                display_lines = [debug_info] + output_lines[-14:]
                task_status['download']['message'] = ''.join(display_lines)
                
                # Пытаемся определить прогресс из вывода [X/Y]
                match = re.search(r'\[(\d+)/(\d+)\]', line)
                if match:
                    current = int(match.group(1))
                    total = int(match.group(2))
                    if total > 0:
                        progress = int((current / total) * 100)
                        task_status['download']['progress'] = progress
                        print(f"[DEBUG] Найден прогресс из [X/Y]: {current}/{total} = {progress}%")
                        # Обновляем total_files если нашли в [X/Y]
                        if task_status['download']['total_files'] is None:
                            task_status['download']['total_files'] = total
                
                # ВСЕГДА проверяем количество файлов для обновления прогресса (каждые 3 строки)
                if line_count % 3 == 0 or task_status['download']['progress'] == 0:
                    current_count = len(list(PDFS_DIR.glob('*.pdf'))) if PDFS_DIR.exists() else 0
                    downloaded_count = current_count - initial_count
                    
                    if task_status['download']['total_files'] and task_status['download']['total_files'] > 0:
                        # Используем реальное количество файлов
                        progress = min(int((downloaded_count / task_status['download']['total_files']) * 100), 95)
                        if progress != last_progress_check:
                            task_status['download']['progress'] = progress
                            print(f"[DEBUG] 📊 Прогресс по файлам: {downloaded_count}/{task_status['download']['total_files']} = {progress}%")
                            last_progress_check = progress
                    elif downloaded_count > 0:
                        # Если не знаем общее количество, используем примерную оценку
                        estimated_total = 75
                        progress = min(int((downloaded_count / estimated_total) * 90), 90)
                        if progress != last_progress_check:
                            task_status['download']['progress'] = progress
                            print(f"[DEBUG] 📊 Прогресс по файлам (примерно): {downloaded_count}/{estimated_total} = {progress}%")
                            last_progress_check = progress
            
            print(f"[DEBUG] Ожидаю завершения процесса...")
            return_code = process.wait()
            print(f"[DEBUG] Процесс завершен с кодом: {return_code}")
            
            # Финальная проверка прогресса
            final_count = len(list(PDFS_DIR.glob('*.pdf'))) if PDFS_DIR.exists() else 0
            final_downloaded = final_count - initial_count
            
            if return_code == 0:
                # Если успешно завершился
                if task_status['download']['total_files'] and task_status['download']['total_files'] > 0:
                    final_progress = min(int((final_downloaded / task_status['download']['total_files']) * 100), 100)
                    task_status['download']['progress'] = final_progress
                    print(f"[DEBUG] 📊 Финальный прогресс: {final_downloaded}/{task_status['download']['total_files']} = {final_progress}%")
                else:
                    task_status['download']['progress'] = 100
                    print(f"[DEBUG] ✅ Процесс завершен успешно, прогресс = 100%")
            else:
                print(f"[DEBUG] ❌ Процесс завершился с ошибкой! Код: {return_code}")
            
            # Формируем финальное сообщение
            final_message = debug_info + ''.join(output_lines)
            task_status['download']['message'] = final_message
        except Exception as e:
            task_status['download']['message'] = f'Ошибка: {str(e)}'
            task_status['download']['progress'] = 0
        finally:
            task_status['download']['running'] = False
            task_status['download']['process'] = None
    
    thread = threading.Thread(target=run_download, daemon=True)
    thread.start()
    return jsonify({'status': 'started'})

@app.route('/api/tasks/parse', methods=['POST'])
def start_parse():
    """Запустить парсинг PDF"""
    if task_status['parse']['running']:
        return jsonify({'error': 'Task already running'}), 400
    
    def run_parse():
        task_status['parse']['running'] = True
        task_status['parse']['progress'] = 0
        task_status['parse']['message'] = 'Запуск парсинга...'
        
        try:
            script_path = BASE_DIR / 'parse_all_schedules.py'
            if not script_path.exists():
                raise FileNotFoundError(f"Script not found: {script_path}")
            
            initial_count = len(list(JSONS_DIR.glob('*.json'))) if JSONS_DIR.exists() else 0
            total_pdfs = len(list(PDFS_DIR.glob('*.pdf'))) if PDFS_DIR.exists() else 0
            
            # Настраиваем окружение
            env = os.environ.copy()
            pythonpath = str(BASE_DIR)
            if 'PYTHONPATH' in env:
                env['PYTHONPATH'] = f"{pythonpath}:{env['PYTHONPATH']}"
            else:
                env['PYTHONPATH'] = pythonpath
            
            # Используем системный Python для запуска скриптов
            # (там установлены все зависимости: requests, beautifulsoup4 и т.д.)
            python_executable = get_system_python()
            
            # Запускаем процесс с чтением вывода в реальном времени
            process = subprocess.Popen(
                [python_executable, str(script_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                cwd=str(BASE_DIR),
                env=env
            )
            
            # Сохраняем процесс для возможности остановки
            task_status['parse']['process'] = process
            
            output_lines = []
            for line in process.stdout:
                output_lines.append(line)
                task_status['parse']['message'] = ''.join(output_lines[-10:])  # Последние 10 строк
                
                # Пытаемся определить прогресс из вывода
                if '[' in line and '/' in line and ']' in line:
                    import re
                    match = re.search(r'\[(\d+)/(\d+)\]', line)
                    if match:
                        current = int(match.group(1))
                        total = int(match.group(2))
                        if total > 0:
                            task_status['parse']['progress'] = int((current / total) * 100)
                
                # Альтернативный способ - по количеству файлов
                current_count = len(list(JSONS_DIR.glob('*.json'))) if JSONS_DIR.exists() else 0
                if total_pdfs > 0 and current_count > initial_count:
                    processed = current_count - initial_count
                    task_status['parse']['progress'] = int((processed / total_pdfs) * 90)
            
            process.wait()
            task_status['parse']['message'] = ''.join(output_lines)
            task_status['parse']['progress'] = 100
        except Exception as e:
            task_status['parse']['message'] = f'Ошибка: {str(e)}'
            task_status['parse']['progress'] = 0
        finally:
            task_status['parse']['running'] = False
            task_status['parse']['process'] = None
    
    thread = threading.Thread(target=run_parse, daemon=True)
    thread.start()
    return jsonify({'status': 'started'})

@app.route('/api/tasks/normalize', methods=['POST'])
def start_normalize():
    """Запустить нормализацию"""
    if task_status['normalize']['running']:
        return jsonify({'error': 'Task already running'}), 400
    
    def run_normalize():
        task_status['normalize']['running'] = True
        task_status['normalize']['progress'] = 0
        task_status['normalize']['message'] = 'Запуск нормализации...'
        
        try:
            script_path = BASE_DIR / 'normalize_disciplines.py'
            if not script_path.exists():
                raise FileNotFoundError(f"Script not found: {script_path}")
            
            initial_count = len(list(PARSED_DIR.glob('*.json'))) if PARSED_DIR.exists() else 0
            total_jsons = len(list(JSONS_DIR.glob('*.json'))) if JSONS_DIR.exists() else 0
            
            # Настраиваем окружение
            env = os.environ.copy()
            pythonpath = str(BASE_DIR)
            if 'PYTHONPATH' in env:
                env['PYTHONPATH'] = f"{pythonpath}:{env['PYTHONPATH']}"
            else:
                env['PYTHONPATH'] = pythonpath
            
            # Используем системный Python для запуска скриптов
            # (там установлены все зависимости: requests, beautifulsoup4 и т.д.)
            python_executable = get_system_python()
            
            # Запускаем процесс с чтением вывода в реальном времени
            process = subprocess.Popen(
                [python_executable, str(script_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                cwd=str(BASE_DIR),
                env=env
            )
            
            # Сохраняем процесс для возможности остановки
            task_status['parse']['process'] = process
            
            output_lines = []
            for line in process.stdout:
                output_lines.append(line)
                task_status['normalize']['message'] = ''.join(output_lines[-10:])  # Последние 10 строк
                
                # Пытаемся определить прогресс из вывода
                if 'Обработка:' in line or 'Найдено JSON файлов:' in line:
                    match = re.search(r'(\d+)', line)
                    if match and total_jsons > 0:
                        # Примерная оценка
                        pass
                
                # Альтернативный способ - по количеству файлов
                current_count = len(list(PARSED_DIR.glob('*.json'))) if PARSED_DIR.exists() else 0
                if total_jsons > 0 and current_count > initial_count:
                    processed = current_count - initial_count
                    task_status['normalize']['progress'] = int((processed / total_jsons) * 90)
            
            process.wait()
            task_status['normalize']['message'] = ''.join(output_lines)
            task_status['normalize']['progress'] = 100
        except Exception as e:
            task_status['normalize']['message'] = f'Ошибка: {str(e)}'
            task_status['normalize']['progress'] = 0
        finally:
            task_status['normalize']['running'] = False
            task_status['normalize']['process'] = None
    
    thread = threading.Thread(target=run_normalize, daemon=True)
    thread.start()
    return jsonify({'status': 'started'})

@app.route('/api/tasks/<task_name>/status')
def get_task_status(task_name):
    """Получить статус задачи"""
    if task_name in task_status:
        # Не возвращаем объект process в JSON
        status = task_status[task_name].copy()
        if 'process' in status:
            del status['process']
        return jsonify(status)
    return jsonify({'error': 'Task not found'}), 404

@app.route('/api/tasks/<task_name>/stop', methods=['POST'])
def stop_task(task_name):
    """Остановить задачу"""
    if task_name not in task_status:
        return jsonify({'error': 'Task not found'}), 404
    
    if not task_status[task_name]['running']:
        return jsonify({'error': 'Task is not running'}), 400
    
    process = task_status[task_name].get('process')
    if process:
        try:
            print(f"[DEBUG] Останавливаю задачу {task_name}, PID: {process.pid}")
            process.terminate()
            # Ждем немного, если не завершился - убиваем
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                print(f"[DEBUG] Процесс не завершился, убиваю PID: {process.pid}")
                process.kill()
                process.wait()
            
            task_status[task_name]['message'] += '\n\n⚠️ Задача остановлена пользователем'
            task_status[task_name]['running'] = False
            task_status[task_name]['process'] = None
            print(f"[DEBUG] Задача {task_name} остановлена")
            return jsonify({'status': 'stopped'})
        except Exception as e:
            print(f"[DEBUG] Ошибка при остановке задачи: {e}")
            return jsonify({'error': f'Failed to stop task: {str(e)}'}), 500
    else:
        task_status[task_name]['running'] = False
        return jsonify({'status': 'stopped'})

if __name__ == '__main__':
    # Запускаем на порту 5001, так как 5000 часто занят AirPlay Receiver на macOS
    # Запускаем на всех интерфейсах (0.0.0.0), чтобы работал и localhost, и 127.0.0.1
    # Используем кастомный обработчик для уменьшения логов
    app.run(debug=True, host='0.0.0.0', port=5001, request_handler=QuietStatusHandler)

