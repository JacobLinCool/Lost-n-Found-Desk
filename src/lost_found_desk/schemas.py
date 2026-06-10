from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Literal


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(5)}"


def new_claim_id() -> str:
    """A claim id doubles as the claimant's private capability token (it grants
    access to their PII/conversation), so it needs to be unguessable — ~144 bits
    of entropy, not the short internal-id form."""
    return f"claim_{secrets.token_urlsafe(18)}"


# Unambiguous alphabet (no 0/O/1/I/L) for human-shareable event codes.
_EVENT_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def new_event_id(length: int = 6) -> str:
    """A short, URL- and QR-friendly event code that is easy to read aloud."""
    return "".join(secrets.choice(_EVENT_ALPHABET) for _ in range(length))


def slugify_event_id(raw: str) -> str:
    """Normalize a staff-supplied event id into a safe slug, or '' if unusable."""
    slug = _SLUG_RE.sub("-", (raw or "").strip().lower()).strip("-")
    return slug[:48]


ItemStatus = Literal["unclaimed", "candidate", "returned", "archived"]
ClaimStatus = Literal["draft", "ready_for_staff_review", "matched", "needs_more_info", "closed"]
CandidateState = Literal["strong_candidate", "weak_candidate", "needs_more_info", "no_match"]
# "staff" messages are written by staff to the claimant and surface in the
# claimant's resume view; "assistant" is the automated intake helper.
ChatRole = Literal["assistant", "user", "system", "staff"]


@dataclass
class Event:
    event_id: str
    name: str
    staff_password_hash: str
    staff_password_salt: str
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def public_dict(self) -> dict[str, Any]:
        """Event view safe for unauthenticated claimants (no secrets)."""
        return {"event_id": self.event_id, "name": self.name, "created_at": self.created_at}


@dataclass
class Item:
    item_id: str
    event_id: str
    caption: str
    photo_url: str
    photo_path: str
    found_location: str = ""
    staff_note: str = ""
    privacy_note: str = "not checked"
    status: ItemStatus = "unclaimed"
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ChatMessage:
    role: ChatRole
    content: str
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Claim:
    claim_id: str
    event_id: str
    conversation: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    missing_info: list[str] = field(default_factory=list)
    readiness_state: str = "collecting"
    contact_name: str = ""
    contact_info: str = ""
    # Photos the claimant uploaded of their *own* lost item, captioned by
    # MiniCPM-V to enrich matching. Each entry: {photo_id, photo_url, caption,
    # privacy_note, created_at}. These belong to the claimant (unlike inventory
    # photos, which are staff-only).
    claimant_photos: list[dict[str, Any]] = field(default_factory=list)
    # Staff-only live match result, recomputed as the description evolves.
    # Stripped from the claimant-facing payload (claimants never see candidates).
    candidates: list[dict[str, Any]] = field(default_factory=list)
    match_state: str = ""
    status: ClaimStatus = "draft"
    # True once the claimant has read the latest staff message (resume view).
    has_unread_staff_message: bool = False
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Candidate:
    item_id: str
    state: CandidateState
    reason: str
    staff_next_step: str
    safe_claimant_message: str
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReturnLog:
    log_id: str
    event_id: str
    item_id: str
    claim_id: str
    staff_note: str = ""
    handoff_method: str = "offline_staff_confirmation"
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
