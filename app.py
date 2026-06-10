from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent / "src"))

from fastapi import File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from gradio import Server
from gradio.data_classes import FileData
from starlette.concurrency import run_in_threadpool

from lost_found_desk.config import get_settings
from lost_found_desk.conversation import SEED_MESSAGE, detect_language
from lost_found_desk.matching import rank_candidates
from lost_found_desk.runtime.gpu import maybe_zerogpu
from lost_found_desk.retrieval import cosine, rank_items_by_embedding
from lost_found_desk.schemas import (
    ChatMessage,
    Claim,
    Event,
    Item,
    ReturnLog,
    new_claim_id,
    new_event_id,
    new_id,
    now_iso,
    slugify_event_id,
)
from lost_found_desk.security import generate_staff_password, hash_password, verify_password
from lost_found_desk.seed import seed_if_empty
from lost_found_desk.services import ModelHub
from lost_found_desk.storage import JsonStore
from lost_found_desk.telemetry import get_logger, increment, setup_telemetry, shutdown_telemetry

BASE_DIR = Path(__file__).parent.resolve()
settings = get_settings()

# Initialize logging/traces/metrics before anything else logs or runs a model.
setup_telemetry()
logger = get_logger("lost_found_desk.app")

store = JsonStore(settings.db_path)
if settings.seed_sample:
    seed_if_empty(store, BASE_DIR, settings)

hub = ModelHub()

# Gradio reserves these top-level paths (plus everything under /gradio_api and
# /api); the SPA catch-all must not shadow them. See spa_fallback below.
_RESERVED_PREFIXES = (
    "api/", "gradio_api/", "assets/", "static/", "svelte/",
    "queue/", "call/", "run/", "file/", "file=",
)
_RESERVED_EXACT = {
    "config", "info", "heartbeat", "upload", "login", "logout", "theme.css",
    "robots.txt", "favicon.ico", "manifest.json", "pwa_icon", "monitoring",
}

app = Server(
    title="Lost & Found Desk",
    description="Multi-event, caption-first lost-and-found workflow with a custom frontend.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
setup_telemetry(app=app)

_assets_dir = BASE_DIR / "static" / "assets"
if _assets_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")
else:
    logger.warning(
        "static assets dir missing: %s — build the frontend (make init) before serving the SPA",
        _assets_dir,
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _staff_item_photo_url(event_id: str, item_id: str) -> str:
    return f"/api/events/{event_id}/staff/items/{item_id}/photo"


def _filedata_path(filedata: Any) -> str:
    if isinstance(filedata, dict):
        return filedata.get("path") or filedata.get("name") or ""
    path = getattr(filedata, "path", None) or getattr(filedata, "name", None)
    return str(path)


_STAFF_ONLY_CLAIM_FIELDS = ("candidates", "match_state")


def _public_claim(claim: dict[str, Any]) -> dict[str, Any]:
    """Strip staff-only fields (candidate matches) from a claimant-facing claim."""
    return {k: v for k, v in claim.items() if k not in _STAFF_ONLY_CLAIM_FIELDS}


def _filter_candidates(event_id: str, state: str, raw_candidates: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Keep only candidates that resolve to a real inventory item; never leak the
    item object, just the staff-facing fields. State is recomputed from the
    survivors so it can't claim a match with zero real candidates."""
    out: list[dict[str, Any]] = []
    for c in raw_candidates:
        item_id = c.get("item_id")
        if not item_id or not store.get_item(event_id, item_id):
            continue
        out.append(
            {k: c.get(k) for k in ("item_id", "state", "score", "reason", "staff_next_step", "safe_claimant_message")}
        )
    if not out and state in {"strong_candidate", "weak_candidate"}:
        state = "no_match"
    return state, out


def _get_event_or_404(event_id: str) -> dict[str, Any]:
    event = store.get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Event not found: {event_id}")
    return event


def _staff_password_from_request(request: Request) -> str:
    return request.headers.get("x-staff-password") or request.query_params.get("staff_password") or ""


def _require_staff(request: Request, event_id: str) -> dict[str, Any]:
    """Authorize a staff request against the per-event password (constant-time)."""
    event = _get_event_or_404(event_id)
    provided = _staff_password_from_request(request)
    if not verify_password(provided, event.get("staff_password_hash", ""), event.get("staff_password_salt", "")):
        raise HTTPException(
            status_code=401,
            detail="Staff password required for this event. Set the x-staff-password header.",
        )
    return event


def _assert_staff_password(event_id: str, password: str) -> None:
    """Password check for Gradio API endpoints (no Request object available)."""
    event = store.get_event(event_id)
    if not event or not verify_password(
        password or "", event.get("staff_password_hash", ""), event.get("staff_password_salt", "")
    ):
        raise ValueError("Invalid event or staff password")


def _save_upload_from_path(source_path: str, original_filename: str | None = None) -> tuple[str, Path]:
    src = Path(source_path)
    suffix = Path(original_filename or src.name or "item.jpg").suffix.lower() or ".jpg"
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    item_id = new_id("item")
    dest = settings.upload_dir / f"{item_id}{suffix}"
    shutil.copyfile(src, dest)
    return item_id, dest


def _unique_event_id(requested: str) -> str:
    """Return a free event id: honour a valid requested slug, else generate one."""
    slug = slugify_event_id(requested)
    if slug:
        if store.event_exists(slug):
            raise HTTPException(status_code=409, detail="That desk code is already taken — try another one.")
        return slug
    for _ in range(20):
        candidate = new_event_id()
        if not store.event_exists(candidate):
            return candidate
    raise HTTPException(status_code=500, detail="We couldn't generate a desk code — please try again.")


def _create_item_record(
    event_id: str, photo_path: Path, item_id: str, found_location: str = "", staff_note: str = ""
) -> dict[str, Any]:
    caption_result = _generate_caption_gpu(str(photo_path), found_location, staff_note)
    caption = caption_result.get("caption", "")
    item = Item(
        item_id=item_id,
        event_id=event_id,
        caption=caption,
        photo_path=str(photo_path),
        photo_url=_staff_item_photo_url(event_id, item_id),
        found_location=found_location,
        staff_note=staff_note,
        privacy_note=caption_result.get("privacy_note", "not checked"),
    )
    stored = store.add_item(event_id, item)
    # Precompute the retrieval embedding now (at caption time) so large-inventory
    # matching can shortlist top-N without re-embedding everything later.
    if settings.retrieval_enabled:
        try:
            doc_text = " ".join(t for t in [caption, found_location, staff_note] if t)
            vec = _embed_item_gpu(str(photo_path), doc_text)
            store.set_item_embedding(event_id, item_id, vec)
        except Exception:  # pragma: no cover - embedding is best-effort
            logger.warning("item embedding failed for %s (event=%s)", item_id, event_id, exc_info=True)
    return stored


def _ensure_item_embeddings(event_id: str, items: list[dict[str, Any]]) -> dict[str, list[float]]:
    embeddings = store.get_item_embeddings(event_id)
    for item in items:
        iid = item.get("item_id", "")
        if iid and iid not in embeddings:
            try:
                doc = " ".join(t for t in [item.get("caption", ""), item.get("found_location", ""), item.get("staff_note", "")] if t)
                vec = _embed_item_gpu(item.get("photo_path", ""), doc)
                store.set_item_embedding(event_id, iid, vec)
                embeddings[iid] = vec
            except Exception:  # pragma: no cover - best effort
                logger.warning("embedding failed for item %s", iid, exc_info=True)
    return embeddings


def _embedding_match(event_id: str, summary: str, items: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Multilingual semantic match via the embedding space — lets a claimant's
    description in any language retrieve an English-captioned item."""
    embeddings = _ensure_item_embeddings(event_id, items)
    query = _embed_query_gpu(summary)
    scored = sorted(((cosine(query, embeddings.get(i.get("item_id", ""), [])), i) for i in items), key=lambda t: t[0], reverse=True)
    candidates: list[dict[str, Any]] = []
    for sim, item in scored[:3]:
        # Thresholds tuned to nvidia/llama-nemotron-embed-vl-1b-v2's scale: a
        # text-query vs image+caption doc tops out ~0.7 (self), a good
        # same-language match ~0.4, a cross-language match ~0.25, and unrelated
        # ~0.06. So ~0.18 surfaces plausible (incl. cross-language) matches for
        # staff to judge, ~0.32 marks a confident one.
        state = "strong_candidate" if sim >= settings.embed_strong_threshold else "weak_candidate" if sim >= settings.embed_weak_threshold else None
        if state is None:
            continue
        candidates.append(
            {
                "item_id": item["item_id"],
                "state": state,
                "score": round(sim, 3),
                "reason": "The owner's description is close to this item record.",
                "staff_next_step": "Review the photo and description privately, then confirm in person before arranging pickup.",
                "safe_claimant_message": "Staff may have a possible item to review. Please be ready to confirm extra details at pickup.",
            }
        )
    return (candidates[0]["state"] if candidates else "no_match"), candidates


def _live_match(event_id: str, summary: str) -> tuple[str, list[dict[str, Any]]]:
    """Per-turn match against unclaimed inventory, so staff see candidates update
    live as the claimant describes their item.

    Real mode uses the multilingual embedding space (bridges Chinese↔English);
    mock/CPU uses the cheap deterministic token matcher. Either way it never
    calls the heavy chat model and falls back gracefully on error."""
    items = store.list_unclaimed_items(event_id)
    if not items:
        return "no_match", []
    if settings.retrieval_enabled and settings.model_mode == "real":
        try:
            return _embedding_match(event_id, summary, items)
        except Exception:  # pragma: no cover - fall back to token matching
            logger.warning("embedding match failed; using token matcher", exc_info=True)
    state, candidates = rank_candidates(summary, items)
    return _filter_candidates(event_id, state, [c.to_dict() for c in candidates])


def _update_claim_with_chat_result(event_id: str, claim_id: str, user_message: str) -> dict[str, Any]:
    claim = store.get_claim(event_id, claim_id)
    if not claim:
        raise ValueError(f"Claim not found: {claim_id}")
    # Real mode: the reply is generated by MiniCPM5 (GPU-wrapped for ZeroGPU),
    # guided by the inventory-aware planner; explicit mock mode answers from
    # the planner directly (see services.claim_chat_step).
    items = store.list_unclaimed_items(event_id)
    result = _claim_chat_gpu(claim.get("conversation", []), user_message, items)
    new_summary = result.get("summary", claim.get("summary", ""))
    match_state, candidates = _live_match(event_id, new_summary)
    # The chat tracks description-readiness + the live match only; it must NOT
    # touch the lifecycle status (submitting does that) so a later chat turn can
    # never demote a submitted/closed claim.
    updated = store.append_to_claim(
        event_id,
        claim_id,
        messages=[
            ChatMessage(role="user", content=user_message).to_dict(),
            ChatMessage(role="assistant", content=result.get("assistant_message", "")).to_dict(),
        ],
        summary=new_summary,
        missing_info=result.get("missing_info", []),
        readiness_state=result.get("readiness_state", "collecting"),
        candidates=candidates,
        match_state=match_state,
    )
    return {"claim": _public_claim(updated), "assistant": result}


def _claimant_photo_url(event_id: str, claim_id: str, photo_id: str) -> str:
    return f"/api/events/{event_id}/claims/{claim_id}/photos/{photo_id}"


def _find_upload_file(file_id: str) -> Path | None:
    """Locate an uploaded file by its id prefix (no stored absolute path)."""
    if not file_id or "/" in file_id or "." in file_id:
        return None
    for candidate in settings.upload_dir.glob(f"{file_id}.*"):
        if candidate.is_file():
            return candidate
    return None


def _add_claimant_photo(
    event_id: str, claim_id: str, source_path: str, original_filename: str | None = None
) -> dict[str, Any]:
    """Caption a claimant-supplied photo and fold it into their claim.

    The claimant's own MiniCPM-V caption is English-normalized like the staff
    inventory captions, so it gives staff something concrete to match against —
    which also bridges the language gap when the claimant types in another
    language.
    """
    claim = store.get_claim(event_id, claim_id)
    if not claim:
        raise ValueError(f"Claim not found: {claim_id}")
    src = Path(source_path)
    suffix = Path(original_filename or src.name or "photo.jpg").suffix.lower() or ".jpg"
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    photo_id = new_id("cphoto")
    dest = settings.upload_dir / f"{photo_id}{suffix}"
    shutil.copyfile(src, dest)

    caption_result = _generate_caption_gpu(str(dest))
    caption = caption_result.get("caption", "")
    entry = {
        "photo_id": photo_id,
        "photo_url": _claimant_photo_url(event_id, claim_id, photo_id),
        "caption": caption,
        "privacy_note": caption_result.get("privacy_note", "not checked"),
        "created_at": now_iso(),
    }
    # Detect from the claimant's own words only — the bilingual seed message
    # would otherwise force "zh" for every conversation.
    language = detect_language(
        " ".join(m.get("content", "") for m in claim.get("conversation", []) if m.get("role") == "user")
    )
    ack = (
        f"我從你上傳的照片辨識到：「{caption}」。如果有想補充的細節，也可以直接告訴我。"
        if language == "zh"
        else f"From your photo I can see: “{caption}”. Tell me anything you'd like to add."
    )
    summary = (claim.get("summary", "") + f" Photo: {caption}").strip()
    match_state, candidates = _live_match(event_id, summary)
    updated = store.append_to_claim(
        event_id,
        claim_id,
        messages=[ChatMessage(role="assistant", content=ack).to_dict()],
        photos=[entry],
        summary=summary,
        # A captioned photo is concrete, matchable evidence — let the claimant
        # submit right away (readiness only; submitting sets the lifecycle status).
        readiness_state="ready_for_staff_review",
        candidates=candidates,
        match_state=match_state,
    )
    increment("lfd.claims.photo_added", attributes={"event_id": event_id})
    logger.info("claimant added photo %s to claim %s (event=%s)", photo_id, claim_id, event_id)
    return {"claim": _public_claim(updated), "photo": entry}


def _shortlist_items(event_id: str, claim: dict[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Narrow a large inventory to the top-N by embedding similarity to the claim.

    No-op for small inventories (<= LFD_MATCH_TOPK) or when retrieval is disabled,
    so small events behave exactly as before and pay no embedding cost at match.
    """
    topk = settings.match_retrieve_topk
    if not settings.retrieval_enabled or len(items) <= topk:
        return items
    embeddings = store.get_item_embeddings(event_id)
    # Self-heal: embed any existing/seed item that lacks a stored vector.
    for item in items:
        iid = item.get("item_id", "")
        if iid and iid not in embeddings:
            try:
                doc = " ".join(t for t in [item.get("caption", ""), item.get("found_location", ""), item.get("staff_note", "")] if t)
                vec = _embed_item_gpu(item.get("photo_path", ""), doc)
                store.set_item_embedding(event_id, iid, vec)
                embeddings[iid] = vec
            except Exception:  # pragma: no cover - best effort
                logger.warning("on-demand item embedding failed for %s", iid, exc_info=True)
    query_vec = _embed_query_gpu(claim.get("summary", ""))
    shortlisted = rank_items_by_embedding(query_vec, items, embeddings, topk)
    logger.info("shortlisted %d/%d items for claim %s via embeddings", len(shortlisted), len(items), claim.get("claim_id"))
    return shortlisted


def _match_claim_for_staff(event_id: str, claim_id: str) -> dict[str, Any]:
    """Deeper, on-demand re-match (uses the model in real mode + embedding
    shortlist). Stores the result on the claim; does NOT change lifecycle status
    (the live per-turn match already keeps ``match_state`` current)."""
    claim = store.get_claim(event_id, claim_id)
    if not claim:
        raise ValueError(f"Claim not found: {claim_id}")
    items = _shortlist_items(event_id, claim, store.list_unclaimed_items(event_id))
    result = _match_claim_gpu(claim, items)
    state, candidates = _filter_candidates(event_id, result.get("state", "no_match"), result.get("candidates", []))
    store.update_claim(event_id, claim_id, candidates=candidates, match_state=state)
    increment("lfd.claims.matched", attributes={"event_id": event_id, "state": state})
    logger.info("re-matched claim %s (event=%s): state=%s candidates=%d", claim_id, event_id, state, len(candidates))
    return {"state": state, "candidates": candidates}


# --------------------------------------------------------------------------- #
# GPU-wrapped model calls (pure inference; no store access)
# --------------------------------------------------------------------------- #
@maybe_zerogpu(duration=settings.zerogpu_caption_duration)
def _generate_caption_gpu(image_path: str, found_location: str = "", staff_note: str = "") -> dict[str, str]:
    return hub.generate_caption(image_path, found_location, staff_note)


@maybe_zerogpu(duration=settings.zerogpu_text_duration)
def _claim_chat_gpu(conversation: list[dict[str, Any]], user_message: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return hub.claim_chat_step(conversation, user_message, items)


@maybe_zerogpu(duration=settings.zerogpu_text_duration)
def _match_claim_gpu(claim: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    return hub.match_claim(claim, items)


@maybe_zerogpu(duration=settings.zerogpu_text_duration)
def _draft_message_gpu(claim: dict[str, Any], item: dict[str, Any] | None = None) -> str:
    return hub.draft_message(claim, item)


@maybe_zerogpu(duration=settings.zerogpu_caption_duration)
def _embed_item_gpu(image_path: str, text: str) -> list[float]:
    return hub.embed_item(image_path, text)


@maybe_zerogpu(duration=settings.zerogpu_text_duration)
def _embed_query_gpu(text: str) -> list[float]:
    return hub.embed_query(text)


# --------------------------------------------------------------------------- #
# Gradio API endpoints (ZeroGPU-friendly; event-aware)
# --------------------------------------------------------------------------- #
@app.api(name="create_item", concurrency_limit=1)
def create_item_api(
    event_id: str, image: FileData, found_location: str = "", staff_note: str = "", staff_password: str = ""
) -> dict[str, Any]:
    """ZeroGPU-friendly item intake from the browser."""
    _assert_staff_password(event_id, staff_password)
    image_path = _filedata_path(image)
    item_id, dest = _save_upload_from_path(image_path)
    item = _create_item_record(event_id, dest, item_id, found_location, staff_note)
    increment("lfd.items.created", attributes={"event_id": event_id, "source": "gradio"})
    logger.info("created item %s (event=%s) via gradio api", item_id, event_id)
    return {"item": item}


@app.api(name="claim_chat", concurrency_limit=1)
def claim_chat_api(event_id: str, claim_id: str, user_message: str) -> dict[str, Any]:
    """Claimant-facing follow-up step with store update."""
    return _update_claim_with_chat_result(event_id, claim_id, user_message)


@app.api(name="claim_add_photo", concurrency_limit=1)
def claim_add_photo_api(event_id: str, claim_id: str, image: FileData) -> dict[str, Any]:
    """ZeroGPU-friendly claimant photo intake + captioning."""
    image_path = _filedata_path(image)
    return _add_claimant_photo(event_id, claim_id, image_path)


@app.api(name="match_claim", concurrency_limit=1)
def match_claim_api(event_id: str, claim_id: str, staff_password: str = "") -> dict[str, Any]:
    """Staff-side candidate ranking."""
    _assert_staff_password(event_id, staff_password)
    return _match_claim_for_staff(event_id, claim_id)


@app.api(name="draft_message", concurrency_limit=1)
def draft_message_api(event_id: str, claim_id: str, item_id: str = "", staff_password: str = "") -> dict[str, str]:
    """Safe handoff message drafting."""
    _assert_staff_password(event_id, staff_password)
    claim = store.get_claim(event_id, claim_id)
    if not claim:
        raise ValueError(f"Claim not found: {claim_id}")
    item = store.get_item(event_id, item_id) if item_id else None
    return {"message": _draft_message_gpu(claim, item)}


# --------------------------------------------------------------------------- #
# SPA shell
# --------------------------------------------------------------------------- #
def _read_index_html() -> str | None:
    index = BASE_DIR / "static" / "index.html"
    try:
        return index.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


_INDEX_MISSING_HTML = (
    "<!doctype html><html><body style='font-family:sans-serif;padding:2rem'>"
    "<h1>Frontend not built</h1><p>Run <code>make init</code> (or "
    "<code>cd frontend &amp;&amp; pnpm install &amp;&amp; pnpm run build</code>) to build the SPA "
    "into <code>static/</code>, then restart.</p></body></html>"
)


@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    html = _read_index_html()
    if html is None:
        return HTMLResponse(_INDEX_MISSING_HTML, status_code=503)
    return HTMLResponse(html)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "model_mode": settings.model_mode,
        "zerogpu": settings.zerogpu,
        "storage": str(settings.db_path),
        "events": len(store.list_events()),
    }


@app.get("/api/config")
async def public_config() -> dict[str, Any]:
    return {
        "app_name": settings.app_name,
        "model_mode": settings.model_mode,
        "device": settings.device,
        "zerogpu": settings.zerogpu,
        "prefer_gradio_client_for_models": settings.zerogpu,
    }


# --------------------------------------------------------------------------- #
# Event lifecycle (public — creating a help desk is self-serve)
# --------------------------------------------------------------------------- #
@app.post("/api/events")
async def create_event(request: Request) -> dict[str, Any]:
    payload = await request.json()
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Give your event a name first.")
    event_id = _unique_event_id(payload.get("event_id") or "")
    password = generate_staff_password()
    password_hash, salt = hash_password(password)
    record = store.create_event(
        Event(event_id=event_id, name=name, staff_password_hash=password_hash, staff_password_salt=salt)
    )
    increment("lfd.events.created")
    logger.info("created event %s (%r)", event_id, name)
    # The plaintext staff password is returned exactly once — it is never stored.
    return {
        "event_id": event_id,
        "name": record["name"],
        "staff_password": password,
        "staff_url": f"/e/{event_id}/staff",
        "claim_url": f"/e/{event_id}",
        "created_at": record["created_at"],
    }


@app.get("/api/events/{event_id}")
async def get_event_public(event_id: str) -> dict[str, Any]:
    event = _get_event_or_404(event_id)
    return {"event_id": event_id, "name": event.get("name", ""), "exists": True}


@app.post("/api/events/{event_id}/staff/verify")
async def verify_staff(event_id: str, request: Request) -> dict[str, Any]:
    _require_staff(request, event_id)
    event = store.get_event(event_id)
    return {"ok": True, "event_id": event_id, "name": event.get("name", "")}


# --------------------------------------------------------------------------- #
# Public claim flow (claimant-facing; no inventory, photos, or candidates)
# --------------------------------------------------------------------------- #
@app.post("/api/events/{event_id}/claims")
async def start_claim(event_id: str) -> dict[str, Any]:
    _get_event_or_404(event_id)
    claim = Claim(
        claim_id=new_claim_id(),
        event_id=event_id,
        conversation=[ChatMessage(role="assistant", content=SEED_MESSAGE).to_dict()],
        status="draft",
        readiness_state="collecting",
    )
    stored = store.add_claim(event_id, claim)
    increment("lfd.claims.started", attributes={"event_id": event_id})
    logger.info("started claim %s (event=%s)", stored["claim_id"], event_id)
    return {"claim": _public_claim(stored)}


@app.get("/api/events/{event_id}/claims/{claim_id}")
async def get_claim_public(event_id: str, claim_id: str) -> dict[str, Any]:
    _get_event_or_404(event_id)
    claim = store.get_claim(event_id, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    # Read-only: the claimant frontend computes "new staff message" by diffing
    # the conversation it has already seen, so a poll never mutates the claim
    # (which would also race a concurrently-set unread flag).
    return {"claim": _public_claim(claim)}


@app.post("/api/events/{event_id}/claims/{claim_id}/chat")
async def public_claim_chat(event_id: str, claim_id: str, request: Request) -> dict[str, Any]:
    _get_event_or_404(event_id)
    if not store.get_claim(event_id, claim_id):
        raise HTTPException(status_code=404, detail="Claim not found")
    payload = await request.json()
    user_message = (payload.get("message") or "").strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Please type a message first.")
    try:
        return await run_in_threadpool(_update_claim_with_chat_result, event_id, claim_id, user_message)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="We couldn't find that report. Check the link and try again.") from exc


@app.post("/api/events/{event_id}/claims/{claim_id}/photo")
async def public_claim_photo(
    event_id: str, claim_id: str, photo: UploadFile = File(...)
) -> dict[str, Any]:
    """Claimant uploads a photo of their own lost item; MiniCPM-V captions it."""
    _get_event_or_404(event_id)
    if not store.get_claim(event_id, claim_id):
        raise HTTPException(status_code=404, detail="Claim not found")
    suffix = Path(photo.filename or "photo.jpg").suffix.lower() or ".jpg"
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    tmp_id = new_id("tmp")
    tmp_path = settings.upload_dir / f"{tmp_id}{suffix}"
    with tmp_path.open("wb") as f:
        shutil.copyfileobj(photo.file, f)
    try:
        result = await run_in_threadpool(
            _add_claimant_photo, event_id, claim_id, str(tmp_path), photo.filename
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="We couldn't find that report. Check the link and try again.") from exc
    finally:
        tmp_path.unlink(missing_ok=True)
    return result


@app.get("/api/events/{event_id}/claims/{claim_id}/photos/{photo_id}")
async def claimant_photo(event_id: str, claim_id: str, photo_id: str):
    """Serve a claimant's own uploaded photo (knowing the claim id authorizes it)."""
    _get_event_or_404(event_id)
    claim = store.get_claim(event_id, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if not any(p.get("photo_id") == photo_id for p in claim.get("claimant_photos", [])):
        raise HTTPException(status_code=404, detail="Photo not found")
    path = _find_upload_file(photo_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Photo file not found")
    return FileResponse(str(path))


@app.post("/api/events/{event_id}/claims/{claim_id}/submit")
async def submit_claim(event_id: str, claim_id: str, request: Request) -> dict[str, Any]:
    _get_event_or_404(event_id)
    claim = store.get_claim(event_id, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    payload = await request.json()
    contact_name = (payload.get("contact_name") or "").strip()
    contact_info = (payload.get("contact_info") or "").strip()
    if not contact_info:
        raise HTTPException(status_code=400, detail="Please add a way to reach you — an email or phone number.")
    status = "ready_for_staff_review" if claim.get("readiness_state") == "ready_for_staff_review" else "needs_more_info"
    updated = store.update_claim(
        event_id, claim_id, contact_name=contact_name, contact_info=contact_info, status=status
    )
    increment("lfd.claims.submitted", attributes={"event_id": event_id, "status": status})
    logger.info("submitted claim %s (event=%s): status=%s", claim_id, event_id, status)
    return {
        "claim": _public_claim(updated),
        "message": "Thanks. Staff will review possible matches and confirm before any handoff.",
    }


# --------------------------------------------------------------------------- #
# Staff console (per-event password required)
# --------------------------------------------------------------------------- #
@app.get("/api/events/{event_id}/staff/items")
async def list_items(event_id: str, request: Request) -> dict[str, Any]:
    _require_staff(request, event_id)
    return {"items": store.list_items(event_id)}


@app.post("/api/events/{event_id}/staff/items")
async def create_item(
    event_id: str,
    request: Request,
    photo: UploadFile = File(...),
    found_location: str = Form(""),
    staff_note: str = Form(""),
) -> dict[str, Any]:
    _require_staff(request, event_id)
    suffix = Path(photo.filename or "item.jpg").suffix.lower() or ".jpg"
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    item_id = new_id("item")
    dest = settings.upload_dir / f"{item_id}{suffix}"
    with dest.open("wb") as f:
        shutil.copyfileobj(photo.file, f)
    # Captioning is CPU/GPU-bound and synchronous; run it off the event loop so a
    # slow (MPS) caption does not freeze the single-worker server.
    item = await run_in_threadpool(_create_item_record, event_id, dest, item_id, found_location, staff_note)
    increment("lfd.items.created", attributes={"event_id": event_id, "source": "rest"})
    logger.info("created item %s (event=%s, found_location=%r)", item_id, event_id, found_location)
    return {"item": item}


@app.get("/api/events/{event_id}/staff/items/{item_id}/photo")
async def staff_item_photo(event_id: str, item_id: str, request: Request):
    """Serve item photos only to authorized staff.

    Claimants never receive inventory photo URLs. The Svelte frontend fetches
    these images as authenticated blobs using the staff password header.
    """
    _require_staff(request, event_id)
    item = store.get_item(event_id, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    path = Path(item.get("photo_path", ""))
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(str(path))


@app.patch("/api/events/{event_id}/staff/items/{item_id}")
async def update_item(event_id: str, item_id: str, request: Request) -> dict[str, Any]:
    _require_staff(request, event_id)
    payload = await request.json()
    allowed = {"caption", "found_location", "staff_note", "privacy_note", "status"}
    updates = {k: v for k, v in payload.items() if k in allowed}
    if not store.get_item(event_id, item_id):
        raise HTTPException(status_code=404, detail="Item not found")
    return {"item": store.update_item(event_id, item_id, **updates)}


@app.get("/api/events/{event_id}/staff/claims")
async def list_claims(event_id: str, request: Request) -> dict[str, Any]:
    _require_staff(request, event_id)
    return {"claims": store.list_claims(event_id)}


@app.post("/api/events/{event_id}/staff/claims/{claim_id}/match")
async def staff_match_claim(event_id: str, claim_id: str, request: Request) -> dict[str, Any]:
    _require_staff(request, event_id)
    if not store.get_claim(event_id, claim_id):
        raise HTTPException(status_code=404, detail="Claim not found")
    return await run_in_threadpool(_match_claim_for_staff, event_id, claim_id)


@app.post("/api/events/{event_id}/staff/claims/{claim_id}/message")
async def staff_message_claimant(event_id: str, claim_id: str, request: Request) -> dict[str, Any]:
    """Post a staff message into the claimant's conversation (visible on resume)."""
    _require_staff(request, event_id)
    claim = store.get_claim(event_id, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    payload = await request.json()
    message = (payload.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Please type a message first.")
    updated = store.append_to_claim(
        event_id,
        claim_id,
        messages=[ChatMessage(role="staff", content=message).to_dict()],
        has_unread_staff_message=True,
    )
    increment("lfd.claims.staff_message", attributes={"event_id": event_id})
    logger.info("staff messaged claim %s (event=%s)", claim_id, event_id)
    return {"claim": updated}


@app.post("/api/events/{event_id}/staff/draft_message")
async def staff_draft_message(event_id: str, request: Request) -> dict[str, Any]:
    _require_staff(request, event_id)
    payload = await request.json()
    claim = store.get_claim(event_id, payload.get("claim_id", ""))
    item = store.get_item(event_id, payload.get("item_id", "")) if payload.get("item_id") else None
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    message = await run_in_threadpool(_draft_message_gpu, claim, item)
    return {"message": message}


@app.post("/api/events/{event_id}/staff/returns")
async def mark_returned(event_id: str, request: Request) -> dict[str, Any]:
    _require_staff(request, event_id)
    payload = await request.json()
    item_id = payload.get("item_id")
    claim_id = payload.get("claim_id")
    if not item_id or not claim_id:
        raise HTTPException(status_code=400, detail="Choose an item and a report before recording a return.")
    if not store.get_item(event_id, item_id):
        raise HTTPException(status_code=404, detail="Item not found")
    if not store.get_claim(event_id, claim_id):
        raise HTTPException(status_code=404, detail="Claim not found")
    log = ReturnLog(
        log_id=new_id("return"),
        event_id=event_id,
        item_id=item_id,
        claim_id=claim_id,
        staff_note=payload.get("staff_note", ""),
    )
    stored = store.add_return(event_id, log)
    increment("lfd.returns.recorded", attributes={"event_id": event_id})
    logger.info("recorded return %s (event=%s): item=%s claim=%s", stored["log_id"], event_id, item_id, claim_id)
    return {"return": stored}


@app.get("/api/events/{event_id}/staff/report")
async def report(event_id: str, request: Request) -> dict[str, Any]:
    _require_staff(request, event_id)
    return store.report(event_id)


@app.middleware("http")
async def spa_fallback(request: Request, call_next):
    """Serve the SPA shell for client-side routes (/e/:id, /e/:id/staff, ...).

    Implemented as middleware rather than a ``/{path:path}`` catch-all route so
    it never shadows Gradio's own GET endpoints (config/info/queue/upload/file),
    which Gradio appends to this same app at launch time. Only unmatched (404)
    GET requests to non-reserved paths fall back to index.html.
    """
    response = await call_next(request)
    if response.status_code == 404 and request.method in {"GET", "HEAD"}:
        path = request.url.path.lstrip("/")
        if not (path.startswith(_RESERVED_PREFIXES) or path in _RESERVED_EXACT):
            html = _read_index_html()
            if html is not None:
                return HTMLResponse(html)
    return response


if __name__ == "__main__":
    # HF Spaces sets PORT; Gradio defaults to 7860 locally.
    port = int(os.getenv("PORT", "7860"))
    logger.info(
        "starting Lost & Found Desk: model_mode=%s device=%s zerogpu=%s events=%d port=%d",
        settings.model_mode,
        settings.device,
        settings.zerogpu,
        len(store.list_events()),
        port,
    )
    try:
        app.launch(server_name="0.0.0.0", server_port=port, show_error=True)
    finally:
        shutdown_telemetry()
