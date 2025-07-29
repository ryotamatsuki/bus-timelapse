# 要件定義書
**プロジェクト名**: Ehime Bus Time-Lapse Theater
**スタック**: Streamlit（フロントエンド兼 API）+ GitHub Actions（バッチ）
**対象データ**: 伊予鉄バス GTFS 静的データ（GTFS-JP）、2025-08 時点の最新を想定

---

## 1. 背景・目的
- 伊予鉄バスの運行系統とルート網を俯瞰するため、**「ある1日24時間を 1 分に凝縮したタイムラプス」**をブラウザで再生できるサービスを作る。
- 「バスロケ（現在位置）」ではなく **「ダイヤに基づく過去・未来の運行計画」**の可視化に重点を置く。

## 2. スコープ
| 分類 | 対象 | 備考 |
|------|------|------|
| 基本 | 1 日分の全経路再生 / 再生 | 静的 GTFS のみで完結（リアルタイムデータなし） |
| 任意 | A. Gemini によるナレーション機能<br>B. 動画エクスポート（MP4） | Gemini はテキスト生成のみ使用 |
| 追加 | 路線選択機能 | ユーザーが特定の路線を選択して表示 |

## 3. ペルソナと想定ユースケース
| ペルソナ | 行動シナリオ |
|----------|-------------|
| 松山市民 30 代・会社員 | 「普段使うバス路線がどう動いているか眺めて SNS にシェア」 |
| 地域交通プランナー | 「平日ダイヤのバス便がどう分布しているか、交通空白地帯へのアクセスを検討」 |
| 全国のオープンデータ活用チャレンジコミュニティ | 「実装やデータ活用の UI/UX の参考事例として確認」 |

## 4. 全体アーキテクチャ
```mermaid
graph TD
    subgraph バッチ (GitHub Actions)
        DL[GTFS zip 取得] --> PRE[前処理<br>(Python)]
        PRE --> FEATHER[日次 Feather/Parquet]
        SCHED[cron 定期実行] --> PRE
    end
    FEATHER --> API[(Streamlit)]
    subgraph Streamlit
        UI[Sidebar: 日付・速度・路線選択
Main: Pydeck 3D 描画] --> PYDECK
        SLIDER[時刻スライダー] --> PYDECK
        PYDECK[TripsLayer でデータ描画]
    end
```

### 4.1 ディレクトリ構成

```
.
├── .github/workflows/gtfs_preprocess.yml
├── app.py
├── data/
│   ├── gtfs/              # zip 展開先（バージョン管理）
│   └── cache/             # bus_trails_YYYY-MM-DD.feather
├── modules/
│   ├── path_builder.py    # 全経路データ生成モジュール
│   └── viz_utils.py
├── requirements.txt
└── README.md
```

## 5. データ仕様

| ファイル                                        | 主キー                             | 使用列                            | 備考          |
| ------------------------------------------- | ------------------------------- | ------------------------------ | ----------- |
| `calendar.txt` / `calendar_dates.txt`       | `service_id`                    | `date`, `exception_type`       | 運行日定義       |
| `trips.txt`                                 | `trip_id`                       | `service_id`, `shape_id`       |             |
| `stop_times.txt`                            | `trip_id`, `stop_sequence`      | `departure_time`, `stop_id`    |             |
| `stops.txt`                                 | `stop_id`                       | `stop_lat`, `stop_lon`         |             |
| `shapes.txt`                                | `shape_id`, `shape_pt_sequence` | `shape_pt_lat`, `shape_pt_lon` |             |
| **キャッシュ** (`bus_trails_YYYY-MM-DD.feather`) | `trip_id`, `timestamp_sec`      | `lat`, `lon`, `route_id`       | 5 秒毎の補間点を保存 |

### 時刻補間アルゴリズム

1.  バス停 A→B の **所要時間 Δt** を算出。
2.  `shapes.txt` で A→B 間の道のりに沿った **道のり比 r** を取得。
3.  `timestamp = t_A + r・Δt`、`lat/lon = A + r・(B−A)` を 5 s ピッチで線形補間。
4.  全便（`trip_id`）について全時間帯を計算 → Feather 保存。

## 6. 機能要件

| 番号            | 機能            | 詳細                                               |
| ------------- | ------------- | ------------------------------------------------ |
| **F-01**      | 日付選択          | 固定日付（2025-07-15）を表示。データ提供範囲も明示。         |
| **F-02**      | タイムスライダー      | 0〜86,400 s、1 s 刻み。`TripsLayer.current_time` に連動  |
| **F-03**      | 3D 描画        | Pydeck `TripsLayer`、trail_length = 120 s、幅 2.5 px |
| **F-04**      | 自動再生          | デフォルトで有効。高速化（1ステップ60秒、0.001秒間隔）。ループ再生。 |
| **F-05**      | 地図テーマ         | ライト / ダーク map_style 切替                          |
| **F-06 (任意)** | Gemini ナレーション | 選択時刻・場所に応じた 100 字コメント生成                           |
| **F-07 (任意)** | MP4 エクスポート    | `deck.gl` screencast → FFMPEG 連携                 |
| **F-08**      | 路線選択          | 複数路線を選択可能。デフォルトは「松山空港（道後温泉）」など3路線。 |
| **F-09**      | 決定ボタン          | 路線選択の変更を明示的に地図に反映するボタン。             |

## 7. 非機能要件

| 項目          | 要件                                                          |
| ----------- | ------------------------------------------------------------ |
| **応答速度**    | キャッシュ未生成時：3 秒以内に描画開始                                          |
| **データ更新**   | GitHub Actions で毎日 03:00 JST に最新 GTFS を pull & 再生成           |
| **ブラウザ互換**  | Chrome / Edge / Safari 最新版                                   |
| **スループット**  | 常時 20 セッションで FPS > 24                                        |
| **コスト**     | Streamlit Community Cloud（無料枠）+ GitHub Actions 2,000 min/月以下 |
| **ライセンス表記** | 画面フッターに「伊予鉄オープンデータ」とライセンス文言リンクを常時表示                            |
| **パフォーマンス** | 路線選択機能により、描画データ量を削減し、パフォーマンスを向上。             |
| **UI/UX**     | 時刻表示を「HH:MM:SS」形式に改善。決定ボタンにより、ユーザー操作の意図を明確化。 |

## 8. 外部インターフェース

| IF              | 方式                     | 内容                                       |
| --------------- | ---------------------- | ---------------------------------------- |
| GTFS 擾         | HTTPS (ODPT CKAN API)  | ZIP ダウンロード URL + `wget`                  |
| バッチ実行           | GitHub Actions (cron)  | Ubuntu-latest / Python 3.10              |
| マップタイル           | deck.gl / Mapbox Style | OpenStreetMap タイル (token 不要の light/dark) |
| Gemini API (任意) | HTTPS                  | text-generation (model: gemini-pro)      |

## 9. セキュリティ

*   環境変数は **API キーを GitHub Secrets に格納**。
*   キャッシュファイルは公開リポジトリに含めず、GitHub Releases or LFS に格納。

## 10. ワークフロー（WBS 概算）

| フェーズ       | タスク ID | 作業内容                           | 担当  | 日数      |
| ---------- | ------ | ------------------------------ | --- | ------- |
| 1. 環境構築    | T1-1   | リポジトリ作成・ブランチ戦略定義              | PM  | Day 1   |
|            | T1-2   | requirements.txt・Dockerfile 作成 | Dev | Day 1   |
| 2. データ処理   | T2-1   | GTFS DL スクリプト                  | Dev | Day 2–3 |
|            | T2-2   | `path_builder.py` 実装           | Dev | Day 4–5 |
| 3. キャッシュ設計 | T3-1   | Feather 出力・ユニットテスト            | Dev | Day 6   |
| 4. UI 実装   | T4-1   | Pydeck 描画（静的）                 | Dev | Day 7   |
|            | T4-2   | タイムスライダー連携                     | Dev | Day 8   |
|            | T4-3   | 自動再生ロジック                       | Dev | Day 9   |
| 5. デプロイ    | T5-1   | Streamlit Cloud 設定             | Ops | Day 10  |
|            | T5-2   | GitHub Actions cron            | Ops | Day 11  |
| 6. テスト     | T6-1   | クロスブラウザ・手動テスト                  | QA  | Day 12  |
| 7. ドキュメント  | T7-1   | README / 運用手順書作成                | Doc | Day 13  |

## 11. リスク & 対策

| リスク                | 影響        | 対策                                       |
| ------------------ | --------- | ---------------------------------------- |
| GTFS URL 変更        | キャッシュ生成失敗 | URL を `env` 変数化・404 チェック              |
| Mapbox タイル仕様変更     | 地図表示が崩れる | OSM / CartoDB など代替スタイルを用意                |
| Streamlit Cloud 障害 | サービス接続不可    | Render.com / Fly.io へ代替デプロイ可能な dockerfile 用意 |

## 12. 最終デモシナリオ

1.  任意の日付を選択し、**3 秒以内にタイムラプスが描画**されること。
2.  `trail_length` を変更しても、滑らかに再描画されること。
3.  F-04 自動再生で **0〜24 h を 60 秒以内に走破**し、クラッシュしないこと。
4.  README 手順通り `pip install -r requirements.txt` と `streamlit run app.py` で起動できること。
