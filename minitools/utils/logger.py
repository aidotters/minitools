#!/usr/bin/env python3
"""
共通ロギングモジュール
各スクリプトで統一されたロギング設定を提供
ターミナル出力はログレベルに応じてカラー表示
"""

import logging
import sys
from pathlib import Path
from typing import Optional


class ColoredFormatter(logging.Formatter):
    """ログレベルに応じて色付きでターミナルに出力するフォーマッター"""

    # ANSIカラーコード
    COLORS = {
        "DEBUG": "\033[36m",  # シアン
        "INFO": "\033[32m",  # 緑
        "WARNING": "\033[33m",  # 黄色
        "ERROR": "\033[31m",  # 赤
        "CRITICAL": "\033[35m",  # マゼンタ
    }
    RESET = "\033[0m"

    def __init__(
        self,
        fmt: Optional[str] = None,
        datefmt: Optional[str] = None,
        use_colors: bool = True,
    ):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and self._supports_color()

    def _supports_color(self) -> bool:
        """ターミナルがカラー出力をサポートしているか確認"""
        # Windows環境の場合
        if sys.platform == "win32":
            return False

        # CI環境や非TTY環境の場合
        if not hasattr(sys.stdout, "isatty"):
            return False
        if not sys.stdout.isatty():
            return False

        # 環境変数でカラー出力が無効化されている場合
        import os

        if os.environ.get("NO_COLOR"):
            return False

        return True

    def format(self, record: logging.LogRecord) -> str:
        """ログレコードをフォーマット（カラー付き）"""
        # カラーコードを適用する場合
        if self.use_colors and record.levelname in self.COLORS:
            # レベル名を一時的にカラー付きに変更
            original_levelname = record.levelname
            record.levelname = (
                f"{self.COLORS[record.levelname]}{record.levelname}{self.RESET}"
            )
            formatted = super().format(record)
            record.levelname = original_levelname  # 元に戻す
        else:
            # カラーなしの場合
            formatted = super().format(record)

        return formatted


def setup_logger(
    name: str = __name__,
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    console_level: Optional[int] = None,
    file_level: Optional[int] = None,
    use_colors: bool = True,
) -> logging.Logger:
    """
    統一されたロガーを設定する

    Args:
        name: ロガー名（通常は__name__を使用）
        log_file: ログファイル名（例: "medium_daily_digest.log"）
        level: デフォルトのログレベル
        console_level: コンソール出力のログレベル（指定しない場合はlevelを使用）
        file_level: ファイル出力のログレベル（指定しない場合はlevelを使用）
        use_colors: ターミナル出力でカラーを使用するか

    Returns:
        設定されたロガーインスタンス
    """
    # ロガーの取得と設定
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 既存のハンドラをクリア（重複を防ぐため）
    logger.handlers = []

    # フォーマットの定義（統一）
    format_string = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # コンソールハンドラの設定
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level or level)

    # フォーマッターを使用（カラーは必要に応じて）
    console_formatter: logging.Formatter
    if use_colors:
        console_formatter = ColoredFormatter(
            fmt=format_string, datefmt=date_format, use_colors=use_colors
        )
    else:
        console_formatter = logging.Formatter(fmt=format_string, datefmt=date_format)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # ファイルハンドラの設定（log_fileが指定されている場合）
    if log_file:
        # ログディレクトリの作成
        log_dir = Path("outputs/logs")
        log_dir.mkdir(parents=True, exist_ok=True)

        # ファイルハンドラの作成
        file_handler = logging.FileHandler(
            log_dir / log_file, mode="a", encoding="utf-8"
        )
        file_handler.setLevel(file_level or level)

        # ファイル出力には通常のフォーマッターを使用（カラーなし）
        file_formatter = logging.Formatter(fmt=format_string, datefmt=date_format)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


def attach_file_handler(
    logger_name: str,
    log_file: str,
    level: int = logging.WARNING,
) -> logging.Logger:
    """
    既存ロガー（とその子ロガー）の出力をログファイルにも書き出す

    ``minitools.*`` の各モジュールはコンソールにしか出力しないため、
    スクリプト側で ``attach_file_handler("minitools", "<script>.log")`` を呼び、
    翻訳失敗などの警告をスクリプトのログファイルにも残す用途。
    子ロガーのレコードは propagate で親ロガーのハンドラに届く。

    Args:
        logger_name: ハンドラを付けるロガー名（例: "minitools"）
        log_file: outputs/logs/ 配下のログファイル名
        level: ファイルに書き出す最小ログレベル（既定: WARNING）

    Returns:
        ハンドラを付けたロガー
    """
    logger = logging.getLogger(logger_name)
    log_dir = Path("outputs/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = (log_dir / log_file).resolve()

    # 同じファイルへのハンドラが既にあれば追加しない（重複出力防止）
    for handler in logger.handlers:
        if (
            isinstance(handler, logging.FileHandler)
            and Path(handler.baseFilename).resolve() == log_path
        ):
            return logger

    file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    # 親ロガーのレベルは変えない（子ロガーの有効レベルに影響するため）。
    # propagate されたレコードは親のレベルを通らず、ハンドラのレベルだけで絞られる。
    logger.addHandler(file_handler)
    return logger


def get_logger(name: str = __name__, log_file: Optional[str] = None) -> logging.Logger:
    """
    簡易的なロガー取得関数（デフォルト設定を使用）

    Args:
        name: ロガー名
        log_file: ログファイル名

    Returns:
        設定されたロガーインスタンス
    """
    return setup_logger(name=name, log_file=log_file)


# テスト用コード
if __name__ == "__main__":
    # テスト用のロガーを設定
    test_logger = setup_logger(
        name="test_logger", log_file="test.log", level=logging.DEBUG
    )

    # 各レベルでログを出力
    test_logger.debug("これはDEBUGメッセージです")
    test_logger.info("これはINFOメッセージです")
    test_logger.warning("これはWARNINGメッセージです")
    test_logger.error("これはERRORメッセージです")
    test_logger.critical("これはCRITICALメッセージです")

    print("\nログが outputs/logs/test.log に保存されました")
