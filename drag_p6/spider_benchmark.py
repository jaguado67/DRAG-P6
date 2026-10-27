from __future__ import annotations

from io import BytesIO
import math

import pandas as pd

from .spider_json import SpiderNetwork, schedule_spider, links_dataframe


def _sign(x, tol=1e-9):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    if x > tol:
        return 1
    if x < -tol:
        return -1
    return 0


def _relation_profile(network: SpiderNetwork, code: str) -> str:
    rels = list(network.incoming.get(code, [])) + list(network.outgoing.get(code, []))
    res = list(network.incoming_resource.get(code, [])) + list(network.outgoing_resource.get(code, []))
    parts = []
    if rels:
        types = sorted({r.rel_type for r in rels})
        volume = sum(1 for r in rels if r.lag_type.lower() != "time")
        parts.append(f"{'/'.join(types)} · {volume} volume" if volume else "/".join(types))
    if res:
        parts.append(f"{len(res)} resource-order")
    return " · ".join(parts) if parts else "No constraints"


def compare_spider_drag(network: SpiderNetwork, tolerance_h: float = 0.01):
    # IMPORTANT: f_DRAGH belongs to the resource-constrained Spider schedule (Start/Fin),
    # not to the logic-only Early schedule.  The benchmark therefore uses the inferred
    # frozen resource-order graph for the counterfactual zero-duration run.
    _, base_f, base_d = schedule_spider(network, include_resources=True)
    target = network.target_code
    baseline_target = base_f[target]
    rows = []

    for code, n in network.nodes.items():
        spider = n.get("spider_drag_h")
        if spider is None:
            continue
        d0 = base_d[code]
        if d0 <= 1e-12:
            signed_gain = 0.0
        else:
            _, f2, _ = schedule_spider(network, {code: 0.0}, include_resources=True)
            signed_gain = baseline_target - f2[target]

        # Positive DRAG is the direct zero-duration project gain.  A negative Spider DRAG
        # is retained as a separate class: reproducing it requires dynamic resource
        # re-levelling/schedule adjustment rather than a frozen resource-order graph.
        our_drag = signed_gain if signed_gain > 0 else 0.0
        error = our_drag - spider
        abs_error = abs(error)
        sign_match = _sign(our_drag) == _sign(spider)
        rel_profile = _relation_profile(network, code)

        if spider < 0:
            note = (
                "Negative Spider DRAG: frozen resource-order counterfactual cannot reproduce "
                "resource re-levelling / schedule-adjustment anti-crashing yet."
            )
        elif abs_error <= tolerance_h:
            note = "Matched: resource-constrained zero-duration counterfactual agrees with Spider."
        else:
            note = "Residual mismatch: inspect inferred resource order / dynamic re-levelling semantics."

        rows.append({
            "Activity ID": code,
            "Activity Name": n["name"],
            "WBS Area": n["wbs_area"],
            "Duration (h)": d0,
            "Spider DRAG (h)": spider,
            "DRAG-P6 Resource-Aware (h)": our_drag,
            "DRAG-P6 (h)": our_drag,  # backward-compatible alias
            "Signed Counterfactual Gain (h)": signed_gain,
            "Error (h)": error,
            "Abs Error (h)": abs_error,
            "Match": abs_error <= tolerance_h,
            "Sign Match": sign_match,
            "Spider Critical": n["critical"],
            "Reserve (h)": n["reserve_h"],
            "Criticality Index": n["crit_index"],
            "Constraint Profile": rel_profile,
            "Diagnostic": note,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["Match", "Abs Error (h)", "Activity ID"], ascending=[False, True, True]).reset_index(drop=True)

    refs = len(df)
    matches = int(df["Match"].sum()) if refs else 0
    mae = float(df["Abs Error (h)"].mean()) if refs else math.nan
    rmse = float(math.sqrt((df["Error (h)"] ** 2).mean())) if refs else math.nan
    pos = df[df["Spider DRAG (h)"] >= 0] if refs else df
    pos_matches = int(pos["Match"].sum()) if len(pos) else 0
    pos_mae = float(pos["Abs Error (h)"].mean()) if len(pos) else math.nan
    corr = float(pos[["Spider DRAG (h)", "DRAG-P6 Resource-Aware (h)"]].corr(method="pearson").iloc[0, 1]) if len(pos) >= 2 else math.nan
    rank_corr = float(pos[["Spider DRAG (h)", "DRAG-P6 Resource-Aware (h)"]].corr(method="spearman").iloc[0, 1]) if len(pos) >= 2 else math.nan

    meta = {
        "reference_activities": refs,
        "matches": matches,
        "match_rate": matches / refs if refs else math.nan,
        "mae_h": mae,
        "rmse_h": rmse,
        "positive_reference_activities": len(pos),
        "positive_matches": pos_matches,
        "positive_match_rate": pos_matches / len(pos) if len(pos) else math.nan,
        "positive_mae_h": pos_mae,
        "positive_correlation": corr,
        "positive_rank_correlation": rank_corr,
        "negative_spider_drag_cases": int((df["Spider DRAG (h)"] < 0).sum()) if refs else 0,
        "baseline_target_h": baseline_target,
        "target_code": target,
        "tolerance_h": tolerance_h,
        "resource_order_edges": len(network.resource_edges),
    }
    return df, meta


def build_spider_benchmark_excel(network, results, meta, classification=None):
    rec = pd.DataFrame([{"Metric": k, "Value": v} for k, v in network.reconciliation.items()])
    summary = pd.DataFrame([{"Metric": k, "Value": v} for k, v in meta.items()])
    links = links_dataframe(network)
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        results.to_excel(writer, index=False, sheet_name="SPIDER_DRAG_BENCHMARK")
        if classification is not None:
            from .model_classification import classification_dataframe
            classification_dataframe(classification).to_excel(writer, index=False, sheet_name="MODEL_CLASSIFICATION")
        summary.to_excel(writer, index=False, sheet_name="BENCHMARK_SUMMARY")
        rec.to_excel(writer, index=False, sheet_name="BASELINE_RECONCILIATION")
        links.to_excel(writer, index=False, sheet_name="LOGIC_RESOURCE_CONSTRAINTS")
    return bio.getvalue()
