# DRAG-P6 Engine v1.1.0.0

## R3 — Schedule Model Classification Gate

Before interpreting DRAG, the application now classifies the scheduling model and labels the analytical mode actually solved.

For P6, resource assignments alone do not prove resource leveling. If TASKRSRC assignments are present but leveling is not demonstrable from the XER, the app asks whether resources drive scheduled dates. If the answer is yes, the current P6 result is explicitly labelled **LOGIC DRAG — DIAGNOSTIC ONLY** because dynamic P6 resource re-leveling is not yet implemented.

The app also distinguishes a pure Remaining-Duration input from an RD that is physically derived from quantity/productivity outside P6. The DRAG equation is unchanged; the fidelity of the counterfactual schedule is what changes.

See `MODEL_CLASSIFICATION.md` for the formal mode definitions.


Primavera P6 external analytics engine for reconciled Critical Path DRAG and sequential compression analysis.

## What changes in v1.1.0.0

v1.0.0.0 established the P6-calibrated one-activity DRAG engine. v1.1.0.0 adds a staged compression laboratory:

**compress → reschedule → identify the new controlling path → compress again**

The new **Sequential Compression Frontier**:

1. Starts from the reconciled P6 remaining network.
2. Recalculates the selected target at every stage.
3. Reads the current representative controlling path.
4. Tests every compressible activity on that path against the selected theoretical compression limit.
5. Selects the activity producing the largest current target gain.
6. Numerically determines the minimum duration reduction needed to reach that stage's gain plateau.
7. Applies the compression, reschedules, records any path switch, and repeats.
8. Stops explicitly when a tied-path / fixed-anchor condition means single-activity compression can no longer move the target.

## Important interpretation

The v1.1 frontier is a **sequential single-activity greedy frontier**. It is not a global cost-optimal crashing solution.

This distinction matters. When two or more tied controlling paths must be compressed simultaneously, individual activity DRAG can be zero even though the project may still be compressible through coordinated action. v1.1 reports this as a **multi-path barrier** rather than claiming that no further compression exists.

A later optimization layer can add simultaneous path compression, activity minimum durations, crash costs and cost/time optimization.

## Main capabilities

- Primavera P6 XER input.
- P6 Reconciliation Gate before DRAG is released.
- Remaining-network calibration to P6 Early Dates.
- FS / SS / FF / SF relationships and lag handling.
- Historical/fixed vs dynamic relationship separation.
- External-relationship detection.
- One-activity DRAG counterfactuals.
- DRAG Transmission Ratio (DTR).
- Compression Headroom.
- Replacement controlling path analysis.
- Target selection: Project Early Finish or Finish Milestone.
- Sequential Compression Frontier.
- Path-switch stage tracking.
- Cumulative target-gain curve.
- Compression-effort vs target-gain curve.
- Excel export including sequential frontier stages.

## Launch in VS Code / PowerShell

```powershell
cd DRAG_P6_Engine_v1.1.0.0

py -m venv .venv

.venv\Scripts\Activate.ps1

py -m pip install -r requirements.txt

py -m streamlit run streamlit_app.py
```

## Tests

```powershell
py -m pip install pytest
py -m pytest
```

## Version boundary

### v1.0.0.0
One-activity reconciled DRAG and replacement-path analytics.

### v1.1.0.0
Sequential single-activity compression and staged path switching.

### Future optimization layer
Simultaneous critical-path compression, crash limits, crash costs and cost/time optimization.

## Spider Project JSON cross-validation — R1

v1.1.0.0 can now load a Spider Project JSON export as well as a P6 XER. When a JSON is loaded, the app opens a dedicated **Spider Project JSON · DRAG Cross-Validation** laboratory.

The benchmark reconstructs schedule-enabled links (FS/SS/FF/SF), time lags and quantity/volume lags, verifies the baseline against Spider-exported early events, runs the DRAG-P6 zero-duration counterfactual, and compares the result against the exported `f_DRAGH` value activity-by-activity.

This mode is deliberately a validation laboratory. It does not overwrite or normalize Spider values. Differences remain visible so that the DRAG-P6 algorithm can be refined from evidence rather than fitted invisibly.

### Run

```powershell
py -m streamlit run streamlit_app.py
```

Then load either:

- a Primavera P6 `.xer`, or
- a Spider Project `.json`.

The included `demo/1km_camino.json` is the initial Spider benchmark supplied for this development.

## Spider JSON Benchmark R2 — important correction

For Spider JSON, `f_DRAGH` is now benchmarked against the **resource-constrained Start/Fin schedule**. R1 used the
logic-only Early schedule, which was not the right baseline for the supplied 1 km resource-loaded project.

R2 infers **resource-order constraints** from the scheduled assignments and resource capacities, then performs the
same zero-duration counterfactual on the resource-aware graph. On the supplied `1km_camino.json`, all nine
non-negative exported Spider DRAG values match within 0.01 h. The one negative DRAG case is retained as an
explicit research boundary because reproducing it requires dynamic resource re-levelling / schedule adjustment,
not merely a frozen resource-order graph.