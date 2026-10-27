from __future__ import annotations

from typing import Dict
import pandas as pd


def _decode_xer(raw: bytes) -> str:
    # P6 exports are commonly Windows-1252/ANSI; UTF-8 is also seen.
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_xer_bytes(raw: bytes) -> Dict[str, pd.DataFrame]:
    text = _decode_xer(raw)
    tables: Dict[str, list] = {}
    current_table = None
    fields = None

    for line in text.splitlines():
        if not line:
            continue
        parts = line.split("\t")
        tag = parts[0]

        if tag == "%T":
            current_table = parts[1] if len(parts) > 1 else None
            fields = None
            if current_table:
                tables.setdefault(current_table, [])
        elif tag == "%F" and current_table:
            fields = parts[1:]
        elif tag == "%R" and current_table and fields:
            values = parts[1:]
            if len(values) < len(fields):
                values += [""] * (len(fields) - len(values))
            tables[current_table].append(dict(zip(fields, values[: len(fields)])))
        elif tag == "%E":
            current_table = None
            fields = None

    return {name: pd.DataFrame(rows) for name, rows in tables.items()}


def project_catalog(tables: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    project = tables.get("PROJECT", pd.DataFrame()).copy()
    if project.empty:
        return pd.DataFrame(columns=["proj_id", "proj_short_name"])
    for col in ["proj_id", "proj_short_name"]:
        if col not in project.columns:
            project[col] = ""
    return project[["proj_id", "proj_short_name"]].fillna("")


def table_for_project(tables: Dict[str, pd.DataFrame], table: str, proj_id: str) -> pd.DataFrame:
    df = tables.get(table, pd.DataFrame()).copy()
    if not df.empty and "proj_id" in df.columns:
        df = df[df["proj_id"].astype(str) == str(proj_id)].copy()
    return df


def normalize_rel_type(value: str) -> str:
    v = (value or "").upper().strip()
    return {
        "PR_FS": "FS", "FS": "FS",
        "PR_SS": "SS", "SS": "SS",
        "PR_FF": "FF", "FF": "FF",
        "PR_SF": "SF", "SF": "SF",
    }.get(v, v)


def to_float(value, default=0.0):
    try:
        if value is None or value == "" or str(value).lower() == "null":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
