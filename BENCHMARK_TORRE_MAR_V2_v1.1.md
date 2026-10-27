# TORRE MAR V2 — DRAG-P6 v1.1.0.0 Benchmark

## P6 reconciliation

The v1.1 engine preserves the v1.0 reconciliation gate and reproduces the remaining-network P6 Early Dates within numerical tolerance before DRAG or compression results are released.

## Target: Project Early Finish

Baseline Project Early Finish:

**27-Apr-2028 13:36**

Baseline terminal driver:

**A27650 — Aseo**

Using the v1.1 sequential single-activity frontier with a theoretical 100% maximum compression per activity:

| Stage | Activity | Compression applied | Target gain | Cumulative gain | Path outcome |
|---:|---|---:|---:|---:|---|
| 1 | A11970 | 80.00 h | 80.00 h | 80.00 h | Same Path |
| 2 | A24170 | 80.00 h | 80.00 h | 160.00 h | Same Path |
| 3 | A24180 | 80.00 h | 80.00 h | 240.00 h | Same Path |
| 4 | A24190 | 40.45 h | 40.45 h | 280.45 h | Terminal Shift |

Cumulative target gain:

**280.45 h = 35.05625 working days at 8 h/day**

Resulting target date:

**01-Mar-2028 13:09**

At Stage 4 the terminal controlling driver shifts from **A27650 — Aseo** to **A14500 — Entrega a Calidad para Observaciones**.

The engine then stops at a **multi-path barrier**: additional target reduction would require coordinated/simultaneous compression rather than another independent single-activity intervention.

This result is especially useful because 35.05625 d is also the separation observed in the P6 model between the 27-Apr-2028 Project Early Finish condition and the 01-Mar-2028 finish regime previously identified in the v1.0 analysis.

## Target: A1940 — Fin Proyecto

Baseline target:

**01-Mar-2028 13:09**

The first sequential stage selects **A5700** and obtains approximately:

- Compression applied: **61.15 h**
- Target gain: **61.15 h = 7.64375 d**
- Path outcome: **Replacement Path**
- Replacement controlling activity: **A1910 — Entrega Calidad Piso 15**

The engine then reaches a fixed-anchor / multi-path barrier for single-activity sequential compression.

## Interpretation boundary

These stages form the v1.1 **sequential single-activity frontier**. They are not a cost-optimal crashing plan and do not prove that no additional project compression is possible after the reported barrier. The barrier means that the next improvement requires simultaneous-path or constraint-aware optimization.
