# APIリファレンス

このドキュメントは、minitoolsプロジェクトの各クラス、関数、データ構造のリファレンスです。

## Collectors

### ArxivCollector

ArXiv論文を収集するクラス。

**ファイル:** `minitools/collectors/arxiv.py`

```python
class ArxivCollector:
    """ArXiv論文を収集するクラス"""

    def __init__(self):
        """
        コンストラクタ

        Attributes:
            base_url (str): ArXiv APIのベースURL
            http_session (aiohttp.ClientSession): HTTPセッション
        """

    async def __aenter__(self) -> 'ArxivCollector':
        """非同期コンテキストマネージャーのエントリー"""

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """非同期コンテキストマネージャーのクリーンアップ"""

    def search(
        self,
        queries: List[str],
        start_date: str,
        end_date: str,
        max_results: int = 50
    ) -> List[Dict[str, str]]:
        """
        arXiv APIを使用して論文を検索

        Args:
            queries: 検索語のリスト
            start_date: 検索開始日（YYYYMMDD形式）
            end_date: 検索終了日（YYYYMMDD形式）
            max_results: 取得する最大結果数

        Returns:
            検索結果の論文情報のリスト
            各論文: {title, url, abstract, authors, published, pdf_url}
        """

    async def fetch_paper_details_async(
        self,
        paper_url: str
    ) -> Optional[str]:
        """
        論文の詳細を非同期で取得

        Args:
            paper_url: 論文のURL

        Returns:
            論文の詳細テキスト
        """
```

**使用例:**
```python
async with ArxivCollector() as collector:
    papers = collector.search(
        queries=["LLM", "RAG"],
        start_date="20240101",
        end_date="20240115",
        max_results=50
    )
```

---

### MediumCollector

Medium Daily Digestメールを収集するクラス。

**ファイル:** `minitools/collectors/medium.py`

```python
class MediumCollector:
    """Medium Daily Digestメールを収集するクラス"""

    def __init__(self, credentials_path: str = None):
        """
        コンストラクタ

        Args:
            credentials_path: Gmail API認証ファイルパス（デフォルト: credentials.json）

        Attributes:
            gmail_service: Gmail APIサービスオブジェクト
            http_session: aiohttpセッション
        """

    async def __aenter__(self) -> 'MediumCollector':
        """非同期コンテキストマネージャーのエントリー"""

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """非同期コンテキストマネージャーのクリーンアップ"""

    async def get_digest_emails(
        self,
        date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Medium Daily Digestメールを取得

        Args:
            date: 取得する日付（指定しない場合は今日）

        Returns:
            メールメッセージのリスト
        """

    def parse_articles(self, html_content: str) -> List[Article]:
        """
        メールHTMLから記事情報を抽出

        Args:
            html_content: メールのHTML内容

        Returns:
            Article データクラスのリスト
        """

    async def fetch_article_content(
        self,
        url: str,
        max_retries: int = 3
    ) -> tuple[str, Optional[str]]:
        """
        記事のコンテンツをJina AI Readerで取得

        Args:
            url: 記事のURL
            max_retries: 最大リトライ回数

        Returns:
            (記事内容, 著者名) のタプル
        """

    def extract_email_body(self, message: Dict) -> str:
        """
        メールメッセージから本文を抽出

        Args:
            message: Gmail APIのメッセージオブジェクト

        Returns:
            メール本文のHTML
        """
```

**使用例:**
```python
async with MediumCollector() as collector:
    messages = await collector.get_digest_emails(datetime.now())
    email_body = collector.extract_email_body(messages[0])
    articles = collector.parse_articles(email_body)

    for article in articles:
        content, author = await collector.fetch_article_content(article.url)
```

---

### GoogleAlertsCollector

Google Alertsメールを収集するクラス。

**ファイル:** `minitools/collectors/google_alerts.py`

```python
class GoogleAlertsCollector:
    """Google Alertsメールを収集するクラス"""

    def __init__(self, credentials_path: str = None):
        """
        コンストラクタ

        Args:
            credentials_path: Gmail API認証ファイルパス
        """

    def get_alerts_emails(
        self,
        hours_back: int = 6,
        date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Google Alertsメールを取得

        Args:
            hours_back: 何時間前までのメールを取得するか
            date: 特定の日付のメールを取得

        Returns:
            メールメッセージのリスト
        """

    def parse_alerts(self, message: Dict) -> List[Alert]:
        """
        メールからアラート情報を抽出

        Args:
            message: Gmail APIのメッセージオブジェクト

        Returns:
            Alert データクラスのリスト
        """

    async def fetch_article_content(
        self,
        url: str,
        retry_count: int = 3
    ) -> str:
        """
        URLから記事の本文を取得

        Args:
            url: 記事のURL
            retry_count: リトライ回数

        Returns:
            記事の本文（最大3000文字）
        """

    async def fetch_articles_for_alerts(
        self,
        alerts: List[Alert]
    ) -> None:
        """
        複数のアラートの記事本文を並列で取得

        Args:
            alerts: アラートのリスト（article_contentが更新される）
        """
```

**使用例:**
```python
collector = GoogleAlertsCollector()
emails = collector.get_alerts_emails(hours_back=6)

all_alerts = []
for email in emails:
    alerts = collector.parse_alerts(email)
    all_alerts.extend(alerts)

await collector.fetch_articles_for_alerts(all_alerts)
```

---

### YouTubeCollector

YouTube動画を収集して文字起こしするクラス。

**ファイル:** `minitools/collectors/youtube.py`

```python
class YouTubeCollector:
    """YouTube動画を収集して文字起こしするクラス"""

    def __init__(
        self,
        output_dir: str = "outputs/temp",
        whisper_model: str = "mlx-community/whisper-base"
    ):
        """
        コンストラクタ

        Args:
            output_dir: 一時ファイルの出力ディレクトリ
            whisper_model: 使用するWhisperモデル
        """

    def download_audio(self, url: str) -> Optional[str]:
        """
        YouTubeから音声をダウンロード

        Args:
            url: YouTube動画のURL

        Returns:
            ダウンロードしたファイルのパス
        """

    def transcribe_audio(
        self,
        audio_file: str
    ) -> Optional[Dict[str, Any]]:
        """
        音声ファイルを文字起こし

        Args:
            audio_file: 音声ファイルのパス

        Returns:
            文字起こし結果（textキーを含む辞書）
        """

    def process_video(self, url: str) -> Optional[Dict[str, str]]:
        """
        YouTube動画をダウンロードして文字起こし

        Args:
            url: YouTube動画のURL

        Returns:
            動画情報と文字起こしテキストを含む辞書
            {url, title, author, duration, transcript, audio_file}
        """

    def get_video_info(self, url: str) -> Optional[Dict[str, Any]]:
        """
        YouTube動画の情報を取得

        Args:
            url: YouTube動画のURL

        Returns:
            動画情報の辞書
            {id, title, uploader, duration, description, upload_date, view_count, like_count}
        """
```

**使用例:**
```python
collector = YouTubeCollector(
    output_dir="outputs/temp",
    whisper_model="mlx-community/whisper-large-v3-turbo"
)

result = collector.process_video("https://youtube.com/watch?v=...")
print(result['transcript'])
```

---

### XTrendCollector

TwitterAPI.ioからX（Twitter）トレンド・キーワード検索・ユーザータイムラインを収集するクラス。日本/グローバルWOEIDのサポート、非同期HTTP通信、指数バックオフリトライ機能。

**ファイル:** `minitools/collectors/x_trend.py`

```python
@dataclass
class Trend:
    """トレンド情報"""
    name: str                       # トレンド名
    tweet_volume: int = 0           # ツイート数
    region: str = ""                # "japan" or "global"

@dataclass
class Tweet:
    """ツイート情報"""
    text: str                       # ツイートテキスト
    retweet_count: int = 0          # リツイート数
    like_count: int = 0             # いいね数
    author: str = ""                # 投稿者名

@dataclass
class TrendWithTweets:
    """トレンドと関連ツイートのセット"""
    trend: Trend
    tweets: list[Tweet] = field(default_factory=list)

@dataclass
class KeywordSearchResult:
    """キーワード検索結果"""
    keyword: str
    tweets: list[Tweet] = field(default_factory=list)

@dataclass
class UserTimelineResult:
    """ユーザータイムライン結果"""
    username: str
    tweets: list[Tweet] = field(default_factory=list)

@dataclass
class CollectResult:
    """全収集結果を格納"""
    trends: dict[str, list[TrendWithTweets]] = field(default_factory=dict)
    keyword_results: list[KeywordSearchResult] = field(default_factory=list)
    timeline_results: list[UserTimelineResult] = field(default_factory=list)


class XTrendCollector:
    """TwitterAPI.ioを使用してトレンドとツイートを収集するクラス"""

    def __init__(self, api_key: Optional[str] = None, max_retries: int = 3):
        """
        Args:
            api_key: TwitterAPI.io APIキー（省略時は環境変数TWITTER_API_IO_KEYから取得）
            max_retries: 最大リトライ回数
        """

    async def get_trends(self, woeid: int) -> list[Trend]:
        """指定地域のトレンドを取得"""

    async def get_tweets_for_trend(self, trend_name: str, count: int = 20) -> list[Tweet]:
        """トレンドに関連するツイートを取得"""

    async def search_by_keyword(self, keyword: str, count: int = 20) -> list[Tweet]:
        """キーワードでツイートを検索"""

    async def get_user_timeline(self, username: str, count: int = 20) -> list[Tweet]:
        """ユーザーの最新ツイートを取得"""

    async def collect_keywords(self, keywords: list[str], tweets_per_keyword: int = 20) -> list[KeywordSearchResult]:
        """全キーワードでツイートを並列検索（Semaphore(5)）"""

    async def collect_timelines(self, accounts: list[str], tweets_per_account: int = 20) -> list[UserTimelineResult]:
        """全アカウントのタイムラインを並列取得（Semaphore(5)）"""

    async def collect(self, regions: list[str] = None, tweets_per_trend: int = 20, fetch_tweets: bool = True) -> dict[str, list[TrendWithTweets]]:
        """指定地域のトレンドと関連ツイートを収集（fetch_tweets=Falseでコスト最適化）"""

    async def collect_all(
        self,
        regions: list[str] | None = None,
        keywords: list[str] | None = None,
        watch_accounts: list[str] | None = None,
        tweets_per_trend: int = 20,
        tweets_per_keyword: int = 20,
        tweets_per_account: int = 20,
        enable_trends: bool = True,
        enable_keywords: bool = True,
        enable_timeline: bool = True,
    ) -> CollectResult:
        """3ソース（トレンド・キーワード・タイムライン）を並列で収集（enable_*フラグで個別制御）"""
```

**使用例:**
```python
# 3ソース統合収集
async with XTrendCollector() as collector:
    result = await collector.collect_all(
        regions=["japan", "global"],
        keywords=["Claude Code", "AI Agent"],
        watch_accounts=["kaboratory"],
    )
    print(f"Trends: {sum(len(v) for v in result.trends.values())}")
    print(f"Keywords: {len(result.keyword_results)}")
    print(f"Timelines: {len(result.timeline_results)}")

# トレンドのみ（ツイート取得なし、コスト最適化）
async with XTrendCollector() as collector:
    trends = await collector.collect(fetch_tweets=False)
```

---

## LLM抽象化レイヤー

### BaseLLMClient

LLMクライアントの抽象基底クラス。

**ファイル:** `minitools/llm/base.py`

```python
class BaseLLMClient(ABC):
    """LLMクライアントの抽象基底クラス"""

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None
    ) -> str:
        """
        メッセージを送信してレスポンスを取得

        Args:
            messages: チャットメッセージのリスト
                      各メッセージは {"role": "user"|"assistant"|"system", "content": "..."}
            model: 使用するモデル名（省略時はデフォルトモデルを使用）

        Returns:
            LLMからのレスポンステキスト
        """

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None
    ) -> str:
        """
        プロンプトからテキスト生成

        Args:
            prompt: 生成のためのプロンプト
            model: 使用するモデル名（省略時はデフォルトモデルを使用）

        Returns:
            生成されたテキスト
        """

    async def generate_from_images(
        self,
        prompt: str,
        images: List[bytes],
        mime_type: str = "image/png",
        model: Optional[str] = None
    ) -> str:
        """
        画像とプロンプトからテキスト生成（multimodal）

        デフォルト実装は warning を出して空文字列を返す。multimodal 対応プロバイダ
        （Gemini / OpenAI）では `HumanMessage` の content list 形式で画像を渡す。

        Args:
            prompt: 生成のためのプロンプト
            images: 画像バイト列のリスト
            mime_type: 画像のMIMEタイプ（"image/png" or "image/jpeg"）
            model: 使用するモデル名（省略時はデフォルトモデルを使用）

        Returns:
            生成されたテキスト（未対応時は空文字列）
        """
```

---

### get_llm_client

LLMクライアントを取得するファクトリ関数。

**ファイル:** `minitools/llm/__init__.py`

```python
def get_llm_client(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    thinking_level: Optional[str] = None,
) -> BaseLLMClient:
    """
    LLMクライアントを取得するファクトリ関数

    LangChainベースの実装を優先使用し、ImportError時は
    ネイティブクライアントにフォールバックします。

    Args:
        provider: LLMプロバイダー名（"ollama", "openai", "gemini"）
                  省略時は設定ファイルから取得
        model: 使用するモデル名（省略時は各プロバイダーのデフォルトを使用）
        thinking_level: Gemini 3系の思考深度（"minimal" / "low" / "medium" / "high"）。
                        Gemini 利用時のみ有効、OpenAI / Ollama では無視。
                        未指定時は ``llm.gemini.default_thinking_level`` 設定値、
                        さらに省略時は ``minimal`` がデフォルト。

    Returns:
        LLMクライアントインスタンス

    Raises:
        ValueError: 未対応のプロバイダー、または不正な thinking_level
        LLMError: クライアントの初期化に失敗した場合
    """
```

**使用例:**
```python
from minitools.llm import get_llm_client

# デフォルト設定で取得
client = get_llm_client()

# プロバイダーとモデルを指定
client = get_llm_client(provider="openai", model="gpt-4o")

# Geminiプロバイダーを指定（thinking_level でコスト/品質を調整）
client = get_llm_client(
    provider="gemini",
    model="gemini-3.1-flash-lite-preview",
    thinking_level="minimal",  # 翻訳・分類タスク向け
)

# VLM 修復のように精度重視のタスクは medium / high を選択
client = get_llm_client(
    provider="gemini",
    model="gemini-3-flash-preview",
    thinking_level="medium",
)

# 共通インターフェースで呼び出し
response = await client.chat([
    {"role": "user", "content": "Hello!"}
])

# シンプルなテキスト生成
text = await client.generate("Summarize this text: ...")

# JSON形式でレスポンスを取得（LangChainクライアントのみ）
json_response = await client.chat_json([
    {"role": "user", "content": "Return JSON: {\"key\": \"value\"}"}
])
```

---

### LangChainクライアントの追加メソッド

LangChainベースのクライアント（`LangChainOllamaClient`, `LangChainOpenAIClient`, `LangChainGeminiClient`）は、基底クラスの`chat()`、`generate()`に加えて以下のメソッドを提供します。

**ファイル:** `minitools/llm/langchain_ollama.py`, `minitools/llm/langchain_openai.py`, `minitools/llm/langchain_gemini.py`

```python
async def chat_json(
    self,
    messages: List[Dict[str, str]],
    model: Optional[str] = None
) -> str:
    """
    JSON形式のレスポンスを取得

    Ollamaの場合はformat="json"を指定、OpenAIの場合は
    response_format={"type": "json_object"}を指定して呼び出します。

    Args:
        messages: チャットメッセージのリスト
        model: 使用するモデル名（省略時はデフォルトモデルを使用）

    Returns:
        LLMからのJSONレスポンステキスト

    Raises:
        LLMError: API呼び出しに失敗した場合
    """
```

**使用例:**
```python
from minitools.llm import get_llm_client

client = get_llm_client(provider="ollama")

# JSON形式でレスポンスを取得
json_str = await client.chat_json([
    {"role": "user", "content": "以下の情報をJSONで返してください: name=Alice, age=30"}
])
# => '{"name": "Alice", "age": 30}'
```

---

### BaseEmbeddingClient

Embeddingクライアントの抽象基底クラス。

**ファイル:** `minitools/llm/embeddings.py`

```python
class BaseEmbeddingClient(ABC):
    """Embeddingクライアントの抽象基底クラス"""

    @abstractmethod
    async def embed_texts(
        self,
        texts: List[str]
    ) -> List[List[float]]:
        """
        テキストリストをEmbeddingベクトルに変換

        Args:
            texts: 変換するテキストのリスト

        Returns:
            各テキストに対応するEmbeddingベクトルのリスト
        """

    @abstractmethod
    async def embed_text(
        self,
        text: str
    ) -> List[float]:
        """
        単一テキストをEmbeddingベクトルに変換

        Args:
            text: 変換するテキスト

        Returns:
            Embeddingベクトル
        """
```

---

### EmbeddingClient 実装クラス

`BaseEmbeddingClient` を継承する具体実装。

**ファイル:** `minitools/llm/embeddings.py`

| クラス | デフォルトモデル | 備考 |
|--------|----------------|------|
| `OllamaEmbeddingClient` | `nomic-embed-text` | ローカル Ollama サーバー（`OLLAMA_HOST` 環境変数で接続先指定可） |
| `OpenAIEmbeddingClient` | `text-embedding-3-small` | OpenAI API 経由、`OPENAI_API_KEY` 必須 |
| `GeminiEmbeddingClient` | `text-embedding-004` | `langchain-google-genai` 経由、`GEMINI_API_KEY` 必須。`embed_texts()`/`embed_text()` を非同期実装 |

各クラスは `embed_texts(texts)` と `embed_text(text)` を実装し、内部で遅延初期化されたクライアントを利用する。失敗時は `EmbeddingError` を送出。

---

### get_embedding_client

Embeddingクライアントを取得するファクトリ関数。

**ファイル:** `minitools/llm/embeddings.py`

```python
def get_embedding_client(
    provider: Optional[str] = None
) -> BaseEmbeddingClient:
    """
    Embeddingクライアントを取得するファクトリ関数

    Args:
        provider: プロバイダー名（"ollama", "openai", "gemini"）
                  省略時は設定ファイルから取得

    Returns:
        Embeddingクライアントインスタンス

    Raises:
        ValueError: 未対応のプロバイダーが指定された場合
    """
```

**使用例:**
```python
from minitools.llm import get_embedding_client

# デフォルト設定で取得
embedding = get_embedding_client()

# プロバイダーを指定
embedding = get_embedding_client(provider="openai")

# 複数テキストのEmbedding
vectors = await embedding.embed_texts([
    "First document",
    "Second document"
])

# 単一テキストのEmbedding
vector = await embedding.embed_text("Query text")
```

---

## Readers

### NotionReader

Notionデータベースから記事を読み取るクラス（読み取り専用）。

**ファイル:** `minitools/readers/notion.py`

```python
class NotionReader:
    """Notionデータベースから記事を読み取るクラス（読み取り専用）"""

    def __init__(self, api_key: Optional[str] = None):
        """
        コンストラクタ

        Args:
            api_key: Notion APIキー（省略時は環境変数から取得）

        Raises:
            ValueError: APIキーが設定されていない場合
        """

    async def get_articles_by_date_range(
        self,
        database_id: str,
        start_date: str,
        end_date: str,
        date_property: str = "Date"
    ) -> List[Dict[str, Any]]:
        """
        指定期間の記事を全件取得

        Args:
            database_id: NotionデータベースID
            start_date: 開始日（YYYY-MM-DD形式）
            end_date: 終了日（YYYY-MM-DD形式）
            date_property: 日付プロパティ名（デフォルト: "Date"）

        Returns:
            記事データの辞書リスト

        Raises:
            NotionReadError: 読み取りに失敗した場合
        """

    async def get_database_info(
        self,
        database_id: str
    ) -> Dict[str, Any]:
        """
        データベースの情報を取得

        Args:
            database_id: NotionデータベースID

        Returns:
            データベース情報の辞書
        """
```

**使用例:**
```python
reader = NotionReader()

# 日付範囲で記事を取得
articles = await reader.get_articles_by_date_range(
    database_id="xxx",
    start_date="2024-01-01",
    end_date="2024-01-07",
    date_property="Date"
)

# ArXiv論文を日付範囲で取得
papers = await reader.get_arxiv_papers_by_date_range(
    start_date="2024-01-01",
    end_date="2024-01-07",
    database_id="xxx"  # 省略時は環境変数から取得
)
```

---

## Researchers

### TrendResearcher

Tavily APIを使用して現在のAIトレンドを調査するクラス。

**ファイル:** `minitools/researchers/trend.py`

```python
class TrendResearcher:
    """Tavily APIを使用して現在のAIトレンドを調査するクラス"""

    def __init__(self, api_key: Optional[str] = None):
        """
        コンストラクタ

        Args:
            api_key: Tavily APIキー（省略時は環境変数TAVILY_API_KEYから取得）
        """

    async def get_current_trends(
        self,
        query: str = "AI machine learning latest trends breakthroughs",
        max_results: int = 5
    ) -> Optional[Dict[str, Any]]:
        """
        現在のAIトレンドを調査

        Args:
            query: 検索クエリ（デフォルト: AI関連のトレンド検索）
            max_results: 取得する検索結果の最大数

        Returns:
            トレンド情報の辞書、またはエラー時はNone
            {
                "summary": "トレンドの要約（500文字程度）",
                "topics": ["トピック1", "トピック2", ...],
                "sources": [{"title": "...", "url": "..."}]
            }
        """
```

**使用例:**
```python
researcher = TrendResearcher()

# トレンド調査
trends = await researcher.get_current_trends()
if trends:
    print(f"Summary: {trends['summary']}")
    print(f"Topics: {trends['topics']}")
```

---

### HFPapersResearcher

HuggingFace Papers APIを使用して論文のupvote数・コメント数を取得するクラス。

**ファイル:** `minitools/researchers/hf_papers.py`

```python
@dataclass
class HFPaperStats:
    """HuggingFace Papers APIから取得した論文統計"""
    arxiv_id: str
    upvotes: int = 0
    num_comments: int = 0
    found_on_hf: bool = False

class HFPapersResearcher:
    """HuggingFace Papers APIを使用して論文の統計情報を取得するクラス"""

    def __init__(self, max_concurrent: int = 5):
        """
        コンストラクタ

        Args:
            max_concurrent: 最大同時接続数（デフォルト: 5）
        """

    async def __aenter__(self) -> "HFPapersResearcher": ...
    async def __aexit__(self, ...): ...

    async def get_paper_stats(self, arxiv_id: str) -> HFPaperStats:
        """
        単一論文のHF統計を取得

        Args:
            arxiv_id: arXiv ID (例: "2601.00001")

        Returns:
            HFPaperStats（404の場合はupvotes=0, found_on_hf=False）
        """

    async def get_papers_stats(self, arxiv_ids: list[str]) -> dict[str, HFPaperStats]:
        """
        複数論文のHF統計を一括取得（asyncio.gatherで並列実行）

        Args:
            arxiv_ids: arXiv IDのリスト

        Returns:
            arXiv ID -> HFPaperStats のマッピング
        """
```

**使用例:**
```python
from minitools.researchers import HFPapersResearcher

async with HFPapersResearcher(max_concurrent=5) as researcher:
    stats = await researcher.get_papers_stats(["2601.00001", "2601.00002"])
    for arxiv_id, stat in stats.items():
        print(f"{arxiv_id}: {stat.upvotes} upvotes, {stat.num_comments} comments")
```

**エラーハンドリング:**
- 404（HF未登録）: `HFPaperStats(upvotes=0, found_on_hf=False)` を返す
- 429/5xx: exponential backoff（2s, 4s, 8s）で最大3回リトライ
- リトライ後も失敗: `HFPaperStats(upvotes=0)` をデフォルト返却

---

## Scrapers

### MediumScraper

Playwrightを使用してMedium記事の全文HTMLを取得するクラス。CDP（Chrome DevTools Protocol）モードとスタンドアロンモードをサポート。

**ファイル:** `minitools/scrapers/medium_scraper.py`

```python
class MediumScraper:
    """Playwrightを使用してMedium記事の全文HTMLを取得するクラス"""

    def __init__(
        self,
        headless: bool = True,
        cdp_mode: bool = False,
    ):
        """
        コンストラクタ

        Args:
            headless: ヘッドレスモードで実行するか（CDPモードでは無視）
            cdp_mode: Trueの場合、実際のChromeにCDP接続する
        """

    async def __aenter__(self) -> 'MediumScraper':
        """ブラウザを起動/接続する"""

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """ブラウザを切断/閉じる"""

    async def scrape_article(self, url: str) -> str:
        """
        記事URLから全文HTMLを取得する

        Args:
            url: Medium記事のURL

        Returns:
            記事のHTML文字列（取得失敗時は空文字列）
        """
```

**使用例:**
```python
# CDPモード（推奨: Cloudflare回避）
async with MediumScraper(cdp_mode=True) as scraper:
    html = await scraper.scrape_article("https://medium.com/...")

# スタンドアロンモード
async with MediumScraper() as scraper:
    html = await scraper.scrape_article("https://medium.com/...")
```

---

### MarkdownConverter

Medium記事のHTMLを構造化Markdownに変換するクラス。

**ファイル:** `minitools/scrapers/markdown_converter.py`

```python
class MarkdownConverter:
    """Medium記事HTMLを構造化Markdownに変換するクラス"""

    def convert(self, html: str) -> str:
        """
        HTMLを構造化Markdownに変換

        Args:
            html: 記事のHTML文字列

        Returns:
            Markdown文字列
        """
```

**使用例:**
```python
converter = MarkdownConverter()
markdown = converter.convert(html)
```

---

### ArxivScraper

ArXiv論文のPDFをダウンロードし、marker-pdfでMarkdown形式に変換するクラス。
Playwright非依存（httpxベース）で動作する。

**ファイル:** `minitools/scrapers/arxiv_scraper.py`

**補助dataclass:**

```python
@dataclass
class PaperImage:
    """PDFから抽出した画像"""
    filename: str       # marker-pdfが付与するファイル名（例: _page_0_Figure_5.jpeg）
    data: bytes         # 画像バイト列
    mime_type: str      # "image/jpeg" または "image/png"

@dataclass
class PaperMetadata:
    """ArXiv APIから取得した論文メタデータ"""
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    published: str      # YYYY-MM-DD
    pdf_url: str
    abs_url: str

@dataclass
class PaperContent:
    """fetch_and_parse() の返り値"""
    metadata: PaperMetadata
    markdown: str       # marker-pdf 出力
    images: list[PaperImage]
```

```python
class ArxivScraper:
    """ArXiv論文PDFをMarkdownに変換するクラス"""

    async def __aenter__(self) -> "ArxivScraper":
        """httpx.AsyncClientとmarker-pdfコンバーターを初期化"""

    async def __aexit__(self, *args) -> None:
        """HTTPクライアントをクローズ"""

    def validate_arxiv_url(self, url: str) -> bool:
        """ArXiv URL（abs/ or pdf/）の形式を検証"""

    @staticmethod
    def extract_arxiv_id(url: str) -> str | None:
        """arXiv IDを抽出（例: 2401.12345 や 2401.12345v2）"""

    async def fetch_pdf(self, url: str) -> bytes | None:
        """
        PDFをダウンロード（最大3回リトライ、指数バックオフ）

        Args:
            url: arXivのabs/またはpdf/URL

        Returns:
            PDFバイト列。失敗時はNone。
        """

    def parse_to_markdown(
        self, pdf_data: bytes
    ) -> tuple[str, list[PaperImage]]:
        """
        marker-pdfでPDF→Markdown変換し、画像も抽出

        Returns:
            (markdown文字列, 画像リスト)
        """

    async def fetch_metadata(self, arxiv_id: str) -> PaperMetadata | None:
        """ArXiv APIからメタデータを取得（feedparser経由）"""

    async def fetch_and_parse(self, url: str) -> PaperContent | None:
        """
        URL→PDFダウンロード→Markdown変換→メタデータ取得を一括実行

        Returns:
            PaperContent。いずれかのステップで失敗した場合はNone。
        """
```

**使用例:**
```python
async with ArxivScraper() as scraper:
    content = await scraper.fetch_and_parse("https://arxiv.org/abs/2401.12345")
    if content:
        print(content.metadata.title)
        print(content.markdown[:500])
        for img in content.images:
            (output_dir / img.filename).write_bytes(img.data)
```

---

## Processors

### Translator

テキストを翻訳するクラス。

**ファイル:** `minitools/processors/translator.py`

```python
class Translator:
    """テキストを翻訳するクラス"""

    def __init__(self, model: Optional[str] = None):
        """
        コンストラクタ

        Args:
            model: 使用するOllamaモデル名（デフォルト: config から取得）
        """

    async def translate_to_japanese(
        self,
        text: str,
        context: str = ""
    ) -> str:
        """
        テキストを日本語に翻訳

        Args:
            text: 翻訳するテキスト
            context: 追加のコンテキスト情報

        Returns:
            翻訳されたテキスト
        """

    async def translate_with_summary(
        self,
        title: str,
        content: str,
        author: str = ""
    ) -> Dict[str, str]:
        """
        タイトルと内容を翻訳し、要約も生成

        Args:
            title: 記事のタイトル
            content: 記事の内容
            author: 著者名（オプション）

        Returns:
            {"japanese_title": str, "japanese_summary": str}
        """
```

**使用例:**
```python
translator = Translator()

# シンプルな翻訳
japanese_text = await translator.translate_to_japanese(
    "Hello, world!",
    context="greeting"
)

# タイトルと要約の同時生成
result = await translator.translate_with_summary(
    title="Introduction to LLM",
    content="Large Language Models are...",
    author="John Doe"
)
print(result['japanese_title'])
print(result['japanese_summary'])
```

---

### Summarizer

コンテンツを要約するクラス。

**ファイル:** `minitools/processors/summarizer.py`

```python
class Summarizer:
    """コンテンツを要約するクラス"""

    def __init__(self, model: Optional[str] = None):
        """
        コンストラクタ

        Args:
            model: 使用するOllamaモデル名（デフォルト: config から取得）
        """

    async def summarize(
        self,
        text: str,
        max_length: int = 200,
        language: str = "japanese"
    ) -> str:
        """
        テキストを要約

        Args:
            text: 要約するテキスト
            max_length: 要約の最大文字数
            language: 要約の言語（japanese/english）

        Returns:
            要約されたテキスト
        """

    async def extract_key_points(
        self,
        text: str,
        num_points: int = 5
    ) -> list[str]:
        """
        テキストから重要ポイントを抽出

        Args:
            text: 分析するテキスト
            num_points: 抽出するポイント数

        Returns:
            重要ポイントのリスト
        """
```

**使用例:**
```python
summarizer = Summarizer()

# 要約
summary = await summarizer.summarize(
    text="Long article content...",
    max_length=500,
    language="japanese"
)

# キーポイント抽出
points = await summarizer.extract_key_points(
    text="Long article content...",
    num_points=5
)
```

---

### WeeklyDigestProcessor

週次ダイジェストを生成するプロセッサ。バッチ処理により高速なスコアリングを実現。

**ファイル:** `minitools/processors/weekly_digest.py`

```python
class WeeklyDigestProcessor:
    """週次ダイジェスト生成プロセッサ"""

    def __init__(
        self,
        llm_client: BaseLLMClient,
        embedding_client: Optional[BaseEmbeddingClient] = None,
        max_concurrent: int = 3,
        batch_size: Optional[int] = None
    ):
        """
        コンストラクタ

        Args:
            llm_client: LLMクライアントインスタンス
            embedding_client: Embeddingクライアント（省略時は自動生成）
            max_concurrent: 最大並列処理数（デフォルト: 3）
            batch_size: バッチスコアリングのサイズ（省略時は設定ファイルから取得、デフォルト: 20）
        """

    async def rank_articles_by_importance(
        self,
        articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        各記事に重要度スコア(1-10)を付与（バッチ処理対応）

        バッチ処理により複数記事を1回のLLM呼び出しでスコアリングし、
        処理時間を大幅に短縮します。バッチ処理が失敗した場合は
        自動的に個別処理にフォールバックします。

        Args:
            articles: 記事データのリスト

        Returns:
            importance_scoreが付与された記事リスト
        """

    async def select_top_articles(
        self,
        articles: List[Dict[str, Any]],
        top_n: int = 20,
        deduplicate: Optional[bool] = None,
        buffer_ratio: Optional[float] = None,
        similarity_threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        スコア上位N件を取得（オプションで重複除去）

        Args:
            articles: importance_scoreが付与された記事リスト
            top_n: 取得する記事数（デフォルト: 20）
            deduplicate: 重複除去を行うか（省略時は設定ファイルに従う）
            buffer_ratio: 候補記事の倍率（省略時は設定ファイルに従う）
            similarity_threshold: 類似度閾値（省略時は設定ファイルに従う）

        Returns:
            上位N件の記事リスト
        """

    async def generate_trend_summary(
        self,
        articles: List[Dict[str, Any]]
    ) -> str:
        """
        週のトレンド総括を生成

        Args:
            articles: 上位記事のリスト

        Returns:
            200-400文字の日本語トレンド総括
        """

    async def generate_article_summaries(
        self,
        articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        各記事の3-4行要約を生成

        Args:
            articles: 記事データのリスト

        Returns:
            digest_summaryが付与された記事リスト
        """

    async def process(
        self,
        articles: List[Dict[str, Any]],
        top_n: int = 20,
        deduplicate: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        週次ダイジェストを一括生成

        Args:
            articles: 全記事リスト
            top_n: 上位記事数（デフォルト: 20）
            deduplicate: 重複除去を行うか

        Returns:
            処理結果の辞書:
            - trend_summary: トレンド総括
            - top_articles: 上位記事リスト（要約付き）
            - total_articles: 処理した記事総数
            - duplicate_groups: 検出した重複グループ数（重複除去時のみ）
        """
```

**使用例:**
```python
from minitools.llm import get_llm_client, get_embedding_client

llm = get_llm_client(provider="ollama")
embedding = get_embedding_client(provider="ollama")

processor = WeeklyDigestProcessor(
    llm_client=llm,
    embedding_client=embedding
)

result = await processor.process(
    articles=articles_list,
    top_n=20,
    deduplicate=True
)

print(result['trend_summary'])
for article in result['top_articles']:
    print(f"{article['title']} - スコア: {article['importance_score']}")
```

**CLIオプション:**
```bash
# 基本使用
uv run google-alert-weekly-digest                 # デフォルト設定で実行
uv run google-alert-weekly-digest --days 14       # 過去14日分を取得
uv run google-alert-weekly-digest --top 10        # 上位10件を選出

# LLMプロバイダー指定
uv run google-alert-weekly-digest --provider openai  # OpenAI APIを使用
uv run google-alert-weekly-digest --embedding openai # Embeddingのみ OpenAI を使用

# オプション
uv run google-alert-weekly-digest --dry-run       # Slack送信をスキップ
uv run google-alert-weekly-digest --output out.md # ファイルに保存
uv run google-alert-weekly-digest --no-dedup      # 類似記事除去をスキップ
```

---

### FullTextTranslator

記事全文を構造を維持しながら日本語に翻訳するクラス。見出しベースのチャンク分割とリトライ機能を備える。

**ファイル:** `minitools/processors/full_text_translator.py`

```python
class FullTextTranslator:
    """記事全文を構造維持で日本語翻訳するクラス"""

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        llm_client: Optional[BaseLLMClient] = None,
        chunk_size: int = 6000,
        max_retries: int = 3,
    ):
        """
        コンストラクタ

        Args:
            provider: LLMプロバイダー（省略時は設定ファイルから取得）
            model: 使用するモデル名（省略時は設定ファイルから取得）
            llm_client: 既存のLLMクライアント（指定時はprovider/modelを無視）
            chunk_size: チャンク分割の最大文字数（デフォルト: 6000）
            max_retries: 最大リトライ回数（デフォルト: 3）
        """

    async def translate(self, markdown: str) -> str:
        """
        Markdown記事全文を日本語に翻訳

        セクション（見出し）単位でチャンク分割し、
        各チャンクを翻訳後に結合する。
        コードブロック内のコード本体は翻訳しない。

        Args:
            markdown: 翻訳するMarkdown文字列

        Returns:
            翻訳されたMarkdown文字列
        """
```

**使用例:**
```python
translator = FullTextTranslator(provider="gemini")
translated_md = await translator.translate(markdown_text)
```

---

### VlmParseRepairer

marker-pdfが生成したMarkdownのパース欠陥（壊れた表・孤立した図の参照など）を、
multimodal LLM（Gemini / OpenAI）に該当ページの画像を渡して修復するクラス。
`arxiv-translate parse` から呼び出される。

**ファイル:** `minitools/processors/vlm_parse_repairer.py`

**補助dataclass:**

```python
@dataclass
class ParseDefect:
    """検出されたパース欠陥"""
    kind: str               # "broken_table" | "orphan_figure" など
    page: int               # PDFページ番号（0始まり）
    line_start: int         # Markdown内の開始行
    line_end: int           # Markdown内の終了行
    excerpt: str            # 該当行の抜粋
    confidence: float       # 検出の信頼度

@dataclass
class RepairResult:
    """修復結果"""
    detected: int           # 検出された欠陥数
    applied: int            # 実際に修復された数
    repaired_markdown: str  # 修復後のMarkdown
```

**主要クラス:**

| クラス | 役割 |
|-------|------|
| `ParseErrorDetector` | ヒューリスティックで欠陥を検出（LLMコストなし） |
| `PdfPageRenderer` | PyMuPDFでページをPNGレンダリング、ディスクキャッシュあり |
| `VlmRepairer` | VLMで表再構築 / 図の日本語要約を生成（Semaphore=2、3回リトライ） |
| `MarkdownPatcher` | 検証付きでMarkdownを置換（idempotent） |
| `VlmParseRepairer` | 上記4つを統合する高レベルAPI |

```python
class VlmParseRepairer:
    """marker-pdfパース欠陥のVLM修復オーケストレーター"""

    def __init__(
        self,
        llm_client: BaseLLMClient,
        pdf_path: Path,
        page_image_dir: Path,
        max_total_calls: int = 30,
        max_dpi: int = 200,
    ):
        """
        Args:
            llm_client: multimodal対応LLMクライアント（generate_from_imagesが必須）
            pdf_path: 元のPDFファイルパス
            page_image_dir: ページ画像のキャッシュディレクトリ
            max_total_calls: VLM呼び出しの総回数上限（コスト制御）
            max_dpi: ページレンダリングの最大DPI
        """

    async def repair(
        self,
        markdown: str,
        dry_run: bool = False,
    ) -> RepairResult:
        """
        Markdownを検査して欠陥を検出し、VLMで修復する

        Args:
            markdown: marker-pdf出力のMarkdown
            dry_run: Trueの場合は検出のみ実行、修復は行わない

        Returns:
            RepairResult（検出数・適用数・修復後Markdown）
        """
```

**使用例:**
```python
from minitools.llm import get_llm_client
from minitools.processors.vlm_parse_repairer import VlmParseRepairer

llm = get_llm_client(
    provider="gemini",
    model="gemini-3-flash-preview",
    thinking_level="medium",
)
repairer = VlmParseRepairer(
    llm_client=llm,
    pdf_path=Path("paper.pdf"),
    page_image_dir=Path("outputs/.../page_images"),
    max_total_calls=30,
)
result = await repairer.repair(markdown)
print(f"detected={result.detected}, applied={result.applied}")
```

**設定キー (settings.yaml):**

| キー | デフォルト | 説明 |
|------|-----------|-----|
| `defaults.arxiv_translate.vlm_repair.enabled` | `true` | 全体の有効/無効 |
| `defaults.arxiv_translate.vlm_repair.provider` | `gemini` | 使用するVLMプロバイダ |
| `defaults.arxiv_translate.vlm_repair.model` | `gemini-3-flash-preview` | モデル名（精度重視） |
| `defaults.arxiv_translate.vlm_repair.thinking_level` | `medium` | 図表理解のための思考深度 |
| `defaults.arxiv_translate.vlm_repair.max_total_calls` | `30` | 1論文あたりのVLM呼び出し上限 |

---

### DuplicateDetector

類似記事を検出してグループ化するクラス。

**ファイル:** `minitools/processors/duplicate_detector.py`

**補助クラス/関数:**

```python
class UnionFind:
    """Union-Findデータ構造（クラスタリング用）"""

    def __init__(self, n: int):
        """
        Args:
            n: 要素数
        """

    def find(self, x: int) -> int:
        """要素の根を取得（経路圧縮付き）"""

    def union(self, x: int, y: int) -> None:
        """2つの要素を同じグループに統合"""

    def get_groups(self) -> Dict[int, List[int]]:
        """各グループのメンバーを返す"""


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    2つのベクトル間のコサイン類似度を計算

    Args:
        vec1: ベクトル1
        vec2: ベクトル2

    Returns:
        コサイン類似度（-1.0〜1.0）
    """
```

**メインクラス:**

```python
class DuplicateDetector:
    """類似記事検出クラス"""

    def __init__(
        self,
        embedding_client: BaseEmbeddingClient,
        similarity_threshold: float = 0.85
    ):
        """
        コンストラクタ

        Args:
            embedding_client: Embeddingクライアント
            similarity_threshold: 類似度閾値（デフォルト: 0.85）
        """

    async def detect_duplicates(
        self,
        articles: List[Dict[str, Any]]
    ) -> List[List[Dict[str, Any]]]:
        """
        類似記事をグループ化して返す

        Args:
            articles: 記事データのリスト

        Returns:
            類似記事グループのリスト（各グループは記事リスト）
        """

    def select_representatives(
        self,
        groups: List[List[Dict[str, Any]]],
        top_n: int = 20
    ) -> List[Dict[str, Any]]:
        """
        各グループから代表記事を選出し、上位N件を返す

        Args:
            groups: 類似記事グループのリスト
            top_n: 取得する記事数（デフォルト: 20）

        Returns:
            代表記事のリスト（スコア降順）
        """


async def deduplicate_articles(
    articles: List[Dict[str, Any]],
    embedding_client: BaseEmbeddingClient,
    similarity_threshold: float = 0.85,
    buffer_ratio: float = 2.5,
    top_n: int = 20
) -> List[Dict[str, Any]]:
    """
    記事リストから重複を除去して上位N件を返す

    Args:
        articles: 記事データのリスト（importance_score付き）
        embedding_client: Embeddingクライアント
        similarity_threshold: 類似度閾値（デフォルト: 0.85）
        buffer_ratio: 候補記事の倍率（デフォルト: 2.5）
        top_n: 最終的に取得する記事数（デフォルト: 20）

    Returns:
        重複除去済みの上位N件記事リスト
    """
```

**使用例:**
```python
from minitools.llm import get_embedding_client
from minitools.processors import DuplicateDetector, deduplicate_articles

embedding = get_embedding_client(provider="ollama")

# クラスを直接使用
detector = DuplicateDetector(
    embedding_client=embedding,
    similarity_threshold=0.85
)
groups = await detector.detect_duplicates(articles)
representatives = detector.select_representatives(groups, top_n=20)

# 便利関数を使用
deduped = await deduplicate_articles(
    articles=articles,
    embedding_client=embedding,
    similarity_threshold=0.85,
    top_n=20
)
```

---

### ArxivWeeklyProcessor

ArXiv週次ダイジェスト生成プロセッサ。2層構成（HF upvotes + LLMスコアリング）によるランキングとバッチ処理による高速スコアリングを実現。

**ファイル:** `minitools/processors/arxiv_weekly.py`

```python
class ArxivWeeklyProcessor:
    """ArXiv週次ダイジェスト生成プロセッサ"""

    def __init__(
        self,
        llm_client: BaseLLMClient,
        trend_researcher: Optional[TrendResearcher] = None,
        hf_researcher: Optional[HFPapersResearcher] = None,
        max_concurrent: int = 3,
        batch_size: Optional[int] = None
    ):
        """
        コンストラクタ

        Args:
            llm_client: LLMクライアントインスタンス
            trend_researcher: TrendResearcherインスタンス（省略時は使用しない）
            hf_researcher: HFPapersResearcherインスタンス（省略時はHFセクションをスキップ）
            max_concurrent: 最大並列処理数（デフォルト: 3）
            batch_size: バッチスコアリングのサイズ（省略時は設定ファイルから取得、デフォルト: 20）
        """

    @staticmethod
    def _extract_arxiv_id(url: str) -> str:
        """URLからarXiv IDを抽出

        Args:
            url: arXiv URL (例: "https://arxiv.org/abs/2601.00001v1")

        Returns:
            arXiv ID (例: "2601.00001")、抽出できない場合は空文字列
        """

    async def rank_papers_by_importance(
        self,
        papers: List[Dict[str, Any]],
        trends: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        各論文に重要度スコア(1-10)を付与（バッチ処理対応）

        バッチ処理により複数論文を1回のLLM呼び出しでスコアリングし、
        処理時間を大幅に短縮します。バッチ処理が失敗した場合は
        自動的に個別処理にフォールバックします。

        評価基準（トレンドあり: 4観点、トレンドなし: 3観点）:
        - 技術的新規性: 新しい手法・アプローチの独創性
        - 業界インパクト: 実務・産業への影響可能性
        - 実用性: 実際に使える・応用できる度合い
        - トレンド関連性: 現在のAIトレンドとの関連度（トレンドありのみ）

        Args:
            papers: 論文リスト
            trends: TrendResearcherから取得したトレンド情報

        Returns:
            importance_scoreが付与された論文リスト
        """

    async def select_top_papers(
        self,
        papers: List[Dict[str, Any]],
        top_n: int = 10
    ) -> List[Dict[str, Any]]:
        """
        スコア上位N件を選出

        Args:
            papers: importance_scoreが付与された論文リスト
            top_n: 取得する論文数（デフォルト: 10）

        Returns:
            上位N件の論文リスト
        """

    async def generate_paper_highlights(
        self,
        papers: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        選出理由と重要ポイントを生成

        Args:
            papers: 論文リスト

        Returns:
            selection_reason, key_pointsが付与された論文リスト
        """

    async def process(
        self,
        papers: List[Dict[str, Any]],
        top_n: int = 10,
        use_trends: bool = True,
        hf_top_n: int = 5,
        llm_top_n: int = 5
    ) -> Dict[str, Any]:
        """
        一括処理: HF統計取得 → トレンド調査 → スコアリング → 選出 → ハイライト生成

        2層構成:
        - セクション1: HF upvote上位 (hf_researcher が指定されている場合)
        - セクション2: LLMスコアリング上位 (セクション1を除外した残り)

        Args:
            papers: 全論文リスト
            top_n: 上位論文数（後方互換、hf_researcher未指定時に使用）
            use_trends: Trueの場合、Tavily APIでトレンドを調査してスコアリングに使用
            hf_top_n: HFセクションの取得件数（デフォルト: 5）
            llm_top_n: LLMセクションの取得件数（デフォルト: 5）

        Returns:
            処理結果の辞書:
            - trend_info: トレンド情報（use_trends=Falseの場合はNone）
            - papers: 全セクションの論文をマージ（後方互換）
            - total_papers: 処理した論文総数
            - hf_papers: セクション1の論文リスト（HF upvote上位）
            - llm_papers: セクション2の論文リスト（LLMスコア上位）
        """
```

**使用例:**
```python
from minitools.llm import get_llm_client
from minitools.processors import ArxivWeeklyProcessor
from minitools.researchers import TrendResearcher, HFPapersResearcher

llm = get_llm_client(provider="openai")
trend_researcher = TrendResearcher()

async with HFPapersResearcher() as hf_researcher:
    processor = ArxivWeeklyProcessor(
        llm_client=llm,
        trend_researcher=trend_researcher,
        hf_researcher=hf_researcher,
    )

    result = await processor.process(
        papers=papers_list,
        use_trends=True,
        hf_top_n=5,
        llm_top_n=5,
    )

print(f"HF papers: {len(result['hf_papers'])}")
print(f"LLM papers: {len(result['llm_papers'])}")
for paper in result['papers']:
    print(f"{paper['title']} - スコア: {paper['importance_score']}")
    print(f"  選出理由: {paper['selection_reason']}")
    print(f"  重要ポイント: {paper['key_points']}")
```

**CLIオプション:**
```bash
# 基本使用
uv run arxiv-weekly                        # デフォルト設定で実行
uv run arxiv-weekly --days 14              # 過去14日分を取得
uv run arxiv-weekly --top 20               # 上位20件を選出

# LLMプロバイダー指定
uv run arxiv-weekly --provider openai      # OpenAI APIを使用

# オプション
uv run arxiv-weekly --dry-run              # Slack送信をスキップ
uv run arxiv-weekly --output out.md        # ファイルに保存
uv run arxiv-weekly --no-trends            # トレンド調査をスキップ
```

---

### XTrendProcessor

X トレンドデータをLLMで処理（AI関連フィルタリング、Tweet要約、キーワード・タイムライン処理）するプロセッサ。

**ファイル:** `minitools/processors/x_trend.py`

```python
@dataclass
class TrendSummary:
    """トレンド要約"""
    trend_name: str
    topics: list[str]               # 話題の箇条書き（最大5件）
    key_opinions: list[str]         # 主要意見（最大3件）
    retweet_total: int = 0          # 合計リツイート数
    region: str = ""                # "japan" or "global"

@dataclass
class KeywordSummary:
    """キーワード検索要約"""
    keyword: str
    topics: list[str]
    key_opinions: list[str]
    retweet_total: int = 0

@dataclass
class TimelineSummary:
    """タイムライン要約"""
    username: str
    topics: list[str]
    key_opinions: list[str]
    retweet_total: int = 0

@dataclass
class ProcessResult:
    """全処理結果"""
    trend_summaries: dict[str, list[TrendSummary]] = field(default_factory=dict)
    keyword_summaries: list[KeywordSummary] = field(default_factory=list)
    timeline_summaries: list[TimelineSummary] = field(default_factory=list)


class XTrendProcessor:
    """X トレンド処理プロセッサ"""

    def __init__(self, llm_client: BaseLLMClient, max_concurrent: int = 3): ...

    async def filter_ai_trends(self, trends: list[TrendWithTweets], max_trends: int = 10) -> list[TrendWithTweets]:
        """AI関連トレンドをLLMでバッチフィルタリング（最大max_trends件）"""

    async def summarize_trend(self, trend_with_tweets: TrendWithTweets) -> TrendSummary:
        """トレンドのツイートを日本語で要約"""

    async def filter_ai_tweets(self, tweets: list[Tweet]) -> list[Tweet]:
        """AI関連ツイートをLLMでフィルタリング"""

    async def summarize_keyword_results(self, results: list[KeywordSearchResult]) -> list[KeywordSummary]:
        """キーワード検索結果を並列で要約"""

    async def summarize_timeline_results(self, results: list[UserTimelineResult]) -> list[TimelineSummary]:
        """タイムライン結果をフィルタリング後に要約"""

    async def process_all(self, collect_result: CollectResult, max_trends: int = 10, collector: XTrendCollector | None = None) -> ProcessResult:
        """3ソースを統合処理（トレンド: フィルタ→ツイート取得→要約、キーワード: 要約、タイムライン: フィルタ→要約）"""
```

**使用例:**
```python
from minitools.llm import get_llm_client
from minitools.processors.x_trend import XTrendProcessor

llm = get_llm_client(provider="openai")
processor = XTrendProcessor(llm_client=llm)

# 3ソース統合処理
async with XTrendCollector() as collector:
    collect_result = await collector.collect_all(
        regions=["japan"], keywords=["AI Agent"], watch_accounts=["kaboratory"]
    )
    process_result = await processor.process_all(
        collect_result=collect_result, max_trends=10, collector=collector
    )
    print(f"Trends: {sum(len(v) for v in process_result.trend_summaries.values())}")
    print(f"Keywords: {len(process_result.keyword_summaries)}")
    print(f"Timelines: {len(process_result.timeline_summaries)}")
```

---

## Publishers

### NotionPublisher

Notionデータベースにコンテンツを保存するクラス。

**ファイル:** `minitools/publishers/notion.py`

```python
class NotionPublisher:
    """Notionデータベースにコンテンツを保存するクラス"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        source_type: Optional[str] = None
    ):
        """
        コンストラクタ

        Args:
            api_key: Notion APIキー（デフォルト: 環境変数から取得）
            source_type: ソースタイプ（'arxiv', 'medium', 'google_alerts'）
        """

    async def _retry_api_call(
        self,
        func,
        max_retries: int = 3,
        description: str = "API call"
    ):
        """
        Notion APIコールをレートリミット対応のリトライ付きで実行
        全APIメソッド（check_existing, create_page, find_page_by_url,
        update_page_properties, append_blocks）で使用。

        Args:
            func: 実行する同期関数（lambda）
            max_retries: 最大リトライ回数（デフォルト: 3）
            description: ログ用の説明

        Returns:
            API呼び出しの結果

        Note:
            レートリミットエラー時のみリトライ（2s, 4s, 8s の指数バックオフ）
            それ以外のエラーは即座にraise
        """

    async def check_existing(
        self,
        database_id: str,
        url: str
    ) -> bool:
        """
        URLが既にデータベースに存在するかチェック

        Args:
            database_id: NotionデータベースID
            url: チェックするURL

        Returns:
            存在する場合True
        """

    async def create_page(
        self,
        database_id: str,
        properties: Dict[str, Any]
    ) -> Optional[str]:
        """
        Notionページを作成

        Args:
            database_id: NotionデータベースID
            properties: ページプロパティ

        Returns:
            作成されたページのID
        """

    async def save_article(
        self,
        database_id: str,
        article_data: Dict[str, Any]
    ) -> bool:
        """
        記事をNotionデータベースに保存

        Args:
            database_id: NotionデータベースID
            article_data: 記事データ

        Returns:
            保存成功の場合True
        """

    async def batch_save_articles(
        self,
        database_id: str,
        articles: List[Dict[str, Any]],
        max_concurrent: int = 3
    ) -> Dict[str, Any]:
        """
        複数の記事を並列でNotionに保存

        Args:
            database_id: NotionデータベースID
            articles: 記事データのリスト
            max_concurrent: 最大同時実行数

        Returns:
            {"stats": {success, skipped, failed}, "results": {...}}
        """

    async def update_page_properties(
        self,
        page_id: str,
        properties: Dict[str, Any]
    ) -> bool:
        """
        既存ページのプロパティを更新

        Args:
            page_id: NotionページID
            properties: 更新するプロパティ辞書

        Returns:
            更新成功の場合True
        """

    async def find_page_by_url(
        self,
        database_id: str,
        url: str
    ) -> Optional[PageInfo]:
        """
        URLでNotionデータベースを検索し、既存ページの情報を取得

        Args:
            database_id: NotionデータベースID
            url: 検索するURL

        Returns:
            PageInfo(page_id, is_translated)（見つからない場合はNone）
        """

    async def append_blocks(
        self,
        page_id: str,
        blocks: List[Dict[str, Any]]
    ) -> bool:
        """
        既存ページにブロックを追記（100ブロック単位でバッチ処理）

        Args:
            page_id: 追記先のページID
            blocks: Notionブロック形式の辞書リスト

        Returns:
            追記成功の場合True
        """

    async def upload_file(
        self,
        file_path: Path,
        mime_type: Optional[str] = None,
    ) -> Optional[str]:
        """
        画像ファイルをNotion File Upload APIにアップロードし、file_upload_idを返す

        2 段階の API 呼び出し:
          1. POST /v1/file_uploads で upload_url を取得
          2. 取得した upload_url に multipart/form-data で画像を送信（3回リトライ）

        5MB超の画像はwarningログを出力し、Noneを返す。
        mime_typeがNoneの場合はmimetypes.guess_type()で推定する。

        Args:
            file_path: アップロードする画像ファイルのパス
            mime_type: MIMEタイプ（指定しない場合は推定）

        Returns:
            file_upload_id (UUID文字列)。失敗時はNone。
        """
```

**使用例:**
```python
publisher = NotionPublisher(source_type='medium')

# 単一記事の保存
success = await publisher.save_article(
    database_id="xxx",
    article_data={
        'title': 'Article Title',
        'url': 'https://example.com',
        'author': 'Author Name',
        'japanese_title': '記事タイトル',
        'japanese_summary': '記事の要約...'
    }
)

# バッチ保存
result = await publisher.batch_save_articles(
    database_id="xxx",
    articles=articles_list,
    max_concurrent=3
)
print(f"成功: {result['stats']['success']}")

# 既存ページにブロック追記（全文翻訳機能）
page_info = await publisher.find_page_by_url(database_id="xxx", url="https://medium.com/...")
if page_info:
    if page_info.is_translated:
        print("Already translated, skipping")
    else:
        blocks = NotionBlockBuilder().build_blocks(translated_markdown)
        success = await publisher.append_blocks(page_info.page_id, blocks)
        if success:
            await publisher.update_page_properties(page_info.page_id, {
                "Translated": {"checkbox": True}
            })
```

---

### NotionBlockBuilder

Markdown文字列をNotion APIのブロック形式に変換するクラス。

**ファイル:** `minitools/publishers/notion_block_builder.py`

```python
class NotionBlockBuilder:
    """MarkdownをNotion APIブロック形式に変換するクラス"""

    def build_blocks(
        self,
        markdown: str,
        image_uploads: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Markdown文字列をNotionブロックのリストに変換

        対応ブロックタイプ:
        - divider（区切り線）
        - heading_1, heading_2, heading_3
        - paragraph
        - code（言語指定付き）
        - image（外部URL / file_upload）
        - bulleted_list_item, numbered_list_item
        - quote
        - equation（ブロック数式 $$...$$）
        - table（Markdownテーブル → Notion table）

        rich_text内のインライン書式:
        - bold, italic, inline code, link
        - equation（インライン数式 $...$、エスケープ \\$ は通常文字として扱う）

        Args:
            markdown: 変換するMarkdown文字列
            image_uploads: ローカル画像ファイル名 → file_upload_id のマッピング。
                Noneまたは空辞書の場合、ローカル画像はキャプション段落にフォールバックする。

        Returns:
            Notion APIブロック形式の辞書リスト
        """
```

**使用例:**
```python
builder = NotionBlockBuilder()
# 基本: 外部URL画像のみ（後方互換）
blocks = builder.build_blocks(translated_markdown)

# ローカル画像を file_upload 型で埋め込む
image_uploads = {"_page_0_Figure_5.jpeg": "abc-123-uuid"}
blocks = builder.build_blocks(translated_markdown, image_uploads=image_uploads)
```

---

### SlackPublisher

Slackにメッセージを送信するクラス。

**ファイル:** `minitools/publishers/slack.py`

```python
class SlackPublisher:
    """Slackにメッセージを送信するクラス"""

    def __init__(self, webhook_url: Optional[str] = None):
        """
        コンストラクタ

        Args:
            webhook_url: Slack Webhook URL
        """

    async def __aenter__(self) -> 'SlackPublisher':
        """非同期コンテキストマネージャーのエントリー"""

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """非同期コンテキストマネージャーのクリーンアップ"""

    def set_webhook_url(self, webhook_url: str):
        """Webhook URLを設定"""

    async def send_message(
        self,
        message: str,
        webhook_url: Optional[str] = None
    ) -> bool:
        """
        Slackにメッセージを送信

        Args:
            message: 送信するメッセージ
            webhook_url: 使用するWebhook URL（オプション）

        Returns:
            送信成功の場合True
        """

    async def send_messages(
        self,
        messages: List[str],
        webhook_url: Optional[str] = None
    ) -> bool:
        """
        複数メッセージを順番にSlackに送信（0.5秒間隔）

        Args:
            messages: 送信するメッセージのリスト
            webhook_url: 使用するWebhook URL（オプション）

        Returns:
            全メッセージの送信成功の場合True
        """

    def format_articles_message(
        self,
        articles: List[Dict[str, Any]],
        date: Optional[str] = None,
        title: str = "Daily Digest"
    ) -> str:
        """
        記事リストをSlackメッセージ形式にフォーマット

        Args:
            articles: 記事データのリスト
            date: 日付文字列
            title: メッセージタイトル

        Returns:
            フォーマットされたメッセージ
        """

    def format_simple_list(
        self,
        items: List[str],
        title: str = "通知"
    ) -> str:
        """
        シンプルなリストをSlackメッセージ形式にフォーマット

        Args:
            items: アイテムのリスト
            title: メッセージタイトル

        Returns:
            フォーマットされたメッセージ
        """

    async def send_articles(
        self,
        articles: List[Dict[str, Any]],
        webhook_url: Optional[str] = None,
        date: Optional[str] = None,
        title: str = "Daily Digest"
    ) -> bool:
        """
        記事リストをフォーマットしてSlackに送信

        Args:
            articles: 記事データのリスト
            webhook_url: 使用するWebhook URL
            date: 日付文字列
            title: メッセージタイトル

        Returns:
            送信成功の場合True
        """

    def format_weekly_digest(
        self,
        start_date: str,
        end_date: str,
        trend_summary: str,
        articles: List[Dict[str, Any]]
    ) -> str:
        """
        週次ダイジェストをSlackメッセージ形式にフォーマット

        Args:
            start_date: 期間開始日（YYYY-MM-DD形式）
            end_date: 期間終了日（YYYY-MM-DD形式）
            trend_summary: 週のトレンド総括
            articles: 上位記事リスト（digest_summary付き）

        Returns:
            フォーマットされたメッセージ
        """

    async def send_weekly_digest(
        self,
        start_date: str,
        end_date: str,
        trend_summary: str,
        articles: List[Dict[str, Any]],
        webhook_url: Optional[str] = None
    ) -> bool:
        """
        週次ダイジェストをフォーマットしてSlackに送信

        Args:
            start_date: 期間開始日
            end_date: 期間終了日
            trend_summary: トレンド総括
            articles: 上位記事リスト
            webhook_url: 使用するWebhook URL（オプション）

        Returns:
            送信成功の場合True
        """

    def format_arxiv_weekly(
        self,
        start_date: str,
        end_date: str,
        papers: List[Dict[str, Any]],
        trend_summary: Optional[str] = None,
        hf_papers: Optional[List[Dict[str, Any]]] = None,
        llm_papers: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        ArXiv週次ダイジェストをSlackメッセージ形式にフォーマット

        hf_papers/llm_papers が渡された場合は2セクション構成:
        - セクション1「今週の注目論文（HuggingFace Upvotes）」: upvote数・コメント数表示
        - セクション2「AIが注目する論文（LLMスコア）」: LLMスコア表示
        渡されない場合は従来のフォーマット（後方互換）。

        Args:
            start_date: 期間開始日（YYYY-MM-DD形式）
            end_date: 期間終了日（YYYY-MM-DD形式）
            papers: 上位論文リスト（後方互換、hf/llm未指定時に使用）
            trend_summary: 今週のAIトレンド概要（省略可）
            hf_papers: セクション1のHF upvote上位論文（省略可）
            llm_papers: セクション2のLLMスコア上位論文（省略可）

        Returns:
            フォーマットされたメッセージ（3000文字以内）
        """

    async def send_arxiv_weekly(
        self,
        start_date: str,
        end_date: str,
        papers: List[Dict[str, Any]],
        trend_summary: Optional[str] = None,
        hf_papers: Optional[List[Dict[str, Any]]] = None,
        llm_papers: Optional[List[Dict[str, Any]]] = None,
        webhook_url: Optional[str] = None
    ) -> bool:
        """
        ArXiv週次ダイジェストをフォーマットしてSlackに送信

        Args:
            start_date: 期間開始日
            end_date: 期間終了日
            papers: 上位論文リスト
            trend_summary: トレンド総括（省略可）
            hf_papers: HF upvote上位論文（省略可）
            llm_papers: LLMスコア上位論文（省略可）
            webhook_url: 使用するWebhook URL（オプション）

        Returns:
            送信成功の場合True
        """

    @staticmethod
    def format_x_trend_digest_sections(
        process_result: Any,
    ) -> List[str]:
        """
        Xトレンドダイジェストをセクションごとのメッセージリストとしてフォーマット

        省略なしで全内容を含む。セクション構成:
        - メッセージ1: ヘッダー + トレンド（グローバル＋日本）
        - メッセージ2: キーワード検索ハイライト
        - メッセージ3: 注目アカウントの発信
        空のセクションはスキップされる。

        Args:
            process_result: ProcessResult または Dict[str, List[TrendSummary]]（後方互換）

        Returns:
            セクションごとのメッセージリスト
        """

    @staticmethod
    def format_x_trend_digest(
        process_result: Any,
    ) -> str:
        """
        Xトレンドダイジェストをフォーマット（後方互換ラッパー）

        内部でformat_x_trend_digest_sections()を呼び出し、
        結果を改行で結合した文字列を返す。

        Args:
            process_result: ProcessResult または Dict[str, List[TrendSummary]]（後方互換）

        Returns:
            フォーマットされたメッセージ
        """
```

**使用例:**
```python
async with SlackPublisher(webhook_url) as slack:
    # シンプルなメッセージ送信
    await slack.send_message("Hello, Slack!")

    # 記事リストの送信
    await slack.send_articles(
        articles=articles_list,
        date="2024-01-15",
        title="Medium Daily Digest"
    )

    # 週次ダイジェストの送信
    await slack.send_weekly_digest(
        start_date="2024-01-08",
        end_date="2024-01-15",
        trend_summary="今週のAI分野では...",
        articles=top_articles
    )

    # ArXiv週次ダイジェストの送信
    await slack.send_arxiv_weekly(
        start_date="2024-01-08",
        end_date="2024-01-15",
        papers=top_papers,
        trend_summary="今週のAIトレンド..."
    )

    # X トレンドダイジェストの送信（セクション分割、省略なし）
    messages = SlackPublisher.format_x_trend_digest_sections(process_result)
    await slack.send_messages(messages)

    # 後方互換: 単一文字列として取得
    message = SlackPublisher.format_x_trend_digest(process_result)
    await slack.send_message(message)
```

---

## Utils

### Config

設定管理クラス（シングルトン）。

**ファイル:** `minitools/utils/config.py`

```python
class Config:
    """設定管理クラス（シングルトン）"""

    def __init__(self):
        """コンストラクタ（シングルトン）"""

    def load_config(self):
        """settings.yamlを読み込み"""

    def get(
        self,
        key_path: str,
        default: Any = None
    ) -> Any:
        """
        ドット記法でネストされた値を取得

        Args:
            key_path: ドット区切りのキーパス
            default: キーが存在しない場合のデフォルト値

        Returns:
            設定値またはデフォルト値

        Examples:
            >>> config.get('models.translation')
            'gemma3:27b'
            >>> config.get('processing.retry_count', 5)
            3
        """

    @staticmethod
    def get_api_key(service: str) -> Optional[str]:
        """
        APIキーを環境変数から取得

        Args:
            service: サービス名

        Returns:
            APIキーまたはWebhook URL

        Examples:
            >>> Config.get_api_key('notion')
            'secret_xxx...'
            >>> Config.get_api_key('slack_arxiv')
            'https://hooks.slack.com/...'
        """

    def reload(self):
        """設定を再読み込み"""

    def to_dict(self) -> dict:
        """現在の設定を辞書として返す"""


def get_config() -> Config:
    """Config インスタンスを取得"""
```

**使用例:**
```python
from minitools.utils.config import get_config, Config

config = get_config()

# 設定値の取得
model = config.get('models.translation', 'default-model')
batch_size = config.get('output.notion.batch_size', 10)

# APIキーの取得
notion_key = Config.get_api_key('notion')
slack_url = Config.get_api_key('slack_arxiv')
```

---

### Logger

カラー対応ロギングモジュール。

**ファイル:** `minitools/utils/logger.py`

```python
class ColoredFormatter(logging.Formatter):
    """ログレベルに応じて色付きでターミナルに出力するフォーマッター"""

    COLORS = {
        'DEBUG': '\033[36m',     # シアン
        'INFO': '\033[32m',      # 緑
        'WARNING': '\033[33m',   # 黄色
        'ERROR': '\033[31m',     # 赤
        'CRITICAL': '\033[35m',  # マゼンタ
    }

    def __init__(
        self,
        fmt: Optional[str] = None,
        datefmt: Optional[str] = None,
        use_colors: bool = True
    ):
        """
        コンストラクタ

        Args:
            fmt: ログフォーマット
            datefmt: 日付フォーマット
            use_colors: カラー出力の有効/無効
        """


def setup_logger(
    name: str = __name__,
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    console_level: Optional[int] = None,
    file_level: Optional[int] = None,
    use_colors: bool = True
) -> logging.Logger:
    """
    統一されたロガーを設定する

    Args:
        name: ロガー名（通常は__name__）
        log_file: ログファイル名
        level: デフォルトのログレベル
        console_level: コンソール出力のログレベル
        file_level: ファイル出力のログレベル
        use_colors: ターミナル出力でカラーを使用するか

    Returns:
        設定されたロガーインスタンス
    """


def get_logger(
    name: str = __name__,
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    簡易的なロガー取得関数

    Args:
        name: ロガー名
        log_file: ログファイル名

    Returns:
        設定されたロガーインスタンス
    """
```

**使用例:**
```python
from minitools.utils.logger import get_logger, setup_logger

# 簡易ロガー
logger = get_logger(__name__)

# 詳細設定付きロガー
logger = setup_logger(
    name="scripts.arxiv",
    log_file="arxiv.log",
    level=logging.DEBUG,
    use_colors=True
)

logger.debug("デバッグ情報")
logger.info("処理開始")
logger.warning("警告メッセージ")
logger.error("エラー発生")
```

---

## Dataclass定義

### Article

Medium記事情報を格納するデータクラス。

**ファイル:** `minitools/collectors/medium.py`

```python
@dataclass
class Article:
    """記事情報を格納するデータクラス"""
    title: str               # 記事タイトル
    url: str                 # 記事URL
    author: str              # 著者名
    claps: int = 0           # 拍手数
    preview: str = ""        # メールから抽出したプレビューテキスト
    japanese_title: str = "" # 日本語タイトル
    summary: str = ""        # 英語要約
    japanese_summary: str = ""  # 日本語要約
    date_processed: str = "" # 処理日時
```

### Alert

Google Alertsアラート情報を格納するデータクラス。

**ファイル:** `minitools/collectors/google_alerts.py`

```python
@dataclass
class Alert:
    """アラート情報を格納するデータクラス"""
    title: str               # アラートタイトル
    url: str                 # 記事URL
    source: str              # ソース（ドメイン名）
    snippet: str = ""        # スニペット
    japanese_title: str = "" # 日本語タイトル
    japanese_summary: str = ""  # 日本語要約
    date_processed: str = "" # 処理日時
    article_content: str = ""   # 記事本文
    email_date: str = ""     # メール配信日
    tags: List[str] = None   # タグリスト

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
```

### Tweet

ツイート情報を格納するデータクラス。

**ファイル:** `minitools/collectors/x_trend.py`

```python
@dataclass
class Tweet:
    """ツイート情報"""
    text: str                # ツイートテキスト
    retweet_count: int = 0   # リツイート数
    like_count: int = 0      # いいね数
    author: str = ""         # 投稿者名
```

### Trend

X トレンド情報を格納するデータクラス。

**ファイル:** `minitools/collectors/x_trend.py`

```python
@dataclass
class Trend:
    """トレンド情報"""
    name: str                # トレンド名
    tweet_volume: int = 0    # ツイート数
    region: str = ""         # "japan" or "global"
```

### TrendWithTweets

トレンドと関連ツイートのセットを格納するデータクラス。

**ファイル:** `minitools/collectors/x_trend.py`

```python
@dataclass
class TrendWithTweets:
    """トレンドと関連ツイートのセット"""
    trend: Trend
    tweets: list[Tweet] = field(default_factory=list)
```

### KeywordSearchResult

キーワード検索結果を格納するデータクラス。

**ファイル:** `minitools/collectors/x_trend.py`

```python
@dataclass
class KeywordSearchResult:
    """キーワード検索結果"""
    keyword: str
    tweets: list[Tweet] = field(default_factory=list)
```

### UserTimelineResult

ユーザータイムライン結果を格納するデータクラス。

**ファイル:** `minitools/collectors/x_trend.py`

```python
@dataclass
class UserTimelineResult:
    """ユーザータイムライン結果"""
    username: str
    tweets: list[Tweet] = field(default_factory=list)
```

### CollectResult

全収集結果を格納するデータクラス。

**ファイル:** `minitools/collectors/x_trend.py`

```python
@dataclass
class CollectResult:
    """全収集結果を格納"""
    trends: dict[str, list[TrendWithTweets]] = field(default_factory=dict)
    keyword_results: list[KeywordSearchResult] = field(default_factory=list)
    timeline_results: list[UserTimelineResult] = field(default_factory=list)
```

### TrendSummary

トレンド要約情報を格納するデータクラス。

**ファイル:** `minitools/processors/x_trend.py`

```python
@dataclass
class TrendSummary:
    """トレンド要約"""
    trend_name: str
    topics: list[str] = field(default_factory=list)       # 話題の箇条書き（最大5件）
    key_opinions: list[str] = field(default_factory=list)  # 主要意見（最大3件）
    retweet_total: int = 0   # RT数合計
    region: str = ""         # "japan" or "global"
```

### KeywordSummary

キーワード検索要約を格納するデータクラス。

**ファイル:** `minitools/processors/x_trend.py`

```python
@dataclass
class KeywordSummary:
    """キーワード検索要約"""
    keyword: str
    topics: list[str] = field(default_factory=list)
    key_opinions: list[str] = field(default_factory=list)
    retweet_total: int = 0
```

### TimelineSummary

ユーザータイムライン要約を格納するデータクラス。

**ファイル:** `minitools/processors/x_trend.py`

```python
@dataclass
class TimelineSummary:
    """ユーザータイムライン要約"""
    username: str
    topics: list[str] = field(default_factory=list)
    key_opinions: list[str] = field(default_factory=list)
    retweet_total: int = 0
```

### ProcessResult

全処理結果を格納するデータクラス。

**ファイル:** `minitools/processors/x_trend.py`

```python
@dataclass
class ProcessResult:
    """全処理結果"""
    trend_summaries: dict[str, list[TrendSummary]] = field(default_factory=dict)
    keyword_summaries: list[KeywordSummary] = field(default_factory=list)
    timeline_summaries: list[TimelineSummary] = field(default_factory=list)
```
