---
name: update-docs
description: 実装済みコードに基づきdocs/core/、CLAUDE.md、README.mdを同期
user-invocable: true
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
argument-hint: "[対象モジュール|ファイルパス|steeringフォルダ], --from-report [パス]"
---

# ドキュメント更新（実装済みコードとの同期）

**目的:** 実装済みコードを解析し、全ドキュメントとの整合性を維持する。

**更新対象:**
- `docs/core/` - 設計・API仕様ドキュメント
- `CLAUDE.md` - Claude Code用プロジェクトコンテキスト
- `README.md` - プロジェクト公式ドキュメント

**重要:** このコマンドは**実装完了後**に使用する。未実装の機能をドキュメントに追加してはならない。

**引数:**
- `/update-docs` - 実装済みコード全体をスキャンして同期
- `/update-docs [対象モジュール]` - 特定のモジュールに関連するドキュメントのみ更新
- `/update-docs [ファイルパス]` - 指定されたファイルパス（例: `src/core/processor.py`）に関連するドキュメントのみ更新
- `/update-docs [steeringフォルダ]` - 指定されたsteeringフォルダの実装内容に基づいて関連ドキュメントのみ更新
  - 例: `/update-docs .steering/20260207-slack-notification/`
  - 例: `/update-docs 20260207-slack-notification`（`.steering/`プレフィックス省略可）
- `/update-docs --from-report [フォルダ名またはファイルパス]` - レビューレポートの指摘事項に沿って修正

**`--from-report`の引数解釈:**

| 入力 | 解釈 |
|------|------|
| `--from-report 20260129-docs-review` | `.steering/20260129-docs-review/` 内の `review-report*.md` を全て対象 |
| `--from-report .steering/20260129-docs-review/review-report.md` | 指定ファイルのみ |

**モード判定:**
1. 引数に `--from-report` が含まれる場合 → **レビュー結果修正モード**
2. 引数が `YYYYMMDD-` 形式で始まる、または `.steering/YYYYMMDD-*/` パターンに一致する場合 → **Steeringフォルダモード**
3. それ以外 → **通常モード**（従来の動作）

---

## モード別処理フロー

### レビュー結果修正モード（`--from-report`指定時）

引数に `--from-report` が含まれる場合、以下のステップを実行:

1. **ステップR1:** レビューレポートの読み込みと解析
2. **ステップR2:** 指摘事項の分類と優先度付け
3. **ステップR3:** 指摘事項に基づくドキュメント修正
4. **ステップR4:** 修正サマリーの出力

→ **ステップR1〜R4** を参照

### Steeringフォルダモード（steeringフォルダ指定時）

引数が `YYYYMMDD-` 形式で始まる、または `.steering/YYYYMMDD-*/` パターンに該当する場合、以下のステップを実行:

1. **ステップS1:** Steeringフォルダの検証と読み込み
2. **ステップS2:** 変更対象ファイルの特定
3. **ステップS3:** 変更対象ファイルの実装内容解析
4. **ステップS4:** 関連ドキュメントの更新
5. **ステップS5:** 更新サマリーの出力

→ **ステップS1〜S5** を参照

### 通常モード（`--from-report`もsteeringフォルダも指定されていない場合）

以下のステップを実行:

1. **ステップ1:** 実装済みコードの解析
2. **ステップ2:** ドキュメントの現状確認
3. **ステップ3:** 差分の検出
4. **ステップ4:** ドキュメントの更新
5. **ステップ5:** 更新サマリーの出力

→ **ステップ1〜5** を参照

---

> **上記3モードの各ステップ（通常: 1〜5 / Steeringフォルダ: S1〜S5 / レビュー結果修正: R1〜R4）の詳細手順・出力フォーマット・モード別の注意事項は、すべて [reference.md](./reference.md) に収録しています。ドキュメント更新を実行する前に必ず reference.md を読むこと。**

## 注意事項

### 絶対守るべきルール

1. **未実装機能を記載しない**
   - `docs/ideas/`の内容を`docs/core/`に転記しない
   - 実装済みコードのみをドキュメント化

2. **削除は慎重に**
   - コードから削除されたものはドキュメントからも削除
   - ただし、手動で追加された説明文は保持

3. **整合性優先**
   - コードが正（source of truth）
   - ドキュメントはコードの反映

> 更新時の詳細な注意（CLAUDE.md / README.md の自動更新範囲と手動管理範囲）・エラー処理・各モード固有の注意事項は [reference.md](./reference.md) を参照してください。

## ワークフロー全体での位置づけ

```
/plan-feature
    ↓ （計画作成）
/implement-feature
    ↓ （実装完了）
/update-docs {steeringフォルダ} ← ここ（Steeringフォルダモード: 実装範囲に限定した効率的な同期）
    ↓
/validate-code
    ↓ （コード修正が発生する可能性）
/update-docs ← ここ（通常モード: 実装・修正後の全体同期）
    ↓
/review-docs
    ↓ （品質レビュー）
/update-docs --from-report {フォルダ名} ← ここ（レビュー結果修正モード）
    ↓ （指摘事項の修正）
コード完成
```

このコマンドは3つの用途がある:

1. **通常モード**: 実装フェーズの最後に実行し、コードとドキュメントの整合性を確保
2. **Steeringフォルダモード**: 特定機能の実装後に実行し、その機能に関連するドキュメントだけを効率的に更新
3. **レビュー結果修正モード**: `/review-docs` の指摘事項に沿って修正を実行

推奨ワークフロー:
1. `/update-docs .steering/YYYYMMDD-feature-name/` で実装した機能のドキュメントを同期（Steeringフォルダモード）
2. `/review-docs` でドキュメント品質をレビュー
3. `/update-docs --from-report YYYYMMDD-docs-review` でレビュー指摘を修正
4. 必要に応じて2-3を繰り返す
5. 全体的な整合性確認が必要な場合は `/update-docs`（通常モード）を実行
