# 13 - Error Handling & Resilience Patterns

The MOTHER backend implements layered fault tolerance across database transactions, AI providers, and presentation generation.

---

## 1. Database Transaction Rollback

In `backend/api/database.py`, database sessions are managed via a generator dependency with automatic rollback on error:

```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```
This guarantees that failed HTTP requests never leave dangling database locks or corrupted transaction states.

---

## 2. AI Provider Resilience & Graceful Degradation

1. **Google Gemini LLM Rate Limiting**:
   - `gemini_service.py` integrates `tenacity` retry loops with exponential backoff on `ResourceExhausted` (429) errors.
   - If Gemini is unreachable, `PromptPlanner` seamlessly falls back to `_generate_fallback_plan()`.
2. **Multi-Source Image Search Failover**:
   - If Unsplash rate limits are reached -> Automatically falls back to Openverse.
   - If Openverse fails -> Queries Wikimedia Commons.
   - If Wikimedia fails -> Calls Pollinations AI on-demand image synthesis.
   - If all external APIs fail -> Employs clean solid gradient cards with zero crashes.

---

## 3. Presentation Engine Layout Resilience

- **Shape Bounding Clamping**: All shape and text bounding boxes are validated against `calculate_available_content_width()` and `calculate_available_content_height()`.
- **Placeholder Recovery**: If a template slide lacks a predefined title or body placeholder, `write_text_or_fallback()` creates a geometric text shape rather than throwing `KeyError`.
- **Font Fallback**: When custom typography fonts are unavailable on the host OS, PowerPoint automatically falls back to system standard sans-serif (`Calibri` / `Arial`).