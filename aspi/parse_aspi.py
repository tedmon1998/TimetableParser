# -*- coding: utf-8 -*-
"""
Парсинг расписания из .docx в папке aspi → JSON в output/aspi.
Поля: группа, научная_специальность, год_обучения, день_недели, пара, дисциплина, фио, предмет, неделя.
Из блока над таблицей: «Группа:», «Научная специальность:», «N год обучения».
"""
import json
import re
import sys
from pathlib import Path
from typing import Optional

# для корректного вывода в консоль на Windows
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

try:
    from docx import Document
    from docx.oxml.ns import qn
except ImportError:
    print("Установите python-docx: pip install python-docx")
    sys.exit(1)


ASPI_DIR = Path(__file__).resolve().parent / "aspi"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

# Заголовки таблицы расписания (для определения столбцов)
HEADER_DAY = "день недели"
HEADER_PARA = "пара"
HEADER_DISC = "дисциплина"
HEADER_TEACHER = "фамилия"

# Ключевые слова для числитель/знаменатель
NUMERATOR = "числитель"
DENOMINATOR = "знаменатель"


def cell_has_diagonal_border(cell, cell_text: str = "") -> Optional[str]:
    """
    Проверяет, есть ли в ячейке диагональная граница (нарисованная линия в Word).
    Возвращает "знаменатель" если текст под линией, "числитель" если над линией, иначе None.
    В OOXML: w:tcPr/w:tcBorders/w:tl2br или w:tr2bl.
    Если vAlign не задан — смотрим по тексту: много пробелов/переносов в начале = текст внизу (знаменатель).
    """
    tc = cell._tc
    tc_pr = tc.find(qn("w:tcPr"))
    if tc_pr is None:
        return None
    borders = tc_pr.find(qn("w:tcBorders"))
    if borders is None:
        return None
    if borders.find(qn("w:tl2br")) is not None or borders.find(qn("w:tr2bl")) is not None:
        v_align = tc_pr.find(qn("w:vAlign"))
        if v_align is not None:
            val = (v_align.get(qn("w:val")) or "").lower()
            if val in ("top", "centertop"):
                return "числитель"
            if val in ("bottom", "centerbottom"):
                return "знаменатель"
        # Нет vAlign: текст вверху ячейки = мало ведущих пробелов/переносов → числитель
        # Текст внизу = много ведущих пробелов/переносов → знаменатель
        raw = cell_text or (cell.text or "")
        stripped = raw.lstrip()
        if not stripped:
            return "знаменатель"
        leading = raw[: len(raw) - len(stripped)]
        # Если в начале много пробелов/переносов — контент «внизу» ячейки
        if len(leading) > 8 or "\n" in leading:
            return "знаменатель"
        return "числитель"
    return None


def normalize_week_cell(text: str, cell_diagonal: Optional[str] = None) -> list[dict]:
    """
    Разбирает ячейку с дисциплиной.
    cell_diagonal: если в ячейке нарисована диагональ в Word — "числитель" или "знаменатель".
    Возвращает список записей: [{"предмет": str, "дисциплина": str, "неделя": "числитель"|"знаменатель"|"обе недели"}].
    - Если в ячейке диагональная линия (из XML): текст под линией — знаменатель, над — числитель.
    - Если в тексте символ "/": над чертой — числитель, под чертой — знаменатель.
    - Если в тексте слово "числитель"/"знаменатель" — соответственно.
    - Иначе — обе недели.
    """
    text = (text or "").strip()
    if not text:
        return [{"предмет": "", "дисциплина": "", "неделя": cell_diagonal or "обе недели"}]

    # Диагональ в самой ячейке (рисованная линия в Word)
    if cell_diagonal is not None:
        clean = " ".join(text.split())
        return [{"предмет": clean, "дисциплина": clean, "неделя": cell_diagonal}]

    # Явные маркеры в тексте
    text_lower = text.lower()
    if NUMERATOR in text_lower and DENOMINATOR not in text_lower:
        clean = re.sub(r"\s*числитель\s*\*?\s*", " ", text, flags=re.I).strip()
        return [{"предмет": clean, "дисциплина": clean, "неделя": "числитель"}]
    if DENOMINATOR in text_lower and NUMERATOR not in text_lower:
        clean = re.sub(r"\s*знаменатель\s*\*?\s*", " ", text, flags=re.I).strip()
        return [{"предмет": clean, "дисциплина": clean, "неделя": "знаменатель"}]

    # Разделитель только наклонная черта "/" (перенос строки — просто форматирование)
    parts = re.split(r"\s*/\s*", text)
    parts = [p.strip().replace("\n", " ") for p in parts if p.strip()]

    if len(parts) >= 2:
        result = []
        result.append({"предмет": parts[0], "дисциплина": parts[0], "неделя": "числитель"})
        result.append({"предмет": parts[1], "дисциплина": parts[1], "неделя": "знаменатель"})
        return result

    clean = re.sub(r"\s*числитель\s*\*?\s*|\s*знаменатель\s*\*?\s*", " ", text, flags=re.I).strip()
    clean = " ".join(clean.split())
    return [{"предмет": clean, "дисциплина": clean, "неделя": "обе недели"}]


def extract_day_name(cell_text: str) -> str:
    """Из ячейки 'ДЕНЬ\\nс 02.02 по ...' берём только название дня."""
    if not cell_text:
        return ""
    first_line = (cell_text.strip().split("\n")[0]).strip()
    return first_line


def is_header_row(cells: list) -> bool:
    if len(cells) < 2:
        return False
    first = (cells[0].text or "").strip().lower()
    second = (cells[1].text or "").strip().lower()
    return HEADER_DAY in first or HEADER_PARA in first or HEADER_PARA in second or "пара" in second


# Паттерны для извлечения из блока над таблицей
GROUP_PATTERN = re.compile(r"группа\s*:\s*(.+)", re.IGNORECASE)
SPECIALTY_PATTERN = re.compile(r"научная\s+специальность\s*:?\s*(.+)", re.IGNORECASE)
YEAR_PATTERN = re.compile(r"(\d+)\s*год\s+обучения", re.IGNORECASE)


def extract_group_from_paragraph(text: str) -> Optional[str]:
    """Из строки вида 'Группа: а606-31' возвращает 'а606-31' или None."""
    if not text:
        return None
    m = GROUP_PATTERN.search(text.strip())
    return m.group(1).strip() if m else None


def extract_specialty_from_paragraph(text: str) -> Optional[str]:
    """Из строки вида 'Научная специальность: 1.1.8. Механика...' возвращает текст после префикса."""
    if not text:
        return None
    m = SPECIALTY_PATTERN.search(text.strip())
    return m.group(1).strip() if m else None


def extract_year_from_paragraph(text: str) -> Optional[str]:
    """Из строки вида '1 год обучения' возвращает '1' или None."""
    if not text:
        return None
    m = YEAR_PATTERN.search(text.strip())
    return m.group(1) if m else None


def _parse_table_rows(
    table,
    group: str,
    scientific_specialty: str = "",
    year_of_study: str = "",
) -> list[dict]:
    """Парсит одну таблицу расписания; все строки получают группу, специальность и год обучения."""
    rows_out = []
    for row in table.rows:
        cells = [c.text or "" for c in row.cells]
        if len(cells) < 4:
            continue
        if is_header_row(row.cells):
            continue

        day_cell = cells[0].strip()
        para_cell = cells[1].strip()
        disc_cell = cells[2].strip()
        fio_cell = cells[3].strip()

        day = extract_day_name(day_cell)
        para = para_cell.split("\n")[0].strip()
        if not para:
            continue

        fio = " ".join(fio_cell.split())
        disc_cell_obj = row.cells[2]
        disc_cell_raw = disc_cell_obj.text or ""
        cell_diagonal = cell_has_diagonal_border(disc_cell_obj, disc_cell_raw)

        for item in normalize_week_cell(disc_cell, cell_diagonal):
            rows_out.append({
                "группа": group,
                "научная_специальность": scientific_specialty,
                "год_обучения": year_of_study,
                "день_недели": day,
                "пара": para,
                "дисциплина": item["дисциплина"],
                "фио": fio,
                "предмет": item["предмет"],
                "неделя": item["неделя"],
            })
    return rows_out


def _block_above_table(
    body_children: list,
    table_idx: int,
    elem_to_para: dict,
    elem_to_table: dict,
) -> dict:
    """
    Над таблицей может быть блок с «Группа:», «Научная специальность:», «N год обучения».
    Собираем все три только из абзацев между предыдущей таблицей и этой.
    """
    out = {"группа": "", "научная_специальность": "", "год_обучения": ""}
    for i in range(table_idx - 1, -1, -1):
        child = body_children[i]
        cid = id(child)
        if cid in elem_to_table:
            break
        if cid not in elem_to_para:
            continue
        text = elem_to_para[cid].text or ""
        if not out["группа"]:
            g = extract_group_from_paragraph(text)
            if g is not None:
                out["группа"] = g
        if not out["научная_специальность"]:
            s = extract_specialty_from_paragraph(text)
            if s is not None:
                out["научная_специальность"] = s
        if not out["год_обучения"]:
            y = extract_year_from_paragraph(text)
            if y is not None:
                out["год_обучения"] = y
    return out


def parse_docx(path: Path) -> list[dict]:
    """
    Парсит .docx: над таблицей блок с «Группа:», «Научная специальность:», «N год обучения».
    Все три поля берутся только из абзацев между предыдущей таблицей и текущей.
    """
    doc = Document(path)
    body = doc.element.body
    body_children = list(body)
    elem_to_para = {id(p._element): p for p in doc.paragraphs}
    elem_to_table = {id(t._tbl): t for t in doc.tables}

    rows_out = []
    for idx, child in enumerate(body_children):
        cid = id(child)
        if cid not in elem_to_table:
            continue
        table = elem_to_table[cid]
        if len(table.rows) < 2:
            continue
        block = _block_above_table(body_children, idx, elem_to_para, elem_to_table)
        rows_out.extend(_parse_table_rows(
            table,
            block["группа"],
            block["научная_специальность"],
            block["год_обучения"],
        ))

    return rows_out


def main():
    ASPI_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    files = list(ASPI_DIR.glob("*.docx"))
    if not files:
        print("В папке aspi нет .docx файлов.")
        return

    all_results = {}
    for path in sorted(files):
        try:
            data = parse_docx(path)
            name = path.stem
            all_results[name] = data
            out_path = OUTPUT_DIR / f"{name}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"Обработан: {path.name} → {out_path} ({len(data)} записей)")
        except Exception as e:
            print(f"Ошибка при обработке {path}: {e}", file=sys.stderr)
            raise

    # Сводный файл по всем файлам (опционально)
    summary_path = OUTPUT_DIR / "_all.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"Сводный файл: {summary_path}")


if __name__ == "__main__":
    main()
