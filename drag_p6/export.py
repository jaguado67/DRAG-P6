from __future__ import annotations

from io import BytesIO
import pandas as pd

from .drag import concentration_tables


def build_excel(results, validation, network, target_meta, frontier=None, frontier_meta=None, classification=None, analysis_context=None):
    meta_rows = [
        {"Parameter": "Project", "Value": network.project_name},
        {"Parameter": "Target", "Value": target_meta["target_kind"]},
        {"Parameter": "Baseline target driver", "Value": target_meta["baseline_driver"]},
        {"Parameter": "Baseline target date", "Value": str(target_meta["baseline_target_date"])},
        {"Parameter": "Baseline controlling path", "Value": target_meta["baseline_controlling_path"]},
        {"Parameter": "Baseline path activities", "Value": target_meta["baseline_controlling_path_count"]},
        {"Parameter": "Baseline finish tie count", "Value": target_meta["baseline_finish_tie_count"]},
        {"Parameter": "Activities with DRAG", "Value": target_meta["activities_with_drag"]},
        {"Parameter": "Full-transmission activities", "Value": target_meta["full_transmission_activities"]},
        {"Parameter": "Partial-transmission activities", "Value": target_meta["partial_transmission_activities"]},
        {"Parameter": "Path-switch activities", "Value": target_meta["path_switch_activities"]},
        {"Parameter": "Maximum Individual DRAG (h)", "Value": target_meta["max_individual_drag_h"]},
        {"Parameter": "Activities at Maximum Individual DRAG", "Value": target_meta["max_individual_drag_activity_count"]},
        {"Parameter": "Maximum Individual DRAG activities", "Value": target_meta["max_individual_drag_activities"]},
        {"Parameter": "Dominant WBS", "Value": target_meta["dominant_wbs"]},
        {"Parameter": "Dominant WBS share", "Value": target_meta["dominant_wbs_share"]},
        {"Parameter": "Dominant location", "Value": target_meta["dominant_location"]},
        {"Parameter": "Dominant location share", "Value": target_meta["dominant_location_share"]},
        {"Parameter": "Reconciled", "Value": network.reconciliation["reconciled"]},
        {"Parameter": "Max baseline start error (h)", "Value": network.reconciliation["max_start_error_h"]},
        {"Parameter": "Max baseline finish error (h)", "Value": network.reconciliation["max_finish_error_h"]},
        {"Parameter": "Mean absolute start error (h)", "Value": network.reconciliation["mae_start_h"]},
        {"Parameter": "Mean absolute finish error (h)", "Value": network.reconciliation["mae_finish_h"]},
    ]

    if frontier_meta:
        meta_rows.extend([
            {"Parameter": "Frontier type", "Value": frontier_meta.get("frontier_type")},
            {"Parameter": "Frontier stages completed", "Value": frontier_meta.get("stages_completed")},
            {"Parameter": "Frontier total target gain (h)", "Value": frontier_meta.get("total_target_gain_h")},
            {"Parameter": "Frontier total compression applied (h)", "Value": frontier_meta.get("total_compression_applied_h")},
            {"Parameter": "Frontier overall transmission ratio", "Value": frontier_meta.get("overall_transmission_ratio")},
            {"Parameter": "Frontier path switch stages", "Value": frontier_meta.get("path_switch_stages")},
            {"Parameter": "Frontier max compression per activity (%)", "Value": frontier_meta.get("max_compression_pct")},
            {"Parameter": "Frontier stop reason", "Value": frontier_meta.get("stop_reason")},
            {"Parameter": "Global optimum claimed", "Value": frontier_meta.get("complete_global_frontier")},
        ])

    if analysis_context:
        meta_rows.extend([
            {"Parameter": "DRAG Mode", "Value": analysis_context.get("drag_mode")},
            {"Parameter": "Requested DRAG Mode", "Value": analysis_context.get("requested_drag_mode")},
            {"Parameter": "Resource basis", "Value": analysis_context.get("resource_basis")},
            {"Parameter": "Duration basis", "Value": analysis_context.get("duration_basis")},
            {"Parameter": "Duration interpretation", "Value": analysis_context.get("duration_interpretation")},
        ])

    meta_df = pd.DataFrame(meta_rows)

    dyn = pd.DataFrame([{
        "Pred Task ID": r.pred_task_id, "Succ Task ID": r.succ_task_id,
        "Type": r.rel_type, "Lag (h)": r.lag_h
    } for r in network.dynamic_relationships])

    hours_per_day = float(network.calendar.day_hours or 8.0)
    area_conc, location_conc = concentration_tables(results, hours_per_day)

    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        results.to_excel(writer, index=False, sheet_name="DRAG_RESULTS")
        if classification is not None:
            from .model_classification import classification_dataframe
            classification_dataframe(classification).to_excel(writer, index=False, sheet_name="MODEL_CLASSIFICATION")
        meta_df.to_excel(writer, index=False, sheet_name="TARGET_RECONCILIATION")
        if frontier is not None:
            frontier.to_excel(writer, index=False, sheet_name="SEQUENTIAL_FRONTIER")
        area_conc.to_excel(writer, index=False, sheet_name="DRAG_BY_WBS_AREA")
        location_conc.to_excel(writer, index=False, sheet_name="DRAG_BY_LOCATION")
        validation.to_excel(writer, index=False, sheet_name="MODEL_VALIDATION")
        dyn.to_excel(writer, index=False, sheet_name="DYNAMIC_RELATIONSHIPS")
        network.fixed_relationships.to_excel(writer, index=False, sheet_name="FIXED_HISTORICAL")
        network.external_relationships.to_excel(writer, index=False, sheet_name="EXTERNAL_RELATIONSHIPS")
    return bio.getvalue()
