"""
Сопоставление названий дисциплин со справочником (info/discipline.json) по эмбеддингам (Ollama nomic-embed-text).
Используется веб-интерфейсом «Сопоставление дисциплин» и может вызываться из других скриптов.

Запросы к Ollama идут из процесса Python (Flask), не из браузера. Адрес по умолчанию:
  локальный режим UI → http://127.0.0.1:11434
  удалённый → http://10.10.10.11:11434

Переопределение (например, Ollama на вашем ПК, а бэкенд на сервере; или Flask в WSL, Ollama в Windows):
  OLLAMA_EMBEDDINGS_URL=http://192.168.x.x:11434   — один URL для любого режима
  либо точечно: OLLAMA_LOCAL_URL=..., OLLAMA_REMOTE_URL=...
"""
import json
import os
import re
import sys
import requests
import numpy as np

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
    s = re.sub(r"-+", "", s)
    for remove in ["(лек", "(пр", "(лаб", ".", ",", ")", "("]:
        s = s.replace(remove, "")
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


def _embeddings_base_url(use_local: bool) -> str:
    """Базовый URL Ollama без завершающего слэша (для /api/embeddings)."""
    override = (
        os.getenv("OLLAMA_EMBEDDINGS_URL")
        or os.getenv("OLLAMA_API_BASE_URL")
        or ""
    ).strip().rstrip("/")
    if override:
        return override
    if use_local:
        return (
            os.getenv("OLLAMA_LOCAL_URL") or "http://127.0.0.1:11434"
        ).strip().rstrip("/")
    return (os.getenv("OLLAMA_REMOTE_URL") or "http://10.10.10.11:11434").strip().rstrip("/")


def get_embedding(text, *, use_local: bool | None = None):
    """
    Получить эмбеддинг текста через Ollama (nomic-embed-text).

    :param use_local: Если True — OLLAMA_LOCAL_URL или http://127.0.0.1:11434,
                      если False — OLLAMA_REMOTE_URL или http://10.10.10.11:11434,
                      если None — брать из окружения USE_LOCAL_OLLAMA (1/true/yes).

    URL целиком можно задать OLLAMA_EMBEDDINGS_URL (или OLLAMA_API_BASE_URL) — тогда
    режим local/remote не меняет хост (удобно, когда бэкенд и Ollama на разных машинах).
    """
    if use_local is None:
        env_val = os.getenv("USE_LOCAL_OLLAMA", "").strip().lower()
        use_local = env_val in ("1", "true", "yes")

    base_url = _embeddings_base_url(use_local)

    try:
        response = requests.post(
            f"{base_url}/api/embeddings",
            json={
                "model": "nomic-embed-text",
                "prompt": text
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return np.array(data["embedding"])
    except Exception as e:
        raise RuntimeError(f"Ollama request failed: {e}") from e


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


def ensure_embeddings(*, use_local: bool | None = None):
    """Загружает документы и эмбеддинги (из кэша или через Ollama). Возвращает (documents, doc_embeddings)."""
    documents = load_documents()
    if not documents:
        return [], None
    doc_embeddings = load_cached_embeddings(documents)
    if doc_embeddings is not None:
        return documents, doc_embeddings
    doc_embeddings = []
    for i, doc in enumerate(documents):
        try:
            doc_embeddings.append(get_embedding(normalize_for_compare(doc), use_local=use_local))
        except Exception as e:
            # Для веб-интерфейса важно видеть конкретную ошибку, поэтому не скрываем её,
            # а пробрасываем дальше (её поймает Flask и вернёт в поле error).
            print(f"Ошибка эмбеддинга для документа {i}: {e}", file=sys.stderr)
            raise
        if (i + 1) % 200 == 0:
            print(f"  {i + 1}/{len(documents)}", file=sys.stderr)
    doc_embeddings = np.array(doc_embeddings)
    save_embeddings(documents, doc_embeddings)
    return documents, doc_embeddings


def match_query(query_text, documents, doc_embeddings, top_k=4, *, use_local: bool | None = None):
    """
    Сопоставляет query_text со справочником по эмбеддингам.
    Возвращает список кортежей (название_документа, оценка_сходства), отсортированный по убыванию, до top_k штук.
    """
    if not documents or doc_embeddings is None or not query_text:
        return []
    try:
        normalized = normalize_for_compare(query_text)
        query_emb = get_embedding(normalized, use_local=use_local)
    except Exception:
        return []
    scores = np.dot(doc_embeddings, query_emb) / (
        np.linalg.norm(doc_embeddings, axis=1) * np.linalg.norm(query_emb)
    )
    top_indices = np.argsort(scores)[::-1][:top_k]
    return [(documents[i], float(scores[i])) for i in top_indices]
