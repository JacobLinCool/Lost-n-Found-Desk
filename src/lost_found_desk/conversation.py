"""Inventory-aware, language-aware claim-intake planner.

Each turn this looks at the *actual unclaimed inventory*, sees which items the
current description could plausibly match, and works out which attribute would
best tell those candidates apart that the claimant hasn't given yet. For
example, if the inventory has a black bottle and a blue bottle and the claimant
only said "a bottle", color is the discriminator; once the description pins
one item down (or no further detail would help), it declares the report ready.

How the output is used (see services.claim_chat_step):
- real mode — MiniCPM5 generates the visible reply; this planner supplies its
  guidance hint (the missing detail categories — generic words that leak
  nothing about the inventory) and all the bookkeeping: the summary staff
  match against (always the claimant's own words), readiness, missing chips.
- mock mode / model failure — ``assistant_message`` from here IS the reply,
  so CPU-only demos and tests keep a working conversation.
"""

from __future__ import annotations

import re
from typing import Any

from .matching import COLORS, DISTINCTIVE_HINTS, ITEM_HINTS, has_location, tokens

# Welcoming, English-first bilingual opener (the claimant's language isn't
# known yet; later turns reply in whatever language the claimant uses).
SEED_MESSAGE = (
    "Hi! Describe the item you lost — include the item type, color, where you "
    "last saw it, and any distinctive mark such as a sticker, logo, brand, "
    "damage, or contents."
)

# Hard ceiling on follow-ups so the flow can never trap a claimant.
_MAX_TURNS = 4

# Order in which we prefer to disambiguate.
_ATTR_ORDER = ("type", "color", "distinctive", "location")

# CJK ideographs + Hiragana/Katakana + CJK compatibility + full-width forms.
_CJK_RE = re.compile("[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uff00-\uffef]")

_QUESTIONS: dict[str, dict[str, list[str]]] = {
    "type": {
        "zh": ["方便先告訴我你掉的是什麼物品嗎？例如水壺、外套、背包、證件之類的。"],
        "en": ["Could you tell me what kind of item it is? For example a bottle, jacket, bag, or badge."],
    },
    "color": {
        "zh": [
            "它大概是什麼顏色呢？如果是透明或有多種顏色，也可以說說看。",
            "方便描述一下它的顏色嗎？多色或透明的話也請說一下。",
        ],
        "en": [
            "What color was it? If it's clear or has several colors, just describe what you remember.",
            "Could you describe its color? Multiple colors or transparent is fine to mention.",
        ],
    },
    "distinctive": {
        "zh": [
            "它上面有沒有什麼比較好認的記號？像是貼紙、logo、品牌、刮痕或吊牌之類的。",
            "有沒有什麼能幫忙認出它的小特徵？例如貼紙、品牌、刮痕、吊牌或內容物。",
        ],
        "en": [
            "Does it have any distinctive marks? A sticker, logo, brand, scratch, or tag, for example.",
            "Anything that would help pick it out — a sticker, brand, damage, tag, or contents?",
        ],
    },
    "location": {
        "zh": ["你大概是在哪裡最後看到它的呢？例如某個房間、大廳、攤位或座位區。"],
        "en": ["Where did you last see it? A room, hall, booth, or seating area, for example."],
    },
}

_OPENERS = {
    "zh": ["好的，", "了解，", "謝謝你～", "嗯嗯，", "收到，"],
    "en": ["Got it. ", "Thanks. ", "Okay. ", "Sure. ", "Alright. "],
}

_READY = {
    "zh": (
        "好的，這些資訊應該足夠讓現場的工作人員幫你找找看了。"
        "請在「報失狀態」面板留下你的聯絡方式並送出，我們確認後會再通知你來領取。"
    ),
    "en": (
        "Great — that should be enough for the desk team to start looking for "
        "you. Please add your contact details in the report panel and submit, "
        "and we'll let you know once it's confirmed."
    ),
}

_MISSING_LABELS = {
    "type": {"zh": "物品類型", "en": "item type"},
    "color": {"zh": "顏色", "en": "color"},
    "distinctive": {"zh": "獨特特徵", "en": "distinctive mark"},
    "location": {"zh": "最後出現地點", "en": "last seen location"},
}


def detect_language(text: str) -> str:
    """Return ``"zh"`` if the text contains CJK/Kana, else ``"en"``."""
    return "zh" if _CJK_RE.search(text or "") else "en"


# A claimant asking what the desk has (or whether their item was found) must
# get a polite, deterministic refusal — never an answer. The 1B chat model
# can't be trusted with this case (in testing it fabricated "the desk is
# empty"), so the guard runs BEFORE any model call, in every mode.
_INVENTORY_PROBE_RE = re.compile(
    r"what\b[^?.!]{0,40}\b(do|does|did)\s+(you|the desk)\s+(have|got)"
    r"|what('s| is| has been) (at|on|in) the desk"
    r"|what (have you|did you|has been) (got|found|collected|turned in|received)"
    r"|(show|list|tell) me (the |your |what )?(items|inventory|things)"
    r"|did (you|anyone|someone) (find|turn in|hand in)"
    r"|have you (got|found|seen)"
    r"|(any|some)(thing| items?)? (been )?(found|turned in|handed in)"
    r"|有(什麼|哪些|沒有)|撿到|拾獲|找到(了)?[嗎沒]|你們有",
    re.IGNORECASE,
)

INVENTORY_PROBE_REFUSAL = {
    "en": (
        "I can't share what's been turned in — the desk team compares reports "
        "with found items privately, and will message you right here."
    ),
    "zh": (
        "抱歉，我無法透露服務台目前收到了哪些物品 — 工作人員會私下比對，"
        "有任何消息都會在這裡回覆你。"
    ),
}


def is_inventory_probe(text: str) -> bool:
    """True when the claimant is asking about the inventory / match status."""
    return bool(_INVENTORY_PROBE_RE.search(text or ""))


def _count_user_turns(conversation: list[dict[str, Any]]) -> int:
    return sum(1 for m in conversation if m.get("role") == "user")


def build_summary(conversation: list[dict[str, Any]], user_message: str = "") -> str:
    """Concatenate the claimant's own words — this is what staff match against."""
    parts = [m.get("content", "") for m in conversation if m.get("role") == "user"]
    if user_message:
        parts.append(user_message)
    return " ".join(p.strip() for p in parts if p.strip()).strip()


# Common Traditional-Chinese attribute words, so a claimant typing in Chinese
# also gets credit for what they've said (and isn't re-asked for it). The item
# captions are English, so these only ever match the claimant's own text.
_ZH_TYPE = ["水壺", "瓶", "杯", "外套", "夾克", "帽", "背包", "包", "錢包", "皮夾", "鑰匙", "充電", "傳輸線",
            "證", "名牌", "雨傘", "傘", "眼鏡", "耳機", "筆電", "手機", "平板", "卡"]
_ZH_COLOR = ["黑", "白", "藍", "紅", "綠", "黃", "灰", "銀", "金", "棕", "咖啡", "紫", "粉", "橘", "透明"]
_ZH_DISTINCT = ["貼紙", "標誌", "品牌", "刮痕", "刮", "吊牌", "標籤", "圖案", "凹", "破", "記號", "字樣", "內容"]
_ZH_LOCATION = ["室", "廳", "樓", "攤位", "座位", "會議", "教室", "球場", "櫃台", "櫃檯", "桌"]


def _attributes_in(text: str) -> dict[str, bool]:
    t = tokens(text)
    low = text or ""
    return {
        "type": bool(t & ITEM_HINTS) or any(w in low for w in _ZH_TYPE),
        "color": bool(t & COLORS) or any(w in low for w in _ZH_COLOR),
        "distinctive": bool(t & DISTINCTIVE_HINTS) or any(w in low for w in _ZH_DISTINCT),
        "location": has_location(text) or any(w in low for w in _ZH_LOCATION),
    }


def _item_text(item: dict[str, Any]) -> str:
    return " ".join([item.get("caption", ""), item.get("found_location", ""), item.get("staff_note", "")])


def _candidate_pool(summary: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Unclaimed items whose caption overlaps the description; all of them if the
    description is still too thin to overlap anything."""
    unclaimed = [i for i in items if i.get("status") == "unclaimed"]
    claim_t = tokens(summary)
    overlapping = [i for i in unclaimed if tokens(_item_text(i)) & claim_t]
    return overlapping or unclaimed


def _pick_question(language: str, attr: str, turn: int) -> str:
    variants = _QUESTIONS[attr][language]
    return variants[turn % len(variants)]


def _asked_attrs(conversation: list[dict[str, Any]]) -> set[str]:
    """Which attributes we've already asked about, recovered from the assistant
    messages — so we never repeat a question even when the claimant's answer
    wasn't machine-parseable (e.g. typed in another language)."""
    asked: set[str] = set()
    for m in conversation:
        if m.get("role") != "assistant":
            continue
        content = m.get("content", "")
        for attr, langs in _QUESTIONS.items():
            if any(v in content for variants in langs.values() for v in variants):
                asked.add(attr)
    return asked


def plan_turn(
    conversation: list[dict[str, Any]], user_message: str, items: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Compute the next intake step from the conversation and the live inventory."""
    items = items or []
    asked = _count_user_turns(conversation)  # answers given before this message
    # Detect from the claimant's own words only — the bilingual seed message
    # (and any staff text) would otherwise force "zh" for every conversation.
    language = detect_language(
        " ".join([m.get("content", "") for m in conversation if m.get("role") == "user"] + [user_message])
    )
    summary = build_summary(conversation, user_message)

    given = _attributes_in(summary)
    pool = _candidate_pool(summary, items)
    if pool:
        # Only ask about attributes the candidate items actually carry.
        pool_attrs = _attributes_in(" ".join(_item_text(i) for i in pool))
    else:
        # No inventory to disambiguate against — collect a basic description.
        pool_attrs = {"type": True, "color": True, "distinctive": True, "location": False}

    # Ordered discriminators the candidate items carry (derived from the English
    # item captions, so reliable regardless of the claimant's language). Capped
    # so the claimant is never asked more than a few quick questions.
    discs = [a for a in _ATTR_ORDER if pool_attrs.get(a)][:3]
    asked_attrs = _asked_attrs(conversation)
    # Still worth asking: a discriminator the claimant hasn't given AND we
    # haven't already asked about. Skipping already-asked attributes is what
    # guarantees progress without repeats, in any language.
    unmet = [a for a in discs if not given[a] and a not in asked_attrs]

    if not unmet or asked >= _MAX_TURNS:
        return {
            "target": "ready",
            "language": language,
            "assistant_message": _READY[language],
            "summary": summary,
            "missing_info": [],
            "readiness_state": "ready_for_staff_review",
        }

    attr = unmet[0]
    opener = _OPENERS[language][asked % len(_OPENERS[language])]
    message = f"{opener}{_pick_question(language, attr, asked)}"
    return {
        "target": attr,
        "language": language,
        "assistant_message": message,
        "summary": summary,
        # Always English: these render inside UI chrome (status chips), where
        # only the conversational messages mirror the claimant's language.
        "missing_info": [_MISSING_LABELS[a]["en"] for a in unmet],
        "readiness_state": "collecting",
    }
