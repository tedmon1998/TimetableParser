#!/usr/bin/env python3
"""
Скрипт переводит файл в кодировку UTF-8.
Путь к файлу задаётся аргументом командной строки или в коде.

Для JSON дополнительно перезаписывает содержимое с реальными символами
(без \\uXXXX), чтобы кириллица отображалась нормально.
"""

import sys
import json
import os

# Популярные кодировки для автоопределения (порядок важен)
ENCODINGS = ['utf-8', 'utf-8-sig', 'cp1251', 'cp866', 'latin-1']


def detect_and_read(path: str) -> tuple[str, str]:
    """Читает файл, пробуя разные кодировки. Возвращает (текст, использованная кодировка)."""
    with open(path, 'rb') as f:
        raw = f.read()
    for enc in ENCODINGS:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise ValueError(f'Не удалось декодировать файл ни одной из кодировок: {ENCODINGS}')


def convert_file_to_utf8(file_path: str, in_place: bool = True, out_path: str | None = None) -> str:
    """
    Переводит файл в UTF-8.
    :param file_path: путь к исходному файлу
    :param in_place: если True, перезаписывает тот же файл
    :param out_path: если задан, результат пишется сюда (иначе перезапись file_path при in_place=True)
    :return: путь к сохранённому файлу
    """
    path = os.path.abspath(file_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f'Файл не найден: {path}')

    ext = os.path.splitext(path)[1].lower()
    save_path = out_path if out_path else path

    if ext == '.json':
        # JSON: читаем как текст (любая кодировка), парсим, пишем UTF-8 с нормальными символами
        text, used_enc = detect_and_read(path)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f'Ошибка разбора JSON: {e}') from e
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f'JSON: перезаписан в UTF-8 (кириллица без \\uXXXX), исходная кодировка: {used_enc}')
    else:
        # Обычный текст: читаем, пишем UTF-8
        text, used_enc = detect_and_read(path)
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f'Текст: перезаписан в UTF-8, исходная кодировка: {used_enc}')

    return save_path


def main():
    if len(sys.argv) < 2:
        print('Использование: python to_utf8.py <путь_к_файлу> [выходной_файл]')
        print('Пример: python to_utf8.py info/teacher_all.json')
        print('Пример с другим выходом: python to_utf8.py file.txt file_utf8.txt')
        sys.exit(1)

    file_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        result = convert_file_to_utf8(file_path, out_path=out_path)
        print(f'Готово: {result}')
    except Exception as e:
        print(f'Ошибка: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
