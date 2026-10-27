# TORRE MAR V2 — Development benchmark

The user's XER was used as a validation benchmark during development but is **not included** in this package.

## Baseline reconciliation

- Activities in XER: 1,465
- Completed: 45
- Remaining activities checked: 1,420
- Dynamic remaining relationships: 1,583
- Fixed/historical internal relationships: 120
- External relationships detected: 46
- Calibration anchors: 60
- Maximum P6 baseline start error: ~0.000001 h
- Maximum P6 baseline finish error: ~0.0000013 h
- Reconciliation status: PASS

## Important discovery

The first logic-only prototype ended on the March 2028 `Fin Proyecto` path. The XER contains activities with P6 Early Finish dates extending to 27-Apr-2028. Therefore the improved engine distinguishes:

1. **Project Early Finish DRAG** — target is the latest P6 early completion.
2. **Milestone DRAG** — target is a selected Finish Milestone, e.g. `A1940 - Fin Proyecto`.

### Project Early Finish target

- Baseline target: 27-Apr-2028 13:36
- Baseline driver: A27650 — Aseo
- Activities with DRAG > 0: 55
- Maximum DRAG: 80 h = 10.00 working days at 8 h/day

### A1940 — Fin Proyecto target

- Baseline target: 01-Mar-2028 13:09
- Activities with DRAG > 0: 42
- Maximum calibrated milestone DRAG: 61.15 h = 7.64375 working days

The earlier 15.26-day result is therefore retained only as evidence of why the reconciliation correction was necessary; it is not treated as validated project DRAG.
