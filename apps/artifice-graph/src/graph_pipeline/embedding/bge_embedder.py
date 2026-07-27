from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

import httpx

from graph_pipeline.config import EmbeddingConfig, load_config

logger = logging.getLogger(__name__)

_CACHE: dict[str, list[float]] = {}


def _text_key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class BGEM3Embedder:
    """Ollama /api/embeddings client with batching and caching."""

    def __init__(self, config: EmbeddingConfig | None = None) -> None:
        if config is None:
            config = load_config().embedding
        self.config = config
        self._client = httpx.Client(timeout=config.timeout)
        self._dimension: int | None = None

    def _embed_one(self, text: str) -> list[float]:
        key = _text_key(text)
        if key in _CACHE:
            return _CACHE[key]

        url = f"{self.config.base_url}/api/embeddings"
        payload = {
            "model": self.config.model,
            "prompt": text,
        }
        try:
            resp = self._client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            embedding = data.get("embedding", [])
            if not embedding:
                raise ValueError(f"Empty embedding returned for: {text[:80]}...")
            _CACHE[key] = embedding
            return embedding
        except (httpx.HTTPError, httpx.ConnectError) as exc:
            raise RuntimeError(
                f"Embedding request failed — is Ollama running at {self.config.base_url}?\n"
                f"Make sure model '{self.config.model}' is pulled:\n"
                f"  ollama pull {self.config.model}\n"
                f"{exc}"
            ) from exc

    def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        batch_size = self.config.batch_size

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            for text in batch:
                emb = self._embed_one(text)
                embeddings.append(emb)

            if i + batch_size < len(texts):
                logger.debug(
                    "Embedded %d/%d texts", min(i + batch_size, len(texts)), len(texts)
                )

        if embeddings and self._dimension is None:
            self._dimension = len(embeddings[0])

        return embeddings

    def embed_single(self, text: str) -> list[float]:
        return self._embed_one(text)

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            emb = self._embed_one("dimension probe")
            self._dimension = len(emb)
        return self._dimension

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> BGEM3Embedder:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
