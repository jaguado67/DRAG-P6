from __future__ import annotations

import pandas as pd

from .calendar import parse_p6_datetime


def _project_task_df(tables, proj_id):
    task = tables.get("TASK", pd.DataFrame())
    if task.empty:
        return task
    return task[task["proj_id"].astype(str) == str(proj_id)].copy()


def _last_recalc(tables, proj_id):
    project = tables.get("PROJECT", pd.DataFrame())
    if project.empty:
        return None
    prow = project[project["proj_id"].astype(str) == str(proj_id)]
    if prow.empty:
        return None
    return parse_p6_datetime(prow.iloc[0].get("last_recalc_date", ""))


def _future_actual_count(task, recalc):
    if recalc is None or task.empty:
        return 0
    count = 0
    for _, r in task.iterrows():
        for col in ("act_start_date", "act_end_date"):
            dt = parse_p6_datetime(r.get(col, ""))
            if dt and dt > recalc:
                count += 1
                break
    return count


def build_validation(tables, proj_id, network):
    issues = []
    rec = network.reconciliation
    if rec["reconciled"]:
        issues.append(("OK", "P6_RECONCILIATION", f"{rec['activities_checked']} incomplete activities reconcile to P6 early dates within {rec['tolerance_h']:.3f} h."))
    else:
        issues.append(("ERROR", "P6_RECONCILIATION", f"Maximum baseline date error is {max(rec['max_start_error_h'], rec['max_finish_error_h']):.3f} h."))

    issues.append(("OK", "CALENDAR", f"Single remaining-network calendar: {network.calendar.name} ({network.calendar.day_hours:g} h/day)."))

    if rec["external_relationships"]:
        incoming = 0
        outgoing = 0
        if not network.external_relationships.empty:
            incoming = int((network.external_relationships["Direction"] == "Incoming").sum())
            outgoing = int((network.external_relationships["Direction"] == "Outgoing").sum())
        issues.append(("WARNING", "EXTERNAL_RELATIONSHIPS", f"{rec['external_relationships']} external relationships detected ({incoming} incoming, {outgoing} outgoing). Their baseline effect is preserved through calibration anchors, but external projects are not rescheduled."))

    if rec["fixed_historical_relationships"]:
        issues.append(("INFO", "HISTORICAL_STATUS_LOGIC", f"{rec['fixed_historical_relationships']} internal relationships classified as historical/fixed; {rec['dynamic_relationships']} remain dynamic for DRAG scenarios."))

    task = _project_task_df(tables, proj_id)
    incomplete = task[task.get("status_code", pd.Series(index=task.index, dtype=str)).astype(str) != "TK_Complete"].copy() if not task.empty else task

    constraints = 0
    if not incomplete.empty and "cstr_type" in incomplete.columns:
        c = incomplete["cstr_type"].fillna("").astype(str).str.strip()
        constraints = int((~c.isin(["", "None", "nan"])).sum())
        if constraints:
            issues.append(("INFO", "CONSTRAINTS", f"{constraints} incomplete activities contain P6 constraints. Their baseline timing effect is preserved by reconciliation/calibration anchors."))

    recalc = _last_recalc(tables, proj_id)
    future_actuals = _future_actual_count(task, recalc)
    if future_actuals:
        issues.append(("WARNING", "ACTUALS_AFTER_RECALC", f"{future_actuals} activities contain an Actual Start/Finish later than PROJECT.last_recalc_date ({recalc:%Y-%m-%d %H:%M}). Review the update chronology."))

    sched = network.schedoptions_row
    if sched.get("sched_retained_logic") == "Y":
        issues.append(("INFO", "RETAINED_LOGIC", "P6 Retained Logic is enabled. The calibrated network preserves status effects visible in the P6 early dates."))
    if sched.get("sched_use_project_end_date_for_float") == "Y":
        issues.append(("INFO", "FLOAT_REFERENCE", "P6 is configured to use Project End Date for float. P6 Total Float therefore does not necessarily identify the path driving the selected DRAG target."))

    return pd.DataFrame(issues, columns=["Severity", "Code", "Message"])


def validation_summary(tables, proj_id, network, validation):
    task = _project_task_df(tables, proj_id)
    incomplete = task[task.get("status_code", pd.Series(index=task.index, dtype=str)).astype(str) != "TK_Complete"].copy() if not task.empty else task

    if not incomplete.empty and "clndr_id" in incomplete.columns:
        calendars = sorted({str(x) for x in incomplete["clndr_id"].fillna("").tolist() if str(x)})
    else:
        calendars = []

    constraints = 0
    if not incomplete.empty and "cstr_type" in incomplete.columns:
        c = incomplete["cstr_type"].fillna("").astype(str).str.strip()
        constraints = int((~c.isin(["", "None", "nan"])).sum())

    recalc = _last_recalc(tables, proj_id)
    future_actuals = _future_actual_count(task, recalc)

    warning_count = int((validation["Severity"] == "WARNING").sum()) if not validation.empty else 0
    error_count = int((validation["Severity"] == "ERROR").sum()) if not validation.empty else 0
    if error_count or not network.reconciliation.get("reconciled", False):
        status = "FAIL"
    elif warning_count:
        status = "PASS WITH WARNINGS"
    else:
        status = "PASS"

    rec = network.reconciliation
    return {
        "gate_status": status,
        "warning_count": warning_count,
        "error_count": error_count,
        "calendars": len(calendars),
        "constraints": constraints,
        "actuals_after_data_date": future_actuals,
        "data_date": recalc,
        "mean_error_h": (float(rec.get("mae_start_h", 0.0)) + float(rec.get("mae_finish_h", 0.0))) / 2.0,
        "external_relationships": int(rec.get("external_relationships", 0)),
    }
