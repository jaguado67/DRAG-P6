# Multi-calendar counterfactual work — experimental branch

This branch **does not change production DRAG-P6 v1.1.0.0 R3**.
It introduces an isolated, opt-in prototype (`drag_p6/multicalendar.py`) plus initial tests.

## What is implemented
- Explicit calendar assignment per activity.
- Timestamp-based forward pass supporting FS/SS/FF/SF.
- Explicit lag-calendar selection, defaulting to predecessor calendar **only as an assumption to test**.
- No automatic baseline-fitted anchors.
- Fail-closed requirement for independent counterfactual reference scenarios.

## Not yet validated / not suitable for production
- Exact P6 calendar and lag-calendar selection modes, day boundaries and DST.
- Constraint semantics including dates, Must Finish/Start, and imposed limits.
- Actual dates, progress override, retained logic and out-of-sequence updates.
- External links, multi-project behavior and complex global project end.
- Unit tests not executed in an isolated test environment yet.
- No production integration or confirmed numerical agreement against P6 F9.

## Validation protocol
1. Use a small P6 reference XER with two different working calendars and FS/SS/FF/SF cases.
2. Export original plus one compressed-duration F9 recalculation per activity.
3. Compare baseline dates (reconciliation) **and** each scenario target date against recalculated P6.
4. Evaluate `DRAG_model = baseline_target - model_counterfactual_target`
   and `DRAG_P6 = baseline_target - F9_counterfactual_target` on a clearly specified
   project working-time measure or in elapsed time. These units must never be silently mixed.
5. Flag every missing reference and every error above tolerance. Only enable a
   validated calendar/lag/constraint combination in the app.

## Local verification
```powershell
git fetch origin
git switch feature/multicalendar-counterfactual-validation
py -m pytest tests/test_multicalendar.py -q
```
