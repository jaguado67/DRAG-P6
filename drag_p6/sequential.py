from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Tuple

import pandas as pd

from .drag import (
    EPS,
    TRACE_TOL,
    _coord_to_date,
    _finish_driver,
    _node_label,
    _path_switch,
    _path_text,
    _schedule_with_trace,
    _trace_path,
    _wbs_area,
    _location,
)


@dataclass
class TargetState:
    target_h: float
    driver_tid: str
    driver_label: str
    finish_ties: list
    path: list
    path_text: str
    starts: dict
    finishes: dict
    durations: dict
    trace: dict


def _target_state(network, target_key: str, durations_override=None) -> TargetState:
    starts, finishes, durations, trace, _ = _schedule_with_trace(network, durations_override)
    is_project = target_key == "__PROJECT_EARLY_FINISH__"

    if is_project:
        driver_tid, ties = _finish_driver(finishes, network)
        target_h = finishes[driver_tid]
        endpoint = driver_tid
    else:
        driver_tid = target_key
        ties = [target_key]
        target_h = finishes[target_key]
        endpoint = target_key

    path = _trace_path(network, endpoint, trace)
    return TargetState(
        target_h=float(target_h),
        driver_tid=driver_tid,
        driver_label=_node_label(network, driver_tid),
        finish_ties=ties,
        path=path,
        path_text=_path_text(network, path),
        starts=starts,
        finishes=finishes,
        durations=durations,
        trace=trace,
    )


def _minimum_compression_for_gain(
    network,
    target_key: str,
    current_durations: Dict[str, float],
    task_id: str,
    current_target_h: float,
    max_gain_h: float,
    min_duration_h: float,
    gain_tolerance_h: float = 1e-7,
    iterations: int = 50,
) -> Tuple[float, TargetState]:
    """Find the smallest duration reduction that reaches the current one-activity plateau.

    This avoids assuming that target gain equals duration reduction. It is robust to PDM
    relationship types because the target response is measured by repeated rescheduling.
    """
    d0 = float(current_durations[task_id])
    max_compression = max(0.0, d0 - float(min_duration_h))
    if max_compression <= EPS:
        return 0.0, _target_state(network, target_key, current_durations)

    goal = max(0.0, float(max_gain_h) - float(gain_tolerance_h))
    lo, hi = 0.0, max_compression
    best_state = None

    for _ in range(iterations):
        mid = (lo + hi) / 2.0
        trial = dict(current_durations)
        trial[task_id] = max(min_duration_h, d0 - mid)
        state = _target_state(network, target_key, trial)
        gain = current_target_h - state.target_h
        if gain >= goal:
            hi = mid
            best_state = state
        else:
            lo = mid

    compression = min(max_compression, hi + 1e-6)
    trial = dict(current_durations)
    trial[task_id] = max(min_duration_h, d0 - compression)
    state = _target_state(network, target_key, trial)
    return compression, state


def compute_sequential_frontier(
    network,
    target_key: str = "__PROJECT_EARLY_FINISH__",
    max_stages: int = 20,
    max_compression_pct: float = 100.0,
    minimum_stage_gain_h: float = 1e-4,
    gain_tolerance_h: float = 1e-7,
):
    """Build a sequential, single-activity greedy compression frontier.

    Policy at each stage:
      1) reschedule the current network;
      2) inspect the representative controlling path;
      3) test every compressible activity on that path against its allowed minimum duration;
      4) choose the activity with the greatest current target gain;
      5) apply only the minimum compression needed to reach that one-activity gain plateau;
      6) reschedule and repeat.

    Important: this is a *sequential single-activity frontier*, not a global cost-optimal
    crashing solution. If tied controlling paths require simultaneous compression, the
    algorithm stops at a multi-path / anchor barrier instead of pretending the frontier is complete.
    """
    max_stages = max(1, int(max_stages))
    pct = max(0.0, min(100.0, float(max_compression_pct))) / 100.0

    baseline_durations = dict(network.baseline_durations)
    current_durations = dict(baseline_durations)
    min_durations = {tid: max(0.0, d * (1.0 - pct)) for tid, d in baseline_durations.items()}

    initial = _target_state(network, target_key, current_durations)
    current = initial
    cumulative_gain = 0.0
    cumulative_compression = 0.0
    rows = []
    stop_reason = "Maximum stages reached"

    for stage in range(1, max_stages + 1):
        # Only the current representative controlling path is eligible in this release.
        candidates = []
        for tid in current.path:
            d0 = float(current_durations.get(tid, 0.0))
            min_d = float(min_durations.get(tid, 0.0))
            if d0 - min_d <= EPS:
                continue

            trial = dict(current_durations)
            trial[tid] = min_d
            trial_state = _target_state(network, target_key, trial)
            max_gain = max(0.0, current.target_h - trial_state.target_h)
            if max_gain > minimum_stage_gain_h:
                candidates.append((max_gain, d0 - min_d, tid, trial_state))

        if not candidates:
            if len(current.finish_ties) > 1:
                stop_reason = "Multi-path barrier: tied target drivers require simultaneous compression"
            else:
                stop_reason = "No positive single-activity gain on the representative controlling path; fixed anchor or multi-path barrier governs"
            break

        # Greatest current target gain. Tie-break by smaller available compression, then Activity ID.
        candidates.sort(
            key=lambda x: (
                -x[0],
                x[1],
                network.nodes[x[2]]["activity_id"],
            )
        )
        max_gain, available_compression, tid, full_trial_state = candidates[0]

        compression_h, new_state = _minimum_compression_for_gain(
            network=network,
            target_key=target_key,
            current_durations=current_durations,
            task_id=tid,
            current_target_h=current.target_h,
            max_gain_h=max_gain,
            min_duration_h=min_durations[tid],
            gain_tolerance_h=gain_tolerance_h,
        )

        # Numerical safety: if binary search landed too conservatively, use the permitted minimum.
        stage_gain = max(0.0, current.target_h - new_state.target_h)
        if stage_gain <= minimum_stage_gain_h:
            trial = dict(current_durations)
            trial[tid] = min_durations[tid]
            new_state = _target_state(network, target_key, trial)
            compression_h = current_durations[tid] - min_durations[tid]
            stage_gain = max(0.0, current.target_h - new_state.target_h)

        if stage_gain <= minimum_stage_gain_h or compression_h <= EPS:
            stop_reason = "Numerical / zero-gain barrier"
            break

        before_duration = float(current_durations[tid])
        after_duration = max(min_durations[tid], before_duration - compression_h)
        current_durations[tid] = after_duration

        # Re-evaluate from the exact updated duration dictionary so the next stage starts cleanly.
        new_state = _target_state(network, target_key, current_durations)
        stage_gain = max(0.0, current.target_h - new_state.target_h)
        cumulative_gain += stage_gain
        cumulative_compression += compression_h

        switch = _path_switch(network, current.path, new_state.path)
        if not switch["changed"]:
            path_outcome = "Same Path"
        elif switch["common_suffix_len"] == 0:
            path_outcome = "Terminal Shift"
        else:
            path_outcome = "Replacement Path"

        n = network.nodes[tid]
        rows.append({
            "Stage": stage,
            "Task ID": tid,
            "Activity ID": n["activity_id"],
            "Activity Name": n["name"],
            "WBS Area": _wbs_area(n.get("wbs_path", "")),
            "Location": _location(n.get("wbs_path", "")),
            "RD Before (h)": before_duration,
            "RD After (h)": after_duration,
            "Compression Applied (h)": compression_h,
            "Stage Target Gain (h)": stage_gain,
            "Compression Transmission Ratio": stage_gain / compression_h if compression_h > EPS else 0.0,
            "Cumulative Compression (h)": cumulative_compression,
            "Cumulative Target Gain (h)": cumulative_gain,
            "Target Before (h coord)": current.target_h,
            "Target After (h coord)": new_state.target_h,
            "Target Before Date": _coord_to_date(network, current.target_h),
            "Target After Date": _coord_to_date(network, new_state.target_h),
            "Baseline Driver": current.driver_label,
            "New Driver": new_state.driver_label,
            "Driver Tie Count After": len(new_state.finish_ties),
            "Path Outcome": path_outcome,
            "Path Switch": switch["switch_point"],
            "Replacement Controlling Activity": switch["replacement"],
            "Controlling Path Before": current.path_text,
            "Controlling Path After": new_state.path_text,
            "Path Activities Before": len(current.path),
            "Path Activities After": len(new_state.path),
        })

        current = new_state
    else:
        stop_reason = "Maximum stages reached"

    frontier = pd.DataFrame(rows)
    total_gain = initial.target_h - current.target_h
    total_compression = sum(
        max(0.0, baseline_durations[tid] - current_durations.get(tid, baseline_durations[tid]))
        for tid in baseline_durations
    )

    meta = {
        "target_key": target_key,
        "initial_target_h": initial.target_h,
        "final_target_h": current.target_h,
        "initial_target_date": _coord_to_date(network, initial.target_h),
        "final_target_date": _coord_to_date(network, current.target_h),
        "initial_driver": initial.driver_label,
        "final_driver": current.driver_label,
        "initial_path": initial.path_text,
        "final_path": current.path_text,
        "stages_completed": len(frontier),
        "total_target_gain_h": total_gain,
        "total_compression_applied_h": total_compression,
        "overall_transmission_ratio": total_gain / total_compression if total_compression > EPS else 0.0,
        "path_switch_stages": int((frontier["Path Outcome"] != "Same Path").sum()) if not frontier.empty else 0,
        "max_compression_pct": pct * 100.0,
        "stop_reason": stop_reason,
        "frontier_type": "Sequential single-activity greedy",
        "complete_global_frontier": False,
    }
    return frontier, meta
