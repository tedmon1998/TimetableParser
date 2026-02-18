# -*- coding: utf-8 -*-
"""
Парсинг расписания СПО (колледж) из .xlsx в папке spo/spo → JSON в spo/output.

Принцип как у основного расписания:
- Курс — в первой строке.
- Справа — день недели, по колонкам подгруппы.
- В каждой колонке блок из 3 строк: преподаватель, дисциплина, аудитория.
- Числителей/знаменателей нет (week_type = "обе недели").
- Парсинг останавливается при первом полностью пустом блоке (не идём до конца листа).
"""
import json
import re
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

try:
    from openpyxl import load_workbook
    from openpyxl.utils import get_column_letter
except ImportError:
    print("Установите openpyxl: pip install openpyxl")
    sys.exit(1)

SPO_DIR = Path(__file__).resolve().parent / "spo"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

# Жёсткий предел: не парсить бесконечно (макс. блоков по 3 строки)
MAX_BLOCKS = 80
MAX_COL = 20

DAY_ALIASES = {
    'понедельник': 'понедельник', 'пон': 'понедельник', 'пн': 'понедельник',
    'вторник': 'вторник', 'вт': 'вторник',
    'среда': 'среда', 'ср': 'среда',
    'четверг': 'четверг', 'чт': 'четверг',
    'пятница': 'пятница', 'пт': 'пятница',
    'суббота': 'суббота', 'сб': 'суббота',
}
DATE_PATTERN = re.compile(r'(\d{1,2})\.(\d{1,2})\.(\d{4})')
TIME_PATTERN = re.compile(r'(\d{1,2})[.:](\d{2})\s*[-–]\s*(\d{1,2})[.:](\d{2})')
GROUP_PATTERN = re.compile(r'(\d{3}-\d{2}(?:-\d+)?)\s*(п\d+)?', re.IGNORECASE)
BRIGADE_PATTERN = re.compile(r'бригада\s*(\d+)', re.IGNORECASE)
COURSE_PATTERN = re.compile(r'(\d+)\s*курс', re.IGNORECASE)


def _cell_value(ws, row_idx: int, col_idx: int) -> str | None:
    """Значение ячейки с учётом объединённых. Пустые и ошибки Excel → None."""
    if row_idx < 1 or col_idx < 1:
        return None
    try:
        cell = ws.cell(row=row_idx, column=col_idx)
        v = cell.value
        if v is not None:
            s = str(v).strip()
            if s and s.upper() not in ('#REF!', '#VALUE!', '#DIV/0!', '#N/A', '########'):
                return s
        for rng in ws.merged_cells.ranges:
            if cell.coordinate in rng:
                top = ws.cell(rng.min_row, rng.min_col)
                if top.value:
                    s = str(top.value).strip()
                    if s:
                        return s
        return None
    except Exception:
        return None


def _parse_date(s: str) -> str | None:
    """dd.mm.yyyy → строка даты или None."""
    if not s:
        return None
    m = DATE_PATTERN.search(s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= d <= 31 and 1 <= mo <= 12:
            return f'{d:02d}.{mo:02d}.{y}'
    return None


def _parse_time(s: str) -> tuple[str, str, str] | None:
    """Строка времени 8.00-9.35 → (pair_time, time_start, time_end) или None."""
    if not s:
        return None
    m = TIME_PATTERN.search(s)
    if m:
        h1, m1, h2, m2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        return (
            f'{h1}.{m1:02d}-{h2}.{m2:02d}',
            f'{h1:02d}:{m1:02d}',
            f'{h2:02d}:{m2:02d}'
        )
    return None


def _normalize_day(s: str) -> str:
    if not s:
        return ''
    k = s.strip().lower()
    return DAY_ALIASES.get(k, k) if k in DAY_ALIASES else k


def _find_structure(ws) -> dict | None:
    """
    Определяет структуру листа СПО:
    - курс (строка 1),
    - столбец времени, столбец дня недели,
    - data_columns: список (col_idx, group_name, subgroup).
    Возвращает dict или None, если структура не найдена.
    """
    course = ''
    time_col: int | None = None
    day_col: int | None = None
    data_columns: list[tuple[int, str, int]] = []
    header_end_row = 0
    default_date: str | None = None

    max_scan_row = min(15, ws.max_row)
    max_scan_col = min(ws.max_column, MAX_COL)

    # Курс — первая строка
    for c in range(1, max_scan_col + 1):
        v = _cell_value(ws, 1, c)
        if v:
            m = COURSE_PATTERN.search(v)
            if m:
                course = f"{m.group(1)} курс"
                break

    # Строки 2–4: группы/подгруппы, время, день
    group_by_col: dict[int, str] = {}
    brigade_by_col: dict[int, int] = {}
    current_group: str | None = None

    for row_idx in range(2, max_scan_row + 1):
        for c in range(1, max_scan_col + 1):
            v = _cell_value(ws, row_idx, c)
            if not v:
                if row_idx == 2 and current_group:
                    group_by_col[c] = current_group
                continue
            dd = _parse_date(v)
            if dd:
                default_date = dd
            if _parse_time(v) and time_col is None:
                time_col = c
            dn = _normalize_day(v)
            if dn and (dn in list(DAY_ALIASES.values()) or 'понедельник' in dn or 'вторник' in dn):
                day_col = c
            gm = GROUP_PATTERN.search(v)
            bm = BRIGADE_PATTERN.search(v)
            if gm:
                gr = gm.group(1)
                suf = (gm.group(2) or '').strip()
                current_group = f"{gr} {suf}" if suf else gr
                group_by_col[c] = current_group
                header_end_row = max(header_end_row, row_idx)
            if bm:
                brigade_by_col[c] = int(bm.group(1))
                header_end_row = max(header_end_row, row_idx)

    # Сопоставление: колонка с бригадой → группа (своя или слева)
    for c in sorted(brigade_by_col.keys()):
        gn = group_by_col.get(c)
        if not gn and c > 1:
            gn = group_by_col.get(c - 1)
        if not gn:
            for prev in range(c - 1, 0, -1):
                if prev in group_by_col:
                    gn = group_by_col[prev]
                    break
        if gn:
            data_columns.append((c, gn, brigade_by_col[c]))

    if not data_columns:
        for r in range(1, min(11, max_scan_row + 1)):
            for c in range(1, max_scan_col + 1):
                v = _cell_value(ws, r, c)
                if not v:
                    continue
                gm = GROUP_PATTERN.search(v)
                bm = BRIGADE_PATTERN.search(v)
                if gm and bm:
                    gr = gm.group(1) + (' ' + (gm.group(2) or '').strip())
                    data_columns.append((c, gr, int(bm.group(1))))
                    header_end_row = max(header_end_row, r)
                elif gm:
                    gr = gm.group(1) + (' ' + (gm.group(2) or '').strip())
                    data_columns.append((c, gr, 1))
                    header_end_row = max(header_end_row, r)

    if not data_columns:
        return None

    data_start_row = header_end_row + 1 if header_end_row else 4
    return {
        'course': course or '',
        'time_col': time_col,
        'day_col': day_col,
        'data_columns': sorted(data_columns, key=lambda x: x[0]),
        'data_start_row': data_start_row,
        'date_value': default_date,
    }


def _parse_sheet(ws, sheet_name: str, source_file: str, file_path: str = '') -> list[dict]:
    """
    Парсит один лист. Идёт блоками по 3 строки (преподаватель, дисциплина, аудитория).
    Останавливается при первом полностью пустом блоке или по MAX_BLOCKS.
    """
    struct = _find_structure(ws)
    if not struct or not struct['data_columns']:
        return []

    course = struct['course']
    time_col = struct['time_col']
    day_col = struct['day_col']
    data_cols = struct['data_columns']
    start_row = struct['data_start_row']
    default_date = struct['date_value']

    records: list[dict] = []
    current_date = default_date
    current_day = ''
    pair_num = 0
    pair_time = time_start = time_end = ''

    # Не идём дальше MAX_BLOCKS блоков (защита от бесконечного парсинга)
    max_row = min(ws.max_row, start_row + 3 * MAX_BLOCKS - 1)
    row = start_row
    blocks_done = 0

    def _str(val) -> str:
        if val is None:
            return ''
        s = str(val).strip()
        if not s or (s.startswith('#') and s.upper() in ('#REF!', '#VALUE!', '#DIV/0!', '#N/A')):
            return ''
        return s

    while row <= max_row - 2 and blocks_done < MAX_BLOCKS:
        blocks_done += 1
        min_c = min(c for c, _, _ in data_cols)
        max_c = max(c for c, _, _ in data_cols)
        print(f"SPO: {source_file} | лист «{sheet_name}» | {get_column_letter(min_c)}{row}:{get_column_letter(max_c)}{row + 2}", file=sys.stderr, flush=True)

        time_val = _cell_value(ws, row, time_col) if time_col else None
        day_val = _cell_value(ws, row, day_col) if day_col else None

        for c in range(1, min(ws.max_column, MAX_COL) + 1):
            v = _cell_value(ws, row, c)
            if v:
                d = _parse_date(v)
                if d:
                    current_date = d
                    break
        if day_val and _normalize_day(day_val):
            current_day = _normalize_day(day_val)

        time_info = _parse_time(time_val) if time_val else None
        if time_info:
            pair_num += 1
            pair_time, time_start, time_end = time_info
        else:
            pair_time = time_start = time_end = ''

        block_has_data = False
        for col_idx, group_name, subgroup in data_cols:
            teacher = _str(_cell_value(ws, row, col_idx))
            discipline = _str(_cell_value(ws, row + 1, col_idx))
            audience = _str(_cell_value(ws, row + 2, col_idx))
            if not teacher and not discipline and not audience:
                continue
            block_has_data = True
            records.append({
                'date': current_date,
                'day_of_week': current_day,
                'pair_number': pair_num if time_info else None,
                'pair_time': pair_time,
                'time_start': time_start,
                'time_end': time_end,
                'subject_name': discipline,
                'discipline_original': discipline,
                'audience': audience,
                'group_name': group_name.strip(),
                'subgroup': subgroup,
                'week_type': 'обе недели',
                'fio': teacher,
                'course': course,
                'institute': '',
                'source_file': source_file,
                'sheet_name': sheet_name,
            })

        if not block_has_data:
            break
        row += 3

    return records


def parse_file(path: Path) -> list[dict]:
    """Парсит один .xlsx: все листы, один проход по каждому."""
    wb = load_workbook(path, data_only=True)
    all_records: list[dict] = []
    file_path_str = str(path.resolve())
    print(f"SPO: парсинг файла «{path.name}»", file=sys.stderr, flush=True)

    for name in wb.sheetnames:
        ws = wb[name]
        try:
            recs = _parse_sheet(ws, name, path.name, file_path=file_path_str)
            all_records.extend(recs)
        except Exception as e:
            print(f"  Ошибка на листе «{name}»: {e}", file=sys.stderr)
    return all_records


def main() -> None:
    print("SPO: старт парсера", file=sys.stderr, flush=True)
    SPO_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    input_dir = SPO_DIR / "spo"
    input_dir.mkdir(parents=True, exist_ok=True)
    files = list(input_dir.glob("*.xlsx")) + list(input_dir.glob("*.xls"))
    if not files:
        files = list(SPO_DIR.glob("*.xlsx")) + list(SPO_DIR.glob("*.xls"))
    if not files:
        print("В папке spo (или spo/spo) нет файлов .xlsx или .xls.", file=sys.stderr)
        return

    all_records: list[dict] = []
    for path in sorted(files):
        try:
            recs = parse_file(path)
            all_records.extend(recs)
            print(f"Обработан: {path.name} → {len(recs)} записей", file=sys.stderr)
        except Exception as e:
            print(f"Ошибка при обработке {path}: {e}", file=sys.stderr)
            raise

    out_path = OUTPUT_DIR / "_all.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)
    print(f"Всего записей: {len(all_records)} → {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
