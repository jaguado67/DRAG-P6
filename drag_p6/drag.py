from __future__ import annotations

import math
from collections import defaultdict

import pandas as pd

from .calibrated import _edge_required_start


EPS = 1e-9
TRACE_TOL = 1e-7


def target_catalog(network):
    rows = []
    latest = max(network.baseline_finishes, key=network.baseline_finishes.get)
    n = network.nodes[latest]
    rows.append({
        "key": "__PROJECT_EARLY_FINISH__",
        "label": f"PROJECT EARLY FINISH — {n['activity_id']} · {n['name']}",
        "task_id": latest,
        "date": n["p6_finish_dt"],
        "kind": "project",
    })

    milestones = []
    for tid, n in network.nodes.items():
        if n["task_type"] == "TT_FinMile":
            milestones.append({
                "key": tid,
                "label": f"{n['activity_id']} — {n['name']}",
                "task_id": tid,
                "date": n["p6_finish_dt"],
                "kind": "milestone",
            })
    milestones.sort(key=lambda x: ("fin proyecto" not in x["label"].lower(), x["date"], x["label"]))
    rows.extend(milestones)
    return rows


def _schedule_with_trace(network, durations_override=None):
    """Schedule the calibrated network and retain one deterministic controlling predecessor."""
    durations = dict(network.baseline_durations)
    if durations_override:
        for k, v in durations_override.items():
            if k in durations:
                durations[k] = max(0.0, float(v))

    starts = {}
    trace = {}
    tie_counts = {}

    for u in network.order:
        candidates = []
        anchor = network.anchors.get(u, float("-inf"))
        if math.isfinite(anchor):
            candidates.append({"kind": "anchor", "pred": None, "value": anchor, "rel": None})

        for r in network.incoming.get(u, []):
            candidates.append({
                "kind": "relationship",
                "pred": r.pred_task_id,
                "value": _edge_required_start(r, starts, durations),
                "rel": r,
            })

        if candidates:
            max_value = max(c["value"] for c in candidates)
            active = [c for c in candidates if abs(c["value"] - max_value) <= TRACE_TOL]
            active.sort(key=lambda c: (
                0 if c["kind"] == "relationship" else 1,
                network.nodes[c["pred"]]["activity_id"] if c["pred"] in network.nodes else "",
            ))
            chosen = active[0]
            starts[u] = max_value
            trace[u] = chosen
            tie_counts[u] = len(active)
        else:
            starts[u] = 0.0
            trace[u] = {"kind": "origin", "pred": None, "value": 0.0, "rel": None}
            tie_counts[u] = 1

    finishes = {u: starts[u] + durations[u] for u in network.order}
    return starts, finishes, durations, trace, tie_counts


def _finish_driver(finishes, network):
    max_finish = max(finishes.values())
    tied = [tid for tid, val in finishes.items() if abs(val - max_finish) <= TRACE_TOL]
    tied.sort(key=lambda tid: network.nodes[tid]["activity_id"])
    return tied[0], tied


def _trace_path(network, endpoint_tid, trace):
    path = []
    seen = set()
    cur = endpoint_tid
    while cur in network.nodes and cur not in seen:
        seen.add(cur)
        path.append(cur)
        src = trace.get(cur, {})
        pred = src.get("pred")
        if not pred:
            break
        cur = pred
    path.reverse()
    return path


def _path_text(network, path, max_items=18):
    ids = [network.nodes[tid]["activity_id"] for tid in path]
    if len(ids) <= max_items:
        return " → ".join(ids)
    head = ids[:8]
    tail = ids[-8:]
    return " → ".join(head + [f"… ({len(ids)-16} more) …"] + tail)


def _node_label(network, tid):
    n = network.nodes[tid]
    return f"{n['activity_id']} — {n['name']}"


def _path_switch(network, baseline_path, scenario_path):
    if baseline_path == scenario_path:
        return {
            "changed": False,
            "replacement_tid": None,
            "replacement": "Same controlling path",
            "switch_point": "No path switch",
            "common_suffix_len": len(baseline_path),
        }

    i = 1
    while i <= min(len(baseline_path), len(scenario_path)) and baseline_path[-i] == scenario_path[-i]:
        i += 1
    common_suffix_len = i - 1

    if common_suffix_len == 0:
        replacement_tid = scenario_path[-1] if scenario_path else None
        return {
            "changed": True,
            "replacement_tid": replacement_tid,
            "replacement": _node_label(network, replacement_tid) if replacement_tid else "Unknown",
            "switch_point": "Terminal controlling driver changed",
            "common_suffix_len": 0,
        }

    branch_idx = len(scenario_path) - common_suffix_len - 1
    rejoin_idx = len(scenario_path) - common_suffix_len
    replacement_tid = scenario_path[branch_idx] if branch_idx >= 0 else None
    rejoin_tid = scenario_path[rejoin_idx] if 0 <= rejoin_idx < len(scenario_path) else None

    replacement = _node_label(network, replacement_tid) if replacement_tid else "Fixed/anchor condition"
    if replacement_tid and rejoin_tid:
        switch_point = f"{network.nodes[replacement_tid]['activity_id']} → {network.nodes[rejoin_tid]['activity_id']}"
    elif rejoin_tid:
        switch_point = f"Fixed/anchor → {network.nodes[rejoin_tid]['activity_id']}"
    else:
        switch_point = "Path changed"

    return {
        "changed": True,
        "replacement_tid": replacement_tid,
        "replacement": replacement,
        "switch_point": switch_point,
        "common_suffix_len": common_suffix_len,
    }


def _wbs_area(path: str) -> str:
    parts = [p.strip() for p in str(path or "").split("/") if p.strip()]
    if len(parts) >= 2:
        return parts[1]
    return parts[0] if parts else "Unassigned"


def _location(path: str) -> str:
    parts = [p.strip() for p in str(path or "").split("/") if p.strip()]
    return parts[-1] if parts else "Unassigned"


def _coord_to_date(network, coord_h):
    try:
        return network.calendar.add_work_hours(network.origin_date, float(coord_h))
    except Exception:
        return None


def _threshold_fields(transmission: str, drag: float, duration: float):
    """Return a rigorous threshold representation.

    Partial: the path switch is observed after `drag` hours of maximum one-activity compression.
    Full: no replacement path takes over before the current RD reaches zero, so the threshold
          is not a finite observed value inside the current RD interval.
    Zero: the activity has no current effect on the selected target.
    """
    if transmission == "Partial":
        return drag, "Switch occurs before RD reaches zero"
    if transmission == "Full":
        return math.nan, "No switch within current RD"
    return math.nan, "No target effect"


def compute_drag(network, target_key="__PROJECT_EARLY_FINISH__"):
    base_starts, base_finishes, base_durations, base_trace, base_ties = _schedule_with_trace(network)
    is_project = target_key == "__PROJECT_EARLY_FINISH__"

    if is_project:
        baseline_driver, baseline_finish_ties = _finish_driver(base_finishes, network)
        baseline_target_h = base_finishes[baseline_driver]
        baseline_endpoint = baseline_driver
    else:
        baseline_target_h = base_finishes[target_key]
        baseline_driver = target_key
        baseline_endpoint = target_key
        baseline_finish_ties = [target_key]

    baseline_path = _trace_path(network, baseline_endpoint, base_trace)
    baseline_path_text = _path_text(network, baseline_path)
    baseline_driver_label = _node_label(network, baseline_driver)

    rows = []
    for tid, n in network.nodes.items():
        d = base_durations[tid]

        if d <= EPS:
            drag = 0.0
            scenario_target_h = baseline_target_h
            scenario_driver = baseline_driver
            scenario_path = baseline_path
            scenario_ties = baseline_finish_ties
        else:
            _, f2, _, trace2, _ = _schedule_with_trace(network, {tid: 0.0})
            if is_project:
                scenario_driver, scenario_ties = _finish_driver(f2, network)
                scenario_target_h = f2[scenario_driver]
                scenario_endpoint = scenario_driver
            else:
                scenario_driver = target_key
                scenario_ties = [target_key]
                scenario_target_h = f2[target_key]
                scenario_endpoint = target_key

            scenario_path = _trace_path(network, scenario_endpoint, trace2)
            drag = max(0.0, baseline_target_h - scenario_target_h)

        ratio = drag / d if d > EPS else 0.0
        headroom = max(0.0, d - drag)
        if drag <= EPS:
            transmission = "Zero"
        elif abs(drag - d) <= 1e-6:
            transmission = "Full"
        else:
            transmission = "Partial"

        switch = _path_switch(network, baseline_path, scenario_path)
        if not switch["changed"]:
            path_outcome = "Same Path"
        elif switch["common_suffix_len"] == 0:
            path_outcome = "Terminal Shift"
        else:
            path_outcome = "Replacement Path"

        scenario_driver_label = _node_label(network, scenario_driver)
        threshold_h, threshold_status = _threshold_fields(transmission, drag, d)
        scenario_target_date = _coord_to_date(network, scenario_target_h)

        rows.append({
            "Task ID": tid,
            "Activity ID": n["activity_id"],
            "Activity Name": n["name"],
            "WBS Path": n["wbs_path"],
            "WBS Area": _wbs_area(n["wbs_path"]),
            "Location": _location(n["wbs_path"]),
            "Status": n["status"],
            "Task Type": n["task_type"],
            "Remaining Duration (h)": d,
            "P6 Total Float (h)": n["p6_total_float_h"],
            "P6 Early Start": n["p6_start_dt"],
            "P6 Early Finish": n["p6_finish_dt"],
            "DRAG (h)": drag,
            "DRAG / RD": ratio,
            "DRAG Transmission Ratio": ratio,
            "DRAG Efficiency": ratio,  # backward-compatible alias; UI uses Transmission Ratio
            "Compression Headroom (h)": headroom,
            "Switch Threshold (h)": threshold_h,
            "Switch Threshold Status": threshold_status,
            "Transmission": transmission,
            "DRAG Driver": drag > EPS,
            "Baseline Target Driver": baseline_driver_label,
            "Target Finish if RD=0 (h coord)": scenario_target_h,
            "Scenario Target Finish": scenario_target_date,
            "Scenario Target Driver": scenario_driver_label,
            "Scenario Driver Tie Count": len(scenario_ties),
            "Path Outcome": path_outcome,
            "Path Switch": switch["switch_point"],
            "Path Switch?": "Yes" if switch["changed"] else "No",
            "Replacement Controlling Activity": switch["replacement"],
            "Controlling Path Changed": switch["changed"],
            "Baseline Controlling Path": baseline_path_text,
            "Scenario Controlling Path": _path_text(network, scenario_path),
        })

    df = pd.DataFrame(rows)
    df = df.sort_values(["DRAG (h)", "Remaining Duration (h)"], ascending=[False, False]).reset_index(drop=True)
    df.insert(0, "DRAG Rank", range(1, len(df) + 1))

    positive = df[df["DRAG (h)"] > EPS]
    max_drag = float(positive["DRAG (h)"].max()) if not positive.empty else 0.0
    max_rows = positive[abs(positive["DRAG (h)"] - max_drag) <= 1e-6] if max_drag > EPS else positive.iloc[0:0]

    # Concentration by count, not by summing overlapping DRAG values.
    if positive.empty:
        dominant_wbs = "—"
        dominant_wbs_share = 0.0
        dominant_location = "—"
        dominant_location_share = 0.0
    else:
        wbs_counts = positive["WBS Area"].fillna("Unassigned").value_counts()
        loc_counts = positive["Location"].fillna("Unassigned").value_counts()
        dominant_wbs = str(wbs_counts.index[0])
        dominant_wbs_share = float(wbs_counts.iloc[0] / len(positive))
        dominant_location = str(loc_counts.index[0])
        dominant_location_share = float(loc_counts.iloc[0] / len(positive))

    baseline_driver_node = network.nodes[baseline_driver]
    meta = {
        "target_key": target_key,
        "target_kind": "Project Early Finish" if is_project else "Finish Milestone",
        "baseline_target_h": baseline_target_h,
        "baseline_driver_task_id": baseline_driver,
        "baseline_driver": baseline_driver_label,
        "baseline_target_date": baseline_driver_node["p6_finish_dt"] if is_project else network.nodes[target_key]["p6_finish_dt"],
        "baseline_controlling_path": baseline_path_text,
        "baseline_controlling_path_count": len(baseline_path),
        "baseline_finish_tie_count": len(baseline_finish_ties),
        "activities_with_drag": int((df["DRAG (h)"] > EPS).sum()),
        "max_drag_h": max_drag,
        "max_individual_drag_h": max_drag,
        "max_individual_drag_activity_count": len(max_rows),
        "max_individual_drag_activities": ", ".join(max_rows["Activity ID"].astype(str).tolist()[:12]),
        # Backward-compatible aliases retained for files/scripts built against the first Build 3.
        "compression_frontier_h": max_drag,
        "compression_frontier_activity_count": len(max_rows),
        "compression_frontier_activities": ", ".join(max_rows["Activity ID"].astype(str).tolist()[:12]),
        "path_switch_activities": int(((df["DRAG (h)"] > EPS) & (df["Controlling Path Changed"])).sum()),
        "full_transmission_activities": int(((df["DRAG (h)"] > EPS) & (df["Transmission"] == "Full")).sum()),
        "partial_transmission_activities": int(((df["DRAG (h)"] > EPS) & (df["Transmission"] == "Partial")).sum()),
        "zero_transmission_activities": int((df["Transmission"] == "Zero").sum()),
        "dominant_wbs": dominant_wbs,
        "dominant_wbs_share": dominant_wbs_share,
        "dominant_location": dominant_location,
        "dominant_location_share": dominant_location_share,
    }
    return df, meta


def concentration_tables(results: pd.DataFrame, hours_per_day: float):
    """Non-additive DRAG concentration summaries based on activity counts and maxima."""
    positive = results[results["DRAG (h)"] > EPS].copy()
    if positive.empty:
        empty = pd.DataFrame()
        return empty, empty

    total_positive = len(positive)

    def summarize(group_col):
        g = positive.groupby(group_col, dropna=False)
        out = g.agg(
            Activities_with_DRAG=("Activity ID", "count"),
            Full_Transmission=("Transmission", lambda s: int((s == "Full").sum())),
            Partial_Transmission=("Transmission", lambda s: int((s == "Partial").sum())),
            Path_Switches=("Controlling Path Changed", lambda s: int(s.sum())),
            Max_DRAG_h=("DRAG (h)", "max"),
            Median_DTR=("DRAG Transmission Ratio", "median"),
            Median_Headroom_h=("Compression Headroom (h)", "median"),
        ).reset_index()
        out["Share of DRAG Activities (%)"] = 100.0 * out["Activities_with_DRAG"] / total_positive
        out["Max DRAG (d)"] = out["Max_DRAG_h"] / hours_per_day
        out["Median Headroom (d)"] = out["Median_Headroom_h"] / hours_per_day
        out = out.drop(columns=["Max_DRAG_h", "Median_Headroom_h"])
        return out.sort_values(["Activities_with_DRAG", "Max DRAG (d)"], ascending=[False, False])

    return summarize("WBS Area"), summarize("Location")
