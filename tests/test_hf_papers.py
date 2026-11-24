"""Tests for HFPapersResearcher."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from minitools.researchers.hf_papers import HFPaperStats, HFPapersResearcher


class TestHFPaperStats:
    """HFPaperStats dataclass のテスト"""

    def test_default_values(self):
        """デフォルト値の確認"""
        stats = HFPaperStats(arxiv_id="2601.00001")
        assert stats.arxiv_id == "2601.00001"
        assert stats.upvotes == 0
        assert stats.num_comments == 0
        assert stats.found_on_hf is False

    def test_with_values(self):
        """値指定時の確認"""
        stats = HFPaperStats(
            arxiv_id="2601.00001",
            upvotes=42,
            num_comments=5,
            found_on_hf=True,
        )
        assert stats.upvotes == 42
        assert stats.num_comments == 5
        assert stats.found_on_hf is True


class TestHFPapersResearcher:
    """HFPapersResearcherのテスト"""

    @pytest.mark.asyncio
    async def test_get_paper_stats_success(self):
        """正常レスポンスでupvote数を取得"""
        researcher = HFPapersResearcher()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"upvotes": 42, "numComments": 5})
        mock_response.raise_for_status = MagicMock()

        mock_session = AsyncMock()
        mock_session.get = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_response), __aexit__=AsyncMock()
            )
        )
        researcher.session = mock_session

        stats = await researcher.get_paper_stats("2601.00001")

        assert stats.arxiv_id == "2601.00001"
        assert stats.upvotes == 42
        assert stats.num_comments == 5
        assert stats.found_on_hf is True

    @pytest.mark.asyncio
    async def test_get_paper_stats_404(self):
        """404レスポンスではupvotes=0, found_on_hf=False"""
        researcher = HFPapersResearcher()
        mock_response = AsyncMock()
        mock_response.status = 404

        mock_session = AsyncMock()
        mock_session.get = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_response), __aexit__=AsyncMock()
            )
        )
        researcher.session = mock_session

        stats = await researcher.get_paper_stats("9999.99999")

        assert stats.upvotes == 0
        assert stats.num_comments == 0
        assert stats.found_on_hf is False

    @pytest.mark.asyncio
    async def test_get_paper_stats_server_error_retries(self):
        """5xxエラー時にリトライしてデフォルト値を返す"""
        researcher = HFPapersResearcher()

        mock_response = AsyncMock()
        mock_response.status = 500

        mock_session = AsyncMock()
        mock_session.get = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_response), __aexit__=AsyncMock()
            )
        )
        researcher.session = mock_session

        with patch(
            "minitools.researchers.hf_papers.asyncio.sleep", new_callable=AsyncMock
        ):
            stats = await researcher.get_paper_stats("2601.00001")

        assert stats.upvotes == 0
        assert stats.found_on_hf is False

    @pytest.mark.asyncio
    async def test_get_paper_stats_no_session(self):
        """セッション未初期化時にRuntimeError"""
        researcher = HFPapersResearcher()
        with pytest.raises(RuntimeError, match="Session not initialized"):
            await researcher.get_paper_stats("2601.00001")

    @pytest.mark.asyncio
    async def test_get_papers_stats_multiple(self):
        """複数論文の一括取得"""
        researcher = HFPapersResearcher()

        async def mock_get_paper_stats(arxiv_id: str) -> HFPaperStats:
            if arxiv_id == "2601.00001":
                return HFPaperStats(arxiv_id=arxiv_id, upvotes=42, found_on_hf=True)
            return HFPaperStats(arxiv_id=arxiv_id)

        researcher.get_paper_stats = mock_get_paper_stats  # type: ignore[assignment]
        researcher.session = AsyncMock()  # session check bypass

        result = await researcher.get_papers_stats(["2601.00001", "2601.00002"])

        assert len(result) == 2
        assert result["2601.00001"].upvotes == 42
        assert result["2601.00002"].upvotes == 0

    @pytest.mark.asyncio
    async def test_get_papers_stats_empty(self):
        """空リストで空辞書を返す"""
        researcher = HFPapersResearcher()
        result = await researcher.get_papers_stats([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """async context managerが正しく動作"""
        async with HFPapersResearcher() as researcher:
            assert researcher.session is not None
        # __aexit__ 後はセッションがcloseされている


def _session_returning(*responses):
    session = AsyncMock()
    session.get = MagicMock(
        side_effect=[
            AsyncMock(__aenter__=AsyncMock(return_value=r), __aexit__=AsyncMock())
            for r in responses
        ]
    )
    return session


def _response(status, payload=None):
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=payload)
    resp.raise_for_status = MagicMock()
    return resp


class TestGetDailyPapers:
    @pytest.mark.asyncio
    async def test_success(self):
        researcher = HFPapersResearcher()
        researcher.session = _session_returning(
            _response(200, [{"paper": {"id": "1"}}])
        )
        items = await researcher.get_daily_papers("2026-11-20")
        assert items == [{"paper": {"id": "1"}}]
        params = researcher.session.get.call_args.kwargs["params"]
        assert params["date"] == "2026-11-20"

    @pytest.mark.asyncio
    async def test_retry_then_success(self):
        researcher = HFPapersResearcher()
        researcher.session = _session_returning(
            _response(429), _response(200, [{"paper": {"id": "2"}}])
        )
        with patch(
            "minitools.researchers.hf_papers.asyncio.sleep", new_callable=AsyncMock
        ):
            items = await researcher.get_daily_papers("2026-11-20")
        assert items == [{"paper": {"id": "2"}}]

    @pytest.mark.asyncio
    async def test_non_list_and_errors_return_empty(self):
        researcher = HFPapersResearcher()
        researcher.session = _session_returning(_response(200, {"error": "x"}))
        assert await researcher.get_daily_papers("2026-11-20") == []

        researcher.session = _session_returning(
            _response(500), _response(500), _response(500)
        )
        with patch(
            "minitools.researchers.hf_papers.asyncio.sleep", new_callable=AsyncMock
        ):
            assert await researcher.get_daily_papers("2026-11-20") == []

    @pytest.mark.asyncio
    async def test_no_session(self):
        with pytest.raises(RuntimeError):
            await HFPapersResearcher().get_daily_papers("2026-11-20")
