.PHONY: init dev mock real test check zip

# Mac MPS needs PYTORCH_ENABLE_MPS_FALLBACK=1 so ops missing on the MPS backend
# fall back to CPU instead of erroring (which would silently drop to the mock).
MPS_FALLBACK = PYTORCH_ENABLE_MPS_FALLBACK=1

init:
	uv sync
	cd frontend && pnpm install
	cd frontend && pnpm run build   # builds straight into ../static (served by app.py)

dev:
	$(MPS_FALLBACK) LFD_MODEL_MODE=real LFD_DEVICE=auto uv run python app.py

mock:
	LFD_MODEL_MODE=mock uv run python app.py

real:
	$(MPS_FALLBACK) LFD_MODEL_MODE=real LFD_DEVICE=auto uv run python app.py

test:
	LFD_MODEL_MODE=mock uv run --group dev python -m pytest tests

check:
	cd frontend && pnpm run check

zip:
	cd .. && zip -r $(notdir $(CURDIR)).zip $(notdir $(CURDIR)) \
		-x "*/__pycache__/*" "*/.pytest_cache/*" "*/node_modules/*" "*/.venv/*" \
		-x "$(notdir $(CURDIR))/data/db.json" "$(notdir $(CURDIR))/data/uploads/*"
