"""Embeddings for incident-signature retrieval.

``HashedEmbedder`` is a deterministic feature-hashing embedder (word uni/bi-grams →
fixed-dimension L2-normalised vector). It has no model dependency, is fully reproducible,
and is good enough for signature similarity because incident signatures are short,
vocabulary-controlled strings produced by Sentinel itself (metric names, signals,
services, categories). When Ollama is configured, ``nomic-embed-text`` is used instead.
"""

from __future__ import annotations

import hashlib
import math
import re

_TOKEN = re.compile(r"[a-z0-9_.]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class HashedEmbedder:
    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def _idx(self, token: str) -> tuple[int, float]:
        h = hashlib.blake2b(token.encode(), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "little") % self.dim
        sign = 1.0 if h[4] & 1 else -1.0
        return idx, sign

    def embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        toks = tokenize(text)
        feats = list(toks) + [f"{a}_{b}" for a, b in zip(toks, toks[1:], strict=False)]
        for f in feats:
            i, s = self._idx(f)
            vec[i] += s
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0
