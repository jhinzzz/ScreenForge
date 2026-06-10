# Self-Healing Walkthrough — a real heal, captured live

> **Path taken: REAL.** Everything below is the actual output of a live self-heal
> run against `the-internet.herokuapp.com/checkboxes` on 2026-06-10. The LLM
> healer endpoint responded (confidence 0.90); nothing here is fabricated or
> illustrative. The throwaway demo file and its `.bak` were deleted after
> capture — only this writeup is committed.

## What self-healing is

When the UI changes and a committed test's locator stops matching, ScreenForge's
engine analyzes the failure scene (the live DOM tree + a failure screenshot),
asks the model for a structured fix with a confidence score, validates that fix,
backs up the original, and overwrites the test in place. Your committed pytest
file survives a UI change instead of just going red.

## How we reproduced it

We took the green `test_checkboxes.py` from this gallery and broke its selector —
`#checkboxes` → `#checkboxes_BROKEN` at all four sites — to simulate a UI change
that renamed an element. Then we ran it once:

```bash
cp docs/examples/web/test_checkboxes.py docs/examples/web/test_selfheal_demo.py
sed -i '' "s/#checkboxes/#checkboxes_BROKEN/g" docs/examples/web/test_selfheal_demo.py

RUN_LIVE_PLATFORM_TESTS=true TEST_PLATFORM=web \
  AUTO_HEAL_ENABLED=true AUTO_HEAL_TRIGGER_THRESHOLD=1 \
  .venv/bin/python -m pytest docs/examples/web/test_selfheal_demo.py -q
```

`AUTO_HEAL_TRIGGER_THRESHOLD=1` makes the engine heal on the **first** failure
(the in-memory failure counter lives for one pytest process, so a single run with
threshold 1 is the deterministic way to trigger it; the default threshold is 2,
i.e. heal after two consecutive failures of the same test in one session).

## What the engine logged (verbatim)

```
⚠️ Test failure detected: …::test_checkboxes (consecutive failures: 1)
🚑 [Self-Healing] Triggered — analyzing failure scene...
🔍 Extracting DOM/XML structure for self-healing analysis...
⏱️ [HealerBrain] Done in 25.61s (confidence=0.90,
     desc=修正定位器的ID，将 `#checkboxes_BROKEN` 改为 `#checkboxes`，以正确定位 checkbox 元素)
📦 [Self-Healing] Original script backed up to: …/test_selfheal_demo.py.bak
✅ [Self-Healing] Script healed successfully (confidence=0.90)
✅ [Self-Healing] Fixed file written to: …/test_selfheal_demo.py
💡 [Self-Healing] Re-run pytest to verify the healed test case.
```

The first run still reports `1 failed` — by design. Healing fires in pytest's
post-failure hook (`conftest.py` `pytest_runtest_makereport`), so the repair lands
*after* the verdict for that run is recorded. The engine tells you to re-run.

## The repair the engine made (real diff: `.bak` → healed)

```diff
-    with allure.step('Click: [#checkboxes_BROKEN input:first-child]'):
-        log.info('Action: click [#checkboxes_BROKEN input:first-child]')
-        d.locator('#checkboxes_BROKEN input:first-child').first.click(timeout=30000.0)
-    with allure.step('Assert: element [#checkboxes_BROKEN] exists'):
-        log.info('Assert: check element [#checkboxes_BROKEN] exists')
+    with allure.step('Click: [#checkboxes input:first-child]'):
+        log.info('Action: click [#checkboxes input:first-child]')
+        d.locator('#checkboxes input:first-child').first.click(timeout=30000.0)
+    with allure.step('Assert: element [#checkboxes] exists'):
+        log.info('Assert: check element [#checkboxes] exists')
-            d.locator('#checkboxes_BROKEN').first.wait_for(state='visible', timeout=30000.0)
+            d.locator('#checkboxes').first.wait_for(state='visible', timeout=30000.0)
```

It repaired all four broken sites, not just the one that threw. Re-running the
healed file:

```
1 passed in 1.90s
```

## The safety rails (why this is trustworthy, not magic)

Every heal passes through gates in `conftest.py` before it can touch your file:

1. **Confidence gate** — fixes below `AUTO_HEAL_MIN_CONFIDENCE` (default `0.7`) are
   logged and **skipped**, never applied. This heal scored `0.90`.
2. **Structural validation** — the fix must parse as Python (`ast.parse` in
   `common/ai_heal.py`) and must still contain a `def test_` function, or the
   overwrite is aborted.
3. **Backup before overwrite** — the original is copied to `<file>.bak` first, so
   a bad heal is always reversible.
4. **Trigger threshold** — healing only fires after `AUTO_HEAL_TRIGGER_THRESHOLD`
   consecutive failures of the same test, so a one-off flake doesn't rewrite code.

## Where this lives in the code

- Trigger + gates: `conftest.py` (`pytest_runtest_makereport` → `_trigger_self_healing`)
- The healer + structured `HealResult` (confidence, AST check): `common/ai_heal.py`
- Config knobs: `config/config.py` (`AUTO_HEAL_ENABLED`, `AUTO_HEAL_TRIGGER_THRESHOLD`, `AUTO_HEAL_MIN_CONFIDENCE`)
