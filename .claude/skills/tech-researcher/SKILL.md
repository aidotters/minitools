---
name: tech-researcher
description: 技術調査を行い、導入手順・実践ガイドを含む調査レポートを作成
user-invocable: true
disable-model-invocation: true
allowed-tools: Read, Write, WebSearch, WebFetch
argument-hint: "[技術名/ライブラリ名/API名]"
---

# 技術調査レポート作成

**目的:** 指定した技術（API、ライブラリ、フレームワーク等）を包括的に調査し、このプロジェクトへの導入に必要な実践ガイドを作成します。

**引数:**
- `/tech-researcher [技術名]` - 技術名を指定して調査（例: `marker-pdf`、`TwitterAPI.io`、`Jina AI Reader`）

**出力:** `.steering/YYYYMMDD-research-[技術名]/research-report.md`

---

## ステップ1: 調査対象の確認

```
技術名 = $ARGUMENTS

if 技術名 == "":
    "エラー: 調査対象の技術名を指定してください。例: /tech-researcher marker-pdf"
    → 処理終了
```

---

## ステップ2: 公式ドキュメント調査

### 2.1 context7 による公式ドキュメント取得（利用可能な場合）

```
# context7 MCP が利用可能なら優先使用
mcp__context7__resolve-library-id(libraryName=技術名)
→ library_id が取得できた場合:
    mcp__context7__query-docs(context7CompatibleLibraryID=library_id, topic="overview installation usage")
    → 取得した公式ドキュメントを基礎情報として使用
```

### 2.2 WebSearch による補足調査

```
WebSearch("[技術名] official documentation")
WebSearch("[技術名] API reference")
WebSearch("[技術名] getting started tutorial")
→ 公式サイト・ドキュメントURLを特定

# 主要ページの内容を取得
WebFetch(公式ドキュメントURL)
WebFetch(APIリファレンスURL)
```

### 2.3 収集する基本情報

| 項目 | 内容 |
|------|------|
| 技術の概要・目的 | 何のための技術か |
| 主要コンポーネント | 構成要素と役割 |
| バージョン・互換性 | 現行バージョン、Python/OS対応状況 |
| ライセンス | 利用条件 |

---

## ステップ3: 実装例・サンプルコード収集

```
WebSearch("[技術名] Python example code")
WebSearch("[技術名] integration example GitHub")
WebSearch("[技術名] best practices")
→ 実装例URLを収集

WebFetch(実装例URL)
```

**収集対象:**
- 最小構成のサンプルコード
- エラーハンドリングを含む実践的なコード
- 認証・初期設定の具体的な手順

---

## ステップ4: 制限事項・注意点調査

```
WebSearch("[技術名] rate limit quota")
WebSearch("[技術名] limitations known issues")
WebSearch("[技術名] vs alternatives comparison")
WebSearch("[技術名] Python issues troubleshooting")
```

**調査項目:**
- レート制限・クォータ（APIの場合）
- データサイズ・処理速度の制限
- 既知の問題と回避策
- 類似技術との比較（このプロジェクトで採用すべき理由）

---

## ステップ5: このプロジェクトへの統合検討

```
# 既存コードとの関連を確認
Grep('[技術名]', 'minitools/')
Read('settings.yaml')
Read('pyproject.toml')
```

**検討事項:**
- 既存の依存関係との競合有無
- 類似機能を持つ既存モジュールとの関係
- `.env` / `settings.yaml` への追加が必要な設定項目
- 既存の非同期パターン（asyncio）との整合性

---

## ステップ6: レポート生成

### 出力形式

```markdown
# [技術名] 調査レポート

> 調査日: YYYY-MM-DD
> 対象バージョン: [バージョン]

## 概要

[技術の概要と主な用途を2-3文で説明]

## 基本情報

| 項目 | 内容 |
|------|------|
| 公式サイト | [URL] |
| ドキュメント | [URL] |
| 最新バージョン | [バージョン] |
| ライセンス | [ライセンス種別] |
| PyPI / npm | [パッケージ名] |

## アーキテクチャ

[主要コンポーネントと動作原理の説明]

## 導入手順

### 前提条件

- [必要な環境・依存関係]

### インストール

```bash
uv add [パッケージ名]
```

### 設定

```yaml
# settings.yaml への追加（必要な場合）
```

```env
# .env への追加（必要な場合）
```

## API リファレンス（主要機能）

### [機能名1]

**用途**: [説明]

```python
# サンプルコード
```

### [機能名2]

**用途**: [説明]

```python
# サンプルコード
```

## 実装例

### 最小構成

```python
# 最小限の実装例
```

### 実践的な実装（エラーハンドリング・リトライ含む）

```python
# このプロジェクトの非同期パターンに合わせた実装例
```

## 制限事項・注意点

| 制限項目 | 内容 | 対処法 |
|----------|------|--------|
| [制限1] | [詳細] | [回避策] |

## このプロジェクトへの統合方針

### 既存モジュールとの関係

[競合・代替・補完関係の説明]

### 推奨統合箇所

- [統合すべきファイル・モジュール]

### 設定追加事項

- `settings.yaml`: [追加項目]
- `.env`: [追加項目]

## トラブルシューティング

### [よくある問題1]

**症状**: [説明]
**原因**: [説明]
**解決策**: [手順]

## 参考リソース

- [リソース名](URL) — [説明]
```

---

## ステップ7: レポートの保存

```
# 保存先ディレクトリの作成
保存先 = '.steering/YYYYMMDD-research-[技術名]'
Bash('mkdir -p {保存先}')

# レポートを保存
Write('{保存先}/research-report.md', レポート内容)
```

**命名規則:**
- 技術名のスペースはハイフンに置換（例: `Jina AI Reader` → `jina-ai-reader`）
- 例: `.steering/20260605-research-marker-pdf/research-report.md`

---

## 調査の姿勢

- **実践志向**: 情報を集めるだけでなく、このプロジェクトで実際に使える形にまとめる
- **正確性重視**: 公式ドキュメントを一次情報として優先し、推測は明示する
- **コード中心**: 説明文より実際のコード例を重視する
- **最新性確認**: バージョンや調査日を明記する
