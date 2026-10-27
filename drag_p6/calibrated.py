from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import math
from typing import Dict, List, Optional

import pandas as pd

from .calendar import P6Calendar, parse_p6_datetime
from .models import Relationship
from .xer import normalize_rel_type, to_float


EPS = 1e-9


@dataclass
class CalibratedNetwork:
    proj_id: str
    project_name: str
    calendar: P6Calendar
    origin_date: object
    nodes: Dict[str, dict]
    dynamic_relationships: List[Relationship]
    fixed_relationships: pd.DataFrame
    external_relationships: pd.DataFrame
    incoming: dict
    outgoing: dict
    order: list
    anchors: Dict[str, float]
    baseline_starts: Dict[str, float]
    baseline_finishes: Dict[str, float]
    baseline_durations: Dict[str, float]
    reconciliation: dict
    project_row: dict
    schedoptions_row: dict


def _scheduled_start(row):
    for col in ("early_start_date", "restart_date", "early_end_date", "reend_date"):
        dt = parse_p6_datetime(row.get(col, ""))
        if dt:
            return dt
    return None


def _scheduled_finish(row):
    for col in ("early_end_date", "reend_date", "early_start_date", "restart_date"):
        dt = parse_p6_datetime(row.get(col, ""))
        if dt:
            return dt
    return None


def _wbs_paths(wbs_df: pd.DataFrame):
    if wbs_df.empty:
        return {}
    rows = {str(r.get("wbs_id", "")): r for _, r in wbs_df.iterrows()}
    cache = {}

    def path(wid):
        wid = str(wid or "")
        if wid in cache:
            return cache[wid]
        parts = []
        seen = set()
        cur = wid
        while cur and cur in rows and cur not in seen:
            seen.add(cur)
            r = rows[cur]
            name = str(r.get("wbs_name", "") or r.get("wbs_short_name", "") or "")
            if name:
                parts.append(name)
            cur = str(r.get("parent_wbs_id", "") or "")
        result = " / ".join(reversed(parts))
        cache[wid] = result
        return result

    return {wid: path(wid) for wid in rows}


def _edge_required_start(r: Relationship, starts, durations):
    p = r.pred_task_id
    s = r.succ_task_id
    if r.rel_type == "FS":
        return starts[p] + durations[p] + r.lag_h
    if r.rel_type == "SS":
        return starts[p] + r.lag_h
    if r.rel_type == "FF":
        return starts[p] + durations[p] + r.lag_h - durations[s]
    if r.rel_type == "SF":
        return starts[p] + r.lag_h - durations[s]
    raise ValueError(f"Unsupported relationship type: {r.rel_type}")


def _topological_order(node_ids, relationships):
    indegree = {n: 0 for n in node_ids}
    outgoing = defaultdict(list)
    for r in relationships:
        if r.pred_task_id in indegree and r.succ_task_id in indegree:
            indegree[r.succ_task_id] += 1
            outgoing[r.pred_task_id].append(r)
    q = deque([n for n, d in indegree.items() if d == 0])
    order = []
    while q:
        u = q.popleft()
        order.append(u)
        for r in outgoing[u]:
            v = r.succ_task_id
            indegree[v] -= 1
            if indegree[v] == 0:
                q.append(v)
    if len(order) != len(indegree):
        raise ValueError("The calibrated remaining network contains a logic cycle.")
    return order


def schedule(network: CalibratedNetwork, durations_override=None):
    durations = dict(network.baseline_durations)
    if durations_override:
        for k, v in durations_override.items():
            if k in durations:
                durations[k] = max(0.0, float(v))

    starts = {}
    for u in network.order:
        candidates = []
        anchor = network.anchors.get(u, float("-inf"))
        if math.isfinite(anchor):
            candidates.append(anchor)
        for r in network.incoming.get(u, []):
            candidates.append(_edge_required_start(r, starts, durations))
        starts[u] = max(candidates) if candidates else 0.0
    finishes = {u: starts[u] + durations[u] for u in network.order}
    return starts, finishes, durations


def build_calibrated_network(tables: dict, proj_id: str, tolerance_h: float = 0.05):
    task = tables.get("TASK", pd.DataFrame()).copy()
    project = tables.get("PROJECT", pd.DataFrame()).copy()
    sched = tables.get("SCHEDOPTIONS", pd.DataFrame()).copy()
    pred = tables.get("TASKPRED", pd.DataFrame()).copy()
    wbs = tables.get("PROJWBS", pd.DataFrame()).copy()
    calendars = tables.get("CALENDAR", pd.DataFrame()).copy()

    task = task[task["proj_id"].astype(str) == str(proj_id)].copy()
    if task.empty:
        raise ValueError("No activities found for the selected project.")

    prow = project[project["proj_id"].astype(str) == str(proj_id)]
    if prow.empty:
        raise ValueError("PROJECT record not found for selected project.")
    project_row = prow.iloc[0].to_dict()
    project_name = str(project_row.get("proj_short_name", proj_id))

    srow = sched[sched["proj_id"].astype(str) == str(proj_id)] if not sched.empty and "proj_id" in sched.columns else pd.DataFrame()
    schedoptions_row = srow.iloc[0].to_dict() if not srow.empty else {}

    incomplete_task = task[task["status_code"].astype(str) != "TK_Complete"].copy()
    used_calendars = sorted({str(x) for x in incomplete_task.get("clndr_id", pd.Series(dtype=str)).tolist() if str(x)})
    if len(used_calendars) != 1:
        raise ValueError(
            f"P6-calibrated v1.0.0.0 requires one activity calendar in the remaining network; found {len(used_calendars)}."
        )
    calendar_id = used_calendars[0]
    crow = calendars[calendars["clndr_id"].astype(str) == calendar_id]
    if crow.empty:
        raise ValueError(f"Calendar {calendar_id} was not found in CALENDAR table.")
    calendar = P6Calendar.from_row(crow.iloc[0].to_dict())

    origin_date = parse_p6_datetime(project_row.get("plan_start_date", ""))
    if origin_date is None:
        dates = [_scheduled_start(r) for _, r in task.iterrows()]
        dates = [d for d in dates if d]
        if not dates:
            raise ValueError("No usable project origin or early dates found.")
        origin_date = min(dates)

    wbsp = _wbs_paths(wbs[wbs["proj_id"].astype(str) == str(proj_id)].copy() if not wbs.empty and "proj_id" in wbs.columns else wbs)

    nodes = {}
    all_task_ids = set(task["task_id"].astype(str))
    for _, row in task.iterrows():
        tid = str(row.get("task_id", ""))
        sdt = _scheduled_start(row)
        fdt = _scheduled_finish(row)
        if sdt is None or fdt is None:
            continue
        status = str(row.get("status_code", ""))
        duration = max(0.0, to_float(row.get("remain_drtn_hr_cnt"), 0.0))
        nodes[tid] = {
            "task_id": tid,
            "activity_id": str(row.get("task_code", tid)),
            "name": str(row.get("task_name", "")),
            "status": status,
            "task_type": str(row.get("task_type", "")),
            "calendar_id": str(row.get("clndr_id", "")),
            "wbs_id": str(row.get("wbs_id", "")),
            "wbs_path": wbsp.get(str(row.get("wbs_id", "")), ""),
            "p6_total_float_h": to_float(row.get("total_float_hr_cnt"), None),
            "constraint_type": str(row.get("cstr_type", "") or ""),
            "constraint_date": str(row.get("cstr_date", "") or ""),
            "actual_start": str(row.get("act_start_date", "") or ""),
            "actual_finish": str(row.get("act_end_date", "") or ""),
            "p6_start_dt": sdt,
            "p6_finish_dt": fdt,
            "p6_start_h": calendar.work_hours_between(origin_date, sdt),
            "p6_finish_h": calendar.work_hours_between(origin_date, fdt),
            "duration_h": duration,
        }

    incomplete = {k: v for k, v in nodes.items() if v["status"] != "TK_Complete"}
    if len(incomplete) != len(incomplete_task):
        raise ValueError("One or more incomplete activities do not contain usable P6 early dates.")

    dynamic = []
    fixed_rows = []
    external_rows = []

    for _, row in pred.iterrows():
        succ_proj = str(row.get("proj_id", "") or "")
        pred_proj = str(row.get("pred_proj_id", "") or "")
        p = str(row.get("pred_task_id", "") or "")
        s = str(row.get("task_id", "") or "")
        typ = normalize_rel_type(str(row.get("pred_type", "") or ""))
        lag = to_float(row.get("lag_hr_cnt"), 0.0)

        touches_selected = succ_proj == str(proj_id) or pred_proj == str(proj_id)
        internal = succ_proj == str(proj_id) and pred_proj == str(proj_id) and p in all_task_ids and s in all_task_ids
        if touches_selected and not internal:
            external_rows.append({
                "Pred Task ID": p, "Succ Task ID": s, "Type": typ, "Lag (h)": lag,
                "Pred Project": pred_proj, "Succ Project": succ_proj,
                "Direction": "Incoming" if succ_proj == str(proj_id) else "Outgoing",
            })
            continue
        if not internal or p not in nodes or s not in nodes:
            continue

        pn = nodes[p]
        sn = nodes[s]
        reason = None
        if sn["status"] == "TK_Complete":
            reason = "successor completed / historical"
        elif pn["status"] == "TK_Complete":
            reason = "predecessor completed / fixed historical event"
        elif pn["status"] == "TK_Active" and typ in ("SS", "SF"):
            reason = "active predecessor start event already historical"

        rel = Relationship(p, s, typ, lag, pred_proj, succ_proj)
        if reason is None:
            starts = {p: pn["p6_start_h"], s: sn["p6_start_h"]}
            durations = {p: pn["duration_h"], s: sn["duration_h"]}
            required = _edge_required_start(rel, starts, durations)
            if sn["p6_start_h"] + tolerance_h < required:
                reason = "not active in P6 baseline / out-of-sequence or status logic"

        if reason is None and p in incomplete and s in incomplete:
            dynamic.append(rel)
        else:
            fixed_rows.append({
                "Pred Activity ID": pn["activity_id"],
                "Succ Activity ID": sn["activity_id"],
                "Type": typ,
                "Lag (h)": lag,
                "Classification": reason or "historical/fixed",
            })

    node_ids = set(incomplete)
    order = _topological_order(node_ids, dynamic)
    incoming = defaultdict(list)
    outgoing = defaultdict(list)
    for r in dynamic:
        incoming[r.succ_task_id].append(r)
        outgoing[r.pred_task_id].append(r)

    baseline_starts = {k: v["p6_start_h"] for k, v in incomplete.items()}
    baseline_finishes = {k: v["p6_finish_h"] for k, v in incomplete.items()}
    baseline_durations = {k: v["duration_h"] for k, v in incomplete.items()}

    anchors = {}
    anchor_reason = {}
    for s in node_ids:
        reqs = [_edge_required_start(r, baseline_starts, baseline_durations) for r in incoming.get(s, [])]
        max_req = max(reqs) if reqs else float("-inf")
        if not reqs:
            anchors[s] = baseline_starts[s]
            anchor_reason[s] = "root / fixed baseline condition"
        elif baseline_starts[s] - max_req > tolerance_h:
            anchors[s] = baseline_starts[s]
            anchor_reason[s] = "constraint, external, status, calendar, or non-driving fixed condition"
        else:
            anchors[s] = float("-inf")
            anchor_reason[s] = "internally logic-driven"

    net = CalibratedNetwork(
        proj_id=str(proj_id), project_name=project_name, calendar=calendar,
        origin_date=origin_date, nodes=incomplete, dynamic_relationships=dynamic,
        fixed_relationships=pd.DataFrame(fixed_rows),
        external_relationships=pd.DataFrame(external_rows), incoming=incoming, outgoing=outgoing,
        order=order, anchors=anchors, baseline_starts=baseline_starts,
        baseline_finishes=baseline_finishes, baseline_durations=baseline_durations,
        reconciliation={}, project_row=project_row, schedoptions_row=schedoptions_row,
    )

    calc_starts, calc_finishes, _ = schedule(net)
    start_res = {k: calc_starts[k] - baseline_starts[k] for k in node_ids}
    finish_res = {k: calc_finishes[k] - baseline_finishes[k] for k in node_ids}
    max_start = max((abs(v) for v in start_res.values()), default=0.0)
    max_finish = max((abs(v) for v in finish_res.values()), default=0.0)
    mae_start = sum(abs(v) for v in start_res.values()) / max(1, len(start_res))
    mae_finish = sum(abs(v) for v in finish_res.values()) / max(1, len(finish_res))
    net.reconciliation = {
        "reconciled": max(max_start, max_finish) <= tolerance_h,
        "tolerance_h": tolerance_h,
        "max_start_error_h": max_start,
        "max_finish_error_h": max_finish,
        "mae_start_h": mae_start,
        "mae_finish_h": mae_finish,
        "activities_checked": len(node_ids),
        "dynamic_relationships": len(dynamic),
        "fixed_historical_relationships": len(fixed_rows),
        "anchors": sum(1 for v in anchors.values() if math.isfinite(v)),
        "external_relationships": len(external_rows),
        "anchor_reason": anchor_reason,
    }
    return net
