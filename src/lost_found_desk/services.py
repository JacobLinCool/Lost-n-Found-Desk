from __future__ import annotations

import logging
from typing import Any, Callable

from .config import get_settings
from .conversation import INVENTORY_PROBE_REFUSAL, is_inventory_probe, plan_turn
from .embeddings import MockEmbedder, build_embedder
from .models.mock import MockTextReasoner, MockVisionCaptioner
from .telemetry import OUTCOME_FALLBACK, OUTCOME_SUCCESS, model_span

logger = logging.getLogger("lost_found_desk.services")


class ModelHub:
    """Facade that selects real MiniCPM adapters or explicit mock mode.

    The default runtime is real MiniCPM-V + MiniCPM5 with LFD_DEVICE=auto.
    Mock mode remains available for CPU-only review or tests by setting
    LFD_MODEL_MODE=mock.

    Every model call is wrapped in an OTel span and timed; when a real-model
    call fails and ``allow_mock_fallback`` is set, the fallback is surfaced
    loudly (warning log + ``outcome=fallback`` metric + span event) instead of
    silently degrading to the rule-based mock.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.mock_vision = MockVisionCaptioner()
        self.mock_text = MockTextReasoner()
        self.mock_embedder = MockEmbedder()
        self._vision = None
        self._text = None
        self._embedder = None

        # ZeroGPU guidance recommends moving/loading CUDA models at module
        # startup instead of inside @spaces.GPU calls. In local CUDA/MPS mode we
        # keep lazy loading for faster developer iteration.
        if self.settings.model_mode == "real" and self.settings.zerogpu:
            self._eager_load_for_zerogpu()

    def _eager_load_for_zerogpu(self) -> None:
        for get_model in (self._get_vision, self._get_text):
            try:
                model = get_model()
                if hasattr(model, "_load"):
                    model._load()
            except Exception:
                logger.exception("ZeroGPU eager model load failed")
                if not self.settings.allow_mock_fallback:
                    raise

    def _get_vision(self):
        if self.settings.model_mode != "real":
            return self.mock_vision
        if self._vision is None:
            from .models.minicpm_v import MiniCPMVCaptioner

            self._vision = MiniCPMVCaptioner()
        return self._vision

    def _get_text(self):
        if self.settings.model_mode != "real":
            return self.mock_text
        if self._text is None:
            from .models.minicpm5 import MiniCPM5Reasoner

            self._text = MiniCPM5Reasoner()
        return self._text

    def _get_embedder(self):
        if self.settings.model_mode != "real":
            return self.mock_embedder
        if self._embedder is None:
            self._embedder = build_embedder(
                self.settings.model_mode, self.settings.embed_model, self.settings.device
            )
        return self._embedder

    def _run(self, op: str, real_call: Callable[[], Any], mock_call: Callable[[Exception], Any]) -> Any:
        """Run a model op with tracing, metrics, and a guarded mock fallback.

        ``real_call`` performs the primary (mode-selected) inference. If it
        raises and fallback is allowed, ``mock_call(exc)`` produces a safe mock
        result; otherwise the error propagates.
        """
        mode = self.settings.model_mode
        with model_span(op, mode) as span:
            try:
                result = real_call()
                span.set_attribute("lfd.model.outcome", OUTCOME_SUCCESS)
                return result
            except Exception as exc:
                if not self.settings.allow_mock_fallback:
                    logger.exception(
                        "model op '%s' (mode=%s) failed and fallback is disabled", op, mode
                    )
                    raise
                logger.warning(
                    "model op '%s' (mode=%s) failed: %s: %s — serving rule-based mock fallback "
                    "(set LFD_ALLOW_MOCK_FALLBACK=0 to surface the error instead)",
                    op,
                    mode,
                    type(exc).__name__,
                    exc,
                )
                span.set_attribute("lfd.model.outcome", OUTCOME_FALLBACK)
                span.add_event(
                    "model.fallback",
                    {"error.type": type(exc).__name__, "error.message": str(exc)[:200]},
                )
                return mock_call(exc)

    def generate_caption(self, image_path: str, found_location: str = "", staff_note: str = "") -> dict[str, str]:
        def _real() -> dict[str, str]:
            return self._get_vision().generate_caption(image_path, found_location, staff_note)

        def _mock(exc: Exception) -> dict[str, str]:
            result = self.mock_vision.generate_caption(image_path, found_location, staff_note)
            result["privacy_note"] += f"; real runtime fallback used: {type(exc).__name__}"
            return result

        return self._run("caption", _real, _mock)

    def claim_chat_step(self, conversation: list[dict[str, Any]], user_message: str, items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Advance the claim intake conversation.

        In real mode the collecting-phase replies are generated by MiniCPM5
        (language-mirroring acknowledgement + the next question). The
        deterministic, inventory-aware planner (``conversation.plan_turn``)
        still does the bookkeeping on every turn:

        - ``summary`` stays the claimant's own words — matching can never be
          steered by a hallucinated model detail;
        - ``readiness_state``/``missing_info`` stay deterministic, so the
          submit gate can't flap with model mood;
        - the planner's output is also the model's per-turn hint (which generic
          detail categories are still missing — leaks nothing about inventory)
          and the loud fallback if the model call fails or its reply trips a
          safety/quality filter (fabricated inventory claims, Simplified
          Chinese).

        Two turn types never reach the model: inventory probes ("what do you
        have?") get a fixed safe refusal, and the ready turn's call to action
        stays product copy. Mock mode answers from the planner everywhere
        (CPU-only demos and tests).
        """
        plan = plan_turn(conversation, user_message, items or [])
        plan_result = {
            "assistant_message": plan["assistant_message"],
            "summary": plan["summary"],
            "missing_info": plan["missing_info"],
            "readiness_state": plan["readiness_state"],
        }

        # Deterministic guardrail in every mode: "what do you have?" gets a
        # safe refusal plus the next useful question — never a model guess.
        if is_inventory_probe(user_message):
            refusal = INVENTORY_PROBE_REFUSAL[plan["language"]]
            return {**plan_result, "assistant_message": f"{refusal}\n{plan['assistant_message']}"}

        if self.settings.model_mode != "real":
            return plan_result

        # The ready turn is a call to action, not a conversation — the 1B model
        # reliably garbles it ("provide the contact details for the person who
        # turned it in"), so that one line stays product copy in every mode.
        if plan["readiness_state"] == "ready_for_staff_review":
            return plan_result

        # MiniCPM5-1B's Chinese chat is not shippable (broken sentences,
        # Simplified drift, even asking the claimant whether the desk found
        # it) — verified live; most zh turns tripped the filters anyway. zh
        # conversations use the planner's native-quality phrasing until a
        # bigger text model is configured.
        if plan["language"] == "zh":
            return plan_result

        def _real() -> dict[str, Any]:
            reply = self._get_text().claim_chat(
                conversation,
                user_message,
                language=plan["language"],
                missing=plan["missing_info"],
            )
            return {**plan_result, "assistant_message": reply}

        return self._run("claim_chat", _real, lambda _exc: plan_result)

    def match_claim(self, claim: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._run(
            "match",
            lambda: self._get_text().match_claim(claim, items),
            lambda _exc: self.mock_text.match_claim(claim, items),
        )

    def draft_message(self, claim: dict[str, Any], item: dict[str, Any] | None = None) -> str:
        return self._run(
            "draft",
            lambda: self._get_text().draft_message(claim, item),
            lambda _exc: self.mock_text.draft_message(claim, item),
        )

    def embed_query(self, text: str) -> list[float]:
        return self._run(
            "embed_query",
            lambda: self._get_embedder().embed_query(text),
            lambda _exc: self.mock_embedder.embed_query(text),
        )

    def embed_item(self, image_path: str, text: str) -> list[float]:
        return self._run(
            "embed_item",
            lambda: self._get_embedder().embed_item(image_path, text),
            lambda _exc: self.mock_embedder.embed_item(image_path, text),
        )
