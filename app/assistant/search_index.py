"""
Поисковый индекс базы знаний Bitrix24.

"""
import math
import os
import re
import threading
from collections import Counter
from dataclasses import dataclass
from typing import List

from app.logger import logger


@dataclass
class Chunk:
    """Фрагмент документации с метаданными."""
    text: str
    url: str
    filename: str


@dataclass
class SearchResult:
    """Результат поиска."""
    text: str
    url: str
    filename: str
    score: float


class SearchIndex:
    """
    BM25-поиск по базе знаний.
    Индекс строится один раз методом build() и хранится в памяти.
    Потокобезопасен (использует threading.RLock).
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.chunks: List[Chunk] = []
        self.avgdl: float = 0.0
        self.doc_freq: dict = {}          # term -> сколько чанков содержит term
        self._lock = threading.RLock()

    # --------------------- построение индекса ---------------------

    def build(self, docs_dir: str = "data/docs") -> int:
        """Читает документы с диска, разбивает на чанки, строит индекс."""
        with self._lock:
            self.chunks.clear()
            self.doc_freq.clear()

            if not os.path.exists(docs_dir):
                logger.warning("Папка %s не найдена — индекс пуст", docs_dir)
                return 0

            for filename in os.listdir(docs_dir):
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

            # Средняя длина чанка
            lengths = [len(self._tokenize(c.text)) for c in self.chunks]
            self.avgdl = sum(lengths) / len(lengths) if lengths else 0

            # Обратный индекс (document frequency)
            for chunk in self.chunks:
                unique_terms = set(self._tokenize(chunk.text))
                for term in unique_terms:
                    self.doc_freq[term] = self.doc_freq.get(term, 0) + 1

            logger.info(
                "Индекс построен: чанков=%d, avgdl=%.1f, уникальных терминов=%d",
                len(self.chunks), self.avgdl, len(self.doc_freq),
            )
            return len(self.chunks)

    # --------------------- поиск ---------------------

    def search(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """Возвращает top_k самых релевантных чанков по BM25."""
        with self._lock:
            if not self.chunks:
                return []

            query_tokens = self._tokenize(query)
            scores: List[float] = []
            n = len(self.chunks)

            for chunk in self.chunks:
                chunk_tokens = self._tokenize(chunk.text)
                dl = len(chunk_tokens)
                term_counts = Counter(chunk_tokens)
                score = 0.0
                for term in query_tokens:
                    if term not in self.doc_freq:
                        continue
                    tf = term_counts.get(term, 0)
                    if tf == 0:
                        continue
                    df = self.doc_freq[term]
                    idf = math.log((n - df + 0.5) / (df + 0.5) + 1.0)
                    tf_norm = (tf * (self.k1 + 1)) / (
                        tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                    ) if self.avgdl > 0 else 0
                    score += idf * tf_norm
                scores.append(score)

            # Индексы top_k максимальных скорингов
            ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
            return [
                SearchResult(
                    text=self.chunks[i].text,
                    url=self.chunks[i].url,
                    filename=self.chunks[i].filename,
                    score=scores[i],
                )
                for i in ranked
            ]

    # --------------------- вспомогательное ---------------------

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Простая токенизация: латиница, кириллица, цифры, точки и подчёркивания."""
        return re.findall(r"[a-zа-яё0-9_.]+", text.lower())

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """Разбивает документ на перекрывающиеся фрагменты по ~1000 символов."""
        if not text:
            return []
        chunks = []
        start = 0
        while start < len(text):
            chunks.append(text[start:start + chunk_size])
            start += chunk_size - overlap
        return chunks


# Глобальный экземпляр индекса — один на всё приложение
index = SearchIndex()