---
license: mit
pretty_name: Lost & Found Desk Codex Trace Dataset
tags:
  - codex
  - agent-trace
  - build-small-hackathon
  - lost-found-desk
  - gradio
language:
  - en
  - zh
size_categories:
  - n<1K
---

# Lost & Found Desk Codex Trace Dataset

This dataset is a sanitized trace artifact for the Codex-assisted Build Small hackathon submission of **Lost & Found Desk**.

It is derived from a local Codex Desktop rollout log, but it does **not** publish raw logs, full prompts, full tool outputs, system instructions, local absolute paths, or secrets. The released rows keep only task summaries, hashed source identifiers, tool-call metadata, public URLs, and verification evidence.

## Public Project Links

- Space: https://huggingface.co/spaces/build-small-hackathon/lost-found-desk
- Live app: https://build-small-hackathon-lost-found-desk.hf.space
- Article: https://huggingface.co/spaces/build-small-hackathon/lost-found-desk/blob/main/docs/article.md
- Demo video: https://youtu.be/AsOM7K0tL-s
- GitHub: https://github.com/JacobLinCool/Lost-n-Found-Desk
- X post: https://x.com/JacobLinCool/status/2066147773481951378
- Trace dataset: https://huggingface.co/datasets/build-small-hackathon/lost-found-desk-codex-traces
- Collection: https://huggingface.co/collections/build-small-hackathon/lost-and-found-desk-6a2ec0551c48861e92dd8443


## Files

- `data/turns.jsonl`: one derived row per user task and assistant completion.
- `data/tool_events.jsonl`: sanitized metadata for tool calls and results.
- `data/session_summary.jsonl`: aggregate counts and source digest.
- `data/public_artifacts.jsonl`: public resources connected to the submission.
- `schema.json`: column names for each split-like file.

## Provenance

- Generated at: `2026-06-14T14:56:46.967779+00:00`
- Source digest prefix: `a723c85c5f6669ce`
- Source event count: `1772`
- Derived turn rows: `15`
- Derived tool-event rows: `922`
- Raw log policy: Raw Codex logs were not published. This dataset contains derived, redacted metadata and short summaries only.

## Intended Use

The dataset provides public evidence of the Codex-assisted submission workflow: requirement audit, deployment hardening, documentation, social/demo link updates, article revision, and verification. It is suitable for judging, reproducibility review, and lightweight study of agent-assisted release preparation.

## Limitations

This is not a full transcript. It is a privacy-preserving trace summary. It should not be used to reconstruct private prompts, local machine state, or complete model behavior.
