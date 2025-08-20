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

# --- Stops Loading ---
@st.cache_data(show_spinner=False)
def load_stops(gtfs_dir: str) -> pd.DataFrame:
    stops_path = Path(gtfs_dir) / "stops.txt"
    df = pd.read_csv(stops_path, dtype={"stop_id": str})
    df = df.rename(columns={"stop_lat": "lat", "stop_lon": "lon"})
    df = df[["stop_id", "stop_name", "lat", "lon"]].dropna(subset=["lat", "lon"])
    # 近い点の重複を抑えるため軽く丸め（見た目・描画負荷対策）
    df["lat"] = df["lat"].round(5)
    df["lon"] = df["lon"].round(5)
    return df

@st.cache_data(show_spinner=False)
def to_stops_payload(df: pd.DataFrame) -> list[dict]:
    # deck.gl に渡す JSON（lon,lat の順に注意）
    return [
        {"stop_id": r.stop_id, "name": str(r.stop_name), "coord": [float(r.lon), float(r.lat)]}
        for r in df.itertuples(index=False)
    ]


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

def render_trips_in_browser(
    trips_data, routes_ui, view_state, map_style,
    min_ts, max_ts, step, trail_length=120, fps=24,
    stops_data=None, show_labels=False, stop_size_px=6
):
    stops_data = stops_data or []
    html_tmpl = Template(r"""
    <div id="map-wrap" style="position:relative;height:80vh;width:100%;">
      <div id="deck-container" style="position:absolute;inset:0;"></div>
    </div>

    <!-- 日本語フォントを iframe 側に読み込む（重要）-->
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700&display=swap" rel="stylesheet">

    <!-- ✅ 空白を削除した正しい CDN URL -->
    <script src="https://unpkg.com/deck.gl@8.9.27/dist.min.js"></script>
    <script src="https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.js"></script>
    <link href="https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.css" rel="stylesheet"/>

    <script>
      // データ
      const trips = $TRIPS;     // [{trip_id, route_id, path, timestamps, color}]
      const routes = $ROUTES;   // [{route_id, name, color}]
      const stops  = $STOPS;    // [{stop_id, name, coord:[lon,lat]}]
      const initialViewState = $VIEW;

      const MIN_TS = $MIN_TS;
      const MAX_TS = $MAX_TS;
      let   STEP   = $STEP;
      let   FPS    = $FPS;
      const TRAIL  = $TRAIL;

      const SHOW_LABELS = $SHOW_LABELS;
      const STOP_SIZE   = $STOP_SIZE;

      const deckgl = new deck.DeckGL({
        container: 'deck-container',
        controller: true,
        initialViewState,
        map: maplibregl,
        mapStyle: "$MAP_STYLE",
        getTooltip: ({object, layer}) => {
          if (!object || !layer) return null;
          if (layer.id === 'stops') {
            // ✅ Template と衝突しない通常の連結
            return {text: object.name + " (" + object.stop_id + ")"};
          }
          if (layer.id === 'trips') {
            return {text: "route: " + object.route_id};
          }
          return null;
        }
      });

      // 状態：有効化された route_id 集合（初期は全ON）
      let enabled = new Set(routes.map(r => r.route_id));
      let currentTime = MIN_TS;

      function makeLayers(ct, visibleTrips) {
        const layers = [];

        layers.push(new deck.TripsLayer({
          id: 'trips',
          data: visibleTrips,
          getPath: d => d.path,
          getTimestamps: d => d.timestamps,
          getColor: d => d.color,
          widthMinPixels: 2.5,
          trailLength: TRAIL,
          currentTime: ct,
          pickable: true
        }));

        if (stops.length > 0) {
          layers.push(new deck.ScatterplotLayer({
            id: 'stops',
            data: stops,
            getPosition: d => d.coord,
            getRadius: d => 1,
            radiusMinPixels: STOP_SIZE,
            radiusMaxPixels: STOP_SIZE,
            stroked: true,
            filled: true,
            getFillColor: [0, 0, 0, 200],
            getLineColor: [255, 255, 255, 220],
            lineWidthMinPixels: 1,
            pickable: true
          }));
        }

        if (SHOW_LABELS && stops.length > 0) {
          // JS内どこか（deckgl 初期化後でOK）：停留所名から文字集合を作る
          const CHARSET = Array.from(new Set(stops.map(d => d.name).join('')));

          layers.push(new deck.TextLayer({
            id: 'stop-labels',
            data: stops,
            getPosition: d => d.coord,
            getText: d => d.name,
            getSize: d => 14,  // px固定。好みで 12〜16
            sizeUnits: 'pixels',
            sizeScale: 1,
            fontFamily: 'Noto Sans JP, "Yu Gothic UI", Meiryo, "Hiragino Kaku Gothic ProN", sans-serif',
            characterSet: CHARSET,
            background: true,
            getBackgroundColor: [255, 255, 255, 220],
            getColor: [20, 20, 20, 255],
            getTextAnchor: 'start',
            getAlignmentBaseline: 'center',
            billboard: true,
            pickable: false,
            parameters: { depthTest: false }   // タイルや線の下に潜らない
          }));
        }

        return layers;
      }

      function updateVisibleTrips() {
        const visibleTrips = trips.filter(t => enabled.has(t.route_id));
        deckgl.setProps({ layers: makeLayers(currentTime, visibleTrips) });
      }

      // 初期描画
      updateVisibleTrips();

      // フォント読込完了後にレイヤを再設定
      if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(() => updateVisibleTrips());
      }

      // アニメーション
      function tick() {
        currentTime += STEP;
        if (currentTime > MAX_TS) currentTime = MIN_TS;
        updateVisibleTrips();
      }
      setInterval(tick, Math.max(1, Math.floor(1000 / FPS)));
    </script>
    """);

    html = html_tmpl.safe_substitute(
        TRIPS=json.dumps(trips_data, separators=(',', ':')),
        ROUTES=json.dumps(routes_ui, separators=(',', ':')),
        STOPS=json.dumps(stops_data, separators=(',', ':')),
        VIEW=json.dumps(view_state, separators=(',', ':')),
        MIN_TS=min_ts, MAX_TS=max_ts, STEP=step, FPS=fps, TRAIL=trail_length,
        MAP_STYLE=map_style,
        SHOW_LABELS=json.dumps(bool(show_labels)),
        STOP_SIZE=int(stop_size_px),
    )
    components.html(html, height=720)


def main() -> None:
    st.set_page_config(layout="wide")
    
    st.title("Ehime Bus Time‑Lapse Theater")

    # --- Path and Date Setup ---
    script_dir = Path(__file__).parent

    # まずは Windows 絶対パスを優先（raw 文字列にしておく）
    abs_gtfs_dir = Path(r"C:\Users\Owner\Desktop\workspace_new\proj_j_bus-timelapse-theater\data\AllLines-20250703")

    candidates = [
        abs_gtfs_dir,
        script_dir / "data" / "gtfs" / "2025-07-03",
    ]

    gtfs_dir = None
    for p in candidates:
        if (p / "stops.txt").exists() and (p / "routes.txt").exists():
            gtfs_dir = p
            break

    if gtfs_dir is None:
        st.error("GTFS データ（stops.txt, routes.txt）が見つかりません。パス設定を確認してください。")
        st.stop()

    fixed_date_str = "2025-07-15"


    # --- Sidebar Controls ---
    st.sidebar.header("表示設定")
    st.sidebar.info(f"表示日付: {fixed_date_str}")

    speed_option = st.sidebar.select_slider(
        "再生速度 (秒ステップ)", options=[1, 5, 10, 25, 60, 120, 300], value=60
    )
    theme = st.sidebar.radio("地図テーマ", options=["Light", "Dark"], index=1)

    # バス停表示の追加オプション
    st.sidebar.subheader("バス停の表示")
    show_stops = st.sidebar.checkbox("バス停ポイントを表示", value=True)
    show_labels = st.sidebar.checkbox("バス停名ラベルを表示（高ズーム推奨）", value=False)
    stop_size_px = st.sidebar.slider("バス停サイズ（px）", min_value=3, max_value=12, value=6)


    # --- Data Loading ---
    with st.spinner(f"{fixed_date_str} のキャッシュデータを生成・読込中..."):
        df = _load_cache(fixed_date_str, gtfs_dir)

    if df.empty:
        st.warning("選択した日に運行するサービスはありません。")
        st.stop()

    # ルート情報は既存のまま
    routes_df = load_routes(gtfs_dir)
    routes_df['display_name'] = routes_df['route_long_name'].fillna('') + " (" + routes_df['route_short_name'].fillna('') + ")"
    route_options = routes_df.set_index('route_id')['display_name'].to_dict()
    all_route_ids = list(route_options.keys())

    # （前回提案の全選択/全解除 UI はそのまま利用）
    # --- Route Selection ---
    route_keys = all_route_ids

    # 初期選択を session_state で管理（既存デフォルトは '10025'）
    if "route_selector" not in st.session_state:
        st.session_state.route_selector = ['10025']

    # 全選択 / 全解除 ボタン
    c1, c2, c3 = st.sidebar.columns([1,1,1])
    with c1:
        if st.button("全て選択", use_container_width=True):
            st.session_state.route_selector = route_keys[:]   # 全部
    with c2:
        if st.button("全て解除", use_container_width=True):
            st.session_state.route_selector = []              # 空
    with c3:
        # お好みで：反転（要らなければこの列ごと削除可）
        if st.button("反転", use_container_width=True):
            cur = set(st.session_state.route_selector)
            st.session_state.route_selector = [k for k in route_keys if k not in cur]

    # multiselect は key で session_state と同期
    selected_route_ids = st.sidebar.multiselect(
        "表示する路線を選択",
        options=route_keys,
        format_func=lambda x: route_options[x],
        key="route_selector"
    )


    # バス停
    stops_data = []
    if show_stops:
        stops_df = load_stops(gtfs_dir)
        stops_data = to_stops_payload(stops_df)


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
    map_style = (
        "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json"
        if theme == "Light" else
        "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
    )
    
    # レイヤ設定の実務的チューニング
    trail_length_tuned = int(min(240, max(60, speed_option * 2))) # trail_length の上限を設定

    render_trips_in_browser(
        trips_data=trips_data,
        routes_ui=routes_ui,
        view_state=view_state,
        map_style=map_style,
        min_ts=min_ts, max_ts=max_ts,
        step=speed_option,
        trail_length=trail_length_tuned,
        fps=24,
        stops_data=stops_data,          # ← 追加
        show_labels=show_labels,        # ← 追加
        stop_size_px=stop_size_px       # ← 追加
    )

if __name__ == "__main__":
    main()
