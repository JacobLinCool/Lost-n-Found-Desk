from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeInfo:
    runtime: str
    device: str
    dtype: str


def detect_runtime(requested: str = "auto") -> RuntimeInfo:
    """Detect a portable runtime for ZeroGPU, CUDA, MPS, or CPU.

    This function avoids importing torch until runtime so the UI and tests can be
    inspected in lightweight environments.
    """
    requested = (requested or "auto").lower()

    if os.getenv("ZEROGPU", "").lower() in {"1", "true", "yes"}:
        return RuntimeInfo(runtime="zerogpu", device="cuda", dtype="auto")

    try:
        import torch
    except Exception:
        return RuntimeInfo(runtime="no-torch", device="cpu", dtype="float32")

    # MiniCPM weights ship as bf16; "auto" lets transformers honor that on both
    # CUDA and MPS, which is numerically safer than forcing fp16. CPU stays fp32.
    # The dtype field is consumed by the model loaders (passed as torch_dtype).
    if requested in {"cuda", "gpu"}:
        return RuntimeInfo(runtime="cuda", device="cuda", dtype="auto")
    if requested == "mps":
        return RuntimeInfo(runtime="mps", device="mps", dtype="auto")
    if requested == "cpu":
        return RuntimeInfo(runtime="cpu", device="cpu", dtype="float32")

    if torch.cuda.is_available():
        return RuntimeInfo(runtime="cuda", device="cuda", dtype="auto")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return RuntimeInfo(runtime="mps", device="mps", dtype="auto")
    return RuntimeInfo(runtime="cpu", device="cpu", dtype="float32")
