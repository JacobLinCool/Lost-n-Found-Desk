from __future__ import annotations

from typing import Callable, TypeVar

F = TypeVar("F", bound=Callable)

try:
    import spaces as _spaces  # type: ignore
except ImportError:  # pragma: no cover - local installs normally include spaces
    _spaces = None


def maybe_zerogpu(duration: int = 60, size: str | None = None):
    """Return the official @spaces.GPU decorator when the package is present.

    The `spaces` package decides whether the current runtime is ZeroGPU from
    Hugging Face's `SPACES_ZERO_GPU` environment variable. Outside ZeroGPU it
    returns the original function unchanged, so local CUDA/MPS/CPU runs keep the
    same call path while HF startup can still discover GPU-decorated functions.
    """

    if _spaces is None:
        def identity(fn: F) -> F:
            return fn

        return identity

    kwargs = {"duration": duration}
    if size:
        kwargs["size"] = size
    return _spaces.GPU(**kwargs)
