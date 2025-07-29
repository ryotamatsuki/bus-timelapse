# 愛媛バスタイムラプスシアター | 詳細タスクリスト ✅

> **チェック方法**  
> - 完了したら `[x]` に変更  
> - 未着手ブロックや不明な行は `?` を付与して更新  

---

## 0. 準備 / 基本設定
- [ ] **0-1. GitHub 新規リポジトリ作成**  
  - [ ] リポジトリ名 `bus-timelapse-theater`  
  - [ ] MIT License 追加
- [x] **0-2. `.gitignore` 作成**  
  - [x] `__pycache__/`, `.venv/`, `.DS_Store`, `data/cache/*` を除外
- [ ] **0-3. Python 環境構築**  
  - [ ] `pyenv install 3.11.9`  
  - [ ] `pyenv local 3.11.9`
- [ ] **0-4. 仮想環境**  
  - [ ] `python -m venv .venv`  
  - [ ] `source .venv/bin/activate`
- [x] **0-5. 必要なライブラリのインストール**  
  - [x] `pip install streamlit pandas pydeck pyarrow numpy tqdm black flake8`  
  - [x] `pip freeze > requirements.txt`
- [x] **0-6. コードフォーマッタ / Linter**  
  - [x] `pre-commit` 導入  
  - [x] `.pre-commit-config.yaml` に `black`, `flake8`, `isort`

---

## 1. データ取得 & ストレージ設計
- [?] **1-1. 最新 GTFS 静的 ZIP URL 取得**  
  - [x] ODPT カタログから伊予鉄バスの URL を確認・利用 (データはローカルに存在するためスキップ)
- [x] **1-2. `data/gtfs/` ディレクトリ作成**
- [x] **1-3. ダウンロードスクリプト `scripts/download_gtfs.py`**  
  - [x] `argparse` で URL / 保存先指定  
  - [x] `wget` or `requests` で取得  
  - [x] 取得後に SHA-256 を計算し `*.sha256` 保存
- [x] **1-4. 展開 & バージョン管理ディレクトリ作成**  
  - [x] ZIP 展開先 `data/gtfs/2025-08/`  
  - [x] 展開後は `LATEST` シンボリックリンクを貼る

---

## 2. データ検証
- [ ] **2-1. CSV 構造テスト `notebooks/validation.ipynb`**  
  - [ ] `pandas.read_csv` で各テーブルを DataFrame へ  
  - [ ] 行数・基本統計量チェック
- [ ] **2-2. 主キー・外部キー整合性**  
  - [ ] `trips.service_id` と `calendar.service_id`  
  - [ ] `stop_times.trip_id` と `trips.trip_id`
- [x] **2-3. 運行日フィルタ関数 `modules/service_filter.py`**  
  - [x] `def get_valid_service_ids(date:str)->set[str]`  
  - [x] 祝日（2025-09-15）で単体テスト
- [x] **2-4. HH:MM:SS パースユーティリティ**  
  - [x] `def hhmmss_to_sec(h:str)->int`  
  - [x] 25:15:30 (翌日) が 90930 秒のテストを追加

---

## 3. 全経路データ生成モジュール `modules/path_builder.py`
- [x] **3-1. キャッシュ用フォルダ `data/cache/` を準備**
- [x] **3-2. `build_day_cache(date)` 実装**  
  - [x] 対象 `bus_trails_<date>.feather` 存在時はスキップ (デバッグのため一時的に無効化中)  
  - [x] 有効 `service_id` 取得  
  - [x] 該当 `trip_id` 抽出
- [x] **3-3. 時刻補間ロジック**  
  - [x] 全バス停の出発・到着を numpy ベクトル化  
  - [x] シェイプ点 geo 取得  
  - [x] 5 秒ピッチで補間し `lat, lon, timestamp` 生成 (バス停座標取得ロジック修正)
- [x] **3-4. Feather 形式で保存**  
  - [x] 列 `['trip_id','timestamp','lat','lon','route_id']`  
  - [x] 圧縮 `lz4`（なければ無圧縮）
- [ ] **3-5. 単体テスト**  
  - [ ] `pytest` で `len(df)%5==0` を保証  
  - [ ] キャッシュ読み書きでスキーマ・dtype が変わらないか確認

---

## 4. GitHub Actions でデータ前処理バッチ
- [x] **4-1. `/.github/workflows/gtfs_preprocess.yml` 作成**  
  - [x] cron `0 18 * * *` (UTC18 は JST03)  
  - [x] `actions/setup-python@v5` で Python 3.11
- [x] **4-2. ジョブ設計**  
  - [x] リポジトリを checkout  
  - [x] `pip install -r requirements.txt --no-cache-dir`  
  - [x] `python scripts/download_gtfs.py`  
  - [x] `python -m modules.path_builder --date tomorrow`  
  - [x] 完了物を `actions/upload-artifact` で `cache/` に保存
- [ ] **4-3. Secrets 設定**  
  - [ ] `ODPT_TOKEN` （今回は不要）
- [ ] **4-4. ワークフロー手動実行テスト**

---

## 5. Streamlit UI 実装 `app.py`
- [x] **5-1. ページ設定**  
  - [x] `st.set_page_config(page_title='Ehime Bus Theater', layout='wide')`
- [x] **5-2. サイドバー**  
  - [x] 日付選択UIを固定日付に変更 (2025-07-15)  
  - [x] 再生速度 `st.select_slider` (デフォルト60秒ステップ)  
  - [x] 地図テーマ `st.radio` (Light/Dark)  
  - [x] 路線選択 `st.multiselect` (デフォルト指定路線)  
  - [x] 決定ボタン `st.sidebar.button`
- [x] **5-3. キャッシュ読み込み**  
  - [x] `_load_cache()` 呼び出し (st.cache_dataでキャッシュ)
- [x] **5-4. Pydeck レイヤー**  
  - [x] `TripsLayer` 作成  
    - [x] `get_path` 関数で `[lon,lat]` 配列を trip ごとに返す  
    - [x] `get_timestamps='timestamp'`  
    - [x] `trail_length=120`  
    - [x] `get_color='color'` (ランダム色付け)  
  - [x] 初期 `ViewState` は松山市駅, pitch45
- [x] **5-5. 時刻スライダー**  
  - [x] `st.slider` 0〜86400 秒、ステップ1  
  - [x] 自動再生: `st.checkbox('Auto Play')` (デフォルトTrue) + `st.rerun()` でアニメーション制御  
  - [x] 現在時刻を `HH:MM:SS` 形式で表示
- [ ] **5-6. レスポンシブテスト**  
  - [ ] ウィンドウ幅を変えても FPS が 24fps を維持するか確認

---

## 6. デプロイ
- [ ] **6-1. Streamlit Community Cloud**  
  - [ ] 新規 App 作成 → GitHub リポジトリ連携  
  - [ ] `main` ブランチ / `app.py` を指定
- [ ] **6-2. 動作デプロイ後確認**  
  - [ ] ローディングが 5s 未満  
  - [ ] キャッシュ生成後の再描画がスムーズ
- [ ] **6-3. ブラウザ互換性テスト**  
  - [ ] Chrome, Edge, Safari 最新で UI 崩れがないか確認

---

## 7. ドキュメント & CI
- [x] **7-1. `README.md`**  
  - [x] プロジェクト概要  
  - [x] ローカル起動手順  
  - [?] スクリーンショット / GIF
- [ ] **7-2. アーキテクチャ図**  
  - [ ] `docs/architecture.drawio`  
  - [ ] PNG エクスポートも
- [ ] **7-3. CI (push 時) ワークフロー**  
  - [ ] フォーマッタ / Lint / Pytest を自動実行

---

## 8. オプション機能（Gemini ナレーション）
- [x] **8-1. `modules/gemini_helper.py`**  
  - [x] `def get_comment(date:str, hour:int)->str`
- [ ] **8-2. API キー環境変数 `GEMINI_API_KEY`**
- [ ] **8-3. サイドバー切替**  
  - [ ] ナレーション表示トグルチェック
- [ ] **8-4. レスポンスキャッシュ**  
  - [ ] `functools.lru_cache(maxsize=128)` でAPIコール削減

---

## 9. QA / 最終受け入れテスト
- [ ] **9-1. 単体テストカバレッジ 80% 以上**
- [ ] **9-2. 最終デモシナリオ 1〜4 を実施**
- [ ] **9-3. Lighthouse パフォーマンススコア > 90**
- [ ] **9-4. コードレビュー依頼 (同僚 3 名)**

---

## 10. リリース & 周知
- [ ] **10-1. GitHub Release v1.0.0**  
  - [ ] リリースノート作成
- [ ] **10-2. SNS 投稿 (X, Threads)**  
  - [ ] 動作キャプチャを添付
- [ ] **10-3. GitHub Discussions 開設 (フィードバック募集)**
- [ ] **10-4. 運用手順書を作成**  
  - [ ] Actions 実行時のエラー対応  
  - [ ] Streamlit Cloud 再起動手順
