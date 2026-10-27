from __future__ import annotations

import math

import altair as alt
import pandas as pd
import streamlit as st

from drag_p6 import __version__, __build__
from drag_p6.calibrated import build_calibrated_network
from drag_p6.drag import compute_drag, concentration_tables, target_catalog
from drag_p6.export import build_excel
from drag_p6.sequential import compute_sequential_frontier
from drag_p6.validation import build_validation, validation_summary
from drag_p6.xer import parse_xer_bytes, project_catalog
from drag_p6.spider_json import parse_spider_json_bytes, build_spider_network, links_dataframe
from drag_p6.spider_benchmark import compare_spider_drag, build_spider_benchmark_excel
from drag_p6.model_classification import (
    classify_p6_model, classify_spider_model, classification_dataframe,
    resolve_p6_analysis_context,
)


st.set_page_config(page_title=f"DRAG-P6 v{__version__}", page_icon="⏱️", layout="wide")

st.title("DRAG-P6 Engine")
st.caption(f"Primavera P6 Critical Path DRAG · v{__version__} · {__build__}")

with st.expander("What changed in v1.1.0.0", expanded=False):
    st.markdown("""
**v1.1.0.0** keeps the reconciled one-activity DRAG engine from v1.0.0.0, adds the sequential compression layer, and now includes a **Schedule Model Classification Gate** plus the Spider Project JSON cross-validation laboratory:

- New **Schedule Model Classification Gate** before DRAG execution.
- Explicit DRAG modes: **Logic DRAG**, **Resource-Constrained DRAG**, and productivity-aware context.
- P6 asks whether resource assignments actually drive scheduled dates when the XER cannot prove it.
- Every result is labelled with the analytical mode actually supported by the current engine.
- New **Sequential Compression Frontier** tab.
- New **Spider Project JSON** input and DRAG benchmark against exported `f_DRAGH`.
- Repeats the cycle **compress → reschedule → identify the new controlling path → compress again**.
- At every stage, the engine tests compressible activities on the current representative controlling path.
- The selected activity is the one with the greatest current target gain.
- The engine numerically finds the **minimum duration reduction needed to reach that stage's gain plateau** instead of assuming that compression hours equal target-gain hours.
- Reports stage gain, cumulative gain, cumulative compression, new target date, path outcome and replacement controlling activity.
- Detects and stops at a **multi-path / fixed-anchor barrier** rather than claiming a false frontier.
- Adds a user-defined theoretical maximum compression percentage per activity.

**Boundary:** this release is a sequential single-activity greedy frontier. It is not yet a cost-optimal multi-path crashing optimizer. Simultaneous compression of tied paths is reserved for the next optimization layer.
""")

uploaded = st.file_uploader("Load Primavera P6 XER or Spider Project JSON", type=["xer", "json"])
if uploaded is None:
    st.info("Load a Primavera P6 XER or Spider Project JSON to begin.")
    st.stop()

# -----------------------------------------------------------------------------
# Spider Project JSON cross-validation mode
# -----------------------------------------------------------------------------
if uploaded.name.lower().endswith(".json"):
    try:
        spider_data = parse_spider_json_bytes(uploaded.getvalue())
        spider_net = build_spider_network(spider_data)
        spider_class = classify_spider_model(spider_data, spider_net)
    except Exception as exc:
        st.exception(exc)
        st.stop()

    st.markdown("## Schedule Model Classification")
    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
    sc1.metric("Detected model", "RESOURCE + LOGIC" if spider_class["resource_status"] == "PRESENT" else "LOGIC")
    sc2.metric("Resources", f"{spider_class['resource_records']:,}")
    sc3.metric("Resource-order edges", f"{spider_class.get('resource_order_edges', 0):,}")
    sc4.metric("Productivity activities", str((spider_class.get("duration_basis_detected", "").split("·")[0]).replace("Productivity:", "").strip()))
    sc5.metric("Recommended DRAG mode", spider_class["recommended_mode"])
    st.success(
        "Automatic classification: Spider exposes scheduled resource assignments / resource-delay evidence, so the benchmark uses "
        "**Resource-Constrained DRAG with frozen resource order**. No user assumption is needed for the positive-DRAG benchmark."
    )
    if spider_class.get("negative_drag_cases", 0):
        st.warning(
            f"{spider_class['negative_drag_cases']} negative Spider DRAG case(s) require dynamic resource re-levelling / schedule adjustment. "
            "Those cases are explicitly outside the frozen-order engine boundary."
        )
    with st.expander("Model classification details", expanded=False):
        st.dataframe(classification_dataframe(spider_class), use_container_width=True, hide_index=True)

    st.markdown("## Spider Project JSON · DRAG Cross-Validation")
    st.caption(
        "This mode reconstructs the schedule-enabled Spider network, including FS/SS/FF/SF and time/volume lags, "
        "reconstructs the resource-constrained Start/Fin baseline with inferred resource-order constraints, then applies the zero-duration counterfactual and compares it activity-by-activity with Spider's exported f_DRAGH values."
    )

    rec = spider_net.reconciliation
    r1, r2, r3, r4, r5 = st.columns(5)
    r1.metric("Baseline gate", rec["status"])
    r2.metric("Activities", f"{rec['activities']:,}")
    r3.metric("Logic links", f"{rec['logic_links']:,}")
    r4.metric("Resource-order edges", f"{rec['resource_order_edges']:,}")
    r5.metric("Target error", f"{rec['target_error_h']:.6f} h")

    if rec["status"] == "FAIL":
        st.error("Spider resource-constrained Start/Fin baseline did not reconcile sufficiently to run a meaningful DRAG comparison.")
        st.stop()
    else:
        st.success(
            f"Resource-constrained baseline reconciled: max Start error {rec['max_plan_start_error_h']:.6f} h · "
            f"max Finish error {rec['max_plan_finish_error_h']:.6f} h."
        )

    tolerance = st.number_input("DRAG comparison tolerance (h)", min_value=0.001, value=0.01, step=0.01)
    spider_results, spider_meta = compare_spider_drag(spider_net, tolerance_h=float(tolerance))

    b1, b2, b3, b4, b5, b6 = st.columns(6)
    b1.metric("Spider DRAG references", spider_meta["reference_activities"])
    b2.metric("All matches", f"{spider_meta['matches']} / {spider_meta['reference_activities']}")
    b3.metric("Positive matches", f"{spider_meta['positive_matches']} / {spider_meta['positive_reference_activities']}")
    b4.metric("Positive MAE", f"{spider_meta['positive_mae_h']:.6f} h")
    b5.metric("Positive Pearson r", f"{spider_meta['positive_correlation']:.3f}")
    b6.metric("Positive Spearman ρ", f"{spider_meta['positive_rank_correlation']:.3f}")
    st.caption(f"Spider negative DRAG cases: {spider_meta['negative_spider_drag_cases']}")

    st.info(
        "R2 correction: Spider f_DRAGH is benchmarked against the resource-constrained Start/Fin schedule, not the logic-only Early schedule. "
        "Positive cases use explicit logic plus inferred resource-order constraints. Negative Spider DRAG remains a separate re-levelling / schedule-adjustment case and is not forced to fit."
    )

    spider_tabs = st.tabs(["DRAG Benchmark", "Baseline Reconciliation", "Spider Links", "Method", "Export"])
    with spider_tabs[0]:
        show = spider_results.copy()
        day_h = float(spider_net.calendar.day_hours or 8.0)
        for col in ["Duration (h)", "Spider DRAG (h)", "DRAG-P6 Resource-Aware (h)", "Signed Counterfactual Gain (h)", "Error (h)", "Abs Error (h)"]:
            show[col.replace("(h)", "(d)")] = show[col] / day_h
        cols = [
            "Activity ID", "Activity Name", "WBS Area", "Duration (d)",
            "Spider DRAG (d)", "DRAG-P6 Resource-Aware (d)", "Signed Counterfactual Gain (d)",
            "Abs Error (d)", "Match", "Spider Critical", "Constraint Profile", "Diagnostic"
        ]
        st.dataframe(show[cols], use_container_width=True, hide_index=True)

        positives = show[show["Spider DRAG (h)"] >= 0].copy()
        if not positives.empty:
            st.markdown("### Spider vs DRAG-P6")
            plot = positives.melt(
                id_vars=["Activity ID"], value_vars=["Spider DRAG (d)", "DRAG-P6 Resource-Aware (d)"],
                var_name="Series", value_name="DRAG (d)"
            )
            chart = alt.Chart(plot).mark_bar().encode(
                y=alt.Y("Activity ID:N", sort="-x"),
                x=alt.X("DRAG (d):Q"),
                color=alt.Color("Series:N"),
                yOffset="Series:N",
                tooltip=["Activity ID:N", "Series:N", alt.Tooltip("DRAG (d):Q", format=".3f")],
            ).properties(height=max(260, 30 * len(positives)))
            st.altair_chart(chart, use_container_width=True)

    with spider_tabs[1]:
        st.dataframe(pd.DataFrame([{"Metric": k, "Value": v} for k, v in rec.items()]), use_container_width=True, hide_index=True)
        st.caption(
            "Gate policy: Spider Start/Fin is the resource-constrained baseline used for f_DRAGH. EarlyStart/EarlyFin is retained only as a logic-only diagnostic."
        )

    with spider_tabs[2]:
        st.dataframe(links_dataframe(spider_net), use_container_width=True, hide_index=True)

    with spider_tabs[3]:
        st.markdown(r"""
### Spider JSON benchmark method

R2 corrects the benchmark baseline. Spider's exported **f_DRAGH** belongs to the scheduled **Start/Fin** plan, which can include resource constraints. It is not benchmarked against the logic-only Early schedule.

For each activity *i*:

\[
\Delta_i = PF_0 - PF_{Dur_i=0}
\]

The counterfactual reschedules explicit **FS/SS/FF/SF**, time/volume lags, and the **resource-order constraints inferred from Spider's scheduled assignments**.

For positive Spider DRAG, the comparison is direct. The supplied 1 km benchmark reconciles the positive reference cases to numerical tolerance.

A negative Spider DRAG is intentionally not manufactured. Negative cases require **dynamic resource re-levelling / schedule adjustment** after the perturbation. R2 uses a frozen resource-order reconstruction, so negative DRAG remains an explicit next research layer rather than a forced fit.
""")

    with spider_tabs[4]:
        xlsx = build_spider_benchmark_excel(spider_net, spider_results, spider_meta, classification=spider_class)
        st.download_button(
            "Download Spider DRAG benchmark (.xlsx)", xlsx,
            file_name=f"DRAG_P6_vs_Spider_{spider_net.project_code or 'benchmark'}_v{__version__}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    st.divider()
    st.caption(f"DRAG-P6 Engine v{__version__} · {__build__} · Spider Project JSON cross-validation")
    st.stop()

try:
    tables = parse_xer_bytes(uploaded.getvalue())
    catalog = project_catalog(tables)
    if catalog.empty:
        raise ValueError("No PROJECT table/project record found.")

    labels = {}
    for _, r in catalog.iterrows():
        label = str(r["proj_short_name"] or r["proj_id"])
        labels[label] = str(r["proj_id"])
    chosen_project = st.selectbox("Project", list(labels.keys())) if len(labels) > 1 else list(labels.keys())[0]
    proj_id = labels[chosen_project]

    with st.spinner("Building P6-calibrated remaining network..."):
        network = build_calibrated_network(tables, proj_id)

    rec = network.reconciliation
    validation = build_validation(tables, proj_id, network)
    gate = validation_summary(tables, proj_id, network, validation)

    if not rec["reconciled"] or gate["gate_status"] == "FAIL":
        st.error("P6 reconciliation/model gate failed. DRAG results are blocked until the baseline is reconciled.")
        st.dataframe(validation, use_container_width=True, hide_index=True)
        st.stop()

    # -------------------------------------------------------------------------
    # Schedule Model Classification Gate: classify first, ask only what the XER
    # cannot prove, then label the DRAG result by the model actually solved.
    # -------------------------------------------------------------------------
    model_class = classify_p6_model(tables, proj_id, network)
    st.markdown("## Schedule Model Classification")
    mc1, mc2, mc3, mc4, mc5 = st.columns(5)
    mc1.metric("Duration basis", model_class["duration_basis_detected"])
    mc2.metric("Logic relationships", f"{model_class['logic_relationships']:,}")
    mc3.metric("Resource assignments", f"{model_class['resource_assignments']:,}")
    mc4.metric("Resource scheduling", model_class["resource_leveling_status"])
    mc5.metric("Recommended mode", model_class["recommended_mode"])

    if model_class["resource_assignments"] > 0:
        resource_options = [
            "Not sure — run Logic DRAG provisionally",
            "Resources do not drive dates — Logic DRAG",
            "Resources drive scheduled dates / schedule is resource-levelled",
        ]
        default_resource_index = 2 if model_class["resource_leveling_status"] == "POSSIBLE / CONFIGURED" else 0
        resource_basis = st.selectbox(
            "Before DRAG: do resources drive the scheduled dates?",
            resource_options, index=default_resource_index,
            help=(
                "P6 can contain resource assignments used only for costs/workload. Their presence alone does not prove that resource leveling "
                "governed the dates. Answer this before interpreting DRAG."
            ),
        )
    else:
        resource_basis = "Resources do not drive dates — Logic DRAG"
        st.caption("No resource assignments were detected for this project; no resource-basis question is required.")

    duration_basis = st.selectbox(
        "What is the physical basis of Remaining Duration?",
        [
            "Use P6 Remaining Duration as scheduling input",
            "Quantity/productivity drives RD outside P6",
        ],
        index=0,
        help=(
            "If only duration is available, use P6 Remaining Duration as the input. If RD comes from quantities/productivity outside P6, "
            "the current engine still perturbs RD but labels that physical interpretation explicitly."
        ),
    )
    analysis_context = resolve_p6_analysis_context(model_class, resource_basis, duration_basis)

    if analysis_context["status"] == "WARNING":
        st.warning(f"DRAG Mode: **{analysis_context['drag_mode']}** · {analysis_context['message']}")
    else:
        st.success(f"DRAG Mode: **{analysis_context['drag_mode']}** · {analysis_context['message']}")
    st.caption(f"Duration interpretation: {analysis_context['duration_interpretation']}. {analysis_context['duration_note']}")

    with st.expander("Model classification details", expanded=False):
        st.dataframe(classification_dataframe(model_class), use_container_width=True, hide_index=True)

    targets = target_catalog(network)
    target_labels = [x["label"] for x in targets]
    target_map = {x["label"]: x["key"] for x in targets}
    selected_label = st.selectbox("DRAG Target", target_labels, index=0)
    target_key = target_map[selected_label]

    with st.spinner("Running counterfactual Remaining Duration and replacement-path scenarios..."):
        results, target_meta = compute_drag(network, target_key)
except Exception as exc:
    st.exception(exc)
    st.stop()

hours_per_day = st.number_input(
    "Display working hours/day", min_value=1.0, max_value=24.0,
    value=float(network.calendar.day_hours or 8.0), step=0.5,
    help="Display conversion only; calculations use P6 working hours and the XER calendar."
)

# ---------- Analytical mode ----------
st.caption(
    f"**DRAG Mode:** {analysis_context['drag_mode']} · "
    f"**Duration basis:** {analysis_context['duration_interpretation']}"
)

# ---------- P6 Reconciliation Gate ----------
st.subheader("P6 Reconciliation Gate")
max_baseline_error = max(float(rec["max_start_error_h"]), float(rec["max_finish_error_h"]))
r1, r2, r3, r4, r5 = st.columns(5)
r1.metric("Model Gate", gate["gate_status"])
r2.metric("Activities checked", f"{rec['activities_checked']:,}")
r3.metric("Max baseline error", f"{max_baseline_error:.6f} h")
r4.metric("Mean baseline error", f"{gate['mean_error_h']:.6f} h")
r5.metric("Dynamic relationships", f"{rec['dynamic_relationships']:,}")

warning_parts = []
if gate["external_relationships"]:
    warning_parts.append(f"{gate['external_relationships']:,} external links")
if gate["constraints"]:
    warning_parts.append(f"{gate['constraints']:,} constrained incomplete activities")
if gate["actuals_after_data_date"]:
    warning_parts.append(f"{gate['actuals_after_data_date']:,} actuals after Data Date")

if gate["gate_status"] == "PASS WITH WARNINGS":
    st.warning("Warnings: " + " · ".join(warning_parts) + ". Review Model Validation before using the result for decisions.")
else:
    st.success("Baseline is reconciled and no blocking model warnings were detected.")

st.caption(
    f"Fixed/historical: {rec['fixed_historical_relationships']:,} · Calendar: {network.calendar.name} · "
    f"Anchors: {rec['anchors']:,}"
    + (f" · Data Date / last recalc: {gate['data_date']:%d-%b-%Y %H:%M}" if gate["data_date"] else "")
)

with st.expander("Gate technical metrics", expanded=False):
    g1, g2, g3, g4, g5 = st.columns(5)
    g1.metric("Max Start error", f"{rec['max_start_error_h']:.6f} h")
    g2.metric("Max Finish error", f"{rec['max_finish_error_h']:.6f} h")
    g3.metric("Fixed / historical", f"{rec['fixed_historical_relationships']:,}")
    g4.metric("Calendars", f"{gate['calendars']:,}")
    g5.metric("External relationships", f"{gate['external_relationships']:,}")
    g6, g7 = st.columns(2)
    g6.metric("Constraints", f"{gate['constraints']:,}")
    g7.metric("Actuals after Data Date", f"{gate['actuals_after_data_date']:,}")

# ---------- Target & DRAG ----------
st.subheader("DRAG Target & Decision Metrics")
t1, t2, t3, t4, t5, t6 = st.columns(6)
t1.metric("Target type", target_meta["target_kind"])
t2.metric("Baseline target", target_meta["baseline_target_date"].strftime("%d-%b-%Y %H:%M"))
t3.metric("Activities with DRAG", f"{target_meta['activities_with_drag']:,}")
t4.metric("Maximum Individual DRAG", f"{target_meta['max_individual_drag_h']/hours_per_day:,.2f} d")
t5.metric("Full / Partial", f"{target_meta['full_transmission_activities']} / {target_meta['partial_transmission_activities']}")
t6.metric("Path switches", f"{target_meta['path_switch_activities']:,}")

st.caption(
    f"Baseline target driver: **{target_meta['baseline_driver']}** · "
    f"Representative controlling chain: {target_meta['baseline_controlling_path_count']} activities · "
    f"Maximum Individual DRAG remains the one-activity exposure metric. Use **Sequential Compression Frontier** for staged crashing."
)

with st.expander("Baseline controlling path", expanded=False):
    st.code(target_meta["baseline_controlling_path"], language=None)
    if target_meta["baseline_finish_tie_count"] > 1:
        st.warning(
            f"{target_meta['baseline_finish_tie_count']} activities tie at the baseline target finish. "
            "The displayed path is one deterministic representative branch."
        )

# ---------- Display conversion ----------
display = results.copy()
display["Remaining Duration (d)"] = display["Remaining Duration (h)"] / hours_per_day
display["DRAG (d)"] = display["DRAG (h)"] / hours_per_day
display["Compression Headroom (d)"] = display["Compression Headroom (h)"] / hours_per_day
display["P6 Total Float (d)"] = pd.to_numeric(display["P6 Total Float (h)"], errors="coerce") / hours_per_day

# A finite switch threshold is only observed for Partial transmission.
display["Switch Threshold (d)"] = pd.to_numeric(display["Switch Threshold (h)"], errors="coerce") / hours_per_day

def threshold_text(row):
    if row["Transmission"] == "Partial" and pd.notna(row["Switch Threshold (d)"]):
        replacement = str(row.get("Replacement Controlling Activity", "")).strip()
        replacement_id = replacement.split(" — ", 1)[0] if replacement else "replacement path"
        return f"{row['Switch Threshold (d)']:.2f} d → {replacement_id}"
    if row["Transmission"] == "Full":
        return "No switch within RD"
    return "—"

display["Switch Threshold"] = display.apply(threshold_text, axis=1)

area_conc, location_conc = concentration_tables(results, hours_per_day)

results_tab, frontier_tab, analytics_tab, recon_tab, validation_tab, method_tab, export_tab = st.tabs([
    "DRAG Results", "Sequential Compression Frontier", "Decision Analytics", "Reconciliation", "Model Validation", "Method", "Export"
])

# ---------- DRAG Results ----------
with results_tab:
    with st.expander("Filters", expanded=False):
        f1, f2, f3 = st.columns(3)
        search_text = f1.text_input("Activity ID / Name contains", value="").strip().lower()
        selected_wbs = f2.multiselect("WBS Area", sorted(display["WBS Area"].dropna().astype(str).unique().tolist()))
        selected_locations = f3.multiselect("Location", sorted(display["Location"].dropna().astype(str).unique().tolist()))

        f4, f5, f6 = st.columns(3)
        selected_transmission = f4.multiselect("Transmission", ["Full", "Partial", "Zero"], default=["Full", "Partial"])
        selected_outcome = f5.multiselect(
            "Path Outcome", ["Same Path", "Terminal Shift", "Replacement Path"],
            default=["Same Path", "Terminal Shift", "Replacement Path"]
        )
        max_drag_days = float(display["DRAG (d)"].max()) if not display.empty else 0.0
        min_drag = f6.number_input("Minimum DRAG (d)", min_value=0.0, max_value=max(0.0, max_drag_days), value=0.0, step=0.25)

    view = display.copy()
    if search_text:
        mask = (
            view["Activity ID"].astype(str).str.lower().str.contains(search_text, na=False)
            | view["Activity Name"].astype(str).str.lower().str.contains(search_text, na=False)
        )
        view = view[mask]
    if selected_wbs:
        view = view[view["WBS Area"].astype(str).isin(selected_wbs)]
    if selected_locations:
        view = view[view["Location"].astype(str).isin(selected_locations)]
    if selected_transmission:
        view = view[view["Transmission"].isin(selected_transmission)]
    if selected_outcome:
        view = view[view["Path Outcome"].isin(selected_outcome)]
    view = view[view["DRAG (d)"] >= float(min_drag) - 1e-12]

    st.caption(f"Showing {len(view):,} of {len(display):,} incomplete activities.")

    main_cols = [
        "DRAG Rank", "Activity ID", "Activity Name", "WBS Area", "Location",
        "Remaining Duration (d)", "DRAG (d)", "DRAG Transmission Ratio",
        "Transmission", "Compression Headroom (d)", "Switch Threshold",
        "Path Outcome", "Replacement Controlling Activity", "Scenario Target Finish"
    ]

    st.dataframe(
        view[main_cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Remaining Duration (d)": st.column_config.NumberColumn("RD (d)", format="%.2f"),
            "DRAG (d)": st.column_config.NumberColumn("DRAG (d)", format="%.2f"),
            "DRAG Transmission Ratio": st.column_config.ProgressColumn(
                "DTR", help="DRAG Transmission Ratio = DRAG / Remaining Duration. The bar is scaled from 0 to 1.",
                min_value=0.0, max_value=1.0, format="%.3f", width="medium"
            ),
            "Compression Headroom (d)": st.column_config.NumberColumn("Headroom (d)", format="%.2f"),
            "Scenario Target Finish": st.column_config.DatetimeColumn("Scenario Finish", format="DD-MMM-YYYY HH:mm"),
        },
    )

    st.markdown(
        "**Reading rule:** `Full` means the current RD is fully transmitted to the selected target. "
        "`Partial` means a replacement branch takes control before RD reaches zero. "
        "**Headroom = RD − DRAG** is the part of current RD that cannot further reduce this target in the one-activity scenario. "
        "**Path Outcome** distinguishes Same Path, Terminal Shift, and a genuine Replacement Path."
    )

    positive_view = view[view["DRAG (h)"] > 1e-9].head(10).copy()
    if not positive_view.empty:
        st.markdown("### RD / DRAG — top 10 decision view")
        bullet = positive_view[[
            "Activity ID", "Activity Name", "Remaining Duration (d)", "DRAG (d)",
            "Compression Headroom (d)", "DRAG Transmission Ratio"
        ]].copy()

        base = alt.Chart(bullet).encode(
            y=alt.Y("Activity ID:N", sort=None, title=None),
            tooltip=[
                alt.Tooltip("Activity ID:N"),
                alt.Tooltip("Activity Name:N"),
                alt.Tooltip("Remaining Duration (d):Q", format=".2f", title="RD (d)"),
                alt.Tooltip("DRAG (d):Q", format=".2f"),
                alt.Tooltip("Compression Headroom (d):Q", format=".2f", title="Headroom (d)"),
                alt.Tooltip("DRAG Transmission Ratio:Q", format=".3f", title="DTR"),
            ],
        )
        rd_layer = base.mark_bar(opacity=0.24, size=24).encode(
            x=alt.X("Remaining Duration (d):Q", title="Working days")
        )
        drag_layer = base.mark_bar(opacity=0.90, size=11).encode(
            x=alt.X("DRAG (d):Q", title="Working days")
        )
        rd_text = base.mark_text(align="left", dx=5, opacity=0.65).encode(
            x=alt.X("Remaining Duration (d):Q"),
            text=alt.Text("Remaining Duration (d):Q", format=".2f"),
        )
        st.altair_chart(
            (rd_layer + drag_layer + rd_text).properties(height=max(260, len(bullet) * 32)),
            use_container_width=True,
        )
        st.caption(
            "RD is the full faint bar; DRAG is overlaid inside it. The uncovered portion is Compression Headroom. "
            "The chart is deliberately non-stacked: DRAG is part of RD, not an additional duration."
        )

    with st.expander("Technical Details", expanded=False):
        technical_cols = [
            "DRAG Rank", "Activity ID", "Activity Name", "Status", "Task Type", "WBS Path",
            "Remaining Duration (d)", "DRAG (d)", "DRAG Transmission Ratio", "Compression Headroom (d)",
            "Switch Threshold (d)", "Switch Threshold Status", "Baseline Target Driver",
            "Path Outcome", "Path Switch", "Replacement Controlling Activity", "Scenario Target Driver",
            "Scenario Driver Tie Count", "P6 Total Float (d)", "P6 Early Start", "P6 Early Finish",
            "Scenario Target Finish"
        ]
        st.dataframe(view[technical_cols], use_container_width=True, hide_index=True)

# ---------- Sequential Compression Frontier ----------
with frontier_tab:
    st.markdown("### Sequential Compression Frontier")
    if analysis_context["drag_mode"] != "LOGIC DRAG":
        st.warning(
            f"Frontier mode: **{analysis_context['drag_mode']}**. The current P6 frontier reschedules logic/calendars/anchors only; "
            "it does not dynamically re-level P6 resources. Treat this frontier as a logic diagnostic under the selected assumptions."
        )
    st.caption(
        "This is the v1.1 sequential logic experiment: compress → reschedule → identify the new controlling path → repeat. "
        "The frontier is conditional on the selected target and the compression limit below."
    )

    fc1, fc2, fc3 = st.columns(3)
    frontier_max_stages = fc1.number_input(
        "Maximum stages", min_value=1, max_value=50, value=20, step=1,
        help="Safety limit for the sequential experiment."
    )
    frontier_compression_pct = fc2.number_input(
        "Maximum compression per activity (%)", min_value=1.0, max_value=100.0, value=100.0, step=5.0,
        help="Theoretical limit relative to the activity's current P6 Remaining Duration. 100% allows RD to reach zero."
    )
    frontier_min_gain_d = fc3.number_input(
        "Minimum stage gain (d)", min_value=0.0, max_value=10.0, value=0.01, step=0.01,
        help="Stops consideration of immaterial stage gains."
    )

    frontier_key = (
        f"frontier::{uploaded.name}::{len(uploaded.getvalue())}::{proj_id}::{target_key}::"
        f"{int(frontier_max_stages)}::{float(frontier_compression_pct):.4f}::{float(frontier_min_gain_d):.6f}"
    )

    if st.button("Run Sequential Compression Frontier", type="primary"):
        with st.spinner("Running sequential compression stages and path-switch recalculations..."):
            frontier_df, frontier_meta = compute_sequential_frontier(
                network,
                target_key=target_key,
                max_stages=int(frontier_max_stages),
                max_compression_pct=float(frontier_compression_pct),
                minimum_stage_gain_h=float(frontier_min_gain_d) * hours_per_day,
            )
            st.session_state[frontier_key] = (frontier_df, frontier_meta)

    frontier_payload = st.session_state.get(frontier_key)
    if frontier_payload is None:
        st.info("Run the sequential frontier to calculate staged compression for this target.")
    else:
        frontier_df, frontier_meta = frontier_payload

        fm1, fm2, fm3, fm4, fm5 = st.columns(5)
        fm1.metric("Stages completed", f"{frontier_meta['stages_completed']:,}")
        fm2.metric("Cumulative target gain", f"{frontier_meta['total_target_gain_h']/hours_per_day:,.2f} d")
        fm3.metric("Compression applied", f"{frontier_meta['total_compression_applied_h']/hours_per_day:,.2f} d")
        fm4.metric("Overall transmission", f"{frontier_meta['overall_transmission_ratio']:.3f}")
        fm5.metric("Path-switch stages", f"{frontier_meta['path_switch_stages']:,}")

        st.markdown(
            f"**Target:** {frontier_meta['initial_target_date']:%d-%b-%Y %H:%M} → "
            f"**{frontier_meta['final_target_date']:%d-%b-%Y %H:%M}**"
        )

        if "Multi-path barrier" in frontier_meta["stop_reason"]:
            st.warning(f"Frontier stop: {frontier_meta['stop_reason']}. This is an explicit optimization boundary, not zero remaining project compressibility.")
        else:
            st.info(f"Frontier stop: {frontier_meta['stop_reason']}")

        if frontier_df.empty:
            st.warning("No positive single-activity sequential compression stage was found for this target under the selected limits.")
        else:
            fview = frontier_df.copy()
            for hcol, dcol in [
                ("RD Before (h)", "RD Before (d)"),
                ("RD After (h)", "RD After (d)"),
                ("Compression Applied (h)", "Compression Applied (d)"),
                ("Stage Target Gain (h)", "Stage Gain (d)"),
                ("Cumulative Compression (h)", "Cumulative Compression (d)"),
                ("Cumulative Target Gain (h)", "Cumulative Gain (d)"),
            ]:
                fview[dcol] = fview[hcol] / hours_per_day

            st.markdown("#### Compression stages")
            frontier_cols = [
                "Stage", "Activity ID", "Activity Name", "WBS Area", "Location",
                "RD Before (d)", "Compression Applied (d)", "Stage Gain (d)",
                "Compression Transmission Ratio", "Cumulative Gain (d)",
                "Target After Date", "Path Outcome", "Replacement Controlling Activity"
            ]
            st.dataframe(
                fview[frontier_cols], use_container_width=True, hide_index=True,
                column_config={
                    "RD Before (d)": st.column_config.NumberColumn(format="%.2f"),
                    "Compression Applied (d)": st.column_config.NumberColumn(format="%.2f"),
                    "Stage Gain (d)": st.column_config.NumberColumn(format="%.2f"),
                    "Compression Transmission Ratio": st.column_config.ProgressColumn(
                        "Stage Transmission", min_value=0.0, max_value=1.0, format="%.3f"
                    ),
                    "Cumulative Gain (d)": st.column_config.NumberColumn(format="%.2f"),
                    "Target After Date": st.column_config.DatetimeColumn("New Target Finish", format="DD-MMM-YYYY HH:mm"),
                }
            )

            st.markdown("#### Project Compression Frontier")
            frontier_chart = alt.Chart(fview).mark_line(point=True).encode(
                x=alt.X("Stage:Q", title="Sequential stage"),
                y=alt.Y("Cumulative Gain (d):Q", title="Cumulative target gain (working days)"),
                tooltip=[
                    alt.Tooltip("Stage:Q"),
                    alt.Tooltip("Activity ID:N"),
                    alt.Tooltip("Activity Name:N"),
                    alt.Tooltip("Compression Applied (d):Q", format=".2f"),
                    alt.Tooltip("Stage Gain (d):Q", format=".2f"),
                    alt.Tooltip("Cumulative Gain (d):Q", format=".2f"),
                    alt.Tooltip("Path Outcome:N"),
                    alt.Tooltip("Replacement Controlling Activity:N"),
                ],
            ).properties(height=320)
            st.altair_chart(frontier_chart, use_container_width=True)

            st.markdown("#### Compression effort vs target gain")
            effort_chart = alt.Chart(fview).mark_line(point=True).encode(
                x=alt.X("Cumulative Compression (d):Q", title="Cumulative duration compressed (working days across selected activities)"),
                y=alt.Y("Cumulative Gain (d):Q", title="Cumulative target gain (working days)"),
                tooltip=[
                    alt.Tooltip("Stage:Q"),
                    alt.Tooltip("Activity ID:N"),
                    alt.Tooltip("Cumulative Compression (d):Q", format=".2f"),
                    alt.Tooltip("Cumulative Gain (d):Q", format=".2f"),
                    alt.Tooltip("Compression Transmission Ratio:Q", format=".3f", title="Stage transmission"),
                ],
            ).properties(height=300)
            st.altair_chart(effort_chart, use_container_width=True)

            switch_only = fview[fview["Path Outcome"] != "Same Path"]
            if not switch_only.empty:
                st.markdown("#### Path switching map")
                st.dataframe(
                    switch_only[[
                        "Stage", "Activity ID", "Stage Gain (d)", "Target After Date",
                        "Path Outcome", "Path Switch", "Replacement Controlling Activity",
                        "Baseline Driver", "New Driver"
                    ]],
                    use_container_width=True, hide_index=True,
                )

            with st.expander("Inspect stage controlling paths", expanded=False):
                stage_pick = st.selectbox("Stage", fview["Stage"].astype(int).tolist(), key="frontier_stage_pick")
                srow = fview[fview["Stage"] == stage_pick].iloc[0]
                cp1, cp2 = st.columns(2)
                with cp1:
                    st.markdown("**Before compression**")
                    st.code(srow["Controlling Path Before"], language=None)
                with cp2:
                    st.markdown("**After compression**")
                    st.code(srow["Controlling Path After"], language=None)

        st.caption(
            "v1.1.0.0 frontier policy: one activity is compressed per stage using a greedy maximum-current-gain rule. "
            "When tied paths need simultaneous action, the engine stops and reports the barrier. "
            "No cost-optimality claim is made in this release."
        )

# ---------- Decision Analytics ----------
with analytics_tab:
    st.markdown("### Target exposure")
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Maximum Individual DRAG", f"{target_meta['max_individual_drag_h']/hours_per_day:,.2f} d")
    a2.metric("Activities at maximum", f"{target_meta['max_individual_drag_activity_count']:,}")
    a3.metric("Dominant WBS Area", target_meta["dominant_wbs"])
    a4.metric("Dominant Location", target_meta["dominant_location"])
    st.caption(
        f"{target_meta['dominant_wbs_share']*100:.1f}% of positive-DRAG activities are concentrated in **{target_meta['dominant_wbs']}**; "
        f"the leading single location is **{target_meta['dominant_location']}** with {target_meta['dominant_location_share']*100:.1f}%. "
        "These are concentration shares by activity count; DRAG values are not summed."
    )

    if target_meta["max_individual_drag_activities"]:
        st.info(f"Activities at Maximum Individual DRAG: {target_meta['max_individual_drag_activities']}")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### DRAG concentration by WBS area")
        if area_conc.empty:
            st.info("No positive DRAG activities for this target.")
        else:
            st.dataframe(area_conc, use_container_width=True, hide_index=True)
    with c2:
        st.markdown("### DRAG concentration by location")
        if location_conc.empty:
            st.info("No positive DRAG activities for this target.")
        else:
            st.dataframe(location_conc, use_container_width=True, hide_index=True)

    st.markdown("### Partial-transmission / switch-threshold decisions")
    partial = display[(display["DRAG (h)"] > 1e-9) & (display["Transmission"] == "Partial")].copy()
    if partial.empty:
        st.info("No Partial-transmission activities for this target. No finite switch threshold is observed inside current RD.")
    else:
        partial_cols = [
            "DRAG Rank", "Activity ID", "Activity Name", "WBS Area", "Location",
            "Remaining Duration (d)", "DRAG (d)", "DRAG Transmission Ratio",
            "Compression Headroom (d)", "Switch Threshold", "Replacement Controlling Activity"
        ]
        st.dataframe(partial[partial_cols], use_container_width=True, hide_index=True)

    st.markdown("### Path-switch scenarios")
    switched = display[(display["DRAG (h)"] > 1e-9) & (display["Controlling Path Changed"])].copy()
    if switched.empty:
        st.info("No positive-DRAG scenario changes the representative controlling path.")
    else:
        switch_cols = [
            "DRAG Rank", "Activity ID", "Activity Name", "DRAG (d)", "DRAG Transmission Ratio",
            "Path Outcome", "Path Switch", "Replacement Controlling Activity", "Scenario Target Driver",
            "Scenario Target Finish", "Scenario Driver Tie Count"
        ]
        st.dataframe(switched[switch_cols], use_container_width=True, hide_index=True)

        selected_activity = st.selectbox(
            "Inspect scenario controlling path",
            switched["Activity ID"].astype(str).tolist(),
        )
        detail = switched[switched["Activity ID"].astype(str) == selected_activity].iloc[0]
        p1, p2 = st.columns(2)
        with p1:
            st.markdown("**Baseline controlling path**")
            st.code(detail["Baseline Controlling Path"], language=None)
        with p2:
            st.markdown("**Scenario controlling path after RD = 0**")
            st.code(detail["Scenario Controlling Path"], language=None)

# ---------- Reconciliation ----------
with recon_tab:
    st.markdown("### Baseline reconciliation")
    rec_df = pd.DataFrame([
        ["Gate status", gate["gate_status"]],
        ["Activities checked", rec["activities_checked"]],
        ["Maximum start error (h)", rec["max_start_error_h"]],
        ["Maximum finish error (h)", rec["max_finish_error_h"]],
        ["Mean absolute start error (h)", rec["mae_start_h"]],
        ["Mean absolute finish error (h)", rec["mae_finish_h"]],
        ["Dynamic relationships", rec["dynamic_relationships"]],
        ["Fixed/historical relationships", rec["fixed_historical_relationships"]],
        ["Calibration anchors", rec["anchors"]],
        ["External relationships", rec["external_relationships"]],
        ["Incomplete-activity calendars", gate["calendars"]],
        ["Incomplete activities with constraints", gate["constraints"]],
        ["Activities with actuals after Data Date", gate["actuals_after_data_date"]],
    ], columns=["Metric", "Value"])
    st.dataframe(rec_df, hide_index=True, use_container_width=True)

    st.markdown("### External relationships")
    if network.external_relationships.empty:
        st.info("No external relationships detected.")
    else:
        st.dataframe(network.external_relationships, hide_index=True, use_container_width=True)

# ---------- Model validation ----------
with validation_tab:
    st.dataframe(validation, use_container_width=True, hide_index=True)

# ---------- Method ----------
with method_tab:
    st.info(
        f"Current analytical context — DRAG Mode: {analysis_context['drag_mode']} · "
        f"Duration basis: {analysis_context['duration_interpretation']}"
    )
    st.markdown(r"""
### P6-calibrated DRAG — v1.1.0.0

For activity *i* and selected target *T*:

\[
DRAG_{i,T} = EF_T^{P6\ baseline} - EF_T^{(RD_i=0)}
\]

Build 3 performs a complete one-activity counterfactual and then identifies the controlling chain active after that intervention.

### Decision variables

\[
DTR_i = \frac{DRAG_i}{RD_i}
\]

**DRAG Transmission Ratio (DTR)** reads:
- **Full:** DTR ≈ 1.0 — all current RD is transmitted to the selected target.
- **Partial:** 0 < DTR < 1.0 — another branch takes control before RD reaches zero.
- **Zero:** DRAG = 0 — this activity does not currently move the selected target in the one-activity scenario.

\[
Compression\ Headroom_i = RD_i - DRAG_i
\]

Headroom is the part of current RD that cannot further reduce the selected target after the controlling condition changes.

For **Partial** activities only, the current one-activity experiment also provides an observed switch threshold:

\[
Switch\ Threshold_i = DRAG_i
\]

For a **Full** activity, Build 3 does **not** claim a finite switch threshold: no path switch occurs before current RD reaches zero.

### Sequential Compression Frontier — v1.1.0.0

v1.1 adds the staged process:

**compress → reschedule → identify the new controlling path → compress again**.

At each stage, the engine tests compressible activities on the current representative controlling path, chooses the greatest current target gain, and numerically finds the minimum compression needed to reach that gain plateau.

This creates a **sequential single-activity frontier**. It is materially different from summing individual DRAG values.

### Optimization boundary

The v1.1 frontier is **not yet a global cost-optimal crashing solution**. When equal / tied controlling paths require simultaneous compression, the engine stops at a **multi-path barrier**. A future optimization layer can solve simultaneous path compression using crash limits and costs.
""")

# ---------- Export ----------
with export_tab:
    export_frontier = None
    export_frontier_meta = None
    # Export the most recently computed frontier for the current target/settings when available.
    try:
        export_payload = st.session_state.get(frontier_key)
        if export_payload is not None:
            export_frontier, export_frontier_meta = export_payload
    except Exception:
        pass

    xlsx = build_excel(
        results, validation, network, target_meta,
        frontier=export_frontier, frontier_meta=export_frontier_meta,
        classification=model_class, analysis_context=analysis_context
    )
    st.download_button(
        "Download DRAG + Frontier analysis (.xlsx)", data=xlsx,
        file_name=f"DRAG_P6_{network.project_name}_v{__version__}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

st.divider()
st.caption(f"DRAG-P6 Engine v{__version__} · {__build__} · Primavera P6 XER external analytics · Explicit DRAG Mode")
