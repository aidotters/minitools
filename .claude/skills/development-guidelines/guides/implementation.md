# 実装ガイド (Implementation Guide)

## Python 規約

### 型ヒント

**組み込み型の使用**:
```python
# ✅ 良い例: Python 3.12+ の組み込み型を使用
def process_items(items: list[str]) -> dict[str, int]:
    """アイテムを処理してカウントを返す"""
    from collections import Counter
    return dict(Counter(items))

# ❌ 悪い例: typing モジュールから非推奨の型をインポート
from typing import List, Dict  # Python 3.9以降は不要
def process_items(items: List[str]) -> Dict[str, int]:
    pass
```

**型注釈の原則**:
```python
# ✅ 良い例: 明示的な型注釈
def calculate_total(prices: list[float]) -> float:
    return sum(prices)

# ❌ 悪い例: 型注釈なし
def calculate_total(prices):  # Any型になる
    return sum(prices)
```

**TypedDict vs dataclass vs Protocol**:
```python
from typing import TypedDict, Protocol, Literal
from dataclasses import dataclass

# TypedDict: 辞書の型定義（外部APIレスポンスなど）
class TaskDict(TypedDict):
    id: str
    title: str
    completed: bool

# dataclass: 内部データモデル（イミュータブル推奨）
@dataclass(frozen=True)
class Task:
    id: str
    title: str
    completed: bool = False

# dataclass の拡張
@dataclass(frozen=True)
class ExtendedTask(Task):
    priority: str = "medium"

# Protocol: 構造的部分型（Duck Typing）
class TaskRepository(Protocol):
    def save(self, task: Task) -> None: ...
    def find_by_id(self, id: str) -> Task | None: ...

# Python 3.12+ type文（型エイリアス）
type TaskStatus = Literal["todo", "in_progress", "completed"]
type TaskId = str
type Nullable[T] = T | None
```

### 命名規則

**変数・関数**:
```python
# 変数: snake_case、名詞
user_name = "John"
task_list = []
is_completed = True

# 関数: snake_case、動詞で始める
def fetch_user_data() -> User: ...
def validate_email(email: str) -> bool: ...
def calculate_total_price(items: list[Item]) -> float: ...

# Boolean: is_, has_, should_, can_ で始める
is_valid = True
has_permission = False
should_retry = True
can_delete = False
```

**クラス・型**:
```python
# クラス: PascalCase、名詞
class TaskManager: ...
class UserAuthenticationService: ...

# Protocol: PascalCase
class TaskRepository(Protocol): ...
class UserProfile(Protocol): ...

# 型エイリアス (Python 3.12+): PascalCase
type TaskStatus = Literal["todo", "in_progress", "completed"]
```

**定数**:
```python
# UPPER_SNAKE_CASE
MAX_RETRY_COUNT = 3
API_BASE_URL = "https://api.example.com"
DEFAULT_TIMEOUT = 5000

# 設定オブジェクトの場合（dataclass + frozen）
from dataclasses import dataclass

@dataclass(frozen=True)
class Config:
    max_retry_count: int = 3
    api_base_url: str = "https://api.example.com"
    default_timeout: int = 5000

CONFIG = Config()
```

**ファイル名**:
```python
# すべて snake_case（PEP 8推奨）
# task_service.py
# user_repository.py
# format_date.py
# validate_email.py

# 定数ファイル: snake_case
# api_endpoints.py
# error_messages.py

# テストファイル: test_ プレフィックス
# test_task_service.py
# tests/test_user_repository.py
```

### 関数設計

**単一責務の原則**:
```python
# ✅ 良い例: 単一の責務
def calculate_total_price(items: list[CartItem]) -> float:
    return sum(item.price * item.quantity for item in items)

def format_price(amount: float) -> str:
    return f"¥{amount:,.0f}"

# ❌ 悪い例: 複数の責務
def calculate_and_format_price(items: list[CartItem]) -> str:
    total = sum(item.price * item.quantity for item in items)
    return f"¥{total:,.0f}"
```

**関数の長さ**:
- 目標: 20行以内
- 推奨: 50行以内
- 100行以上: リファクタリングを検討

**パラメータの数**:
```python
from dataclasses import dataclass
from datetime import date
from typing import Literal

# ✅ 良い例: dataclass でパラメータをまとめる
@dataclass
class CreateTaskOptions:
    title: str
    description: str | None = None
    priority: Literal["high", "medium", "low"] = "medium"
    due_date: date | None = None

def create_task(options: CreateTaskOptions) -> Task:
    """タスクを作成する"""
    ...

# 使用例
task = create_task(CreateTaskOptions(
    title="新しいタスク",
    priority="high"
))

# ❌ 悪い例: パラメータが多すぎる
def create_task(
    title: str,
    description: str,
    priority: str,
    due_date: date,
    tags: list[str],
    assignee: str
) -> Task:
    ...
```

### エラーハンドリング

**カスタム例外クラス**:
```python
from dataclasses import dataclass
from typing import Any

# 例外クラスの定義
@dataclass
class ValidationError(Exception):
    """バリデーションエラー"""
    message: str
    field: str
    value: Any

    def __str__(self) -> str:
        return f"{self.message} (field={self.field}, value={self.value})"

@dataclass
class NotFoundError(Exception):
    """リソースが見つからないエラー"""
    resource: str
    id: str

    def __str__(self) -> str:
        return f"{self.resource} not found: {self.id}"

class DatabaseError(Exception):
    """データベースエラー"""
    def __init__(self, message: str, cause: Exception | None = None):
        super().__init__(message)
        self.__cause__ = cause
```

**エラーハンドリングパターン**:
```python
import logging

logger = logging.getLogger(__name__)

# ✅ 良い例: 適切なエラーハンドリング
async def get_task(id: str) -> Task:
    try:
        task = await repository.find_by_id(id)

        if task is None:
            raise NotFoundError(resource="Task", id=id)

        return task
    except NotFoundError:
        # 予期されるエラー: 適切に処理
        logger.warning(f"タスクが見つかりません: {id}")
        raise
    except Exception as e:
        # 予期しないエラー: ラップして上位に伝播
        raise DatabaseError("タスクの取得に失敗しました", cause=e) from e

# ❌ 悪い例: エラーを無視
async def get_task(id: str) -> Task | None:
    try:
        return await repository.find_by_id(id)
    except Exception:
        return None  # エラー情報が失われる
```

**エラーメッセージ**:
```python
# ✅ 良い例: 具体的で解決策を示す
raise ValidationError(
    message="タイトルは1-200文字で入力してください。現在の文字数: 250",
    field="title",
    value=title
)

# ❌ 悪い例: 曖昧で役に立たない
raise Exception("Invalid input")
```

### 非同期処理

**async/await の使用**:
```python
import asyncio

# ✅ 良い例: async/await
async def fetch_user_tasks(user_id: str) -> list[Task]:
    try:
        user = await user_repository.find_by_id(user_id)
        tasks = await task_repository.find_by_user_id(user.id)
        return tasks
    except Exception as e:
        logger.error("タスクの取得に失敗", exc_info=e)
        raise
```

**並列処理**:
```python
# ✅ 良い例: asyncio.gather で並列実行
async def fetch_multiple_users(ids: list[str]) -> list[User]:
    tasks = [user_repository.find_by_id(id) for id in ids]
    return await asyncio.gather(*tasks)

# ✅ エラーハンドリング付き並列実行
async def fetch_multiple_users_safe(ids: list[str]) -> list[User | None]:
    tasks = [user_repository.find_by_id(id) for id in ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r if not isinstance(r, Exception) else None for r in results]

# ❌ 悪い例: 逐次実行（遅い）
async def fetch_multiple_users(ids: list[str]) -> list[User]:
    users: list[User] = []
    for id in ids:
        user = await user_repository.find_by_id(id)  # 遅い
        users.append(user)
    return users
```

## コメント規約

### ドキュメントコメント

**Google Style Docstring**:
```python
async def create_task(data: CreateTaskData) -> Task:
    """タスクを作成する。

    Args:
        data: 作成するタスクのデータ

    Returns:
        作成されたタスク

    Raises:
        ValidationError: データが不正な場合
        DatabaseError: データベースエラーの場合

    Example:
        >>> task = await create_task(CreateTaskData(
        ...     title="新しいタスク",
        ...     priority="high"
        ... ))
        >>> print(task.id)
        'task-123'
    """
    ...
```

### インラインコメント

**良いコメント**:
```python
# ✅ 理由を説明
# キャッシュを無効化して最新データを取得
cache.clear()

# ✅ 複雑なロジックを説明
# Kadaneのアルゴリズムで最大部分配列和を計算
# 時間計算量: O(n)
max_so_far = arr[0]
max_ending_here = arr[0]

# ✅ TODO・FIXMEを活用
# TODO: キャッシュ機能を実装 (Issue #123)
# FIXME: 大量データでパフォーマンス劣化 (Issue #456)
# HACK: 一時的な回避策、後でリファクタリング必要
```

**悪いコメント**:
```python
# ❌ コードの内容を繰り返すだけ
# iを1増やす
i += 1

# ❌ 古い情報
# このコードは2020年に追加された (不要な情報)

# ❌ コメントアウトされたコード
# old_implementation = lambda: ...  # 削除すべき
```

## セキュリティ

### 入力検証

```python
import re

# ✅ 良い例: 厳密な検証
def validate_email(email: str) -> None:
    if not email or not isinstance(email, str):
        raise ValidationError(
            message="メールアドレスは必須です",
            field="email",
            value=email
        )

    email_regex = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    if not re.match(email_regex, email):
        raise ValidationError(
            message="メールアドレスの形式が不正です",
            field="email",
            value=email
        )

    if len(email) > 254:
        raise ValidationError(
            message="メールアドレスが長すぎます",
            field="email",
            value=email
        )

# ❌ 悪い例: 検証なし
def validate_email(email: str) -> None:
    pass  # 検証なし
```

### 機密情報の管理

```python
import os
from functools import lru_cache
from pydantic_settings import BaseSettings

# ✅ 良い例 1: os.environ + python-dotenv
from dotenv import load_dotenv

load_dotenv()  # .env ファイルを読み込み

api_key = os.environ.get("API_KEY")
if not api_key:
    raise EnvironmentError("API_KEY環境変数が設定されていません")

# ✅ 良い例 2: pydantic-settings（推奨）
class Settings(BaseSettings):
    api_key: str
    database_url: str
    debug: bool = False

    class Config:
        env_file = ".env"

@lru_cache
def get_settings() -> Settings:
    return Settings()

# 使用
settings = get_settings()
print(settings.api_key)

# ❌ 悪い例: ハードコード
api_key = "sk-1234567890abcdef"  # 絶対にしない！
```

## パフォーマンス

### データ構造の選択

```python
# ✅ 良い例: dict で O(1) アクセス
user_map = {u.id: u for u in users}
user = user_map.get(user_id)  # O(1)

# ❌ 悪い例: list で O(n) 検索
user = next((u for u in users if u.id == user_id), None)  # O(n)

# ✅ set でメンバーシップテスト O(1)
valid_ids = {u.id for u in valid_users}
if user_id in valid_ids:  # O(1)
    ...

# ❌ list でメンバーシップテスト O(n)
valid_ids = [u.id for u in valid_users]
if user_id in valid_ids:  # O(n)
    ...
```

### ループの最適化

```python
# ✅ 良い例: リスト内包表記
result = [process(item) for item in items]

# ✅ 良い例: ジェネレータ式（メモリ効率）
result = (process(item) for item in items)

# ❌ 悪い例: 手動でリスト構築
result = []
for item in items:
    result.append(process(item))
```

### メモ化

```python
from functools import lru_cache, cache

# Python 3.9+ @cache（無制限キャッシュ）
@cache
def expensive_calculation(input: str) -> Result:
    """重い計算"""
    ...

# @lru_cache（サイズ制限付き）
@lru_cache(maxsize=128)
def expensive_calculation(input: str) -> Result:
    """重い計算"""
    ...

# 非同期関数用のカスタムキャッシュ
from asyncio import Lock

_cache: dict[str, Result] = {}
_lock = Lock()

async def expensive_calculation_async(input: str) -> Result:
    async with _lock:
        if input in _cache:
            return _cache[input]
        result = await compute(input)
        _cache[input] = result
        return result
```

## テストコード

### テストの構造 (Given-When-Then)

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

class TestTaskService:
    """TaskService のテスト"""

    @pytest.fixture
    def mock_repository(self) -> MagicMock:
        """モックリポジトリを作成"""
        return MagicMock(spec=TaskRepository)

    @pytest.fixture
    def service(self, mock_repository: MagicMock) -> TaskService:
        """テスト対象のサービスを作成"""
        return TaskService(mock_repository)

    async def test_create_with_valid_data_returns_task(
        self,
        service: TaskService,
        mock_repository: MagicMock
    ) -> None:
        """正常なデータでタスクを作成できる"""
        # Given: 準備
        task_data = CreateTaskData(
            title="テストタスク",
            description="テスト用の説明",
        )
        mock_repository.save = AsyncMock(return_value=Task(
            id="task-123",
            title="テストタスク",
            description="テスト用の説明",
            created_at=datetime.now()
        ))

        # When: 実行
        result = await service.create(task_data)

        # Then: 検証
        assert result is not None
        assert result.id == "task-123"
        assert result.title == "テストタスク"
        assert result.description == "テスト用の説明"
        assert isinstance(result.created_at, datetime)

    async def test_create_with_empty_title_raises_validation_error(
        self,
        service: TaskService
    ) -> None:
        """タイトルが空の場合ValidationErrorをスローする"""
        # Given: 準備
        invalid_data = CreateTaskData(title="")

        # When/Then: 実行と検証
        with pytest.raises(ValidationError) as exc_info:
            await service.create(invalid_data)

        assert exc_info.value.field == "title"
```

### パラメータ化テスト

```python
@pytest.mark.parametrize("title,expected_error", [
    ("", "タイトルは必須です"),
    ("a" * 201, "タイトルは200文字以内です"),
    ("   ", "タイトルは空白のみにできません"),
])
async def test_validate_title_invalid_cases(
    title: str,
    expected_error: str,
    service: TaskService
) -> None:
    """無効なタイトルでValidationErrorをスローする"""
    with pytest.raises(ValidationError) as exc_info:
        await service.create(CreateTaskData(title=title))

    assert expected_error in str(exc_info.value)
```

### モックの作成

```python
from unittest.mock import MagicMock, AsyncMock, patch

# ✅ 良い例: Protocol に基づくモック
mock_repository = MagicMock(spec=TaskRepository)

# 非同期メソッドのモック
mock_repository.find_by_id = AsyncMock(return_value=mock_task)
mock_repository.save = AsyncMock()

# テストごとに動作を設定
@pytest.fixture
def mock_repository() -> MagicMock:
    repo = MagicMock(spec=TaskRepository)

    async def find_by_id_side_effect(id: str) -> Task | None:
        if id == "existing-id":
            return mock_task
        return None

    repo.find_by_id = AsyncMock(side_effect=find_by_id_side_effect)
    return repo
```

## リファクタリング

### マジックナンバーの排除

```python
# ✅ 良い例: 定数を定義
MAX_RETRY_COUNT = 3
RETRY_DELAY_SECONDS = 1.0

for i in range(MAX_RETRY_COUNT):
    try:
        return await fetch_data()
    except Exception:
        if i < MAX_RETRY_COUNT - 1:
            await asyncio.sleep(RETRY_DELAY_SECONDS)

# ❌ 悪い例: マジックナンバー
for i in range(3):
    try:
        return await fetch_data()
    except Exception:
        if i < 2:
            await asyncio.sleep(1.0)
```

### 関数の抽出

```python
# ✅ 良い例: 関数を抽出
def process_order(order: Order) -> None:
    validate_order(order)
    calculate_total(order)
    apply_discounts(order)
    save_order(order)

def validate_order(order: Order) -> None:
    if not order.items:
        raise ValidationError(
            message="商品が選択されていません",
            field="items",
            value=order.items
        )

def calculate_total(order: Order) -> None:
    order.total = sum(
        item.price * item.quantity
        for item in order.items
    )

# ❌ 悪い例: 長い関数
def process_order(order: Order) -> None:
    if not order.items:
        raise ValidationError(
            message="商品が選択されていません",
            field="items",
            value=order.items
        )

    order.total = sum(
        item.price * item.quantity
        for item in order.items
    )

    if order.coupon:
        order.total -= order.total * order.coupon.discount_rate

    repository.save(order)
```

## チェックリスト

実装完了前に確認:

### コード品質
- [ ] 命名が明確で一貫している（PEP 8準拠）
- [ ] 関数が単一の責務を持っている
- [ ] マジックナンバーがない
- [ ] 型ヒントが適切に記載されている
- [ ] エラーハンドリングが実装されている

### セキュリティ
- [ ] 入力検証が実装されている
- [ ] 機密情報がハードコードされていない
- [ ] SQLインジェクション対策がされている

### パフォーマンス
- [ ] 適切なデータ構造を使用している
- [ ] 不要な計算を避けている
- [ ] ループが最適化されている

### テスト
- [ ] ユニットテストが書かれている
- [ ] テストがパスする
- [ ] エッジケースがカバーされている

### ドキュメント
- [ ] 関数・クラスにDocstringがある
- [ ] 複雑なロジックにコメントがある
- [ ] TODOやFIXMEが記載されている(該当する場合)

### ツール
- [ ] Ruffエラーがない
- [ ] mypyエラーがない
- [ ] フォーマットが統一されている
