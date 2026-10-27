from collections import defaultdict
from datetime import datetime, timedelta
from math import inf
from types import SimpleNamespace

from drag_p6.models import Relationship
from drag_p6.sequential import compute_sequential_frontier


class DummyCalendar:
    day_hours = 8.0
    name = "Dummy"
    def add_work_hours(self, origin, hours):
        return origin + timedelta(hours=float(hours))


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
        calendar=DummyCalendar(),
        origin_date=datetime(2026, 1, 1),
    )


def test_sequential_frontier_advances_then_stops_at_tied_path_barrier():
    net = _network()
    df, meta = compute_sequential_frontier(net, max_stages=10, max_compression_pct=100.0)

    # A is common to both branches and is the largest first-stage gain.
    assert df.iloc[0]["Activity ID"] == "A"
    assert abs(df.iloc[0]["Stage Target Gain (h)"] - 10.0) < 1e-3

    # D is common after the branch and should also be fully removable.
    assert "D" in df["Activity ID"].tolist()

    # B can then be reduced only until it ties C (3h target gain).
    brow = df[df["Activity ID"] == "B"]
    assert not brow.empty
    assert abs(float(brow.iloc[0]["Stage Target Gain (h)"]) - 3.0) < 1e-3

    # At B=C, no single activity can move the target; simultaneous action would be required.
    assert "barrier" in meta["stop_reason"].lower()
    assert meta["complete_global_frontier"] is False
    assert meta["stages_completed"] >= 3
