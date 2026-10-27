import pandas as pd

from drag_p6.model_classification import classify_p6_model, classify_spider_model, resolve_p6_analysis_context
from drag_p6.spider_json import parse_spider_json_bytes, build_spider_network


def test_p6_classification_asks_when_resources_exist_but_leveling_unconfirmed():
    tables = {
        "PROJECT": pd.DataFrame([{"proj_id": "1", "proj_short_name": "P"}]),
        "TASK": pd.DataFrame([
            {"proj_id": "1", "task_id": "A", "status_code": "TK_NotStart", "duration_type": "DT_FixedDrtn", "clndr_id": "C", "cstr_type": ""},
            {"proj_id": "1", "task_id": "B", "status_code": "TK_NotStart", "duration_type": "DT_FixedDrtn", "clndr_id": "C", "cstr_type": ""},
        ]),
        "TASKPRED": pd.DataFrame([{"proj_id": "1", "task_id": "B", "pred_task_id": "A"}]),
        "TASKRSRC": pd.DataFrame([{"proj_id": "1", "task_id": "A", "rsrc_id": "R1"}]),
        "RSRC": pd.DataFrame([{"rsrc_id": "R1", "rsrc_name": "Dummy", "level_flag": ""}]),
        "SCHEDOPTIONS": pd.DataFrame([{"proj_id": "1", "level_all_rsrc_flag": ""}]),
        "CALENDAR": pd.DataFrame([{"clndr_id": "C"}]),
    }
    c = classify_p6_model(tables, "1")
    assert c["resource_assignments"] == 1
    assert c["resource_leveling_status"] == "UNCONFIRMED"
    assert c["recommended_mode"] == "ASK BEFORE RUNNING"


def test_p6_resource_driven_answer_labels_logic_result_diagnostic_only():
    c = {"resource_assignments": 1}
    ctx = resolve_p6_analysis_context(
        c,
        "Resources drive scheduled dates / schedule is resource-levelled",
        "Use P6 Remaining Duration as scheduling input",
    )
    assert ctx["drag_mode"] == "LOGIC DRAG — DIAGNOSTIC ONLY"
    assert ctx["status"] == "WARNING"


def test_spider_1km_classifies_resource_and_productivity_model():
    raw = open("demo/1km_camino.json", "rb").read()
    data = parse_spider_json_bytes(raw)
    net = build_spider_network(data)
    c = classify_spider_model(data, net)
    assert c["resource_status"] == "PRESENT"
    assert c["resource_order_edges"] > 0
    assert "EXPLICIT PRODUCTIVITY MODEL" == c["productivity_status"]
    assert c["recommended_mode"].startswith("RESOURCE-CONSTRAINED DRAG")
