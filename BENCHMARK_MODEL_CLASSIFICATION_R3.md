# DRAG-P6 v1.1.0.0 — Model Classification Gate R3

## TORRE MAR V2.xer

Detected:

- Activities: 1,465
- Internal logic relationships: 1,703
- Resource assignments: 1,321
- Activities with resource assignments: 1,321
- Assigned resource records: 1
- Assigned resource name: `Dummy`
- Exported resource-leveling evidence: **unconfirmed**
- Duration model: **P6 Remaining Duration · Fixed Duration dominant**
- Physical productivity model: **not established from standard P6 resource-unit rates**

Automatic recommendation:

**ASK BEFORE RUNNING**

The application therefore asks whether resources actually drive scheduled dates. If they do not, the correct current mode is **LOGIC DRAG**. If they do, the current P6 result is explicitly labelled **LOGIC DRAG — DIAGNOSTIC ONLY** until dynamic P6 resource re-leveling is implemented.

## Spider ROAD 1 KM JSON

Detected:

- Activities: 17
- Logic relationships: 32
- Resources: 16
- Scheduled resource assignments: 81
- Inferred resource-order edges: 15
- Activities whose delay reason explicitly names a resource: 5
- `DPH=Productivity`: 15 activities
- `DPH=Duration`: 1 activity
- Milestone: 1
- Negative Spider DRAG references: 1

Automatic recommendation:

**RESOURCE-CONSTRAINED DRAG · FROZEN RESOURCE ORDER**

The positive Spider DRAG benchmark remains 9/9 within numerical tolerance. The negative DRAG case remains outside the frozen-order engine and requires dynamic resource re-leveling / schedule adjustment.
