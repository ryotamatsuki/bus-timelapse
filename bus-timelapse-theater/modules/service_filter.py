"""
Utilities for working with GTFS service calendars.

This module exposes two helpers:

* `get_valid_service_ids(date: str, gtfs_dir: str = 'data/gtfs/LATEST') -> set[str]` –
  return a set of `service_id` values that operate on the given date by
  consulting the `calendar.txt` and `calendar_dates.txt` files from the
  specified GTFS directory.  Services are active when the date falls
  between `start_date` and `end_date` (inclusive) and the weekday flag
  (monday, tuesday, …, sunday) is set to 1.  Any exceptions listed in
  `calendar_dates.txt` for the same date are applied afterwards (1 to
  add and 2 to remove a service).

* `hhmmss_to_sec(h: str) -> int` – convert an `HH:MM:SS` string into
  an integer number of seconds.  Hours may exceed 24 (e.g. `25:15:30`)
  which will be converted to 90930 seconds.  Invalid inputs return 0.

These utilities deliberately accept a GTFS directory parameter to
facilitate testing and reuse.  If you keep your GTFS feeds in
`data/gtfs/<YYYY‑MM‑DD>` you can point `gtfs_dir` at a specific
subdirectory or to the `LATEST` symlink.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Set

import pandas as pd


def hhmmss_to_sec(h: str) -> int:
    """Convert a time string ``HH:MM:SS`` to seconds.

    The GTFS specification allows times beyond 24:00 to denote services
    operating after midnight.  For example, ``25:15:30`` becomes
    90 930 seconds.  Any parsing errors return 0.

    Parameters
    ----------
    h : str
        A time string in ``HH:MM:SS`` format.

    Returns
    -------
    int
        The number of seconds since 00:00:00.
    """
    try:
        parts = h.split(":")
        if len(parts) != 3:
            raise ValueError(f"Invalid time format: {h}")
        hours, minutes, seconds = map(int, parts)
        return hours * 3600 + minutes * 60 + seconds
    except Exception:
        # return zero on any error to avoid breaking processing
        return 0


def get_valid_service_ids(date: str, gtfs_dir: str = "data/gtfs/LATEST") -> Set[str]:
    """Return the set of ``service_id`` values active on a given date.

    This function inspects the GTFS ``calendar.txt`` and
    ``calendar_dates.txt`` files located in ``gtfs_dir`` to determine
    which services operate on the specified date.  A service in
    ``calendar.txt`` is considered active when the provided date falls
    between its ``start_date`` and ``end_date`` (inclusive) and the
    corresponding weekday flag is set to 1.  Afterwards any matching
    entries in ``calendar_dates.txt`` are applied: rows with
    ``exception_type`` 1 add a service and rows with ``exception_type`` 2
    remove it.

    Parameters
    ----------
    date : str
        A date in ``YYYY-MM-DD`` format.
    gtfs_dir : str
        Path to a directory containing the GTFS files.  Defaults to
        ``data/gtfs/LATEST`` which should point to the most recent feed.

    Returns
    -------
    set[str]
        A set of ``service_id`` strings active on the specified date.  If
        no services operate the set will be empty.
    """
    date_obj = datetime.strptime(date, "%Y-%m-%d").date()
    yyyymmdd = date_obj.strftime("%Y%m%d")

    cal_path = os.path.join(gtfs_dir, "calendar.txt")
    cal_dates_path = os.path.join(gtfs_dir, "calendar_dates.txt")

    if not os.path.exists(cal_path) or not os.path.exists(cal_dates_path):
        # missing files: return empty set
        return set()

    # load calendar; dtype spec ensures strings not ints for dates
    cal = pd.read_csv(cal_path, dtype=str)
    cal_dates = pd.read_csv(cal_dates_path, dtype=str)

    valid_services: Set[str] = set()

    # iterate calendar rows
    for row in cal.itertuples(index=False):
        # convert start_date and end_date (YYYYMMDD) to date objects
        try:
            start = datetime.strptime(row.start_date, "%Y%m%d").date()
            end = datetime.strptime(row.end_date, "%Y%m%d").date()
        except Exception:
            continue
        if not (start <= date_obj <= end):
            continue
        # determine day-of-week flag (Monday=0)
        weekday_flags = {
            0: row.monday,
            1: row.tuesday,
            2: row.wednesday,
            3: row.thursday,
            4: row.friday,
            5: row.saturday,
            6: row.sunday,
        }
        try:
            if int(weekday_flags[date_obj.weekday()]) == 1:
                valid_services.add(row.service_id)
        except Exception:
            # if flags are missing or non‑numeric skip
            continue

    # apply calendar dates overrides
    for row in cal_dates.itertuples(index=False):
        rec_date = str(row.date)
        if rec_date != yyyymmdd:
            continue
        # apply exception
        try:
            exception_type = int(row.exception_type)
        except Exception:
            continue
        sid = row.service_id
        if exception_type == 1:
            valid_services.add(sid)
        elif exception_type == 2 and sid in valid_services:
            valid_services.remove(sid)

    return valid_services