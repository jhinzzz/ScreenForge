# ScreenForge — Architecture Deep-Dive

How a "describe it in plain language, keep a real pytest file" UI-automation engine
is actually built. This is the engineering story behind the README: the design
decisions, the safety rails, and the hygiene that makes the output trustworthy.

Every path below is real and in this repo.

---

## 1. Brain / Hands split

ScreenForge's central design choice is that **the LLM is the brain and ScreenForge
is the hands** — and the two never blur. The agent decides *what* to do; the engine
deterministically executes UI actions and emits code. This is spelled out as a hard
protocol in [`CLAUDE.md`](../CLAUDE.md): the agent calls `inspect_ui`, analyzes the
real DOM/XML tree itself, then issues discrete `--action` commands.

The execution side lives in `cli/modes/` — one module per execution shape:

- `cli/modes/action.py` — a single action (`click`, `input`, `assert_exist`, …).
- `cli/modes/workflow.py` — a YAML workflow: **one process emits one cumulative,
  multi-step pytest file**.
- `cli/modes/default.py` — the autonomous `--goal` loop (the *only* path where the
  engine itself calls a model to decide the next step).

Why it matters: the happy path (inspect → decide → act → verify) makes **no hidden
LLM calls**. The model you plug in is the only intelligence, and you can watch every
decision. The same surface is exposed to MCP clients via `ui_agent_execute`, so an
agent in Claude Desktop / Cursor / Cline drives the exact same code path as the shell.

## 2. L1/L2 semantic cache

Re-running the same instruction against the same page shouldn't cost an LLM call.
`common/cache/cache_manager.py` (`CacheManager`) implements a two-tier cache:

- **L1-Action** — exact-match keyed on `(platform, instruction_hash, ui_hash)`
  (see `exact_key = f"L1_{platform}_{inst_hash}_{ui_hash}"`). Same page + same
  instruction → instant hit, zero model tokens.
- **L2-SimpleQA** — semantic similarity over embeddings for near-matches, gated by
  a similarity threshold (`CACHE_SIMILARITY_THRESHOLD`); when embeddings aren't
  available it conservatively treats the lookup as a miss rather than guessing.

The payoff is cost and latency: a stable flow re-runs without paying the model again.

## 3. Self-healing with AST validation

When a committed test's locator breaks after a UI change, the engine repairs it
in place instead of just going red — but only behind real safety rails.

- **Trigger:** `conftest.py`'s `pytest_runtest_makereport` hook tracks consecutive
  failures per test and fires `_trigger_self_healing` on the
  `AUTO_HEAL_TRIGGER_THRESHOLD`-th consecutive failure.
- **The healer:** `common/ai_heal.py` (`HealerBrain.heal_script`) analyzes the live
  failure scene (DOM tree + screenshot) and returns a structured `HealResult`
  carrying a `confidence` score and the `fixed_code`.
- **The gates** (all in `conftest.py` / `common/ai_heal.py`), each of which can abort
  the overwrite:
  1. **Confidence gate** — below `AUTO_HEAL_MIN_CONFIDENCE` (default `0.7`) → skipped,
     never applied.
  2. **AST validation** — `HealResult` runs `ast.parse` on the fix; unparseable code
     is rejected.
  3. **Structural check** — the fix must still contain a `def test_` function.
  4. **Backup before overwrite** — the original is copied to `<file>.bak`, so every
     heal is reversible.

A worked, real (not illustrative) heal — break a selector, watch the engine repair
all four sites at confidence 0.90, then replay green — is captured in
[`docs/examples/web/SELFHEAL.md`](examples/web/SELFHEAL.md).

## 4. Live observation parity (brain sees what the hands see)

A subtle correctness property: whether the agent drives a single `--action` or a
whole `--workflow`, the post-action observation it gets back is built by the **same
payload builders** (`build_success_payload` / `build_failure_payload` in
`cli/modes/action.py`), reused by `cli/modes/workflow.py`. On failure the agent
receives a real diagnosis (error code, candidate elements, recommended next step)
derived from the live page — not a stale summary. One observation per execute,
single-sourced, identical across shell `--json` and MCP. This keeps the brain's
model of the page honest.

## 5. Cross-platform over one protocol

All three platforms subclass one abstract base, `common/adapters/base_adapter.py`:

- `common/adapters/android_adapter.py` — uiautomator2 (real devices).
- `common/adapters/ios_adapter.py` — WebDriverAgent (real devices).
- the web adapter — Playwright.

Because they share the action protocol, the agent-facing surface is identical across
Web, Android, and iOS. **Driving real physical phones — not just a headless browser —
is the one capability pure-web agents (Playwright MCP, Browser Use) structurally
can't match.**

## 6. Engineering hygiene as a feature

The output is only as trustworthy as the engine, so the engine is held to a
production bar:

- **551 tests** (`pytest tests/`), spanning the cache, the self-heal gates, the MCP
  payload builders, and the platform compressors — driven with fakes so the suite
  runs without a browser or a live model.
- **CI matrix** ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) on Python
  **3.11 and 3.12**, gating three ways on every push:
  `ruff check .` (whole repo) → `mypy cli/ common/ config/ utils/` → `pytest tests/ -q`.
- **Strict typing** layered in by package via `pyproject.toml` mypy overrides — the
  agent-facing modules are held to a stricter standard than the edges.
- **~12,200 lines** of typed Python across `cli/ common/ config/ utils/`.

For a reader evaluating ScreenForge as a portfolio piece: the interesting part isn't
that it clicks buttons — it's that a black-box-feeling capability (an agent that
writes and heals its own tests) is built on a deterministic, well-tested,
fully-typed core where every LLM decision is observable and every automatic code
edit is gated and reversible.
