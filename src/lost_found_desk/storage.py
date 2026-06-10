from __future__ import annotations

import json
import shutil
from pathlib import Path
from threading import RLock
from typing import Any

from .schemas import Claim, Event, Item, ReturnLog, now_iso

SCHEMA_VERSION = 2


class JsonStore:
    """Small multi-event JSON store for a hackathon/demo Space.

    The document is keyed by event so each lost-and-found desk (one per real
    event/activity) is fully isolated::

        {
          "version": 2,
          "events": {
            "<event_id>": {
              "event_id", "name", "staff_password_hash", "staff_password_salt",
              "created_at", "items": [...], "claims": [...], "returns": [...]
            }
          }
        }

    It intentionally avoids a database service so the app can run on HF Spaces,
    ZeroGPU, local CUDA, and Mac MPS with the same code. For production, replace
    this class with SQLite/Postgres while keeping the method surface unchanged.

    Single writes are serialized through a reentrant lock. For read-modify-write
    sequences that append to a list (conversation, claimant photos), callers must
    use the atomic ``append_to_claim`` helper rather than read-then-``update_claim``
    with a snapshot, otherwise concurrent appends can lose each other.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = RLock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.db_path.exists():
            self._write({"version": SCHEMA_VERSION, "events": {}})

    # ----------------------------------------------------------------- I/O
    def _read(self) -> dict[str, Any]:
        with self._lock:
            with self.db_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        data.setdefault("version", SCHEMA_VERSION)
        data.setdefault("events", {})
        return data

    def _write(self, data: dict[str, Any]) -> None:
        with self._lock:
            tmp = self.db_path.with_suffix(".tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            shutil.move(str(tmp), str(self.db_path))

    @staticmethod
    def _event(data: dict[str, Any], event_id: str) -> dict[str, Any]:
        event = data.get("events", {}).get(event_id)
        if event is None:
            raise KeyError(f"Event not found: {event_id}")
        event.setdefault("items", [])
        event.setdefault("claims", [])
        event.setdefault("returns", [])
        event.setdefault("item_embeddings", {})
        return event

    # -------------------------------------------------------------- events
    def event_exists(self, event_id: str) -> bool:
        return event_id in self._read().get("events", {})

    def create_event(self, event: Event) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            events = data.setdefault("events", {})
            if event.event_id in events:
                raise ValueError(f"Event already exists: {event.event_id}")
            record = event.to_dict()
            record["items"] = []
            record["claims"] = []
            record["returns"] = []
            events[event.event_id] = record
            self._write(data)
            return record

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        """Full event record including password hash (internal/auth use only)."""
        return self._read().get("events", {}).get(event_id)

    def list_events(self) -> list[dict[str, Any]]:
        events = self._read().get("events", {}).values()
        out = [
            {"event_id": e.get("event_id"), "name": e.get("name"), "created_at": e.get("created_at")}
            for e in events
        ]
        return sorted(out, key=lambda x: x.get("created_at", ""), reverse=True)

    # --------------------------------------------------------------- items
    def list_items(self, event_id: str, include_archived: bool = False) -> list[dict[str, Any]]:
        items = self._event(self._read(), event_id)["items"]
        if not include_archived:
            items = [i for i in items if i.get("status") != "archived"]
        return sorted(items, key=lambda x: x.get("created_at", ""), reverse=True)

    def list_unclaimed_items(self, event_id: str) -> list[dict[str, Any]]:
        return [i for i in self.list_items(event_id) if i.get("status") == "unclaimed"]

    def add_item(self, event_id: str, item: Item) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            self._event(data, event_id)["items"].append(item.to_dict())
            self._write(data)
            return item.to_dict()

    def get_item(self, event_id: str, item_id: str) -> dict[str, Any] | None:
        for item in self._event(self._read(), event_id)["items"]:
            if item.get("item_id") == item_id:
                return item
        return None

    def update_item(self, event_id: str, item_id: str, **updates: Any) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            for item in self._event(data, event_id)["items"]:
                if item.get("item_id") == item_id:
                    item.update(updates)
                    item["updated_at"] = now_iso()
                    self._write(data)
                    return item
            raise KeyError(f"Item not found: {item_id}")

    # -------------------------------------------------------------- claims
    def list_claims(self, event_id: str) -> list[dict[str, Any]]:
        claims = self._event(self._read(), event_id)["claims"]
        return sorted(claims, key=lambda x: x.get("created_at", ""), reverse=True)

    def add_claim(self, event_id: str, claim: Claim) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            self._event(data, event_id)["claims"].append(claim.to_dict())
            self._write(data)
            return claim.to_dict()

    def get_claim(self, event_id: str, claim_id: str) -> dict[str, Any] | None:
        for claim in self._event(self._read(), event_id)["claims"]:
            if claim.get("claim_id") == claim_id:
                return claim
        return None

    def update_claim(self, event_id: str, claim_id: str, **updates: Any) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            for claim in self._event(data, event_id)["claims"]:
                if claim.get("claim_id") == claim_id:
                    claim.update(updates)
                    claim["updated_at"] = now_iso()
                    self._write(data)
                    return claim
            raise KeyError(f"Claim not found: {claim_id}")

    def append_to_claim(
        self,
        event_id: str,
        claim_id: str,
        *,
        messages: list[dict[str, Any]] | None = None,
        photos: list[dict[str, Any]] | None = None,
        **updates: Any,
    ) -> dict[str, Any]:
        """Atomically append to conversation/claimant_photos and apply updates.

        The append re-reads the *current* stored lists inside the lock, so two
        concurrent appends (e.g. a claimant chat turn and a staff message) both
        land instead of one overwriting the other's snapshot.
        """
        with self._lock:
            data = self._read()
            for claim in self._event(data, event_id)["claims"]:
                if claim.get("claim_id") == claim_id:
                    if messages:
                        claim.setdefault("conversation", []).extend(messages)
                    if photos:
                        claim.setdefault("claimant_photos", []).extend(photos)
                    for k, v in updates.items():
                        claim[k] = v
                    claim["updated_at"] = now_iso()
                    self._write(data)
                    return claim
            raise KeyError(f"Claim not found: {claim_id}")

    # --------------------------------------------------------- embeddings
    def get_item_embeddings(self, event_id: str) -> dict[str, list[float]]:
        return dict(self._event(self._read(), event_id)["item_embeddings"])

    def set_item_embedding(self, event_id: str, item_id: str, vector: list[float]) -> None:
        with self._lock:
            data = self._read()
            self._event(data, event_id)["item_embeddings"][item_id] = vector
            self._write(data)

    # ------------------------------------------------------------- returns
    def add_return(self, event_id: str, log: ReturnLog) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            event = self._event(data, event_id)
            event["returns"].append(log.to_dict())
            for item in event["items"]:
                if item.get("item_id") == log.item_id:
                    item["status"] = "returned"
                    item["updated_at"] = now_iso()
            for claim in event["claims"]:
                if claim.get("claim_id") == log.claim_id:
                    claim["status"] = "closed"
                    claim["updated_at"] = now_iso()
            self._write(data)
            return log.to_dict()

    def list_returns(self, event_id: str) -> list[dict[str, Any]]:
        returns = self._event(self._read(), event_id)["returns"]
        return sorted(returns, key=lambda x: x.get("created_at", ""), reverse=True)

    # -------------------------------------------------------------- report
    def report(self, event_id: str) -> dict[str, Any]:
        event = self._event(self._read(), event_id)
        items = event["items"]
        claims = event["claims"]
        returns = event["returns"]
        return {
            "event_id": event_id,
            "event_name": event.get("name", ""),
            "items_catalogued": len(items),
            "unclaimed_items": len([i for i in items if i.get("status") == "unclaimed"]),
            "returned_items": len([i for i in items if i.get("status") == "returned"]),
            "claims_received": len(claims),
            "claims_ready_for_review": len([c for c in claims if c.get("status") == "ready_for_staff_review"]),
            "claims_need_more_info": len([c for c in claims if c.get("status") in {"draft", "needs_more_info"}]),
            "handoff_logs": len(returns),
            "auto_ownership_decisions": 0,
            "public_photo_exposures": 0,
            "claimant_visible_ranked_candidates": 0,
            "returns": returns,
        }
