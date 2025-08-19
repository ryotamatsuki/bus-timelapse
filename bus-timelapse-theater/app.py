"""
Streamlit front end for the Ehime Bus Time‑Lapse Theater.

This application allows users to select a date, adjust the playback
speed and choose between light and dark map themes. When run the
first time for a given date the application invokes
``build_day_cache`` to produce a 5‑second resolution position cache
based on the GTFS timetable. Afterwards the positions are grouped
into per‑trip lists and visualised using a `TripsLayer` from Pydeck.

To start the app locally use:

```bash
streamlit run app.py
```

See the README.md for further details.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from string import Template
from typing import Dict, List

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from modules.path_builder import build_day_cache


# --- Data Loading and Caching ---

@st.cache_data(show_spinner=False, persist=True)
def _load_cache(date_str: str, gtfs_dir: str) -> pd.DataFrame:
    """Load a bus position cache from disk, building it if necessary."""
    return build_day_cache(date_str, gtfs_dir=str(gtfs_dir))

@st.cache_data(show_spinner=False)
def load_routes(gtfs_dir: str) -> pd.DataFrame:
    # Path型に合わせて結合（strでも動くがPathの方が安全）
    routes_path = (Path(gtfs_dir) / "routes.txt")
    return pd.read_csv(routes_path, dtype={'route_id': str})

def thin_by_time(df: pd.DataFrame, step_sec: int) -> pd.DataFrame:
    # 各 trip 内で相対時刻に変換して % step == 0 の行だけ残す
    df = df.sort_values(["trip_id", "timestamp"])
    df["t0"] = df.groupby("trip_id")["timestamp"].transform("min")
    keep = ((df["timestamp"] - df["t0"]) % step_sec) == 0
    return df.loc[keep, ["trip_id","lat","lon","timestamp","route_id"]]

def drop_near_duplicates(df: pd.DataFrame, eps_m: float = 3.0) -> pd.DataFrame:
    # ほぼ同一点が連続する場合を除去（水平距離eps_m未満）
    R = 6371000.0
    def hav(lat1, lon1, lat2, lon2):
        dlat=math.radians(lat2-lat1); dlon=math.radians(lon2-lon1)
        la1, lo1 = math.radians(lat1), math.radians(lon1)
        x = math.sin(dlat/2)**2 + math.cos(la1)*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
        return 2*R*math.atan2(math.sqrt(x), math.sqrt(1-x))
    
    kept_indices = []
    for trip_id, g in df.groupby("trip_id"):
        g = g.sort_values("timestamp") # 時系列でソート
        prev_row = None
        # itertuples(index=True) で高速化
        for row in g.itertuples(index=True):
            if prev_row is None or hav(prev_row.lat, prev_row.lon, row.lat, row.lon) >= eps_m:
                kept_indices.append(row.Index)
                prev_row = row
    return df.loc[kept_indices].reset_index(drop=True)

# 追加: カラーパレット（ColorBrewer系）
PALETTE = [
    [228,26,28],[55,126,184],[77,175,74],[152,78,163],[255,127,0],
    [255,255,51],[166,86,40],[247,129,191],[153,153,153],[2,129,138]
]

@st.cache_data(show_spinner=False)
def to_trips_payload(df: pd.DataFrame, route_colors: dict[str, list[int]]) -> list[dict]:
    trips = []
    for trip_id, g in df.groupby("trip_id", sort=False):
        g = g.sort_values("timestamp")
        rid = g["route_id"].iloc[0]
        trips.append({
            "trip_id": trip_id,
            "route_id": rid,  # ← 追加
            "path": g[["lon","lat"]].to_numpy().tolist(),
            "timestamps": g["timestamp"].to_numpy(dtype=np.int32).tolist(),
            "color": route_colors[rid],  # ← ルート別の色
        })
    return trips

def render_trips_in_browser(trips_data, routes_ui, view_state, map_style, min_ts, max_ts, step, trail_length=120, fps=24):
    html_tmpl = Template(r"""
    <div id="map-wrap" style="position:relative;height:80vh;width:100%;">
      <div id="deck-container" style="position:absolute;inset:0;"></div>

      <!-- 固定凡例パネル（右上） -->
      <div id="legend-panel" style="
          position:absolute;top:12px;right:12px;z-index:10;
          width:340px;max-height:70vh;overflow:auto;
          background:rgba(255,255,255,0.92);backdrop-filter:saturate(1.2) blur(3px);
          border:1px solid rgba(0,0,0,0.1); border-radius:10px; box-shadow:0 4px 16px rgba(0,0,0,0.15);
          font-family:system-ui, -apple-system, Segoe UI, Roboto, sans-serif; color:#222;">
        <div style="display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid rgba(0,0,0,0.06);">
          <strong style="font-size:14px;">路線フィルタ</strong>
          <div style="margin-left:auto;display:flex;gap:6px;">
            <button id="btn-all"  style="padding:4px 8px;border:1px solid #ddd;border-radius:6px;background:#f7f7f7;cursor:pointer;">すべてON</button>
            <button id="btn-none" style="padding:4px 8px;border:1px solid #ddd;border-radius:6px;background:#f7f7f7;cursor:pointer;">すべてOFF</button>
          </div>
        </div>
        <div style="padding:10px 12px;border-bottom:1px solid rgba(0,0,0,0.06);display:flex;gap:8px;">
          <input id="route-search" type="search" placeholder="路線名やIDで検索" 
                 style="flex:1;padding:6px 8px;border:1px solid #ddd;border-radius:6px;"/>
        </div>
        <div id="route-list" style="padding:8px 12px;display:flex;flex-direction:column;gap:6px;"></div>
        <div id="legend-footer" style="padding:8px 12px;border-top:1px solid rgba(0,0,0,0.06);font-size:12px;color:#555;">
          <span id="count"></span>
        </div>
      </div>
    </div>

    <script src="https://unpkg.com/deck.gl@8.9.27/dist.min.js"></script>
    <script src="https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.js"></script>
    <link href="https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.css" rel="stylesheet"/>

    <script>
      // データ
      const trips = $TRIPS;     // [{trip_id, route_id, path, timestamps, color}]
      const routes = $ROUTES;   // [{route_id, name, color}]
      const initialViewState = $VIEW;
      const MIN_TS = $MIN_TS;
      const MAX_TS = $MAX_TS;
      let   STEP   = $STEP;
      let   FPS    = $FPS;
      const TRAIL  = $TRAIL;

      const deckgl = new deck.DeckGL({
        container: 'deck-container',
        controller: true,
        initialViewState,
        map: maplibregl,
        mapStyle: "$MAP_STYLE"
      });

      // 状態：有効化されたroute_id集合（初期は全ON）
      let enabled = new Set(routes.map(r => r.route_id));
      let currentTime = MIN_TS;
      let filteredRoutes = routes.slice(); // 検索後の表示対象

      // UI構築
      const listEl = document.getElementById('route-list');
      const searchEl = document.getElementById('route-search');
      const countEl = document.getElementById('count');

      function renderList() {
        listEl.innerHTML = '';
        filteredRoutes.forEach(r => {
          const id = 'route-' + r.route_id;
          const row = document.createElement('label');
          row.style.display = 'flex';
          row.style.alignItems = 'center';
          row.style.gap = '8px';
          row.style.cursor = 'pointer';
          row.innerHTML = `
            <input type="checkbox" id="${id}" ${enabled.has(r.route_id) ? 'checked' : ''} />
            <span style="width:12px;height:12px;border-radius:2px;display:inline-block;background:rgb(${r.color.join(',')});"></span>
            <span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${r.name}">${r.name}</span>
            <span style="margin-left:auto;color:#999;font-size:11px;">${r.route_id}</span>
          `;
          listEl.appendChild(row);
          row.querySelector('input').addEventListener('change', (e) => {
            if (e.target.checked) enabled.add(r.route_id); else enabled.delete(r.route_id);
            updateVisibleTrips();
          });
        });
        updateCount();
      }

      function updateCount() {
        countEl.textContent = `選択 ${enabled.size} / 総数 ${routes.length}` +
          (filteredRoutes.length !== routes.length ? `（表示中 ${filteredRoutes.length}）` : '');
      }

      function doSearch(text) {
        const q = (text || '').trim().toLowerCase();
        filteredRoutes = routes.filter(r =>
          !q || r.name.toLowerCase().includes(q) || String(r.route_id).toLowerCase().includes(q)
        );
        renderList();
      }

      document.getElementById('btn-all').addEventListener('click', () => {
        filteredRoutes.forEach(r => enabled.add(r.route_id));  // 表示中（=検索結果）だけON
        renderList();
        updateVisibleTrips();
      });
      document.getElementById('btn-none').addEventListener('click', () => {
        filteredRoutes.forEach(r => enabled.delete(r.route_id)); // 表示中だけOFF
        renderList();
        updateVisibleTrips();
      });
      searchEl.addEventListener('input', (e) => doSearch(e.target.value));

      function makeLayer(ct, data) {
        return new deck.TripsLayer({
          id: 'trips',
          data,
          getPath: d => d.path,
          getTimestamps: d => d.timestamps,
          getColor: d => d.color,
          widthMinPixels: 2.5,
          trailLength: TRAIL,
          currentTime: ct,
          pickable: false
        });
      }

      function updateVisibleTrips() {
        const visibleTrips = trips.filter(t => enabled.has(t.route_id));
        deckgl.setProps({ layers: [makeLayer(currentTime, visibleTrips)] });
      }

      // 初期描画
      doSearch('');        // 一覧生成
      updateVisibleTrips();

      // アニメーション
      function tick() {
        currentTime += STEP;
        if (currentTime > MAX_TS) currentTime = MIN_TS;
        updateVisibleTrips();
      }
      setInterval(tick, Math.max(1, Math.floor(1000 / FPS)));
    </script>
    """)
    html = html_tmpl.safe_substitute(
        TRIPS=json.dumps(trips_data, separators=(',', ':')),
        ROUTES=json.dumps(routes_ui, separators=(',', ':')),
        VIEW=json.dumps(view_state, separators=(',', ':')),
        MIN_TS=min_ts, MAX_TS=max_ts, STEP=step, FPS=fps, TRAIL=trail_length,
        MAP_STYLE=map_style
    )
    components.html(html, height=720)


def main() -> None:
    st.set_page_config(page_title="Ehime Bus Theater", layout="wide")
    st.title("Ehime Bus Time‑Lapse Theater")

    # --- Path and Date Setup ---
    script_dir = Path(__file__).parent
    gtfs_dir = script_dir / "data" / "gtfs" / "2025-07-03"
    fixed_date_str = "2025-07-15"

    # --- Sidebar Controls ---
    st.sidebar.header("表示設定")
    st.sidebar.info(f"表示日付: {fixed_date_str}")

    speed_option = st.sidebar.select_slider(
        "再生速度 (秒ステップ)", options=[1, 5, 10, 25, 60, 120, 300], value=60
    )
    theme = st.sidebar.radio("地図テーマ", options=["Light", "Dark"], index=1)

    # --- Data Loading ---
    with st.spinner(f"{fixed_date_str} のキャッシュデータを生成・読込中..."):
        df = _load_cache(fixed_date_str, gtfs_dir)

    if df.empty:
        st.warning("選択した日に運行するサービスはありません。")
        st.stop()

    # --- Route Selection ---
    routes_df = load_routes(gtfs_dir)
    routes_df['display_name'] = routes_df['route_long_name'].fillna('') + \
                            " (" + routes_df['route_short_name'].fillna('') + ")"
    route_options = routes_df.set_index('route_id')['display_name'].to_dict()

    selected_route_ids = st.sidebar.multiselect(
        "表示する路線を選択",
        options=list(route_options.keys()),
        format_func=lambda x: route_options[x],
        default=['10025']
    )

    # --- Apply Filters and Process Data ---
    if not selected_route_ids:
        st.warning("路線を1つ以上選択してください。")
        st.stop()

    # 2) route filter
    filtered_df = df[df['route_id'].isin(selected_route_ids)]

    if filtered_df.empty:
        st.warning("選択された路線は、この日に運行データがありません。")
        st.stop()

    st.success(f"{fixed_date_str} の {len(selected_route_ids)} 路線を読み込みました。(軌跡データ: {len(filtered_df):,}行)")

    # 3) 時間間引き＆近傍除去＆量子化
    processed_df = thin_by_time(filtered_df, step_sec=min(speed_option, 15))
    processed_df = drop_near_duplicates(processed_df, eps_m=3.0)
    processed_df["lat"] = processed_df["lat"].round(5)
    processed_df["lon"] = processed_df["lon"].round(5)
    processed_df["timestamp"] = processed_df["timestamp"].astype(np.int32)

    # 4) Trips化（ルート別カラー割当）
    uniq_routes = list(pd.unique(processed_df["route_id"]))
    route_colors = {rid: PALETTE[i % len(PALETTE)] for i, rid in enumerate(uniq_routes)}

    # 凡例/UI用メタ
    routes_ui = [
        {"route_id": rid, "name": route_options.get(rid, rid), "color": route_colors[rid]}
        for rid in uniq_routes
    ]

    trips_data = to_trips_payload(processed_df, route_colors)

    if trips_data:
        lat_center, lon_center = float(processed_df["lat"].mean()), float(processed_df["lon"].mean())
        min_ts, max_ts = int(processed_df["timestamp"].min()), int(processed_df["timestamp"].max())
    else:
        st.warning("処理されたデータがありません。")
        st.stop()


    # --- Deck.gl Rendering (Browser-side Animation) ---
    view_state = dict(latitude=lat_center, longitude=lon_center, zoom=12, pitch=45, bearing=0)
    map_style = (\
        "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json"\
        if theme == "Light" else\
        "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"\
    )
    
    # レイヤ設定の実務的チューニング
    trail_length_tuned = int(min(240, max(60, speed_option * 2))) # trail_length の上限を設定

    render_trips_in_browser(
        trips_data=trips_data,
        routes_ui=routes_ui,          # ← 追加
        view_state=view_state,
        map_style=map_style,
        min_ts=min_ts, max_ts=max_ts,
        step=speed_option,
        trail_length=trail_length_tuned,
        fps=24 # 固定FPS
    )

if __name__ == "__main__":
    main()