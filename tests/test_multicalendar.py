from datetime import datetime, time
from drag_p6.calendar import P6Calendar
from drag_p6.multicalendar import CalendarRelationship, forward_pass, compare_counterfactuals


def cal(name, workdays):
    return P6Calendar(name, name, 8.0, {i: ([(time(8), time(16))] if i in workdays else []) for i in range(7)}, {})


def test_parallel_5x8_and_7x8_calendar():
    cals = {"W": cal("W", set(range(5))), "C": cal("C", set(range(7)))}
    starts, finishes = forward_pass(
        ["A", "B"], {"A": 8, "B": 8}, {"A": "W", "B": "C"}, cals,
        [CalendarRelationship("A", "B", "FS")],
        {"A": datetime(2026, 1, 2, 8)},
    )
    assert finishes["A"] == datetime(2026, 1, 2, 16)
    assert starts["B"] == datetime(2026, 1, 2, 16)
    assert finishes["B"] == datetime(2026, 1, 3, 16)


def test_reference_mandatory():
    try:
        compare_counterfactuals(datetime(2026, 1, 1), {}, {})
    except ValueError:
        pass
    else:
        raise AssertionError("Missing independent scenario references must fail")
