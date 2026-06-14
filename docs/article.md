# Lost & Found Desk: small models for staff-controlled item return

- **Demo video:** https://youtu.be/AsOM7K0tL-s
- **Live app:** https://build-small-hackathon-lost-found-desk.hf.space
- **GitHub:** https://github.com/JacobLinCool/Lost-n-Found-Desk
- **Social post:** https://x.com/JacobLinCool/status/2066147773481951378

Lost & Found Desk explores a narrow but common operational problem: how a temporary front desk can return lost objects while preserving private inventory evidence and reducing manual comparison work. Conferences, gyms, schools, coworking spaces, and community events all accumulate the same objects: bottles, chargers, badges, bags, jackets, keys, and small personal accessories. The work is ordinary, but it is also time-sensitive and privacy-sensitive. A claimant may say only "I lost a black bottle near room B," while staff may have dozens of visually similar objects to review.

The project argues for a small, staff-controlled workflow. A vision-language model turns each found item photo into a readable caption. A claimant-facing assistant gathers a private description in the claimant's own language. A staff-only review surface then combines the claim transcript, generated summaries, item captions, and retrieval signals to surface plausible candidates for human confirmation. The system uses AI to reduce search cost; ownership remains a staff decision made offline.

## Problem and Scope

Lost-and-found work has two sources of friction. The first is information quality: claimants often remember partial details, and staff often record found items under pressure. The second is information exposure: a system that reveals inventory photos or candidate matches can teach a dishonest claimant what to say. A useful design therefore needs to make the inventory searchable for staff while keeping candidate evidence out of the public claim flow.

Lost & Found Desk focuses on small and medium event inventories, where one staff member can photograph items one at a time and where the main bottleneck is comparison, not warehouse-scale indexing. This scope keeps the product close to the real front-desk workflow: quick intake, private claims, staff review, and an auditable handoff log.

## Design Claim

The central design claim is that caption-first intake is a practical unit of work for lost-and-found operations. One item photo produces one item record. The caption becomes a bridge between visual evidence, multilingual owner descriptions, staff review, and later reporting. This choice removes the need for a brittle object-segmentation step during the hackathon build and gives staff a record they can read, search, and correct.

The system follows three principles:

- **One item, one record.** Staff photograph each object separately, so the inventory aligns with how returns are actually handled.
- **Private claimant intake.** Claimants describe their item and may upload a reference photo while inventory photos, ranked candidates, and staff reasoning remain private.
- **Staff-controlled handoff.** Model outputs support comparison and message drafting; staff confirm identity and record the return offline.

## User Experience

The staff workflow starts by creating an event desk. The app generates a public claim link and a staff password. Staff then add found items by uploading one photo per object, with optional context such as location or notes. MiniCPM-V produces a caption and a privacy note when visible identifying text appears. The item enters a private event inventory.

The claimant workflow is a short conversation. The assistant asks for missing categories of information such as color, location, distinctive marks, or supporting photos. Its questions stay at the category level until the claimant supplies specific details. A claimant can resume the conversation through a private link, and staff can reply while the inventory remains private.

The staff review workflow brings the two sides together. Staff see the claim summary, conversation, claimant photo captions, candidate items, match reasons, and a safe draft message. A return is logged only after staff confirm the item offline.

## Technical Approach

Lost & Found Desk is deployed as a Gradio Server app with a compiled Svelte interface. The backend provides event, claim, upload, staff-auth, reporting, and model services; the frontend presents the experience as a task-focused product surface. On Hugging Face ZeroGPU, model-heavy actions run through Gradio API routes so the runtime can schedule GPU work correctly.

The model stack is intentionally small:

- `openbmb/MiniCPM-V-4.6` captions found-item photos and claimant reference photos.
- `openbmb/MiniCPM5-1B` supports claimant intake, staff-side comparison, and safe message drafting.
- `nvidia/llama-nemotron-embed-vl-1b-v2` provides multilingual vision-language retrieval signals for larger inventories.

All models are below the Build Small 32B cap. The deployed configuration uses open-weight local models with `LFD_MODEL_MODE=real` and `LFD_ALLOW_MOCK_FALLBACK=0`, so judge-facing validation exercises the real model path and makes runtime failures explicit.

## Privacy and Safety Boundary

The project treats a claim as a private capability link. A claimant who knows the event code and claim ID can continue that claim, so the resume URL is not public content. Staff item photos are served through staff-only routes, not as public static files.

The claimant assistant is also constrained by an information boundary. It may ask open-ended questions about missing evidence, such as whether the item had a sticker, logo, label, scratch, or other distinctive mark. It should not introduce a specific detail from the private inventory before the claimant has mentioned it. This boundary keeps model assistance useful while limiting the chance that the conversation reveals the answer.

## Development and Codex

Codex helped move the project from prototype to submission-ready release. The final pass aligned the official Build Small requirements, README metadata, quest tags, deployment links, `.gitignore` hygiene, strict real-model defaults, ZeroGPU startup behavior, dependency compatibility with the current Spaces builder, and co-authored Git history for the Codex challenge. It also produced the article draft, X post draft, submission notes, and verification record used for final submission.

Codex's most useful role was convergence: making failure states explicit, documenting the model/runtime choices, verifying public links, and keeping the hackathon package consistent across GitHub, Hugging Face Space, demo video, social post, and article materials.

## Limitations

The current build is designed for event-scale inventories, not long-term institutional archives. Retrieval can support larger candidate sets, but production use would need persistence beyond local JSON storage, stronger authentication, rate limiting, retention policies, and evaluation with real venue photos. Privacy behavior around visible names, badges, and access cards should also be tested with representative data before deployment in a live organization.

Within the hackathon scope, the evidence is a working public deployment, a seeded demo event, tests for core claim and matching behavior, and a demo video that exercises the staff and claimant flows. The contribution is a compact operational pattern: small models can make lost-and-found work faster and safer when the system centers staff review, bounded disclosure, and offline confirmation.

## Links

- Hugging Face Space: https://huggingface.co/spaces/build-small-hackathon/lost-found-desk
- App URL: https://build-small-hackathon-lost-found-desk.hf.space
- Demo video: https://youtu.be/AsOM7K0tL-s
- GitHub: https://github.com/JacobLinCool/Lost-n-Found-Desk
- X post: https://x.com/JacobLinCool/status/2066147773481951378
