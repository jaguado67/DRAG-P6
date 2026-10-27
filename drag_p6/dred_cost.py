"""DRED and DRAG Cost scenario evaluation on the existing calibrated P6 network.

DRED is an independently estimated duration after doubling resources, not
an assumed productivity equation. All monetary values are user-provided.
This module does not perform resource leveling.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from .calibrated import schedule


@dataclass(frozen=True)
class DredCostScenario:
    task_id: str
    dred_duration_h: float
    economic_value_per_hour: float | None = None
    incremental_intervention_cost: float | None = None


def _nonnegative_finite(value: float, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite nonnegative number") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field} must be a finite nonnegative number")
    return number


def evaluate_dred_cost(network, scenario: DredCostScenario,
                       target_key: str = "__PROJECT_EARLY_FINISH__") -> dict:
    """Reschedule one DRED intervention and optionally value its target gain.

    Time gains are measured in the calibrated network's working-hour coordinate.
    Economic valuation requires a separately justified project-level value/hour.
    Monetary outputs are intentionally unavailable until that value is supplied.
    """
    if scenario.task_id not in network.baseline_durations:
        raise ValueError("Unknown task_id in calibrated remaining network")
    if target_key != "__PROJECT_EARLY_FINISH__" and target_key not in network.baseline_durations:
        raise ValueError("Unknown target_key in calibrated remaining network")

    before_d = _nonnegative_finite(network.baseline_durations[scenario.task_id], "Remaining Duration")
    after_d = _nonnegative_finite(scenario.dred_duration_h, "DRED")
    if after_d > before_d:
        raise ValueError("DRED must not exceed current Remaining Duration for a compression scenario")

    value_rate = (None if scenario.economic_value_per_hour is None else
                  _nonnegative_finite(scenario.economic_value_per_hour, "Economic value/hour"))
    intervention_cost = (None if scenario.incremental_intervention_cost is None else
                         _nonnegative_finite(scenario.incremental_intervention_cost, "Intervention cost"))

    _, baseline_finishes, _ = schedule(network)
    _, scenario_finishes, _ = schedule(network, {scenario.task_id: after_d})
    if target_key == "__PROJECT_EARLY_FINISH__":
        baseline_target = max(baseline_finishes.values())
        scenario_target = max(scenario_finishes.values())
    else:
        baseline_target = baseline_finishes[target_key]
        scenario_target = scenario_finishes[target_key]

    signed_gain = baseline_target - scenario_target
    # Do not conceal a regression behind a zero-clipped benefit.
    gross_value = signed_gain * value_rate if value_rate is not None else None
    net_value = (gross_value - intervention_cost
                 if gross_value is not None and intervention_cost is not None else None)

    return {
        "task_id": scenario.task_id,
        "target_key": target_key,
        "remaining_duration_h": before_d,
        "dred_duration_h": after_d,
        "duration_reduction_h": before_d - after_d,
        "baseline_target_h": baseline_target,
        "scenario_target_h": scenario_target,
        "target_gain_h_signed": signed_gain,
        "economic_value_per_hour": value_rate,
        "gross_time_value": gross_value,
        "incremental_intervention_cost": intervention_cost,
        "net_economic_value": net_value,
        "mode": "LOGIC DRED SCENARIO — NO RESOURCE RE-LEVELING",
        "assumptions": (
            "DRED is supplied as an engineering estimate; "
            "resource doubling and physical feasibility are not inferred; "
            "economic value and intervention cost are independently supplied."
        ),
    }
