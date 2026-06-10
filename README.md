---
title: Lost & Found Desk
emoji: 🧾
colorFrom: indigo
colorTo: amber
sdk: gradio
sdk_version: 6.17.3
app_file: app.py
python_version: 3.12.12
pinned: false
tags:
  - track:backyard
  - sponsor:openbmb
  - sponsor:openai
  - sponsor:nvidia
  - achievement:offgrid
  - achievement:offbrand
  - achievement:fieldnotes
---

# Lost & Found Desk

- **Live Space:** https://huggingface.co/spaces/build-small-hackathon/lost-found-desk
- **App URL:** https://build-small-hackathon-lost-found-desk.hf.space
- **Demo video:** https://huggingface.co/spaces/build-small-hackathon/lost-found-desk/resolve/main/demo/lost-found-desk-demo.mp4
- **GitHub:** https://github.com/JacobLinCool/Lost-n-Found-Desk
- **Social post:** pending manual publication; draft is in [`docs/social-post.md`](docs/social-post.md).

Lost & Found Desk is a **caption-first return desk** for conferences, event venues, gyms, coworking spaces, schools, and any front desk that accumulates forgotten bottles, badges, chargers, jackets, bags, keys, and accessories.

It is **multi-event**: anyone can create an independent help desk for their own event and gets a short event code plus an auto-generated staff password. Each event has three **fully separated** surfaces — a public home page, a claimant-facing report flow, and a password-gated staff console — so claimants and staff never share a screen.

Staff photograph **one item per photo**. MiniCPM-V writes a searchable caption. Claimants describe their lost item through a private, **language-aware** Claim Assistant (it replies in the claimant's own language — Traditional Chinese, English, …) and may optionally **upload a photo of their own lost item**, which MiniCPM-V captions to strengthen matching. MiniCPM5 compares the refined claim against the live inventory for staff review. Staff can post messages back into the claimant's thread, and the final handoff is always confirmed by staff offline.

The app deliberately does **not**:

- segment table photos;
- run a separate OCR pipeline;
- build an embedding index in the MVP;
- expose item photos to claimants;
- show ranked candidates to claimants;
- let AI decide ownership.

## Default runtime

The default is now the real model path:

```bash
uv run python app.py
```

Equivalent explicit settings:

```bash
LFD_MODEL_MODE=real LFD_DEVICE=auto uv run python app.py
```

`LFD_DEVICE=auto` resolves ZeroGPU/CUDA/MPS/CPU in one place. Mock mode is available only as an explicit path for tests and CPU-only UI review:

```bash
LFD_MODEL_MODE=mock uv run python app.py
```

Real-model failures surface by default (`LFD_ALLOW_MOCK_FALLBACK=0`). Set `LFD_ALLOW_MOCK_FALLBACK=1` only when you deliberately want the rule-based mock path for local resilience testing.

## Multi-event model & roles

The store is keyed by event; each event owns its own items, claims, and returns,
and its staff password is stored only as a salted PBKDF2 hash. The three surfaces
are routed client-side:

```text
/                       Home — create an event, or enter an existing one
/e/{event_id}           Public claim — start or resume a lost-item report
/e/{event_id}/c/{id}    Public claim — a specific report (the resume link)
/e/{event_id}/staff     Staff console — password-gated (per event)
```

Creating an event returns its staff password **once**; it is never stored in
plaintext. Claimants reach `/e/{event_id}` via a shared link/QR and get a unique
resume link (`/e/{event_id}/c/{claim_id}`) to come back and check staff replies.

## Demo event

On first boot a reproducible demo event is seeded so reviewers have data:

```text
event code:     demo        (LFD_SEED_EVENT_ID)
staff password: demo-pass    (LFD_SEED_STAFF_PASSWORD)
staff console:  /e/demo/staff
```

Set `LFD_SEED_SAMPLE=0` to skip seeding, or change the seed values via env.

## Core workflow

```text
one item photo
  -> MiniCPM-V caption
  -> item inventory
  -> Claim Assistant conversation
  -> MiniCPM5 prompt-packed inventory search
  -> staff-only match review
  -> safe draft message
  -> offline handoff log
```

## Surfaces

**Home** (`/`) — create an event (name + optional custom code), or enter an
existing event as staff (code + password) or as a claimant (code).

**Public claim** (`/e/{event_id}`) — claimant-only. A conversational, language-
aware intake; optional photo upload of the claimant's own item; a running
summary; a contact-info submit; a prominent "save this link" resume box; and any
staff messages shown inline. No inventory photos, candidates, or ownership
decisions are ever exposed here.

**Staff console** (`/e/{event_id}/staff`) — password-gated tabs:

1. **Overview** — counts, recent items, open claims, the shareable public link.
2. **Add items** — one item, one photo, found location, optional note, generated caption.
3. **Claims (Inbox + Match)** — review claims (including claimant-uploaded photos), run candidate matching, draft + send a message to the claimant, mark returned after offline confirmation.
4. **Report** — returned items, safety counters, JSON export.

### Claim conversation (model-driven, inventory-guided)

In real mode the English collecting-phase replies are **generated by
MiniCPM5** — the assistant acknowledges what the claimant said and asks the
next useful question in its own words. The model never sees the inventory; it
only receives the dialogue plus a per-turn hint from the deterministic,
**inventory-aware planner** (`conversation.plan_turn`).

The planner runs on every turn regardless of mode and owns the bookkeeping: it
looks at which unclaimed items the current description could match and works
out whatever attribute best tells those candidates apart and that the claimant
hasn't given yet — so the model's questions are **guided by the live
inventory, never a fixed script**, while leaking nothing (a hint like "still
missing: color" is generic). If the inventory has a black bottle and a blue
bottle and the claimant only said "a bottle", color is the next question;
once the description pins one item down (or no further detail would help), the
report is declared ready. The matching summary always stays the claimant's own
words (never model prose), and readiness/missing-info chips stay deterministic
so the submit gate can't flap with model mood.

Guardrails around the 1B model (each violation is surfaced; when the explicit
fallback flag is enabled it is recorded as `outcome=fallback` in telemetry):

- replies claiming inventory state ("the desk has nothing") are rejected;
- verbatim repeats of an earlier reply are rejected;
- inventory probes ("what do you have?") never reach the model — they get a
  fixed safe refusal plus the next question;
- the ready turn's call to action stays product copy;
- Traditional-Chinese conversations use the planner's native-quality phrasing
  end-to-end (MiniCPM5-1B's zh chat output proved unshippable: broken
  sentences and Simplified drift).

In mock mode (CPU-only review, tests) the planner's own bilingual phrasing is
the reply everywhere, so the workflow never stalls. It understands common
English and Traditional-Chinese attribute words and tracks which attributes it
has already asked about, so it never repeats in any language.

Matching runs **continuously during the conversation** — candidates are stored on
the claim so staff see them automatically, with no required button press (a
"Re-run match" button re-runs a deeper match, e.g. after staff add new inventory). In
real mode the live match uses the multilingual embedding space, so a Chinese
description can retrieve an English-captioned item; mock/CPU uses the token
matcher. Candidates are **stripped from the claimant-facing payload** — claimants
never see candidates, scores, or item details.

The intake chat only updates the *description-readiness* signal; it never sets
the claim's lifecycle status. **Submitting** (which requires contact info) is the
action that marks a claim ready for staff — so staff never see a "ready" claim
they cannot contact, and a later chat turn can never demote a claim staff already
matched.

### Scaling matching with embeddings (retrieve-then-rerank)

Packing every caption into the matching prompt does not scale. When an event's
unclaimed inventory exceeds `LFD_MATCH_TOPK` (default 10), matching first narrows
to the top-N by embedding similarity to the claimant's description, then runs the
LLM/ranker on that shortlist only:

- At intake (caption time) each item is embedded with NVIDIA's multilingual
  vision-language model `nvidia/llama-nemotron-embed-vl-1b-v2` (photo + caption,
  2048-d) and the vector is stored per-event (never shipped to the frontend).
- At match time the claimant's description is embedded as a text query in the
  same space; the top-N items are kept. Because the space is multilingual and
  cross-modal, a Chinese description can retrieve an English-captioned item.
- Small events (≤ `LFD_MATCH_TOPK`) are unaffected and pay no embedding cost.
- Explicit mock mode uses a deterministic embedder for CPU/offline tests, and
  missing real embeddings self-heal on demand.

```bash
LFD_MATCH_TOPK=10          # shortlist size / threshold for triggering retrieval
LFD_RETRIEVAL=0            # disable embedding shortlisting entirely
LFD_EMBED_MODEL=nvidia/llama-nemotron-embed-vl-1b-v2
```

### Claimant resume link is a secret

A `claim_id` is a high-entropy (~144-bit) capability token: knowing the event
code + claim id grants access to that claim's conversation, contact info, and
photos. Treat the resume link (`/e/{event_id}/c/{claim_id}`) as a secret; do not
post it publicly. A production deployment should add per-IP rate limiting on the
public claim endpoints.

## Official runtime pass

This repo was updated to match the current official docs as of 2026-06-14:

| Layer | Choice in this repo | Why |
| --- | --- | --- |
| Gradio | `gradio==6.17.3` | Current PyPI release; Space metadata pins the same `sdk_version`. |
| Gradio Server mode | `gradio.Server` + `@app.api()` | Gives FastAPI routes plus Gradio API queue/concurrency/ZeroGPU behavior. |
| ZeroGPU | `spaces>=0.50.4`, `@spaces.GPU` via `maybe_zerogpu()` | GPU-dependent calls are wrapped only when `ZEROGPU=1`; in ZeroGPU mode the real MiniCPM adapters are eagerly loaded at app startup to match the ZeroGPU model-loading recommendation. |
| MiniCPM-V | `openbmb/MiniCPM-V-4.6` through `AutoProcessor` + `AutoModelForImageTextToText` | Matches the model card's Transformers path. |
| MiniCPM5 | `openbmb/MiniCPM5-1B` through `AutoTokenizer` + `AutoModelForCausalLM` | Matches the model card's standard `LlamaForCausalLM` path. |
| Frontend | Svelte 5 + Vite 8 + `@gradio/client` | The compiled Svelte app is committed into `static/` so the Space needs no Node build step. |

The built frontend uses normal REST routes for CRUD. Staff item photos are fetched as authenticated blobs from staff-only routes, so the public Claim Assistant never receives inventory photo URLs. When the Space reports ZeroGPU, the frontend switches model-heavy actions to Gradio API endpoints through `@gradio/client`, which is the official browser path for Server mode + ZeroGPU quota handling.

## Hackathon submission fit

Lost & Found Desk targets **Backyard AI**: it is a practical, local-first workflow for a real front-desk problem. It uses only models below the 32B cap:

| Model | Role | Parameter fit |
| --- | --- | --- |
| `openbmb/MiniCPM-V-4.6` | Staff and claimant photo captioning | Listed by the hackathon kit as about 1.3B. |
| `openbmb/MiniCPM5-1B` | Claim intake, matching, safe staff messaging | 1B. |
| `nvidia/llama-nemotron-embed-vl-1b-v2` | Multilingual vision-language retrieval shortlist | 1B-class embed model. |

Requested official tags:

- `track:backyard`
- `sponsor:openbmb` — MiniCPM-V and MiniCPM5 are core to the experience.
- `sponsor:openai` — Codex was used for final hardening, documentation, deployment prep, and Codex-attributed commits.
- `sponsor:nvidia` — Nemotron Embed is used for multilingual cross-modal retrieval.
- `achievement:offgrid` — the app does not depend on hosted model APIs.
- `achievement:offbrand` — the UI is a compiled Svelte product surface served through `gradio.Server`, not stock Gradio components.
- `achievement:fieldnotes` — the write-up and submission notes are in [`docs/article.md`](docs/article.md) and [`docs/submission-notes.md`](docs/submission-notes.md).

The project also fits the prize-table spirit of **Tiny Titan** because every model is at or below roughly 4B parameters. The official README tag generator does not expose a `tiny` tag, so this is documented here instead of inventing a non-official tag.

## Install locally

```bash
uv sync
uv run python app.py
```

Open:

```text
http://localhost:7860
```

Mac MPS:

```bash
PYTORCH_ENABLE_MPS_FALLBACK=1 LFD_DEVICE=mps uv run python app.py
```

Local CUDA:

```bash
LFD_DEVICE=cuda uv run python app.py
```

Hugging Face ZeroGPU:

1. Create a Gradio SDK Space.
2. Select ZeroGPU hardware in Space settings.
3. Keep the repo default `LFD_MODEL_MODE=real` and `LFD_DEVICE=auto`.
4. Keep `LFD_ALLOW_MOCK_FALLBACK=0` for judge-facing validation.

## Frontend development

The production Space serves the compiled Svelte frontend in `static/`.

The frontend is written in **TypeScript** (Svelte 5 `<script lang="ts">` + typed
API/model interfaces in `frontend/src/types.ts`).

To edit the frontend source:

```bash
cd frontend
pnpm install
pnpm run dev      # Vite dev server with /api + /gradio_api proxied to :7860
pnpm run check    # svelte-check type gate (also: make check)
```

To rebuild the Space frontend, just build — Vite writes straight into `static/`
(no manual copy step), which is the directory `app.py` serves:

```bash
cd frontend
pnpm run build
```

Current frontend package versions:

```text
@sveltejs/vite-plugin-svelte 7.1.2
@gradio/client 2.2.1
svelte 5.56.3
vite 8.0.16
typescript 5.x  ·  svelte-check 4.x
```

Vite 8 requires Node `^20.19.0 || >=22.12.0`; this is declared in `frontend/package.json`.

## Observability

The backend is instrumented with OpenTelemetry (traces, metrics, and
trace-correlated logs):

- **Traces** — every HTTP request is a span (FastAPI instrumentation), and each
  model op (`model.caption`, `model.claim_chat`, `model.match`, `model.draft`)
  is a child span recording its mode and outcome (`success`/`fallback`/`error`).
- **Metrics** — `lfd.model.calls` and `lfd.model.duration` plus business
  counters (`lfd.events.created`, `lfd.items.created`, `lfd.claims.started`,
  `lfd.claims.photo_added`, `lfd.claims.submitted`, `lfd.claims.matched`,
  `lfd.claims.staff_message`, `lfd.returns.recorded`), most tagged with `event_id`.
- **Logs** — stdlib logs carry the active `trace_id`/`span_id`. When a real
  model call fails and falls back to the mock, it is logged at WARNING with a
  `outcome=fallback` metric and span event (no more silent degradation).

By default everything is exported to the console, so no collector is required:

```bash
LFD_TELEMETRY=0                      # disable telemetry entirely
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318   # ship OTLP/HTTP instead of console
LFD_OTEL_METRIC_INTERVAL_MS=60000    # metric export interval (lower it to see metrics sooner)
LFD_LOG_LEVEL=INFO                   # app log level
```

## API summary

Staff endpoints require `x-staff-password` (validated against that event's hash).

```text
GET  /api/config
POST /api/events                                     create event -> code + password (shown once)
GET  /api/events/{event_id}                          public event info
POST /api/events/{event_id}/staff/verify             staff password check

POST /api/events/{event_id}/claims                   start a claim
GET  /api/events/{event_id}/claims/{claim_id}        resume a claim (public, by id)
POST /api/events/{event_id}/claims/{claim_id}/chat
POST /api/events/{event_id}/claims/{claim_id}/photo  claimant photo upload + caption
GET  /api/events/{event_id}/claims/{claim_id}/photos/{photo_id}
POST /api/events/{event_id}/claims/{claim_id}/submit

GET  /api/events/{event_id}/staff/items
POST /api/events/{event_id}/staff/items
GET  /api/events/{event_id}/staff/items/{item_id}/photo
PATCH /api/events/{event_id}/staff/items/{item_id}
GET  /api/events/{event_id}/staff/claims
POST /api/events/{event_id}/staff/claims/{claim_id}/match
POST /api/events/{event_id}/staff/claims/{claim_id}/message   staff -> claimant message
POST /api/events/{event_id}/staff/draft_message
POST /api/events/{event_id}/staff/returns
GET  /api/events/{event_id}/staff/report
```

Gradio model endpoints (event-aware; ZeroGPU path):

```text
/gradio_api/call/generate_caption
/gradio_api/call/create_item
/gradio_api/call/claim_chat
/gradio_api/call/claim_add_photo
/gradio_api/call/match_claim
/gradio_api/call/draft_message
```

## Safety rules

- Claimants cannot browse item photos.
- Claimants cannot see ranked candidates.
- The app never says “this is yours.”
- Staff must confirm handoff offline.
- Visible identifying text is not transcribed into public traces.
- Returned items are removed from candidate search.
- Confirmation messages ask for details, not ownership.
- The claimant assistant may ask for categories of missing details, but it must not reveal unmentioned inventory details.

## Design article

See [`ARTICLE.md`](ARTICLE.md) for the product decisions, tradeoffs, architecture, and evaluation plan.

## References

- Gradio Server mode guide: https://www.gradio.app/guides/server-mode
- Gradio Server docs: https://www.gradio.app/docs/gradio/server
- Gradio JavaScript client docs: https://www.gradio.app/docs/js-client
- Hugging Face ZeroGPU docs: https://huggingface.co/docs/hub/en/spaces-zerogpu
- MiniCPM-V 4.6 model card: https://huggingface.co/openbmb/MiniCPM-V-4.6
- MiniCPM5-1B model card: https://huggingface.co/openbmb/MiniCPM5-1B
- Svelte docs: https://svelte.dev/docs/svelte/overview
- Vite: https://vite.dev/
