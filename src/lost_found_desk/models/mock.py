from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat

from ..matching import rank_candidates

COLOR_NAMES = [
    ("black", (35, 35, 35)),
    ("white", (235, 235, 235)),
    ("blue", (60, 110, 210)),
    ("red", (210, 60, 60)),
    ("green", (80, 160, 90)),
    ("yellow", (230, 200, 70)),
    ("gray", (135, 135, 135)),
    ("silver", (180, 180, 185)),
    ("brown", (125, 80, 45)),
]

ITEM_WORDS = ["bottle", "hoodie", "jacket", "charger", "badge", "bag", "wallet", "keys", "umbrella", "case", "airpods"]
COLOR_WORDS = ["black", "white", "blue", "red", "green", "yellow", "gray", "grey", "silver", "brown", "navy", "purple", "pink"]
DETAIL_WORDS = ["sticker", "logo", "brand", "scratch", "cap", "lid", "strap", "label", "conference", "dinosaur", "shark", "silver", "white"]
LOCATION_WORDS = ["room", "hall", "lobby", "workshop", "booth", "gym", "field", "front desk", "desk"]


def _nearest_color(rgb: tuple[float, float, float]) -> str:
    best = min(COLOR_NAMES, key=lambda item: sum((rgb[i] - item[1][i]) ** 2 for i in range(3)))
    return best[0]


def _file_stem_words(image_path: str) -> list[str]:
    stem = Path(image_path).stem.lower().replace("_", " ").replace("-", " ")
    return re.findall(r"[a-z0-9]+", stem)


class MockVisionCaptioner:
    """Deterministic captioner for explicit mock mode and tests."""

    def generate_caption(self, image_path: str, found_location: str = "", staff_note: str = "") -> dict[str, str]:
        words = _file_stem_words(image_path)
        color = None
        try:
            im = Image.open(image_path).convert("RGB").resize((1, 1))
            rgb = ImageStat.Stat(im).mean[:3]
            color = _nearest_color(tuple(rgb))
        except Exception:
            pass
        file_color = next((w for w in words if w in COLOR_WORDS), None)
        color = file_color or color or "neutral-colored"
        item_type = next((w for w in words if w in ITEM_WORDS), "item")
        details = [w for w in words if w in DETAIL_WORDS and w != color]
        detail_text = ""
        if details:
            detail_text = " with " + ", ".join(dict.fromkeys(details))
        note_text = f" Staff note: {staff_note.strip()}" if staff_note.strip() else ""
        location_text = f" Found near {found_location.strip()}." if found_location.strip() else ""
        caption = f"{color.title()} {item_type}{detail_text}.{location_text}{note_text}".strip()
        privacy_note = (
            "Visible personal details may be present"
            if re.search(r"name|phone|badge|id|student|email", staff_note, re.I)
            else "No personal details were called out in the photo description"
        )
        return {"caption": caption, "privacy_note": privacy_note}


class MockTextReasoner:
    """Small rule-based assistant for demos and tests.

    The real app can set LFD_MODEL_MODE=real to use MiniCPM5. This mock keeps
    the product workflow visible when running on CPU-only machines.
    """

    def match_claim(self, claim: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
        state, candidates = rank_candidates(claim.get("summary", ""), items)
        return {
            "state": state,
            "candidates": [c.to_dict() for c in candidates],
        }

    def draft_message(self, claim: dict[str, Any], item: dict[str, Any] | None = None) -> str:
        return (
            "Staff may have a possible match for your lost item description. "
            "Please be ready to confirm any additional identifying details at pickup. "
            "The item will only be handed off after staff confirmation."
        )
