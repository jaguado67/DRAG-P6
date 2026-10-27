# DRAG-P6 | DRED and DRAG Cost: Phase 1

## Purpose
This branch adds a **non-invasive scenario engine** that reuses the existing
P6-calibrated scheduling engine. It does not change Critical Path DRAG,
the baseline reconciliation code, or the current Streamlit interface.

## Definitions
- **Critical Path DRAG**: baseline target finish minus the target finish
  after zeroing one activity's remaining duration, under the selected
  scheduling model. Its accuracy depends on the CPM reconstruction.
- **DRED (Doubled Resource Estimated Duration)**: an independently justified
  estimate of the activity duration after doubling its resources. DRED is
  **not** calculated as RD/2. An estimator, crew model, or engineer supplies it.
- **DRED scenario target gain**: target finish before intervention minus
  target finish after setting the activity's remaining duration to DRED.
  Duration reduction and project gain are not interchangeable.
- **Gross time value**: signed target gain (working hours) multiplied by the
  independently supplied value of an hour of earlier project completion.
- **Net economic value**: gross time value minus the independently estimated
  incremental cost of the intervention.

## Phase 1 implementation
`drag_p6/dred_cost.py` exposes:
`DredCostScenario` and `evaluate_dred_cost(network, scenario, target_key)`.

It deliberately:
1. Rejects nonfinite/negative durations and costs, and DRED > current RD.
2. Leaves monetary outputs unavailable when economic assumptions are missing.
3. Retains signed time gain, rather than silently suppressing regressions.
4. Recalculates project finish or a specific target after the intervention.
5. Labels results **LOGIC DRED SCENARIO — NO RESOURCE RE-LEVELING**.

## Model fidelity limitations
The existing calibrated P6 engine supports only one remaining-activity
calendar and can include fixed reconciliation anchors. This phase does NOT
resolve multi-calendar scheduling, anchor validity, resource sequencing,
dynamic re-leveling, cost calendars, or non-linear time-dependent cash flows.

The exported result must never be presented as proof that doubled resources
physically achieve DRED, nor as a fully resource-constrained DRAG Cost.
The project-hour value must reflect a consistent economic time basis.

## Validation plan
- Run `py -m pytest tests/test_dred_cost.py`.
- Run all pre-existing tests for regressions.
- Compare hand-built parallel path cases and milestone-specific scenarios.
- Cross-check at least one feasible DRED compression in P6.
- Only then add UI forms and cost-oriented reporting.
