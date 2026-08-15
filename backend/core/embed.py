"""Embeddings via a small local sentence-transformers model."""
from functools import lru_cache

from core.config import EMBED_MODEL

EMBED_DIM = 384


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBED_MODEL)


def embed(texts: list[str]) -> list[list[float]]:
    return _model().encode(texts, normalize_embeddings=True).tolist()
