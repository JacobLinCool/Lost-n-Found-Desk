from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


PROJECT_NAME = "Lost & Found Desk"
PROJECT_REPO = "https://github.com/JacobLinCool/Lost-n-Found-Desk"
SPACE_REPO = "https://huggingface.co/spaces/build-small-hackathon/lost-found-desk"
APP_URL = "https://build-small-hackathon-lost-found-desk.hf.space"
ARTICLE_URL = "https://huggingface.co/spaces/build-small-hackathon/lost-found-desk/blob/main/docs/article.md"
DEMO_URL = "https://youtu.be/AsOM7K0tL-s"
X_POST_URL = "https://x.com/JacobLinCool/status/2066147773481951378"
DATASET_URL = "https://huggingface.co/datasets/build-small-hackathon/lost-found-desk-codex-traces"
COLLECTION_URL = "https://huggingface.co/collections/build-small-hackathon/lost-and-found-desk-6a2ec0551c48861e92dd8443"

MODELS = [
    "openbmb/MiniCPM-V-4.6",
    "openbmb/MiniCPM5-1B",
    "nvidia/llama-nemotron-embed-vl-1b-v2",
]

TASK_SUMMARIES = {
    "我們準備要提交目前這個專案到 hackathon": {
        "task_id": "submission_hardening",
        "summary": "Audit official Build Small requirements, harden runtime defaults, deploy the Space, publish GitHub, add documentation, and verify submission links.",
        "public_outputs": [
            SPACE_REPO,
            APP_URL,
            PROJECT_REPO,
        ],
    },
    "should use the youtube link for demo video": {
        "task_id": "youtube_demo_link",
        "summary": "Replace repository and Space demo-video references with the public YouTube demo link.",
        "public_outputs": [DEMO_URL],
    },
    "for social media post, we are going to post on X": {
        "task_id": "x_post_draft",
        "summary": "Shorten the social-media draft into an X-ready post within the platform character budget.",
        "public_outputs": [],
    },
    "here's the link of the post": {
        "task_id": "published_x_post",
        "summary": "Add the published X post URL to README, submission notes, and Space materials.",
        "public_outputs": [X_POST_URL],
    },
    "did you write article on huggingface": {
        "task_id": "article_publication_status",
        "summary": "Clarify that the article exists as repository and Space markdown rather than a separate Hugging Face Community Article.",
        "public_outputs": [ARTICLE_URL],
    },
    "i think for article, we should put the yt link": {
        "task_id": "article_demo_link_position",
        "summary": "Move the YouTube demo link near the top of the article files.",
        "public_outputs": [DEMO_URL, ARTICLE_URL],
    },
    "consider to use": {
        "task_id": "academic_article_rewrite",
        "summary": "Rewrite the public article with a clearer argument, scope, privacy boundary, evidence, and limitation structure.",
        "public_outputs": [ARTICLE_URL],
    },
    "looks good, and i think our last step": {
        "task_id": "trace_dataset_and_collection",
        "summary": "Create a sanitized Codex trace dataset and a Hugging Face collection that groups the Space, models, article link, and dataset.",
        "public_outputs": [DATASET_URL, COLLECTION_URL],
    },
}

PUBLIC_ARTIFACTS = [
    {
        "artifact_type": "space",
        "name": "Lost & Found Desk Space",
        "url": SPACE_REPO,
        "repo_id": "build-small-hackathon/lost-found-desk",
    },
    {
        "artifact_type": "app",
        "name": "Lost & Found Desk live app",
        "url": APP_URL,
        "repo_id": "build-small-hackathon/lost-found-desk",
    },
    {
        "artifact_type": "repository",
        "name": "GitHub repository",
        "url": PROJECT_REPO,
        "repo_id": "JacobLinCool/Lost-n-Found-Desk",
    },
    {
        "artifact_type": "article",
        "name": "Project article",
        "url": ARTICLE_URL,
        "repo_id": "build-small-hackathon/lost-found-desk",
    },
    {
        "artifact_type": "demo_video",
        "name": "YouTube demo video",
        "url": DEMO_URL,
        "repo_id": "",
    },
    {
        "artifact_type": "social_post",
        "name": "X post",
        "url": X_POST_URL,
        "repo_id": "",
    },
    {
        "artifact_type": "dataset",
        "name": "Codex trace dataset",
        "url": DATASET_URL,
        "repo_id": "build-small-hackathon/lost-found-desk-codex-traces",
    },
    {
        "artifact_type": "collection",
        "name": "Lost & Found Desk Hugging Face collection",
        "url": COLLECTION_URL,
        "repo_id": "build-small-hackathon/lost-and-found-desk-6a2ec0551c48861e92dd8443",
    },
    *[
        {
            "artifact_type": "model",
            "name": model,
            "url": f"https://huggingface.co/{model}",
            "repo_id": model,
        }
        for model in MODELS
    ],
]


TOKEN_PATTERNS = [
    re.compile(r"hf_[A-Za-z0-9]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
]

ABS_PATH = re.compile(r"/Users/jacoblincool/[^\s\"']+")


def redact_text(text: str) -> str:
    text = ABS_PATH.sub("$LOCAL_PATH", text)
    for pattern in TOKEN_PATTERNS:
        text = pattern.sub("[REDACTED_TOKEN]", text)
    return text


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def classify_task(message: str) -> dict[str, Any]:
    for needle, task in TASK_SUMMARIES.items():
        if needle in message:
            return task
    return {
        "task_id": f"task_{short_hash(message)}",
        "summary": redact_text(message[:240]).strip(),
        "public_outputs": [],
    }


def tool_summary(name: str, arguments: str) -> tuple[str, str]:
    if name == "exec_command":
        try:
            args = json.loads(arguments)
            cmd = args.get("cmd", "")
        except Exception:
            cmd = arguments
        redacted = redact_text(cmd)
        sensitive_markers = (
            "github_pat_",
            "ghp_",
            "gho_",
            "hf_",
            "sk-",
            "OPENAI_API_KEY",
            "HF_TOKEN",
            "Authorization",
            "PRIVATE KEY",
            "password\\s*=",
            "token\\s*=",
        )
        if any(marker.lower() in redacted.lower() for marker in sensitive_markers):
            return "shell", "secret scan command"
        if ".env.example" in redacted:
            return "shell", "inspect example environment file"
        try:
            parts = shlex.split(redacted)
        except ValueError:
            parts = redacted.split()
        if not parts:
            return "shell", ""
        executable = parts[0]
        if executable in {"git", "gh", "hf", "curl", "uv", "rg", "sed", "sqlite3", "python3"}:
            return "shell", " ".join(parts[:6])
        return "shell", executable
    if name == "apply_patch":
        return "edit", "apply_patch"
    if name in {"web_search_call", "web_search_end"}:
        return "web", name
    return "tool", name


def extract_exit_code(output: str) -> int | None:
    match = re.search(r"Process exited with code (-?\d+)", output)
    return int(match.group(1)) if match else None


def is_relevant_public_ref(ref: str) -> bool:
    if "\\" in ref or "${" in ref:
        return False
    parsed = urlparse(ref)
    host = parsed.netloc.lower()
    path = parsed.path
    if host == "build-small-hackathon-lost-found-desk.hf.space":
        return True
    if host == "build-small-hackathon-field-guide.hf.space":
        return path in {"/", "/submit"}
    if host == "youtu.be" and path == "/AsOM7K0tL-s":
        return True
    if host == "x.com" and (ref == X_POST_URL or path == "/buildsmall"):
        return True
    if host == "github.com":
        return path.startswith("/JacobLinCool/Lost-n-Found-Desk")
    if host == "huggingface.co":
        return (
            path.startswith("/spaces/build-small-hackathon/lost-found-desk")
            or path.startswith("/datasets/build-small-hackathon/lost-found-desk-codex-traces")
            or path.startswith("/collections/build-small-hackathon/lost-and-found-desk-6a2ec0551c48861e92dd8443")
            or path in {"/openbmb/MiniCPM-V-4.6", "/openbmb/MiniCPM5-1B", "/nvidia/llama-nemotron-embed-vl-1b-v2"}
            or path.startswith("/docs/")
            or path == "/BuildSmall"
        )
    return False


def extract_public_refs(text: str) -> list[str]:
    refs: set[str] = set()
    for raw in re.findall(r"https?://[^\s<>\]\)\"'`]+", text):
        ref = raw.rstrip(".,;:，。\\")
        if is_relevant_public_ref(ref):
            refs.add(ref)
    return sorted(refs)


def build_dataset(rollout_path: Path, out_dir: Path, collection_url: str | None = None) -> None:
    rows = read_jsonl(rollout_path)
    source_digest = hashlib.sha256(rollout_path.read_bytes()).hexdigest()

    session_meta = next((r.get("payload", {}) for r in rows if r.get("type") == "session_meta"), {})
    thread_id = session_meta.get("id") or rollout_path.stem.rsplit("-", 1)[-1]
    created_at = session_meta.get("timestamp")

    turns: list[dict[str, Any]] = []
    tool_events: list[dict[str, Any]] = []
    task_by_sequence: dict[int, str] = {}
    current_task = ""
    task_sequence = -1
    tool_call_by_id: dict[str, dict[str, Any]] = {}
    counters: Counter[str] = Counter()

    for event_index, row in enumerate(rows):
        timestamp = row.get("timestamp")
        payload = row.get("payload") or {}
        payload_type = payload.get("type") if isinstance(payload, dict) else None

        if payload_type == "user_message":
            message = str(payload.get("message") or payload.get("content") or "")
            task_sequence += 1
            task = classify_task(message)
            current_task = task["task_id"]
            task_by_sequence[task_sequence] = current_task
            turns.append(
                {
                    "project": PROJECT_NAME,
                    "thread_id_hash": short_hash(thread_id),
                    "source_session_digest": source_digest[:16],
                    "turn_index": task_sequence,
                    "task_id": current_task,
                    "timestamp": timestamp,
                    "role": "user",
                    "summary": task["summary"],
                    "message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
                    "public_outputs": task["public_outputs"],
                    "privacy_level": "derived_summary",
                }
            )

        elif payload_type == "task_complete" and current_task:
            final = str(payload.get("last_agent_message") or "")
            public_refs = extract_public_refs(final)
            turns.append(
                {
                    "project": PROJECT_NAME,
                    "thread_id_hash": short_hash(thread_id),
                    "source_session_digest": source_digest[:16],
                    "turn_index": task_sequence,
                    "task_id": current_task,
                    "timestamp": timestamp,
                    "role": "assistant",
                    "summary": redact_text(final[:360]).strip(),
                    "message_sha256": hashlib.sha256(final.encode("utf-8")).hexdigest(),
                    "public_outputs": public_refs,
                    "privacy_level": "redacted_excerpt",
                }
            )

        elif payload_type in {"function_call", "custom_tool_call"}:
            name = str(payload.get("name") or "unknown")
            arguments = str(payload.get("arguments") or payload.get("input") or "")
            category, summary = tool_summary(name, arguments)
            call_id = str(payload.get("call_id") or f"event-{event_index}")
            counters[f"tool.{name}"] += 1
            event = {
                "project": PROJECT_NAME,
                "thread_id_hash": short_hash(thread_id),
                "source_session_digest": source_digest[:16],
                "event_index": event_index,
                "task_id": current_task,
                "timestamp": timestamp,
                "event_type": "tool_call",
                "tool_name": name,
                "tool_category": category,
                "summary": summary,
                "call_id_hash": short_hash(call_id),
                "exit_code": None,
                "success": None,
                "public_refs": extract_public_refs(arguments),
                "privacy_level": "sanitized_metadata",
            }
            tool_call_by_id[call_id] = event
            tool_events.append(event)

        elif payload_type in {"function_call_output", "custom_tool_call_output", "patch_apply_end"}:
            call_id = str(payload.get("call_id") or f"event-{event_index}")
            output = str(payload.get("output") or payload.get("stdout") or "")
            success = payload.get("success")
            exit_code = extract_exit_code(output)
            if success is None and exit_code is not None:
                success = exit_code == 0
            source = tool_call_by_id.get(call_id)
            event = {
                "project": PROJECT_NAME,
                "thread_id_hash": short_hash(thread_id),
                "source_session_digest": source_digest[:16],
                "event_index": event_index,
                "task_id": current_task,
                "timestamp": timestamp,
                "event_type": "tool_result",
                "tool_name": source["tool_name"] if source else str(payload_type),
                "tool_category": source["tool_category"] if source else "tool",
                "summary": "result captured; raw output omitted",
                "call_id_hash": short_hash(call_id),
                "exit_code": exit_code,
                "success": success,
                "public_refs": extract_public_refs(output),
                "privacy_level": "sanitized_metadata",
            }
            tool_events.append(event)

    session_summary = {
        "project": PROJECT_NAME,
        "thread_id_hash": short_hash(thread_id),
        "source_session_digest": source_digest[:16],
        "created_at": created_at,
        "source_event_count": len(rows),
        "derived_turn_rows": len(turns),
        "derived_tool_event_rows": len(tool_events),
        "task_count": len({t["task_id"] for t in turns}),
        "tool_counts": dict(sorted(counters.items())),
        "raw_log_policy": "Raw Codex logs were not published. This dataset contains derived, redacted metadata and short summaries only.",
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    write_jsonl(data_dir / "turns.jsonl", turns)
    write_jsonl(data_dir / "tool_events.jsonl", tool_events)
    write_jsonl(data_dir / "session_summary.jsonl", [session_summary])
    write_jsonl(data_dir / "public_artifacts.jsonl", PUBLIC_ARTIFACTS)
    (out_dir / "schema.json").write_text(
        json.dumps(
            {
                "turns": list(turns[0].keys()) if turns else [],
                "tool_events": list(tool_events[0].keys()) if tool_events else [],
                "session_summary": list(session_summary.keys()),
                "public_artifacts": list(PUBLIC_ARTIFACTS[0].keys()),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "README.md").write_text(dataset_card(session_summary, collection_url), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def dataset_card(summary: dict[str, Any], collection_url: str | None = None) -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    collection_url = collection_url or COLLECTION_URL
    collection_line = f"- Collection: {collection_url}\n" if collection_url else ""
    return f"""---
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

- Space: {SPACE_REPO}
- Live app: {APP_URL}
- Article: {ARTICLE_URL}
- Demo video: {DEMO_URL}
- GitHub: {PROJECT_REPO}
- X post: {X_POST_URL}
- Trace dataset: {DATASET_URL}
{collection_line}

## Files

- `data/turns.jsonl`: one derived row per user task and assistant completion.
- `data/tool_events.jsonl`: sanitized metadata for tool calls and results.
- `data/session_summary.jsonl`: aggregate counts and source digest.
- `data/public_artifacts.jsonl`: public resources connected to the submission.
- `schema.json`: column names for each split-like file.

## Provenance

- Generated at: `{generated_at}`
- Source digest prefix: `{summary["source_session_digest"]}`
- Source event count: `{summary["source_event_count"]}`
- Derived turn rows: `{summary["derived_turn_rows"]}`
- Derived tool-event rows: `{summary["derived_tool_event_rows"]}`
- Raw log policy: {summary["raw_log_policy"]}

## Intended Use

The dataset provides public evidence of the Codex-assisted submission workflow: requirement audit, deployment hardening, documentation, social/demo link updates, article revision, and verification. It is suitable for judging, reproducibility review, and lightweight study of agent-assisted release preparation.

## Limitations

This is not a full transcript. It is a privacy-preserving trace summary. It should not be used to reconstruct private prompts, local machine state, or complete model behavior.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("codex_trace_dataset"))
    parser.add_argument("--collection-url", default=None)
    args = parser.parse_args()
    build_dataset(args.rollout.expanduser(), args.out, args.collection_url)


if __name__ == "__main__":
    main()
