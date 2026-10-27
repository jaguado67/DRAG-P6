"""Initial regression tests for DRED/cost scenario evaluator."""
import pytest

from drag_p6.dred_cost import DredCostScenario, evaluate_dred_cost


class FakeNetwork:
    baseline_durations = {"A": 10.0, "B": 8.0}

# Patch the scheduling boundary: these tests verify valuation and scenario
# contracts, not correctness of the underlying P6 CPM engine.
def fake_schedule(network, overrides=None):
    d = dict(network.baseline_durations)
    d.update(overrides or {})
    return {}, {"A": d["A"], "B": d["B"]}, d


def test_dred_competes_with_another_finish_path(monkeypatch):
    monkeypatch.setattr("drag_p6.dred_cost.schedule", fake_schedule)
    result = evaluate_dred_cost(
        FakeNetwork(), DredCostScenario("A", 4.0, 100.0, 150.0)
    )
    assert result["duration_reduction_h"] == 6.0
    assert result["target_gain_h_signed"] == 2.0
    assert result["gross_time_value"] == 200.0
    assert result["net_economic_value"] == 50.0


def test_no_cost_estimate_no_monetary_claim(monkeypatch):
    monkeypatch.setattr("drag_p6.dred_cost.schedule", fake_schedule)
    result = evaluate_dred_cost(FakeNetwork(), DredCostScenario("A", 4.0))
    assert result["gross_time_value"] is None
    assert result["net_economic_value"] is None


@pytest.mark.parametrize("dred", [-1.0, 11.0, float("nan"), float("inf")])
def test_reject_invalid_dred(monkeypatch, dred):
    monkeypatch.setattr("drag_p6.dred_cost.schedule", fake_schedule)
    with pytest.raises(ValueError):
        evaluate_dred_cost(FakeNetwork(), DredCostScenario("A", dred))


def test_reject_unknown_target(monkeypatch):
    monkeypatch.setattr("drag_p6.dred_cost.schedule", fake_schedule)
    with pytest.raises(ValueError):
        evaluate_dred_cost(FakeNetwork(), DredCostScenario("A", 4), "missing")
