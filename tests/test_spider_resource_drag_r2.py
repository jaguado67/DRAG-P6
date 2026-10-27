from pathlib import Path

from drag_p6.spider_json import parse_spider_json_bytes, build_spider_network
from drag_p6.spider_benchmark import compare_spider_drag


def test_spider_1km_positive_drag_matches_resource_aware():
    root = Path(__file__).resolve().parents[1]
    data = parse_spider_json_bytes((root / "demo" / "1km_camino.json").read_bytes())
    net = build_spider_network(data)
    assert net.reconciliation["status"] == "PASS"
    df, meta = compare_spider_drag(net, tolerance_h=0.01)
    assert meta["positive_reference_activities"] == 9
    assert meta["positive_matches"] == 9
    assert meta["positive_mae_h"] < 0.001
    neg = df[df["Spider DRAG (h)"] < 0]
    assert len(neg) == 1
    assert neg.iloc[0]["Activity ID"] == "pnd"
