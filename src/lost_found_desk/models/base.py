from __future__ import annotations

from typing import Any, Protocol


class VisionCaptioner(Protocol):
    def generate_caption(self, image_path: str, found_location: str = "", staff_note: str = "") -> dict[str, str]:
        ...


class TextReasoner(Protocol):
    # Staff-side matching and message drafting are required of every adapter.
    # The claimant conversation is real-mode only: MiniCPM5 additionally
    # implements ``claim_chat(conversation, user_message, guidance)``. Mock mode
    # answers from the deterministic planner in ``conversation.plan_turn``; see
    # services.claim_chat_step.
    def match_claim(self, claim: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
        ...

    def draft_message(self, claim: dict[str, Any], item: dict[str, Any] | None = None) -> str:
        ...
