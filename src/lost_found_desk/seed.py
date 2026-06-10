from __future__ import annotations

from pathlib import Path

from .config import Settings
from .schemas import ChatMessage, Claim, Event, Item
from .security import hash_password
from .storage import JsonStore


def _photo_url(event_id: str, item_id: str) -> str:
    return f"/api/events/{event_id}/staff/items/{item_id}/photo"


SAMPLE_ITEMS = [
    {
        "item_id": "item_black_bottle",
        "photo": "black_bottle_conference_sticker.png",
        "caption": "Black insulated water bottle with a silver cap and a white conference sticker. Found near Workshop Room B.",
        "found_location": "Workshop Room B",
        "privacy_note": "no visible identifying text detected",
    },
    {
        "item_id": "item_blue_bottle",
        "photo": "blue_bottle_dinosaur_sticker.png",
        "caption": "Blue plastic water bottle with a white lid and a dinosaur sticker on the front. Found near the soccer field bench.",
        "found_location": "Soccer field bench",
        "privacy_note": "no visible identifying text detected",
    },
    {
        "item_id": "item_navy_hoodie",
        "photo": "navy_hoodie_small_logo.png",
        "caption": "Navy hoodie with a small white logo on the left chest. Found in the lobby seating area.",
        "found_location": "Lobby seating area",
        "privacy_note": "no visible identifying text detected",
    },
    {
        "item_id": "item_usb_c_charger",
        "photo": "white_usb_c_charger.png",
        "caption": "White USB-C laptop charger with a long cable and small gray scuff marks. Found in Hall A under a chair.",
        "found_location": "Hall A",
        "privacy_note": "no visible identifying text detected",
    },
    {
        "item_id": "item_badge_lanyard",
        "photo": "red_badge_lanyard_visible_text.png",
        "caption": "Red conference lanyard with a plastic badge holder; visible identifying text present. Found at the front desk.",
        "found_location": "Front desk",
        "privacy_note": "visible identifying text present",
    },
]

SAMPLE_CLAIMS = [
    {
        "claim_id": "claim_black_bottle",
        "summary": "Lost item: black bottle, probably in Workshop Room B, with a white conference sticker and silver cap.",
        "conversation": [
            ChatMessage(role="assistant", content="What did you lose?").to_dict(),
            ChatMessage(role="user", content="I lost a black bottle, maybe in Room B.").to_dict(),
            ChatMessage(role="assistant", content="Do you remember any sticker, logo, cap color, brand, scratch, or other distinctive mark?").to_dict(),
            ChatMessage(role="user", content="It had a white conference sticker and a silver cap.").to_dict(),
        ],
        "status": "ready_for_staff_review",
        "readiness_state": "ready_for_staff_review",
        "contact_name": "Demo Attendee",
        "contact_info": "demo@example.com",
    }
]


def seed_if_empty(store: JsonStore, base_dir: Path, settings: Settings) -> None:
    """Create a reproducible demo event on first boot so reviewers have data.

    Real events are created at runtime through the UI/API; this only ensures the
    configured demo event (``LFD_SEED_EVENT_ID``) exists with sample inventory
    and a known staff password (``LFD_SEED_STAFF_PASSWORD``).
    """
    event_id = settings.seed_event_id
    if store.event_exists(event_id):
        return

    password_hash, salt = hash_password(settings.seed_staff_password)
    store.create_event(
        Event(
            event_id=event_id,
            name=settings.seed_event_name,
            staff_password_hash=password_hash,
            staff_password_salt=salt,
        )
    )

    for sample in SAMPLE_ITEMS:
        item = Item(
            item_id=sample["item_id"],
            event_id=event_id,
            caption=sample["caption"],
            photo_url=_photo_url(event_id, sample["item_id"]),
            photo_path=str(base_dir / "sample_data" / "photos" / sample["photo"]),
            found_location=sample["found_location"],
            privacy_note=sample["privacy_note"],
            status="unclaimed",
        )
        store.add_item(event_id, item)

    for sample in SAMPLE_CLAIMS:
        claim = Claim(
            claim_id=sample["claim_id"],
            event_id=event_id,
            conversation=sample["conversation"],
            summary=sample["summary"],
            status=sample["status"],
            readiness_state=sample["readiness_state"],
            contact_name=sample["contact_name"],
            contact_info=sample["contact_info"],
        )
        store.add_claim(event_id, claim)
