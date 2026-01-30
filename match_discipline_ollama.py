"""
Модуль сопоставления названия дисциплины со справочником info/discipline.json
с помощью локальной модели Ollama.

Возвращает: оригинальное название, найденное в справочнике, и примерный процент отличия.

Требования:
  - Ollama установлен и запущен (ollama serve)
  - Модель скачана, например: ollama pull llama3.2
  - pip install ollama

Использование:
    from match_discipline_ollama import match_discipline, load_disciplines

    result = match_discipline("матматика", model="llama3.2")
    # result = {
    #   "original": "матматика",
    #   "matched": "Математика",
    #   "difference_percent": 5.0,
    #   "similarity_percent": 95.0
    # }

    # Без Ollama (только difflib):
    result = match_discipline("матматика", use_ollama=False)
"""

import json
import os
import re
import difflib
from typing import Optional

# Путь к справочнику дисциплин (относительно корня проекта)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DISCIPLINE_FILE = os.path.join(SCRIPT_DIR, "info", "discipline.json")

# Количество кандидатов для отправки в Ollama (чтобы не перегружать контекст)
TOP_N_CANDIDATES = 25


def load_disciplines(path: Optional[str] = None) -> list[str]:
    """Загружает список дисциплин из info/discipline.json."""
    file_path = path or DISCIPLINE_FILE
    if not os.path.isfile(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return []
    return [str(x).strip() for x in data if x is not None and str(x).strip()]


def _get_candidates(query: str, disciplines: list[str], n: int = TOP_N_CANDIDATES) -> list[str]:
    """Возвращает топ-n кандидатов по строковому сходству (difflib)."""
    if not disciplines:
        return []
    # get_close_matches учитывает регистр слабо при cutoff; даём небольшой cutoff
    candidates = difflib.get_close_matches(query.strip(), disciplines, n=n, cutoff=0.1)
    if not candidates:
        # Если ничего не найдено — вернуть первые n по длине похожих (по ratio)
        query_lower = query.strip().lower()
        scored = [(d, difflib.SequenceMatcher(None, query_lower, d.lower()).ratio()) for d in disciplines]
        scored.sort(key=lambda x: -x[1])
        return [s[0] for s in scored[:n]]
    return candidates


def _similarity_ratio(a: str, b: str) -> float:
    """Сходство 0..1 (1 — идентично)."""
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _match_via_ollama(query: str, candidates: list[str], model: str) -> Optional[tuple[str, float]]:
    """
    Отправляет в Ollama запрос: выбрать лучший вариант из candidates для query.
    Возвращает (matched_name, similarity_0_100) или None при ошибке.
    """
    try:
        import ollama
    except ImportError:
        return None

    if not candidates:
        return None

    list_text = "\n".join(f"- {c}" for c in candidates)
    prompt = f"""Список названий дисциплин (ровно один из них нужно выбрать):
{list_text}

Пользователь ввёл: "{query}"

Выбери из списка выше ОДНУ дисциплину, которая лучше всего соответствует вводу (учти опечатки и синонимы).
Ответь СТРОГО в одну строку в формате:
НАЗВАНИЕ_ИЗ_СПИСКА|ЧИСЛО
где НАЗВАНИЕ_ИЗ_СПИСКА — точная строка из списка выше (скопируй как есть), а ЧИСЛО — степень совпадения от 0 до 100 (100 = полное совпадение)."""

    try:
        response = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
        text = (response.message.content or "").strip()
    except Exception:
        return None

    # Парсим ответ: "Название дисциплины|85" или "Название| 85" (последний | отделяет число)
    parts = text.split("|")
    if len(parts) >= 2:
        name_part = parts[0].strip()
        num_str = parts[-1].strip()
        num_match = re.search(r"[\d.]+", num_str)
        try:
            sim = float(num_match.group(0)) if num_match else 50.0
            sim = max(0, min(100, sim))
        except ValueError:
            sim = 50.0
        # Проверяем, что name_part есть в candidates
        for c in candidates:
            if c.strip() == name_part or name_part in c or c in name_part:
                return (c, sim)
        for c in candidates:
            if name_part.lower() in c.lower():
                return (c, sim)
        if candidates:
            return (candidates[0], sim)
        return None

    # Fallback: ищем в ответе любую строку из candidates
    for c in candidates:
        if c in text or (len(c) >= 10 and c[:20] in text):
            return (c, 50.0)
    if candidates:
        return (candidates[0], 50.0)
    return None


def match_discipline(
    discipline_name: str,
    disciplines_path: Optional[str] = None,
    model: str = "llama3.2",
    use_ollama: bool = True,
) -> dict:
    """
    Находит в справочнике info/discipline.json наиболее подходящее название дисциплины.

    :param discipline_name: Введённое пользователем название (возможно с опечаткой).
    :param disciplines_path: Путь к JSON со списком дисциплин (по умолчанию info/discipline.json).
    :param model: Имя модели Ollama (например llama3.2, gemma2).
    :param use_ollama: Если False — использовать только difflib (без Ollama).

    :return: Словарь:
        - original: исходная строка
        - matched: найденное название из справочника
        - difference_percent: примерный процент отличия (0 = совпадение, 100 = полное отличие)
        - similarity_percent: примерный процент совпадения (100 - difference_percent)
    """
    original = (discipline_name or "").strip()
    if not original:
        return {
            "original": original,
            "matched": "",
            "difference_percent": 100.0,
            "similarity_percent": 0.0,
        }

    disciplines = load_disciplines(disciplines_path)
    if not disciplines:
        return {
            "original": original,
            "matched": "",
            "difference_percent": 100.0,
            "similarity_percent": 0.0,
        }

    # Точное совпадение (без учёта регистра)
    for d in disciplines:
        if d.strip().lower() == original.lower():
            return {
                "original": original,
                "matched": d,
                "difference_percent": 0.0,
                "similarity_percent": 100.0,
            }

    candidates = _get_candidates(original, disciplines, n=TOP_N_CANDIDATES)
    if not candidates:
        return {
            "original": original,
            "matched": "",
            "difference_percent": 100.0,
            "similarity_percent": 0.0,
        }

    matched_name: str
    similarity_percent: float

    if use_ollama:
        ollama_result = _match_via_ollama(original, candidates, model=model)
        if ollama_result:
            matched_name, similarity_percent = ollama_result
        else:
            # Fallback: лучший по difflib
            best = candidates[0]
            similarity_percent = _similarity_ratio(original, best) * 100
            matched_name = best
    else:
        best = candidates[0]
        similarity_percent = _similarity_ratio(original, best) * 100
        matched_name = best

    difference_percent = max(0.0, min(100.0, 100.0 - similarity_percent))

    return {
        "original": original,
        "matched": matched_name,
        "difference_percent": round(difference_percent, 1),
        "similarity_percent": round(similarity_percent, 1),
    }


def main():
    """Пример использования из командной строки."""
    import sys
    name = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "матматика"
    model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    result = match_discipline(name, model=model)
    print(f"Исходное:     {result['original']}")
    print(f"В справочнике: {result['matched']}")
    print(f"Отличие:      {result['difference_percent']}%")
    print(f"Совпадение:   {result['similarity_percent']}%")


if __name__ == "__main__":
    main()
