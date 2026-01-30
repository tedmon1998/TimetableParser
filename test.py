import json
import os
import sys
import requests
import numpy as np

# Путь к справочнику дисциплин
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DISCIPLINE_FILE = os.path.join(SCRIPT_DIR, "info", "discipline.json")


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
        "http://localhost:11434/api/embeddings",
        json={
            "model": "nomic-embed-text",
            "prompt": text
        }
    )
    return np.array(response.json()["embedding"])


def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def main():
    documents = load_documents()
    print(f"Загружено документов из {DISCIPLINE_FILE}: {len(documents)}", file=sys.stderr)
    if not documents:
        print("Список дисциплин пуст. Завершение.", file=sys.stderr)
        return

    print("Загрузка эмбеддингов документов...", file=sys.stderr)
    doc_embeddings = []
    for i, doc in enumerate(documents):
        try:
            doc_embeddings.append(get_embedding(doc))
        except Exception as e:
            print(f"Ошибка эмбеддинга для документа {i}: {e}", file=sys.stderr)
            return
        if (i + 1) % 200 == 0:
            print(f"  {i + 1}/{len(documents)}", file=sys.stderr)
    doc_embeddings = np.array(doc_embeddings)
    print("Готово.", file=sys.stderr)
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
            query_emb = get_embedding(query)
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