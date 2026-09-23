"""Диагностика гибридного поиска: отдельно BM25 и семантика."""
from app.assistant.search_index import index
from app.logger import logger

if __name__ == "__main__":
    n = index.build()
    logger.info("Чанков в индексе: %d, Векторы: %s", n, "нет" if index.vectors is None else index.vectors.shape)

    query = "как создать сделку"
    logger.info("Вопрос: %s", query)
    
    # Отдельно BM25
    bm25_rank = index._bm25_ranking(query)
    logger.info("BM25 топ-3:")
    for i in bm25_rank[:3]:
        logger.info("  %s", index.chunks[i].url or index.chunks[i].filename)
    
    # Отдельно семантика
    if index.vectors is not None:
        semantic_rank = index._semantic_ranking(query)
        if semantic_rank:
            logger.info("Семантика топ-3:")
            for i in semantic_rank[:3]:
                logger.info("  %s", index.chunks[i].url or index.chunks[i].filename)
    
    # Гибрид (RRF)
    logger.info("Гибрид (RRF) топ-3:")
    for r in index.search(query, top_k=3):
        logger.info("  score=%.4f  %s", r.score, r.url or r.filename)