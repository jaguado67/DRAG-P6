# DRAG-P6 v1.1.0.0 — Spider Project JSON Benchmark R1

## Source benchmark

Project: **ROAD 1 KM** (`1km_road`)

The Spider JSON contains 17 activities, 32 schedule-enabled links, one 10 h/day calendar, 19 volume/quantity links and 13 time links. Ten activities expose a stored Spider `f_DRAGH` value.

## Baseline reconstruction

The DRAG-P6 Spider parser reconstructs the schedule-enabled logic and quantity/time lags before comparing DRAG.

- Activities: 17
- Links: 32
- Volume links: 19
- Time links: 13
- Maximum start-event error: ~0.000278 h
- Finish target error: ~0.000278 h
- Baseline gate: **PASS WITH WARNINGS**

The warning is caused mainly by exported `EarlyFin` for activity `drc`, which is not reproduced by simple `EarlyStart + DurPlan` arithmetic. The project Finish target itself reconciles almost exactly.

## DRAG cross-validation R1

Tolerance: 0.25 h.

- Spider DRAG reference activities: 10
- Near-exact matches: 1 / 10
- MAE: ~5.907 h
- RMSE: ~7.677 h
- Pearson correlation on non-negative Spider DRAG cases: ~0.929
- Spearman rank correlation on non-negative Spider DRAG cases: ~0.725
- Negative Spider DRAG cases: 1 (`pnd`)

The first exact benchmark is `drl — Drainage Layout`: both engines return approximately **47.619 h**.

The high positive Pearson correlation is encouraging for directional exposure, but the magnitude mismatches are material and must not be hidden. The principal investigation area is Spider's handling of FF/SS quantity dependencies and its negative-DRAG / anti-crashing convention.

## R1 interpretation

DRAG-P6 currently uses the shortening-only counterfactual:

`DRAG_i = max(0, PF_baseline - PF_if_duration_i_is_zero)`

The Spider JSON reference can contain negative DRAG. R1 does not force those values into the DRAG-P6 definition. Instead it reports the Spider value, the signed counterfactual target change and the residual side by side.

This benchmark is therefore a **cross-validation instrument**, not a claim that the two algorithms are already equivalent.
