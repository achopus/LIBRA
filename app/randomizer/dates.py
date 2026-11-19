"""Calendar: real dates for every subject and period, and daily sheets ("who gets what today").

Period k of a subject is planned for start + (k - 1) × days_between. With skip_weekends, a date
that falls on a Saturday, Sunday or listed holiday moves to the next working day (later periods
keep their planned dates, so one holiday does not shift the whole study).
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from .export import long_format
from .solver import Result


def parse_date(text) -> date | None:
    if text is None or (isinstance(text, float) and pd.isna(text)) or str(text).strip() == "":
        return None
    try:
        return pd.to_datetime(str(text).strip(), dayfirst=False).date()
    except (ValueError, TypeError):
        return None


def working_day(d: date, skip_weekends: bool, holidays: set[date]) -> date:
    while (skip_weekends and d.weekday() >= 5) or d in holidays:
        d += timedelta(days=1)
    return d


def check(cal: dict, res: Result | None = None) -> list[str]:
    """Problems with the calendar settings, in plain words (empty = fine)."""
    out = []
    if parse_date(cal.get("start_date")) is None and not cal.get("start_column"):
        out.append("Enter a start date (for example 2026-11-02).")
    try:
        if int(cal.get("days_between", 7)) < 1:
            out.append("Days between periods must be at least 1.")
    except (TypeError, ValueError):
        out.append("Days between periods must be a whole number.")
    bad = [h for h in cal.get("holidays", []) if parse_date(h) is None]
    if bad:
        out.append(f"Unreadable holiday dates: {', '.join(map(str, bad[:3]))}.")
    col = cal.get("start_column")
    if res is not None and col:
        if col not in res.schedule.columns:
            out.append(f"The start date column '{col}' is not in the schedule.")
        else:
            missing = res.schedule[col].map(parse_date).isna()
            if missing.any() and parse_date(cal.get("start_date")) is None:
                out.append(f"{int(missing.sum())} rows have no readable date in '{col}' and there is no "
                           f"default start date.")
    return out


def dated_schedule(res: Result, cal: dict, blinded: bool = False) -> pd.DataFrame:
    """Long format (one row per subject and period) with a Date and Weekday column."""
    spec = res.spec
    df = long_format(res)
    per = spec.period_name
    start = parse_date(cal.get("start_date"))
    step = int(cal.get("days_between", 7))
    skip = bool(cal.get("skip_weekends", True))
    hol = {d for d in (parse_date(h) for h in cal.get("holidays", [])) if d}
    col = cal.get("start_column") or None
    own = res.schedule.set_index(res.schedule[spec.id_column].astype(str))[col].map(parse_date) \
        if col and col in res.schedule.columns else None
    dates = []
    for sid, k in zip(df[spec.id_column].astype(str), df[per]):
        s0 = own.get(sid) if own is not None else None
        s0 = s0 or start
        dates.append(working_day(s0 + timedelta(days=step * (int(k) - 1)), skip, hol) if s0 else None)
    df.insert(0, "Date", pd.to_datetime(pd.Series(dates, dtype=object)).dt.date)
    df.insert(1, "Weekday", pd.to_datetime(df["Date"]).dt.day_name())
    if blinded and "Code" in df.columns:
        df = df.drop(columns=["Treatment"])
    return df.sort_values(["Date", spec.id_column, per], kind="stable").reset_index(drop=True)


def daily_sheets(res: Result, cal: dict, blinded: bool = False) -> dict[date, pd.DataFrame]:
    """One table per date: the subjects treated that day and their treatment (or code)."""
    df = dated_schedule(res, cal, blinded)
    df = df[df["Date"].notna()]
    keep = [c for c in df.columns if c not in ("Weekday", "Date")]
    return {d: g[keep].reset_index(drop=True) for d, g in df.groupby("Date", sort=True)}
