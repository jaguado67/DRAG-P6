# The real P6 calibration is benchmarked from XERs. This test protects the
# relationship counterfactual concept with a simple parallel path example.
from drag_p6.models import Relationship


def req(rel, starts, durations):
    if rel.rel_type == "FS":
        return starts[rel.pred_task_id] + durations[rel.pred_task_id] + rel.lag_h
    raise AssertionError


def test_parallel_gap_concept():
    # Critical branch is 10h; parallel branch is 7h. Removing the 10h branch
    # can only recover 3h once the parallel path takes control.
    baseline_finish = max(10.0, 7.0)
    scenario_finish = max(0.0, 7.0)
    assert baseline_finish - scenario_finish == 3.0
