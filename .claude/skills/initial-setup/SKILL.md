---
name: initial-setup
description: プロジェクト初期セットアップ（新規/既存対応）
user-invocable: true
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# 初期セットアップ (initial-setup)

**目的:** Claude Commands/Skillsをプロジェクトに適合させる

**対応モード:**
- **既存プロジェクト**: Commands/Skillsの適合
- **新規プロジェクト**: 基本構成作成 + 適合

**使用方法（別プロジェクトでの導入）:**
```bash
# 1. テンプレートの .claude/ をコピー
cp -r /path/to/_common/.claude /path/to/new-project/

# 2. 新プロジェクトで /initial-setup を実行
# → プロジェクトに合わせて自動適合
```

---

## ステップ1: プロジェクト状態の検出

### 1.1 検出対象ファイルの確認

以下のファイル/ディレクトリを確認する:

```
# 必須確認
Bash('ls -la') # ルートディレクトリの確認
Read('CLAUDE.md') # 存在確認（存在しない場合はエラー返却を期待）
```

### 1.2 パッケージマネージャの検出

| ファイル | 言語 | デフォルトソースDir | デフォルトテストDir |
|----------|------|---------------------|---------------------|
| pyproject.toml | Python | `src/` | `tests/` |
| package.json | Node.js | `src/` | `tests/` or `__tests__/` |
| Cargo.toml | Rust | `src/` | `tests/` |
| go.mod | Go | `cmd/`, `internal/` | `*_test.go` |
| (なし) | 不明 | `src/` | `tests/` |

```
# パッケージマネージャ検出
Glob('pyproject.toml')
Glob('package.json')
Glob('Cargo.toml')
Glob('go.mod')
```

### 1.3 ソースディレクトリの検出

以下の順序で候補を検出:

```
# 既存ソースディレクトリ候補
Glob('src/**/*.py') or Glob('src/**/*.ts') # src/ 配下
Glob('lib/**/*.py') or Glob('lib/**/*.ts') # lib/ 配下
Glob('backend/**/*.py')                     # backend/ 配下
Glob('app/**/*.py') or Glob('app/**/*.ts') # app/ 配下
```

### 1.4 設定ファイルの検出

```
# 環境変数/設定ファイル
Glob('.env')
Glob('.env.example')
Glob('settings.yaml') or Glob('config.yaml')
Glob('config/**/*') or Glob('settings/**/*')
```

### 1.5 テストディレクトリの検出

```
Glob('tests/**/*.py') or Glob('tests/**/*.ts')
Glob('test/**/*.py') or Glob('test/**/*.ts')
Glob('__tests__/**/*.ts') or Glob('__tests__/**/*.tsx')
```

### 1.6 検出結果の記録

以下の形式で検出結果を記録する:

```markdown
## プロジェクト検出結果

- CLAUDE.md: {存在する/存在しない}
- 言語: {Python/Node.js/Rust/Go/不明}
- パッケージファイル: {pyproject.toml/package.json/Cargo.toml/go.mod/なし}
- ソースディレクトリ: {検出パス または なし}
- テストディレクトリ: {検出パス または なし}
- 設定ファイル: {検出ファイル または なし}
```

---

## ステップ2: セットアップモードの判定

### 判定ロジック

| CLAUDE.md | ソースDir | モード | 処理内容 |
|-----------|-----------|--------|----------|
| あり | あり | 適合モード | Commands/Skillsの適合のみ |
| なし | あり | 適合モード + CLAUDE.md生成 | CLAUDE.md生成 → 適合 |
| なし | なし | 初期化モード | 全て新規作成 |

### ユーザー確認

AskUserQuestion を使用して以下を確認:

**質問1: セットアップモードの確認**
```
検出結果:
- 言語: {検出された言語}
- ソースディレクトリ: {検出パス}
- 設定ファイル: {検出ファイル}

以下のモードでセットアップを実行しますか？
- モード: {初期化モード/適合モード}
```

オプション:
- `はい、続行する` (推奨)
- `いいえ、中止する`

**質問2: ソースディレクトリの確認（検出されなかった場合のみ）**
```
ソースディレクトリが検出できませんでした。
ソースコードを配置するディレクトリを指定してください:
```

オプション:
- `src/` (推奨)
- `lib/`
- `backend/`
- `app/`
- その他（手動入力）

---

## ステップ3: 基本構成の作成（初期化モードのみ）

### 3.1 ディレクトリ構造の作成

```bash
# 基本ディレクトリの作成
Bash('mkdir -p src tests docs/ideas docs/core .steering')
```

### 3.2 CLAUDE.md の作成

以下のテンプレートで CLAUDE.md を作成:

```markdown
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

{プロジェクト名}は{目的/概要}です。

## Commands

### Running Tests
\`\`\`bash
# Run all tests
{テストコマンド: pytest / npm test / cargo test / go test ./...}
\`\`\`

### Linting/Formatting
\`\`\`bash
{リントコマンド: ruff check . / eslint . / cargo clippy / golangci-lint run}
{フォーマットコマンド: black . / prettier --write . / cargo fmt / gofmt -w .}
\`\`\`

## Architecture

### Key Directories
- `{ソースディレクトリ}/`: ソースコード
- `tests/`: テストコード
- `docs/`: ドキュメント

### Data Flow
{データフローの概要を記載}

## Testing
- テストフレームワーク: {pytest / jest / cargo test / go test}
- テストディレクトリ: `tests/`
```

### 3.3 .env.example の作成

```
# Environment Variables

# Example:
# API_KEY=your_api_key_here
# DATABASE_URL=sqlite:///data/app.db
```

### 3.4 .gitignore の確認

既存の .gitignore がない場合、言語に応じた基本的な .gitignore を作成:

```
# Python
__pycache__/
*.py[cod]
.env
.venv/
dist/
*.egg-info/

# Node.js
node_modules/
.env
dist/

# General
.DS_Store
*.log
```

---

## ステップ4: Commands/Skills の適合

### 4.1 適合対象ファイル

以下のファイルを読み込み、パターン置換を行う:

**スキルファイル:**
- `.claude/skills/**/*.md` (全ファイル)

### 4.2 置換パターン

| 置換対象 | 検索パターン | 置換先 | 説明 |
|----------|--------------|--------|------|
| ソースパス | `backend/` | `{検出されたソースディレクトリ}/` | ソースコードパス |
| テストパス | `tests/` | `{検出されたテストディレクトリ}/` | テストパス |
| Pythonコマンド | `uv run python` | `{検出されたPythonランナー}` | Python実行 |
| テストコマンド | `uv run pytest` | `{検出されたテストコマンド}` | テスト実行 |

### 4.3 言語別のデフォルト置換

**Python (pyproject.toml 検出時):**
```
backend/ → {検出されたソースディレクトリ}/ (例: src/)
uv run pytest → uv run pytest (または pytest)
uv run python → uv run python (または python)
```

**Node.js (package.json 検出時):**
```
backend/ → {検出されたソースディレクトリ}/ (例: src/)
uv run pytest → npm test (または yarn test)
uv run python → node (または npx ts-node)
```

**Go (go.mod 検出時):**
```
backend/ → {検出されたソースディレクトリ}/ (例: cmd/ または internal/)
uv run pytest → go test ./...
uv run python → go run
```

**Rust (Cargo.toml 検出時):**
```
backend/ → src/
uv run pytest → cargo test
uv run python → cargo run
```

### 4.4 settings.local.json の更新

検出された言語/ツールに基づいて settings.local.json を更新:

```json
{
  "permissions": {
    "allow": [
      // 既存の許可を保持しつつ、言語固有の許可を追加/変更
    ]
  }
}
```

### 4.5 適合処理の実行

各対象ファイルに対して:

1. ファイルを読み込む
2. 置換パターンを適用
3. 変更があった場合のみファイルを更新
4. 変更箇所を記録

---

## ステップ5: docs/core/ の準備

### 5.1 ディレクトリの確認

```
Bash('mkdir -p docs/core docs/ideas')
```

### 5.2 /gen-all-docs の案内

完了レポートに以下を含める:

```
ドキュメント生成の案内:
プロジェクトドキュメントを生成するには、以下を実行してください:

/gen-all-docs

これにより以下のドキュメントが生成されます:
- docs/core/architecture.md
- docs/core/api-reference.md
- docs/core/diagrams.md
- docs/core/development-guidelines.md
- docs/core/repository-structure.md
- docs/core/CHANGELOG.md
```

---

## ステップ6: 完了レポートとユーザー確認

**このステップでワークフローは停止する。**

### 6.1 完了レポートの出力

以下の形式でレポートを出力:

```markdown
# セットアップ完了レポート

## 検出されたプロジェクト情報

| 項目 | 値 |
|------|-----|
| 言語 | {Python/Node.js/Go/Rust/不明} |
| パッケージファイル | {pyproject.toml/package.json/go.mod/Cargo.toml/なし} |
| ソースディレクトリ | {検出パス} |
| テストディレクトリ | {検出パス} |
| 設定ファイル | {検出ファイル} |

## 実行されたセットアップ

### モード: {初期化モード/適合モード}

### 作成されたファイル（初期化モードのみ）
- [ ] CLAUDE.md
- [ ] .env.example
- [ ] src/ ディレクトリ
- [ ] tests/ ディレクトリ
- [ ] docs/ideas/ ディレクトリ
- [ ] docs/core/ ディレクトリ
- [ ] .steering/ ディレクトリ

### 適合されたファイル
| ファイル | 変更内容 |
|----------|----------|
| {ファイル名} | {置換内容の要約} |

## 次のステップ

1. **CLAUDE.md を確認・編集**
   - プロジェクト概要を更新
   - コマンド例を確認

2. **ドキュメント生成**
   \`\`\`
   /gen-all-docs
   \`\`\`

3. **機能開発の開始**
   \`\`\`
   /plan-feature [機能名]
   \`\`\`

## 注意事項

- `.claude/` ディレクトリはバージョン管理に含めることを推奨
- `settings.local.json` には個人設定が含まれるため、必要に応じて .gitignore に追加
```

### 6.2 確認待ち状態

ユーザーにレポートを提示して停止する。

---

## CLAUDE.md テンプレート（言語別）

### Python プロジェクト用

```markdown
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

{プロジェクト概要を記載}

## Commands

### Running Tests
\`\`\`bash
pytest
pytest tests/test_example.py
pytest -v
\`\`\`

### Linting/Formatting
\`\`\`bash
ruff check .
black .
mypy .
\`\`\`

## Architecture

### Key Directories
- `src/`: ソースコード
- `tests/`: テストコード
- `docs/`: ドキュメント

### Configuration
- 環境変数: `.env` (`.env.example` を参照)
- 設定: `pyproject.toml`

## Testing
- テストフレームワーク: pytest
- テストディレクトリ: `tests/`
- フィクスチャ: `tests/conftest.py`
```

### Node.js プロジェクト用

```markdown
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

{プロジェクト概要を記載}

## Commands

### Running Tests
\`\`\`bash
npm test
npm run test:watch
\`\`\`

### Linting/Formatting
\`\`\`bash
npm run lint
npm run format
\`\`\`

### Development
\`\`\`bash
npm run dev
\`\`\`

## Architecture

### Key Directories
- `src/`: ソースコード
- `tests/` or `__tests__/`: テストコード
- `docs/`: ドキュメント

### Configuration
- 環境変数: `.env` (`.env.example` を参照)
- パッケージ: `package.json`

## Testing
- テストフレームワーク: Jest / Vitest
- テストディレクトリ: `tests/` or `__tests__/`
```

### Go プロジェクト用

```markdown
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

{プロジェクト概要を記載}

## Commands

### Running Tests
\`\`\`bash
go test ./...
go test -v ./...
go test -cover ./...
\`\`\`

### Linting/Formatting
\`\`\`bash
golangci-lint run
gofmt -w .
\`\`\`

### Build
\`\`\`bash
go build ./...
\`\`\`

## Architecture

### Key Directories
- `cmd/`: エントリーポイント
- `internal/`: 内部パッケージ
- `pkg/`: 公開パッケージ

### Configuration
- 環境変数: `.env` (`.env.example` を参照)
- モジュール: `go.mod`

## Testing
- テストファイル: `*_test.go`
- テーブル駆動テストを推奨
```

### Rust プロジェクト用

```markdown
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

{プロジェクト概要を記載}

## Commands

### Running Tests
\`\`\`bash
cargo test
cargo test -- --nocapture
\`\`\`

### Linting/Formatting
\`\`\`bash
cargo clippy
cargo fmt
\`\`\`

### Build
\`\`\`bash
cargo build
cargo build --release
\`\`\`

## Architecture

### Key Directories
- `src/`: ソースコード
- `tests/`: 統合テスト

### Configuration
- 環境変数: `.env` (`.env.example` を参照)
- パッケージ: `Cargo.toml`

## Testing
- ユニットテスト: 各モジュール内の `#[cfg(test)]`
- 統合テスト: `tests/` ディレクトリ
```

---

## 完了条件

このワークフローは、以下の条件を満たした時点で完了（ユーザー確認待ち）となる:

- プロジェクト状態が検出されている
- セットアップモードが決定されている
- (初期化モードの場合) 基本構成が作成されている
- Commands/Skills が適合されている
- 完了レポートがユーザーに提示されている
