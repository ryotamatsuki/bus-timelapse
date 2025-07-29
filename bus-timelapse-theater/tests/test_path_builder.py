"""
Unit tests for the path builder.

These tests focus on basic properties of the generated caches.  They
verify that the timestamps are spaced at five‑second intervals and that
the DataFrame has the expected columns.  To keep the runtime short the
tests process only a limited number of trips.
"""

import os

import pandas as pd

from modules.path_builder import build_day_cache


def test_build_day_cache_tmpdir(tmp_path):
    # Use a temporary cache directory to avoid clobbering real data
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    # Use the sample feed and a date known to be within its range
    df = build_day_cache(
        date="2025-07-10",
        gtfs_dir="data/gtfs/2025-07-03",
        cache_dir=str(cache_dir),
        limit_trips=2,
    )
    # Ensure DataFrame has correct columns
    assert list(df.columns) == ["trip_id", "timestamp", "lat", "lon"]
    # Ensure there are records
    assert len(df) > 0
    # Timestamps should be multiples of five seconds
    remainders = df["timestamp"].astype(int) % 5
    assert remainders.nunique() == 1
    assert remainders.iloc[0] == 0
