from datetime import datetime
from drag_p6.calendar import P6Calendar


def test_simple_work_calendar():
    row = {
        "clndr_id": "1", "clndr_name": "5x8", "day_hr_cnt": "8",
        "clndr_data": "(0||CalendarData()((0||DaysOfWeek()((0||1()())(0||2()((0||0(s|7:00|f|12:00)())(0||1(s|13:00|f|16:00)())))(0||3()((0||0(s|7:00|f|12:00)())(0||1(s|13:00|f|16:00)())))(0||4()((0||0(s|7:00|f|12:00)())(0||1(s|13:00|f|16:00)())))(0||5()((0||0(s|7:00|f|12:00)())(0||1(s|13:00|f|16:00)())))(0||6()((0||0(s|7:00|f|12:00)())(0||1(s|13:00|f|16:00)())))(0||7()())))(0||Exceptions()())))"
    }
    cal = P6Calendar.from_row(row)
    a = datetime(2026, 9, 7, 7, 0)   # Monday
    b = datetime(2026, 9, 8, 16, 0)  # Tuesday
    assert abs(cal.work_hours_between(a, b) - 16.0) < 1e-9
