from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Relationship:
    pred_task_id: str
    succ_task_id: str
    rel_type: str
    lag_h: float = 0.0
    pred_proj_id: str = ""
    succ_proj_id: str = ""
