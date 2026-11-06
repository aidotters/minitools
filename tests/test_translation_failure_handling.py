"""翻訳失敗時に英語原文が「翻訳済み」として残らないことのテスト

2026-11-06、Gemini Prepay のクレジット枯渇（402）で FullTextTranslator が
原文を返し、英語本文が Notion に翻訳済みとして保存された。その再発防止。
"""

import logging
import os
import sys

import pytest

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

import scripts.arxiv_translate as arxiv_translate  # noqa: E402
from minitools.processors.full_text_translator import TranslationError  # noqa: E402
from minitools.utils.logger import attach_file_handler  # noqa: E402


class _FailingTranslator:
    async def translate(self, markdown: str) -> str:
        raise TranslationError("402 Payment Required", fatal=True)


class TestArxivStepTranslate:
    @pytest.mark.asyncio
    async def test_failure_does_not_write_translated_md(self, tmp_path, monkeypatch):
        """翻訳失敗時は translated.md を書かず failed を返す

        書いてしまうと次回以降「Translation already exists」でスキップされる。
        """
        monkeypatch.setattr(arxiv_translate, "OUTPUT_DIR", tmp_path)
        # logger は main() 内で初期化されるグローバルのため差し替える
        monkeypatch.setattr(
            arxiv_translate, "logger", logging.getLogger("test"), raising=False
        )
        url = "https://arxiv.org/abs/2401.12345"
        _, raw_path, translated_path, _ = arxiv_translate.resolve_paths(url)
        raw_path.write_text("# Title\n\nEnglish body.", encoding="utf-8")

        result = await arxiv_translate.step_translate(url, _FailingTranslator())

        assert result == "failed"
        assert not translated_path.exists()


class TestAttachFileHandler:
    @pytest.fixture
    def parent_logger(self):
        name = "test_attach_parent"
        logger = logging.getLogger(name)
        yield name
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)

    def test_child_warnings_written_to_file(self, tmp_path, monkeypatch, parent_logger):
        """子ロガーの WARNING 以上がファイルに書かれ、INFO は書かれない"""
        monkeypatch.chdir(tmp_path)
        attach_file_handler(parent_logger, "script.log")

        child = logging.getLogger(f"{parent_logger}.processors.translator")
        child.setLevel(logging.INFO)
        child.info("info message")
        child.error("Translation failed after 3 attempts")
        for handler in logging.getLogger(parent_logger).handlers:
            handler.flush()

        content = (tmp_path / "outputs/logs/script.log").read_text(encoding="utf-8")
        assert "Translation failed after 3 attempts" in content
        assert "info message" not in content

    def test_no_duplicate_handler(self, tmp_path, monkeypatch, parent_logger):
        """同じファイルに2回付けてもハンドラは1つ"""
        monkeypatch.chdir(tmp_path)
        attach_file_handler(parent_logger, "script.log")
        attach_file_handler(parent_logger, "script.log")

        handlers = [
            h
            for h in logging.getLogger(parent_logger).handlers
            if isinstance(h, logging.FileHandler)
        ]
        assert len(handlers) == 1
