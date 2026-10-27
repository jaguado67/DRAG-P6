from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, time
import json
import math
from typing import Dict, List

import pandas as pd

from .calendar import P6Calendar


SPIDER_DATE_FORMATS = (
    "%m/%d/%y  %H:%M:%S",
    "%m/%d/%y %H:%M:%S",
    "%m/%d/%Y  %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
)


def parse_spider_datetime(value):
    if not value:
        return None
    text = str(value).strip()
    for fmt in SPIDER_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        result = float(value)
        if math.isnan(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def parse_spider_json_bytes(raw: bytes) -> dict:
    last = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return json.loads(raw.decode(enc))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            last = exc
    raise ValueError(f"Unable to decode/parse Spider Project JSON: {last}")


def _spider_calendar(data: dict) -> P6Calendar:
    calendars = data.get("calendars") or []
    if not calendars:
        raise ValueError("Spider JSON does not contain a calendar definition.")
    row = calendars[0]
    cal_id = str(row.get("Code", "1"))
    week_code = str(row.get("WeekCode", ""))

    weekly = {i: [] for i in range(7)}
    for d in data.get("days") or []:
        if week_code and str(d.get("WeekCode", "")) != week_code:
            continue
        try:
            spider_day = int(d.get("DayNumber"))
        except (TypeError, ValueError):
            continue
        # Spider: 1=Sunday, 2=Monday, ..., 7=Saturday.
        py_day = (spider_day + 5) % 7
        try:
            sh, sm = map(int, str(d.get("Start", "0:00")).split(":"))
            fh, fm = map(int, str(d.get("Fin", "0:00")).split(":"))
            weekly[py_day].append((time(sh, sm), time(fh, fm)))
        except Exception:
            continue

    day_hours = _float(row.get("MeanWorkDay"), 8.0)
    return P6Calendar(
        calendar_id=cal_id,
        name=str(row.get("Name", "Spider Calendar")),
        day_hours=day_hours,
        weekly=weekly,
        exceptions={},
    )


def _wbs_area_map(data: dict) -> Dict[str, str]:
    group_name = {str(x.get("Code", "")): str(x.get("Name", "")) for x in data.get("wbsCont") or []}
    out = {}
    for row in data.get("wbsObjects") or []:
        out[str(row.get("ObjCode", ""))] = group_name.get(str(row.get("ParentCode", "")), str(row.get("ParentCode", "")))
    return out


def _normalize_type(text: str) -> str:
    return {
        "Finish-Start": "FS",
        "Start-Start": "SS",
        "Finish-Finish": "FF",
        "Start-Finish": "SF",
        "FS": "FS", "SS": "SS", "FF": "FF", "SF": "SF",
    }.get(str(text or "").strip(), str(text or "").strip())


@dataclass(frozen=True)
class SpiderLink:
    pred: str
    succ: str
    rel_type: str
    lag_type: str
    lag_value: float
    lag_unit: str
    calendar_id: str
    uid: str

    def lag_hours(self, durations: Dict[str, float], nodes: Dict[str, dict], day_hours: float) -> float:
        if self.lag_type.lower() == "time":
            unit = self.lag_unit.lower()
            if unit.startswith("day"):
                return self.lag_value * day_hours
            if unit.startswith("minute"):
                return self.lag_value / 60.0
            return self.lag_value

        # Spider quantity/volume links move with production. For SS/FS the lag is measured
        # on the predecessor. For FF/SF it is measured on the successor side. This convention
        # reproduces the 1 km benchmark baseline to sub-second precision.
        if "%" in self.lag_unit:
            fraction = self.lag_value / 100.0
        elif "volume" in self.lag_unit.lower():
            basis_code = self.pred if self.rel_type in ("SS", "FS") else self.succ
            volume = float(nodes[basis_code].get("volume", 0.0) or 0.0)
            fraction = self.lag_value / volume if volume > 0 else 0.0
        else:
            fraction = 0.0

        basis_code = self.pred if self.rel_type in ("SS", "FS") else self.succ
        return max(0.0, durations.get(basis_code, 0.0)) * fraction

    def required_start(self, starts, durations, nodes, day_hours):
        p, s = self.pred, self.succ
        lag = self.lag_hours(durations, nodes, day_hours)
        dp, ds = durations[p], durations[s]
        if self.rel_type == "FS":
            return starts[p] + dp + lag
        if self.rel_type == "SS":
            return starts[p] + lag
        if self.rel_type == "FF":
            return starts[p] + dp + lag - ds
        if self.rel_type == "SF":
            return starts[p] + lag - ds
        raise ValueError(f"Unsupported Spider relationship type: {self.rel_type}")


@dataclass(frozen=True)
class SpiderResourceEdge:
    pred: str
    succ: str
    resources: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass
class SpiderNetwork:
    project_name: str
    project_code: str
    calendar: P6Calendar
    origin_date: datetime
    nodes: Dict[str, dict]
    links: List[SpiderLink]
    resource_edges: List[SpiderResourceEdge]
    incoming: dict
    outgoing: dict
    incoming_resource: dict
    outgoing_resource: dict
    order: list
    baseline_durations: Dict[str, float]
    target_code: str
    reconciliation: dict


def _topological(nodes, links, resource_edges=None):
    resource_edges = resource_edges or []
    indegree = {n: 0 for n in nodes}
    outgoing = defaultdict(list)
    for r in links:
        if r.pred in indegree and r.succ in indegree:
            indegree[r.succ] += 1
            outgoing[r.pred].append(r.succ)
    for r in resource_edges:
        if r.pred in indegree and r.succ in indegree:
            indegree[r.succ] += 1
            outgoing[r.pred].append(r.succ)
    q = deque([n for n, d in indegree.items() if d == 0])
    order = []
    while q:
        u = q.popleft()
        order.append(u)
        for v in outgoing[u]:
            indegree[v] -= 1
            if indegree[v] == 0:
                q.append(v)
    if len(order) != len(indegree):
        raise ValueError("Spider JSON network contains a cycle in logic/resource order constraints.")
    return order


def _infer_resource_edges(data: dict, calendar: P6Calendar, origin: datetime, tolerance_h: float = 0.002):
    """Infer the resource-order constraints exposed by the scheduled Spider plan.

    Spider's f_DRAGH for a resource-constrained schedule is not a logic-only Early-Date metric.
    The exported Start/Fin dates encode the levelled plan.  We therefore reconstruct the
    resource sequencing that is observable in that plan:

    * capacity-one / pair-conflicting resources create an ordered resource chain;
    * for multi-capacity resources, an activity that starts exactly when a blocking assignment
      releases capacity receives a release edge from that predecessor.

    This is deliberately called a *frozen resource-order* reconstruction. It is sufficient to
    reproduce the positive DRAG values in the supplied 1 km benchmark, but it is not yet a full
    re-levelling optimizer after every duration perturbation.
    """
    capacities = {}
    for r in data.get("resources") or []:
        capacities[str(r.get("Code", ""))] = max(1e-9, _float(r.get("Number"), 1.0))

    by_resource = defaultdict(list)
    for a in data.get("assigns") or []:
        if not a.get("Start") or not a.get("Fin"):
            continue  # rows without scheduled dates are alternatives/unselected pool members
        op = str(a.get("OperCode", ""))
        res = str(a.get("ResCode", ""))
        if not op or not res:
            continue
        st = parse_spider_datetime(a.get("Start"))
        fn = parse_spider_datetime(a.get("Fin"))
        if not st or not fn:
            continue
        q = max(0.0, _float(a.get("Number"), 1.0))
        if q <= 0:
            q = 1.0
        by_resource[res].append({
            "op": op,
            "start": calendar.work_hours_between(origin, st),
            "finish": calendar.work_hours_between(origin, fn),
            "qty": q,
        })

    raw = {}
    for res, rows in by_resource.items():
        cap = capacities.get(res, 1.0)
        # One row per activity/resource is enough for sequencing.
        dedup = {}
        for x in rows:
            dedup[x["op"]] = x
        rows = sorted(dedup.values(), key=lambda x: (x["start"], x["finish"], x["op"]))

        # Pair conflicts: if two assignments cannot coexist, preserve their observed order.
        for j, b in enumerate(rows):
            candidates = [
                a for a in rows[:j]
                if a["finish"] <= b["start"] + tolerance_h
                and a["qty"] + b["qty"] > cap + tolerance_h
            ]
            if candidates:
                a = max(candidates, key=lambda x: (x["finish"], x["start"], x["op"]))
                raw.setdefault((a["op"], b["op"]), []).append((res, "pair-conflict"))

        # Multi-capacity release: just before B starts, if capacity is saturated and an
        # assignment ending at B.start releases the required capacity, preserve that order.
        for b in rows:
            t = b["start"]
            active_before = [
                a for a in rows
                if a["op"] != b["op"]
                and a["start"] < t - tolerance_h
                and a["finish"] >= t - tolerance_h
            ]
            usage = sum(a["qty"] for a in active_before)
            if usage + b["qty"] > cap + tolerance_h:
                ending = [a for a in active_before if abs(a["finish"] - t) <= tolerance_h]
                for a in ending:
                    raw.setdefault((a["op"], b["op"]), []).append((res, "capacity-release"))

    edges = []
    for (pred, succ), evidence in sorted(raw.items()):
        resources = tuple(sorted({r for r, _ in evidence}))
        reasons = tuple(sorted({why for _, why in evidence}))
        if pred != succ:
            edges.append(SpiderResourceEdge(pred, succ, resources, reasons))
    return edges


def schedule_spider(network: SpiderNetwork, durations_override=None, include_resources: bool = True):
    durations = dict(network.baseline_durations)
    if durations_override:
        for k, v in durations_override.items():
            if k in durations:
                durations[k] = max(0.0, float(v))

    starts = {}
    for u in network.order:
        candidates = [0.0]
        for r in network.incoming.get(u, []):
            candidates.append(r.required_start(starts, durations, network.nodes, network.calendar.day_hours))
        if include_resources:
            for r in network.incoming_resource.get(u, []):
                candidates.append(starts[r.pred] + durations[r.pred])
        starts[u] = max(candidates)
    finishes = {u: starts[u] + durations[u] for u in network.order}
    return starts, finishes, durations


def build_spider_network(data: dict, tolerance_h: float = 0.05) -> SpiderNetwork:
    acts = data.get("activities") or []
    if not acts:
        raise ValueError("Spider JSON does not contain activities.")
    calendar = _spider_calendar(data)
    wbs_area = _wbs_area_map(data)

    # Resource-constrained Start dates are the primary baseline for Spider f_DRAGH.
    dates = [parse_spider_datetime(a.get("Start")) for a in acts]
    dates = [x for x in dates if x]
    if not dates:
        dates = [parse_spider_datetime(a.get("EarlyStart")) for a in acts]
        dates = [x for x in dates if x]
    if not dates:
        raise ValueError("Spider JSON does not contain usable activity dates.")
    origin = min(dates)

    nodes = {}
    for a in acts:
        code = str(a.get("Code", ""))
        if not code:
            continue
        est = parse_spider_datetime(a.get("EarlyStart"))
        efn = parse_spider_datetime(a.get("EarlyFin"))
        pst = parse_spider_datetime(a.get("Start"))
        pfn = parse_spider_datetime(a.get("Fin"))
        nodes[code] = {
            "activity_id": code,
            "name": str(a.get("Name", "")),
            "duration_h": max(0.0, _float(a.get("DurPlan"), _float(a.get("TeamDur"), 0.0))),
            "duration_d": _float(a.get("DurPlanD"), 0.0),
            "volume": _float(a.get("VolPlan"), 0.0),
            "unit": str(a.get("Unit", "")),
            "dph": str(a.get("DPH", "")),
            "calendar_id": str(a.get("Calen", "")),
            "critical": str(a.get("f_Critical", "")) == "1",
            "spider_drag_h": _float(a.get("f_DRAGH"), None),
            "spider_drag_d": _float(a.get("f_DRAGD"), None),
            "reserve_h": _float(a.get("ReservFinH"), _float(a.get("Reserv"), None)),
            "crit_index": _float(a.get("f_CritIndex"), None),
            "early_start_dt": est,
            "early_finish_dt": efn,
            "plan_start_dt": pst,
            "plan_finish_dt": pfn,
            "wbs_area": wbs_area.get(code, "Unassigned"),
        }

    links = []
    for x in data.get("links") or []:
        if str(x.get("f_UseInSched", "Yes")) != "Yes":
            continue
        if str(x.get("f_BrokenLink", "No")) == "Yes" or str(x.get("f_BrokenLink2", "No")) == "Yes":
            continue
        p, s = str(x.get("PredCode", "")), str(x.get("SuccCode", ""))
        if p not in nodes or s not in nodes:
            continue
        links.append(SpiderLink(
            pred=p,
            succ=s,
            rel_type=_normalize_type(x.get("TypeSF")),
            lag_type=str(x.get("LagType", "Time")),
            lag_value=_float(x.get("Lag"), 0.0),
            lag_unit=str(x.get("LagUnit", "Hour")),
            calendar_id=str(x.get("Calen", "")),
            uid=str(x.get("f_UniId", "")),
        ))

    resource_edges = _infer_resource_edges(data, calendar, origin)
    order = _topological(nodes, links, resource_edges)
    incoming, outgoing = defaultdict(list), defaultdict(list)
    for r in links:
        incoming[r.succ].append(r)
        outgoing[r.pred].append(r)
    incoming_resource, outgoing_resource = defaultdict(list), defaultdict(list)
    for r in resource_edges:
        incoming_resource[r.succ].append(r)
        outgoing_resource[r.pred].append(r)

    milestones = [c for c, n in nodes.items() if n["dph"].lower() == "milestone"]
    target = next((c for c in milestones if nodes[c]["name"].strip().lower() == "finish"), None)
    if target is None:
        target = milestones[0] if milestones else order[-1]

    project = data.get("project") or {}
    net = SpiderNetwork(
        project_name=str(project.get("Name", "Spider Project")),
        project_code=str(project.get("Code", "")),
        calendar=calendar,
        origin_date=origin,
        nodes=nodes,
        links=links,
        resource_edges=resource_edges,
        incoming=incoming,
        outgoing=outgoing,
        incoming_resource=incoming_resource,
        outgoing_resource=outgoing_resource,
        order=order,
        baseline_durations={c: n["duration_h"] for c, n in nodes.items()},
        target_code=target,
        reconciliation={},
    )

    # Primary: resource-constrained Start/Fin schedule used by Spider f_DRAGH.
    calc_s, calc_f, _ = schedule_spider(net, include_resources=True)
    start_errs, finish_errs = {}, {}
    for c, n in nodes.items():
        if n["plan_start_dt"]:
            ref = calendar.work_hours_between(origin, n["plan_start_dt"])
            start_errs[c] = calc_s[c] - ref
        if n["plan_finish_dt"]:
            ref = calendar.work_hours_between(origin, n["plan_finish_dt"])
            finish_errs[c] = calc_f[c] - ref

    target_ref_h = None
    target_dt = nodes[target]["plan_finish_dt"] or nodes[target]["plan_start_dt"]
    if target_dt:
        target_ref_h = calendar.work_hours_between(origin, target_dt)
    target_err = calc_f[target] - target_ref_h if target_ref_h is not None else math.nan

    max_start = max((abs(x) for x in start_errs.values()), default=0.0)
    max_finish = max((abs(x) for x in finish_errs.values()), default=0.0)
    mae_start = sum(abs(x) for x in start_errs.values()) / max(1, len(start_errs))
    mae_finish = sum(abs(x) for x in finish_errs.values()) / max(1, len(finish_errs))
    gate_ok = max_start <= tolerance_h and max_finish <= tolerance_h and (math.isnan(target_err) or abs(target_err) <= tolerance_h)
    status = "PASS" if gate_ok else "FAIL"

    # Secondary diagnostic: logic-only Early schedule, useful to quantify resource displacement.
    early_s, early_f, _ = schedule_spider(net, include_resources=False)
    early_target_ref = None
    if nodes[target]["early_finish_dt"]:
        early_target_ref = calendar.work_hours_between(origin, nodes[target]["early_finish_dt"])
    early_target_err = early_f[target] - early_target_ref if early_target_ref is not None else math.nan

    net.reconciliation = {
        "status": status,
        "tolerance_h": tolerance_h,
        "activities": len(nodes),
        "logic_links": len(links),
        "resource_order_edges": len(resource_edges),
        "volume_links": sum(1 for r in links if r.lag_type.lower() != "time"),
        "time_links": sum(1 for r in links if r.lag_type.lower() == "time"),
        "max_plan_start_error_h": max_start,
        "max_plan_finish_error_h": max_finish,
        "mae_plan_start_h": mae_start,
        "mae_plan_finish_h": mae_finish,
        "target_error_h": target_err,
        "calculated_target_h": calc_f[target],
        "exported_target_h": target_ref_h,
        "logic_only_early_target_error_h": early_target_err,
        "baseline_mode": "Resource-constrained Start/Fin + inferred frozen resource order",
    }
    return net


def links_dataframe(network: SpiderNetwork) -> pd.DataFrame:
    rows = []
    for r in network.links:
        rows.append({
            "Constraint Kind": "Logic",
            "Pred": r.pred, "Succ": r.succ, "Type": r.rel_type,
            "Lag Type": r.lag_type, "Lag": r.lag_value, "Lag Unit": r.lag_unit,
            "Baseline Lag (h)": r.lag_hours(network.baseline_durations, network.nodes, network.calendar.day_hours),
            "Resource Evidence": "",
        })
    for r in network.resource_edges:
        rows.append({
            "Constraint Kind": "Resource order",
            "Pred": r.pred, "Succ": r.succ, "Type": "RESOURCE-FS",
            "Lag Type": "Resource", "Lag": 0.0, "Lag Unit": "Hour",
            "Baseline Lag (h)": 0.0,
            "Resource Evidence": ", ".join(r.resources) + " · " + ", ".join(r.reasons),
        })
    return pd.DataFrame(rows)
