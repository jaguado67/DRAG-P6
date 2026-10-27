# Changelog

## v1.1.0.0 — Sequential Compression Frontier — Release 1

### Added
- Sequential Compression Frontier tab.
- Stage-by-stage `compress → reschedule → path switch → repeat` engine.
- Current-path candidate evaluation at every stage.
- Greedy maximum-current-target-gain selection policy.
- Numerical search for minimum compression required to reach a stage gain plateau.
- User-defined maximum theoretical compression percentage per activity.
- Stage Target Gain.
- Cumulative Target Gain.
- Compression Applied.
- Cumulative Compression.
- Compression Transmission Ratio by stage.
- Target date before/after each stage.
- Path Outcome and Replacement Controlling Activity by stage.
- Multi-path / fixed-anchor barrier detection.
- Sequential frontier charts.
- Frontier export to Excel.
- Automated sequential-frontier test.

### Preserved from v1.0.0.0
- P6 Reconciliation Gate.
- P6-calibrated remaining network.
- Individual DRAG.
- DTR and Compression Headroom.
- Replacement-path analytics.
- WBS/location concentration.

### Explicit boundary
v1.1.0.0 does not claim global crash-cost optimality. Simultaneous compression of tied paths is not yet solved; the engine stops and reports the barrier.

## v1.1.0.0 — Spider JSON Benchmark R1

- Added Spider Project JSON input alongside Primavera P6 XER.
- Added direct parser for Spider `activities`, `links`, `calendars`, `days`, WBS and exported `f_DRAGH/f_DRAGD`.
- Added FS/SS/FF/SF reconstruction with time and quantity/volume lags.
- Added baseline reconciliation against Spider Early events and Finish target.
- Added activity-by-activity cross-validation: Spider DRAG vs DRAG-P6 counterfactual DRAG.
- Added signed counterfactual gain to expose anti-crashing behavior instead of hiding it.
- Added diagnostics for negative Spider DRAG and quantity-linked semantics.
- Added Excel benchmark export.
- No claim is made that R1 reproduces Spider's proprietary DRAG semantics; mismatches are intentionally surfaced as validation evidence.

## Spider Benchmark R2 — Resource-Aware correction

- Corrected Spider benchmark baseline from logic-only `EarlyStart/EarlyFin` to resource-constrained `Start/Fin`.
- Added inference of resource-order constraints from scheduled Spider assignments and resource capacities.
- Added frozen resource-order counterfactual scheduling.
- Positive 1 km reference cases now match Spider 9/9 within 0.01 h.
- Negative DRAG remains explicitly unresolved because it requires dynamic re-levelling / schedule adjustment.

## v1.1.0.0 — Model Classification Gate R3

### Added
- New **Schedule Model Classification Gate** before DRAG interpretation.
- Explicit analytical labels:
  - **LOGIC DRAG**
  - **RESOURCE-CONSTRAINED DRAG REQUIRED**
  - **LOGIC DRAG — PROVISIONAL**
  - **LOGIC DRAG — DIAGNOSTIC ONLY** when the user confirms resource-driven dates but the P6 counterfactual engine cannot dynamically re-level resources.
- P6 automatic detection of:
  - activity duration types;
  - logic relationships;
  - calendars and constraints;
  - TASKRSRC resource assignments and affected activities;
  - resource records and resource names;
  - exported leveling-related SCHEDOPTIONS / resource level flags.
- P6 asks **whether resources actually drive scheduled dates** when assignments exist but the XER cannot prove the scheduling role.
- P6 asks whether Remaining Duration is being treated as the scheduling input or is physically derived from quantity/productivity outside P6.
- Standard P6 resource-unit rates are explicitly **not** treated as a construction productivity model.
- Spider JSON automatic classification of resource-constrained and productivity-aware model evidence.
- MODEL_CLASSIFICATION worksheet in both P6 and Spider Excel exports.
- DRAG Mode and duration-basis context added to P6 export metadata.

### Benchmark classification
- TORRE MAR V2: 1,321 resource assignments across 1,321 activities, but only one assigned resource (`Dummy`) and no exported evidence that the last schedule was resource-levelled. Classification: **ASK BEFORE RUNNING**; fixed-duration / Remaining-Duration model dominant.
- Spider ROAD 1 KM: 16 resources, 81 scheduled resource assignments, 15 inferred resource-order edges, 5 resource-delay activities, and 15 activities explicitly marked `DPH=Productivity`. Classification: **RESOURCE-CONSTRAINED DRAG · FROZEN RESOURCE ORDER**.

### Test status
- 10 automated tests passing, including P6 and Spider model-classification tests.
