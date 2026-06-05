# プロセスガイド (Process Guide)

## 基本原則

### 1. 具体例を豊富に含める

抽象的なルールだけでなく、具体的なコード例を提示します。

**悪い例**:
```
変数名は分かりやすくすること
```

**良い例**:
```python
# ✅ 良い例: 役割が明確
user_authentication = UserAuthenticationService()
task_repository = TaskRepository()

# ❌ 悪い例: 曖昧
auth = Service()
repo = Repository()
```

### 2. 理由を説明する

「なぜそうするのか」を明確にします。

**例**:
```
## エラーを無視しない

理由: エラーを無視すると、問題の原因究明が困難になります。
予期されるエラーは適切に処理し、予期しないエラーは上位に伝播させて
ログに記録できるようにします。
```

### 3. 測定可能な基準を設定

曖昧な表現を避け、具体的な数値を示します。

**悪い例**:
```
コードカバレッジは高く保つこと
```

**良い例**:
```
コードカバレッジ目標:
- ユニットテスト: 80%以上
- 統合テスト: 60%以上
- E2Eテスト: 主要フロー100%
```

## Git運用ルール

### ブランチ戦略（Git Flow採用）

**Git Flowとは**:
Vincent Driessenが提唱した、機能開発・リリース・ホットフィックスを体系的に管理するブランチモデル。明確な役割分担により、チーム開発での並行作業と安定したリリースを実現します。

**ブランチ構成**:
```
main (本番環境)
└── develop (開発・統合環境)
    ├── feature/* (新機能開発)
    ├── fix/* (バグ修正)
    └── release/* (リリース準備)※必要に応じて
```

**運用ルール**:
- **main**: 本番リリース済みの安定版コードのみを保持。タグでバージョン管理
- **develop**: 次期リリースに向けた最新の開発コードを統合。CIでの自動テスト実施
- **feature/\*、fix/\***: developから分岐し、作業完了後にPRでdevelopへマージ
- **直接コミット禁止**: すべてのブランチでPRレビューを必須とし、コード品質を担保
- **マージ方針**: feature→develop は squash merge、develop→main は merge commit を推奨

**Git Flowのメリット**:
- ブランチの役割が明確で、複数人での並行開発がしやすい
- 本番環境(main)が常にクリーンな状態に保たれる
- 緊急対応時はhotfixブランチで迅速に対応可能（必要に応じて導入）

### コミットメッセージの規約

**Conventional Commitsを推奨**:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type一覧**:
```
feat: 新機能 (minor version up)
fix: バグ修正 (patch version up)
docs: ドキュメント
style: フォーマット (コードの動作に影響なし)
refactor: リファクタリング
perf: パフォーマンス改善
test: テスト追加・修正
build: ビルドシステム
ci: CI/CD設定
chore: その他 (依存関係更新など)

BREAKING CHANGE: 破壊的変更 (major version up)
```

**良いコミットメッセージの例**:

```
feat(task): 優先度設定機能を追加

ユーザーがタスクに優先度(高/中/低)を設定できるようになりました。

実装内容:
- Taskモデルにpriorityフィールド追加
- CLI に --priority オプション追加
- 優先度によるソート機能実装

破壊的変更:
- Task型の構造が変更されました
- 既存のタスクデータはマイグレーションが必要です

Closes #123
BREAKING CHANGE: Task型にpriority必須フィールド追加
```

### プルリクエストのテンプレート

**効果的なPRテンプレート**:

```markdown
## 変更の種類
- [ ] 新機能 (feat)
- [ ] バグ修正 (fix)
- [ ] リファクタリング (refactor)
- [ ] ドキュメント (docs)
- [ ] その他 (chore)

## 変更内容
### 何を変更したか
[簡潔な説明]

### なぜ変更したか
[背景・理由]

### どのように変更したか
- [変更点1]
- [変更点2]

## テスト
### 実施したテスト
- [ ] ユニットテスト追加
- [ ] 統合テスト追加
- [ ] 手動テスト実施

### テスト結果
[テスト結果の説明]

## 関連Issue
Closes #[番号]
Refs #[番号]

## レビューポイント
[レビュアーに特に見てほしい点]
```

## テスト戦略

### テストピラミッド

```
       /\
      /E2E\       少 (遅い、高コスト)
     /------\
    / 統合   \     中
   /----------\
  / ユニット   \   多 (速い、低コスト)
 /--------------\
```

**目標比率**:
- ユニットテスト: 70%
- 統合テスト: 20%
- E2Eテスト: 10%

### テストの書き方

**Given-When-Then パターン (pytest)**:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

class TestTaskService:
    """TaskService のテスト"""

    class TestCreate:
        """タスク作成のテスト"""

        async def test_with_valid_data_creates_task(
            self,
            service: TaskService,
            mock_repository: MagicMock
        ) -> None:
            """正常なデータの場合、タスクを作成できる"""
            # Given: 準備
            valid_data = CreateTaskData(title="テスト")

            # When: 実行
            result = await service.create(valid_data)

            # Then: 検証
            assert result.id is not None
            assert result.title == "テスト"

        async def test_with_empty_title_raises_validation_error(
            self,
            service: TaskService
        ) -> None:
            """タイトルが空の場合、ValidationErrorをスローする"""
            # Given: 準備
            invalid_data = CreateTaskData(title="")

            # When/Then: 実行と検証
            with pytest.raises(ValidationError):
                await service.create(invalid_data)
```

### カバレッジ目標

**測定可能な目標 (pyproject.toml)**:

```toml
[tool.pytest.ini_options]
minversion = "8.0"
addopts = [
    "-ra",
    "-q",
    "--strict-markers",
    "--strict-config",
    "--cov=src",
    "--cov-report=term-missing",
    "--cov-report=html",
    "--cov-fail-under=80",
]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.coverage.run]
source = ["src"]
branch = true
omit = ["*/__init__.py", "*/tests/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
    "if __name__ == .__main__.:",
]
fail_under = 80
```

**理由**:
- 重要なビジネスロジック(src/)は高いカバレッジを要求
- UI層は低めでも許容
- 100%を目指さない (コストと効果のバランス)

## コードレビュープロセス

### レビューの目的

1. **品質保証**: バグの早期発見
2. **知識共有**: チーム全体でコードベースを理解
3. **学習機会**: ベストプラクティスの共有

### 効果的なレビューのポイント

**レビュアー向け**:

1. **建設的なフィードバック**
```markdown
## ❌ 悪い例
このコードはダメです。

## ✅ 良い例
この実装だと O(n²) の時間計算量になります。
dict を使うと O(n) に改善できます:

```python
task_map = {t.id: t for t in tasks}
result = [task_map.get(id) for id in ids]
```
```

2. **優先度の明示**
```markdown
[必須] セキュリティ: パスワードがログに出力されています
[推奨] パフォーマンス: ループ内でのDB呼び出しを避けましょう
[提案] 可読性: この関数名をもっと明確にできませんか？
[質問] この処理の意図を教えてください
```

3. **ポジティブなフィードバックも**
```markdown
✨ この実装は分かりやすいですね！
👍 エッジケースがしっかり考慮されています
💡 このパターンは他でも使えそうです
```

**レビュイー向け**:

1. **セルフレビューを実施**
   - PR作成前に自分でコードを見直す
   - 説明が必要な箇所にコメントを追加

2. **小さなPRを心がける**
   - 1PR = 1機能
   - 変更ファイル数: 10ファイル以内を推奨
   - 変更行数: 300行以内を推奨

3. **説明を丁寧に**
   - なぜこの実装にしたか
   - 検討した代替案
   - 特に見てほしいポイント

### レビュー時間の目安

- 小規模PR (100行以下): 15分
- 中規模PR (100-300行): 30分
- 大規模PR (300行以上): 1時間以上

**原則**: 大規模PRは避け、分割する

## 自動化の推進（該当する場合）

### 品質チェックの自動化

**自動化項目と採用ツール**:

1. **Lint・フォーマット**
   - **Ruff**
     - Python用の超高速リンター＋フォーマッター
     - flake8, isort, black, pyupgrade を統合
     - 設定ファイル: `pyproject.toml`

2. **型チェック**
   - **mypy**
     - Python の静的型チェッカー
     - `mypy --strict`で厳密な型チェック
     - 設定ファイル: `pyproject.toml`

3. **テスト実行**
   - **pytest**
     - Python標準のテストフレームワーク
     - 非同期テスト対応（pytest-asyncio）
     - カバレッジ測定（pytest-cov）

4. **パッケージ管理**
   - **uv**
     - Rust製の超高速パッケージ管理ツール
     - pip/pip-tools/poetry の代替
     - ロックファイル: `uv.lock`

5. **Gitフック**
   - **pre-commit**
     - コミット前の自動チェック
     - 設定ファイル: `.pre-commit-config.yaml`

**実装方法**:

**1. pyproject.toml 設定**
```toml
[project]
name = "your-project"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[project.optional-dependencies]
dev = [
    "ruff>=0.8.0",
    "mypy>=1.14.0",
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=6.0.0",
    "pre-commit>=4.0.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

# ========== Ruff 設定 ==========
[tool.ruff]
target-version = "py312"
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = [
    "E",      # pycodestyle errors
    "W",      # pycodestyle warnings
    "F",      # Pyflakes
    "I",      # isort
    "B",      # flake8-bugbear
    "C4",     # flake8-comprehensions
    "UP",     # pyupgrade
    "ARG",    # flake8-unused-arguments
    "SIM",    # flake8-simplify
    "TCH",    # flake8-type-checking
    "PTH",    # flake8-use-pathlib
    "ERA",    # eradicate (commented-out code)
    "PL",     # Pylint
    "RUF",    # Ruff-specific rules
]
ignore = [
    "E501",    # line too long (formatter handles this)
    "PLR0913", # too many arguments
]

[tool.ruff.lint.isort]
known-first-party = ["src"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
skip-magic-trailing-comma = false
line-ending = "auto"

# ========== mypy 設定 ==========
[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_ignores = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_configs = true
show_error_codes = true
show_column_numbers = true

[[tool.mypy.overrides]]
module = ["tests.*"]
disallow_untyped_defs = false

# ========== pytest 設定 ==========
[tool.pytest.ini_options]
minversion = "8.0"
addopts = [
    "-ra",
    "-q",
    "--strict-markers",
    "--strict-config",
]
testpaths = ["tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
```

**2. pre-commit 設定**
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.4
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.14.0
    hooks:
      - id: mypy
        additional_dependencies: []
        args: [--config-file=pyproject.toml]
```

**3. CI/CD (GitHub Actions)**
```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"
      - run: uv sync --dev
      - run: ruff check .
      - run: ruff format --check .

  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"
      - run: uv sync --dev
      - run: mypy src/

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"
      - run: uv sync --dev
      - run: pytest --cov=src --cov-report=xml
      - uses: codecov/codecov-action@v4
        with:
          files: ./coverage.xml
```

**導入効果**:
- コミット前に自動チェックが走り、不具合コードの混入を防止
- PR作成時に自動でCI実行され、マージ前に品質を担保
- 早期発見により、修正コストを最大80%削減（バグ検出が本番後の場合と比較）

**この構成を選んだ理由**:
- 2025年時点でのPythonエコシステムにおける最新かつモダンな構成
- Ruffは従来ツール（flake8, black, isort）を統合し、設定の衝突が少ない
- uvは従来のpip/poetryより10-100倍高速
- 開発体験と実行速度のバランスが優れている

## チェックリスト

- [ ] ブランチ戦略が決まっている
- [ ] コミットメッセージ規約が明確である
- [ ] PRテンプレートが用意されている
- [ ] テストの種類とカバレッジ目標が設定されている
- [ ] コードレビュープロセスが定義されている
- [ ] CI/CDパイプラインが構築されている
