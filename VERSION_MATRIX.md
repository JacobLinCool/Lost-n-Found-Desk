# Version and Compatibility Matrix

Checked on 2026-06-10.

## Python / Space runtime

| Package | Version constraint | Note |
| --- | --- | --- |
| `gradio` | `==6.17.3` | Matches Space `sdk_version`; current PyPI release at time of check. |
| `spaces` | `>=0.50.4` | Provides `@spaces.GPU` for ZeroGPU functions. |
| `transformers[torch]` | `>=5.11.0` | Above MiniCPM-V requirement `>=5.7.0` and MiniCPM5 requirement `>=5.6`. |
| `torch` | `>=2.8.0` | ZeroGPU docs support PyTorch 2.8.0 to latest. |
| `torchvision` | `>=0.27.0` | Latest checked release. |
| `av` | `>=17.1.0` | Used instead of `torchcodec` to avoid CUDA-version decoder issues noted by MiniCPM-V. |
| `accelerate` | `>=1.13.0` | Latest checked release. |
| `fastapi` | `>=0.136.3` | Latest checked release. |
| `uvicorn` | `>=0.49.0` | Latest checked release. |
| `pydantic` | `>=2.13.4` | Latest checked release. |

## Frontend

| Package | Version | Note |
| --- | ---: | --- |
| `svelte` | `5.56.3` | Latest checked release. |
| `vite` | `8.0.16` | Latest checked release. Requires Node `^20.19.0 || >=22.12.0`. |
| `@sveltejs/vite-plugin-svelte` | `7.1.2` | Latest checked release; peer-compatible with Vite 8 and Svelte 5. |
| `@gradio/client` | `2.2.1` | Current official JS client release shown by Gradio docs/npm at check time. |
