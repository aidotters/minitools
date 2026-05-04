# 開発ガイドライン

このドキュメントは、minitoolsプロジェクトのコーディング規約とパターンを説明します。

## コーディング規約

### 命名規則

```python
# クラス名: パスカルケース
class ArxivCollector:
class MediumCollector:
class NotionPublisher:

# 関数/メソッド名: スネークケース
def get_alerts_emails(self, hours_back: int = 6):
async def fetch_article_content(self, url: str):
def _extract_body(self, message: Dict):  # プライベートメソッドは_プレフィックス

# 定数: 大文字スネークケース
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
USER_AGENTS = [...]
MLX_WHISPER_AVAILABLE = True

# 変数名: スネークケース
article_content = ""
processed_papers = []
```

### 型ヒント

すべての関数/メソッドに型ヒントを付与:

```python
from typing import List, Dict, Optional, Any, Tuple

def search(self, queries: List[str], start_date: str, end_date: str,
           max_results: int = 50) -> List[Dict[str, str]]:
    """検索を実行"""
    pass

async def translate_to_japanese(self, text: str, context: str = "") -> str:
    """日本語に翻訳"""
    pass

def _normalize_url_by_source(self, url: str) -> str:
    """URL正規化"""
    pass

async def check_existing(self, database_id: str, url: str) -> bool:
    """重複チェック"""
    pass
```

### Docstring

Google スタイルの docstring を使用:

```python
def search(self, queries: List[str], start_date: str, end_date: str,
           max_results: int = 50) -> List[Dict[str, str]]:
    """
    arXiv APIを使用して論文を検索

    Args:
        queries: 検索語のリスト
        start_date: 検索開始日（YYYYMMDD形式）
        end_date: 検索終了日（YYYYMMDD形式）
        max_results: 取得する最大結果数

    Returns:
        検索結果の論文情報のリスト

    Raises:
        requests.RequestException: API呼び出しに失敗した場合
    """
    pass
```

### データクラス

構造化データには dataclass を使用:

```python
from dataclasses import dataclass
from typing import List

@dataclass
class Article:
    """記事情報を格納するデータクラス"""
    title: str
    url: str
    author: str
    preview: str = ""
    claps: int = 0
    japanese_title: str = ""
    summary: str = ""
    japanese_summary: str = ""
    date_processed: str = ""

@dataclass
class Alert:
    """アラート情報を格納するデータクラス"""
    title: str
    url: str
    source: str
    snippet: str = ""
    japanese_title: str = ""
    japanese_summary: str = ""
    date_processed: str = ""
    article_content: str = ""
    email_date: str = ""
    tags: List[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
```

## エラー処理パターン

### リトライ with Exponential Backoff

```python
async def fetch_article_content(self, url: str, max_retries: int = 3) -> tuple[str, Optional[str]]:
    """記事コンテンツを取得（リトライ付き）"""
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status == 200:
                        return await response.text(), None
                    else:
                        raise Exception(f"HTTP {response.status}")

        except Exception as e:
            wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4秒

            if attempt < max_retries - 1:
                logger.warning(f"Error fetching {url}, retrying in {wait_time}s... "
                             f"(attempt {attempt + 1}/{max_retries}): {e}")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Error fetching article from {url}: {e}")
                return "", None

    return "", None
```

### HTTP ステータス別エラー処理

```python
async def fetch_article_content(self, url: str, retry_count: int = 3) -> str:
    """記事の本文を取得"""
    for attempt in range(retry_count):
        try:
            async with session.get(url, timeout=30) as response:
                if response.status == 200:
                    return await response.text()

                elif response.status in [403, 422, 429]:
                    # アクセス制限系のエラー: リトライ
                    if attempt < retry_count - 1:
                        wait_time = (attempt + 1) * random.uniform(2, 5)
                        logger.warning(f"記事取得エラー ({url}): {response.status}. "
                                     f"{wait_time:.1f}秒後にリトライ...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"記事取得エラー ({url}): {response.status}. リトライ回数超過")
                        return ""
                else:
                    logger.error(f"記事取得エラー ({url}): HTTPステータス {response.status}")
                    return ""

        except asyncio.TimeoutError:
            if attempt < retry_count - 1:
                wait_time = (attempt + 1) * 2
                logger.warning(f"記事取得タイムアウト ({url}). {wait_time}秒後にリトライ...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"記事取得タイムアウト ({url}). リトライ回数超過")
                return ""

        except Exception as e:
            if attempt < retry_count - 1:
                wait_time = (attempt + 1) * 1.5
                logger.warning(f"記事取得エラー ({url}): {e}. {wait_time}秒後にリトライ...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"記事取得エラー ({url}): {e}. リトライ回数超過")
                return ""

    return ""
```

### 個別エラー分離

バッチ処理では個別の失敗が全体に影響しないようにする:

```python
async def batch_save_articles(self, database_id: str, articles: List[Dict],
                             max_concurrent: int = 3) -> Dict[str, Any]:
    """複数の記事を並列で保存"""
    semaphore = asyncio.Semaphore(max_concurrent)
    stats = {"success": 0, "skipped": 0, "failed": 0}

    async def save_with_semaphore(article):
        async with semaphore:
            title = article.get('title', 'Unknown')
            try:
                result = await self.save_article(database_id, article)
                if result:
                    stats["success"] += 1
                else:
                    stats["skipped"] += 1
            except Exception as e:
                logger.error(f"記事の保存エラー '{title}': {e}")
                stats["failed"] += 1

    # 全記事を並列処理（個別の失敗は他に影響しない）
    tasks = [save_with_semaphore(article) for article in articles]
    await asyncio.gather(*tasks)

    return stats
```

## ログ出力規則

### ColoredFormatter の使用

```python
from minitools.utils.logger import get_logger, setup_logger

# 簡易ロガー取得
logger = get_logger(__name__)

# 詳細設定付きロガー
logger = setup_logger(
    name="scripts.arxiv",
    log_file="arxiv.log",
    level=logging.DEBUG
)
```

### ログレベルの使い分け

```python
# DEBUG: 詳細なデバッグ情報
logger.debug(f"Translated text: {translation[:100]}...")
logger.debug(f"Query result count: {len(result.get('results', []))}")

# INFO: 処理の進行状況
logger.info(f"Found {len(papers)} papers matching criteria")
logger.info(f"翻訳・要約処理を開始: {len(papers)}件の論文を処理中...")
logger.info(f"Notion保存完了: 成功={stats['success']}, スキップ={stats['skipped']}")

# WARNING: 注意が必要だが処理は継続
logger.warning("mlx_whisper is not installed. YouTube transcription will not be available.")
logger.warning(f"Jina Reader blocked by Medium for {url}")
logger.warning(f"SSL検証を無効化してリトライ: {url}")

# ERROR: エラーが発生したが処理は継続可能
logger.error(f"Error searching ArXiv: {e}")
logger.error(f"Translation error: {e}")
logger.error(f"記事の保存エラー '{title}': {e}")

# CRITICAL: 致命的エラー（アプリケーション終了レベル）
logger.critical(f"Database connection failed: {e}")
```

### 進捗表示パターン

```python
# バッチ処理の進捗
logger.info(f"バッチ {batch_num + 1}/{total_batches} を処理中 ({len(batch)}件)...")

# 個別アイテムの進捗
logger.info(f"  論文処理中 ({i}/{len(papers)}): {paper['title'][:60]}...")
logger.info(f"    -> 翻訳完了: {result['japanese_title'][:40]}...")

# 結果サマリー
logger.info("=" * 60)
logger.info("Notion保存結果:")
logger.info(f"  成功: {stats.get('success', 0)}件")
logger.info(f"  スキップ (既存): {stats.get('skipped', 0)}件")
logger.info(f"  失敗: {stats.get('failed', 0)}件")
logger.info("=" * 60)
```

## 非同期処理パターン

### Semaphore による並列制限

```python
async def batch_save_articles(self, database_id: str, articles: List[Dict],
                             max_concurrent: int = 3) -> Dict[str, Any]:
    """Semaphoreで並列数を制限"""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def save_with_semaphore(article):
        async with semaphore:  # ここで同時実行数を制限
            return await self.save_article(database_id, article)

    tasks = [save_with_semaphore(article) for article in articles]
    await asyncio.gather(*tasks)
```

### バッチ処理

```python
async def process_articles(articles: List[Article]) -> List[Dict]:
    """バッチ単位で記事を処理"""
    batch_size = 5
    total_batches = (len(articles) + batch_size - 1) // batch_size
    processed = []

    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, len(articles))
        batch = articles[start_idx:end_idx]

        logger.info(f"バッチ {batch_num + 1}/{total_batches} を処理中 ({len(batch)}件)...")

        # バッチ内を並列処理
        tasks = [process_article(article, start_idx + i + 1, len(articles))
                 for i, article in enumerate(batch)]

        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        # 成功した結果のみ追加
        for result in batch_results:
            if result and not isinstance(result, Exception):
                processed.append(result)

    return processed
```

### Executor パターン（同期API呼び出し）

Ollama など同期APIを非同期コンテキストで使用:

```python
async def translate_to_japanese(self, text: str) -> str:
    """Ollamaは同期APIなので、executorで実行"""
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,  # デフォルトのThreadPoolExecutor
        lambda: self.client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}]
        )
    )
    return response.message.content.strip()
```

### Async Context Manager

```python
class MediumCollector:
    """非同期コンテキストマネージャー対応クラス"""

    async def __aenter__(self):
        """非同期コンテキストマネージャーのエントリー"""
        connector = aiohttp.TCPConnector(limit=5)
        timeout = aiohttp.ClientTimeout(total=60)
        self.http_session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """非同期コンテキストマネージャーのクリーンアップ"""
        if self.http_session:
            await self.http_session.close()

# 使用例
async with MediumCollector() as collector:
    articles = await collector.get_digest_emails(date)
```

## 外部API呼び出しパターン

### Gmail API

```python
def _authenticate_gmail(self):
    """Gmail APIの認証"""
    creds = None
    token_path = 'token.pickle'

    # 既存トークンの読み込み
    if os.path.exists(token_path):
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)

    # トークンの更新または新規取得
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                self.credentials_path, SCOPES
            )
            creds = flow.run_local_server(port=0)

        # トークンの保存
        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)

    self.gmail_service = build('gmail', 'v1', credentials=creds)
```

### Notion API

```python
async def create_page(self, database_id: str, properties: Dict) -> Optional[str]:
    """Notionページを作成"""
    try:
        loop = asyncio.get_event_loop()
        page = await loop.run_in_executor(
            None,
            lambda: self.client.pages.create(
                parent={"database_id": database_id},
                properties=properties
            )
        )
        return page.get('id')
    except Exception as e:
        logger.error(f"Notionページ作成エラー: {e}")
        return None
```

### Jina AI Reader

```python
async def fetch_article_content(self, url: str) -> tuple[str, Optional[str]]:
    """Jina AI Readerでコンテンツ取得"""
    jina_url = f"https://r.jina.ai/{url}"

    # ランダム遅延（bot検出回避）
    delay = random.uniform(1, 3)
    await asyncio.sleep(delay)

    user_agent = random.choice(USER_AGENTS)
    headers = {
        'User-Agent': user_agent,
        'Accept': 'text/plain',
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(jina_url, headers=headers, timeout=30) as response:
            if response.status == 200:
                text_content = await response.text()

                # ブロック検出
                if 'error 403' in text_content.lower():
                    logger.warning(f"Jina Reader blocked for {url}")
                    return "", None

                return text_content.strip()[:3000], None
```

### Slack Webhook

```python
async def send_message(self, message: str, webhook_url: Optional[str] = None) -> bool:
    """Slackにメッセージを送信"""
    url = webhook_url or self.webhook_url
    if not url:
        logger.error("No Slack webhook URL provided")
        return False

    payload = {"text": message}

    try:
        async with self.http_session.post(url, json=payload) as response:
            if response.status == 200:
                logger.info("Message sent to Slack successfully")
                return True
            else:
                logger.error(f"Failed to send to Slack. Status: {response.status}")
                return False
    except Exception as e:
        logger.error(f"Error sending to Slack: {e}")
        return False
```

## URL正規化パターン

ソースタイプに応じたURL正規化:

```python
def _normalize_url_by_source(self, url: str) -> str:
    """ソースタイプに応じたURL正規化"""
    if self.source_type == 'arxiv':
        # ArXiv: HTTP→HTTPS、ドメイン統一
        url = url.replace("http://", "https://")
        url = url.replace("export.arxiv.org", "arxiv.org")

    elif self.source_type == 'medium':
        # Medium: クエリパラメータ除去、末尾スラッシュ除去
        url = url.split('?')[0]
        url = url.rstrip('/')
        if '#' in url:
            url = url.split('#')[0]

    elif self.source_type == 'google_alerts':
        # Google Alerts: トラッキングパラメータ除去
        url = url.split('?')[0]
        url = url.rstrip('/')
        if '#' in url:
            url = url.split('#')[0]

    return url
```

## テストパターン

### テストファイルの配置

```
minitools/
├── collectors/
│   └── xxx_collector.py      # → tests/test_xxx_collector.py
├── processors/
│   └── xxx_processor.py      # → tests/test_xxx_processor.py
├── publishers/
│   └── xxx_publisher.py      # → tests/test_xxx_publisher.py
└── llm/
    └── xxx_client.py         # → tests/test_xxx_client.py

tests/
├── __init__.py
├── conftest.py               # 共通フィクスチャ・モック
├── test_xxx_collector.py
├── test_xxx_processor.py
└── ...
```

### テストクラスの構造

```python
"""Tests for XxxProcessor."""

import pytest

from minitools.processors.xxx_processor import XxxProcessor


class TestXxxProcessor:
    """XxxProcessorのテスト"""

    @pytest.mark.asyncio
    async def test_process_basic(self, mock_llm_client):
        """基本的な処理のテスト"""
        processor = XxxProcessor(llm_client=mock_llm_client)
        result = await processor.process("input")

        assert result is not None
        assert "expected" in result

    @pytest.mark.asyncio
    async def test_process_empty_input(self, mock_llm_client):
        """空入力の場合のテスト"""
        processor = XxxProcessor(llm_client=mock_llm_client)
        result = await processor.process("")

        assert result == ""

    @pytest.mark.asyncio
    async def test_process_error_handling(self, mock_llm_client):
        """エラー時の処理テスト"""
        mock_llm_client.chat_response = None  # エラー状態をシミュレート
        processor = XxxProcessor(llm_client=mock_llm_client)

        with pytest.raises(ValueError):
            await processor.process("input")
```

### 共通フィクスチャ（conftest.py）

プロジェクトには以下のモッククライアントが用意されている:

```python
from tests.conftest import MockLLMClient, MockEmbeddingClient

# MockLLMClient: LLMクライアントのモック
# - chat_response: chatメソッドの戻り値を設定
# - json_response: chat_jsonメソッドの戻り値を設定
# - chat_calls: 呼び出し履歴を記録

# MockEmbeddingClient: Embeddingクライアントのモック
# - テキストごとに異なるembeddingを生成（ハッシュベース）
# - embed_texts_calls, embed_text_calls: 呼び出し履歴を記録
```

フィクスチャの使用例:

```python
@pytest.fixture
def mock_llm_client():
    """デフォルトのモックLLMクライアント"""
    return MockLLMClient()

@pytest.fixture
def mock_llm_client_custom():
    """カスタムレスポンスのモックLLMクライアント"""
    return MockLLMClient(
        chat_response="カスタムレスポンス",
        json_response='{"score": 8.5}'
    )

@pytest.fixture
def sample_articles():
    """テスト用のサンプル記事データ"""
    return [
        {"title": "Article 1", "summary": "Summary 1", "url": "https://example.com/1"},
        {"title": "Article 2", "summary": "Summary 2", "url": "https://example.com/2"},
    ]
```

### 非同期テストのパターン

```python
import pytest
import asyncio


class TestAsyncProcessor:
    """非同期処理のテスト"""

    @pytest.mark.asyncio
    async def test_async_method(self, mock_llm_client):
        """非同期メソッドのテスト"""
        processor = AsyncProcessor(llm_client=mock_llm_client)
        result = await processor.async_method()
        assert result is not None

    @pytest.mark.asyncio
    async def test_concurrent_processing(self, mock_llm_client):
        """並行処理のテスト"""
        processor = AsyncProcessor(llm_client=mock_llm_client)
        tasks = [processor.process(f"item_{i}") for i in range(5)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        assert all(r is not None for r in results)

    @pytest.mark.asyncio
    async def test_timeout_handling(self, mock_llm_client):
        """タイムアウト処理のテスト"""
        processor = AsyncProcessor(llm_client=mock_llm_client, timeout=0.1)

        with pytest.raises(asyncio.TimeoutError):
            await processor.slow_operation()
```

### テスト実行コマンド

```bash
# 全テスト実行
uv run pytest tests/ -v

# 特定ファイルのテスト実行
uv run pytest tests/test_xxx_processor.py -v

# 特定クラスのテスト実行
uv run pytest tests/test_xxx_processor.py::TestXxxProcessor -v

# 特定テストのみ実行
uv run pytest tests/test_xxx_processor.py::TestXxxProcessor::test_process_basic -v

# カバレッジ付きで実行
uv run pytest tests/ --cov=minitools --cov-report=term-missing

# 失敗したテストのみ再実行
uv run pytest tests/ --lf
```

### テスト設計のチェックリスト

新機能のテストを作成する際は、以下を確認:

- [ ] **正常系**: 主要な機能が期待通り動作するか
- [ ] **異常系**: エラー入力時に適切に処理されるか
- [ ] **エッジケース**: 境界値、空値、None値
- [ ] **モック**: 外部依存（LLM、API）が適切にモックされているか
- [ ] **非同期**: async/awaitが正しくテストされているか

## 設定管理パターン

### シングルトン Config

```python
from minitools.utils.config import get_config, Config

# 設定値の取得
config = get_config()
model = config.get('models.translation', 'gemma3:27b')
batch_size = config.get('output.notion.batch_size', 10)

# APIキーの取得（環境変数から）
api_key = Config.get_api_key('notion')  # NOTION_API_KEY
webhook = Config.get_api_key('slack_arxiv')  # SLACK_WEBHOOK_URL
```

### 環境変数のフォールバック

```python
# 新しい環境変数名を優先、旧名にフォールバック
database_id = os.getenv('NOTION_ARXIV_DATABASE_ID') or os.getenv('NOTION_DB_ID')
webhook_url = os.getenv('SLACK_ARXIV_WEBHOOK_URL') or os.getenv('SLACK_WEBHOOK_URL')
```

## 新モジュール追加パターン

新しい収集・変換・処理モジュール（特に外部バイナリやmultimodal LLMに依存するもの）を追加する際の指針。

### 外部バイナリ・重量級ライブラリ依存の追加チェックリスト

`marker-pdf`, `pymupdf`, `opencv-python-headless`, `mlx-whisper`, `ffmpeg` のようにバイナリ依存・モデル依存を含むライブラリを追加するときは、以下を必ず実施する:

- [ ] **`pyproject.toml`**: バージョン下限を明示的に指定（例: `marker-pdf>=1.10.0`）
  - メジャーバージョンの破壊的変更を避けるため、`>=` で固定し、CHANGELOG にバージョン根拠を残す
  - 巨大依存はオプショナル extras に分離する選択肢を検討（例: `[whisper]`）
- [ ] **`docs/core/CHANGELOG.md`**: `[Unreleased]` の Dependencies セクションにバージョンと採用理由を追記
- [ ] **`docs/core/repo-structure.md`**: 新規ファイル/ディレクトリを追加
- [ ] **`docs/core/architecture.md`**: 外部依存の役割と配置レイヤを記載
- [ ] **`README.md`** / **`CLAUDE.md`**: セットアップ手順（FFmpeg等の外部ツール）を補足
- [ ] **遅延 import**: モジュールロード時間を抑えるため、重量級ライブラリ（`marker-pdf`, `mlx-whisper` 等）は実際に使用する関数の中で import する
- [ ] **テスト**: 重量級依存はモックで隔離し、CIで全件ロードしないよう配慮

### Multimodal LLM の Graceful Degradation パターン

`BaseLLMClient.generate_from_images()` のように、すべてのプロバイダで対応していないAPIを追加する際は、未対応プロバイダで例外を出さずに警告ログ + 安全なデフォルト値を返す。

```python
# minitools/llm/ollama_client.py の例
async def generate_from_images(
    self, prompt: str, images: list[bytes], model: str | None = None
) -> str:
    """Ollama は multimodal を未サポート。warning を出して空文字列を返す"""
    logger.warning(
        "Ollama client does not support multimodal generation. "
        "Switch provider to gemini or openai for VLM features."
    )
    return ""
```

**設計原則**:
- 呼び出し側は「空文字列 or 短い応答」を `applied += 0` として正しくカウントする
- 機能ON/OFFの設定キー（例: `vlm_repair.enabled`）で完全スキップも可能にする
- ログは `WARNING` 以上のレベルで残し、サイレントフェイルにしない

### Heuristic 検出 + LLM 修復の二段構成

`VlmParseRepairer` のように、コストの高いLLM呼び出しを伴う処理は、まず軽量なヒューリスティック検出器（`ParseErrorDetector`）で候補を絞り込み、必要箇所だけLLMに渡す構成を推奨する。

- **検出器（heuristic）**: LLM不使用、`detect()` 関数のみ。リファクタしやすく単体テスト容易
- **修復器（LLM）**: `Semaphore=2` 程度で並列度を絞る（VLMは1呼び出しあたりコスト高）
- **予算制御**: `max_total_calls` で1ジョブあたりの最大LLM呼び出し回数を制限
- **冪等性**: `MarkdownPatcher` のように、同じ入力を2回当てても結果が変わらない実装にする

### テストファイル命名例

新規モジュールに対応するテストファイルは `tests/test_{モジュール名}.py` に配置する:

| ソースモジュール | テストファイル |
|------------------|---------------|
| `minitools/scrapers/arxiv_scraper.py` | `tests/test_arxiv_scraper.py` |
| `minitools/processors/vlm_parse_repairer.py` | `tests/test_vlm_parse_repairer.py` |
| `minitools/processors/full_text_translator.py` | `tests/test_full_text_translator.py` |
