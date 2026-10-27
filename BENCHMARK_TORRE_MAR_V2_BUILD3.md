# DRAG-P6 v1.0.0.0 Build 3 — TORRE MAR V2 Benchmark

## P6 Reconciliation Gate

- Status: RECONCILED
- Activities checked: 1,420
- Maximum baseline error: ~0.000001 h
- Dynamic relationships: 1,583
- Fixed / historical relationships: 120
- External relationships: 46

## Target 1 — Project Early Finish

Baseline terminal driver: **A27650 — Aseo**  
Baseline controlling chain: **56 activities**

Results:

- Activities with DRAG: 55
- Maximum single-activity DRAG: 80 h = 10.00 working days
- Full transmission: 55
- Partial transmission: 0
- Path switches among positive-DRAG scenarios: 1
- All 55 positive-DRAG activities are concentrated in WBS area **08. Punto Fijo**

### Interpretation correction

The 10-day maximum is **not** a demonstrated parallel-path takeover threshold. Build 3 shows that zeroing the 10-day activities generally keeps the same representative controlling chain and transmits the full 10 days to Project Early Finish.

The only positive-DRAG path change is when the terminal activity **A27650 — Aseo** is reduced to zero, after which **A27640 — Detallado PF** becomes the project terminal driver. This is a terminal-driver change on the same chain, not a new parallel route.

## Target 2 — A1940 — Fin Proyecto

Results:

- Activities with DRAG: 42
- Maximum DRAG: 61.15 h = 7.64375 working days
- Full transmission: 11
- Partial transmission: 31
- Path-switch scenarios: 31

For the maximum-DRAG group, Build 3 identifies the replacement branch entering at:

**A1910 — Entrega Calidad Piso 15 → A1920**

Examples:

| Activity | RD (h) | DRAG (h) | Efficiency | Transmission | Replacement branch |
|---|---:|---:|---:|---|---|
| A4800 | 336.00 | 61.15 | 0.181994 | Partial | A1910 → A1920 |
| A3370 | 144.00 | 61.15 | 0.424653 | Partial | A1910 → A1920 |
| A19630 | 112.00 | 61.15 | 0.545982 | Partial | A1910 → A1920 |
| A6700 | 96.00 | 61.15 | 0.636979 | Partial | A1910 → A1920 |
| A5700 | 64.00 | 61.15 | 0.955469 | Partial | A1910 → A1920 |

This benchmark demonstrates the distinction between:

1. **Full transmission:** the complete RD reduction reaches the selected target.
2. **Partial transmission:** only part of the RD reduction reaches the target because another branch takes control.
3. **Replacement path:** Build 3 identifies the branch that becomes controlling after the counterfactual intervention.
