"""Experimental multi-calendar PDM scheduling kernel.

Calendar-aware forward pass in real dates. This is a separate, opt-in research
kernel; it does NOT silently replace the reconciled single-calendar production
engine. Lag calendars require explicit selection and P6 F9 comparisons.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping


@dataclass(frozen=True)
class CalendarRelationship:
    pred: str
    succ: str
    kind: str
    lag_hours: float = 0.0
    lag_calendar_id: str | None = None


def forward_pass(
    order: list[str],
    durations_h: Mapping[str, float],
    activity_calendar_ids: Mapping[str, str],
    calendars: Mapping[str, object],
    relationships: list[CalendarRelationship],
    earliest_starts: Mapping[str, datetime],
):
    """Return (starts, finishes) using each activity's working calendar.

    FS/SS/FF/SF constraints are evaluated as timestamp inequalities. Lag is
    applied with an explicit lag calendar, or (default) predecessor calendar.
    Calendar.add_work_hours must support negative offsets. A fixed anchor is
    NEVER inferred from the fitted baseline in this function.
    """
    incoming = {tid: [] for tid in order}
    for edge in relationships:
        if edge.pred not in incoming or edge.succ not in incoming:
            raise ValueError("Relationship refers to an unknown activity")
        incoming[edge.succ].append(edge)
    starts, finishes = {}, {}
    for tid in order:
        if tid not in activity_calendar_ids:
            raise ValueError(f"Missing calendar assignment for {tid}")
        cid = activity_calendar_ids[tid]
        if cid not in calendars:
            raise ValueError(f"Unknown activity calendar {cid}")
        cal = calendars[cid]
        duration = float(durations_h[tid])
        if duration < 0:
            raise ValueError("Negative remaining duration")
        options = []
        if tid in earliest_starts:
            options.append(earliest_starts[tid])
        for edge in incoming[tid]:
            if edge.pred not in starts:
                raise ValueError("Order is not topological")
            lag_cid = edge.lag_calendar_id or activity_calendar_ids[edge.pred]
            if lag_cid not in calendars:
                raise ValueError(f"Unknown lag calendar {lag_cid}")
            lag_cal = calendars[lag_cid]
            if edge.kind in ("FS", "FF"):
                event = finishes[edge.pred]
            elif edge.kind in ("SS", "SF"):
                event = starts[edge.pred]
            else:
                raise ValueError(f"Unsupported relationship {edge.kind}")
            requirement = lag_cal.add_work_hours(event, edge.lag_hours)
            if edge.kind in ("FF", "SF"):
                requirement = cal.add_work_hours(requirement, -duration)
            options.append(requirement)
        if not options:
            raise ValueError(f"No explicit start boundary for {tid}")
        candidate = max(options)
        # Align to successor calendar's next working instant, by advancing
        # an epsilon hour. Zero-duration milestones remain at exact event time.
        if duration > 0:
            advanced = cal.add_work_hours(candidate, 1e-7)
            candidate = advanced.replace(microsecond=0) if advanced > candidate else candidate
        starts[tid] = candidate
        finishes[tid] = cal.add_work_hours(candidate, duration)
    return starts, finishes


def compare_counterfactuals(
    baseline_finish: datetime,
    scenarios: Mapping[str, datetime],
    p6_reference_finishes: Mapping[str, datetime],
    tolerance_seconds: float = 60.0,
):
    """Compare scenario gains to independently recalculated P6 F9 outcomes.

    References are mandatory: baseline reconciliation alone is NOT a DRAG
    validation. Returns an audit dictionary per scenario.
    """
    if not p6_reference_finishes:
        raise ValueError("Independent P6 F9 scenario references are required")
    results = {}
    for scenario, p6_finish in p6_reference_finishes.items():
        if scenario not in scenarios:
            raise ValueError(f"Missing motor scenario {scenario}")
        model_finish = scenarios[scenario]
        error_seconds = abs((model_finish - p6_finish).total_seconds())
        results[scenario] = {
            "model_finish": model_finish,
            "reference_finish": p6_finish,
            "finish_error_hours": error_seconds / 3600,
            "pass": error_seconds <= tolerance_seconds,
        }
    return results
