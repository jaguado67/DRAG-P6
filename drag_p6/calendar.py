from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, time, date
import re
from typing import Dict, List, Tuple


DATE_FMT = "%Y-%m-%d %H:%M"


def parse_p6_datetime(value: str | None):
    if not value:
        return None
    value = str(value).strip()
    if not value:
        return None
    for fmt in (DATE_FMT, "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def excel_serial_to_date(serial: int) -> date:
    return (datetime(1899, 12, 30) + timedelta(days=int(serial))).date()


@dataclass
class P6Calendar:
    calendar_id: str
    name: str
    day_hours: float
    weekly: Dict[int, List[Tuple[time, time]]]
    exceptions: Dict[date, List[Tuple[time, time]]]

    @classmethod
    def from_row(cls, row):
        data = str(row.get("clndr_data", "") or "")
        weekly = {i: [] for i in range(7)}

        dow = data.split("(0||Exceptions()", 1)[0]
        for p6_day in range(1, 8):
            marker = f"(0||{p6_day}()"
            start = dow.find(marker)
            if start < 0:
                continue
            next_positions = [
                dow.find(f"(0||{n}()", start + 1)
                for n in range(p6_day + 1, 8)
            ]
            next_positions = [x for x in next_positions if x >= 0]
            end = min(next_positions) if next_positions else len(dow)
            segment = dow[start:end]
            intervals = []
            for s, f in re.findall(r"s\|(\d{1,2}:\d{2})\|f\|(\d{1,2}:\d{2})", segment):
                sh, sm = map(int, s.split(":"))
                fh, fm = map(int, f.split(":"))
                intervals.append((time(sh, sm), time(fh, fm)))
            # P6 day 1=Sunday, 2=Monday, ..., 7=Saturday.
            python_weekday = (p6_day + 5) % 7
            weekly[python_weekday] = intervals

        exceptions: Dict[date, List[Tuple[time, time]]] = {}
        exc_part = data.split("(0||Exceptions()", 1)[1] if "(0||Exceptions()" in data else ""
        starts = list(re.finditer(r"\(0\|\|\d+\(d\|(\d+)\)", exc_part))
        for idx, match in enumerate(starts):
            serial = int(match.group(1))
            end = starts[idx + 1].start() if idx + 1 < len(starts) else len(exc_part)
            segment = exc_part[match.start():end]
            intervals = []
            for s, f in re.findall(r"s\|(\d{1,2}:\d{2})\|f\|(\d{1,2}:\d{2})", segment):
                sh, sm = map(int, s.split(":"))
                fh, fm = map(int, f.split(":"))
                intervals.append((time(sh, sm), time(fh, fm)))
            exceptions[excel_serial_to_date(serial)] = intervals

        try:
            day_hours = float(row.get("day_hr_cnt", 8.0) or 8.0)
        except (TypeError, ValueError):
            day_hours = 8.0

        return cls(
            calendar_id=str(row.get("clndr_id", "")),
            name=str(row.get("clndr_name", "")),
            day_hours=day_hours,
            weekly=weekly,
            exceptions=exceptions,
        )

    def intervals_for_date(self, d: date):
        if d in self.exceptions:
            return self.exceptions[d]
        return self.weekly.get(d.weekday(), [])

    def work_hours_between(self, a: datetime, b: datetime) -> float:
        if a == b:
            return 0.0
        if b < a:
            return -self.work_hours_between(b, a)

        total = 0.0
        d = a.date()
        while d <= b.date():
            lo = a if d == a.date() else datetime.combine(d, time.min)
            hi = b if d == b.date() else datetime.combine(d, time.min) + timedelta(days=1)
            for st, ft in self.intervals_for_date(d):
                s = datetime.combine(d, st)
                f = datetime.combine(d, ft)
                x = max(lo, s)
                y = min(hi, f)
                if y > x:
                    total += (y - x).total_seconds() / 3600.0
            d += timedelta(days=1)
        return total

    def add_work_hours(self, start: datetime, hours: float) -> datetime:
        if abs(hours) < 1e-12:
            return start
        if hours < 0:
            return self._subtract_work_hours(start, -hours)

        remaining = float(hours)
        cursor = start
        safety = 0
        while remaining > 1e-10:
            safety += 1
            if safety > 20000:
                raise RuntimeError("Calendar iteration limit reached.")
            d = cursor.date()
            intervals = self.intervals_for_date(d)
            progressed = False
            for st, ft in intervals:
                s = datetime.combine(d, st)
                f = datetime.combine(d, ft)
                if cursor >= f:
                    continue
                seg_start = max(cursor, s)
                available = max(0.0, (f - seg_start).total_seconds() / 3600.0)
                if available <= 0:
                    continue
                progressed = True
                if remaining <= available + 1e-12:
                    return seg_start + timedelta(hours=remaining)
                remaining -= available
                cursor = f
            if not progressed or remaining > 1e-10:
                cursor = datetime.combine(d + timedelta(days=1), time.min)
        return cursor

    def _subtract_work_hours(self, start: datetime, hours: float) -> datetime:
        remaining = float(hours)
        cursor = start
        safety = 0
        while remaining > 1e-10:
            safety += 1
            if safety > 20000:
                raise RuntimeError("Calendar iteration limit reached.")
            d = cursor.date()
            intervals = list(reversed(self.intervals_for_date(d)))
            progressed = False
            for st, ft in intervals:
                s = datetime.combine(d, st)
                f = datetime.combine(d, ft)
                if cursor <= s:
                    continue
                seg_end = min(cursor, f)
                available = max(0.0, (seg_end - s).total_seconds() / 3600.0)
                if available <= 0:
                    continue
                progressed = True
                if remaining <= available + 1e-12:
                    return seg_end - timedelta(hours=remaining)
                remaining -= available
                cursor = s
            if not progressed or remaining > 1e-10:
                cursor = datetime.combine(d - timedelta(days=1), time.max.replace(microsecond=0))
        return cursor
