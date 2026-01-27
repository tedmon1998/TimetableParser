from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import subprocess
import os
import glob
import shutil
import threading
import time
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

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
    'clean_audiences': {'running': False, 'progress': 0, 'message': '', 'error': None}
}

def get_project_root():
    """Возвращает корневую директорию проекта (где находятся скрипты parse_timetable_excel.py и clean_audiences.py)"""
    # Текущий файл: web_app/backend/app.py
    # Нужно подняться на 2 уровня вверх: web_app/backend -> web_app -> корень проекта
    current_dir = os.path.dirname(os.path.abspath(__file__))  # web_app/backend
    parent_dir = os.path.dirname(current_dir)  # web_app
    project_root = os.path.dirname(parent_dir)  # корень проекта (H:\Project\TimetableParser)
    return project_root

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

@app.route('/api/db/stats', methods=['GET'])
def get_db_stats():
    """Возвращает статистику из базы данных"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Общее количество записей
        cursor.execute("SELECT COUNT(*) as total FROM timetable_cleaned")
        total = cursor.fetchone()['total']
        
        # Количество по дням недели
        cursor.execute("""
            SELECT day_of_week, COUNT(*) as count 
            FROM timetable_cleaned 
            GROUP BY day_of_week 
            ORDER BY day_of_week
        """)
        by_day = cursor.fetchall()
        
        # Количество по типам занятий
        cursor.execute("""
            SELECT lecture_type, COUNT(*) as count 
            FROM timetable_cleaned 
            GROUP BY lecture_type 
            ORDER BY lecture_type
        """)
        by_type = cursor.fetchall()
        
        # Последнее обновление
        cursor.execute("""
            SELECT MAX(created_at) as last_update 
            FROM timetable_cleaned
        """)
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
    """Возвращает записи из базы данных с пагинацией и фильтрами"""
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        offset = (page - 1) * limit
        
        # Получаем фильтры из query параметров
        filters = {
            'day_of_week': request.args.get('day_of_week', '').strip(),
            'pair_number': request.args.get('pair_number', '').strip(),
            'subject_name': request.args.get('subject_name', '').strip(),
            'lecture_type': request.args.get('lecture_type', '').strip(),
            'audience': request.args.get('audience', '').strip(),
            'fio': request.args.get('fio', '').strip(),
            'teacher': request.args.get('teacher', '').strip(),
            'group_name': request.args.get('group_name', '').strip(),
            'week_type': request.args.get('week_type', '').strip(),
            'institute': request.args.get('institute', '').strip(),
            'course': request.args.get('course', '').strip(),
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
        
        # Фильтр по типу занятия
        if filters['lecture_type']:
            where_conditions.append("lecture_type ILIKE %s")
            query_params.append(f"%{filters['lecture_type']}%")
        
        # Фильтр по аудитории
        if filters['audience']:
            where_conditions.append("audience ILIKE %s")
            query_params.append(f"%{filters['audience']}%")
        
        # Фильтр по ФИО преподавателя
        if filters['fio']:
            where_conditions.append("(fio ILIKE %s OR teacher ILIKE %s)")
            query_params.append(f"%{filters['fio']}%")
            query_params.append(f"%{filters['fio']}%")
        
        # Фильтр по преподавателю (альтернативное поле)
        if filters['teacher']:
            where_conditions.append("(teacher ILIKE %s OR fio ILIKE %s)")
            query_params.append(f"%{filters['teacher']}%")
            query_params.append(f"%{filters['teacher']}%")
        
        # Фильтр по группе
        if filters['group_name']:
            where_conditions.append("group_name ILIKE %s")
            query_params.append(f"%{filters['group_name']}%")
        
        # Фильтр по типу недели
        if filters['week_type']:
            where_conditions.append("week_type ILIKE %s")
            query_params.append(f"%{filters['week_type']}%")
        
        # Фильтр по институту
        if filters['institute']:
            where_conditions.append("institute ILIKE %s")
            query_params.append(f"%{filters['institute']}%")
        
        # Фильтр по курсу
        if filters['course']:
            where_conditions.append("course ILIKE %s")
            query_params.append(f"%{filters['course']}%")
        
        # Формируем SQL запрос
        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)
        
        # Получаем параметры сортировки
        sort_by = request.args.get('sort_by', 'id').strip()
        sort_order = request.args.get('sort_order', 'desc').strip().upper()
        
        # Валидация параметров сортировки
        allowed_sort_fields = ['id', 'day_of_week', 'pair_number', 'subject_name', 'lecture_type', 
                              'audience', 'fio', 'teacher', 'group_name', 'week_type']
        if sort_by not in allowed_sort_fields:
            sort_by = 'id'
        
        if sort_order not in ['ASC', 'DESC']:
            sort_order = 'DESC'
        
        # Запрос для получения записей (явно указываем все нужные поля)
        query = f"""
            SELECT 
                id,
                day_of_week,
                pair_number,
                subject_name,
                lecture_type,
                audience,
                fio,
                teacher,
                group_name,
                week_type,
                subgroup,
                institute,
                course,
                direction,
                department,
                is_external,
                is_remote,
                num_subgroups
            FROM timetable_cleaned 
            {where_clause}
            ORDER BY {sort_by} {sort_order}
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
        
        # Запрос для подсчета общего количества (с учетом фильтров)
        count_query = f"SELECT COUNT(*) as total FROM timetable_cleaned {where_clause}"
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
    """Очищает базу данных"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("TRUNCATE TABLE timetable_cleaned")
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'message': 'Database cleared successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/db/records/<int:record_id>', methods=['PUT'])
def update_record(record_id):
    """Обновляет запись в базе данных"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Получаем список разрешенных полей для обновления
        allowed_fields = [
            'day_of_week', 'pair_number', 'subject_name', 'lecture_type',
            'audience', 'fio', 'teacher', 'group_name', 'week_type',
            'subgroup', 'institute', 'course', 'direction', 'department',
            'is_external', 'is_remote', 'num_subgroups'
        ]
        
        # Формируем список полей для обновления
        update_fields = []
        update_values = []
        
        for field in allowed_fields:
            if field in data:
                update_fields.append(f"{field} = %s")
                # Обрабатываем пустые строки как NULL
                value = data[field]
                if value == '' or value is None:
                    update_values.append(None)
                elif field in ['pair_number', 'subgroup', 'num_subgroups']:
                    # Для числовых полей пытаемся преобразовать
                    try:
                        update_values.append(int(value) if value is not None else None)
                    except (ValueError, TypeError):
                        update_values.append(None)
                elif field in ['is_external', 'is_remote']:
                    # Для булевых полей
                    update_values.append(bool(value) if value is not None else None)
                else:
                    # Для строковых полей
                    update_values.append(str(value) if value is not None else None)
        
        if not update_fields:
            return jsonify({'error': 'No fields to update'}), 400
        
        # Добавляем ID в конец для WHERE условия
        update_values.append(record_id)
        
        # Формируем SQL запрос
        update_query = f"""
            UPDATE timetable_cleaned 
            SET {', '.join(update_fields)}
            WHERE id = %s
        """
        
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(update_query, update_values)
        rows_affected = cursor.rowcount
        conn.commit()
        
        if rows_affected == 0:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Record not found'}), 404
        
        # Получаем обновленную запись
        cursor.execute("SELECT * FROM timetable_cleaned WHERE id = %s", (record_id,))
        updated_record = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if updated_record:
            # Преобразуем в словарь
            record_dict = dict(updated_record)
            return jsonify({'message': 'Record updated successfully', 'record': record_dict})
        else:
            return jsonify({'error': 'Record not found'}), 404
            
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error updating record {record_id}: {error_trace}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/db/records', methods=['POST'])
def create_record():
    """Создает новую запись в базе данных"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Получаем параметры позиционирования (если есть)
        reference_id = data.get('_reference_id')
        position = data.get('_position')  # 'before' or 'after'
        
        # Удаляем служебные поля из данных
        record_data = {k: v for k, v in data.items() if not k.startswith('_')}
        
        # Получаем список разрешенных полей
        allowed_fields = [
            'day_of_week', 'pair_number', 'subject_name', 'lecture_type',
            'audience', 'fio', 'teacher', 'group_name', 'week_type',
            'subgroup', 'institute', 'course', 'direction', 'department',
            'is_external', 'is_remote', 'num_subgroups'
        ]
        
        # Формируем списки полей и значений для INSERT
        insert_fields = []
        insert_values = []
        placeholders = []
        
        for field in allowed_fields:
            if field in record_data:
                insert_fields.append(field)
                placeholders.append('%s')
                value = record_data[field]
                
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
        
        # Создаем запись
        insert_query = f"""
            INSERT INTO timetable_cleaned ({', '.join(insert_fields)})
            VALUES ({', '.join(placeholders)})
            RETURNING *
        """
        cursor.execute(insert_query, insert_values)
        new_record = cursor.fetchone()
        new_id = new_record['id']
        
        # Если указана позиция относительно другой записи, используем специальную логику
        if reference_id and position:
            # Получаем ID целевой записи
            cursor.execute("SELECT id FROM timetable_cleaned WHERE id = %s", (reference_id,))
            ref_record = cursor.fetchone()
            
            if not ref_record:
                cursor.close()
                conn.close()
                return jsonify({'error': 'Reference record not found'}), 404
            
            ref_id = ref_record['id']
            
            # Если нужно создать "выше", используем временный большой ID для перестановки
            if position == 'before':
                # Находим максимальный ID в таблице
                cursor.execute("SELECT MAX(id) as max_id FROM timetable_cleaned")
                max_id_result = cursor.fetchone()
                max_id = max_id_result['max_id'] if max_id_result and max_id_result['max_id'] else new_id
                temp_id = max_id + 1000000  # Временный очень большой ID
                
                # Переставляем ID: новая запись -> temp, целевая -> новая, temp -> целевая
                cursor.execute("UPDATE timetable_cleaned SET id = %s WHERE id = %s", (temp_id, new_id))
                cursor.execute("UPDATE timetable_cleaned SET id = %s WHERE id = %s", (new_id, ref_id))
                cursor.execute("UPDATE timetable_cleaned SET id = %s WHERE id = %s", (ref_id, temp_id))
                final_id = new_id
            else:
                # Для "after" запись уже создана с большим ID, ничего не делаем
                final_id = new_id
        else:
            final_id = new_id
        
        conn.commit()
        
        # Получаем финальную версию записи
        cursor.execute("SELECT * FROM timetable_cleaned WHERE id = %s", (final_id,))
        final_record = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if final_record:
            record_dict = dict(final_record)
            return jsonify({'message': 'Record created successfully', 'record': record_dict}), 201
        else:
            return jsonify({'error': 'Failed to create record'}), 500
            
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error creating record: {error_trace}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/db/records/<int:record_id>', methods=['DELETE'])
def delete_record(record_id):
    """Удаляет запись из базы данных"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Проверяем существование записи
        cursor.execute("SELECT id FROM timetable_cleaned WHERE id = %s", (record_id,))
        record = cursor.fetchone()
        
        if not record:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Record not found'}), 404
        
        # Удаляем запись
        cursor.execute("DELETE FROM timetable_cleaned WHERE id = %s", (record_id,))
        rows_affected = cursor.rowcount
        conn.commit()
        
        cursor.close()
        conn.close()
        
        if rows_affected > 0:
            return jsonify({'message': 'Record deleted successfully'}), 200
        else:
            return jsonify({'error': 'Failed to delete record'}), 500
            
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error deleting record {record_id}: {error_trace}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')
