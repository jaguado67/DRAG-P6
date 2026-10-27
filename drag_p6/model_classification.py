from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd


def _project_rows(df: pd.DataFrame | None, proj_id: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    if "proj_id" not in df.columns:
        return df.copy()
    return df[df["proj_id"].astype(str) == str(proj_id)].copy()


def _nonempty(v: Any) -> bool:
    if v is None:
        return False
    s = str(v).strip()
    return s not in ("", "None", "nan", "NaN")


def _count_constraints(task: pd.DataFrame) -> int:
    if task.empty:
        return 0
    status = task["status_code"].astype(str) if "status_code" in task.columns else pd.Series("", index=task.index)
    incomplete = task[status != "TK_Complete"].copy()
    count = 0
    for col in ("cstr_type", "cstr_type2"):
        if col in incomplete.columns:
            vals = incomplete[col].fillna("").astype(str).str.strip()
            count += int((~vals.isin(["", "None", "nan", "NaN"])).sum())
    return count


def _duration_type_summary(task: pd.DataFrame) -> tuple[str, dict[str, int]]:
    if task.empty or "duration_type" not in task.columns:
        return "Unknown", {}
    status = task["status_code"].astype(str) if "status_code" in task.columns else pd.Series("", index=task.index)
    incomplete = task[status != "TK_Complete"].copy()
    values = [str(x).strip() for x in incomplete["duration_type"].fillna("") if str(x).strip()]
    counts = dict(Counter(values))
    if not counts:
        return "Unknown", counts
    if len(counts) == 1 and "DT_FixedDrtn" in counts:
        return "P6 Remaining Duration · Fixed Duration dominant", counts
    if "DT_FixedDrtn" in counts and counts["DT_FixedDrtn"] / max(1, sum(counts.values())) >= 0.8:
        return "P6 Remaining Duration · Fixed Duration dominant", counts
    return "Mixed P6 duration types", counts


def classify_p6_model(tables: dict[str, pd.DataFrame], proj_id: str, network=None) -> dict:
    task = _project_rows(tables.get("TASK"), proj_id)
    pred = tables.get("TASKPRED", pd.DataFrame()).copy()
    taskrsrc = _project_rows(tables.get("TASKRSRC"), proj_id)
    rsrc = tables.get("RSRC", pd.DataFrame()).copy()
    sched = _project_rows(tables.get("SCHEDOPTIONS"), proj_id)
    cal = tables.get("CALENDAR", pd.DataFrame()).copy()

    task_ids = set(task["task_id"].astype(str)) if not task.empty and "task_id" in task.columns else set()
    if not pred.empty:
        if "proj_id" in pred.columns:
            pred = pred[pred["proj_id"].astype(str) == str(proj_id)].copy()
        if task_ids and "task_id" in pred.columns and "pred_task_id" in pred.columns:
            pred = pred[
                pred["task_id"].astype(str).isin(task_ids)
                & pred["pred_task_id"].astype(str).isin(task_ids)
            ].copy()

    duration_basis, duration_counts = _duration_type_summary(task)

    calendar_ids = set()
    if not task.empty and "clndr_id" in task.columns:
        calendar_ids = {str(x) for x in task["clndr_id"].fillna("") if str(x).strip()}
    if not calendar_ids and network is not None:
        cid = getattr(network.calendar, "calendar_id", "")
        if cid:
            calendar_ids.add(str(cid))

    assignments = taskrsrc.copy()
    if not assignments.empty and "rsrc_id" in assignments.columns:
        assignments = assignments[assignments["rsrc_id"].fillna("").astype(str).str.strip() != ""].copy()
    resource_assignment_count = len(assignments)
    resource_activity_count = int(assignments["task_id"].astype(str).nunique()) if resource_assignment_count and "task_id" in assignments.columns else 0
    assigned_resource_ids = set(assignments["rsrc_id"].astype(str)) if resource_assignment_count and "rsrc_id" in assignments.columns else set()
    resource_record_count = len(assigned_resource_ids)

    resource_names = []
    if assigned_resource_ids and not rsrc.empty and "rsrc_id" in rsrc.columns:
        rsub = rsrc[rsrc["rsrc_id"].astype(str).isin(assigned_resource_ids)]
        for _, row in rsub.iterrows():
            nm = str(row.get("rsrc_name", "") or row.get("rsrc_short_name", "") or row.get("rsrc_id", ""))
            if nm:
                resource_names.append(nm)

    level_settings = {}
    if not sched.empty:
        srow = sched.iloc[0].to_dict()
        for k, v in srow.items():
            if str(k).lower().startswith("level_") and _nonempty(v):
                level_settings[str(k)] = str(v)

    resource_level_flags = 0
    if assigned_resource_ids and not rsrc.empty and "level_flag" in rsrc.columns:
        rsub = rsrc[rsrc["rsrc_id"].astype(str).isin(assigned_resource_ids)]
        resource_level_flags = int((rsub["level_flag"].fillna("").astype(str).str.upper() == "Y").sum())

    if resource_assignment_count == 0:
        resource_status = "NOT PRESENT"
        leveling_status = "NOT APPLICABLE"
        recommended_mode = "LOGIC DRAG"
        confidence = "HIGH"
    elif level_settings or resource_level_flags:
        resource_status = "PRESENT"
        leveling_status = "POSSIBLE / CONFIGURED"
        recommended_mode = "RESOURCE-CONSTRAINED DRAG REQUIRED"
        confidence = "MEDIUM"
    else:
        resource_status = "PRESENT"
        leveling_status = "UNCONFIRMED"
        recommended_mode = "ASK BEFORE RUNNING"
        confidence = "MEDIUM"

    # Standard P6 resource quantities are not treated as physical production quantities.
    productivity_status = "NOT DETECTED AS PHYSICAL PRODUCTIVITY MODEL"
    if resource_assignment_count:
        productivity_status = "RESOURCE UNIT RATES PRESENT · PHYSICAL PRODUCTIVITY UNCONFIRMED"

    project_name = ""
    project = _project_rows(tables.get("PROJECT"), proj_id)
    if not project.empty:
        project_name = str(project.iloc[0].get("proj_short_name", "") or project.iloc[0].get("proj_id", ""))

    notes = []
    if resource_assignment_count and not level_settings and not resource_level_flags:
        notes.append("Resource assignments exist, but the XER does not prove that the last schedule was resource-levelled.")
    if resource_names and len(resource_names) <= 5:
        notes.append("Assigned resources detected: " + ", ".join(sorted(set(resource_names))))
    notes.append("Standard P6 TASKRSRC unit rates are not automatically interpreted as construction quantity/productivity.")

    return {
        "source": "Primavera P6 XER",
        "project": project_name,
        "activity_count": len(task),
        "logic_relationships": len(pred),
        "calendar_count": len(calendar_ids),
        "constraint_count": _count_constraints(task),
        "duration_basis_detected": duration_basis,
        "duration_type_counts": duration_counts,
        "resource_assignments": resource_assignment_count,
        "resource_activities": resource_activity_count,
        "resource_records": resource_record_count,
        "resource_status": resource_status,
        "resource_leveling_status": leveling_status,
        "resource_leveling_settings": level_settings,
        "resource_level_flags": resource_level_flags,
        "productivity_status": productivity_status,
        "recommended_mode": recommended_mode,
        "classification_confidence": confidence,
        "notes": notes,
    }


def resolve_p6_analysis_context(classification: dict, resource_basis: str, duration_basis: str) -> dict:
    rb = str(resource_basis or "")
    db = str(duration_basis or "")

    if rb.startswith("Resources drive"):
        requested = "RESOURCE-CONSTRAINED DRAG"
        actual = "LOGIC DRAG — DIAGNOSTIC ONLY"
        status = "WARNING"
        message = (
            "You indicated that resources drive scheduled dates. The current P6 counterfactual engine does not dynamically "
            "re-level P6 resources after each RD perturbation, so the displayed result is Logic DRAG only and must not be "
            "presented as Resource-Constrained DRAG."
        )
    elif rb.startswith("Not sure"):
        requested = "UNRESOLVED RESOURCE BASIS"
        actual = "LOGIC DRAG — PROVISIONAL"
        status = "WARNING"
        message = (
            "Resource assignments are present but their scheduling role is unresolved. Results are calculated as Logic DRAG "
            "and should be treated as provisional until the resource-leveling question is answered."
        )
    else:
        requested = "LOGIC DRAG"
        actual = "LOGIC DRAG"
        status = "OK"
        message = "Resources are not assumed to drive the counterfactual schedule. The logic/calendars/constraints model is used."

    if db.startswith("Quantity/productivity"):
        duration_interpretation = "RD derived externally from quantity/productivity"
        duration_note = (
            "Current P6 DRAG still perturbs Remaining Duration. Quantity/productivity is treated as the physical origin of RD, "
            "not yet as the direct counterfactual decision variable."
        )
    else:
        duration_interpretation = "P6 Remaining Duration is the scheduling input"
        duration_note = "Remaining Duration is treated as the intervention variable for the counterfactual."

    return {
        "requested_drag_mode": requested,
        "drag_mode": actual,
        "status": status,
        "message": message,
        "resource_basis": rb,
        "duration_basis": db,
        "duration_interpretation": duration_interpretation,
        "duration_note": duration_note,
    }


def classify_spider_model(data: dict, network=None) -> dict:
    activities = data.get("activities") or []
    links = data.get("links") or []
    resources = data.get("resources") or []
    assigns = data.get("assigns") or []

    dph = Counter(str(a.get("DPH", "") or "").strip() for a in activities)
    productivity_count = int(dph.get("Productivity", 0))
    duration_count = int(dph.get("Duration", 0))
    milestone_count = int(dph.get("Milestone", 0))

    resource_delay_activities = 0
    for a in activities:
        reason = str(a.get("f_DelayReason", "") or "")
        if reason.startswith('Resource "'):
            resource_delay_activities += 1

    scheduled_assignments = sum(1 for a in assigns if a.get("Start") and a.get("Fin") and a.get("ResCode"))
    resource_edges = len(getattr(network, "resource_edges", [])) if network is not None else 0
    negative_drag = sum(1 for a in activities if _nonempty(a.get("f_DRAGH")) and float(a.get("f_DRAGH")) < 0)

    if resources and (resource_edges or resource_delay_activities or scheduled_assignments):
        recommended = "RESOURCE-CONSTRAINED DRAG · FROZEN RESOURCE ORDER"
        confidence = "HIGH"
    else:
        recommended = "LOGIC DRAG"
        confidence = "MEDIUM"

    return {
        "source": "Spider Project JSON",
        "project": str((data.get("project") or {}).get("Name", "")),
        "activity_count": len(activities),
        "logic_relationships": len(links),
        "calendar_count": len(data.get("calendars") or []),
        "constraint_count": 0,
        "duration_basis_detected": f"Productivity: {productivity_count} · Duration: {duration_count} · Milestone: {milestone_count}",
        "resource_assignments": scheduled_assignments,
        "resource_records": len(resources),
        "resource_status": "PRESENT" if resources else "NOT PRESENT",
        "resource_leveling_status": "OBSERVED IN SCHEDULE" if resource_edges or resource_delay_activities else "UNCONFIRMED",
        "resource_order_edges": resource_edges,
        "resource_delay_activities": resource_delay_activities,
        "productivity_status": "EXPLICIT PRODUCTIVITY MODEL" if productivity_count else "NOT DETECTED",
        "negative_drag_cases": negative_drag,
        "recommended_mode": recommended,
        "classification_confidence": confidence,
        "notes": [
            "Spider activities expose DPH=Productivity/Duration/Milestone directly.",
            "Scheduled resource assignments and resource-delay reasons are treated as evidence that resources can govern dates.",
            "Negative Spider DRAG requires dynamic re-levelling / schedule adjustment beyond the frozen-order benchmark layer.",
        ],
    }


def classification_dataframe(classification: dict) -> pd.DataFrame:
    rows = []
    labels = {
        "source": "Source",
        "project": "Project",
        "activity_count": "Activities",
        "logic_relationships": "Logic relationships",
        "calendar_count": "Calendars",
        "constraint_count": "Constraints",
        "duration_basis_detected": "Detected duration basis",
        "resource_assignments": "Resource assignments",
        "resource_activities": "Activities with resources",
        "resource_records": "Resource records",
        "resource_status": "Resources",
        "resource_leveling_status": "Resource scheduling / leveling",
        "resource_order_edges": "Resource-order edges",
        "resource_delay_activities": "Resource-delay activities",
        "productivity_status": "Productivity model",
        "recommended_mode": "Recommended DRAG mode",
        "classification_confidence": "Classification confidence",
        "negative_drag_cases": "Negative DRAG references",
    }
    for k, label in labels.items():
        if k in classification:
            rows.append({"Parameter": label, "Value": classification[k]})
    for i, note in enumerate(classification.get("notes", []), 1):
        rows.append({"Parameter": f"Note {i}", "Value": note})
    return pd.DataFrame(rows)
