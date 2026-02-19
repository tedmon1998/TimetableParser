import json
import os
import re
import sys
import requests
import numpy as np

# Путь к справочнику дисциплин и кэшу эмбеддингов
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DISCIPLINE_FILE = os.path.join(SCRIPT_DIR, "info", "discipline.json")
EMBEDDINGS_DIR = os.path.join(SCRIPT_DIR, "subject")
EMBEDDINGS_FILE = os.path.join(EMBEDDINGS_DIR, "discipline_embeddings.npy")
EMBEDDINGS_META_FILE = os.path.join(EMBEDDINGS_DIR, "discipline_embeddings_meta.json")


def normalize_for_compare(s):
    """Нормализация строки перед сравнением: убрать '-', '(лек', '(пр', '(лаб', '.', ',', числа; обрезать пробелы по краям."""
    if not s:
        return s
    s = str(s).strip()
    # Убрать все '-' (в любом количестве: '--', '---', '-- ----' и т.д.)
    s = re.sub(r"-+", "", s)
    # Убрать подстроки и символы
    for remove in ["(лек", "(пр", "(лаб", ".", ",", ")", "(", "'"]:
        s = s.replace(remove, "")
    # Убрать числа
    s = re.sub(r"\d+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def load_documents():
    """Загружает список дисциплин из info/discipline.json."""
    if not os.path.isfile(DISCIPLINE_FILE):
        return []
    with open(DISCIPLINE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return []
    return [str(x).strip() for x in data if x is not None and str(x).strip()]


def get_embedding(text):
    response = requests.post(
        "http://10.10.10.11:11434/api/embeddings",
        json={
            "model": "nomic-embed-text",
            "prompt": text
        }
    )
    return np.array(response.json()["embedding"])


def load_cached_embeddings(documents):
    """Загружает эмбеддинги из файла, если кэш есть и соответствует текущему списку документов."""
    if not os.path.isfile(EMBEDDINGS_FILE) or not os.path.isfile(EMBEDDINGS_META_FILE):
        return None
    try:
        with open(EMBEDDINGS_META_FILE, "r", encoding="utf-8") as f:
            meta = json.load(f)
        if meta.get("documents") != documents:
            return None
        return np.load(EMBEDDINGS_FILE)
    except Exception:
        return None


def save_embeddings(documents, embeddings):
    """Сохраняет эмбеддинги и метаданные (список документов) в папку subject."""
    os.makedirs(EMBEDDINGS_DIR, exist_ok=True)
    np.save(EMBEDDINGS_FILE, embeddings)
    with open(EMBEDDINGS_META_FILE, "w", encoding="utf-8") as f:
        json.dump({"documents": documents}, f, ensure_ascii=False, indent=0)


def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def main():
    documents = load_documents()
    print(f"Загружено документов из {DISCIPLINE_FILE}: {len(documents)}", file=sys.stderr)
    if not documents:
        print("Список дисциплин пуст. Завершение.", file=sys.stderr)
        return

    doc_embeddings = load_cached_embeddings(documents)
    if doc_embeddings is not None:
        print("Эмбеддинги загружены из кэша.", file=sys.stderr)
    else:
        print("Загрузка эмбеддингов документов...", file=sys.stderr)
        doc_embeddings = []
        for i, doc in enumerate(documents):
            try:
                doc_embeddings.append(get_embedding(normalize_for_compare(doc)))
            except Exception as e:
                print(f"Ошибка эмбеддинга для документа {i}: {e}", file=sys.stderr)
                return
            if (i + 1) % 200 == 0:
                print(f"  {i + 1}/{len(documents)}", file=sys.stderr)
        doc_embeddings = np.array(doc_embeddings)
        save_embeddings(documents, doc_embeddings)
        print("Готово. Эмбеддинги сохранены в кэш.", file=sys.stderr)
    print("-" * 50)
    print("Вводите текст для проверки (пустая строка или exit — выход):")
    print()

    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            break
        if not line or line.lower() in ("exit", "quit", "q"):
            break
        query = line
        try:
            normalized_query = normalize_for_compare(query)
            print(f"normalized_query : {normalized_query}")
            query_emb = get_embedding(normalized_query)
        except Exception as e:
            print(f"Ошибка: {e}\n")
            continue
        scores = np.dot(doc_embeddings, query_emb) / (
            np.linalg.norm(doc_embeddings, axis=1) * np.linalg.norm(query_emb)
        )
        best_idx = int(np.argmax(scores))
        best_doc = documents[best_idx]
        best_score = float(scores[best_idx])
        print("Лучшее совпадение:", best_doc)
        print("Сходство:", round(best_score, 3))
        print()


if __name__ == "__main__":
    main()