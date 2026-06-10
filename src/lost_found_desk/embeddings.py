"""Embedding adapters for retrieve-then-rerank inventory matching.

When a single event's inventory grows large, packing every caption into the
matching prompt is slow, noisy, and eventually exceeds context. Instead we
precompute an embedding per item at intake (caption time) and, at match time,
embed the claimant's description and keep only the top-N most similar items
before the LLM/ranker runs.

The real adapter uses NVIDIA's multilingual vision-language embedder
(``nvidia/llama-nemotron-embed-vl-1b-v2``), which embeds the *item photo + its
caption* and a *text query* into one 2048-d space — so a Chinese description can
retrieve an English-captioned item. A deterministic mock embedder keeps the
feature testable offline when mock mode is explicitly selected.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Protocol

logger = logging.getLogger("lost_found_desk.embeddings")

_TOKEN_RE = re.compile(r"[a-z0-9]+|[぀-ヿ㐀-鿿豈-﫿]")


class Embedder(Protocol):
    def embed_query(self, text: str) -> list[float]: ...
    def embed_item(self, image_path: str, text: str) -> list[float]: ...


class MockEmbedder:
    """Deterministic, dependency-free embedder (lexical, language-agnostic).

    Hashes word and character n-gram features into a fixed-width L2-normalized
    vector. Not semantic like the real model, but it makes retrieval functional
    and testable without any download, and degrades gracefully.
    """

    def __init__(self, dim: int = 256):
        self.dim = dim

    def _features(self, text: str) -> list[str]:
        toks = _TOKEN_RE.findall((text or "").lower())
        feats = list(toks)
        for t in toks:
            for i in range(len(t) - 1):  # char bigrams help short/CJK tokens
                feats.append(t[i : i + 2])
        return feats

    def _vec(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for feat in self._features(text):
            h = int(hashlib.md5(feat.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if (h >> 8) & 1 else -1.0
            vec[idx] += sign
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)

    def embed_item(self, image_path: str, text: str) -> list[float]:
        # The mock has no vision; it embeds the caption text only.
        return self._vec(text)


class NemotronVLEmbedder:
    """``nvidia/llama-nemotron-embed-vl-1b-v2`` via sentence-transformers.

    Items are embedded as multimodal docs (photo + caption); queries as text.
    Both land in the same 2048-d multilingual space. Lazy-loaded like the other
    real adapters.
    """

    def __init__(self, model_id: str, device: str | None = None):
        self.model_id = model_id
        self.device = device
        self.model: Any | None = None

    def _load(self) -> None:
        if self.model is not None:
            return
        from sentence_transformers import SentenceTransformer

        from .runtime.device import detect_runtime

        runtime = detect_runtime(self.device or "auto")
        st_device = None if runtime.device == "cuda" else runtime.device
        self.model = SentenceTransformer(self.model_id, trust_remote_code=True, device=st_device)

    def embed_query(self, text: str) -> list[float]:
        self._load()
        assert self.model is not None
        out = self.model.encode_query([text or ""])
        return [float(x) for x in out[0]]

    def embed_item(self, image_path: str, text: str) -> list[float]:
        self._load()
        assert self.model is not None
        try:
            from PIL import Image

            image = Image.open(image_path).convert("RGB")
            out = self.model.encode([{"image": image, "text": text or ""}])
        except Exception:
            logger.warning("image embed failed for %s; embedding caption text only", image_path, exc_info=True)
            out = self.model.encode([text or ""])
        return [float(x) for x in out[0]]


def build_embedder(model_mode: str, model_id: str, device: str | None = None) -> Embedder:
    if model_mode != "real":
        return MockEmbedder()
    return NemotronVLEmbedder(model_id, device)
