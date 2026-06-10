from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from ..config import get_settings
from ..prompts import ITEM_CAPTION_PROMPT
from ..runtime.device import detect_runtime


class MiniCPMVCaptioner:
    """MiniCPM-V 4.6 caption adapter using Hugging Face Transformers.

    The adapter follows the model-card pattern:
    AutoProcessor + AutoModelForImageTextToText + apply_chat_template.
    """

    def __init__(self, model_id: str | None = None, device: str | None = None):
        settings = get_settings()
        self.model_id = model_id or settings.minicpm_v_model
        self.runtime = detect_runtime(device or settings.device)
        self.processor: Any | None = None
        self.model: Any | None = None

    def _load(self) -> None:
        if self.model is not None and self.processor is not None:
            return
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        self.processor = AutoProcessor.from_pretrained(self.model_id, trust_remote_code=True)
        kwargs: dict[str, Any] = {"torch_dtype": self.runtime.dtype, "trust_remote_code": True}
        if self.runtime.device == "cuda":
            kwargs["device_map"] = "auto"
        self.model = AutoModelForImageTextToText.from_pretrained(self.model_id, **kwargs)
        if self.runtime.device in {"mps", "cpu"}:
            self.model.to(self.runtime.device)
        self.model.eval()
        if self.runtime.device == "cuda":
            try:
                torch.set_float32_matmul_precision("high")
            except Exception:
                pass

    def generate_caption(self, image_path: str, found_location: str = "", staff_note: str = "") -> dict[str, str]:
        self._load()
        assert self.processor is not None and self.model is not None

        prompt = ITEM_CAPTION_PROMPT
        if found_location:
            prompt += f"\nFound location provided by staff: {found_location}"
        if staff_note:
            prompt += f"\nStaff note: {staff_note}"

        # Local file path is loaded as a PIL image and passed to the chat template.
        image = Image.open(Path(image_path)).convert("RGB")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        downsample_mode = "16x"
        inputs = self.processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
            downsample_mode=downsample_mode,
            max_slice_nums=36,
        ).to(self.model.device)
        generated_ids = self.model.generate(
            **inputs,
            downsample_mode=downsample_mode,
            max_new_tokens=220,
            do_sample=False,
        )
        generated_ids_trimmed = [
            out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        caption = self.processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0].strip()
        privacy_note = (
            "Visible personal details may be present"
            if "visible identifying text present" in caption.lower()
            else "No personal details were called out in the photo description"
        )
        return {"caption": caption, "privacy_note": privacy_note}
