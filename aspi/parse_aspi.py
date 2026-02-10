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


def _cell_has_diagonal(cell) -> bool:
    """Проверяет только наличие диагонали в ячейке (без определения части по тексту)."""
    tc = cell._tc
    tc_pr = tc.find(qn("w:tcPr"))
    if tc_pr is None:
        return False
    borders = tc_pr.find(qn("w:tcBorders"))
    if borders is None:
        return False
    return borders.find(qn("w:tl2br")) is not None or borders.find(qn("w:tr2bl")) is not None


def get_diagonal_cell_parts(cell) -> Optional[tuple[str, str]]:
    """
    Если в ячейке есть диагональ, разбивает содержимое на блок «над диагональю» (числитель)
    и «под диагональю» (знаменатель). Сначала по абзацам (пустой абзац = граница). Если один
    абзац — пробуем разбить по двойному переносу \\n\\n в тексте ячейки.
    Возвращает (num_text, denom_text) или None, если диагонали нет.
    """
    if not _cell_has_diagonal(cell):
        return None

    def clean(s: str) -> str:
        return " ".join((s or "").split())

    parts_top = []
    parts_bottom = []
    after_separator = False
    for para in cell.paragraphs:
        t = (para.text or "").strip()
        if not after_separator:
            if not t:
                after_separator = True
            else:
                parts_top.append(t)
        else:
            parts_bottom.append(t)

    num_text = clean(" ".join(parts_top))
    denom_text = clean(" ".join(parts_bottom))

    # Если пустой абзац не встретился, но в ячейке есть двойной перенос — разбиваем по нему
    if not denom_text and parts_top:
        raw = (cell.text or "").replace("\r\n", "\n")
        if "\n\n" in raw:
            blocks = re.split(r"\n\s*\n", raw, maxsplit=1)
            if len(blocks) >= 2:
                num_text = clean(blocks[0])
                denom_text = clean(blocks[1])

    if not num_text and not denom_text:
        return None
    return (num_text or "", denom_text or "")


def normalize_week_cell(text: str, cell_diagonal: Optional[str] = None) -> list[dict]:
    """
    Разбирает ячейку с дисциплиной.
    cell_diagonal: если в ячейке нарисована диагональ в Word — "числитель" или "знаменатель".
    Возвращает список записей: [{"предмет": str, "дисциплина": str, "неделя": "числитель"|"знаменатель"|"обе недели"}].
    - Если в тексте символ "/" или перенос строки — две части: числитель и знаменатель (обе записи).
    - Если в тексте оба слова "числитель" и "знаменатель" — разбиваем и даём две записи.
    - Если в ячейке диагональ и одна часть текста — одна запись по cell_diagonal.
    - Если только "числитель" или только "знаменатель" — одна запись.
    - Иначе — обе недели.
    """
    text = (text or "").strip()
    if not text:
        return [{"предмет": "", "дисциплина": "", "неделя": cell_diagonal or "обе недели"}]

    def clean(s: str) -> str:
        return " ".join((s or "").split())

    # Разделитель "/" (с пробелами или без): над чертой — числитель, под чертой — знаменатель
    parts_slash = SLASH_SEP.split(text)
    parts_slash = [p.strip().replace("\n", " ") for p in parts_slash if p.strip()]
    if len(parts_slash) >= 2:
        return [
            {"предмет": parts_slash[0], "дисциплина": parts_slash[0], "неделя": "числитель"},
            {"предмет": parts_slash[1], "дисциплина": parts_slash[1], "неделя": "знаменатель"},
        ]

    # Несколько строк в ячейке без диагонали — одна дисциплина с переносами (напр. "Математическое моделирование..." на одной строке, "и комплексы", "программ", "ЭОиДОТ*" на следующих). Объединяем в одну запись "обе недели".
    # Случай «две строки таблицы = пара 7 и пара 8» обрабатывается в _parse_table_rows до вызова normalize_week_cell.
    if cell_diagonal is None:
        lines = [ln.strip() for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]
        if len(lines) >= 2:
            one = clean(" ".join(lines))
            return [{"предмет": one, "дисциплина": one, "неделя": "обе недели"}]

    # В тексте явно оба маркера "числитель" и "знаменатель" — разбиваем на две записи
    text_lower = text.lower()
    if NUMERATOR in text_lower and DENOMINATOR in text_lower:
        # Порядок: "... числитель ... знаменатель ..." или "... знаменатель ... числитель ..."
        idx_ch = text_lower.find(NUMERATOR)
        idx_zn = text_lower.find(DENOMINATOR)
        if idx_ch < idx_zn:
            part_num = text[:idx_zn].strip()
            part_den = text[idx_zn:].strip()
        else:
            part_den = text[:idx_ch].strip()
            part_num = text[idx_ch:].strip()
        part_num = re.sub(r"\s*числитель\s*\*?\s*", " ", part_num, flags=re.I).strip()
        part_den = re.sub(r"\s*знаменатель\s*\*?\s*", " ", part_den, flags=re.I).strip()
        if part_num or part_den:
            return [
                {"предмет": clean(part_num), "дисциплина": clean(part_num), "неделя": "числитель"},
                {"предмет": clean(part_den), "дисциплина": clean(part_den), "неделя": "знаменатель"},
            ]

    # Диагональ в ячейке и одна часть текста — одна запись
    if cell_diagonal is not None:
        return [{"предмет": clean(text), "дисциплина": clean(text), "неделя": cell_diagonal}]

    # Только один маркер
    if NUMERATOR in text_lower:
        c = clean(re.sub(r"\s*числитель\s*\*?\s*", " ", text, flags=re.I))
        return [{"предмет": c, "дисциплина": c, "неделя": "числитель"}]
    if DENOMINATOR in text_lower:
        c = clean(re.sub(r"\s*знаменатель\s*\*?\s*", " ", text, flags=re.I))
        return [{"предмет": c, "дисциплина": c, "неделя": "знаменатель"}]

    clean_all = re.sub(r"\s*числитель\s*\*?\s*|\s*знаменатель\s*\*?\s*", " ", text, flags=re.I).strip()
    clean_all = " ".join(clean_all.split())
    return [{"предмет": clean_all, "дисциплина": clean_all, "неделя": "обе недели"}]


def normalize_fio_cell(text: str) -> list[dict]:
    """
    Разбирает ячейку с преподавателем по аналогии с дисциплиной: числитель/знаменатель.
    Возвращает [{"фио": str, "неделя": "числитель"|"знаменатель"|"обе недели"}, ...].
    - "/" или перенос строки — две части: первая числитель, вторая знаменатель.
    - Иначе — одна запись "обе недели".
    """
    text = (text or "").strip()
    if not text:
        return [{"фио": "", "неделя": "обе недели"}]

    def clean(s: str) -> str:
        return " ".join((s or "").split())

    # Разделитель "/" (с пробелами или без): первая часть — числитель, вторая — знаменатель
    parts_slash = SLASH_SEP.split(text)
    parts_slash = [p.strip().replace("\n", " ") for p in parts_slash if p.strip()]
    if len(parts_slash) >= 2:
        return [
            {"фио": clean(parts_slash[0]), "неделя": "числитель"},
            {"фио": clean(parts_slash[1]), "неделя": "знаменатель"},
        ]

    # Две строки по переносу (числитель сверху, знаменатель снизу)
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]
    if len(lines) >= 2:
        return [
            {"фио": clean(lines[0]), "неделя": "числитель"},
            {"фио": clean(lines[1]), "неделя": "знаменатель"},
        ]

    return [{"фио": clean(text), "неделя": "обе недели"}]


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


# Разделитель "/": с пробелами или без (все варианты: " / ", "/", " /", "/ ", неразрывный пробел \xa0)
SLASH_SEP = re.compile(r"[\s\xa0]*/[\s\xa0]*")
SPECIALTY_GROUP_SEP = SLASH_SEP  # то же для специальность / гр. X
# После "гр." или "гр " — номер группы (например 5.7.1-24)
GR_PREFIX = re.compile(r"гр\.?\s*(.+)", re.IGNORECASE)
# Номер группы без префикса: 5.8.7-25, 1.2.2-25
GROUP_NUMBER_PATTERN = re.compile(r"^\s*(\d+\.\d+\.\d+-\d+)\s*$")


def split_specialty_and_group(specialty_raw: str) -> tuple[str, str]:
    """
    Если в строке научной специальности есть «специальность / гр. X.X.X-XX» (с возможными пробелами),
    возвращает (научная_специальность, группа). Иначе (specialty_raw, "").
    Примеры:
      "5.7.1. Онтология и теория познания/гр.5.7.1-24" -> ("5.7.1. Онтология и теория познания", "5.7.1-24")
      "5.2.3. Региональная и отраслевая экономика / гр. 5.2.3-25" -> ("5.2.3. Региональная и отраслевая экономика", "5.2.3-25")
    """
    if not specialty_raw or "/" not in specialty_raw:
        return (specialty_raw or "").strip(), ""
    parts = SPECIALTY_GROUP_SEP.split(specialty_raw)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) < 2:
        return (specialty_raw or "").strip(), ""
    # Последняя часть: "гр. X.X.X-XX" или просто "X.X.X-25" (напр. "образования / 5.8.7-25")
    last = parts[-1]
    m = GR_PREFIX.match(last)
    if m:
        group = m.group(1).strip()
        specialty = " ".join(parts[:-1]).strip()
        return specialty, group
    m_num = GROUP_NUMBER_PATTERN.match(last)
    if m_num:
        group = m_num.group(1).strip()
        specialty = " ".join(parts[:-1]).strip()
        return specialty, group
    return (specialty_raw or "").strip(), ""


def _parse_table_rows(
    table,
    group: str,
    scientific_specialty: str = "",
    year_of_study: str = "",
) -> list[dict]:
    """Парсит одну таблицу расписания; все строки получают группу, специальность и год обучения."""
    rows_out = []
    rows_list = list(table.rows)
    i = 0
    while i < len(rows_list):
        row = rows_list[i]
        cells = [c.text or "" for c in row.cells]
        if len(cells) < 4:
            i += 1
            continue
        if is_header_row(row.cells):
            i += 1
            continue

        day_cell = cells[0].strip()
        para_cell = cells[1].strip()
        disc_cell = cells[2].strip()
        fio_cell = cells[3].strip()

        day = extract_day_name(day_cell)
        para = para_cell.split("\n")[0].strip()
        if not para:
            i += 1
            continue

        fio_items = normalize_fio_cell(fio_cell)
        disc_cell_obj = row.cells[2]
        disc_cell_raw = disc_cell_obj.text or ""
        cell_diagonal = cell_has_diagonal_border(disc_cell_obj, disc_cell_raw)

        # Случай «объединённая ячейка по вертикали»: две строки таблицы — пара 7 и пара 8,
        # в одной ячейке дисциплины два фрагмента (первая строка = пара 7, вторая = пара 8), без диагонали.
        next_para = None
        next_disc = ""
        if i + 1 < len(rows_list):
            next_cells = [c.text or "" for c in rows_list[i + 1].cells]
            if len(next_cells) >= 3:
                next_para_cell = (next_cells[1] or "").strip()
                next_para = next_para_cell.split("\n")[0].strip()
                next_disc = (next_cells[2] or "").strip()

        lines_no_diag = [ln.strip() for ln in disc_cell.replace("\r\n", "\n").split("\n") if ln.strip()]
        next_row_shared_cell = next_para and next_para != para and (not next_disc or next_disc == disc_cell.strip())

        def clean(s: str) -> str:
            return " ".join((s or "").split())

        # Ровно две строки в ячейке и две строки таблицы (пара 7, пара 8) — два занятия: первая строка → пара 7, вторая → пара 8
        if (
            cell_diagonal is None
            and len(lines_no_diag) == 2
            and next_row_shared_cell
        ):
            for line_idx, disc_line in enumerate(lines_no_diag):
                use_para = para if line_idx == 0 else next_para
                fio = fio_items[0].get("фио") or "" if fio_items else ""
                rows_out.append({
                    "группа": group,
                    "научная_специальность": scientific_specialty,
                    "год_обучения": year_of_study,
                    "день_недели": day,
                    "пара": use_para,
                    "дисциплина": clean(disc_line),
                    "фио": fio,
                    "предмет": clean(disc_line),
                    "неделя": "обе недели",
                })
            i += 2
            continue

        # Три и более строк в ячейке при объединённой ячейке (след. строка таблицы — та же ячейка): одна дисциплина, все строки склеиваем
        if (
            cell_diagonal is None
            and len(lines_no_diag) >= 3
            and next_row_shared_cell
        ):
            one_disc = clean(" ".join(lines_no_diag))
            fio = fio_items[0].get("фио") or "" if fio_items else ""
            rows_out.append({
                "группа": group,
                "научная_специальность": scientific_specialty,
                "год_обучения": year_of_study,
                "день_недели": day,
                "пара": para,
                "дисциплина": one_disc,
                "фио": fio,
                "предмет": one_disc,
                "неделя": "обе недели",
            })
            i += 2
            continue

        # При диагонали разбиваем по абзацам (пустой абзац = граница числитель/знаменатель)
        disc_items = []
        if cell_diagonal is not None:
            diagonal_parts = get_diagonal_cell_parts(disc_cell_obj)
            if diagonal_parts is not None:
                num_text = " ".join((diagonal_parts[0] or "").split())
                denom_text = " ".join((diagonal_parts[1] or "").split())
                if num_text and denom_text:
                    disc_items = [
                        {"предмет": num_text, "дисциплина": num_text, "неделя": "числитель"},
                        {"предмет": denom_text, "дисциплина": denom_text, "неделя": "знаменатель"},
                    ]
                elif num_text:
                    disc_items = [{"предмет": num_text, "дисциплина": num_text, "неделя": "числитель"}]
                elif denom_text:
                    disc_items = [{"предмет": denom_text, "дисциплина": denom_text, "неделя": "знаменатель"}]
        if not disc_items:
            disc_items = normalize_week_cell(disc_cell, cell_diagonal)

        for item in disc_items:
            week = item.get("неделя") or "обе недели"
            fio = ""
            for fi in fio_items:
                if fi.get("неделя") == week:
                    fio = fi.get("фио") or ""
                    break
            if not fio and fio_items:
                for fi in fio_items:
                    if fi.get("неделя") == "обе недели":
                        fio = fi.get("фио") or ""
                        break
            if not fio and fio_items:
                fio = fio_items[0].get("фио") or ""

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
        i += 1
    return rows_out


def _block_above_table(
    body_children: list,
    table_idx: int,
    elem_to_para: dict,
    elem_to_table: dict,
) -> list:
    """
    Над таблицей может быть блок с «Группа:», «Научная специальность:», «N год обучения».
    Собираем все абзацы между предыдущей таблицей и этой. Несколько научных специальностей
    могут быть в одном абзаце (через \\n) или в разных абзацах подряд.
    Возвращает list[dict] — один блок или несколько (по одной паре специальность/группа).
    """
    # Собрать все абзацы над таблицей в порядке документа (сверху вниз)
    block_paras = []
    for i in range(table_idx - 1, -1, -1):
        child = body_children[i]
        cid = id(child)
        if cid in elem_to_table:
            break
        if cid not in elem_to_para:
            continue
        text = (elem_to_para[cid].text or "").strip()
        block_paras.append((i, text))
    block_paras.reverse()  # порядок документа: первый абзац блока, затем следующие

    out = {"группа": "", "научная_специальность": "", "год_обучения": ""}
    specialty_lines = []

    for i, text in block_paras:
        if not out["группа"]:
            g = extract_group_from_paragraph(text)
            if g is not None:
                out["группа"] = g
        if not out["год_обучения"]:
            y = extract_year_from_paragraph(text)
            if y is not None:
                out["год_обучения"] = y

        # Научная специальность: может быть один абзац "Научная специальность: строка1" или "строка1\nстрока2"
        # или несколько подряд абзацев: "Научная специальность: 5.7.1.../гр.5.7.1-24", "5.7.2.../гр.5.7.2-24", ...
        m = SPECIALTY_PATTERN.search(text)
        if m:
            first_line = m.group(1).strip()
            specialty_lines = [first_line]
            continue
        # Продолжение блока специальностей: строка с "/" и "гр." или номером группы X.X.X-XX, либо строка только "гр. X.X.X-XX"
        if specialty_lines and text and not GROUP_PATTERN.match(text) and not YEAR_PATTERN.search(text):
            if "/" in text and ("гр." in text.lower() or re.search(r"\d+\.\d+\.\d+-\d+", text)):
                # Напр. "образования / 5.8.7-25" или ".../гр. 5.7.1-24"
                specialty_lines.append(text)
            elif GR_PREFIX.match(text.strip()):
                # Напр. первая строка "... культура/", вторая "гр. 5.7.8-25"
                specialty_lines.append(text)

    out["научная_специальность"] = "\n".join(specialty_lines) if specialty_lines else ""

    specialty_text = (out.get("научная_специальность") or "").strip()
    # Сначала объединяем переносы в одну строку и пробуем извлечь группу (напр. "1.2.2. ... методы" + "и комплексы программ / гр. 1.2.2-25" → одна специальность и группа)
    if specialty_text and not out["группа"] and "/" in specialty_text:
        combined = " ".join(specialty_text.replace("\r\n", "\n").split())
        spec, gr = split_specialty_and_group(combined)
        if gr:
            out["научная_специальность"] = spec
            out["группа"] = gr
    # Несколько направлений: только если это действительно отдельные строки вида "специальность / гр. X" (не одна специальность с переносом — её уже обработали выше)
    if specialty_text and ("\n" in specialty_text or "\r\n" in specialty_text) and not out["группа"]:
        raw_lines = specialty_text.replace("\r\n", "\n").split("\n")
        lines = [ln.strip() for ln in raw_lines if ln.strip()]
        pairs = []
        for ln in lines:
            spec, gr = split_specialty_and_group(ln)
            if spec or gr:
                pairs.append((spec or ln, gr))
        if len(pairs) >= 2:
            return [
                {"группа": gr, "научная_специальность": spec, "год_обучения": out["год_обучения"]}
                for spec, gr in pairs
            ]
        if len(pairs) == 1:
            out["научная_специальность"] = pairs[0][0]
            out["группа"] = pairs[0][1]
    # Одна строка: если группа ещё не задана, но есть "специальность / гр. X.X.X-XX"
    elif not out["группа"] and specialty_text and "/" in specialty_text:
        spec, gr = split_specialty_and_group(specialty_text)
        if gr:
            out["научная_специальность"] = spec
            out["группа"] = gr

    return [out]


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
        blocks = _block_above_table(body_children, idx, elem_to_para, elem_to_table)
        for block in blocks:
            rows_out.extend(_parse_table_rows(
                table,
                block["группа"],
                block["научная_специальность"],
                block["год_обучения"],
            ))

    return rows_out


def _collect_unresolved_parse(all_results: dict) -> list[dict]:
    """Собирает записи для ручной проверки: группа не извлечена при наличии «гр.» в специальности и т.п."""
    out = []
    seen = set()
    for fname, data in all_results.items():
        if not isinstance(data, list):
            continue
        for rec in data:
            if not isinstance(rec, dict):
                continue
            group = (rec.get("группа") or "").strip()
            specialty = (rec.get("научная_специальность") or "").strip()
            disc = (rec.get("дисциплина") or "").strip()
            day = rec.get("день_недели", "")
            para = rec.get("пара", "")
            # Группа не извлечена, хотя в специальности есть «гр.» или «/»
            if not group and specialty and ("гр." in specialty.lower() or "/" in specialty):
                key = (fname, "group", specialty[:80], day, str(para))
                if key not in seen:
                    seen.add(key)
                    out.append({
                        "type": "group_not_extracted",
                        "file": fname,
                        "specialty": specialty,
                        "day": day,
                        "para": para,
                    })
            # Дисциплина похожа на обрыв (начинается с «и » — продолжение с предыдущей строки)
            if disc and disc.strip().startswith("и ") and len(disc) < 120:
                key = (fname, "disc_fragment", disc[:60], day, str(para))
                if key not in seen:
                    seen.add(key)
                    out.append({
                        "type": "discipline_fragment",
                        "file": fname,
                        "discipline": disc,
                        "day": day,
                        "para": para,
                    })
    return out


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

    # Сводный файл по всем файлам
    summary_path = OUTPUT_DIR / "_all.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"Сводный файл: {summary_path}")

    # Записи для ручной проверки (группа не извлечена, обрыв дисциплины и т.д.)
    unresolved_parse = _collect_unresolved_parse(all_results)
    unresolved_path = OUTPUT_DIR / "unresolved_parse.json"
    with open(unresolved_path, "w", encoding="utf-8") as f:
        json.dump(unresolved_parse, f, ensure_ascii=False, indent=2)
    if unresolved_parse:
        print(f"Записей для ручной проверки: {len(unresolved_parse)} → {unresolved_path}")


if __name__ == "__main__":
    main()
