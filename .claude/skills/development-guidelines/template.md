# 開発ガイドライン (Development Guidelines)

## コーディング規約

### 命名規則

#### 変数・関数

**Python**:
```python
# ✅ 良い例
user_profile_data = fetch_user_profile()
def calculate_total_price(items: list[CartItem]) -> float: ...

# ❌ 悪い例
data = fetch()
def calc(arr: list) -> float: ...
```

**原則**:
- 変数: snake_case、名詞または名詞句
- 関数: snake_case、動詞で始める
- 定数: UPPER_SNAKE_CASE
- Boolean: `is_`, `has_`, `should_`で始める

#### クラス・型

```python
from typing import Protocol, Literal
from dataclasses import dataclass

# クラス: PascalCase、名詞
class TaskManager: ...
class UserAuthenticationService: ...

# Protocol: PascalCase
class TaskRepository(Protocol):
    def save(self, task: Task) -> None: ...
    def find_by_id(self, id: str) -> Task | None: ...

# 型エイリアス: PascalCase (Python 3.12+)
type TaskStatus = Literal["todo", "in_progress", "completed"]
```

### コードフォーマット

**インデント**: 4スペース（PEP 8準拠）

**行の長さ**: 最大100文字

**例**:
```python
# リスト内包表記
result = [
    process_item(item)
    for item in items
    if item.is_valid
]

# 長い関数呼び出し
response = await client.send_request(
    endpoint="/api/tasks",
    method="POST",
    body={"title": title, "priority": priority},
    headers=headers,
)
```

### コメント規約

**関数・クラスのドキュメント (Google Style Docstring)**:
```python
def count_tasks(
    tasks: list[Task],
    filter: TaskFilter | None = None
) -> int:
    """タスクの合計数を計算する。

    Args:
        tasks: 計算対象のタスクリスト
        filter: フィルター条件（オプション）

    Returns:
        タスクの合計数

    Raises:
        ValidationError: タスクリストが不正な場合
    """
    # 実装
```

**インラインコメント**:
```python
# ✅ 良い例: なぜそうするかを説明
# キャッシュを無効化して、最新データを取得
cache.clear()

# ❌ 悪い例: 何をしているか(コードを見れば分かる)
# キャッシュをクリアする
cache.clear()
```

### エラーハンドリング

**原則**:
- 予期されるエラー: 適切な例外クラスを定義
- 予期しないエラー: 上位に伝播
- エラーを無視しない

**例**:
```python
from dataclasses import dataclass
from typing import Any

# 例外クラス定義
@dataclass
class ValidationError(Exception):
    """バリデーションエラー"""
    message: str
    field: str
    value: Any

    def __str__(self) -> str:
        return f"{self.message} (field={self.field}, value={self.value})"

# エラーハンドリング
try:
    task = await task_service.create(data)
except ValidationError as e:
    print(f"検証エラー [{e.field}]: {e.message}")
    # ユーザーにフィードバック
except Exception as e:
    print(f"予期しないエラー: {e}")
    raise  # 上位に伝播
```

## Git運用ルール

### ブランチ戦略

**ブランチ種別**:
- `main`: 本番環境にデプロイ可能な状態
- `develop`: 開発の最新状態
- `feature/[機能名]`: 新機能開発
- `fix/[修正内容]`: バグ修正
- `refactor/[対象]`: リファクタリング

**フロー**:
```
main
  └─ develop
      ├─ feature/task-management
      ├─ feature/user-auth
      └─ fix/task-validation
```

### コミットメッセージ規約

**フォーマット**:
```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type**:
- `feat`: 新機能
- `fix`: バグ修正
- `docs`: ドキュメント
- `style`: コードフォーマット
- `refactor`: リファクタリング
- `test`: テスト追加・修正
- `chore`: ビルド、補助ツール等

**例**:
```
feat(task): タスクの優先度設定機能を追加

ユーザーがタスクに優先度(高/中/低)を設定できるようにしました。
- Taskモデルにpriorityフィールドを追加
- CLIに--priorityオプションを追加
- 優先度によるソート機能を実装

Closes #123
```

### プルリクエストプロセス

**作成前のチェック**:
- [ ] 全てのテストがパス
- [ ] Ruffエラーがない
- [ ] mypyエラーがない
- [ ] 競合が解決されている

**PRテンプレート**:
```markdown
## 概要
[変更内容の簡潔な説明]

## 変更理由
[なぜこの変更が必要か]

## 変更内容
- [変更点1]
- [変更点2]

## テスト
- [ ] ユニットテスト追加
- [ ] 手動テスト実施

## スクリーンショット(該当する場合)
[画像]

## 関連Issue
Closes #[Issue番号]
```

**レビュープロセス**:
1. セルフレビュー
2. 自動テスト実行
3. レビュアーアサイン
4. レビューフィードバック対応
5. 承認後マージ

## テスト戦略

### テストの種類

#### ユニットテスト

**対象**: 個別の関数・クラス

**カバレッジ目標**: [80/90/100]%

**例 (pytest)**:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock

class TestTaskService:
    """TaskService のテスト"""

    class TestCreate:
        """create メソッドのテスト"""

        async def test_with_valid_data_creates_task(
            self,
            service: TaskService,
            mock_repository: MagicMock
        ) -> None:
            """正常なデータでタスクを作成できる"""
            task = await service.create(CreateTaskData(
                title="テストタスク",
                description="説明",
            ))

            assert task.id is not None
            assert task.title == "テストタスク"

        async def test_with_empty_title_raises_validation_error(
            self,
            service: TaskService
        ) -> None:
            """タイトルが空の場合ValidationErrorをスローする"""
            with pytest.raises(ValidationError):
                await service.create(CreateTaskData(title=""))
```

#### 統合テスト

**対象**: 複数コンポーネントの連携

**例**:
```python
class TestTaskCRUD:
    """タスクCRUD操作の統合テスト"""

    async def test_full_lifecycle(
        self,
        task_service: TaskService
    ) -> None:
        """タスクの作成・取得・更新・削除ができる"""
        # 作成
        created = await task_service.create(CreateTaskData(title="テスト"))

        # 取得
        found = await task_service.find_by_id(created.id)
        assert found is not None
        assert found.title == "テスト"

        # 更新
        await task_service.update(created.id, UpdateTaskData(title="更新後"))
        updated = await task_service.find_by_id(created.id)
        assert updated is not None
        assert updated.title == "更新後"

        # 削除
        await task_service.delete(created.id)
        deleted = await task_service.find_by_id(created.id)
        assert deleted is None
```

#### E2Eテスト

**対象**: ユーザーシナリオ全体

**例**:
```python
class TestTaskManagementFlow:
    """タスク管理フローのE2Eテスト"""

    async def test_user_can_add_and_complete_task(
        self,
        cli: CLI
    ) -> None:
        """ユーザーがタスクを追加して完了できる"""
        # タスク追加
        result = await cli.run(["add", "新しいタスク"])
        assert "タスクを追加しました" in result.output

        # タスク一覧表示
        result = await cli.run(["list"])
        assert "新しいタスク" in result.output

        # タスク完了
        result = await cli.run(["complete", "1"])
        assert "タスクを完了しました" in result.output
```

### テスト命名規則

**パターン**: `test_[対象]_[条件]_[期待結果]` または日本語docstring

**例**:
```python
# ✅ 良い例
async def test_create_with_empty_title_raises_validation_error(self) -> None:
    """タイトルが空の場合ValidationErrorをスローする"""
    ...

async def test_find_by_id_with_existing_id_returns_task(self) -> None:
    """存在するIDの場合タスクを返す"""
    ...

async def test_delete_with_non_existent_id_raises_not_found_error(self) -> None:
    """存在しないIDの場合NotFoundErrorをスローする"""
    ...

# ❌ 悪い例
async def test_1(self) -> None: ...
async def test_works(self) -> None: ...
async def test_should_work_correctly(self) -> None: ...
```

### モック・スタブの使用

**原則**:
- 外部依存(API、DB、ファイルシステム)はモック化
- ビジネスロジックは実装を使用

**例**:
```python
from unittest.mock import MagicMock, AsyncMock
import pytest

@pytest.fixture
def mock_repository() -> MagicMock:
    """リポジトリをモック化"""
    repo = MagicMock(spec=TaskRepository)
    repo.save = AsyncMock()
    repo.find_by_id = AsyncMock(return_value=None)
    repo.find_all = AsyncMock(return_value=[])
    repo.delete = AsyncMock()
    return repo

@pytest.fixture
def service(mock_repository: MagicMock) -> TaskService:
    """サービスは実際の実装を使用"""
    return TaskService(mock_repository)
```

## コードレビュー基準

### レビューポイント

**機能性**:
- [ ] 要件を満たしているか
- [ ] エッジケースが考慮されているか
- [ ] エラーハンドリングが適切か

**可読性**:
- [ ] 命名が明確か
- [ ] Docstringが適切か
- [ ] 複雑なロジックが説明されているか

**保守性**:
- [ ] 重複コードがないか
- [ ] 責務が明確に分離されているか
- [ ] 変更の影響範囲が限定的か

**パフォーマンス**:
- [ ] 不要な計算がないか
- [ ] メモリリークの可能性がないか
- [ ] データベースクエリが最適化されているか

**セキュリティ**:
- [ ] 入力検証が適切か
- [ ] 機密情報がハードコードされていないか
- [ ] 権限チェックが実装されているか

### レビューコメントの書き方

**建設的なフィードバック**:
```markdown
## ✅ 良い例
この実装だと、タスク数が増えた時にパフォーマンスが劣化する可能性があります。
代わりに、dictを使った検索を検討してはどうでしょうか？

```python
task_map = {t.id: t for t in tasks}
result = task_map.get(task_id)
```

## ❌ 悪い例
この書き方は良くないです。
```

**優先度の明示**:
- `[必須]`: 修正必須
- `[推奨]`: 修正推奨
- `[提案]`: 検討してほしい
- `[質問]`: 理解のための質問

## 開発環境セットアップ

### 必要なツール

| ツール | バージョン | インストール方法 |
|--------|-----------|-----------------|
| Python | 3.12+ | pyenv, asdf, または公式インストーラー |
| uv | 最新 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Ruff | 0.8+ | `uv add --dev ruff` |
| mypy | 1.14+ | `uv add --dev mypy` |
| pytest | 8.0+ | `uv add --dev pytest` |

### セットアップ手順

```bash
# 1. リポジトリのクローン
git clone [URL]
cd [project-name]

# 2. Python環境のセットアップ
uv sync

# 3. 開発用依存関係のインストール
uv sync --dev

# 4. 環境変数の設定
cp .env.example .env
# .envファイルを編集

# 5. pre-commitフックのインストール
pre-commit install

# 6. テストの実行
pytest
```

### 推奨開発ツール（該当する場合）

- **VSCode + Pylance**: Python開発の推奨IDE
- **Ruff Extension**: リアルタイムのLint・フォーマット
- **mypy Extension**: リアルタイムの型チェック
