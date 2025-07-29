"""
Generate per‑trip position traces from GTFS timetable information.

This module contains a single entry point, :func:`build_day_cache`, which
accepts a date string and produces a Feather file containing the
latitude/longitude positions of every bus in the feed sampled every
five seconds.  The implementation relies only on the basic GTFS
tables—`trips.txt`, `stop_times.txt` and `stops.txt`—and therefore
falls back to straight‑line interpolation between consecutive stops if
no detailed shape geometry is available.  The output is stored in
``data/cache/bus_trails_<YYYY‑MM‑DD>.feather`` by default.

Example usage:

```
from modules.path_builder import build_day_cache
build_day_cache("2025-07-10")
```

which will read the GTFS feed under ``data/gtfs/LATEST``, build the
cache and return a ``pandas.DataFrame``.
"""

from __future__ import annotations

import argparse
import os
from typing import Iterable, List, Tuple

import numpy as np
import pandas as pd

from .service_filter import get_valid_service_ids, hhmmss_to_sec


def _interpolate_segment(
    trip_id: str,
    t_a: int,
    t_b: int,
    lat_a: float,
    lon_a: float,
    lat_b: float,
    lon_b: float,
    step: int = 5,
) -> List[Tuple[str, int, float, float]]:
    """Interpolate a single stop‑to‑stop segment.

    Given start/end times and coordinates this helper returns a list of
    tuples ``(trip_id, timestamp, lat, lon)`` sampled every ``step``
    seconds between ``t_a`` and ``t_b`` inclusive.  If ``t_b <= t_a``
    an empty list is returned.

    Parameters
    ----------
    trip_id : str
        Identifier of the trip.
    t_a, t_b : int
        Start and end timestamps (seconds since midnight).
    lat_a, lon_a, lat_b, lon_b : float
        Starting and ending coordinates.
    step : int, optional
        Sampling interval in seconds, by default 5.

    Returns
    -------
    list of tuple
        A list of rows describing the interpolated positions.
    """
    if t_b <= t_a:
        return []
    duration = t_b - t_a
    num_steps = (duration // step) + 1
    timestamps = np.arange(t_a, t_b + 1, step, dtype=int)
    # handle potential rounding so last timestamp equals t_b
    if timestamps[-1] != t_b:
        timestamps = np.append(timestamps, t_b)
    # linear interpolation
    ratios = (timestamps - t_a) / float(duration)
    lats = lat_a + ratios * (lat_b - lat_a)
    lons = lon_a + ratios * (lon_b - lon_a)
    return [
        (trip_id, int(ts), float(lat), float(lon))
        for ts, lat, lon in zip(timestamps, lats, lons)
    ]


def build_day_cache(
    date: str,
    gtfs_dir: str = "data/gtfs/LATEST",
    cache_dir: str = "data/cache",
    limit_trips: int | None = None,
) -> pd.DataFrame:
    """Build a per‑trip position cache for a single day.

    The function loads the GTFS tables from ``gtfs_dir``, filters the
    trips by those whose service is active on ``date``, interpolates
    between consecutive stops at five‑second intervals and writes the
    result to a Feather file in ``cache_dir``.  The returned
    ``pandas.DataFrame`` has columns ``['trip_id','timestamp','lat','lon']``.

    Parameters
    ----------
    date : str
        Target date in ``YYYY‑MM‑DD`` format.
    gtfs_dir : str, optional
        Directory containing GTFS files.  Defaults to
        ``data/gtfs/LATEST`` which should be a symlink to the most
        recent feed.
    cache_dir : str, optional
        Directory where the Feather file will be written.  Defaults to
        ``data/cache``.  The directory is created if necessary.
    limit_trips : int or None, optional
        If given, only the first ``limit_trips`` trips will be
        processed.  This parameter exists for testing and profiling.

    Returns
    -------
    pandas.DataFrame
        A DataFrame containing the interpolated positions.  If no
        services operate on the date an empty DataFrame is returned.
    """
    # Determine cache path
    os.makedirs(cache_dir, exist_ok=True)
    out_path = os.path.join(cache_dir, f"bus_trails_{date}.feather")

    # Filter services active on this date
    service_ids = get_valid_service_ids(date, gtfs_dir=gtfs_dir)
    if not service_ids:
        # create and save empty frame
        empty_df = pd.DataFrame(columns=["trip_id", "timestamp", "lat", "lon"])
        empty_df.to_feather(out_path)
        return empty_df

    # Load GTFS tables
    trips_path = os.path.join(gtfs_dir, "trips.txt")
    stop_times_path = os.path.join(gtfs_dir, "stop_times.txt")
    stops_path = os.path.join(gtfs_dir, "stops.txt")

    # Use dtype specification to ensure numeric ids remain strings
    trips = pd.read_csv(trips_path, dtype=str)
    stop_times = pd.read_csv(stop_times_path, dtype=str)
    stops = pd.read_csv(stops_path, dtype={"stop_id": str, "stop_lat": float, "stop_lon": float})

    # Filter trips by service_id
    trips = trips[trips["service_id"].isin(service_ids)]
    if limit_trips is not None:
        trips = trips.head(limit_trips)

    valid_trip_ids = set(trips["trip_id"].unique())
    # Filter stop_times
    stop_times = stop_times[stop_times["trip_id"].isin(valid_trip_ids)]
    # Sort by trip_id then stop_sequence (cast stop_sequence to int)
    stop_times["stop_sequence"] = stop_times["stop_sequence"].astype(int)
    stop_times = stop_times.sort_values(["trip_id", "stop_sequence"])

    # Map stops to coordinates
    stop_coords = stops.set_index("stop_id")[["stop_lat", "stop_lon"]].to_dict("index")

    records: List[Tuple[str, int, float, float]] = []

    # Group by trip_id
    for trip_id, group in stop_times.groupby("trip_id"):
        group = group.reset_index(drop=True)
        print(f"DEBUG: Processing trip_id: {trip_id}, group length: {len(group)}")
        # iterate over consecutive stops
        for idx in range(len(group) - 1):
            row_a = group.iloc[idx]
            row_b = group.iloc[idx + 1]
            # parse times
            t_a = hhmmss_to_sec(str(row_a["departure_time"]))
            t_b = hhmmss_to_sec(str(row_b["departure_time"]))
            print(f"DEBUG:   Segment {idx}: t_a={t_a}, t_b={t_b}, stop_a={row_a['stop_id']}, stop_b={row_b['stop_id']}")
            # skip invalid or zero duration segments
            if t_b <= t_a:
                print(f"DEBUG:     Skipping segment due to t_b <= t_a")
                continue
            # coordinates
            coord_a = stop_coords.get(row_a["stop_id"])
            coord_b = stop_coords.get(row_b["stop_id"])
            if not coord_a or not coord_b:
                print(f"DEBUG:     Skipping segment due to missing coordinates (stop_a: {row_a['stop_id']}, found: {bool(coord_a)}; stop_b: {row_b['stop_id']}, found: {bool(coord_b)})")
                continue
            lat_a, lon_a = coord_a["stop_lat"], coord_a["stop_lon"]
            lat_b, lon_b = coord_b["stop_lat"], coord_b["stop_lon"]
            seg_records = _interpolate_segment(
                trip_id=trip_id,
                t_a=t_a,
                t_b=t_b,
                lat_a=lat_a,
                lon_a=lon_a,
                lat_b=lat_b,
                lon_b=lon_b,
                step=5,
            )
            print(f"DEBUG:     Interpolated {len(seg_records)} records for segment")
            records.extend(seg_records)
    print(f"DEBUG: Final records count before DataFrame creation: {len(records)}")

    # Create DataFrame and join with trips to get route_id
    df = pd.DataFrame(records, columns=["trip_id", "timestamp", "lat", "lon"])
    if not df.empty:
        # Ensure trip_id types match for merging
        trips["trip_id"] = trips["trip_id"].astype(df["trip_id"].dtype)
        df = pd.merge(df, trips[["trip_id", "route_id"]], on="trip_id", how="left")
    # Save to feather (use lz4 compression if available).  If the optional
    # dependency ``pyarrow`` is unavailable or another error occurs,
    # degrade gracefully by writing a CSV file instead.  The CSV name
    # matches the feather name but uses a .csv extension.  Returning
    # the DataFrame allows callers to continue even if writing fails.
    try:
        try:
            df.to_feather(out_path, compression="lz4")
        except Exception:
            # fallback to default compression
            df.to_feather(out_path)
    except ImportError:
        # missing pyarrow; write CSV as fallback
        csv_path = out_path.replace(".feather", ".csv")
        df.to_csv(csv_path, index=False)
    except Exception:
        # final fallback: write CSV
        csv_path = out_path.replace(".feather", ".csv")
        df.to_csv(csv_path, index=False)
    return df


def main(argv: Iterable[str] | None = None) -> int:
    """Command‑line entry point for building a daily cache.

    This function can be invoked via ``python -m modules.path_builder`` or
    directly as a script.  It accepts a `--date` argument and optional
    `--gtfs-dir` and `--cache-dir` arguments.  Use the `--limit-trips`
    option to restrict the number of trips processed (useful for
    debugging).
    """
    parser = argparse.ArgumentParser(description="Build bus position cache for a given date.")
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD format")
    parser.add_argument("--gtfs-dir", default="data/gtfs/LATEST", help="Path to GTFS feed directory")
    parser.add_argument("--cache-dir", default="data/cache", help="Path to cache directory")
    parser.add_argument("--limit-trips", type=int, default=None, help="Limit number of trips (debugging)")
    args = parser.parse_args(argv)

    build_day_cache(
        date=args.date,
        gtfs_dir=args.gtfs_dir,
        cache_dir=args.cache_dir,
        limit_trips=args.limit_trips,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())