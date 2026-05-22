## Summary

<!-- What does this PR do? 1-3 bullet points. -->

-

## Motivation

<!-- Why is this change needed? Link issues if applicable. -->

## Test plan

<!-- How did you verify this works? -->

- [ ] `pytest tests/` passes
- [ ] `ruff check .` passes
- [ ] Tested manually with: (describe command)

## Checklist

- [ ] Error messages use English three-tier format: `[EXXX] What. Why. Fix: ...`
- [ ] No `print()` — use `log.error/warning/info` from `common.logs`
- [ ] No hardcoded config values — everything via env vars in `config/config.py`
