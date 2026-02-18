# -*- coding: utf-8 -*-
"""
Парсинг расписания СПО (колледж) из .xlsx в папке spo/spo → Excel в spo/output.

Формат (по примеру на скриншоте):
- Вверху по горизонтали может быть несколько блоков (1 курс / 2 курс / 3 курс).
- Для каждого блока: колонки = подгруппы (бригада 1/2/3), строки идут «пакетами» по 3:
  преподаватель / дисциплина / аудитория.
- Начало пары определяется по ячейке со временем (например 8.00-9.35) в «столбце времени» блока.
- День недели обычно в соседнем столбце (merged, вертикальная надпись).
- Числитель/знаменатель: первые встретившиеся дни недели = «числитель», вторые такие же дни = «знаменатель»
  (второй понедельник, второй вторник и т.д.).

Защита от бесконечного парсинга:
- Парсим только строки, где распознано время пары.
- Есть лимит на количество распознанных пар в блоке (MAX_PAIRS_PER_BLOCK).
"""
import json
import re
import sys
from pathlib import Path

_reconf = getattr(sys.stdout, "reconfigure", None)
if callable(_reconf) and sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        _reconf(encoding='utf-8')
    except Exception:
        pass

try:
    from openpyxl import load_workbook, Workbook
    from openpyxl.utils import get_column_letter
except ImportError:
    print("Установите openpyxl: pip install openpyxl")
    sys.exit(1)

SPO_DIR = Path(__file__).resolve().parent / "spo"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

# Лимиты (защита от бесконечного парсинга)
MAX_COL = 200
SCAN_HEADER_MAX_ROW = 35
SCAN_BODY_MAX_ROW = 250
MAX_PAIRS_PER_BLOCK = 220

# Константы для СПО
SPO_INSTITUTE = "Институт среднего медицинского образования"

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

_MERGED_RANGES_CACHE: dict[int, list[tuple[int, int, int, int, str | None]]] = {}


def _cell_value(ws, row_idx: int, col_idx: int) -> str | None:
    """Значение ячейки с учётом объединённых. Пустые и ошибки Excel → None."""
    if row_idx < 1 or col_idx < 1:
        return None
    try:
        cache_key = id(ws)
        ranges = _MERGED_RANGES_CACHE.get(cache_key)
        if ranges is None:
            ranges = []
            try:
                for rng in ws.merged_cells.ranges:
                    top = ws.cell(rng.min_row, rng.min_col).value
                    top_s = str(top).strip() if top is not None and str(top).strip() else None
                    ranges.append((rng.min_row, rng.max_row, rng.min_col, rng.max_col, top_s))
            except Exception:
                ranges = []
            _MERGED_RANGES_CACHE[cache_key] = ranges

        cell = ws.cell(row=row_idx, column=col_idx)
        v = cell.value
        if v is not None:
            s = str(v).strip()
            if s and s.upper() not in ('#REF!', '#VALUE!', '#DIV/0!', '#N/A', '########'):
                return s
        for r1, r2, c1, c2, top_s in ranges:
            if top_s and r1 <= row_idx <= r2 and c1 <= col_idx <= c2:
                return top_s
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


def _clean_group_name(group_name: str) -> str:
    """Убирает из названия группы суффиксы подгрупп: 'п 1', 'П 1', 'п 2', 'п1', 'П1' и т.д."""
    if not group_name:
        return ''
    # Убираем паттерны типа "п 1", "П 1", "п 2", "п1", "П1", "п2" в конце строки
    cleaned = re.sub(r'\s*[пП]\s*\d+\s*$', '', group_name.strip())
    return cleaned.strip()


def _is_day_value(v: str | None) -> bool:
    if not v:
        return False
    dn = _normalize_day(v)
    return dn in DAY_ALIASES.values()


def _find_course_near_col(ws, col_idx: int, max_col: int) -> str:
    # Ищем «N курс» в строке 1 в этой колонке или слева (merged часто тянется на блок)
    for c in range(col_idx, max(0, col_idx - 15), -1):
        if c < 1 or c > max_col:
            continue
        v = _cell_value(ws, 1, c)
        if not v:
            continue
        m = COURSE_PATTERN.search(v)
        if m:
            return f"{m.group(1)} курс"
    return ''


def _collect_header_columns(ws) -> list[dict]:
    """Собирает все колонки подгрупп (бригада N) по всему листу."""
    max_scan_row = min(SCAN_HEADER_MAX_ROW, ws.max_row)
    max_scan_col = min(ws.max_column, MAX_COL)

    group_by_col: dict[int, str] = {}
    brigade_by_col: dict[int, int] = {}
    current_group: str = ''

    for r in range(1, max_scan_row + 1):
        for c in range(1, max_scan_col + 1):
            v = _cell_value(ws, r, c)
            if not v:
                # Протягиваем группу вправо, если заголовок объединён
                if r in (2, 3, 4) and current_group:
                    group_by_col[c] = current_group
                continue
            gm = GROUP_PATTERN.search(v)
            if gm:
                gr = gm.group(1)
                suf = (gm.group(2) or '').strip()
                # Сохраняем с суффиксом для сопоставления с бригадами, но потом очистим
                current_group = f"{gr} {suf}" if suf else gr
                group_by_col[c] = current_group
            bm = BRIGADE_PATTERN.search(v)
            if bm:
                brigade_by_col[c] = int(bm.group(1))

    cols: list[dict] = []
    for c in sorted(brigade_by_col.keys()):
        gn = group_by_col.get(c, '')
        if not gn:
            for prev in range(c - 1, 0, -1):
                if prev in group_by_col:
                    gn = group_by_col[prev]
                    break
        course = _find_course_near_col(ws, c, max_scan_col)
        # Очищаем название группы от суффиксов подгрупп
        cleaned_group = _clean_group_name(gn.strip())
        cols.append({'col': c, 'group': cleaned_group, 'subgroup': brigade_by_col[c], 'course': course})
    return cols


def _split_into_blocks(cols: list[dict]) -> list[dict]:
    """Группирует колонки подгрупп по блокам (1 курс / 2 курс / 3 курс и т.п.)."""
    if not cols:
        return []
    blocks: list[dict] = []
    current: list[dict] = []

    for item in cols:
        if not current:
            current = [item]
            continue
        prev = current[-1]
        gap = item['col'] - prev['col']
        course_changed = bool(item['course']) and bool(prev.get('course')) and item['course'] != prev.get('course')
        if gap > 5 or course_changed:
            blocks.append({'cols': current})
            current = [item]
        else:
            current.append(item)
    if current:
        blocks.append({'cols': current})

    for b in blocks:
        bcols = b['cols']
        b['min_col'] = min(x['col'] for x in bcols)
        b['max_col'] = max(x['col'] for x in bcols)
        # курс: берем первый непустой в блоке
        b['course'] = next((x['course'] for x in bcols if x.get('course')), '')
        b['data_columns'] = [(x['col'], x['group'], x['subgroup']) for x in bcols]
    return blocks


def _guess_time_and_day_cols(ws, min_data_col: int) -> tuple[int | None, int | None]:
    """
    Подбирает столбцы времени и дня недели для блока:
    смотрим 4 колонки слева от первой колонки данных и выбираем ту,
    где чаще всего встречается время / день недели.
    """
    max_scan_row = min(SCAN_BODY_MAX_ROW, ws.max_row)
    candidates = [c for c in range(max(1, min_data_col - 5), min_data_col) if c >= 1]
    if not candidates:
        return None, None

    time_scores: dict[int, int] = {}
    day_scores: dict[int, int] = {}
    for c in candidates:
        tcnt = 0
        dcnt = 0
        for r in range(1, max_scan_row + 1):
            v = _cell_value(ws, r, c)
            if not v:
                continue
            if _parse_time(v):
                tcnt += 1
            if _is_day_value(v):
                dcnt += 1
        time_scores[c] = tcnt
        day_scores[c] = dcnt

    time_col = max(time_scores, key=lambda k: time_scores[k]) if time_scores else None
    if time_col is not None and time_scores.get(time_col, 0) == 0:
        time_col = None
    day_col = max(day_scores, key=lambda k: day_scores[k]) if day_scores else None
    if day_col is not None and day_scores.get(day_col, 0) == 0:
        day_col = None
    if day_col == time_col:
        # пробуем второй лучший для дня
        sorted_days = sorted(day_scores.items(), key=lambda kv: kv[1], reverse=True)
        day_col = next((c for c, score in sorted_days if score > 0 and c != time_col), day_col)

    return time_col, day_col


def _find_blocks(ws) -> list[dict]:
    cols = _collect_header_columns(ws)
    blocks = _split_into_blocks(cols)
    for b in blocks:
        time_col, day_col = _guess_time_and_day_cols(ws, b['min_col'])
        b['time_col'] = time_col
        b['day_col'] = day_col
    return [b for b in blocks if b.get('data_columns')]


def _parse_sheet(ws, sheet_name: str, source_file: str, file_path: str = '') -> list[dict]:
    blocks = _find_blocks(ws)
    if not blocks:
        return []

    def _clean(val: str | None) -> str:
        if not val:
            return ''
        s = str(val).strip()
        if not s or (s.startswith('#') and s.upper() in ('#REF!', '#VALUE!', '#DIV/0!', '#N/A')):
            return ''
        return s

    records: list[dict] = []
    file_name = source_file

    for b in blocks:
        data_cols: list[tuple[int, str, int]] = b['data_columns']
        time_col: int | None = b.get('time_col')
        day_col: int | None = b.get('day_col')
        course: str = b.get('course') or ''

        if time_col is None:
            continue

        min_c = min(c for c, _, _ in data_cols)
        max_c = max(c for c, _, _ in data_cols)

        current_date: str | None = None
        current_day = ''
        current_week_type = ''
        day_counts: dict[str, int] = {}  # Счётчик дней для ЭТОГО блока (сбрасывается для каждого блока)
        pair_num = 0
        pairs_parsed = 0

        # Сканируем весь лист, но обрабатываем только строки со временем пары
        # Одна пара = 3 строки подряд (row, row+1, row+2), поэтому после обработки пропускаем следующие 2 строки
        last_processed_row = 0
        
        for row in range(1, ws.max_row - 2):
            # Пропускаем строки, которые уже обработаны как часть предыдущей пары (3 строки = одна пара)
            if row <= last_processed_row:
                continue
            
            tv = _cell_value(ws, row, time_col)
            time_info = _parse_time(tv or '')
            if not time_info:
                continue
            
            # Проверяем, что в этой строке есть данные в колонках блока (иначе это время из другого блока)
            has_data_in_block = False
            for col_idx, _, _ in data_cols:
                v1 = _cell_value(ws, row, col_idx)
                v2 = _cell_value(ws, row + 1, col_idx)
                v3 = _cell_value(ws, row + 2, col_idx)
                if v1 or v2 or v3:
                    has_data_in_block = True
                    break
            if not has_data_in_block:
                continue  # Пропускаем строки времени, которые не относятся к этому блоку
            
            pairs_parsed += 1
            if pairs_parsed > MAX_PAIRS_PER_BLOCK:
                break
            
            # Помечаем, что обработали пару из 3 строк (row, row+1, row+2)
            last_processed_row = row + 2

            # Ищем день недели: сначала в day_col, потом в соседних колонках слева
            # Проверяем также предыдущие строки (merged ячейки могут начинаться выше)
            dn = ''
            if day_col:
                for check_row in [row, row - 1, row - 2]:
                    if check_row < 1:
                        continue
                    dv = _cell_value(ws, check_row, day_col)
                    if dv:
                        dn_candidate = _normalize_day(dv)
                        if dn_candidate and dn_candidate in DAY_ALIASES.values():
                            dn = dn_candidate
                            break
                    if dn:
                        break
            
            if not dn:
                # Пробуем найти день в колонках слева от time_col (merged ячейки часто там)
                for c in range(max(1, time_col - 3), time_col):
                    for check_row in [row, row - 1, row - 2]:
                        if check_row < 1:
                            continue
                        dv = _cell_value(ws, check_row, c)
                        if dv:
                            dn_candidate = _normalize_day(dv)
                            if dn_candidate and dn_candidate in DAY_ALIASES.values():
                                dn = dn_candidate
                                break
                        if dn:
                            break
                    if dn:
                        break
            
            if dn and dn != current_day:
                # Новый день недели в этом блоке — увеличиваем счётчик
                current_day = dn
                pair_num = 0
                n = day_counts.get(dn, 0) + 1
                day_counts[dn] = n
                current_week_type = 'числитель' if n == 1 else 'знаменатель'
                print(
                    f"SPO DEBUG: блок {course or '?'} | день {dn} встречается {n}-й раз → {current_week_type}",
                    file=sys.stderr,
                    flush=True
                )

            # дата может встречаться где-то в строке (редко) — попробуем подхватить
            for c in range(max(1, min_c - 4), min(ws.max_column, max_c + 4) + 1):
                v = _cell_value(ws, row, c)
                if v:
                    dd = _parse_date(v)
                    if dd:
                        current_date = dd
                        break

            pair_num += 1
            pair_time, time_start, time_end = time_info

            # Обрабатываем все колонки подгрупп для этой пары
            # Создаём одну запись на каждую уникальную комбинацию (группа, подгруппа, ФИО, дисциплина, аудитория)
            seen_in_pair: set[tuple[str, int, str, str, str]] = set()
            
            for col_idx, group_name, subgroup in data_cols:
                # Одна пара = 3 строки подряд: row (ФИО), row+1 (дисциплина), row+2 (аудитория)
                cell_val_row = _cell_value(ws, row, col_idx)      # ФИО
                cell_val_row1 = _cell_value(ws, row + 1, col_idx)  # дисциплина
                cell_val_row2 = _cell_value(ws, row + 2, col_idx)  # аудитория
                
                teacher = ''
                discipline = ''
                audience = ''
                
                # Проверяем, может быть данные в одной ячейке как многострочный текст (в первой строке)
                if cell_val_row and '\n' in str(cell_val_row):
                    lines = [line.strip() for line in str(cell_val_row).split('\n') if line.strip()]
                    if len(lines) >= 3:
                        teacher = _clean(lines[0])
                        discipline = _clean(lines[1])
                        audience = _clean(lines[2])
                
                # Если не нашли в многострочной ячейке, читаем из трёх отдельных строк
                if not teacher and not discipline and not audience:
                    teacher = _clean(cell_val_row)
                    discipline = _clean(cell_val_row1)
                    audience = _clean(cell_val_row2)
                
                # Пропускаем, если нет данных
                if not teacher and not discipline and not audience:
                    continue
                
                # Очищаем название группы от суффиксов подгрупп
                cleaned_group_name = _clean_group_name((group_name or '').strip())
                
                # Проверяем, не создали ли мы уже запись с такими же данными для этой пары
                key = (cleaned_group_name, subgroup, teacher, discipline, audience)
                if key in seen_in_pair:
                    continue  # Пропускаем дубликат
                seen_in_pair.add(key)
                
                # Одна запись на уникальную комбинацию (как в основном расписании)
                records.append({
                    'day_of_week': current_day,
                    'pair_number': pair_num,
                    'subject_name': discipline,
                    'discipline_original': discipline,
                    'lecture_type': '',  # как в основном расписании
                    'audience': audience,
                    'group_name': cleaned_group_name,
                    'week_type': current_week_type or 'обе недели',
                    'subgroup': subgroup,
                    'institute': SPO_INSTITUTE,
                    'course': course,
                    'direction': '',  # как в основном расписании
                    'department': '',  # как в основном расписании
                    'is_external': False,  # как в основном расписании
                    'is_remote': False,  # как в основном расписании
                    'num_subgroups': None,  # как в основном расписании
                    'fio': teacher,
                })

    return records


def parse_file(path: Path) -> list[dict]:
    """Парсит один .xlsx: все листы, один проход по каждому. Пропускает скрытые листы."""
    wb = load_workbook(path, data_only=True)
    all_records: list[dict] = []
    file_path_str = str(path.resolve())

    for name in wb.sheetnames:
        ws = wb[name]
        # Пропускаем скрытые листы
        if getattr(ws, 'sheet_state', 'visible') != 'visible':
            continue
        try:
            recs = _parse_sheet(ws, name, path.name, file_path=file_path_str)
            all_records.extend(recs)
        except Exception as e:
            print(f"Ошибка на листе «{name}»: {e}", file=sys.stderr)
    return all_records


def main() -> None:
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

    # Сохраняем в Excel вместо JSON
    out_path = OUTPUT_DIR / "_all.xlsx"
    wb = Workbook()
    ws = wb.active
    if ws is not None:
        ws.title = "СПО расписание"
        
        # Заголовки (как в основном расписании - intermediate_timetable)
        headers = [
            'day_of_week', 'pair_number', 'subject_name', 'discipline_original', 'lecture_type',
            'audience', 'group_name', 'week_type', 'subgroup', 'institute', 'course',
            'direction', 'department', 'is_external', 'is_remote', 'num_subgroups', 'fio'
        ]
        ws.append(headers)
        
        # Данные
        for rec in all_records:
            row = [
                rec.get('day_of_week'),
                rec.get('pair_number'),
                rec.get('subject_name'),
                rec.get('discipline_original'),
                rec.get('lecture_type'),
                rec.get('audience'),
                rec.get('group_name'),
                rec.get('week_type'),
                rec.get('subgroup'),
                rec.get('institute'),
                rec.get('course'),
                rec.get('direction'),
                rec.get('department'),
                rec.get('is_external'),
                rec.get('is_remote'),
                rec.get('num_subgroups'),
                rec.get('fio'),
            ]
            ws.append(row)
    
    wb.save(out_path)
    print(f"Всего записей: {len(all_records)} → {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
