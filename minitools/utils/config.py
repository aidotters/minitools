"""
Configuration management for minitools.
Handles both settings.yaml (application config) and .env (secrets).
"""

import os
import yaml
from pathlib import Path
from typing import Any, Optional
from dotenv import load_dotenv

from minitools.utils.logger import get_logger

logger = get_logger(__name__)


class Config:
    """設定管理クラス（シングルトン）

    settings.yaml: アプリケーション設定（モデル名、処理パラメータ等）
    .env: セキュリティ関連（APIキー、Webhook URL等）
    """

    _instance = None
    _config = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            # .envファイルを読み込み
            load_dotenv()
            # settings.yamlを読み込み
            self.load_config()
            self._initialized = True

    def load_config(self):
        """settings.yamlを読み込み"""
        # 設定ファイルの検索パス（優先順位順）
        config_paths = [
            Path.cwd() / "settings.yaml",
            Path.cwd() / "settings.yml",
            Path.home() / ".minitools" / "settings.yaml",
            Path(__file__).parent.parent.parent / "settings.yaml",
        ]

        for path in config_paths:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        self._config = yaml.safe_load(f)
                        logger.info(f"Loaded config from: {path}")
                        return
                except Exception as e:
                    logger.error(f"Failed to load config from {path}: {e}")

        # デフォルト設定を使用
        logger.info("Using default configuration (no settings.yaml found)")
        self._config = self._get_default_config()

    def _get_default_config(self) -> dict:
        """デフォルト設定を返す"""
        return {
            "models": {
                "translation": "gemma3:27b",
                "summarization": "gemma3:27b",
                "youtube_summary": "gemma2",
            },
            "processing": {
                "max_concurrent_articles": 10,
                "max_concurrent_ollama": 3,
                "max_concurrent_notion": 3,
                "max_concurrent_http": 10,
                "retry_count": 3,
                "retry_delay": 2,
            },
            "defaults": {
                "arxiv": {"min_upvotes": 10, "max_papers": 7, "weekly_top": 10},
                "arxiv_search": {
                    "keywords": ["LLM", "(RAG OR FINETUNING OR AGENT)"],
                    "max_results": 50,
                },
                "google_alerts": {"hours_back": 6, "max_alerts_per_message": 12},
                "medium": {"fetch_today": True},
                "youtube": {
                    "output_dir": "outputs",
                    "whisper_model": "mlx-community/whisper-large-v3-turbo",
                    "audio_quality": "192",
                    "temp_dir": "outputs/temp",
                },
            },
            "logging": {
                "level": "INFO",
                "colored": True,
                "log_dir": "outputs/logs",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
            "gmail": {
                "credentials_file": "credentials.json",
                "token_file": "token.pickle",
                "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
            },
            "output": {
                "save_transcripts": True,
                "save_summaries": True,
                "notion": {
                    "batch_size": 10,
                    "properties": {"title_max_length": 255, "summary_max_length": 2000},
                },
                "slack": {
                    "max_message_length": 3500,
                    "use_blocks": False,
                    "include_timestamps": True,
                },
            },
        }

    def get(self, key_path: str, default: Any = None) -> Any:
        """ドット記法でネストされた値を取得

        Args:
            key_path: ドット区切りのキーパス（例: 'models.translation'）
            default: キーが存在しない場合のデフォルト値

        Returns:
            設定値またはデフォルト値

        Examples:
            >>> config = Config()
            >>> config.get('models.translation')
            'gemma3:27b'
            >>> config.get('processing.retry_count', 5)
            3
            >>> config.get('nonexistent.key', 'default')
            'default'
        """
        if self._config is None:
            return default

        keys = key_path.split(".")
        value = self._config

        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default

        return value

    @staticmethod
    def get_api_key(service: str) -> Optional[str]:
        """APIキーを環境変数から取得（セキュリティ用）

        Args:
            service: サービス名

        Returns:
            APIキーまたはWebhook URL

        Note:
            セキュリティ関連の情報は.envファイルから取得
        """
        key_mapping = {
            # Notion
            "notion": "NOTION_API_KEY",
            "notion_db_arxiv": "NOTION_DB_ID",
            "notion_db_medium": "NOTION_DB_ID_DAILY_DIGEST",
            "notion_db_alerts": "NOTION_DB_ID_GOOGLE_ALERTS",
            # Slack
            "slack_arxiv": "SLACK_WEBHOOK_URL",
            "slack_medium": "SLACK_WEBHOOK_URL_MEDIUM_DAILY_DIGEST",
            "slack_alerts": "SLACK_WEBHOOK_URL_GOOGLE_ALERTS",
            # Gmail
            "gmail_credentials": "GMAIL_CREDENTIALS_PATH",
        }

        env_key = key_mapping.get(service)
        if env_key:
            return os.getenv(env_key)

        # 直接環境変数名が渡された場合
        return os.getenv(service)

    def reload(self):
        """設定を再読み込み"""
        self._initialized = False
        self.__init__()
        logger.info("Configuration reloaded")

    def to_dict(self) -> dict:
        """現在の設定を辞書として返す"""
        return self._config.copy() if self._config else {}


# グローバルインスタンス（オプション）
_config = None


def get_config() -> Config:
    """Config インスタンスを取得"""
    global _config
    if _config is None:
        _config = Config()
    return _config
