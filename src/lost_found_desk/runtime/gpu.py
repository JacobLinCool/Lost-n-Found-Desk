from __future__ import annotations

import os
from typing import Callable, TypeVar

F = TypeVar("F", bound=Callable)


def maybe_zerogpu(duration: int = 60, size: str | None = None):
    """Return @spaces.GPU on ZeroGPU; otherwise return an identity decorator.

    Keeping this import isolated makes local CUDA/MPS development independent
    from the Hugging Face Spaces-only `spaces` module.
    """
    is_zero = os.getenv("ZEROGPU", "").lower() in {"1", "true", "yes"}
    if not is_zero:
        def identity(fn: F) -> F:
            return fn
        return identity

    import spaces  # type: ignore

    kwargs = {"duration": duration}
    if size:
        kwargs["size"] = size
    return spaces.GPU(**kwargs)
