
"""
Streamlit front end for the Ehime Bus Time‑Lapse Theater.

This application allows users to select a date, adjust the playback
speed and choose between light and dark map themes.  When run the
first time for a given date the application invokes
``build_day_cache`` to produce a 5‑second resolution position cache
based on the GTFS timetable.  Afterwards the positions are grouped
into per‑trip lists and visualised using a `TripsLayer` from Pydeck.

To start the app locally use:

```bash
streamlit run app.py
```

See the README.md for further details.
"""

from __future__ import annotations

import os
import time
from datetime import date as date_type
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

from modules.path_builder import build_day_cache


def _load_cache(date_str: str, gtfs_dir: str) -> pd.DataFrame:
    """Load a bus position cache from disk, building it if necessary."""
    return build_day_cache(date_str, gtfs_dir=gtfs_dir)


def _restructure_for_tripslayer(df: pd.DataFrame) -> List[Dict]:
    """Convert a flat DataFrame into a list of dicts for TripsLayer."""
    trips: List[Dict] = []
    if df.empty:
        return trips

    # Use a fixed color for now to simplify debugging
    fixed_color = [253, 128, 93] # Orange

    for trip_id, grp in df.groupby("trip_id"):
        grp = grp.sort_values("timestamp")
        coords = grp[["lon", "lat"]].values.tolist()
        ts = grp["timestamp"].astype(int).tolist()
        trips.append({"path": coords, "timestamps": ts, "trip_id": trip_id, "color": fixed_color})
    return trips


def main() -> None:
    st.set_page_config(page_title="Ehime Bus Theater", layout="wide")
    st.title("Ehime Bus Time‑Lapse Theater")

    # --- Path setup ---
    # Get the directory of the current script
    script_dir = Path(__file__).parent
    # Set GTFS directory relative to the script directory
    gtfs_dir = script_dir / "data" / "gtfs" / "2025-07-03"

    fixed_date_str = "2025-07-15" # 固定の日付

    # --- Sidebar controls ---
    st.sidebar.header("表示設定")

    # 日付選択UIを削除し、固定の日付を使用
    st.sidebar.info(f"表示日付: {fixed_date_str}")

    speed_option = st.sidebar.select_slider(
        "再生速度 (秒ステップ)", options=[1, 5, 10, 25, 60], value=60
    )
    theme = st.sidebar.radio("地図テーマ", options=["Light", "Dark"], index=1)

    # Cache building/loading
    with st.spinner(f"{fixed_date_str} のキャッシュデータを生成・読込中..."):
        df = _load_cache(fixed_date_str, gtfs_dir)

    if df.empty:
        st.warning("選択した日に運行するサービスはありません。別の日付を選んでください。")
        return

    # --- Route Selection UI ---
    routes_df = pd.read_csv(os.path.join(gtfs_dir, "routes.txt"), dtype={'route_id': str})
    routes_df['display_name'] = routes_df['route_long_name'] + " (" + routes_df['route_short_name'].fillna('') + ")"
    route_options = routes_df.set_index('route_id')['display_name'].to_dict()

    selected_route_ids = st.sidebar.multiselect(
        "表示する路線を選択",
        options=list(route_options.keys()),
        format_func=lambda x: route_options[x],
        default=['10025'] # デフォルトを10025のみに設定
    )

    # 決定ボタンを追加
    apply_filter_button = st.sidebar.button("決定")

    # フィルタリングを適用するトリガー
    # 初回ロード時、または決定ボタンが押された場合にフィルタリングを適用
    if 'filtered_df' not in st.session_state or apply_filter_button:
        st.session_state.filtered_df = df[df['route_id'].isin(selected_route_ids)]

    df = st.session_state.filtered_df

    if not selected_route_ids:
        st.warning("路線を1つ以上選択してください。")
        st.stop()

    if df.empty:
        st.warning("選択された路線は、この日に運行データがありません。")
        return

    st.success(f"{fixed_date_str} の {len(selected_route_ids)} 路線を読み込みました。(軌跡データ: {len(df):,}行)")

    # --- Map and Time Slider ---
    trips_data = _restructure_for_tripslayer(df)

    lat_center = float(df["lat"].mean())
    lon_center = float(df["lon"].mean())

    current_time_header = st.empty()
    min_ts = int(df["timestamp"].min())
    max_ts = int(df["timestamp"].max())

    current_time = st.slider(
        "時刻",
        min_value=min_ts,
        max_value=max_ts,
        value=min_ts,
        step=speed_option,
    )
    h, m, s = current_time // 3600, (current_time % 3600) // 60, current_time % 60
    current_time_header.metric("現在時刻", f"{h:02d}:{m:02d}:{s:02d}")

    auto_play = st.checkbox("自動再生", value=True) # デフォルトをTrueに変更

    layer = pdk.Layer(
        "TripsLayer",
        data=trips_data,
        get_path="path",
        get_timestamps="timestamps",
        get_color="color",
        width_min_pixels=2.5,
        trail_length=120,
        current_time=current_time,
    )

    map_style = (
        "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json"
        if theme == "Light"
        else "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
    )
    view_state = pdk.ViewState(
        latitude=lat_center,
        longitude=lon_center,
        zoom=12,
        pitch=45,
        bearing=0,
    )
    deck = pdk.Deck(layers=[layer], initial_view_state=view_state, map_style=map_style)

    map_container = st.empty()
    map_container.pydeck_chart(deck)

    if auto_play:
        for ts in range(current_time, max_ts + 1, speed_option):
            layer.current_time = ts
            h, m, s = ts // 3600, (ts % 3600) // 60, ts % 60
            current_time_header.metric("現在時刻", f"{h:02d}:{m:02d}:{s:02d}")
            # st.slider("時刻", min_value=min_ts, max_value=max_ts, value=ts, step=speed_option, disabled=True) # 削除
            deck.layers = [layer]
            map_container.pydeck_chart(deck)
            time.sleep(0.001) # 高速化
        st.button("リセット")


if __name__ == "__main__":
    main()
