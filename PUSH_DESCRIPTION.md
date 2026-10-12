# Push Description — Refactoring Plan (Phase 0-4 + Dynamic Models)

Branch: `refactor-plan` → `main`

## Changes (2 commits)

### 5f3a090 — Phase 0-4
- `config_loader.py`, `services/ai_service.py`, `services/schema_models.py`
- `app/` package
- Retry + caching in providers
- Document parser validation

### 5934ee9 — Dynamic Models
- Removed hardcoded `ALLOWED_MODELS` filter in `app.py`
- Dynamic provider-discovered model lists for Google and Groq
