# DRAG-P6 v1.1.0.0 — Spider 1 km Benchmark R2

## Why R1 was incomplete

R1 reconstructed the Spider **Early** schedule and compared zero-duration target gain against `f_DRAGH`.
That baseline was conceptually wrong for this file because the project is resource constrained: Spider's scheduled
`Start` / `Fin` dates extend beyond the logic-only `EarlyStart` / `EarlyFin` dates.

The clearest example is the Finish milestone:

- logic-only Early Finish: about 03-Feb-2020;
- resource-constrained scheduled Finish: 06-Feb-2020.

The file also exposes resource delay reasons and scheduled resource assignments.

## R2 correction

R2 reconstructs:

1. explicit FS / SS / FF / SF logic;
2. time and volume lags;
3. the resource-constrained Start/Fin baseline;
4. resource-order constraints inferred from the scheduled resource assignments;
5. zero-duration counterfactuals on that resource-aware graph.

The resource-order graph is intentionally described as **frozen resource order**. It preserves the resource
sequencing observed in the exported Spider plan; it is not yet a full dynamic resource re-leveller.

## 1 km result

Using a 0.01 h comparison tolerance:

| Activity | Spider DRAG (h) | DRAG-P6 R2 (h) | Result |
|---|---:|---:|---|
| drl | 47.619167 | 47.619167 | Match |
| str | 0.121944 | 0.121944 | Match |
| stb | 13.114722 | 13.114778 | Match |
| srf | 2.086944 | 2.087000 | Match |
| ct2 | 17.066667 | 17.066222 | Match |
| ct1 | 8.586389 | 8.586056 | Match |
| rds | 13.131111 | 13.131111 | Match |
| trs | 2.500000 | 2.500000 | Match |
| brr | 22.727500 | 22.727500 | Match |
| pnd | -6.081667 | 0.000000 | Unresolved negative case |

### Positive reference result

- Positive Spider DRAG references: **9**
- Matches: **9 / 9**
- Positive MAE: approximately **0.000099 h**
- Positive Pearson correlation: approximately **1.000000**

### All references

- References with exported `f_DRAGH`: **10**
- Matches: **9 / 10**
- Remaining case: **pnd — Retention Pond**, Spider DRAG = **-6.081667 h**

## What the remaining negative case means

The frozen resource-order graph is monotone with respect to most predecessor-duration reductions.  It cannot
reproduce a negative resource-schedule DRAG that arises because Spider **re-levels / adjusts** the resource
schedule after the duration perturbation.

Therefore R2 does **not** replace Spider's negative value with zero and claim success. It reports the unresolved
case explicitly. The next research layer is a dynamic resource re-levelling engine or a calibrated recreation of
Spider's schedule-adjustment policy.

## Key conclusion

The 1 km benchmark shows that the earlier mismatch was not evidence that the DRAG counterfactual definition was
wrong. The main R1 error was benchmarking Spider's resource-schedule DRAG against a logic-only Early schedule.
Once resource sequencing is reconstructed, all **nine non-negative Spider DRAG values** are reproduced to
numerical tolerance.
