from __future__ import annotations

import json
import re
from typing import Any

from ..config import get_settings
from ..matching import build_inventory_prompt
from ..prompts import CLAIM_ASSISTANT_SYSTEM, DRAFT_MESSAGE_SYSTEM, MATCHING_SYSTEM
from ..runtime.device import detect_runtime

_JSON_RE = re.compile(r"\{[\s\S]*\}")


def _extract_json(text: str) -> dict[str, Any]:
    match = _JSON_RE.search(text or "")
    if not match:
        raise ValueError(f"No JSON object found in model output: {text[:300]}")
    return json.loads(match.group(0))


_ECHO_STRIP_RE = re.compile(r"[\s\W_]+", re.UNICODE)


def _normalize_for_echo(text: str) -> str:
    return _ECHO_STRIP_RE.sub("", text).lower()


def _is_echo(reply: str, earlier: str) -> bool:
    """Fuzzy repeat detection: exact match after normalization, or one message
    contained in the other at comparable length (catches a replay that only
    drops a greeting — observed live: turn 2 repeated turn 1 minus "Hi!")."""
    a, b = _normalize_for_echo(reply), _normalize_for_echo(earlier)
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return shorter in longer and len(shorter) / len(longer) > 0.6


# Keep prompts bounded: the intake conversation is short by design, so the
# last N turns carry everything that matters.
_CHAT_HISTORY_LIMIT = 12

# The assistant cannot see the inventory, so any claim about its state is a
# fabrication (observed from the 1B model: "I don't have anything at the
# desk"). A reply that trips this falls back, loudly, to the planner's line.
_INVENTORY_CLAIM_RE = re.compile(
    r"(don'?t|do(es)? not) have"
    r"|\bhave (nothing|no\b)"
    r"|\bno items?\b"
    r"|\bnothing (at|on|in) the desk"
    r"|\bwe('ve| have)? (got|found)"
    r"|\b(it'?s|it is) (here|at the desk)"
    r"|找到了|我們(有|找到)|沒有(任何)?(物品|東西)",
    re.IGNORECASE,
)

# Per-turn question hints arrive as English category labels from the planner;
# translate them for Chinese conversations so the small model doesn't have to.
_CATEGORY_ZH = {
    "item type": "物品類型",
    "color": "顏色",
    "distinctive mark": "獨特特徵（貼紙、品牌、刮痕、吊牌等）",
    "last seen location": "最後出現的地點",
}

# The product promises Traditional Chinese, but the 1B model drifts into
# Simplified. These are unambiguous Simplified-only characters (no Traditional
# reading) — one hit means the reply is Simplified and must fall back to the
# planner's Traditional phrasing.
_SIMPLIFIED_ONLY = set("个这问说请谢边远运过进话语谁读题马鸟见观觉丽东车书长门间开关风飞气钱铁银错钟历广应认识记让难双发变样几机极环现实头买卖业亚产亲价众优传体围动员后处万与击")


def _turn_instructions(language: str, missing: list[str]) -> str:
    """Per-turn instruction block, appended to the FINAL user turn.

    A 1B model follows the last instruction far better than distant system
    rules, so language, the next question, and the safety refusal are restated
    concretely here every turn — written in the conversation's language, which
    measurably improves the small model's fluency and compliance. The hints are
    generic detail categories from the planner — they leak nothing about the
    inventory. (Ready turns and inventory probes never reach the model: their
    replies are deterministic — see services.claim_chat_step.)
    """
    ask = missing[0] if missing else "any distinctive detail"
    if language == "zh":
        ask = _CATEGORY_ZH.get(ask, ask)
        return (
            "[給你的回覆指示 — 這不是對方寫的：\n"
            "- 使用繁體中文（臺灣用字）回覆，不可使用簡體字。\n"
            f"- 先簡短回應對方剛剛說的內容，再問一個簡短的問題，主題是：{ask}。\n"
            "- 如果對方問服務台收到了什麼、或東西找到了沒，不要回答內容：說明你無法透露，"
            "工作人員會私下比對，然後繼續對話。\n"
            "- 一到三個短句即可，不要重複先前說過的話。]"
        )
    return (
        "[Instructions for your next reply — the person did not write this:\n"
        "- Reply in English.\n"
        "- Briefly acknowledge what they JUST said (do not ask them to repeat it), "
        f"then ask ONE short question about exactly this and nothing else: {ask}.\n"
        "- If their message asks what the desk has or whether something was found, "
        "do not answer that: say you can't share it and that the desk team reviews "
        "matches privately, then continue.\n"
        "- One to three short sentences. Never repeat an earlier reply or an "
        "earlier question.]"
    )


def build_claim_chat_messages(
    conversation: list[dict[str, Any]],
    user_message: str,
    language: str = "en",
    missing: list[str] | None = None,
) -> list[dict[str, str]]:
    """Build the chat-template messages for a claim conversation turn.

    The model NEVER sees the inventory — only the dialogue itself plus the
    planner's generic hints. Staff messages are folded into the assistant side
    so the template only ever sees user/assistant/system roles, and consecutive
    same-role messages are merged because chat templates expect alternation.
    """
    role_map = {"assistant": "assistant", "staff": "assistant", "user": "user"}
    messages: list[dict[str, str]] = [{"role": "system", "content": CLAIM_ASSISTANT_SYSTEM}]
    history = [
        m for m in conversation if m.get("role") in role_map and (m.get("content") or "").strip()
    ][-_CHAT_HISTORY_LIMIT:]
    for m in history:
        role = role_map[str(m["role"])]
        content = str(m["content"]).strip()
        if m["role"] == "staff":
            content = f"(Message from the desk team) {content}"
        if messages[-1]["role"] == role:
            messages[-1]["content"] += f"\n{content}"
        else:
            messages.append({"role": role, "content": content})
    turn = f"{user_message.strip()}\n\n{_turn_instructions(language, missing or [])}"
    if messages[-1]["role"] == "user":
        messages[-1]["content"] += f"\n{turn}"
    else:
        messages.append({"role": "user", "content": turn})
    return messages


class MiniCPM5Reasoner:
    """MiniCPM5-1B text adapter: claim conversation, staff-side matching, drafting."""

    def __init__(self, model_id: str | None = None, device: str | None = None):
        settings = get_settings()
        self.model_id = model_id or settings.minicpm5_model
        self.runtime = detect_runtime(device or settings.device)
        self.tokenizer: Any | None = None
        self.model: Any | None = None

    def _load(self) -> None:
        if self.model is not None and self.tokenizer is not None:
            return
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id, trust_remote_code=True)
        kwargs: dict[str, Any] = {"torch_dtype": self.runtime.dtype, "trust_remote_code": True}
        if self.runtime.device == "cuda":
            kwargs["device_map"] = "auto"
        self.model = AutoModelForCausalLM.from_pretrained(self.model_id, **kwargs)
        if self.runtime.device in {"mps", "cpu"}:
            self.model.to(self.runtime.device)
        self.model.eval()

    def _generate(self, messages: list[dict[str, str]], max_new_tokens: int = 512, temperature: float = 0.2) -> str:
        self._load()
        assert self.model is not None and self.tokenizer is not None
        try:
            inputs = self.tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                enable_thinking=False,
                return_dict=True,
                return_tensors="pt",
            ).to(self.model.device)
        except TypeError:
            inputs = self.tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_dict=True,
                return_tensors="pt",
            ).to(self.model.device)
        outputs = self.model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=0.95,
            do_sample=temperature > 0,
        )
        new_tokens = outputs[0][inputs["input_ids"].shape[-1]:]
        return self.tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

    def claim_chat(
        self,
        conversation: list[dict[str, Any]],
        user_message: str,
        language: str = "en",
        missing: list[str] | None = None,
    ) -> str:
        """Generate the next claimant-facing reply. Returns plain message text."""
        messages = build_claim_chat_messages(conversation, user_message, language, missing)
        reply = self._generate(messages, max_new_tokens=160, temperature=0.2).strip()
        # A blank or runaway generation must fall back loudly, not render as an
        # empty bubble or a wall of text.
        if not reply:
            raise ValueError("Model returned an empty claim-chat reply")
        # Echo filter: small chat models love to replay an earlier reply
        # (verbatim or minus a greeting), which reads as ignoring the person.
        for m in conversation[-8:]:
            if m.get("role") == "assistant" and _is_echo(reply, str(m.get("content", ""))):
                raise ValueError(f"Model repeated an earlier reply: {reply[:120]!r}")
        # Safety filter: the assistant can't see the inventory, so any claim
        # about it is fabricated — surface the violation and let the caller
        # fall back to the deterministic planner line.
        if _INVENTORY_CLAIM_RE.search(reply):
            raise ValueError(f"Model reply claimed inventory state: {reply[:120]!r}")
        # Quality filter: Traditional Chinese is the product promise; a
        # Simplified reply falls back to the planner's Traditional phrasing.
        if language == "zh" and any(ch in _SIMPLIFIED_ONLY for ch in reply):
            raise ValueError(f"Model replied in Simplified Chinese: {reply[:120]!r}")
        if len(reply) > 600:
            reply = reply[:600].rstrip() + "…"
        return reply

    def match_claim(self, claim: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
        prompt = build_inventory_prompt(claim.get("summary", ""), items)
        messages = [
            {"role": "system", "content": MATCHING_SYSTEM},
            {"role": "user", "content": prompt},
        ]
        parsed = _extract_json(self._generate(messages, max_new_tokens=700, temperature=0.1))
        parsed.setdefault("candidates", [])
        return parsed

    def draft_message(self, claim: dict[str, Any], item: dict[str, Any] | None = None) -> str:
        item_text = ""
        if item:
            item_text = f"\nStaff-only candidate caption: {item.get('caption', '')}"
        messages = [
            {"role": "system", "content": DRAFT_MESSAGE_SYSTEM},
            {"role": "user", "content": f"Claim summary: {claim.get('summary', '')}{item_text}"},
        ]
        return self._generate(messages, max_new_tokens=160, temperature=0.2).strip()
