from collections import defaultdict
from datetime import datetime
from math import inf
from types import SimpleNamespace

from drag_p6.drag import compute_drag
from drag_p6.models import Relationship


def _node(activity_id):
    return {
        "activity_id": activity_id,
        "name": activity_id,
        "wbs_path": "DEMO / AREA / LOC",
        "status": "TK_NotStart",
        "task_type": "TT_Task",
        "p6_total_float_h": 0.0,
        "p6_start_dt": datetime(2026, 1, 1),
        "p6_finish_dt": datetime(2026, 1, 1),
    }


def _network():
    # A(10) -> B(10) -> D(5) = 25
    # A(10) -> C(7)  -> D(5) = 22
    rels = [
        Relationship("A", "B", "FS", 0.0),
        Relationship("A", "C", "FS", 0.0),
        Relationship("B", "D", "FS", 0.0),
        Relationship("C", "D", "FS", 0.0),
    ]
    incoming = defaultdict(list)
    outgoing = defaultdict(list)
    for r in rels:
        incoming[r.succ_task_id].append(r)
        outgoing[r.pred_task_id].append(r)

    return SimpleNamespace(
        baseline_durations={"A": 10.0, "B": 10.0, "C": 7.0, "D": 5.0},
        anchors={"A": 0.0, "B": -inf, "C": -inf, "D": -inf},
        order=["A", "B", "C", "D"],
        incoming=incoming,
        outgoing=outgoing,
        nodes={k: _node(k) for k in ["A", "B", "C", "D"]},
    )


def test_build3_detects_parallel_replacement_path():
    net = _network()
    df, meta = compute_drag(net)
    row_b = df[df["Activity ID"] == "B"].iloc[0]

    assert row_b["DRAG (h)"] == 3.0
    assert row_b["Transmission"] == "Partial"
    assert row_b["DRAG Transmission Ratio"] == 0.3
    assert row_b["Compression Headroom (h)"] == 7.0
    assert row_b["Switch Threshold (h)"] == 3.0
    assert row_b["Switch Threshold Status"] == "Switch occurs before RD reaches zero"
    assert bool(row_b["Controlling Path Changed"])
    assert row_b["Path Outcome"] == "Replacement Path"
    assert str(row_b["Replacement Controlling Activity"]).startswith("C —")
    assert row_b["Path Switch"] == "C → D"
    assert meta["partial_transmission_activities"] == 1
    assert meta["max_individual_drag_h"] == 10.0


def test_full_transmission_has_zero_headroom_and_no_finite_switch_threshold():
    net = _network()
    df, _ = compute_drag(net)
    row_a = df[df["Activity ID"] == "A"].iloc[0]

    assert row_a["Transmission"] == "Full"
    assert row_a["Path Outcome"] == "Same Path"
    assert row_a["DRAG Transmission Ratio"] == 1.0
    assert row_a["Compression Headroom (h)"] == 0.0
    assert row_a["Switch Threshold (h)"] != row_a["Switch Threshold (h)"]  # NaN
    assert row_a["Switch Threshold Status"] == "No switch within current RD"
