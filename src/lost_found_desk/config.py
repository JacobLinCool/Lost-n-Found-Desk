from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _env_flag(name: str, default: str) -> bool:
    return os.getenv(name, default).lower() not in {"0", "false", "no", ""}


def _hf_zero_gpu_enabled() -> bool:
    return os.getenv("SPACES_ZERO_GPU", "").lower() in {"1", "t", "true"}


@dataclass(frozen=True)
class Settings:
    app_name: str
    storage_dir: Path
    model_mode: str  # real | mock
    device: str  # auto | cuda | mps | cpu
    seed_sample: bool
    allow_mock_fallback: bool
    minicpm_v_model: str
    minicpm5_model: str
    embed_model: str
    # Above this many unclaimed items, matching first narrows the inventory to
    # the top-N by embedding similarity before the LLM/ranker sees it.
    match_retrieve_topk: int
    retrieval_enabled: bool
    embed_strong_threshold: float
    embed_weak_threshold: float
    zerogpu: bool
    zerogpu_caption_duration: int
    zerogpu_text_duration: int
    # A reproducible demo event seeded on first boot so reviewers have something
    # to click through. Real events are created at runtime via the UI/API.
    seed_event_id: str
    seed_event_name: str
    seed_staff_password: str

    @property
    def db_path(self) -> Path:
        return self.storage_dir / "db.json"

    @property
    def upload_dir(self) -> Path:
        return self.storage_dir / "uploads"


def _load_settings() -> Settings:
    """Build Settings from the environment at call time.

    Reading env here (rather than as dataclass field defaults) means
    ``get_settings.cache_clear()`` actually picks up env changes, which keeps
    tests and tooling honest.
    """
    return Settings(
        app_name="Lost & Found Desk",
        storage_dir=Path(os.getenv("LFD_STORAGE_DIR", "data")),
        model_mode=os.getenv("LFD_MODEL_MODE", "real").lower(),
        device=os.getenv("LFD_DEVICE", "auto").lower(),
        seed_sample=_env_flag("LFD_SEED_SAMPLE", "1"),
        allow_mock_fallback=_env_flag("LFD_ALLOW_MOCK_FALLBACK", "0"),
        minicpm_v_model=os.getenv("LFD_MINICPM_V_MODEL", "openbmb/MiniCPM-V-4.6"),
        minicpm5_model=os.getenv("LFD_MINICPM5_MODEL", "openbmb/MiniCPM5-1B"),
        embed_model=os.getenv("LFD_EMBED_MODEL", "nvidia/llama-nemotron-embed-vl-1b-v2"),
        match_retrieve_topk=int(os.getenv("LFD_MATCH_TOPK", "10")),
        retrieval_enabled=_env_flag("LFD_RETRIEVAL", "1"),
        embed_strong_threshold=float(os.getenv("LFD_EMBED_STRONG", "0.32")),
        embed_weak_threshold=float(os.getenv("LFD_EMBED_WEAK", "0.18")),
        zerogpu=_hf_zero_gpu_enabled(),
        zerogpu_caption_duration=int(os.getenv("LFD_ZEROGPU_CAPTION_DURATION", "45")),
        zerogpu_text_duration=int(os.getenv("LFD_ZEROGPU_TEXT_DURATION", "30")),
        seed_event_id=os.getenv("LFD_SEED_EVENT_ID", "demo"),
        seed_event_name=os.getenv("LFD_SEED_EVENT_NAME", "Demo Conference 2026"),
        seed_staff_password=os.getenv("LFD_SEED_STAFF_PASSWORD", "demo-pass"),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = _load_settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    return settings
