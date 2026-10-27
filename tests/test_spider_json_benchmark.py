from pathlib import Path

from drag_p6.spider_json import parse_spider_json_bytes, build_spider_network, schedule_spider
from drag_p6.spider_benchmark import compare_spider_drag


def test_spider_demo_if_available():
    path = Path(__file__).resolve().parents[1] / "demo" / "1km_camino.json"
    if not path.exists():
        return
    data = parse_spider_json_bytes(path.read_bytes())
    net = build_spider_network(data)
    _, finish, _ = schedule_spider(net)
    assert net.target_code == "fin"
    assert abs(net.reconciliation["target_error_h"]) < 0.01
    results, meta = compare_spider_drag(net)
    assert meta["reference_activities"] >= 1
    drl = results[results["Activity ID"] == "drl"].iloc[0]
    assert abs(float(drl["DRAG-P6 (h)"]) - float(drl["Spider DRAG (h)"])) < 0.01
