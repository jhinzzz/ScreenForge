# Mobile Examples — real-device recordings pending

> **Status: owner-blocked, honestly.** A web example can be driven end-to-end in
> CI with no hardware. A real-device mobile example cannot: it needs a physically
> connected iPhone (via WebDriverAgent) or Android device (via uiautomator2). No
> such recording is committed here **yet** — we will not fake one.

## Why there's no recording here (and why the README still claims real devices)

The README's "drives real iOS + Android devices" line is the project's one true
moat over pure-web agents (Playwright MCP, Browser Use). It is backed today by
**shipped capability + passing tests**, not by a screen recording:

- **Adapters exist and are exercised:** `common/adapters/ios_adapter.py` and
  `common/adapters/android_adapter.py` implement the same action protocol the web
  adapter does (subclassing `common/adapters/base_adapter.py`).
- **The mobile-specific logic is under test.** The mobile-capability suite
  (iOS DOM de-shadowing, Android row-label resolution, adapter behavior) currently
  reports **43 passed, 19 skipped, 0 failed** (the skips are live-device smoke
  tests that need attached hardware). Reproduce:

  ```bash
  .venv/bin/python -m pytest tests/ -q -k "ios or android or mobile or row_label or de_shadow"
  ```

## What's pending an owner with a device

When a device is attached, the deliverable is a recorded mobile flow (e.g. a real
login or navigation on a physical phone) plus its generated pytest, dropped into
`docs/examples/mobile/` exactly as the web examples live in `docs/examples/web/`.

Connection steps (device + WDA/uiautomator2 setup) are in
[`docs/mobile-setup.md`](../../mobile-setup.md).

Until then, this file documents the gap deliberately, so the "real device" claim
is backed by code and tests you can run — not vaporware.
