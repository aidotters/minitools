# アーキテクチャ設計ガイド

## 基本原則

### 1. 技術選定には理由を明記

**悪い例**:
```
- Python
- uv
```

**良い例**:
```
- Python 3.12+
  - 型ヒント（PEP 695）の完全サポートにより、コードの可読性と保守性が向上
  - asyncio による非同期I/O処理で高いパフォーマンスを発揮
  - 豊富なエコシステムで必要なライブラリの入手が容易

- uv 0.5+
  - Rust製の高速パッケージマネージャで、pip比で10-100倍高速
  - pyproject.toml による統一的な依存関係管理
  - lock ファイルによる再現可能なビルド環境

- Ruff 0.8+
  - Rust製の高速リンター/フォーマッターで、flake8/black/isortを統合
  - 1秒以内でプロジェクト全体をチェック可能
  - pyproject.toml で一元管理

- mypy 1.14+
  - 静的型チェックによりランタイムエラーを事前に検出
  - IDE補完との連携で開発効率向上
```

### 2. レイヤー分離の原則

各レイヤーの責務を明確にし、依存関係を一方向に保ちます:

```
UI → Service → Data (OK)
UI ← Service (NG)
UI → Data (NG)
```

### 3. 測定可能な要件

すべてのパフォーマンス要件は測定可能な形で記述します。

## レイヤードアーキテクチャの設計

### 各レイヤーの責務

**UIレイヤー**:
```python
# 責務: ユーザー入力の受付とバリデーション
class CLI:
    def __init__(self, task_service: TaskService) -> None:
        self.task_service = task_service

    # OK: サービスレイヤーを呼び出す
    async def add_task(self, title: str) -> None:
        task = await self.task_service.create(CreateTaskData(title=title))
        print(f"Created: {task.id}")

    # NG: データレイヤーを直接呼び出す
    # async def add_task(self, title: str) -> None:
    #     task = await self.repository.save({"title": title})  # ❌
```

**サービスレイヤー**:
```python
# 責務: ビジネスロジックの実装
class TaskService:
    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository

    # ビジネスロジック: 優先度の自動推定
    async def create(self, data: CreateTaskData) -> Task:
        task = Task(
            id=str(uuid4()),
            title=data.title,
            estimated_priority=self._estimate_priority(data),
        )
        await self.repository.save(task)
        return task
```

**データレイヤー**:
```python
# 責務: データの永続化
class TaskRepository:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    async def save(self, task: Task) -> None:
        await self.storage.write(task)
```

## パフォーマンス要件の設定

### 具体的な数値目標

```
コマンド実行時間: 100ms以内(平均的なPC環境で)
└─ 測定方法: time モジュールでCLI起動から結果表示まで計測
└─ 測定環境: CPU Core i5相当、メモリ8GB、SSD

タスク一覧表示: 1000件まで1秒以内
└─ 測定方法: 1000件のダミーデータで計測
└─ 許容範囲: 100件で100ms、1000件で1秒、10000件で10秒
```

## セキュリティ設計

### データ保護の3原則

1. **最小権限の原則**
```bash
# ファイルパーミッション
chmod 600 ~/.devtask/tasks.json  # 所有者のみ読み書き
```

2. **入力検証**
```python
def validate_title(title: str) -> None:
    """タイトルのバリデーション"""
    if not title or len(title) == 0:
        raise ValidationError("タイトルは必須です")
    if len(title) > 200:
        raise ValidationError("タイトルは200文字以内です")
```

3. **機密情報の管理**
```bash
# 環境変数で管理
export DEVTASK_API_KEY="xxxxx"  # コード内にハードコードしない
```

## スケーラビリティ設計

### データ増加への対応

**想定データ量**: [例: 10,000件のタスク]

**対策**:
- データのページネーション
- 古いデータのアーカイブ
- インデックスの最適化

```python
from datetime import datetime

# アーカイブ機能の例: 古いタスクを別ファイルに移動
class ArchiveService:
    def __init__(
        self,
        repository: TaskRepository,
        archive_storage: ArchiveStorage,
    ) -> None:
        self.repository = repository
        self.archive_storage = archive_storage

    async def archive_completed_tasks(self, older_than: datetime) -> None:
        old_tasks = await self.repository.find_completed(older_than)
        await self.archive_storage.save(old_tasks)
        await self.repository.delete_many([t.id for t in old_tasks])
```

## 依存関係管理

### バージョン管理方針

```toml
# pyproject.toml
[project]
dependencies = [
    "click>=8.0.0,<9.0.0",   # マイナーバージョンアップは許可
    "rich==13.7.0",          # 破壊的変更のリスクがある場合は固定
]

[project.optional-dependencies]
dev = [
    "ruff>=0.8.0",           # 開発ツールは最新を許可
    "mypy>=1.14.0",
    "pytest>=8.0.0",
]
```

**方針**:
- 安定版は範囲指定（>=x.y.z,<x+1.0.0）
- 破壊的変更のリスクがある場合は完全固定（==x.y.z）
- 開発ツールは最新を許可（>=x.y.z）

## チェックリスト

- [ ] すべての技術選定に理由が記載されている
- [ ] レイヤードアーキテクチャが明確に定義されている
- [ ] パフォーマンス要件が測定可能である
- [ ] セキュリティ考慮事項が記載されている
- [ ] スケーラビリティが考慮されている
- [ ] バックアップ戦略が定義されている
- [ ] 依存関係管理のポリシーが明確である
- [ ] テスト戦略が定義されている
