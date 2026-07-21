# AI Agent Reference for ha-traderepublic

---

## Token Efficiency Rules (CRITICAL — Read First)

These rules apply to **every response** without exception:

1. **Output minimal prose.** Bullet points only. No introductory sentences, no filler.
2. **No walkthrough unless explicitly asked.** Never create or update `walkthrough.md` unless requested.
3. **Short change summaries only.** Output ≤5 bullet points describing *what* changed and *why*.
4. **No repeating file content.** Reference filenames with links instead.
5. **No tool-call narration.** Do not describe what tool you are about to call. Just call it.
6. **Targeted file reads only.** Use line ranges when viewing files.
7. **Strict Read-Only Enforcement.** NEVER add order execution, buy/sell, or funds transfer methods.

---

## Codebase Architecture

| Area | Path |
|---|---|
| Integration Entry | `custom_components/traderepublic/__init__.py` |
| API Client (Read-Only) | `custom_components/traderepublic/api.py` |
| Coordinator (Anti-Ban) | `custom_components/traderepublic/coordinator.py` |
| Config Flow | `custom_components/traderepublic/config_flow.py` |
| Sensor Platform | `custom_components/traderepublic/sensor.py` |
| Diagnostics | `custom_components/traderepublic/diagnostics.py` |
| Brand Assets | `custom_components/brand/` & `custom_components/traderepublic/brand/` |
| Workflows | `.github/workflows/` |
| Scripts | `.github/scripts/` |

---

## CLI Commands

| Task | Command | Dir |
|---|---|---|
| Pytest | `pytest` | Root |
| Ruff linter | `ruff check . --fix` | Root |
| mypy linter | `mypy .` | Root |

---

## Coding Rules

- **Strict Read-Only**: The API client must never include write, trade, or transfer operations.
- **Anti-Ban Enforcement**: All requests must go through the coordinator with random jitter delay (5–30s), domain lock, exponential backoff, and persistent caching (`storage.Store`).
- **Traceback Preservation**: ALWAYS use `raise ... from e` or a naked `raise` to prevent stack trace destruction.
- **Silent Failure Prohibition**: `except: pass` is FORBIDDEN. All exceptions must be wrapped and propagated or logged with context.
