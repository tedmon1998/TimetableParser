from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import json
import subprocess
import os
import glob
import shutil
import threading
import time
import csv
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

app = Flask(__name__)
CORS(app)

# Параметры подключения к БД
DB_CONFIG = {
    'host': 'edro.su',
    'port': 50003,
    'user': 'edro',
    'password': 'Pg123!',
    'database': 'test_sursu_timetable'
}

# Глобальные переменные для отслеживания прогресса
script_status = {
    'parse_timetable': {'running': False, 'progress': 0, 'message': '', 'error': None},
    'clean_audiences': {'running': False, 'progress': 0, 'message': '', 'error': None},
    'process_timetable': {'running': False, 'progress': 0, 'message': '', 'error': None},
    'fetch_teachers': {'running': False, 'progress': 0, 'message': '', 'error': None}
}

# Разрешённые таблицы для просмотра записей
ALLOWED_TABLES = ('timetable_cleaned', 'timetable_teacher')

def get_table_param():
    """Возвращает имя таблицы из query param (timetable_cleaned или timetable_teacher)."""
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
    """Удаляет все файлы в output/timetable"""
    output_dir = os.path.join(get_project_root(), 'output', 'timetable')
    if os.path.exists(output_dir):
        deleted_count = 0
        for file in glob.glob(os.path.join(output_dir, '*')):
            if os.path.isfile(file) and not os.path.basename(file).startswith('~$'):
                try:
                    os.remove(file)
                    deleted_count += 1
                    print(f"Удален файл: {file}")
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
        
        # Запускаем скрипт
        process = subprocess.Popen(
            ['python', script_path],
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        script_status['parse_timetable']['progress'] = 40
        script_status['parse_timetable']['message'] = 'Обработка файлов...'
        
        # Читаем вывод в реальном времени
        output_lines = []
        
        # Простой способ чтения вывода
        while True:
            output = process.stdout.readline()
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
        stderr_output = process.stderr.read()
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
                except Exception as e:
                    print(f"Ошибка при удалении {file}: {e}")
        
        script_status['clean_audiences']['progress'] = 20
        script_status['clean_audiences']['message'] = 'Запуск скрипта очистки...'
        
        # Запускаем скрипт
        process = subprocess.Popen(
            ['python', script_path],
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        script_status['clean_audiences']['progress'] = 40
        script_status['clean_audiences']['message'] = 'Обработка данных...'
        
        # Читаем вывод в реальном времени
        output_lines = []
        while True:
            output = process.stdout.readline()
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
        stderr_output = process.stderr.read()
        if stderr_output:
            print(f"Stderr: {stderr_output}")
        
        if return_code == 0:
            script_status['clean_audiences']['progress'] = 100
            script_status['clean_audiences']['message'] = 'Очистка завершена успешно! База данных обновлена.'
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
        process = subprocess.Popen(
            ['python', script_path],
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        script_status['process_timetable']['progress'] = 40
        script_status['process_timetable']['message'] = 'Обработка файла занятости...'
        output_lines = []
        while True:
            out = process.stdout.readline()
            if out == '' and process.poll() is not None:
                break
            if out:
                line = out.strip()
                if line:
                    output_lines.append(line)
                    script_status['process_timetable']['progress'] = min(40 + min(len(output_lines) * 2, 50), 90)
                    script_status['process_timetable']['message'] = f'Обработано строк: {len(output_lines)}'
        return_code = process.wait()
        stderr_output = process.stderr.read()
        if stderr_output:
            print(f"Stderr process_timetable: {stderr_output}")
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
    """Запускает clean_audiences.py"""
    if script_status['clean_audiences']['running']:
        return jsonify({'error': 'Script is already running'}), 400
    
    thread = threading.Thread(target=run_clean_audiences)
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
        process = subprocess.Popen(
            ['python', script_path],
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        output_lines = []
        while True:
            out = process.stdout.readline()
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
        stderr_output = process.stderr.read()
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
    """Возвращает статистику из базы данных (таблица: timetable_cleaned или timetable_teacher)"""
    try:
        table = get_table_param()
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(f"SELECT COUNT(*) as total FROM {table}")
        total = cursor.fetchone()['total']
        
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
        
        # Фильтр по типу занятия (только для timetable_cleaned)
        if table == 'timetable_cleaned' and filters['lecture_type']:
            where_conditions.append("lecture_type ILIKE %s")
            query_params.append(f"%{filters['lecture_type']}%")
        
        # Фильтр по аудитории
        if filters['audience']:
            where_conditions.append("audience ILIKE %s")
            query_params.append(f"%{filters['audience']}%")
        
        # Фильтр по ФИО преподавателя (timetable_teacher имеет только fio, timetable_cleaned — fio и teacher)
        if filters['fio']:
            if table == 'timetable_teacher':
                where_conditions.append("fio ILIKE %s")
                query_params.append(f"%{filters['fio']}%")
            else:
                where_conditions.append("(fio ILIKE %s OR teacher ILIKE %s)")
                query_params.append(f"%{filters['fio']}%")
                query_params.append(f"%{filters['fio']}%")
        
        # Фильтр по преподавателю (альтернативное поле; для timetable_teacher ищем по fio)
        if filters['teacher']:
            if table == 'timetable_teacher':
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
        
        # Фильтр по подгруппе
        if filters['subgroup']:
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
        
        # Фильтр по институту (только для timetable_cleaned)
        if table == 'timetable_cleaned' and filters['institute']:
            where_conditions.append("institute ILIKE %s")
            query_params.append(f"%{filters['institute']}%")
        
        # Фильтр по курсу (только для timetable_cleaned)
        if table == 'timetable_cleaned' and filters['course']:
            where_conditions.append("course ILIKE %s")
            query_params.append(f"%{filters['course']}%")
        
        # Фильтр по направлению (только для timetable_cleaned)
        if table == 'timetable_cleaned' and filters['direction']:
            where_conditions.append("direction ILIKE %s")
            query_params.append(f"%{filters['direction']}%")
        
        # Фильтр по профилю (только для timetable_cleaned)
        if table == 'timetable_cleaned' and filters['profile']:
            where_conditions.append("profile ILIKE %s")
            query_params.append(f"%{filters['profile']}%")
        
        # Формируем SQL запрос
        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)
        
        # Получаем параметры сортировки
        sort_by = request.args.get('sort_by', 'id').strip()
        sort_order = request.args.get('sort_order', 'desc').strip().upper()
        
        # Валидация параметров сортировки
        allowed_sort_fields = ['id', 'day_of_week', 'pair_number', 'subject_name', 'lecture_type', 
                              'audience', 'fio', 'teacher', 'group_name', 'subgroup', 'course', 
                              'institute', 'direction', 'profile', 'week_type']
        if sort_by not in allowed_sort_fields:
            sort_by = 'id'
        
        if sort_order not in ['ASC', 'DESC']:
            sort_order = 'DESC'
        
        # Для дня недели — сортировка по порядку (понедельник=1, ..., воскресенье=7), а не по алфавиту
        day_order_sql = """CASE LOWER(TRIM(COALESCE(day_of_week, '')))
            WHEN 'понедельник' THEN 1 WHEN 'вторник' THEN 2 WHEN 'среда' THEN 3
            WHEN 'четверг' THEN 4 WHEN 'пятница' THEN 5 WHEN 'суббота' THEN 6
            WHEN 'воскресенье' THEN 7 ELSE 8 END"""
        order_clause = f"{day_order_sql} {sort_order}" if sort_by == 'day_of_week' else f"{sort_by} {sort_order}"
        
        if table == 'timetable_teacher':
            sort_by_allowed = ['id', 'day_of_week', 'pair_number', 'subject_name', 'audience', 'fio', 'group_name', 'subgroup', 'course', 'week_type']
            if sort_by not in sort_by_allowed:
                sort_by = 'id'
                order_clause = f"{sort_by} {sort_order}"
            elif sort_by == 'day_of_week':
                order_clause = f"{day_order_sql} {sort_order}"
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
            if sort_by == 'day_of_week':
                order_clause = f"{day_order_sql} {sort_order}"
            query = f"""
                SELECT id, day_of_week, pair_number, subject_name, lecture_type, audience,
                    fio, teacher, group_name, week_type, subgroup,
                    institute, course, direction, department,
                    is_external, is_remote, num_subgroups
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
            
            # Логируем первую запись для отладки
            if len(records_list) == 0:
                print(f"DEBUG: Первая запись из БД: {record_dict}")
                print(f"DEBUG: Ключи записи: {list(record_dict.keys())}")
                print(f"DEBUG: fio={record_dict.get('fio')}, teacher={record_dict.get('teacher')}, group_name={record_dict.get('group_name')}, week_type={record_dict.get('week_type')}")
            
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
    """Очищает выбранную таблицу (table=timetable_cleaned или timetable_teacher)"""
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

def _allowed_update_fields(table):
    """Разрешённые поля для обновления в зависимости от таблицы."""
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

@app.route('/api/db/records/<int:record_id>', methods=['PUT'])
def update_record(record_id):
    """Обновляет запись в выбранной таблице (table=...)."""
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
        
        update_fields = []
        update_values = []
        
        for field in allowed_fields:
            if field not in data:
                continue
            value = data[field]
            if value == '' or value is None:
                update_values.append(None)
            elif field in ['pair_number', 'subgroup', 'num_subgroups']:
                try:
                    update_values.append(int(value) if value is not None else None)
                except (ValueError, TypeError):
                    update_values.append(None)
            elif field in ['is_external', 'is_remote']:
                update_values.append(bool(value) if value is not None else None)
            else:
                update_values.append(str(value) if value is not None else None)
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

def _allowed_insert_fields(table):
    """Разрешённые поля для вставки в зависимости от таблицы."""
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

@app.route('/api/db/records', methods=['POST'])
def create_record():
    """Создаёт новую запись в выбранной таблице (table=...)."""
    try:
        table = get_table_param()
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        reference_id = data.get('_reference_id')
        position = data.get('_position')
        record_data = {k: v for k, v in data.items() if not k.startswith('_')}
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
    """Удаляет запись из выбранной таблицы (table=...)."""
    try:
        table = get_table_param()
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
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


if __name__ == '__main__':
    app.run(debug=True, port=5001, host='0.0.0.0')
