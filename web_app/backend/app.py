from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import json
import subprocess
import os
import sys

# Вывод консоли в UTF-8 (кириллица без кракозябр)
_reconfigure = getattr(sys.stdout, 'reconfigure', None)
if _reconfigure is not None:
    try:
        _reconfigure(encoding='utf-8')
        _reconfigure_err = getattr(sys.stderr, 'reconfigure', None)
        if _reconfigure_err is not None:
            _reconfigure_err(encoding='utf-8')
    except Exception:
        pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import glob
import re
import shutil
import threading
import time
import csv
from datetime import datetime
from decimal import Decimal
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

# Корень проекта для импорта discipline_validate (сопоставление дисциплин по эмбеддингам)
def _project_root():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(current_dir))

if _project_root() not in sys.path:
    sys.path.insert(0, _project_root())

app = Flask(__name__)
CORS(app)

# Параметры подключения к БД (текущая / dev)
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'edro.su'),
    'port': int(os.environ.get('DB_PORT', '50003')),
    'user': os.environ.get('DB_USER', 'edro'),
    'password': os.environ.get('DB_PASSWORD', 'Pg123!'),
    'database': os.environ.get('DB_NAME', 'test_sursu_timetable')
}

# Параметры подключения к продакшн БД (для отправки расписания)
def _prod_db_config():
    host = os.environ.get('DB_PROD_HOST')
    if not host:
        return None
    return {
        'host': host,
        'port': int(os.environ.get('DB_PROD_PORT', '5432')),
        'user': os.environ.get('DB_PROD_USER', ''),
        'password': os.environ.get('DB_PROD_PASSWORD', ''),
        'database': os.environ.get('DB_PROD_NAME', '')
    }

# Глобальные переменные для отслеживания прогресса
script_status = {
    'parse_timetable': {'running': False, 'progress': 0, 'message': '', 'error': None},
    'clean_audiences': {'running': False, 'progress': 0, 'message': '', 'error': None},
    'load_timetable_to_db': {'running': False, 'progress': 0, 'message': '', 'error': None},
    'merge_timetable': {'running': False, 'progress': 0, 'message': '', 'error': None},
    'process_timetable': {'running': False, 'progress': 0, 'message': '', 'error': None},
    'fetch_teachers': {'running': False, 'progress': 0, 'message': '', 'error': None},
    'parse_aspi': {'running': False, 'progress': 0, 'message': '', 'error': None},
    'normalize_aspi': {'running': False, 'progress': 0, 'message': '', 'error': None},
    'load_aspi_to_db': {'running': False, 'progress': 0, 'message': '', 'error': None},
    'merge_aspi_to_intermediate': {'running': False, 'progress': 0, 'message': '', 'error': None}
}

def _make_json_serializable(obj):
    """Рекурсивно приводит данные к типам, сериализуемым в JSON (Decimal -> int/float)."""
    if isinstance(obj, dict):
        return {k: _make_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_json_serializable(x) for x in obj]
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    return obj


# Разрешённые таблицы для просмотра записей (включая расписание аспирантов)
ALLOWED_TABLES = ('timetable_cleaned', 'timetable_teacher', 'intermediate_timetable', 'timetable_aspi')

# Таблицы для бэкапа/восстановления (включая schedule и расписание аспирантов)
BACKUP_TABLES = ('timetable_cleaned', 'timetable_teacher', 'intermediate_timetable', 'timetable_aspi', 'schedule')
BACKUP_TABLE_LABELS = {
    'timetable_cleaned': 'Спаршенное расписание',
    'timetable_teacher': 'Занятость преподавателей',
    'intermediate_timetable': 'Промежуточное расписание',
    'timetable_aspi': 'Расписание аспирантов',
    'schedule': 'Расписание'
}

def get_table_param():
    """Возвращает имя таблицы из query param (timetable_cleaned, timetable_teacher, intermediate_timetable, timetable_aspi)."""
    table = request.args.get('table', '').strip()
    if table in ALLOWED_TABLES:
        return table
    return 'timetable_cleaned'

def get_project_root():
    """Возвращает корневую директорию проекта (где находятся скрипты parse_timetable_excel.py и clean_audiences.py)"""
    # Текущий файл: web_app/backend/app.py
    # Нужно подняться на 2 уровня вверх: web_app/backend -> web_app -> корень проекта
    current_dir = os.path.dirname(os.path.abspath(__file__))  # web_app/backend
    parent_dir = os.path.dirname(current_dir)  # web_app
    project_root = os.path.dirname(parent_dir)  # корень проекта (H:\Project\TimetableParser)
    return project_root


INPUT_TIMETABLE_DIR = os.path.join(get_project_root(), 'input', 'timetable')


def _normalize_group_for_search(s):
    """Нормализует строку группы для поиска: 606.22, 606 22 -> 606-22."""
    if not s or not isinstance(s, str):
        return ''
    s = re.sub(r'[\s.]+', '-', s.strip())
    s = re.sub(r'-+', '-', s)  # несколько дефисов в один
    return s.strip('-')


def find_group_in_timetable_files(group_query):
    """
    Ищет номер группы в Excel-файлах input/timetable (рекурсивно).
    Возвращает список: [{"file_path": "относительный/путь.xlsx", "file_name": "имя.xlsx", "sheet_name": "1 курс", "sheet_index": 1}, ...]
    """
    try:
        from openpyxl import load_workbook
    except ImportError:
        return []
    if not group_query or not isinstance(group_query, str):
        return []
    query_norm = _normalize_group_for_search(group_query)
    if not query_norm:
        return []
    results = []
    if not os.path.isdir(INPUT_TIMETABLE_DIR):
        return results
    for root, _dirs, files in os.walk(INPUT_TIMETABLE_DIR):
        for f in files:
            if not (f.endswith('.xlsx') and not f.startswith('~$')):
                continue
            full_path = os.path.join(root, f)
            try:
                wb = load_workbook(full_path, data_only=True, read_only=True)
            except Exception:
                continue
            rel_root = os.path.relpath(root, INPUT_TIMETABLE_DIR)
            if rel_root == '.':
                rel_dir = ''
            else:
                rel_dir = rel_root.replace('\\', '/') + '/'
            rel_path = rel_dir + f
            for sheet_idx, sheet_name in enumerate(wb.sheetnames, start=1):
                ws = wb[sheet_name]
                found = False
                for row in ws.iter_rows(values_only=True):
                    if found:
                        break
                    for cell in row or []:
                        if cell is None:
                            continue
                        cell_str = re.sub(r'[\s.]+', '-', str(cell).strip())
                        cell_str = re.sub(r'-+', '-', cell_str)
                        if query_norm in cell_str or group_query.strip() in str(cell):
                            found = True
                            break
                if found:
                    results.append({
                        'file_path': rel_path,
                        'file_name': f,
                        'sheet_name': sheet_name,
                        'sheet_index': sheet_idx
                    })
            try:
                wb.close()
            except Exception:
                pass
    return results

# --- Преподаватели (info/teacher_all.json) ---
TEACHER_KEYS = ['fio', 'post_name', 'post_struct', 'all_staj', 'staj_spec', 'phone', 'predmet']
TEACHER_FILE = os.path.join(get_project_root(), 'info', 'teacher_all.json')

def read_teachers():
    """Читает список преподавателей из info/teacher_all.json."""
    if not os.path.isfile(TEACHER_FILE):
        return []
    with open(TEACHER_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, list):
        return []
    # Нормализуем каждую запись: все ключи должны быть строками
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        row = {k: (item.get(k) or '') if isinstance(item.get(k), str) else str(item.get(k) or '') for k in TEACHER_KEYS}
        out.append(row)
    return out

def save_teachers(teachers):
    """Сохраняет список преподавателей в info/teacher_all.json (UTF-8, без escape)."""
    os.makedirs(os.path.dirname(TEACHER_FILE), exist_ok=True)
    with open(TEACHER_FILE, 'w', encoding='utf-8') as f:
        json.dump(teachers, f, ensure_ascii=False, indent=2)

def cleanup_output_files():
    """Удаляет файлы в output/timetable (кроме заблокированных — например открытых в Excel)."""
    output_dir = os.path.join(get_project_root(), 'output', 'timetable')
    if os.path.exists(output_dir):
        deleted_count = 0
        for file in glob.glob(os.path.join(output_dir, '*')):
            if os.path.isfile(file) and not os.path.basename(file).startswith('~$'):
                try:
                    os.remove(file)
                    deleted_count += 1
                    print(f"Удален файл: {file}")
                except OSError as e:
                    if e.winerror == 32 if hasattr(e, 'winerror') else getattr(e, 'errno', None) == 32:
                        print(f"Файл занят, пропуск: {os.path.basename(file)} (закройте в Excel при необходимости)")
                    else:
                        print(f"Ошибка при удалении {file}: {e}")
                except Exception as e:
                    print(f"Ошибка при удалении {file}: {e}")
        print(f"Удалено файлов: {deleted_count}")

def run_parse_timetable():
    """Запускает parse_timetable_excel.py"""
    script_status['parse_timetable']['running'] = True
    script_status['parse_timetable']['progress'] = 0
    script_status['parse_timetable']['message'] = 'Начало парсинга расписания...'
    script_status['parse_timetable']['error'] = None
    
    try:
        project_root = get_project_root()
        script_path = os.path.join(project_root, 'parse_timetable_excel.py')
        
        # Проверяем существование скрипта
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"Скрипт не найден: {script_path}")
        
        script_status['parse_timetable']['progress'] = 10
        script_status['parse_timetable']['message'] = 'Очистка выходных файлов...'
        cleanup_output_files()
        
        script_status['parse_timetable']['progress'] = 20
        script_status['parse_timetable']['message'] = 'Запуск скрипта парсинга...'
        
        # Запускаем скрипт с UTF-8, чтобы в консоли был читаемый русский текст
        env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
        process = subprocess.Popen(
            ['python', script_path],
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env,
            bufsize=1
        )
        
        script_status['parse_timetable']['progress'] = 40
        script_status['parse_timetable']['message'] = 'Обработка файлов...'
        
        # Читаем вывод в реальном времени
        output_lines = []
        
        # Простой способ чтения вывода
        stdout_stream = process.stdout
        while True:
            output = stdout_stream.readline() if stdout_stream is not None else ''
            if output == '' and process.poll() is not None:
                break
            if output:
                line = output.strip()
                if line:
                    output_lines.append(line)
                    print(f"Output: {line}")
                    # Обновляем прогресс на основе количества строк
                    progress = min(40 + min(len(output_lines) * 2, 50), 90)
                    script_status['parse_timetable']['progress'] = progress
                    script_status['parse_timetable']['message'] = f'Обработано строк: {len(output_lines)}'
        
        # Ждем завершения процесса
        return_code = process.wait()
        
        # Читаем ошибки, если есть
        stderr_stream = process.stderr
        stderr_output = stderr_stream.read() if stderr_stream is not None else ''
        if stderr_output:
            print(f"Stderr: {stderr_output}")
        
        if return_code == 0:
            script_status['parse_timetable']['progress'] = 100
            script_status['parse_timetable']['message'] = 'Парсинг завершен успешно!'
        else:
            error_msg = stderr_output if stderr_output else 'Неизвестная ошибка (код возврата: {})'.format(return_code)
            script_status['parse_timetable']['error'] = error_msg
            script_status['parse_timetable']['message'] = 'Ошибка при выполнении скрипта'
            script_status['parse_timetable']['progress'] = 0
    except Exception as e:
        script_status['parse_timetable']['error'] = str(e)
        script_status['parse_timetable']['message'] = f'Ошибка: {str(e)}'
        script_status['parse_timetable']['progress'] = 0
    finally:
        script_status['parse_timetable']['running'] = False

def run_clean_audiences():
    """Запускает clean_audiences.py"""
    script_status['clean_audiences']['running'] = True
    script_status['clean_audiences']['progress'] = 0
    script_status['clean_audiences']['message'] = 'Начало очистки аудиторий...'
    script_status['clean_audiences']['error'] = None
    
    try:
        project_root = get_project_root()
        script_path = os.path.join(project_root, 'clean_audiences.py')
        
        # Проверяем существование скрипта
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"Скрипт не найден: {script_path}")
        
        script_status['clean_audiences']['progress'] = 10
        script_status['clean_audiences']['message'] = 'Очистка выходных файлов...'
        
        # Удаляем только cleaned файлы
        output_dir = os.path.join(project_root, 'output', 'timetable')
        for file in glob.glob(os.path.join(output_dir, '*_cleaned.*')):
            if os.path.isfile(file):
                try:
                    os.remove(file)
                except OSError as e:
                    if getattr(e, 'winerror', None) == 32:
                        print(f"Файл занят, пропуск: {os.path.basename(file)}")
                except Exception as e:
                    print(f"Ошибка при удалении {file}: {e}")
        
        script_status['clean_audiences']['progress'] = 20
        script_status['clean_audiences']['message'] = 'Запуск скрипта очистки...'
        
        # Запускаем скрипт без загрузки в БД (только обработка); UTF-8 для вывода с кириллицей
        env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
        process = subprocess.Popen(
            ['python', script_path, '--no-db'],
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env,
            bufsize=1
        )
        
        script_status['clean_audiences']['progress'] = 40
        script_status['clean_audiences']['message'] = 'Обработка данных...'
        
        # Читаем вывод в реальном времени
        output_lines = []
        stdout_stream = process.stdout
        while True:
            output = stdout_stream.readline() if stdout_stream is not None else ''
            if output == '' and process.poll() is not None:
                break
            if output:
                line = output.strip()
                if line:
                    output_lines.append(line)
                    print(f"Output: {line}")
                    # Обновляем прогресс на основе количества строк
                    progress = min(40 + min(len(output_lines) * 2, 50), 90)
                    script_status['clean_audiences']['progress'] = progress
                    script_status['clean_audiences']['message'] = f'Обработано записей: {len(output_lines)}'
        
        # Ждем завершения процесса
        return_code = process.wait()
        
        # Читаем ошибки, если есть
        stderr_stream = process.stderr
        stderr_output = stderr_stream.read() if stderr_stream is not None else ''
        if stderr_output:
            print(f"Stderr: {stderr_output}")
        
        if return_code == 0:
            script_status['clean_audiences']['progress'] = 100
            script_status['clean_audiences']['message'] = 'Очистка завершена успешно!'
        else:
            error_msg = stderr_output if stderr_output else 'Неизвестная ошибка (код возврата: {})'.format(return_code)
            script_status['clean_audiences']['error'] = error_msg
            script_status['clean_audiences']['message'] = 'Ошибка при выполнении скрипта'
            script_status['clean_audiences']['progress'] = 0
    except Exception as e:
        script_status['clean_audiences']['error'] = str(e)
        script_status['clean_audiences']['message'] = f'Ошибка: {str(e)}'
        script_status['clean_audiences']['progress'] = 0
    finally:
        script_status['clean_audiences']['running'] = False

def run_load_timetable_to_db():
    """Загружает данные в timetable_cleaned. Если очищенного файла нет — сначала запускает очистку (clean_audiences без --no-db)."""
    script_status['load_timetable_to_db']['running'] = True
    script_status['load_timetable_to_db']['progress'] = 0
    script_status['load_timetable_to_db']['message'] = 'Подготовка загрузки в БД...'
    script_status['load_timetable_to_db']['error'] = None
    try:
        project_root = get_project_root()
        excel_cleaned = os.path.join(project_root, 'output', 'timetable', 'timetable_processed_cleaned.xlsx')
        excel_processed = os.path.join(project_root, 'output', 'timetable', 'timetable_processed.xlsx')
        script_path = os.path.join(project_root, 'clean_audiences.py')
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"Скрипт не найден: {script_path}")
        # Если очищенного файла нет, но есть спаршенный — сначала выполняем очистку (она же сохранит в БД)
        if not os.path.isfile(excel_cleaned):
            if os.path.isfile(excel_processed):
                script_status['load_timetable_to_db']['message'] = 'Очистка аудиторий и загрузка в БД...'
                script_status['load_timetable_to_db']['progress'] = 15
                env = {
                    **os.environ,
                    'PYTHONIOENCODING': 'utf-8',
                    'DB_HOST': str(DB_CONFIG.get('host', '')),
                    'DB_PORT': str(DB_CONFIG.get('port', '')),
                    'DB_USER': str(DB_CONFIG.get('user', '')),
                    'DB_PASSWORD': str(DB_CONFIG.get('password', '')),
                    'DB_NAME': str(DB_CONFIG.get('database', '')),
                }
                process = subprocess.Popen(
                    ['python', script_path],
                    cwd=project_root,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    env=env,
                    bufsize=1
                )
                stdout_output, stderr_output = process.communicate()
                return_code = process.returncode
                if stdout_output:
                    for line in stdout_output.splitlines():
                        if line.strip():
                            print(f"[LOAD_DB] {line}", flush=True)
                if stderr_output and stderr_output.strip():
                    for line in stderr_output.splitlines():
                        if line.strip():
                            print(f"[LOAD_DB stderr] {line}", flush=True)
                if return_code != 0:
                    error_msg = stderr_output.strip() if stderr_output else f'Код возврата: {return_code}'
                    script_status['load_timetable_to_db']['error'] = error_msg
                    script_status['load_timetable_to_db']['message'] = 'Ошибка при очистке или загрузке в БД'
                    script_status['load_timetable_to_db']['progress'] = 0
                    return
                script_status['load_timetable_to_db']['progress'] = 100
                script_status['load_timetable_to_db']['message'] = 'Данные расписания загружены в БД.'
                return
            raise FileNotFoundError(
                'Нет файла timetable_processed.xlsx. Сначала выполните «Парсинг расписания», затем «Загрузить в БД» или «Очистка аудиторий».'
            )
        script_status['load_timetable_to_db']['progress'] = 20
        script_status['load_timetable_to_db']['message'] = 'Загрузка в БД (timetable_cleaned)...'
        env = {
            **os.environ,
            'PYTHONIOENCODING': 'utf-8',
            'DB_HOST': str(DB_CONFIG.get('host', '')),
            'DB_PORT': str(DB_CONFIG.get('port', '')),
            'DB_USER': str(DB_CONFIG.get('user', '')),
            'DB_PASSWORD': str(DB_CONFIG.get('password', '')),
            'DB_NAME': str(DB_CONFIG.get('database', '')),
        }
        process = subprocess.Popen(
            ['python', script_path, '--db-only'],
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env,
            bufsize=1
        )
        stdout_output, stderr_output = process.communicate()
        return_code = process.returncode
        if stdout_output:
            for line in stdout_output.splitlines():
                if line.strip():
                    print(f"[LOAD_DB] {line}", flush=True)
        if stderr_output and stderr_output.strip():
            for line in stderr_output.splitlines():
                if line.strip():
                    print(f"[LOAD_DB stderr] {line}", flush=True)
        if return_code != 0:
            error_msg = stderr_output.strip() if stderr_output else f'Код возврата: {return_code}'
            script_status['load_timetable_to_db']['error'] = error_msg
            script_status['load_timetable_to_db']['message'] = 'Ошибка загрузки в БД'
            script_status['load_timetable_to_db']['progress'] = 0
        else:
            script_status['load_timetable_to_db']['progress'] = 100
            script_status['load_timetable_to_db']['message'] = 'Данные расписания загружены в БД.'
    except Exception as e:
        script_status['load_timetable_to_db']['error'] = str(e)
        script_status['load_timetable_to_db']['message'] = f'Ошибка: {str(e)}'
        script_status['load_timetable_to_db']['progress'] = 0
    finally:
        script_status['load_timetable_to_db']['running'] = False

def run_merge_timetable():
    """Слияние timetable_cleaned и timetable_teacher в intermediate_timetable.
    Данные только из timetable_cleaned (кроме id), ФИО только из timetable_teacher.
    Join по дню, паре, группе; проверки: неделя и аудитория совпадают или нет (week_error, audience_error).
    """
    script_status['merge_timetable']['running'] = True
    script_status['merge_timetable']['progress'] = 0
    script_status['merge_timetable']['message'] = 'Подготовка слияния...'
    script_status['merge_timetable']['error'] = None
    try:
        script_status['merge_timetable']['progress'] = 10
        script_status['merge_timetable']['message'] = 'Создание таблицы intermediate_timetable...'
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS intermediate_timetable")
        conn.commit()
        cursor.execute("""
            CREATE TABLE intermediate_timetable (
                id SERIAL PRIMARY KEY,
                cleaned_id INTEGER,
                teacher_id INTEGER,
                day_of_week VARCHAR(50),
                pair_number INTEGER,
                subject_name TEXT,
                discipline_original TEXT,
                lecture_type VARCHAR(50),
                audience VARCHAR(50),
                group_name VARCHAR(50),
                week_type VARCHAR(50),
                subgroup INTEGER,
                institute TEXT,
                course VARCHAR(10),
                direction TEXT,
                department TEXT,
                is_external BOOLEAN,
                is_remote BOOLEAN,
                num_subgroups INTEGER,
                fio TEXT,
                week_error BOOLEAN,
                duration_pairs NUMERIC(3,1),
                audience_error BOOLEAN,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        script_status['merge_timetable']['progress'] = 30
        script_status['merge_timetable']['message'] = 'Очистка и слияние данных...'
        cursor.execute("ALTER TABLE timetable_cleaned ADD COLUMN IF NOT EXISTS duration_pairs NUMERIC(3,1)")
        conn.commit()
        # Основа — вся timetable_cleaned; из timetable_teacher только fio и флаги ошибок (по одному преподавателю на день/пара/группа).
        cursor.execute("""
            INSERT INTO intermediate_timetable (
                cleaned_id, teacher_id,
                day_of_week, pair_number, subject_name, discipline_original, lecture_type, audience,
                group_name, week_type, subgroup, institute, course, direction,
                department, is_external, is_remote, num_subgroups,
                fio, week_error, duration_pairs, audience_error
            )
            SELECT
                c.id,
                t.id,
                c.day_of_week,
                c.pair_number,
                c.subject_name,
                NULL,
                c.lecture_type,
                c.audience,
                c.group_name,
                c.week_type,
                c.subgroup,
                c.institute,
                c.course,
                c.direction,
                c.department,
                c.is_external,
                c.is_remote,
                c.num_subgroups,
                t.fio,
                CASE WHEN t.id IS NULL THEN NULL ELSE (NULLIF(TRIM(c.week_type), '') IS DISTINCT FROM NULLIF(TRIM(t.week_type), '')) END AS week_error,
                c.duration_pairs,
                CASE WHEN t.id IS NULL THEN NULL ELSE (NULLIF(TRIM(c.audience), '') IS DISTINCT FROM NULLIF(TRIM(t.audience), '')) END AS audience_error
            FROM timetable_cleaned c
            LEFT JOIN (
                SELECT id, day_of_week, pair_number, group_name, week_type, fio, audience,
                       ROW_NUMBER() OVER (
                           PARTITION BY NULLIF(TRIM(day_of_week), ''), pair_number, NULLIF(TRIM(group_name), ''),
                                      NULLIF(TRIM(week_type), '')
                           ORDER BY id
                       ) AS rn
                FROM timetable_teacher
            ) t
                ON t.rn = 1
               AND NULLIF(TRIM(c.day_of_week), '') IS NOT DISTINCT FROM NULLIF(TRIM(t.day_of_week), '')
               AND c.pair_number IS NOT DISTINCT FROM t.pair_number
               AND NULLIF(TRIM(c.group_name), '') IS NOT DISTINCT FROM NULLIF(TRIM(t.group_name), '')
               AND NULLIF(TRIM(c.week_type), '') IS NOT DISTINCT FROM NULLIF(TRIM(t.week_type), '')
        """)
        conn.commit()
        n = cursor.rowcount
        cursor.close()
        conn.close()
        script_status['merge_timetable']['progress'] = 100
        script_status['merge_timetable']['message'] = f'Готово. Загружено записей: {n}'
    except Exception as e:
        script_status['merge_timetable']['error'] = str(e)
        script_status['merge_timetable']['message'] = f'Ошибка: {str(e)}'
        script_status['merge_timetable']['progress'] = 0
    finally:
        script_status['merge_timetable']['running'] = False

def load_teacher_csv_to_db():
    """Создаёт таблицу timetable_teacher при необходимости и загружает в неё output/timetable_teacher.csv"""
    csv_path = os.path.join(get_project_root(), 'output', 'timetable_teacher.csv')
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f'Файл не найден: {csv_path}. Сначала запустите process_timetable.py.')
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    create_sql = """
    CREATE TABLE IF NOT EXISTS timetable_teacher (
        id SERIAL PRIMARY KEY,
        fio TEXT,
        pair_number INTEGER,
        day_of_week VARCHAR(50),
        group_name VARCHAR(50),
        audience VARCHAR(50),
        department TEXT,
        week_type VARCHAR(50),
        subgroup INTEGER,
        num_subgroups INTEGER,
        is_external BOOLEAN,
        is_remote BOOLEAN,
        subject_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    cursor.execute(create_sql)
    conn.commit()
    cursor.execute("TRUNCATE TABLE timetable_teacher")
    conn.commit()
    rows_to_insert = []
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            def to_int(v):
                if v is None or str(v).strip() == '':
                    return None
                try:
                    return int(v)
                except (ValueError, TypeError):
                    return None
            def to_bool(v):
                if v is None or str(v).strip() == '':
                    return False
                s = str(v).lower()
                return s in ('true', '1', 'yes', 't')
            rows_to_insert.append((
                row.get('fio') or None,
                to_int(row.get('pair_number')),
                row.get('day_of_week') or None,
                (row.get('group_name') or row.get('group') or '').strip() or None,
                row.get('audience') or None,
                row.get('department') or None,
                (row.get('week_type') or row.get('week') or '').strip() or None,
                to_int(row.get('subgroup')),
                to_int(row.get('num_subgroups')),
                to_bool(row.get('is_external')),
                to_bool(row.get('is_remote')),
                row.get('subject_name') or None,
            ))
    if rows_to_insert:
        insert_sql = """
        INSERT INTO timetable_teacher (
            fio, pair_number, day_of_week, group_name, audience, department,
            week_type, subgroup, num_subgroups, is_external, is_remote, subject_name
        ) VALUES %s
        """
        execute_values(cursor, insert_sql, rows_to_insert)
        conn.commit()
    cursor.close()
    conn.close()
    return len(rows_to_insert)

def run_process_timetable():
    """Запускает process_timetable.py и загружает результат в timetable_teacher"""
    script_status['process_timetable']['running'] = True
    script_status['process_timetable']['progress'] = 0
    script_status['process_timetable']['message'] = 'Начало парсинга занятости преподавателей...'
    script_status['process_timetable']['error'] = None
    try:
        project_root = get_project_root()
        script_path = os.path.join(project_root, 'process_timetable.py')
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"Скрипт не найден: {script_path}")
        script_status['process_timetable']['progress'] = 10
        script_status['process_timetable']['message'] = 'Запуск process_timetable.py...'
        env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
        process = subprocess.Popen(
            ['python', script_path],
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env,
            bufsize=1
        )
        script_status['process_timetable']['progress'] = 40
        script_status['process_timetable']['message'] = 'Обработка файла занятости...'
        output_lines = []
        stdout_stream = process.stdout
        while True:
            out = stdout_stream.readline() if stdout_stream is not None else ''
            if out == '' and process.poll() is not None:
                break
            if out:
                line = out.strip()
                if line:
                    output_lines.append(line)
                    script_status['process_timetable']['progress'] = min(40 + min(len(output_lines) * 2, 50), 90)
                    script_status['process_timetable']['message'] = f'Обработано строк: {len(output_lines)}'
        return_code = process.wait()
        stderr_stream = process.stderr
        stderr_output = stderr_stream.read() if stderr_stream is not None else ''
        if return_code != 0:
            error_msg = stderr_output if stderr_output else f'Код возврата: {return_code}'
            script_status['process_timetable']['error'] = error_msg
            script_status['process_timetable']['message'] = 'Ошибка при выполнении скрипта'
            script_status['process_timetable']['progress'] = 0
        else:
            script_status['process_timetable']['progress'] = 92
            script_status['process_timetable']['message'] = 'Загрузка в БД (timetable_teacher)...'
            try:
                n = load_teacher_csv_to_db()
                script_status['process_timetable']['progress'] = 100
                script_status['process_timetable']['message'] = f'Готово. Загружено записей: {n}'
            except Exception as e:
                script_status['process_timetable']['error'] = str(e)
                script_status['process_timetable']['message'] = f'Ошибка загрузки в БД: {str(e)}'
                script_status['process_timetable']['progress'] = 0
    except Exception as e:
        script_status['process_timetable']['error'] = str(e)
        script_status['process_timetable']['message'] = f'Ошибка: {str(e)}'
        script_status['process_timetable']['progress'] = 0
    finally:
        script_status['process_timetable']['running'] = False

@app.route('/api/status/<script_name>', methods=['GET'])
def get_status(script_name):
    """Возвращает статус выполнения скрипта"""
    if script_name in script_status:
        return jsonify(script_status[script_name])
    return jsonify({'error': 'Script not found'}), 404

@app.route('/api/run/parse_timetable', methods=['POST'])
def run_parse():
    """Запускает parse_timetable_excel.py"""
    if script_status['parse_timetable']['running']:
        return jsonify({'error': 'Script is already running'}), 400
    
    thread = threading.Thread(target=run_parse_timetable)
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': 'Script started'})

@app.route('/api/run/clean_audiences', methods=['POST'])
def run_clean():
    """Запускает clean_audiences.py (только обработка, без загрузки в БД)"""
    if script_status['clean_audiences']['running']:
        return jsonify({'error': 'Script is already running'}), 400
    
    thread = threading.Thread(target=run_clean_audiences)
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': 'Script started'})

@app.route('/api/run/load_timetable_to_db', methods=['POST'])
def run_load_timetable_to_db_route():
    """Загружает timetable_processed_cleaned в БД (timetable_cleaned)"""
    if script_status['load_timetable_to_db']['running']:
        return jsonify({'error': 'Script is already running'}), 400
    thread = threading.Thread(target=run_load_timetable_to_db)
    thread.daemon = True
    thread.start()
    return jsonify({'message': 'Script started'})

@app.route('/api/run/merge_timetable', methods=['POST'])
def run_merge_timetable_route():
    """Слияние timetable_cleaned и timetable_teacher в intermediate_timetable"""
    if script_status['merge_timetable']['running']:
        return jsonify({'error': 'Script is already running'}), 400
    thread = threading.Thread(target=run_merge_timetable)
    thread.daemon = True
    thread.start()
    return jsonify({'message': 'Script started'})

@app.route('/api/run/process_timetable', methods=['POST'])
def run_process_timetable_route():
    """Запускает process_timetable.py (занятость преподавателей) и загружает в timetable_teacher"""
    if script_status['process_timetable']['running']:
        return jsonify({'error': 'Script is already running'}), 400
    thread = threading.Thread(target=run_process_timetable)
    thread.daemon = True
    thread.start()
    return jsonify({'message': 'Script started'})


def run_parse_aspi():
    """Запускает parse_aspi.py — парсинг расписания аспирантов из .docx в aspi/aspi → JSON в aspi/output."""
    script_status['parse_aspi']['running'] = True
    script_status['parse_aspi']['progress'] = 0
    script_status['parse_aspi']['message'] = 'Начало парсинга расписания аспирантов...'
    script_status['parse_aspi']['error'] = None
    try:
        project_root = get_project_root()
        aspi_dir = os.path.join(project_root, 'aspi')
        script_path = os.path.join(aspi_dir, 'parse_aspi.py')
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"Скрипт не найден: {script_path}")
        script_status['parse_aspi']['progress'] = 10
        script_status['parse_aspi']['message'] = 'Запуск parse_aspi.py...'
        env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
        process = subprocess.Popen(
            [sys.executable, script_path],
            cwd=aspi_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env,
            bufsize=1
        )
        script_status['parse_aspi']['progress'] = 40
        script_status['parse_aspi']['message'] = 'Обработка .docx файлов...'
        output_lines = []
        stdout_stream = process.stdout
        while True:
            out = stdout_stream.readline() if stdout_stream is not None else ''
            if out == '' and process.poll() is not None:
                break
            if out:
                line = out.strip()
                if line:
                    output_lines.append(line)
                    script_status['parse_aspi']['progress'] = min(40 + min(len(output_lines) * 5, 50), 90)
                    script_status['parse_aspi']['message'] = line[:80] if len(line) > 80 else line
        return_code = process.wait()
        stderr_stream = process.stderr
        stderr_output = stderr_stream.read() if stderr_stream is not None else ''
        if return_code != 0:
            error_msg = stderr_output.strip() if stderr_output else f'Код возврата: {return_code}'
            script_status['parse_aspi']['error'] = error_msg
            script_status['parse_aspi']['message'] = 'Ошибка при выполнении скрипта'
            script_status['parse_aspi']['progress'] = 0
        else:
            script_status['parse_aspi']['progress'] = 100
            script_status['parse_aspi']['message'] = 'Парсинг расписания аспирантов завершён. Результаты в aspi/output/'
    except Exception as e:
        script_status['parse_aspi']['error'] = str(e)
        script_status['parse_aspi']['message'] = f'Ошибка: {str(e)}'
        script_status['parse_aspi']['progress'] = 0
    finally:
        script_status['parse_aspi']['running'] = False


@app.route('/api/run/parse_aspi', methods=['POST'])
def run_parse_aspi_route():
    """Запускает parse_aspi.py (парсинг расписания аспирантов из .docx)."""
    if script_status['parse_aspi']['running']:
        return jsonify({'error': 'Script is already running'}), 400
    thread = threading.Thread(target=run_parse_aspi)
    thread.daemon = True
    thread.start()
    return jsonify({'message': 'Script started'})


def run_normalize_aspi():
    """Запускает normalize_aspi.py — нормализация JSON аспирантов (ФИО, дни, дисциплины, audience)."""
    script_status['normalize_aspi']['running'] = True
    script_status['normalize_aspi']['progress'] = 0
    script_status['normalize_aspi']['message'] = 'Начало нормализации расписания аспирантов...'
    script_status['normalize_aspi']['error'] = None
    try:
        project_root = get_project_root()
        aspi_dir = os.path.join(project_root, 'aspi')
        script_path = os.path.join(aspi_dir, 'normalize_aspi.py')
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"Скрипт не найден: {script_path}")
        script_status['normalize_aspi']['progress'] = 10
        script_status['normalize_aspi']['message'] = 'Запуск normalize_aspi.py...'
        env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
        process = subprocess.Popen(
            [sys.executable, script_path],
            cwd=aspi_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env,
            bufsize=1
        )
        script_status['normalize_aspi']['progress'] = 40
        script_status['normalize_aspi']['message'] = 'Нормализация JSON...'
        output_lines = []
        stdout_stream = process.stdout
        while True:
            out = stdout_stream.readline() if stdout_stream is not None else ''
            if out == '' and process.poll() is not None:
                break
            if out:
                line = out.strip()
                if line:
                    output_lines.append(line)
                    script_status['normalize_aspi']['progress'] = min(40 + min(len(output_lines) * 5, 50), 90)
                    script_status['normalize_aspi']['message'] = line[:80] if len(line) > 80 else line
        return_code = process.wait()
        stderr_stream = process.stderr
        stderr_output = stderr_stream.read() if stderr_stream is not None else ''
        if return_code != 0:
            error_msg = stderr_output.strip() if stderr_output else f'Код возврата: {return_code}'
            script_status['normalize_aspi']['error'] = error_msg
            script_status['normalize_aspi']['message'] = 'Ошибка при выполнении скрипта'
            script_status['normalize_aspi']['progress'] = 0
        else:
            script_status['normalize_aspi']['progress'] = 100
            script_status['normalize_aspi']['message'] = 'Нормализация завершена. Файлы в aspi/output/ обновлены.'
    except Exception as e:
        script_status['normalize_aspi']['error'] = str(e)
        script_status['normalize_aspi']['message'] = f'Ошибка: {str(e)}'
        script_status['normalize_aspi']['progress'] = 0
    finally:
        script_status['normalize_aspi']['running'] = False


@app.route('/api/run/normalize_aspi', methods=['POST'])
def run_normalize_aspi_route():
    """Запускает normalize_aspi.py (нормализация JSON аспирантов)."""
    if script_status['normalize_aspi']['running']:
        return jsonify({'error': 'Script is already running'}), 400
    thread = threading.Thread(target=run_normalize_aspi)
    thread.daemon = True
    thread.start()
    return jsonify({'message': 'Script started'})


ASPI_OUTPUT_SKIP = ('_all.json', 'unresolved_fio.json', 'fio_overrides.json', 'unresolved_parse.json')


def _aspi_output_dir():
    """Единый абсолютный путь к aspi/output для чтения/записи и для передачи нормализатору."""
    return os.path.abspath(os.path.join(get_project_root(), 'aspi', 'output'))


@app.route('/api/aspi/unresolved', methods=['GET'])
def aspi_unresolved():
    """Возвращает список нераспознанных ФИО (после нормализации)."""
    try:
        aspi_output = _aspi_output_dir()
        path = os.path.join(aspi_output, 'unresolved_fio.json')
        if not os.path.isfile(path):
            return jsonify({'items': []})
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            data = json.load(f)
        items = data if isinstance(data, list) else []
        return jsonify({'items': items})
    except Exception as e:
        return jsonify({'error': str(e), 'items': []}), 500


@app.route('/api/aspi/unresolved-parse', methods=['GET'])
def aspi_unresolved_parse():
    """Возвращает список записей парсинга для ручной проверки (группа не извлечена, обрыв дисциплины и т.д.)."""
    try:
        aspi_output = _aspi_output_dir()
        path = os.path.join(aspi_output, 'unresolved_parse.json')
        if not os.path.isfile(path):
            return jsonify({'items': []})
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            data = json.load(f)
        items = data if isinstance(data, list) else []
        return jsonify({'items': items})
    except Exception as e:
        return jsonify({'error': str(e), 'items': []}), 500


def _apply_fio_overrides_to_record(fio_str, overrides):
    """В строке fio (например 'A | B') заменяет короткие ФИО на полные по словарю overrides."""
    if not (fio_str and overrides):
        return fio_str or ''
    parts = [p.strip() for p in (fio_str or '').split('|') if p.strip()]
    out = [overrides.get(p, p) for p in parts]
    return ' | '.join(out)


@app.route('/api/aspi/apply-fio-replacements', methods=['POST'])
def aspi_apply_fio_replacements():
    """
    Дообработка без полной нормализации: принимает замены ФИО, дописывает в fio_overrides.json,
    применяет их к уже существующим JSON в aspi/output (только поле fio), обновляет unresolved_fio.json
    и перезагружает в БД. Нормализатор не запускается.
    """
    try:
        data = request.get_json() or {}
        raw_replacements = data.get('replacements')
        replacements = raw_replacements if isinstance(raw_replacements, dict) else {}
        replacements = {k.strip(): (v or '').strip() for k, v in replacements.items() if (k or '').strip() and (v or '').strip()}
        if not replacements:
            return jsonify({'error': 'Нет замен для применения (заполните «Заменить на»)'}), 400
        aspi_output = _aspi_output_dir()
        os.makedirs(aspi_output, exist_ok=True)
        overrides_path = os.path.join(aspi_output, 'fio_overrides.json')
        existing = {}
        if os.path.isfile(overrides_path):
            try:
                with open(overrides_path, 'r', encoding='utf-8', errors='replace') as f:
                    existing = json.load(f)
                if not isinstance(existing, dict):
                    existing = {}
            except Exception:
                existing = {}
        merged = {**existing, **replacements}
        with open(overrides_path, 'w', encoding='utf-8') as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)

        # Применяем замены только к полю fio в существующих JSON (нормализатор не запускаем)
        json_files = [f for f in glob.glob(os.path.join(aspi_output, '*.json')) if os.path.basename(f) not in ASPI_OUTPUT_SKIP]
        for path in json_files:
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    records = json.load(f)
                if not isinstance(records, list):
                    continue
                for rec in records:
                    if isinstance(rec, dict) and 'fio' in rec:
                        rec['fio'] = _apply_fio_overrides_to_record(rec.get('fio'), merged)
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(records, f, ensure_ascii=False, indent=2)
            except Exception as e:
                return jsonify({'error': f'Ошибка при обновлении {os.path.basename(path)}: {str(e)}'}), 500

        # Обновляем _all.json: перечитываем все курсовые файлы и собираем сводку
        all_normalized = {}
        for path in sorted(json_files):
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    all_normalized[os.path.splitext(os.path.basename(path))[0]] = json.load(f)
            except Exception:
                pass
        if all_normalized:
            summary_path = os.path.join(aspi_output, '_all.json')
            with open(summary_path, 'w', encoding='utf-8') as f:
                json.dump(all_normalized, f, ensure_ascii=False, indent=2)

        # Убираем из unresolved_fio.json те ФИО, для которых добавили замену
        unresolved_path = os.path.join(aspi_output, 'unresolved_fio.json')
        current_unresolved = []
        if os.path.isfile(unresolved_path):
            try:
                with open(unresolved_path, 'r', encoding='utf-8', errors='replace') as f:
                    current_unresolved = json.load(f)
                if not isinstance(current_unresolved, list):
                    current_unresolved = []
            except Exception:
                pass
        new_unresolved = [u for u in current_unresolved if (u or '').strip() and (u or '').strip() not in merged]
        with open(unresolved_path, 'w', encoding='utf-8') as f:
            json.dump(new_unresolved, f, ensure_ascii=False, indent=2)

        # Загрузка в БД
        run_load_aspi_to_db()

        return jsonify({
            'message': f'Применено замен: {len(replacements)}. Дообработка выполнена (нормализатор не запускался).',
            'items': new_unresolved
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def run_load_aspi_to_db():
    """Загружает нормализованные JSON из aspi/output в таблицу timetable_aspi."""
    script_status['load_aspi_to_db']['running'] = True
    script_status['load_aspi_to_db']['progress'] = 0
    script_status['load_aspi_to_db']['message'] = 'Подготовка загрузки в БД...'
    script_status['load_aspi_to_db']['error'] = None
    try:
        aspi_output = _aspi_output_dir()
        if not os.path.isdir(aspi_output):
            raise FileNotFoundError('Папка aspi/output не найдена. Сначала запустите парсер и нормализацию.')
        json_files = [f for f in glob.glob(os.path.join(aspi_output, '*.json')) if os.path.basename(f) not in ASPI_OUTPUT_SKIP]
        if not json_files:
            raise FileNotFoundError('В aspi/output нет JSON-файлов (кроме _all.json). Запустите парсер и нормализацию.')
        script_status['load_aspi_to_db']['progress'] = 10
        script_status['load_aspi_to_db']['message'] = 'Чтение нормализованных JSON...'
        all_rows = []
        for path in sorted(json_files):
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                data = json.load(f)
            if isinstance(data, list):
                all_rows.extend(data)
        if not all_rows:
            raise ValueError('Нет записей для загрузки.')
        script_status['load_aspi_to_db']['progress'] = 30
        script_status['load_aspi_to_db']['message'] = f'Загрузка в таблицу timetable_aspi ({len(all_rows)} записей)...'
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS timetable_aspi (
                id SERIAL PRIMARY KEY,
                day_of_week VARCHAR(50),
                pair_number TEXT,
                subject_name TEXT,
                discipline_original TEXT,
                audience VARCHAR(255),
                group_name VARCHAR(100),
                week_type VARCHAR(50),
                fio TEXT,
                course VARCHAR(20),
                scientific_specialty TEXT,
                institute TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cursor.execute("ALTER TABLE timetable_aspi ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        conn.commit()
        cursor.execute("ALTER TABLE timetable_aspi ADD COLUMN IF NOT EXISTS institute TEXT")
        conn.commit()
        cursor.execute("TRUNCATE TABLE timetable_aspi")
        conn.commit()
        cols = ['day_of_week', 'pair_number', 'subject_name', 'discipline_original', 'audience',
                'group_name', 'week_type', 'fio', 'course', 'scientific_specialty', 'institute']
        def row_vals(rec):
            pair = rec.get('pair_number')
            if pair is not None and not isinstance(pair, str):
                pair = str(pair)
            return (
                (rec.get('day_of_week') or '').strip() or None,
                pair,
                (rec.get('subject_name') or '').strip() or None,
                (rec.get('discipline_original') or '').strip() or None,
                (rec.get('audience') or '').strip() or None,
                (rec.get('group_name') or '').strip() or None,
                (rec.get('week_type') or '').strip() or None,
                (rec.get('fio') or '').strip() or None,
                (rec.get('course') or '').strip() or None,
                (rec.get('scientific_specialty') or rec.get('научная_специальность') or '').strip() or None,
                (rec.get('institute') or '').strip() or None,
            )
        rows_to_insert = [row_vals(rec) for rec in all_rows]
        insert_sql = """
            INSERT INTO timetable_aspi (day_of_week, pair_number, subject_name, discipline_original,
                audience, group_name, week_type, fio, course, scientific_specialty, institute)
            VALUES %s
        """
        execute_values(cursor, insert_sql, rows_to_insert)
        conn.commit()
        cursor.close()
        conn.close()
        script_status['load_aspi_to_db']['progress'] = 100
        script_status['load_aspi_to_db']['message'] = f'Готово. Загружено записей в timetable_aspi: {len(rows_to_insert)}'
    except Exception as e:
        script_status['load_aspi_to_db']['error'] = str(e)
        script_status['load_aspi_to_db']['message'] = f'Ошибка: {str(e)}'
        script_status['load_aspi_to_db']['progress'] = 0
    finally:
        script_status['load_aspi_to_db']['running'] = False


@app.route('/api/run/load_aspi_to_db', methods=['POST'])
def run_load_aspi_to_db_route():
    """Загружает нормализованное расписание аспирантов из aspi/output в timetable_aspi."""
    if script_status['load_aspi_to_db']['running']:
        return jsonify({'error': 'Script is already running'}), 400
    thread = threading.Thread(target=run_load_aspi_to_db)
    thread.daemon = True
    thread.start()
    return jsonify({'message': 'Script started'})


def run_merge_aspi_to_intermediate():
    """Добавляет записи из timetable_aspi в intermediate_timetable."""
    script_status['merge_aspi_to_intermediate']['running'] = True
    script_status['merge_aspi_to_intermediate']['progress'] = 0
    script_status['merge_aspi_to_intermediate']['message'] = 'Добавление расписания аспирантов в intermediate_timetable...'
    script_status['merge_aspi_to_intermediate']['error'] = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'intermediate_timetable'"
        )
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            raise RuntimeError('Таблица intermediate_timetable не найдена. Сначала выполните «Слияние расписания» во вкладке «Бакалавры + магистры».')
        cursor.execute("ALTER TABLE intermediate_timetable ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        conn.commit()
        cursor.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'timetable_aspi'"
        )
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            raise RuntimeError('Таблица timetable_aspi не найдена. Сначала выполните «Добавить в БД» для аспирантов.')
        script_status['merge_aspi_to_intermediate']['progress'] = 30
        script_status['merge_aspi_to_intermediate']['message'] = 'Копирование данных timetable_aspi → intermediate_timetable...'
        cursor.execute("""
            INSERT INTO intermediate_timetable (
                cleaned_id, teacher_id, day_of_week, pair_number, subject_name, discipline_original,
                lecture_type, audience, group_name, week_type, subgroup, institute, course, direction,
                department, is_external, is_remote, num_subgroups, fio, week_error, audience_error
            )
            SELECT
                NULL,
                NULL,
                day_of_week,
                CASE WHEN pair_number ~ '^\\s*\\d+\\s*$' THEN pair_number::integer ELSE NULL END,
                subject_name,
                discipline_original,
                NULL,
                audience,
                group_name,
                week_type,
                NULL,
                institute,
                course,
                scientific_specialty,
                NULL,
                FALSE,
                FALSE,
                NULL,
                fio,
                NULL,
                NULL
            FROM timetable_aspi
        """)
        conn.commit()
        n = cursor.rowcount
        cursor.close()
        conn.close()
        script_status['merge_aspi_to_intermediate']['progress'] = 100
        script_status['merge_aspi_to_intermediate']['message'] = f'Готово. Добавлено записей аспирантов в intermediate_timetable: {n}'
    except Exception as e:
        script_status['merge_aspi_to_intermediate']['error'] = str(e)
        script_status['merge_aspi_to_intermediate']['message'] = f'Ошибка: {str(e)}'
        script_status['merge_aspi_to_intermediate']['progress'] = 0
    finally:
        script_status['merge_aspi_to_intermediate']['running'] = False


@app.route('/api/run/merge_aspi_to_intermediate', methods=['POST'])
def run_merge_aspi_to_intermediate_route():
    """Добавляет расписание аспирантов из timetable_aspi в intermediate_timetable."""
    if script_status['merge_aspi_to_intermediate']['running']:
        return jsonify({'error': 'Script is already running'}), 400
    thread = threading.Thread(target=run_merge_aspi_to_intermediate)
    thread.daemon = True
    thread.start()
    return jsonify({'message': 'Script started'})


@app.route('/api/group-source', methods=['GET'])
def api_group_source():
    """Поиск по номеру группы: возвращает список файлов и листов, где встречается группа."""
    group = request.args.get('group', '').strip()
    if not group:
        return jsonify({'error': 'Укажите номер группы (параметр group)'}), 400
    results = find_group_in_timetable_files(group)
    return jsonify({'results': results})


@app.route('/api/files/timetable/<path:file_path>', methods=['GET'])
def api_serve_timetable_file(file_path):
    """Отдаёт файл из input/timetable по относительному пути (для открытия/скачивания)."""
    if not file_path or '..' in file_path or file_path.startswith('/'):
        return jsonify({'error': 'Invalid path'}), 400
    full_path = os.path.normpath(os.path.join(INPUT_TIMETABLE_DIR, file_path))
    if not os.path.abspath(full_path).startswith(os.path.abspath(INPUT_TIMETABLE_DIR)):
        return jsonify({'error': 'Invalid path'}), 400
    if not os.path.isfile(full_path):
        return jsonify({'error': 'File not found'}), 404
    return send_file(
        full_path,
        as_attachment=False,
        download_name=os.path.basename(full_path),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


def run_fetch_teachers():
    """Запускает get_teacher_data.py — сбор преподавателей с сайта СурГУ в info/teacher_all.json."""
    script_status['fetch_teachers']['running'] = True
    script_status['fetch_teachers']['progress'] = 0
    script_status['fetch_teachers']['message'] = 'Сбор преподавателей с сайта...'
    script_status['fetch_teachers']['error'] = None
    try:
        project_root = get_project_root()
        script_path = os.path.join(project_root, 'get_teacher_data.py')
        if not os.path.exists(script_path):
            raise FileNotFoundError(f'Скрипт не найден: {script_path}')
        env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
        process = subprocess.Popen(
            ['python', script_path],
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env,
            bufsize=1
        )
        output_lines = []
        stdout_stream = process.stdout
        while True:
            out = stdout_stream.readline() if stdout_stream is not None else ''
            if out == '' and process.poll() is not None:
                break
            if out:
                line = out.strip()
                if line.isdigit():
                    i = int(line)
                    script_status['fetch_teachers']['progress'] = min(90, 10 + (i * 80 // 1000))
                    script_status['fetch_teachers']['message'] = f'Обработано страниц: {i}'
            output_lines.append(out)
        return_code = process.wait()
        stderr_stream = process.stderr
        stderr_output = stderr_stream.read() if stderr_stream is not None else ''
        if return_code == 0:
            script_status['fetch_teachers']['progress'] = 100
            script_status['fetch_teachers']['message'] = 'Готово. Данные сохранены в info/teacher_all.json'
        else:
            script_status['fetch_teachers']['error'] = stderr_output or f'Код возврата: {return_code}'
            script_status['fetch_teachers']['message'] = 'Ошибка при сборе с сайта'
            script_status['fetch_teachers']['progress'] = 0
    except Exception as e:
        script_status['fetch_teachers']['error'] = str(e)
        script_status['fetch_teachers']['message'] = str(e)
        script_status['fetch_teachers']['progress'] = 0
    finally:
        script_status['fetch_teachers']['running'] = False


@app.route('/api/run/fetch_teachers', methods=['POST'])
def run_fetch_teachers_route():
    """Запускает get_teacher_data.py (сбор преподавателей с сайта)."""
    if script_status['fetch_teachers']['running']:
        return jsonify({'error': 'Script is already running'}), 400
    thread = threading.Thread(target=run_fetch_teachers)
    thread.daemon = True
    thread.start()
    return jsonify({'message': 'Script started'})


@app.route('/api/db/stats', methods=['GET'])
def get_db_stats():
    """Возвращает статистику из базы данных (timetable_cleaned, timetable_teacher, intermediate_timetable, timetable_aspi)"""
    try:
        table = get_table_param()
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(f"SELECT COUNT(*) as total FROM {table}")
        total = cursor.fetchone()['total']
        
        if table == 'timetable_aspi':
            cursor.execute("""
                SELECT day_of_week, COUNT(*) as count
                FROM timetable_aspi
                GROUP BY day_of_week
                ORDER BY day_of_week
            """)
            by_day = cursor.fetchall()
            by_type = []
            cursor.execute("SELECT MAX(created_at) as last_update FROM timetable_aspi")
            row = cursor.fetchone()
            last_update = row['last_update'] if row else None
        elif table == 'intermediate_timetable':
            cursor.execute("""
                SELECT day_of_week, COUNT(*) as count
                FROM intermediate_timetable
                GROUP BY day_of_week
                ORDER BY day_of_week
            """)
            by_day = cursor.fetchall()
            cursor.execute("""
                SELECT lecture_type, COUNT(*) as count
                FROM intermediate_timetable
                GROUP BY lecture_type
                ORDER BY lecture_type
            """)
            by_type = cursor.fetchall()
            last_update = None
        else:
            cursor.execute(f"""
                SELECT day_of_week, COUNT(*) as count 
                FROM {table} 
                GROUP BY day_of_week 
                ORDER BY day_of_week
            """)
            by_day = cursor.fetchall()
            
            if table == 'timetable_cleaned':
                cursor.execute("""
                    SELECT lecture_type, COUNT(*) as count 
                    FROM timetable_cleaned 
                    GROUP BY lecture_type 
                    ORDER BY lecture_type
                """)
                by_type = cursor.fetchall()
            else:
                by_type = []
            
            cursor.execute(f"SELECT MAX(created_at) as last_update FROM {table}")
            last_update = cursor.fetchone()['last_update']
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'total': total,
            'by_day': [dict(row) for row in by_day],
            'by_type': [dict(row) for row in by_type],
            'last_update': last_update.isoformat() if last_update else None
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/db/records', methods=['GET'])
def get_db_records():
    """Возвращает записи из базы данных с пагинацией и фильтрами (table=timetable_cleaned или timetable_teacher)"""
    try:
        table = get_table_param()
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        offset = (page - 1) * limit
        
        filters = {
            'day_of_week': request.args.get('day_of_week', '').strip(),
            'pair_number': request.args.get('pair_number', '').strip(),
            'subject_name': request.args.get('subject_name', '').strip(),
            'lecture_type': request.args.get('lecture_type', '').strip(),
            'audience': request.args.get('audience', '').strip(),
            'fio': request.args.get('fio', '').strip(),
            'teacher': request.args.get('teacher', '').strip(),
            'group_name': request.args.get('group_name', '').strip(),
            'subgroup': request.args.get('subgroup', '').strip(),
            'week_type': request.args.get('week_type', '').strip(),
            'institute': request.args.get('institute', '').strip(),
            'course': request.args.get('course', '').strip(),
            'direction': request.args.get('direction', '').strip(),
            'profile': request.args.get('profile', '').strip(),
            'has_error': request.args.get('has_error', '').strip(),
            'week_error': request.args.get('week_error', '').strip(),
            'audience_error': request.args.get('audience_error', '').strip(),
        }
        
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Строим WHERE условия для фильтров
        where_conditions = []
        query_params = []
        
        # Фильтр по дню недели
        if filters['day_of_week']:
            where_conditions.append("day_of_week ILIKE %s")
            query_params.append(f"%{filters['day_of_week']}%")
        
        # Фильтр по номеру пары
        if filters['pair_number']:
            try:
                pair_num = int(filters['pair_number'])
                where_conditions.append("pair_number = %s")
                query_params.append(pair_num)
            except ValueError:
                # Если не число, ищем как строку
                where_conditions.append("CAST(pair_number AS TEXT) ILIKE %s")
                query_params.append(f"%{filters['pair_number']}%")
        
        # Фильтр по названию предмета
        if filters['subject_name']:
            where_conditions.append("subject_name ILIKE %s")
            query_params.append(f"%{filters['subject_name']}%")
        
        # Фильтр по типу занятия (timetable_cleaned и intermediate_timetable)
        if filters['lecture_type'] and table in ('timetable_cleaned', 'intermediate_timetable'):
            where_conditions.append("lecture_type ILIKE %s")
            query_params.append(f"%{filters['lecture_type']}%")
        
        # Фильтр по аудитории
        if filters['audience']:
            where_conditions.append("audience ILIKE %s")
            query_params.append(f"%{filters['audience']}%")
        
        # Фильтр по ФИО преподавателя (intermediate, aspi — только fio)
        if filters['fio']:
            if table in ('timetable_teacher', 'intermediate_timetable', 'timetable_aspi'):
                where_conditions.append("fio ILIKE %s")
                query_params.append(f"%{filters['fio']}%")
            else:
                where_conditions.append("(fio ILIKE %s OR teacher ILIKE %s)")
                query_params.append(f"%{filters['fio']}%")
                query_params.append(f"%{filters['fio']}%")
        
        # Фильтр по преподавателю
        if filters['teacher']:
            if table in ('timetable_teacher', 'intermediate_timetable', 'timetable_aspi'):
                where_conditions.append("fio ILIKE %s")
                query_params.append(f"%{filters['teacher']}%")
            else:
                where_conditions.append("(teacher ILIKE %s OR fio ILIKE %s)")
                query_params.append(f"%{filters['teacher']}%")
                query_params.append(f"%{filters['teacher']}%")
        
        # Фильтр по группе
        if filters['group_name']:
            where_conditions.append("group_name ILIKE %s")
            query_params.append(f"%{filters['group_name']}%")
        
        # Фильтр по подгруппе (в timetable_aspi нет столбца subgroup)
        if filters['subgroup'] and table != 'timetable_aspi':
            try:
                sub_num = int(filters['subgroup'])
                where_conditions.append("subgroup = %s")
                query_params.append(sub_num)
            except ValueError:
                where_conditions.append("CAST(subgroup AS TEXT) ILIKE %s")
                query_params.append(f"%{filters['subgroup']}%")
        
        # Фильтр по типу недели
        if filters['week_type']:
            where_conditions.append("week_type ILIKE %s")
            query_params.append(f"%{filters['week_type']}%")
        
        # Фильтры по ошибкам (только intermediate_timetable)
        if table == 'intermediate_timetable':
            if filters['has_error'] and filters['has_error'].lower() in ('1', 'true', 'yes', 'да'):
                where_conditions.append("(week_error = TRUE OR audience_error = TRUE)")
            if filters['week_error'] and filters['week_error'].lower() in ('1', 'true', 'yes', 'да'):
                where_conditions.append("week_error = TRUE")
            if filters['audience_error'] and filters['audience_error'].lower() in ('1', 'true', 'yes', 'да'):
                where_conditions.append("audience_error = TRUE")
        
        # Фильтр по институту (timetable_cleaned, intermediate_timetable, timetable_aspi)
        if filters['institute'] and table in ('timetable_cleaned', 'intermediate_timetable', 'timetable_aspi'):
            where_conditions.append("institute ILIKE %s")
            query_params.append(f"%{filters['institute']}%")
        
        # Фильтр по курсу
        if filters['course'] and table in ('timetable_cleaned', 'intermediate_timetable', 'timetable_aspi'):
            where_conditions.append("course ILIKE %s")
            query_params.append(f"%{filters['course']}%")
        
        # Фильтр по направлению
        if filters['direction'] and table in ('timetable_cleaned', 'intermediate_timetable'):
            where_conditions.append("direction ILIKE %s")
            query_params.append(f"%{filters['direction']}%")
        
        # Фильтр по профилю (только timetable_cleaned)
        if table == 'timetable_cleaned' and filters['profile']:
            where_conditions.append("profile ILIKE %s")
            query_params.append(f"%{filters['profile']}%")
        
        # Фильтр по научной специальности (timetable_aspi)
        if table == 'timetable_aspi' and request.args.get('scientific_specialty', '').strip():
            scientific_specialty = request.args.get('scientific_specialty', '').strip()
            where_conditions.append("scientific_specialty ILIKE %s")
            query_params.append(f"%{scientific_specialty}%")
        
        # Формируем SQL запрос
        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)
        
        # Получаем параметры сортировки (можно несколько столбцов через запятую)
        sort_by_raw = request.args.get('sort_by', 'id').strip()
        sort_order_raw = request.args.get('sort_order', 'desc').strip().upper()
        sort_by_list = [s.strip() for s in sort_by_raw.split(',') if s.strip()]
        sort_order_list = [s.strip().upper() for s in sort_order_raw.split(',') if s.strip()]
        
        # Валидация параметров сортировки
        if table == 'timetable_aspi':
            allowed_sort_fields = ['id', 'day_of_week', 'pair_number', 'subject_name', 'discipline_original',
                                  'audience', 'group_name', 'week_type', 'fio', 'course', 'scientific_specialty', 'institute']
        elif table == 'intermediate_timetable':
            allowed_sort_fields = ['id', 'day_of_week', 'pair_number', 'subject_name', 'lecture_type', 'audience',
                                  'group_name', 'week_type', 'subgroup', 'institute', 'course', 'direction',
                                  'department', 'fio', 'week_error', 'audience_error']
        else:
            allowed_sort_fields = ['id', 'day_of_week', 'pair_number', 'subject_name', 'lecture_type',
                                  'audience', 'fio', 'teacher', 'group_name', 'subgroup', 'course',
                                  'institute', 'direction', 'profile', 'week_type']
        if table == 'timetable_teacher':
            sort_by_allowed = ['id', 'day_of_week', 'pair_number', 'subject_name', 'audience', 'fio', 'group_name', 'subgroup', 'course', 'week_type']
            allowed_sort_fields = sort_by_allowed
        
        # Собираем пары (поле, порядок), по умолчанию id DESC
        order_parts = []
        for i, sort_by in enumerate(sort_by_list):
            if sort_by not in allowed_sort_fields:
                continue
            sort_order = sort_order_list[i] if i < len(sort_order_list) else (sort_order_list[0] if sort_order_list else 'DESC')
            if sort_order not in ['ASC', 'DESC']:
                sort_order = 'DESC'
            day_order_sql = """CASE LOWER(TRIM(COALESCE(day_of_week, '')))
                WHEN 'понедельник' THEN 1 WHEN 'вторник' THEN 2 WHEN 'среда' THEN 3
                WHEN 'четверг' THEN 4 WHEN 'пятница' THEN 5 WHEN 'суббота' THEN 6
                WHEN 'воскресенье' THEN 7 ELSE 8 END"""
            part = f"{day_order_sql} {sort_order}" if sort_by == 'day_of_week' else f"{sort_by} {sort_order}"
            order_parts.append(part)
        if not order_parts:
            order_parts = ['id DESC']
        order_clause = ', '.join(order_parts)
        
        if table == 'timetable_aspi':
            query = f"""
                SELECT id, day_of_week, pair_number, subject_name, discipline_original, audience,
                    group_name, week_type, fio, course, scientific_specialty, institute, created_at
                FROM timetable_aspi
                {where_clause}
                ORDER BY {order_clause}
                LIMIT %s OFFSET %s
            """
        elif table == 'intermediate_timetable':
            query = f"""
                SELECT *
                FROM intermediate_timetable
                {where_clause}
                ORDER BY {order_clause}
                LIMIT %s OFFSET %s
            """
        elif table == 'timetable_teacher':
            query = f"""
                SELECT id, day_of_week, pair_number, subject_name, audience, fio,
                    fio AS teacher, group_name, week_type, subgroup,
                    NULL::TEXT AS institute, NULL::TEXT AS course, NULL::TEXT AS direction,
                    department, is_external, is_remote, num_subgroups
                FROM timetable_teacher
                {where_clause}
                ORDER BY {order_clause}
                LIMIT %s OFFSET %s
            """
        else:
            query = f"""
                SELECT id, day_of_week, pair_number, subject_name, lecture_type, audience,
                    fio, teacher, group_name, week_type, subgroup,
                    institute, course, direction, department,
                    is_external, is_remote, num_subgroups, duration_pairs
                FROM timetable_cleaned
                {where_clause}
                ORDER BY {order_clause}
                LIMIT %s OFFSET %s
            """
        query_params.extend([limit, offset])
        
        cursor.execute(query, query_params)
        records = cursor.fetchall()
        
        # Преобразуем записи в словари, убеждаясь что все поля присутствуют
        records_list = []
        for row in records:
            record_dict = dict(row)
            
            # Убеждаемся, что все поля присутствуют (даже если они None)
            record_dict['fio'] = record_dict.get('fio')
            record_dict['teacher'] = record_dict.get('teacher')
            record_dict['group_name'] = record_dict.get('group_name')
            record_dict['week_type'] = record_dict.get('week_type')
            
            records_list.append(record_dict)
        
        count_query = f"SELECT COUNT(*) as total FROM {table} {where_clause}"
        count_params = query_params[:-2]  # Убираем LIMIT и OFFSET
        cursor.execute(count_query, count_params)
        total = cursor.fetchone()['total']
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'records': records_list,
            'total': total,
            'page': page,
            'limit': limit,
            'pages': (total + limit - 1) // limit if total > 0 else 0
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/db/clear', methods=['POST'])
def clear_database():
    """Очищает выбранную таблицу (timetable_cleaned, timetable_teacher или intermediate_timetable)"""
    try:
        table = get_table_param()
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute(f"TRUNCATE TABLE {table}")
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'message': f'Table {table} cleared successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- Расписание: чистая сущность без полей ошибок, бэкап и восстановление ---

SCHEDULE_COLUMNS = [
    'day_of_week', 'pair_number', 'subject_name', 'lecture_type', 'audience',
    'group_name', 'week_type', 'subgroup', 'institute', 'course', 'direction',
    'department', 'is_external', 'is_remote', 'num_subgroups', 'fio'
]

def _ensure_schedule_table(conn):
    """Создаёт таблицу schedule, если её ещё нет (только поля расписания, без ошибок и служебных id)."""
    cur = conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schedule (
                id SERIAL PRIMARY KEY,
                day_of_week VARCHAR(50),
                pair_number INTEGER,
                subject_name TEXT,
                lecture_type VARCHAR(50),
                audience VARCHAR(50),
                group_name VARCHAR(50),
                week_type VARCHAR(50),
                subgroup INTEGER,
                institute TEXT,
                course VARCHAR(10),
                direction TEXT,
                department TEXT,
                is_external BOOLEAN,
                is_remote BOOLEAN,
                num_subgroups INTEGER,
                fio TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cur.execute("ALTER TABLE schedule ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        conn.commit()
    finally:
        cur.close()


@app.route('/api/schedule/save', methods=['POST'])
def schedule_save():
    """Копирует данные из intermediate_timetable в таблицу schedule (только поля расписания, без ошибок)."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'intermediate_timetable'"
        )
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': 'Сначала выполните «Слияние расписания» (intermediate_timetable).'}), 400
        _ensure_schedule_table(conn)
        cols = ', '.join(SCHEDULE_COLUMNS)
        placeholders = ', '.join(['%s'] * len(SCHEDULE_COLUMNS))
        cur.execute("TRUNCATE TABLE schedule")
        cur.execute(f"""
            INSERT INTO schedule ({cols})
            SELECT {cols}
            FROM intermediate_timetable
        """)
        n = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'saved': n, 'message': f'В расписание сохранено записей: {n}'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/schedule/backup', methods=['GET'])
def schedule_backup():
    """Возвращает JSON-файл с полным дампом таблицы schedule (бэкап)."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        _ensure_schedule_table(conn)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, day_of_week, pair_number, subject_name, lecture_type, audience,
                   group_name, week_type, subgroup, institute, course, direction,
                   department, is_external, is_remote, num_subgroups, fio
            FROM schedule
            ORDER BY id
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        data = {'schedule': [dict(r) for r in rows], 'version': 1, 'exported_at': datetime.utcnow().isoformat() + 'Z'}
        data = _make_json_serializable(data)
        from flask import Response
        return Response(
            json.dumps(data, ensure_ascii=False, indent=2),
            mimetype='application/json',
            headers={'Content-Disposition': 'attachment; filename=schedule_backup.json'}
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/schedule/restore', methods=['POST'])
def schedule_restore():
    """Восстанавливает таблицу schedule из загруженного JSON-файла бэкапа."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'Файл не выбран'}), 400
        f = request.files['file']
        if not f.filename or not f.filename.lower().endswith('.json'):
            return jsonify({'error': 'Нужен файл .json'}), 400
        content = f.read()
        data = json.loads(content.decode('utf-8') if isinstance(content, bytes) else content)
        if not isinstance(data, dict) or 'schedule' not in data:
            return jsonify({'error': 'Неверный формат бэкапа: ожидается объект с полем schedule'}), 400
        rows = data['schedule']
        if not isinstance(rows, list):
            return jsonify({'error': 'Неверный формат: schedule должен быть массивом'}), 400
        conn = psycopg2.connect(**DB_CONFIG)
        _ensure_schedule_table(conn)
        cur = conn.cursor()
        cur.execute("TRUNCATE TABLE schedule")
        cols_s = ", ".join(SCHEDULE_COLUMNS)
        rows_to_insert = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            vals = tuple(row.get(c) for c in SCHEDULE_COLUMNS)
            rows_to_insert.append(vals)
        if rows_to_insert:
            execute_values(cur, f"INSERT INTO schedule ({cols_s}) VALUES %s", rows_to_insert)
        conn.commit()
        n = len(rows_to_insert)
        cur.close()
        conn.close()
        return jsonify({'restored': n, 'message': f'Восстановлено записей: {n}'})
    except json.JSONDecodeError as e:
        return jsonify({'error': f'Ошибка JSON: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/schedule/push-to-prod', methods=['POST'])
def schedule_push_to_prod():
    """Копирует таблицу schedule из текущей БД в продакшн БД (DB_PROD_*)."""
    prod_config = _prod_db_config()
    if not prod_config:
        return jsonify({'error': 'Продакшн БД не настроена: задайте DB_PROD_HOST в .env'}), 400
    try:
        conn_local = psycopg2.connect(**DB_CONFIG)
        _ensure_schedule_table(conn_local)
        cur_local = conn_local.cursor(cursor_factory=RealDictCursor)
        cur_local.execute(
            f"SELECT {', '.join(SCHEDULE_COLUMNS)} FROM schedule ORDER BY id"
        )
        rows = cur_local.fetchall()
        cur_local.close()
        conn_local.close()
        rows_data = [tuple(r[c] for c in SCHEDULE_COLUMNS) for r in rows]
        conn_prod = psycopg2.connect(**prod_config)
        _ensure_schedule_table(conn_prod)
        cur_prod = conn_prod.cursor()
        cur_prod.execute("TRUNCATE TABLE schedule RESTART IDENTITY")
        if rows_data:
            cols_s = ", ".join(SCHEDULE_COLUMNS)
            execute_values(cur_prod, f"INSERT INTO schedule ({cols_s}) VALUES %s", rows_data)
        conn_prod.commit()
        n = len(rows_data)
        cur_prod.close()
        conn_prod.close()
        return jsonify({'pushed': n, 'message': f'В продакшн отправлено записей: {n}'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Колонки intermediate_timetable для бэкапа (все, кроме id — при restore id генерируется)
INTERMEDIATE_BACKUP_COLUMNS = [
    'cleaned_id', 'teacher_id', 'day_of_week', 'pair_number', 'subject_name', 'discipline_original',
    'lecture_type', 'audience', 'group_name', 'week_type', 'subgroup', 'institute', 'course',
    'direction', 'department', 'is_external', 'is_remote', 'num_subgroups', 'fio',
    'week_error', 'duration_pairs', 'audience_error'
]


@app.route('/api/intermediate/backup', methods=['GET'])
def intermediate_backup():
    """Возвращает JSON-файл с полным дампом таблицы intermediate_timetable (бэкап)."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'intermediate_timetable'"
        )
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': 'Таблица intermediate_timetable не найдена'}), 404
        cur.execute("""
            SELECT id, cleaned_id, teacher_id, day_of_week, pair_number, subject_name, discipline_original,
                   lecture_type, audience, group_name, week_type, subgroup, institute, course, direction,
                   department, is_external, is_remote, num_subgroups, fio, week_error, duration_pairs, audience_error
            FROM intermediate_timetable
            ORDER BY id
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        data = {'intermediate_timetable': [dict(r) for r in rows], 'version': 1, 'exported_at': datetime.utcnow().isoformat() + 'Z'}
        data = _make_json_serializable(data)
        from flask import Response
        return Response(
            json.dumps(data, ensure_ascii=False, indent=2),
            mimetype='application/json',
            headers={'Content-Disposition': 'attachment; filename=intermediate_backup.json'}
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/intermediate/restore', methods=['POST'])
def intermediate_restore():
    """Восстанавливает таблицу intermediate_timetable из загруженного JSON-файла бэкапа."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'Файл не выбран'}), 400
        f = request.files['file']
        if not f.filename or not f.filename.lower().endswith('.json'):
            return jsonify({'error': 'Нужен файл .json'}), 400
        content = f.read()
        data = json.loads(content.decode('utf-8') if isinstance(content, bytes) else content)
        if not isinstance(data, dict) or 'intermediate_timetable' not in data:
            return jsonify({'error': 'Неверный формат бэкапа: ожидается объект с полем intermediate_timetable'}), 400
        rows = data['intermediate_timetable']
        if not isinstance(rows, list):
            return jsonify({'error': 'Неверный формат: intermediate_timetable должен быть массивом'}), 400
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'intermediate_timetable'"
        )
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': 'Таблица intermediate_timetable не найдена. Сначала выполните «Слияние расписания».'}), 400
        cur.execute("ALTER TABLE intermediate_timetable ADD COLUMN IF NOT EXISTS duration_pairs NUMERIC(3,1)")
        cur.execute("TRUNCATE TABLE intermediate_timetable")
        rows_to_insert = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            vals = tuple(row.get(c) for c in INTERMEDIATE_BACKUP_COLUMNS)
            rows_to_insert.append(vals)
        if rows_to_insert:
            cols_s = ", ".join(INTERMEDIATE_BACKUP_COLUMNS)
            execute_values(cur, f"INSERT INTO intermediate_timetable ({cols_s}) VALUES %s", rows_to_insert)
        conn.commit()
        n = len(rows_to_insert)
        cur.close()
        conn.close()
        return jsonify({'restored': n, 'message': f'Восстановлено записей в intermediate_timetable: {n}'})
    except json.JSONDecodeError as e:
        return jsonify({'error': f'Ошибка JSON: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- Унифицированный бэкап и восстановление для всех таблиц ---

ASPI_BACKUP_COLUMNS = [
    'day_of_week', 'pair_number', 'subject_name', 'discipline_original', 'audience',
    'group_name', 'week_type', 'fio', 'course', 'scientific_specialty', 'institute'
]

BACKUP_COLUMNS = {
    'timetable_cleaned': [
        'day_of_week', 'pair_number', 'subject_name', 'lecture_type', 'audience',
        'fio', 'teacher', 'group_name', 'week_type', 'subgroup', 'institute', 'course',
        'direction', 'department', 'is_external', 'is_remote', 'num_subgroups', 'duration_pairs'
    ],
    'timetable_teacher': [
        'fio', 'pair_number', 'day_of_week', 'group_name', 'audience', 'department',
        'week_type', 'subgroup', 'num_subgroups', 'is_external', 'is_remote', 'subject_name'
    ],
    'intermediate_timetable': INTERMEDIATE_BACKUP_COLUMNS,
    'timetable_aspi': ASPI_BACKUP_COLUMNS,
    'schedule': SCHEDULE_COLUMNS,
}


@app.route('/api/db/backup-tables', methods=['GET'])
def backup_tables_list():
    """Список таблиц для бэкапа/восстановления."""
    return jsonify({
        'tables': [
            {'id': t, 'label': BACKUP_TABLE_LABELS.get(t, t)}
            for t in BACKUP_TABLES
        ]
    })


@app.route('/api/db/backup', methods=['GET'])
def unified_backup():
    """Бэкап выбранной таблицы (timetable_cleaned, timetable_teacher, intermediate_timetable, schedule)."""
    table = request.args.get('table', '').strip()
    if table not in BACKUP_TABLES:
        return jsonify({'error': f'Неизвестная таблица: {table}. Допустимы: {", ".join(BACKUP_TABLES)}'}), 400
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s",
            (table,)
        )
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': f'Таблица {table} не найдена'}), 404
        cols = BACKUP_COLUMNS[table]
        cols_str = ', '.join(cols)
        cur.execute(f"SELECT {cols_str} FROM {table} ORDER BY id")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        data = {table: [dict(r) for r in rows], 'version': 1, 'exported_at': datetime.utcnow().isoformat() + 'Z'}
        data = _make_json_serializable(data)
        from flask import Response
        return Response(
            json.dumps(data, ensure_ascii=False, indent=2),
            mimetype='application/json',
            headers={'Content-Disposition': f'attachment; filename={table}_backup.json'}
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/db/restore', methods=['POST'])
def unified_restore():
    """Восстановление таблицы из JSON-файла бэкапа."""
    table = request.form.get('table', '').strip()
    if table not in BACKUP_TABLES:
        return jsonify({'error': f'Неизвестная таблица: {table}'}), 400
    if 'file' not in request.files:
        return jsonify({'error': 'Файл не выбран'}), 400
    f = request.files['file']
    if not f.filename or not f.filename.lower().endswith('.json'):
        return jsonify({'error': 'Нужен файл .json'}), 400
    try:
        content = f.read()
        data = json.loads(content.decode('utf-8') if isinstance(content, bytes) else content)
        if not isinstance(data, dict) or table not in data:
            return jsonify({'error': f'Неверный формат бэкапа: ожидается объект с полем {table}'}), 400
        rows = data[table]
        if not isinstance(rows, list):
            return jsonify({'error': f'{table} должен быть массивом'}), 400
        cols = BACKUP_COLUMNS[table]
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s",
            (table,)
        )
        if not cur.fetchone():
            if table == 'schedule':
                _ensure_schedule_table(conn)
            elif table == 'timetable_aspi':
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS timetable_aspi (
                        id SERIAL PRIMARY KEY,
                        day_of_week VARCHAR(50),
                        pair_number TEXT,
                        subject_name TEXT,
                        discipline_original TEXT,
                        audience VARCHAR(255),
                        group_name VARCHAR(100),
                        week_type VARCHAR(50),
                        fio TEXT,
                        course VARCHAR(20),
                        scientific_specialty TEXT,
                        institute TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
            else:
                cur.close()
                conn.close()
                return jsonify({'error': f'Таблица {table} не найдена'}), 404
        if table == 'timetable_cleaned':
            cur.execute("ALTER TABLE timetable_cleaned ADD COLUMN IF NOT EXISTS duration_pairs NUMERIC(3,1)")
            conn.commit()
        cur.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY")
        rows_to_insert = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            vals = tuple(row.get(c) for c in cols)
            rows_to_insert.append(vals)
        if rows_to_insert:
            cols_s = ", ".join(cols)
            execute_values(cur, f"INSERT INTO {table} ({cols_s}) VALUES %s", rows_to_insert)
        conn.commit()
        n = len(rows_to_insert)
        cur.close()
        conn.close()
        return jsonify({'restored': n, 'message': f'Восстановлено записей в {table}: {n}'})
    except json.JSONDecodeError as e:
        return jsonify({'error': f'Ошибка JSON: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/schedule/stats', methods=['GET'])
def schedule_stats():
    """Возвращает количество записей в schedule."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        _ensure_schedule_table(conn)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM schedule")
        total = cur.fetchone()[0]
        cur.close()
        conn.close()
        return jsonify({'total': total})
    except Exception as e:
        return jsonify({'error': str(e), 'total': 0}), 500


@app.route('/api/schedule/records', methods=['GET'])
def schedule_records():
    """Возвращает записи из schedule с пагинацией."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        _ensure_schedule_table(conn)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        page = int(request.args.get('page', 1))
        limit = min(max(int(request.args.get('limit', 50)), 1), 500)
        offset = (page - 1) * limit
        cur.execute("SELECT COUNT(*) as total FROM schedule")
        total = cur.fetchone()['total']
        cur.execute("""
            SELECT id, day_of_week, pair_number, subject_name, lecture_type, audience,
                   group_name, week_type, subgroup, institute, course, direction,
                   department, is_external, is_remote, num_subgroups, fio
            FROM schedule
            ORDER BY id
            LIMIT %s OFFSET %s
        """, (limit, offset))
        records = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return jsonify({
            'records': records,
            'total': total,
            'page': page,
            'limit': limit,
            'pages': (total + limit - 1) // limit if total > 0 else 0
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _allowed_update_fields(table):
    """Разрешённые поля для обновления в зависимости от таблицы. intermediate_timetable — редактируемые поля с синхронизацией в cleaned/teacher и пересчётом ошибок."""
    if table == 'intermediate_timetable':
        return [
            'week_type', 'audience', 'subject_name', 'discipline_original', 'lecture_type',
            'day_of_week', 'pair_number', 'group_name', 'subgroup',
            'institute', 'course', 'direction', 'department', 'duration_pairs'
        ]
    if table == 'timetable_teacher':
        return [
            'day_of_week', 'pair_number', 'subject_name', 'audience', 'fio',
            'group_name', 'week_type', 'subgroup', 'department',
            'is_external', 'is_remote', 'num_subgroups'
        ]
    return [
        'day_of_week', 'pair_number', 'subject_name', 'lecture_type',
        'audience', 'fio', 'teacher', 'group_name', 'week_type',
        'subgroup', 'institute', 'course', 'direction', 'department',
        'is_external', 'is_remote', 'num_subgroups'
    ]

def _normalize_update_value(field, value):
    """Приводит значение поля к типу для UPDATE."""
    if value == '' or value is None:
        return None
    if field in ['pair_number', 'subgroup', 'num_subgroups']:
        try:
            return int(value) if value is not None else None
        except (ValueError, TypeError):
            return None
    if field in ['is_external', 'is_remote']:
        return bool(value) if value is not None else None
    if field == 'duration_pairs':
        if value is None or value == '':
            return None
        try:
            return float(str(value).replace(',', '.'))
        except (ValueError, TypeError):
            return None
    return str(value) if value is not None else None


@app.route('/api/db/records/<int:record_id>', methods=['PUT'])
def update_record(record_id):
    """Обновляет запись в выбранной таблице (table=...). Для intermediate_timetable синхронизирует cleaned/teacher и пересчитывает week_error, audience_error."""
    try:
        table = get_table_param()
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        allowed_fields = _allowed_update_fields(table)
        # Для timetable_teacher teacher не существует — маппим на fio
        if table == 'timetable_teacher' and 'teacher' in data:
            data = dict(data)
            data['fio'] = data.get('fio') or data.get('teacher')

        if table == 'intermediate_timetable':
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            if not _intermediate_has_cleaned_id(cursor):
                cursor.close()
                conn.close()
                return jsonify({
                    'error': 'Таблица intermediate_timetable создана старой версией. Выполните «Слияние расписания» (merge) заново.'
                }), 400
            cursor.execute(
                "SELECT cleaned_id, teacher_id FROM intermediate_timetable WHERE id = %s",
                (record_id,)
            )
            row = cursor.fetchone()
            if not row or (row.get('cleaned_id') is None and row.get('teacher_id') is None):
                cursor.close()
                conn.close()
                return jsonify({'error': 'Record not found or no source ids'}), 404
            cleaned_id = row['cleaned_id']
            teacher_id = row['teacher_id']

            # Поля, которые есть в timetable_cleaned
            cleaned_fields = [
                'day_of_week', 'pair_number', 'subject_name', 'lecture_type',
                'audience', 'group_name', 'week_type', 'subgroup',
                'institute', 'course', 'direction', 'department', 'duration_pairs'
            ]
            # Поля, которые есть в timetable_teacher
            teacher_fields = [
                'day_of_week', 'pair_number', 'subject_name', 'audience',
                'group_name', 'week_type', 'subgroup', 'department'
            ]

            update_cleaned = []
            vals_cleaned = []
            for f in cleaned_fields:
                if f not in data:
                    continue
                v = _normalize_update_value(f, data[f])
                update_cleaned.append(f"{f} = %s")
                vals_cleaned.append(v)
            if cleaned_id and update_cleaned:
                vals_cleaned.append(cleaned_id)
                cursor.execute(
                    f"UPDATE timetable_cleaned SET {', '.join(update_cleaned)} WHERE id = %s",
                    vals_cleaned
                )

            update_teacher = []
            vals_teacher = []
            for f in teacher_fields:
                if f not in data:
                    continue
                v = _normalize_update_value(f, data[f])
                update_teacher.append(f"{f} = %s")
                vals_teacher.append(v)
            if teacher_id and update_teacher:
                vals_teacher.append(teacher_id)
                cursor.execute(
                    f"UPDATE timetable_teacher SET {', '.join(update_teacher)} WHERE id = %s",
                    vals_teacher
                )

            # Обновить intermediate_timetable: те же поля + пересчитать week_error, audience_error
            update_int = []
            vals_int = []
            for f in allowed_fields:
                if f not in data:
                    continue
                v = _normalize_update_value(f, data[f])
                update_int.append(f"{f} = %s")
                vals_int.append(v)
            if update_int:
                vals_int.append(record_id)
                cursor.execute(
                    f"UPDATE intermediate_timetable SET {', '.join(update_int)} WHERE id = %s",
                    vals_int
                )
            # Пересчёт week_error и audience_error (сравнение с TRIM, чтобы пробелы не давали ложную ошибку)
            cursor.execute("""
                UPDATE intermediate_timetable it SET
                    week_error = (
                        SELECT (NULLIF(TRIM(c.week_type), '') IS DISTINCT FROM NULLIF(TRIM(t.week_type), ''))
                        FROM timetable_cleaned c, timetable_teacher t
                        WHERE c.id = it.cleaned_id AND t.id = it.teacher_id
                    ),
                    audience_error = (
                        SELECT (NULLIF(TRIM(c.audience), '') IS DISTINCT FROM NULLIF(TRIM(t.audience), ''))
                        FROM timetable_cleaned c, timetable_teacher t
                        WHERE c.id = it.cleaned_id AND t.id = it.teacher_id
                    )
                WHERE it.id = %s AND it.cleaned_id IS NOT NULL AND it.teacher_id IS NOT NULL
            """, (record_id,))
            cursor.execute(
                "SELECT * FROM intermediate_timetable WHERE id = %s",
                (record_id,)
            )
            updated_record = cursor.fetchone()
            conn.commit()
            cursor.close()
            conn.close()
            if updated_record:
                return jsonify({'message': 'Record updated successfully', 'record': dict(updated_record)})
            return jsonify({'error': 'Record not found'}), 404

        # Обычное обновление для timetable_cleaned / timetable_teacher
        update_fields = []
        update_values = []
        for field in allowed_fields:
            if field not in data:
                continue
            value = _normalize_update_value(field, data[field])
            update_values.append(value)
            update_fields.append(f"{field} = %s")
        if not update_fields:
            return jsonify({'error': 'No fields to update'}), 400
        update_values.append(record_id)
        update_query = f"UPDATE {table} SET {', '.join(update_fields)} WHERE id = %s"
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(update_query, update_values)
        rows_affected = cursor.rowcount
        conn.commit()
        if rows_affected == 0:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Record not found'}), 404
        if table == 'timetable_teacher':
            cursor.execute(
                """SELECT id, day_of_week, pair_number, subject_name, audience, fio,
                    fio AS teacher, group_name, week_type, subgroup,
                    NULL::TEXT AS institute, NULL::TEXT AS course, NULL::TEXT AS direction,
                    department, is_external, is_remote, num_subgroups
                FROM timetable_teacher WHERE id = %s""",
                (record_id,)
            )
        else:
            cursor.execute("SELECT * FROM timetable_cleaned WHERE id = %s", (record_id,))
        updated_record = cursor.fetchone()
        cursor.close()
        conn.close()
        if updated_record:
            return jsonify({'message': 'Record updated successfully', 'record': dict(updated_record)})
        return jsonify({'error': 'Record not found'}), 404
    except Exception as e:
        import traceback
        print(f"Error updating record {record_id}: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


def _intermediate_has_cleaned_id(cursor):
    """Проверяет, что intermediate_timetable имеет колонки cleaned_id/teacher_id (новая схема)."""
    cursor.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'intermediate_timetable' AND column_name = 'cleaned_id'
    """)
    return cursor.fetchone() is not None


@app.route('/api/db/records/<int:record_id>/fix-field', methods=['PUT', 'POST'])
def fix_intermediate_field(record_id):
    """Отметить поле как правильное: скопировать значение из intermediate в cleaned и teacher, пересчитать ошибки."""
    try:
        table = get_table_param()
        if table != 'intermediate_timetable':
            return jsonify({'error': 'Доступно только для таблицы intermediate_timetable'}), 400
        data = request.get_json() or {}
        field = (data.get('field') or request.args.get('field', '')).strip()
        if field not in ('week_type', 'audience'):
            return jsonify({'error': 'Укажите field: week_type или audience'}), 400
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        if not _intermediate_has_cleaned_id(cursor):
            cursor.close()
            conn.close()
            return jsonify({
                'error': 'Таблица intermediate_timetable создана старой версией. Выполните «Слияние расписания» (merge) заново.'
            }), 400
        cursor.execute(
            "SELECT cleaned_id, teacher_id, week_type, audience FROM intermediate_timetable WHERE id = %s",
            (record_id,)
        )
        row = cursor.fetchone()
        if not row or (row.get('cleaned_id') is None and row.get('teacher_id') is None):
            cursor.close()
            conn.close()
            return jsonify({'error': 'Record not found or no source ids'}), 404
        cleaned_id = row['cleaned_id']
        teacher_id = row['teacher_id']
        value = row.get(field)
        if cleaned_id:
            cursor.execute(
                f"UPDATE timetable_cleaned SET {field} = %s WHERE id = %s",
                (value, cleaned_id)
            )
        if teacher_id:
            cursor.execute(
                f"UPDATE timetable_teacher SET {field} = %s WHERE id = %s",
                (value, teacher_id)
            )
        cursor.execute("""
            UPDATE intermediate_timetable it SET
                week_error = (
                    SELECT (NULLIF(TRIM(c.week_type), '') IS DISTINCT FROM NULLIF(TRIM(t.week_type), ''))
                    FROM timetable_cleaned c, timetable_teacher t
                    WHERE c.id = it.cleaned_id AND t.id = it.teacher_id
                ),
                audience_error = (
                    SELECT (NULLIF(TRIM(c.audience), '') IS DISTINCT FROM NULLIF(TRIM(t.audience), ''))
                    FROM timetable_cleaned c, timetable_teacher t
                    WHERE c.id = it.cleaned_id AND t.id = it.teacher_id
                )
            WHERE it.id = %s AND it.cleaned_id IS NOT NULL AND it.teacher_id IS NOT NULL
        """, (record_id,))
        cursor.execute("SELECT * FROM intermediate_timetable WHERE id = %s", (record_id,))
        updated_record = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        if updated_record:
            return jsonify({'message': 'Поле отмечено как правильное', 'record': dict(updated_record)})
        return jsonify({'error': 'Record not found'}), 404
    except Exception as e:
        import traceback
        print(f"Error fix-field {record_id}: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


def _allowed_insert_fields(table):
    """Разрешённые поля для вставки в зависимости от таблицы. intermediate_timetable — только чтение."""
    if table == 'intermediate_timetable':
        return []
    if table == 'timetable_teacher':
        return [
            'day_of_week', 'pair_number', 'subject_name', 'audience', 'fio',
            'group_name', 'week_type', 'subgroup', 'department',
            'is_external', 'is_remote', 'num_subgroups'
        ]
    return [
        'day_of_week', 'pair_number', 'subject_name', 'lecture_type',
        'audience', 'fio', 'teacher', 'group_name', 'week_type',
        'subgroup', 'institute', 'course', 'direction', 'department',
        'is_external', 'is_remote', 'num_subgroups'
    ]

def _create_record_intermediate(reference_id, position, empty=False):
    """Дублирует или создаёт пустую запись в объединённой таблице: вставка в cleaned/teacher + merge."""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    if not _intermediate_has_cleaned_id(cursor):
        cursor.close()
        conn.close()
        return None, 'Таблица intermediate_timetable создана старой версией. Выполните «Слияние расписания» заново.'
    cursor.execute(
        "SELECT cleaned_id, teacher_id, day_of_week, pair_number, subject_name, lecture_type, audience, "
        "group_name, week_type, subgroup, institute, course, direction, department, "
        "is_external, is_remote, num_subgroups, fio, duration_pairs FROM intermediate_timetable WHERE id = %s",
        (reference_id,)
    )
    ref_row = cursor.fetchone()
    if not ref_row:
        cursor.close()
        conn.close()
        return None, 'Запись не найдена'
    cleaned_id = ref_row.get('cleaned_id')
    teacher_id = ref_row.get('teacher_id')

    cleaned_cols = [
        'day_of_week', 'pair_number', 'subject_name', 'lecture_type', 'audience',
        'fio', 'teacher', 'group_name', 'week_type', 'subgroup',
        'institute', 'course', 'direction', 'department',
        'is_external', 'is_remote', 'num_subgroups', 'duration_pairs'
    ]
    teacher_cols = [
        'fio', 'pair_number', 'day_of_week', 'group_name', 'audience', 'department',
        'week_type', 'subgroup', 'num_subgroups', 'is_external', 'is_remote', 'subject_name'
    ]

    if empty:
        # Пустая запись: только ключевые поля из reference для join при merge
        cleaned_vals = [
            ref_row.get('day_of_week'), ref_row.get('pair_number'), None, None, None,
            None, None, ref_row.get('group_name'), ref_row.get('week_type'), ref_row.get('subgroup'),
            None, None, None, None, None, None, None, None
        ]
        teacher_vals = [
            None, ref_row.get('pair_number'), ref_row.get('day_of_week'), ref_row.get('group_name'),
            None, None, ref_row.get('week_type'), ref_row.get('subgroup'), None, None, None, None
        ]
    else:
        # Дубликат: копируем из cleaned и teacher
        if cleaned_id:
            cursor.execute("SELECT * FROM timetable_cleaned WHERE id = %s", (cleaned_id,))
            c_row = cursor.fetchone()
            if c_row:
                cleaned_vals = [c_row.get(f) for f in cleaned_cols]
            else:
                cleaned_vals = [ref_row.get(f) if f != 'teacher' else ref_row.get('fio') for f in cleaned_cols]
        else:
            cleaned_vals = [
                ref_row.get('day_of_week'), ref_row.get('pair_number'), ref_row.get('subject_name'),
                ref_row.get('lecture_type'), ref_row.get('audience'), ref_row.get('fio'), ref_row.get('fio'),
                ref_row.get('group_name'), ref_row.get('week_type'), ref_row.get('subgroup'),
                ref_row.get('institute'), ref_row.get('course'), ref_row.get('direction'), ref_row.get('department'),
                ref_row.get('is_external'), ref_row.get('is_remote'), ref_row.get('num_subgroups'),
                ref_row.get('duration_pairs')
            ]
        if teacher_id:
            cursor.execute("SELECT * FROM timetable_teacher WHERE id = %s", (teacher_id,))
            t_row = cursor.fetchone()
            if t_row:
                teacher_vals = [t_row.get(f) for f in teacher_cols]
            else:
                teacher_vals = [
                    ref_row.get('fio'), ref_row.get('pair_number'), ref_row.get('day_of_week'),
                    ref_row.get('group_name'), ref_row.get('audience'), ref_row.get('department'),
                    ref_row.get('week_type'), ref_row.get('subgroup'), ref_row.get('num_subgroups'),
                    ref_row.get('is_external'), ref_row.get('is_remote'), ref_row.get('subject_name')
                ]
        else:
            teacher_vals = [
                ref_row.get('fio'), ref_row.get('pair_number'), ref_row.get('day_of_week'),
                ref_row.get('group_name'), ref_row.get('audience'), ref_row.get('department'),
                ref_row.get('week_type'), ref_row.get('subgroup'), ref_row.get('num_subgroups'),
                ref_row.get('is_external'), ref_row.get('is_remote'), ref_row.get('subject_name')
            ]

    def to_val(v):
        if v is None or v == '':
            return None
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return int(v) if v == v else None
        return str(v)

    cleaned_vals = [to_val(v) for v in cleaned_vals]
    teacher_vals = [to_val(v) for v in teacher_vals]

    cursor.execute(
        "INSERT INTO timetable_cleaned (" + ", ".join(cleaned_cols) + ") VALUES (" + ", ".join(["%s"] * len(cleaned_cols)) + ") RETURNING id",
        cleaned_vals
    )
    new_cleaned_id = cursor.fetchone()['id']
    cursor.execute(
        "INSERT INTO timetable_teacher (" + ", ".join(teacher_cols) + ") VALUES (" + ", ".join(["%s"] * len(teacher_cols)) + ") RETURNING id",
        teacher_vals
    )
    new_teacher_id = cursor.fetchone()['id']
    conn.commit()
    cursor.close()
    conn.close()
    run_merge_timetable()
    return True, None


@app.route('/api/db/records', methods=['POST'])
def create_record():
    """Создаёт новую запись в выбранной таблице (table=...). Для intermediate_timetable — дубликат/пустая через cleaned+teacher+merge."""
    try:
        table = get_table_param()
        data = request.get_json() or {}
        reference_id = data.get('_reference_id')
        position = data.get('_position')
        record_data = {k: v for k, v in data.items() if not k.startswith('_')}

        if table == 'intermediate_timetable':
            if reference_id is None:
                return jsonify({'error': 'Для объединённой таблицы укажите _reference_id (id строки)'}), 400
            has_data = any(
                record_data.get(k) not in (None, '') for k in
                ['day_of_week', 'pair_number', 'subject_name', 'group_name', 'week_type', 'fio']
            )
            ok, err = _create_record_intermediate(reference_id, position, empty=not has_data)
            if err:
                return jsonify({'error': err}), 400 if 'старой версией' in err else 404
            return jsonify({'message': 'Record created successfully; merge completed'}), 201

        if not data:
            return jsonify({'error': 'No data provided'}), 400
        if table == 'timetable_teacher' and 'teacher' in record_data:
            record_data['fio'] = record_data.get('fio') or record_data.get('teacher')
        
        allowed_fields = _allowed_insert_fields(table)
        insert_fields = []
        insert_values = []
        placeholders = []
        
        for field in allowed_fields:
            if field not in record_data:
                continue
            value = record_data[field]
            insert_fields.append(field)
            placeholders.append('%s')
            if value == '' or value is None:
                insert_values.append(None)
            elif field in ['pair_number', 'subgroup', 'num_subgroups']:
                try:
                    insert_values.append(int(value) if value is not None else None)
                except (ValueError, TypeError):
                    insert_values.append(None)
            elif field in ['is_external', 'is_remote']:
                insert_values.append(bool(value) if value is not None else None)
            else:
                insert_values.append(str(value) if value is not None else None)
        
        if not insert_fields:
            return jsonify({'error': 'No valid fields provided'}), 400
        
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        insert_query = f"""
            INSERT INTO {table} ({', '.join(insert_fields)})
            VALUES ({', '.join(placeholders)})
            RETURNING *
        """
        cursor.execute(insert_query, insert_values)
        new_record = cursor.fetchone()
        new_id = new_record['id']
        
        final_id = new_id
        if reference_id and position and table == 'timetable_cleaned':
            cursor.execute(f"SELECT id FROM {table} WHERE id = %s", (reference_id,))
            ref_record = cursor.fetchone()
            if ref_record:
                ref_id = ref_record['id']
                if position == 'before':
                    cursor.execute(f"SELECT MAX(id) as max_id FROM {table}")
                    max_id_result = cursor.fetchone()
                    max_id = max_id_result['max_id'] if max_id_result and max_id_result['max_id'] else new_id
                    temp_id = max_id + 1000000
                    cursor.execute(f"UPDATE {table} SET id = %s WHERE id = %s", (temp_id, new_id))
                    cursor.execute(f"UPDATE {table} SET id = %s WHERE id = %s", (new_id, ref_id))
                    cursor.execute(f"UPDATE {table} SET id = %s WHERE id = %s", (ref_id, temp_id))
                    final_id = ref_id
                else:
                    final_id = new_id
        conn.commit()
        
        if table == 'timetable_teacher':
            cursor.execute(
                """SELECT id, day_of_week, pair_number, subject_name, audience, fio,
                    fio AS teacher, group_name, week_type, subgroup,
                    NULL::TEXT AS institute, NULL::TEXT AS course, NULL::TEXT AS direction,
                    department, is_external, is_remote, num_subgroups
                FROM timetable_teacher WHERE id = %s""",
                (final_id,)
            )
        else:
            cursor.execute(f"SELECT * FROM {table} WHERE id = %s", (final_id,))
        final_record = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if final_record:
            return jsonify({'message': 'Record created successfully', 'record': dict(final_record)}), 201
        return jsonify({'error': 'Failed to create record'}), 500
    except Exception as e:
        import traceback
        print(f"Error creating record: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/db/records/<int:record_id>', methods=['DELETE'])
def delete_record(record_id):
    """Удаляет запись из выбранной таблицы (table=...). Для intermediate_timetable удаляет из cleaned/teacher и пересобирает merge."""
    try:
        table = get_table_param()
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        if table == 'intermediate_timetable':
            if not _intermediate_has_cleaned_id(cursor):
                cursor.close()
                conn.close()
                return jsonify({
                    'error': 'Таблица intermediate_timetable создана старой версией. Выполните «Слияние расписания» заново.'
                }), 400
            cursor.execute(
                "SELECT cleaned_id, teacher_id FROM intermediate_timetable WHERE id = %s",
                (record_id,)
            )
            row = cursor.fetchone()
            if not row:
                cursor.close()
                conn.close()
                return jsonify({'error': 'Record not found'}), 404
            cleaned_id, teacher_id = row.get('cleaned_id'), row.get('teacher_id')
            if cleaned_id is not None:
                cursor.execute("DELETE FROM timetable_cleaned WHERE id = %s", (cleaned_id,))
            if teacher_id is not None:
                cursor.execute("DELETE FROM timetable_teacher WHERE id = %s", (teacher_id,))
            conn.commit()
            cursor.close()
            conn.close()
            run_merge_timetable()
            return jsonify({'message': 'Record deleted successfully'}), 200
        cursor.execute(f"SELECT id FROM {table} WHERE id = %s", (record_id,))
        record = cursor.fetchone()
        if not record:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Record not found'}), 404
        cursor.execute(f"DELETE FROM {table} WHERE id = %s", (record_id,))
        rows_affected = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        if rows_affected > 0:
            return jsonify({'message': 'Record deleted successfully'}), 200
        return jsonify({'error': 'Failed to delete record'}), 500
    except Exception as e:
        import traceback
        print(f"Error deleting record {record_id}: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# --- API преподавателей (info/teacher_all.json) ---
@app.route('/api/teachers', methods=['GET'])
def get_teachers():
    """Список преподавателей с пагинацией и фильтром по ФИО."""
    try:
        teachers = read_teachers()
        fio_filter = (request.args.get('fio') or '').strip().lower()
        if fio_filter:
            teachers = [t for t in teachers if fio_filter in (t.get('fio') or '').lower()]
        total = len(teachers)
        page = max(1, int(request.args.get('page', 1)))
        limit = max(1, min(100, int(request.args.get('limit', 50))))
        offset = (page - 1) * limit
        page_list = teachers[offset:offset + limit]
        # Добавляем глобальный индекс для PUT/DELETE
        for i, t in enumerate(page_list):
            t['_index'] = offset + i
        pages = (total + limit - 1) // limit if total > 0 else 0
        return jsonify({
            'teachers': page_list,
            'total': total,
            'page': page,
            'limit': limit,
            'pages': pages
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/teachers', methods=['POST'])
def add_teacher():
    """Добавить одного преподавателя (для дубликата или пустой записи)."""
    try:
        data = request.get_json() or {}
        teacher = {k: (data.get(k) or '') if k in data else '' for k in TEACHER_KEYS}
        for k in TEACHER_KEYS:
            val = teacher.get(k)
            teacher[k] = '' if val is None else str(val).strip()
        teachers = read_teachers()
        teachers.append(teacher)
        save_teachers(teachers)
        return jsonify({'message': 'OK', 'total': len(teachers)}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/teachers/<int:index>', methods=['PUT'])
def update_teacher(index):
    """Обновить преподавателя по индексу (0-based)."""
    try:
        teachers = read_teachers()
        if index < 0 or index >= len(teachers):
            return jsonify({'error': 'Index out of range'}), 404
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        for key in TEACHER_KEYS:
            if key in data:
                val = data[key]
                teachers[index][key] = '' if val is None else str(val).strip()
        save_teachers(teachers)
        return jsonify({'message': 'OK', 'teacher': teachers[index]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/teachers/bulk', methods=['POST'])
def bulk_add_teachers():
    """Добавить преподавателей из списка строк (каждая строка — ФИО). Дубликаты по ФИО пропускаются."""
    try:
        data = request.get_json()
        lines = (data.get('lines') or '').strip()
        if not lines:
            return jsonify({'error': 'lines is required'}), 400
        teachers = read_teachers()
        existing_fios = {(t.get('fio') or '').strip().lower() for t in teachers}
        added = 0
        skipped = 0
        for line in lines.split('\n'):
            fio = line.strip()
            if not fio:
                continue
            key = fio.lower()
            if key in existing_fios:
                skipped += 1
                continue
            existing_fios.add(key)
            teachers.append({k: fio if k == 'fio' else '' for k in TEACHER_KEYS})
            added += 1
        save_teachers(teachers)
        return jsonify({
            'message': 'OK',
            'added': added,
            'skipped_duplicates': skipped,
            'total': len(teachers)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/teachers/<int:index>', methods=['DELETE'])
def delete_teacher(index):
    """Удалить преподавателя по индексу (0-based)."""
    try:
        teachers = read_teachers()
        if index < 0 or index >= len(teachers):
            return jsonify({'error': 'Index out of range'}), 404
        teachers.pop(index)
        save_teachers(teachers)
        return jsonify({'message': 'OK', 'total': len(teachers)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- Дисциплины (info/discipline.json) ---
DISCIPLINE_FILE = os.path.join(get_project_root(), 'info', 'discipline.json')


def read_disciplines():
    """Читает список названий дисциплин из info/discipline.json (массив строк)."""
    if not os.path.isfile(DISCIPLINE_FILE):
        return []
    with open(DISCIPLINE_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, list):
        return []
    return [str(x).strip() for x in data if x is not None and str(x).strip()]


def save_disciplines(disciplines):
    """Сохраняет список дисциплин в info/discipline.json (UTF-8)."""
    os.makedirs(os.path.dirname(DISCIPLINE_FILE), exist_ok=True)
    with open(DISCIPLINE_FILE, 'w', encoding='utf-8') as f:
        json.dump(disciplines, f, ensure_ascii=False, indent=2)


# --- Сопоставление дисциплин из БД со справочником (discipline.json + discipline_validate.py) ---

def _intermediate_table_exists(cursor):
    """Проверяет, что таблица intermediate_timetable существует."""
    cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'intermediate_timetable'"
    )
    return cursor.fetchone() is not None


def _timetable_aspi_exists(cursor):
    """Проверяет, что таблица timetable_aspi существует."""
    cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'timetable_aspi'"
    )
    return cursor.fetchone() is not None


def _discipline_match_table(request_or_args, body_key='table'):
    """Возвращает 'intermediate' или 'aspi' из query (GET) или body (POST). По умолчанию intermediate."""
    if hasattr(request_or_args, 'args'):
        t = (request_or_args.args.get('table') or '').strip().lower()
    else:
        t = (request_or_args.get(body_key) or '').strip().lower()
    return 'aspi' if t == 'aspi' else 'intermediate'


def _strip_for_match(s, strip_text, strip_at):
    """Удаляет strip_text из начала или конца строки s. strip_at: 'start' или 'end'."""
    if not s or not strip_text:
        return (s or '').strip()
    s = str(s).strip()
    if strip_at == 'end':
        if s.endswith(strip_text):
            return s[:-len(strip_text)].strip()
    else:
        if s.startswith(strip_text):
            return s[len(strip_text):].strip()
    return s


def _is_matched_by_canonical(original, canonical_lower, canonical_list, strip_text, strip_at, match_full):
    """Проверяет, считается ли original уже совпавшим со справочником.
    match_full=True: точное совпадение (после strip).
    match_full=False: частичное — строка справочника входит в original или наоборот."""
    if not original:
        return False
    o = original.strip()
    o_lower = o.lower()
    stripped = _strip_for_match(o, strip_text, strip_at) if strip_text else o
    stripped_lower = stripped.lower()
    if match_full:
        return stripped_lower in canonical_lower or o_lower in canonical_lower
    for c in canonical_list:
        c_lower = c.strip().lower()
        if not c_lower:
            continue
        if c_lower in stripped_lower or stripped_lower in c_lower:
            return True
    return False


def _ensure_intermediate_discipline_original(conn):
    """Добавляет колонку discipline_original в intermediate_timetable, если её ещё нет (миграция для старых БД)."""
    cur = conn.cursor()
    try:
        cur.execute(
            "ALTER TABLE intermediate_timetable ADD COLUMN IF NOT EXISTS discipline_original TEXT"
        )
        conn.commit()
    finally:
        cur.close()


@app.route('/api/discipline-match/unmatched', methods=['GET'])
def get_discipline_match_unmatched():
    """Список названий из intermediate_timetable или timetable_aspi (query: table=intermediate|aspi), которых нет в discipline.json.
    Параметры: strip_text — удалить перед сравнением, strip_at — start|end, match_full — 1|0 (полное/частичное)."""
    try:
        table = _discipline_match_table(request)
        strip_text = (request.args.get('strip_text') or '').strip()
        strip_at = (request.args.get('strip_at') or 'start').strip().lower()
        if strip_at not in ('start', 'end'):
            strip_at = 'start'
        match_full = request.args.get('match_full', '1') in ('1', 'true', 'yes')
        import discipline_validate as match_module
        canonical = read_disciplines()
        canonical_lower = {d.strip().lower() for d in canonical}
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        if table == 'aspi':
            if not _timetable_aspi_exists(cur):
                cur.close()
                conn.close()
                return jsonify({
                    'error': 'Таблица timetable_aspi не найдена. Сначала выполните «Добавить в БД» для аспирантов.',
                    'items': []
                }), 400
            sql = "SELECT DISTINCT subject_name FROM timetable_aspi WHERE subject_name IS NOT NULL AND TRIM(subject_name) != ''"
        else:
            if not _intermediate_table_exists(cur):
                cur.close()
                conn.close()
                return jsonify({
                    'error': 'Таблица intermediate_timetable не найдена. Сначала выполните «Слияние расписания» в разделе загрузки.',
                    'items': []
                }), 400
            _ensure_intermediate_discipline_original(conn)
            sql = "SELECT DISTINCT subject_name FROM intermediate_timetable WHERE subject_name IS NOT NULL AND TRIM(subject_name) != ''"
        cur.execute(sql)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        distinct = [r[0].strip() for r in rows if r[0] and str(r[0]).strip()]
        # Фильтр «несовпадающие» — только по исходной строке, без strip (не убираем строки из списка)
        unmatched = list(dict.fromkeys(
            s for s in distinct
            if not _is_matched_by_canonical(s, canonical_lower, canonical, '', 'start', match_full)
        ))
        if not unmatched:
            return jsonify({'items': [], 'message': 'Нет несовпадающих дисциплин'})

        documents, doc_embeddings = match_module.ensure_embeddings()
        if not documents or doc_embeddings is None:
            return jsonify({'error': 'Не удалось загрузить справочник или эмбеддинги', 'items': []}), 500

        items = []
        for original in unmatched:
            query_text = _strip_for_match(original, strip_text, strip_at) if strip_text else original
            try:
                top4 = match_module.match_query(query_text, documents, doc_embeddings, top_k=4)
            except Exception:
                top4 = []
            if not top4:
                items.append({
                    'original': original,
                    'suggested': '',
                    'score': 0.0,
                    'alternatives': []
                })
                continue
            suggested, score = top4[0]
            alternatives = [{'name': name, 'score': round(s, 3)} for name, s in top4[1:4]]
            items.append({
                'original': original,
                'suggested': suggested,
                'score': round(score, 3),
                'alternatives': alternatives
            })
        return jsonify({'items': items})
    except Exception as e:
        return jsonify({'error': str(e), 'items': []}), 500


@app.route('/api/discipline-match/apply', methods=['POST'])
def apply_discipline_match():
    """Для всех несовпадающих: если точность >= threshold, заменить subject_name на предложенное. body: threshold, table, strip_text, strip_at, match_full."""
    conn = None
    try:
        data = request.get_json(silent=True) or {}
        try:
            threshold = float(data.get('threshold', 0.95))
        except (TypeError, ValueError):
            threshold = 0.95
        threshold = max(0.0, min(1.0, threshold))
        table = _discipline_match_table(data, 'table')
        strip_text = (data.get('strip_text') or '').strip()
        strip_at = (str(data.get('strip_at') or 'start')).strip().lower()
        if strip_at not in ('start', 'end'):
            strip_at = 'start'
        match_full = data.get('match_full', True) in (True, 1, '1', 'true', 'yes')
        import discipline_validate as match_module
        canonical = read_disciplines()
        canonical_lower = {d.strip().lower() for d in canonical}
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        if table == 'aspi':
            if not _timetable_aspi_exists(cur):
                cur.close()
                conn.close()
                return jsonify({
                    'error': 'Таблица timetable_aspi не найдена. Сначала выполните «Добавить в БД» для аспирантов.'
                }), 400
            sql_distinct = "SELECT DISTINCT subject_name FROM timetable_aspi WHERE subject_name IS NOT NULL AND TRIM(subject_name) != ''"
        else:
            if not _intermediate_table_exists(cur):
                cur.close()
                conn.close()
                return jsonify({
                    'error': 'Таблица intermediate_timetable не найдена. Сначала выполните «Слияние расписания» в разделе загрузки.'
                }), 400
            _ensure_intermediate_discipline_original(conn)
            sql_distinct = "SELECT DISTINCT subject_name FROM intermediate_timetable WHERE subject_name IS NOT NULL AND TRIM(subject_name) != ''"
        cur.execute(sql_distinct)
        rows = cur.fetchall()
        distinct = [r[0].strip() for r in rows if r[0] and str(r[0]).strip()]
        # Фильтр «несовпадающие» — только по исходной строке, без strip
        unmatched = list(dict.fromkeys(
            s for s in distinct
            if not _is_matched_by_canonical(s, canonical_lower, canonical, '', 'start', match_full)
        ))
        if not unmatched:
            cur.close()
            conn.close()
            return jsonify({'replaced': 0, 'message': 'Нет несовпадающих дисциплин'})

        documents, doc_embeddings = match_module.ensure_embeddings()
        if not documents or doc_embeddings is None:
            cur.close()
            conn.close()
            return jsonify({'error': 'Не удалось загрузить справочник или эмбеддинги. Убедитесь, что Ollama запущен (nomic-embed-text).'}), 500

        table_name = 'timetable_aspi' if table == 'aspi' else 'intermediate_timetable'
        replaced = 0
        for original in unmatched:
            cleaned_ids = []
            query_text = _strip_for_match(original, strip_text, strip_at) if strip_text else original
            try:
                top4 = match_module.match_query(query_text, documents, doc_embeddings, top_k=1)
            except Exception:
                continue
            score = top4[0][1] if top4 else 0.0
            if score < threshold - 1e-9:
                continue
            suggested = top4[0][0]
            if table == 'intermediate':
                cur.execute(
                    "SELECT cleaned_id FROM intermediate_timetable WHERE TRIM(COALESCE(subject_name, '')) = %s",
                    (original,)
                )
                cleaned_ids = [r[0] for r in cur.fetchall() if r[0]]
            cur.execute(
                f"UPDATE {table_name} SET subject_name = %s, discipline_original = %s WHERE TRIM(COALESCE(subject_name, '')) = %s",
                (suggested, original, original)
            )
            replaced += cur.rowcount
            if table == 'intermediate' and cleaned_ids:
                cur.execute(
                    "UPDATE timetable_cleaned SET subject_name = %s WHERE id = ANY(%s)",
                    (suggested, cleaned_ids)
                )
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'replaced': replaced})
    except Exception as e:
        if conn:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
        return jsonify({'error': str(e)}), 500


@app.route('/api/discipline-match/replace', methods=['POST'])
def replace_discipline_match():
    """Заменить все вхождения original на replacement. body: original, replacement, table=intermediate|aspi. Для intermediate синхронизирует timetable_cleaned."""
    try:
        data = request.get_json(silent=True) or {}
        original = (data.get('original') or '').strip()
        replacement = (data.get('replacement') or '').strip()
        table = _discipline_match_table(data, 'table')
        if not original:
            return jsonify({'error': 'original is required'}), 400
        new_name = replacement or original
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        if table == 'aspi':
            if not _timetable_aspi_exists(cur):
                cur.close()
                conn.close()
                return jsonify({'error': 'Таблица timetable_aspi не найдена. Сначала выполните «Добавить в БД» для аспирантов.'}), 400
            table_name = 'timetable_aspi'
            cur.execute(
                f"UPDATE {table_name} SET subject_name = %s, discipline_original = %s WHERE TRIM(COALESCE(subject_name, '')) = %s",
                (new_name, original, original)
            )
            updated = cur.rowcount
        else:
            if not _intermediate_table_exists(cur):
                cur.close()
                conn.close()
                return jsonify({'error': 'Таблица intermediate_timetable не найдена. Сначала выполните «Слияние расписания».'}), 400
            _ensure_intermediate_discipline_original(conn)
            cur.execute(
                "SELECT cleaned_id FROM intermediate_timetable WHERE TRIM(COALESCE(subject_name, '')) = %s",
                (original,)
            )
            cleaned_ids = [r[0] for r in cur.fetchall() if r[0]]
            cur.execute(
                "UPDATE intermediate_timetable SET subject_name = %s, discipline_original = %s WHERE TRIM(COALESCE(subject_name, '')) = %s",
                (new_name, original, original)
            )
            updated = cur.rowcount
            if cleaned_ids:
                cur.execute(
                    "UPDATE timetable_cleaned SET subject_name = %s WHERE id = ANY(%s)",
                    (new_name, cleaned_ids)
                )
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'updated': updated})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/disciplines', methods=['GET'])
def get_disciplines():
    """Список дисциплин с пагинацией и фильтром по названию."""
    try:
        disciplines = read_disciplines()
        name_filter = (request.args.get('name') or '').strip().lower()
        if name_filter:
            disciplines = [d for d in disciplines if name_filter in d.lower()]
        total = len(disciplines)
        page = max(1, int(request.args.get('page', 1)))
        limit = max(1, min(100, int(request.args.get('limit', 50))))
        offset = (page - 1) * limit
        page_list = disciplines[offset:offset + limit]
        # Добавляем глобальный индекс для PUT/DELETE
        result = [{'name': d, '_index': offset + i} for i, d in enumerate(page_list)]
        pages = (total + limit - 1) // limit if total > 0 else 0
        return jsonify({
            'disciplines': result,
            'total': total,
            'page': page,
            'limit': limit,
            'pages': pages
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/disciplines', methods=['POST'])
def add_discipline():
    """Добавить одну дисциплину. Тело: { "name": "..." }."""
    try:
        data = request.get_json() or {}
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'error': 'name is required'}), 400
        disciplines = read_disciplines()
        if name.lower() in [d.lower() for d in disciplines]:
            return jsonify({'error': 'Duplicate discipline', 'total': len(disciplines)}), 400
        disciplines.append(name)
        save_disciplines(disciplines)
        return jsonify({'message': 'OK', 'total': len(disciplines)}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/disciplines/bulk', methods=['POST'])
def bulk_add_disciplines():
    """Добавить дисциплины из списка строк (каждая строка — название). Дубликаты пропускаются."""
    try:
        data = request.get_json()
        lines = (data.get('lines') or '').strip()
        if not lines:
            return jsonify({'error': 'lines is required'}), 400
        disciplines = read_disciplines()
        existing = {d.strip().lower() for d in disciplines}
        added = 0
        skipped = 0
        for line in lines.split('\n'):
            name = line.strip()
            if not name:
                continue
            key = name.lower()
            if key in existing:
                skipped += 1
                continue
            existing.add(key)
            disciplines.append(name)
            added += 1
        save_disciplines(disciplines)
        return jsonify({
            'message': 'OK',
            'added': added,
            'skipped_duplicates': skipped,
            'total': len(disciplines)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/disciplines/<int:index>', methods=['PUT'])
def update_discipline(index):
    """Обновить дисциплину по индексу (0-based). Тело: { "name": "..." }."""
    try:
        disciplines = read_disciplines()
        if index < 0 or index >= len(disciplines):
            return jsonify({'error': 'Index out of range'}), 404
        data = request.get_json() or {}
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'error': 'name is required'}), 400
        disciplines[index] = name
        save_disciplines(disciplines)
        return jsonify({'message': 'OK', 'name': name})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/disciplines/<int:index>', methods=['DELETE'])
def delete_discipline(index):
    """Удалить дисциплину по индексу (0-based)."""
    try:
        disciplines = read_disciplines()
        if index < 0 or index >= len(disciplines):
            return jsonify({'error': 'Index out of range'}), 404
        disciplines.pop(index)
        save_disciplines(disciplines)
        return jsonify({'message': 'OK', 'total': len(disciplines)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Редактируемые JSON-файлы из info/ (skip_row_phrases, slash_protected, strip_from_subject)
INFO_EDITABLE_FILES = ('skip_row_phrases', 'slash_protected', 'strip_from_subject', 'replace_in_subject')


def _info_file_path(name):
    """Путь к файлу info/<name>.json в корне проекта."""
    if name not in INFO_EDITABLE_FILES:
        return None
    return os.path.join(get_project_root(), 'info', name + '.json')


@app.route('/api/info-files/<name>', methods=['GET'])
def get_info_file(name):
    """Прочитать JSON-файл из info/ (skip_row_phrases, slash_protected, strip_from_subject)."""
    path = _info_file_path(name)
    if not path or not os.path.isfile(path):
        return jsonify({'error': 'File not found or not allowed'}), 404
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify({'content': data, 'raw': json.dumps(data, ensure_ascii=False, indent=2)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/info-files/<name>', methods=['PUT'])
def put_info_file(name):
    """Сохранить JSON-файл в info/. Тело: { "content": <массив или объект> } или { "raw": "строка JSON" }."""
    path = _info_file_path(name)
    if not path:
        return jsonify({'error': 'Not allowed'}), 400
    try:
        body = request.get_json() or {}
        if 'raw' in body:
            data = json.loads(body['raw'])
        elif 'content' in body:
            data = body['content']
        else:
            return jsonify({'error': 'Need "content" or "raw" in body'}), 400
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return jsonify({'message': 'OK', 'raw': json.dumps(data, ensure_ascii=False, indent=2)})
    except json.JSONDecodeError as e:
        return jsonify({'error': f'Invalid JSON: {e}'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5001, host='0.0.0.0')
