#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backend API для веб-интерфейса управления расписаниями
"""

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Dict, List, Optional

app = Flask(__name__)
CORS(app)

# Пути к папкам
BASE_DIR = Path(__file__).parent.parent.parent
PDFS_DIR = BASE_DIR / 'schedules_pdf'
JSONS_DIR = BASE_DIR / 'schedules_json'
PARSED_DIR = BASE_DIR / 'schedules_parsed'
ABBREV_FILE = BASE_DIR / 'abbreviations.json'

# Статус выполнения задач
task_status = {
    'download': {'running': False, 'progress': 0, 'message': ''},
    'parse': {'running': False, 'progress': 0, 'message': ''},
    'normalize': {'running': False, 'progress': 0, 'message': ''}
}

@app.route('/api/status')
def status():
    """Получить статус сервера"""
    return jsonify({
        'status': 'ok',
        'pdfs_count': len(list(PDFS_DIR.glob('*.pdf'))) if PDFS_DIR.exists() else 0,
        'jsons_count': len(list(JSONS_DIR.glob('*.json'))) if JSONS_DIR.exists() else 0,
        'parsed_count': len(list(PARSED_DIR.glob('*.json'))) if PARSED_DIR.exists() else 0,
        'tasks': task_status
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
        task_status['download']['message'] = 'Starting download...'
        
        try:
            script_path = BASE_DIR / 'download_schedules.py'
            result = subprocess.run(
                ['python3', str(script_path)],
                capture_output=True,
                text=True,
                cwd=str(BASE_DIR)
            )
            task_status['download']['message'] = result.stdout + result.stderr
            task_status['download']['progress'] = 100
        except Exception as e:
            task_status['download']['message'] = f'Error: {str(e)}'
        finally:
            task_status['download']['running'] = False
    
    thread = threading.Thread(target=run_download)
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
        task_status['parse']['message'] = 'Starting parsing...'
        
        try:
            script_path = BASE_DIR / 'parse_all_schedules.py'
            result = subprocess.run(
                ['python3', str(script_path)],
                capture_output=True,
                text=True,
                cwd=str(BASE_DIR)
            )
            task_status['parse']['message'] = result.stdout + result.stderr
            task_status['parse']['progress'] = 100
        except Exception as e:
            task_status['parse']['message'] = f'Error: {str(e)}'
        finally:
            task_status['parse']['running'] = False
    
    thread = threading.Thread(target=run_parse)
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
        task_status['normalize']['message'] = 'Starting normalization...'
        
        try:
            script_path = BASE_DIR / 'normalize_disciplines.py'
            result = subprocess.run(
                ['python3', str(script_path)],
                capture_output=True,
                text=True,
                cwd=str(BASE_DIR)
            )
            task_status['normalize']['message'] = result.stdout + result.stderr
            task_status['normalize']['progress'] = 100
        except Exception as e:
            task_status['normalize']['message'] = f'Error: {str(e)}'
        finally:
            task_status['normalize']['running'] = False
    
    thread = threading.Thread(target=run_normalize)
    thread.start()
    return jsonify({'status': 'started'})

@app.route('/api/tasks/<task_name>/status')
def get_task_status(task_name):
    """Получить статус задачи"""
    if task_name in task_status:
        return jsonify(task_status[task_name])
    return jsonify({'error': 'Task not found'}), 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)

