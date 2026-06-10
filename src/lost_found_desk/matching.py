from __future__ import annotations

import re
from typing import Any

from .schemas import Candidate

_WORD_RE = re.compile(r"[a-zA-Z0-9#\-]+")
_CJK_RE = re.compile("[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uff00-\uffef]")

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for", "with", "this", "that",
    "i", "lost", "left", "maybe", "possibly", "probably", "item", "thing", "near", "after", "before",
    "please", "my", "it", "is", "was", "has", "had", "have", "from", "by", "around",
}

COLORS = {
    "black", "white", "blue", "navy", "red", "green", "yellow", "purple", "pink", "orange", "gray",
    "grey", "silver", "gold", "brown", "beige", "clear", "transparent",
}

ITEM_HINTS = {
    "bottle", "water", "jacket", "hoodie", "sweater", "charger", "cable", "phone", "laptop", "bag",
    "backpack", "badge", "wallet", "keys", "key", "case", "airpods", "earbuds", "notebook", "umbrella",
    "hat", "cap", "glasses", "pencil", "lunch", "box",
}

DISTINCTIVE_HINTS = {
    "sticker", "logo", "brand", "scratch", "scratched", "dent", "mark", "label", "strap", "zipper",
    "silver", "cap", "lid", "conference", "dinosaur", "shark", "name", "tag", "badge",
}

LOCATION_WORDS = ["room", "hall", "lobby", "booth", "field", "gym", "desk", "workshop", "track", "stage", "court"]


def has_location(text: str) -> bool:
    return any(w in (text or "").lower() for w in LOCATION_WORDS)


def tokens(text: str) -> set[str]:
    return {m.group(0).lower() for m in _WORD_RE.finditer(text or "") if m.group(0).lower() not in STOPWORDS}


def color_tokens(text: str) -> set[str]:
    return tokens(text) & COLORS


def has_enough_claim_detail(summary: str) -> bool:
    s = (summary or "").strip()
    if not s:
        return False
    # Language-agnostic floor: a description with enough substance (in any
    # language) is worth ranking. Counting CJK characters alongside latin word
    # tokens keeps non-English claims from being wrongly judged "too vague" —
    # the original English-keyword-only gate stalled Chinese/Japanese claims.
    cjk_chars = len(_CJK_RE.findall(s))
    latin_tokens = len(tokens(s))
    if cjk_chars >= 4 or latin_tokens >= 4:
        return True
    # For short latin-only summaries, require an item plus one more signal.
    t = tokens(s)
    has_item = bool(t & ITEM_HINTS)
    has_color = bool(t & COLORS)
    has_distinctive = bool(t & DISTINCTIVE_HINTS)
    return has_item and (has_color or has_distinctive or has_location(s))


def score_claim_to_item(claim: str, item_caption: str) -> tuple[float, list[str]]:
    claim_t = tokens(claim)
    item_t = tokens(item_caption)
    if not claim_t or not item_t:
        return 0.0, []

    overlap = claim_t & item_t
    union = claim_t | item_t
    base = len(overlap) / max(1, len(union))

    reasons: list[str] = []
    item_overlap = overlap & ITEM_HINTS
    color_overlap = overlap & COLORS
    distinctive_overlap = overlap & DISTINCTIVE_HINTS

    bonus = 0.0
    if item_overlap:
        bonus += 0.18
        reasons.append("item type aligns: " + ", ".join(sorted(item_overlap)[:4]))
    if color_overlap:
        bonus += 0.18
        reasons.append("color aligns: " + ", ".join(sorted(color_overlap)[:4]))
    if distinctive_overlap:
        bonus += 0.24
        reasons.append("distinctive detail aligns: " + ", ".join(sorted(distinctive_overlap)[:5]))

    # Mild phrase/location boosts.
    for phrase in ["room b", "room a", "hall a", "lobby", "workshop", "soccer", "booth", "front desk"]:
        if phrase in claim.lower() and phrase in item_caption.lower():
            bonus += 0.15
            reasons.append(f"location/context aligns: {phrase}")

    # Negative evidence: both mention colors, but no color overlaps.
    claim_colors = color_tokens(claim)
    item_colors = color_tokens(item_caption)
    penalty = 0.0
    if claim_colors and item_colors and not (claim_colors & item_colors):
        penalty += 0.25
        reasons.append("color conflict: claim and item mention different colors")

    score = max(0.0, min(1.0, base + bonus - penalty))
    if not reasons and overlap:
        reasons.append("some descriptive terms overlap: " + ", ".join(sorted(overlap)[:6]))
    return score, reasons


def rank_candidates(claim_summary: str, items: list[dict[str, Any]], max_candidates: int = 3) -> tuple[str, list[Candidate]]:
    if not has_enough_claim_detail(claim_summary):
        return "needs_more_info", [
            Candidate(
                item_id="",
                state="needs_more_info",
                score=0.0,
                reason="The claim is too vague to safely rank candidates.",
                staff_next_step="Ask for item type, color, location, and one distinctive mark such as logo, sticker, brand, damage, or contents.",
                safe_claimant_message="Could you describe the item type, color, where you last saw it, and any sticker, logo, brand, size, damage, or other distinctive mark?",
            )
        ]

    scored: list[tuple[float, dict[str, Any], list[str]]] = []
    for item in items:
        if item.get("status") != "unclaimed":
            continue
        caption = " ".join([item.get("caption", ""), item.get("found_location", ""), item.get("staff_note", "")])
        score, reasons = score_claim_to_item(claim_summary, caption)
        if score > 0:
            scored.append((score, item, reasons))

    scored.sort(key=lambda x: x[0], reverse=True)
    candidates: list[Candidate] = []
    for score, item, reasons in scored[:max_candidates]:
        if score >= 0.58:
            state = "strong_candidate"
        elif score >= 0.28:
            state = "weak_candidate"
        else:
            continue
        candidates.append(
            Candidate(
                item_id=item["item_id"],
                state=state,
                score=round(score, 3),
                reason="; ".join(reasons) if reasons else "The claim and item caption share relevant details.",
                staff_next_step="Review the photo and caption privately, then confirm handoff offline. Ask one open-ended detail question if needed.",
                safe_claimant_message="Staff may have a possible match for your description. Please be ready to confirm any additional identifying details at pickup.",
            )
        )

    if not candidates:
        return "no_match", []
    overall = "strong_candidate" if candidates[0].state == "strong_candidate" else "weak_candidate"
    return overall, candidates


def build_inventory_prompt(claim_summary: str, items: list[dict[str, Any]]) -> str:
    lines = []
    for item in items:
        if item.get("status") == "unclaimed":
            lines.append(f"{item.get('item_id')}: {item.get('caption')} Found location: {item.get('found_location', '')}")
    inventory = "\n".join(lines) or "No unclaimed items."
    return f"Claim summary:\n{claim_summary}\n\nUnclaimed inventory:\n{inventory}"
