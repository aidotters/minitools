# arxiv-translate VLM Parse Repair 手動スモークテスト

実 VLM 呼び出し（API 課金）を伴うため CI には組み込めない検証項目をまとめる。
`GEMINI_API_KEY`（または `OPENAI_API_KEY`）を保有する開発者向け手順。

## 前提

- `.env` に `GEMINI_API_KEY` が設定済（既定 provider）
- `settings.yaml` で `arxiv_translate.vlm_repair.enabled: true`
- 1 論文あたりの想定コスト: Gemini 2.5 Flash で $0.05 以下
- 想定追加処理時間: +60 秒以内（10 ページ規模）

## 共通リセットコマンド

各テスト前に対象論文のキャッシュを削除する:

```bash
SAFE_ID=2602.12670  # 対象論文の safe_id (ArXiv ID と同じ形式)
rm -f outputs/arxiv_translate/${SAFE_ID}_raw.md \
      outputs/arxiv_translate/${SAFE_ID}.pdf
rm -rf outputs/arxiv_translate/${SAFE_ID}_page_images
```

## テスト 1: Table 9 復元

**目的**: marker-pdf が崩した複雑テーブルを VLM で復元できることを確認。

**対象**: `2602.12670` の Table 9（タスク一覧）

**手順**:

```bash
uv run arxiv-translate parse --url "https://arxiv.org/abs/2602.12670"
```

**期待結果**:

`outputs/arxiv_translate/2602.12670_raw.md` 内に以下のような 4 列 Markdown テーブルが生成される:

```markdown
| Task ID | Domain | Diff. | Description |
|---------|--------|-------|-------------|
| ...     | ...    | ...   | ...         |
```

**確認ポイント**:

- ヘッダ行が `| Task ID | Domain | Diff. | Description |` 形式である
- データ行のセル数が 4（±1 まで許容）
- 区切り行 `|---|---|---|---|` が含まれる
- セル内容は英語のまま（翻訳されていない）

## テスト 2: 主要図への日本語要約挿入

**目的**: 図直後に `> [図解説]` 形式で 50〜200 字の日本語要約が入ることを確認。

**対象**: `2602.12670` の Figure 1, 4, 11–13

**手順**: テスト 1 と同じコマンドを実行（同時に検証可能）。

**期待結果**:

`_raw.md` 内の主要図（`![](_page_X_Figure_Y.jpeg)`）の直後に以下のような行が挿入される:

```markdown
![](_page_3_Figure_1.jpeg)

> [図解説] 図1は提案手法の全体像を示しており、入力テキストから...（50〜200字）

Figure 1: ...
```

**確認ポイント**:

- 各主要図の直後に `> [図解説]` 行が 1 つだけ存在（冪等性）
- 要約は 50〜200 字の段落 1 つ
- 数値・軸ラベル・凡例の主要項目が含まれる
- 不明確な部分は「(読み取り不能)」と明記

## テスト 3: 誤検出による破壊なし（リグレッション）

**目的**: 破損のない論文に対して修復ありで実行しても、テーブル/段落構造が壊れないことを確認。

**手順**:

```bash
SAFE_ID=<破損のない論文の safe_id>
URL=<対応する ArXiv URL>

# 1. ベースライン取得（修復なし）
rm -f outputs/arxiv_translate/${SAFE_ID}_raw.md outputs/arxiv_translate/${SAFE_ID}.pdf
uv run arxiv-translate parse --url "${URL}" --no-vlm-repair
cp outputs/arxiv_translate/${SAFE_ID}_raw.md /tmp/${SAFE_ID}_raw_baseline.md

# 2. 修復ありで再実行
rm -f outputs/arxiv_translate/${SAFE_ID}_raw.md outputs/arxiv_translate/${SAFE_ID}.pdf
rm -rf outputs/arxiv_translate/${SAFE_ID}_page_images
uv run arxiv-translate parse --url "${URL}"

# 3. 比較
diff /tmp/${SAFE_ID}_raw_baseline.md outputs/arxiv_translate/${SAFE_ID}_raw.md
```

**期待結果**:

- diff の差分は「`> [図解説]` 行の追加」と「正常テーブルの再フォーマット（セル幅調整等）」のみ
- 段落構造・本文・既存テーブルのデータが破壊されていない
- 元になかった行が大量に挿入されていない

## テスト 4: コスト/時間計測（参考）

**目的**: 1 論文あたりのコストが Gemini 2.5 Flash で $0.05 以下、追加処理時間 +60 秒以内（10 ページ規模）であることを確認。

**手順**:

```bash
# 修復なしの実行時間
time uv run arxiv-translate parse --url "https://arxiv.org/abs/2602.12670" --no-vlm-repair

# キャッシュリセット後、修復ありの実行時間
rm -f outputs/arxiv_translate/2602.12670_raw.md outputs/arxiv_translate/2602.12670.pdf
rm -rf outputs/arxiv_translate/2602.12670_page_images
time uv run arxiv-translate parse --url "https://arxiv.org/abs/2602.12670"
```

**期待結果**:

- 修復ありの追加時間: +60 秒以内
- Gemini ダッシュボードでの該当時刻のコスト: $0.05 以下

## トラブルシューティング

| 症状 | 原因 / 対処 |
|------|-------------|
| `PyMuPDF not installed` エラー | `uv add pymupdf` を実行 |
| `GEMINI_API_KEY not set` 警告 | `.env` を確認、`source .env` |
| Table が復元されない | `arxiv-translate repair --url "..." --dry-run` で defect が検出されているか確認 |
| 図解説が重複挿入される | 既存 `_raw.md` を削除して再実行（idempotent 検出は同一行範囲のみ） |
| budget 超過 warning | `settings.yaml` の `max_total_calls` を確認、または `repair_figures: false` で table 優先 |

## 関連

- 設定: `settings.yaml` の `arxiv_translate.vlm_repair`
- 実装: `minitools/processors/vlm_parse_repairer.py`
- ユニットテスト: `tests/test_vlm_parse_repairer.py`
- スペック: `.steering/20260425-vlm-parse-error-repair/`
