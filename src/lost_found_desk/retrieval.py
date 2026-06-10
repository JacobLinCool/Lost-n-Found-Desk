"""Pure helpers for embedding-based candidate shortlisting (no model deps)."""

from __future__ import annotations

from typing import Any


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def rank_items_by_embedding(
    query_vec: list[float],
    items: list[dict[str, Any]],
    embeddings: dict[str, list[float]],
    topk: int,
) -> list[dict[str, Any]]:
    """Return the ``topk`` items most similar to ``query_vec``.

    Items without a usable (same-dimension) embedding sort last but are not
    dropped, so retrieval never silently hides inventory just because an
    embedding is missing.
    """
    scored: list[tuple[float, int, dict[str, Any]]] = []
    for i, item in enumerate(items):
        vec = embeddings.get(item.get("item_id", ""))
        sim = cosine(query_vec, vec) if vec else -1.0
        scored.append((sim, i, item))
    scored.sort(key=lambda t: (t[0], -t[1]), reverse=True)
    return [item for _, _, item in scored[: max(1, topk)]]
