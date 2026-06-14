# Lost & Found Desk: a caption-first return desk for real-world lost items

- **Demo video:** https://youtu.be/AsOM7K0tL-s
- **Live app:** https://build-small-hackathon-lost-found-desk.hf.space
- **GitHub:** https://github.com/JacobLinCool/Lost-n-Found-Desk

Lost & Found Desk is a small-model workflow for a problem every event venue eventually has: a table full of bottles, badges, chargers, jackets, keys, and bags, plus a stream of vague "I lost something" messages.

The app turns that mess into a return desk. Staff photograph one found item at a time. MiniCPM-V writes a searchable caption. A claimant reports their lost item through a private assistant that asks only for missing details and can accept a photo of the claimant's own item. Staff then review candidate matches in a password-gated console, send safe follow-up messages, and record the offline handoff.

The important part is what the app refuses to do. It never exposes inventory photos to claimants. It never shows ranked candidates to the public. It never says "this is yours." AI narrows the work for humans; staff still confirm ownership offline.

## The problem

Lost-and-found work is not technically glamorous, but it is real operational friction. After a conference, gym class, school day, coworking event, or club meetup, a front desk may have dozens of objects and only a few seconds to handle each one. The incoming descriptions are often incomplete:

```text
I lost a black bottle, maybe near room B.
```

That creates repeated work: ask follow-up questions, look through photos, compare descriptions, avoid leaking item details, and prevent accidental returns. Lost & Found Desk is built for that narrow workflow.

## The solution

The product has three surfaces:

- A public home page where an organizer creates an independent desk for an event.
- A claimant flow at `/e/{event_id}` where the owner describes the lost item and saves a private resume link.
- A staff console at `/e/{event_id}/staff` where staff add found items, review reports, match candidates, message claimants, and log returns.

The workflow is deliberately small:

```text
one item photo
  -> MiniCPM-V caption
  -> private event inventory
  -> Claim Assistant intake
  -> MiniCPM5 staff-side reasoning
  -> staff review
  -> offline handoff log
```

For larger inventories, the app uses `nvidia/llama-nemotron-embed-vl-1b-v2` to shortlist items by multilingual vision-language similarity before the staff-side model sees the candidate set. That lets a Traditional Chinese or English claim retrieve an English-captioned item without exposing any candidate details to the claimant.

## User experience

For staff, the app is a focused desk console:

- Create an event and get a public link plus a one-time staff password.
- Photograph found items one by one.
- Let MiniCPM-V describe each item, including privacy notes when visible identifying text is present.
- Review incoming claims with claimant-uploaded photos, transcript, summary, and candidate items.
- Draft a safe message that asks for confirmation details rather than asserting ownership.
- Record the final return only after offline confirmation.

For claimants, the app feels like a private intake conversation:

- Open the event link.
- Describe the item in their own language.
- Upload a photo if they have one.
- Save a resume link.
- Receive staff messages without seeing the inventory or candidate list.

## Technical implementation

The backend is a Gradio Server app with FastAPI-style routes and Gradio API endpoints:

- `gradio.Server` hosts the app and model endpoints.
- REST endpoints handle events, claims, uploads, staff auth, reports, and static frontend delivery.
- `@app.api()` model endpoints keep ZeroGPU model calls inside Gradio's API path.
- The frontend is Svelte 5 + Vite, compiled into `static/` so Hugging Face Spaces does not need a Node build step.
- Event data is stored in a JSON store for the hackathon build; per-event staff passwords are salted PBKDF2 hashes.
- Claim IDs are high-entropy capability tokens, so a resume link is treated as a secret.
- OpenTelemetry instrumentation records model operations, durations, outcomes, and business counters.

Models:

- `openbmb/MiniCPM-V-4.6` for found-item and claimant-photo captions.
- `openbmb/MiniCPM5-1B` for English claim intake, staff-side matching, and safe message drafting.
- `nvidia/llama-nemotron-embed-vl-1b-v2` for cross-modal retrieval shortlisting.

All model dependencies stay below the Build Small 32B cap, and the default runtime uses local/open-weight models rather than hosted model APIs.

## Challenges

The first design temptation was to make the app more impressive than useful: segment a table photo into objects, add an OCR pipeline, build a broad embedding index, or let claimants see candidate matches. Each of those made the product riskier.

The final build intentionally narrows the scope:

- One item, one photo.
- Caption-first instead of OCR-first.
- Staff-only candidate review.
- AI assistance without ownership decisions.
- Explicit mock mode for tests, while real-model failures surface by default.

The hardest product detail was claimant safety. A helpful assistant can accidentally leak inventory details by asking, "Did it have a white sticker?" before the claimant mentioned a sticker. Lost & Found Desk avoids that by using an inventory-aware planner that asks only for generic missing detail categories while the model never receives the inventory during claimant chat.

## How Codex helped

Codex helped turn the project from an app prototype into a hackathon-ready submission package:

- Reviewed the official Build Small submission guide and tag generator.
- Cleaned runtime defaults so the real model path is strict by default.
- Checked `.gitignore` and kept runtime state, uploads, caches, and generated recording scratch files out of the repo.
- Added submission documents, social copy, README tags, and quest notes.
- Ran tests and deployment checks.
- Prepared Codex-attributed commits for the OpenAI Codex challenge.

## Links

- Live Space: https://huggingface.co/spaces/build-small-hackathon/lost-found-desk
- App URL: https://build-small-hackathon-lost-found-desk.hf.space
- Demo video: https://youtu.be/AsOM7K0tL-s
- GitHub: https://github.com/JacobLinCool/Lost-n-Found-Desk
