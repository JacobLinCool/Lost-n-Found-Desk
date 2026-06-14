---
license: mit
pretty_name: Lost & Found Desk Codex Trace Dataset
tags:
  - agent-traces
  - codex
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

This dataset is an official-format Codex trace artifact for the Codex-assisted Build Small hackathon submission of **Lost & Found Desk**.

It follows the Hugging Face Agent Traces guidance: Codex sessions are published as JSONL files under `traces/`, preserving the Codex session event schema so the Hub trace viewer can open the session. For public release, the trace is redacted in-place: local absolute paths, token-shaped strings, and secret-label strings are replaced while keeping the JSONL structure intact.

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

- `traces/2026/06/14/rollout-2026-06-14T20-33-08-019ec61f-1e93-79f1-a186-19bc0288e629.jsonl`: Codex-compatible JSONL session trace for the Hugging Face Agent Trace Viewer.
- `metadata/session_summary.json`: aggregate counts and source digest.
- `metadata/public_artifacts.json`: public resources connected to the submission.
- `metadata/derived_turns.json`: compact task-level summaries for quick review.
- `metadata/redaction_report.json`: source/released digests and redaction counts.

## Provenance

- Generated at: `2026-06-14T15:10:14.520794+00:00`
- Source digest prefix: `1db62550a9be41a3`
- Source event count: `2046`
- Derived turn rows: `17`
- Derived tool-event rows: `1054`
- Raw log policy: The published trace preserves Codex JSONL event schema for the official Hugging Face Agent Trace Viewer, with public redaction applied to local paths, token-shaped strings, and secret-label strings.
- Official trace docs: https://huggingface.co/docs/hub/en/agent-traces
- Changelog: https://huggingface.co/changelog/agent-trace-viewer

## Intended Use

The dataset provides viewer-compatible public evidence of the Codex-assisted submission workflow: requirement audit, deployment hardening, documentation, social/demo link updates, article revision, trace publication, collection creation, and verification. It is suitable for judging, reproducibility review, and lightweight study of agent-assisted release preparation.

## Limitations

This is a public redacted trace, not a private forensic archive. It should not be used to reconstruct local machine state or secrets. The redaction preserves the Codex event schema but may replace private path and secret-marker text inside prompts, tool inputs, or tool outputs.
