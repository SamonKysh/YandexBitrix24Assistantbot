"""
Гибридный поисковый индекс базы знаний Bitrix24.

"""
import hashlib
import math
import os
import re
import threading
from collections import Counter
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from app.config import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_CACHE_PATH,
    EMBEDDING_DOC_MODEL,
    EMBEDDING_QUERY_MODEL,
    USE_SEMANTIC_SEARCH,
)
from app.logger import logger


@dataclass
class Chunk:
    text: str
    url: str
    filename: str


@dataclass
class SearchResult:
    text: str
    url: str
    filename: str
    score: float


class SearchIndex:
    """BM25 + эмбеддинги + RRF. Потокобезопасен (threading.RLock)."""

    def __init__(self, k1: float = 1.5, b: float = 0.75, rrf_k: int = 60):
        self.k1 = k1
        self.b = b
        self.rrf_k = rrf_k
        self.chunks: List[Chunk] = []
        self.avgdl = 0.0
        self.doc_freq: dict = {}
        self.vectors: Optional[np.ndarray] = None
        self._lock = threading.RLock()
        self._sdk = None

    @property
    def sdk(self):
        if self._sdk is None:
            from yandex_ai_studio_sdk import AIStudio
            from yandex_ai_studio_sdk.auth import APIKeyAuth
            from app.config import YC_API_KEY, YC_FOLDER_ID
            self._sdk = AIStudio(folder_id=YC_FOLDER_ID, auth=APIKeyAuth(YC_API_KEY))
        return self._sdk

    # ---------------- построение индекса ----------------

    def build(self, docs_dir: str = "data/docs") -> int:
        with self._lock:
            self.chunks.clear()
            self.doc_freq.clear()
            self.vectors = None

            if not os.path.exists(docs_dir):
                logger.warning("Папка %s не найдена — индекс пуст", docs_dir)
                return 0

            for filename in sorted(os.listdir(docs_dir)):
                if not filename.endswith(".txt"):
                    continue
                try:
                    with open(os.path.join(docs_dir, filename), "r", encoding="utf-8") as f:
                        content = f.read()
                except Exception as exc:
                    logger.error("Не удалось прочитать %s: %s", filename, exc)
                    continue

                lines = content.splitlines()
                url = ""
                if lines and lines[0].startswith("Source:"):
                    url = lines[0].replace("Source:", "").strip()
                    content = "\n".join(lines[1:]).strip()

                for chunk_text in self._chunk_text(content):
                    self.chunks.append(Chunk(text=chunk_text, url=url, filename=filename))

            lengths = [len(self._tokenize(c.text)) for c in self.chunks]
            self.avgdl = (sum(lengths) / len(lengths)) if lengths else 0.0

            for chunk in self.chunks:
                for term in set(self._tokenize(chunk.text)):
                    self.doc_freq[term] = self.doc_freq.get(term, 0) + 1

            logger.info("BM25-индекс построен: чанков=%d, avgdl=%.1f, терминов=%d",
                        len(self.chunks), self.avgdl, len(self.doc_freq))

            if USE_SEMANTIC_SEARCH:
                self._load_or_compute_embeddings()
            else:
                logger.info("Семантический поиск отключён (USE_SEMANTIC_SEARCH=false)")

            return len(self.chunks)

    # ---------------- эмбеддинги и векторное хранилище ----------------

    @staticmethod
    def _chunk_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _save_cache(self, hashes: List[str], cache: dict) -> None:
        try:
            os.makedirs(os.path.dirname(EMBEDDING_CACHE_PATH) or ".", exist_ok=True)
            present = [h for h in hashes if h in cache]
            np.savez(
                EMBEDDING_CACHE_PATH,
                hashes=np.array(present, dtype=np.str_),
                vectors=np.stack([cache[h] for h in present]),
            )
        except Exception as exc:
            logger.warning("Не удалось сохранить кэш эмбеддингов: %s", exc)

    def _load_or_compute_embeddings(self) -> None:
        hashes = [self._chunk_hash(c.text) for c in self.chunks]
        cache: dict = {}

        if os.path.exists(EMBEDDING_CACHE_PATH):
            try:
                with np.load(EMBEDDING_CACHE_PATH) as data:
                    for h, vec in zip(data["hashes"], data["vectors"]):
                        cache[str(h)] = np.asarray(vec, dtype=np.float32)
                logger.info("Кэш эмбеддингов загружен: %d векторов", len(cache))
            except Exception as exc:
                logger.error("Не удалось прочитать кэш %s: %s", EMBEDDING_CACHE_PATH, exc)
                cache = {}

        missing_idx = [i for i, h in enumerate(hashes) if h not in cache]
        if missing_idx:
            logger.info("Вычисляю эмбеддинги для %d новых чанков...", len(missing_idx))
            try:
                doc_model = self.sdk.chat.text_embeddings(EMBEDDING_DOC_MODEL)
            except Exception as exc:
                logger.error("Модель эмбеддингов недоступна, остаюсь на BM25: %s", exc)
                self.vectors = None
                return

            done = 0
            for start in range(0, len(missing_idx), EMBEDDING_BATCH_SIZE):
                batch_idx = missing_idx[start:start + EMBEDDING_BATCH_SIZE]
                try:
                    for i in batch_idx:
                        vec = doc_model.run(self.chunks[i].text)
                        cache[hashes[i]] = np.array(vec, dtype=np.float32)
                    done += len(batch_idx)
                    logger.info("Эмбеддинги: %d/%d", done, len(missing_idx))
                    self._save_cache(hashes, cache)  # защита от обрыва сети
                except Exception as exc:
                    logger.error("Ошибка батча эмбеддингов, остаюсь на BM25: %s", exc)
                    self.vectors = None
                    return

        # Замечание №5: устаревшие векторы не хранятся
        cache = {h: cache[h] for h in hashes if h in cache}
        if len(cache) != len(hashes):
            logger.warning("Не хватает векторов для %d чанков, остаюсь на BM25",
                           len(hashes) - len(cache))
            self.vectors = None
            return
        self._save_cache(hashes, cache)

        matrix = np.stack([cache[h] for h in hashes])
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self.vectors = matrix / norms
        logger.info("Эмбеддинги готовы: матрица %s", self.vectors.shape)

    # ---------------- гибридный поиск ----------------

    def search(self, query: str, top_k: int = 5) -> List[SearchResult]:
        with self._lock:
            if not self.chunks:
                return []

            rankings = [self._bm25_ranking(query)]

            if self.vectors is not None:
                semantic = self._semantic_ranking(query)
                if semantic is not None:
                    rankings.append(semantic)

            fused = self._rrf(rankings)
            order = sorted(range(len(fused)), key=lambda i: fused[i], reverse=True)[:top_k]
            return [
                SearchResult(
                    text=self.chunks[i].text,
                    url=self.chunks[i].url,
                    filename=self.chunks[i].filename,
                    score=fused[i],
                )
                for i in order
            ]

    def _bm25_ranking(self, query: str) -> List[int]:
        scores = self._bm25_scores(query)
        return sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

    def _bm25_scores(self, query: str) -> List[float]:
        query_tokens = self._tokenize(query)
        n = len(self.chunks)
        scores = []
        for chunk in self.chunks:
            chunk_tokens = self._tokenize(chunk.text)
            dl = len(chunk_tokens)
            counts = Counter(chunk_tokens)
            score = 0.0
            for term in query_tokens:
                df = self.doc_freq.get(term, 0)
                tf = counts.get(term, 0)
                if df == 0 or tf == 0:
                    continue
                idf = math.log((n - df + 0.5) / (df + 0.5) + 1.0)
                denom = tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl) if self.avgdl else 1.0
                score += idf * (tf * (self.k1 + 1)) / denom
            scores.append(score)
        return scores

def _semantic_ranking(self, query: str) -> Optional[List[int]]:
    try:
        query_model = self.sdk.chat.text_embeddings(EMBEDDING_QUERY_MODEL)
        qvec = np.array(query_model.run(query), dtype=np.float32)
    except Exception as exc:
        logger.error("Не удалось эмбеддить запрос, использую только BM25: %s", exc)
        return None
    norm = np.linalg.norm(qvec)
    if norm == 0:
        return None
    sims = self.vectors @ (qvec / norm)  # косинусное сходство
    
    # Убираем дубликаты: сортируем по (score, index) для стабильности
    ranked_with_scores = [(i, sims[i]) for i in range(len(sims))]
    ranked_with_scores.sort(key=lambda x: (-x[1], x[0]))  # сначала по score desc, потом по index asc
    
    # Возвращаем только индексы без дубликатов
    seen_urls = set()
    result = []
    for idx, score in ranked_with_scores:
        url = self.chunks[idx].url or self.chunks[idx].filename
        if url not in seen_urls:
            seen_urls.add(url)
            result.append(idx)
    return result

    def _rrf(self, rankings: List[List[int]]) -> List[float]:
        """Reciprocal Rank Fusion: score(d) = Σ по ранжированиям 1/(k + rank(d))."""
        fused = [0.0] * len(self.chunks)
        for ranking in rankings:
            for rank, idx in enumerate(ranking):
                fused[idx] += 1.0 / (self.rrf_k + rank + 1)
        return fused

    # ---------------- вспомогательное ----------------

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 2000, overlap: int = 400) -> List[str]:
        if not text:
            return []
        chunks = []
        start = 0
        while start < len(text):
            chunks.append(text[start:start + chunk_size])
            start += chunk_size - overlap
        return chunks

    @staticmethod
    def _stem(token: str) -> str:
        """Лёгкий стемер: 'сделку' и 'сделка' дают один термин."""
        if len(token) > 5 and token[-3:] in ("ами", "ями", "ого", "его", "ыми", "ими"):
            return token[:-3]
        if len(token) > 4 and token[-2:] in ("ов", "ев", "ам", "ям", "ах", "ях", "ой",
                                             "ей", "ый", "ий", "ая", "яя", "ое", "ее",
                                             "ье", "ья", "ут", "ют", "ет", "ть"):
            return token[:-2]
        if len(token) > 4 and token[-1] in ("у", "ю", "а", "я", "ы", "и", "е", "й", "ь"):
            return token[:-1]
        return token

    @classmethod
    def _tokenize(cls, text: str) -> List[str]:
        return [cls._stem(t) for t in re.findall(r"[a-zа-яё0-9_.]+", text.lower())]


# Глобальный экземпляр индекса — один на всё приложение
index = SearchIndex()