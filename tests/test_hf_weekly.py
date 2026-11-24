"""「今週の注目論文」ページのテスト"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from minitools.processors.hf_weekly import (
    build_weekly_blocks,
    create_weekly_page,
    week_range,
    weekly_title,
)
from minitools.researchers.hf_papers import HFPaperStats


def test_week_range_and_title():
    start, end = week_range(date(2026, 11, 20))
    assert (start, end) == ("2026-11-14", "2026-11-20")
    assert weekly_title(start, end) == "今週の注目論文（2026-11-14〜2026-11-20）"


def test_build_weekly_blocks_empty():
    blocks = build_weekly_blocks([], "2026-11-14", "2026-11-20")
    assert len(blocks) == 2
    text = blocks[1]["paragraph"]["rich_text"][0]["text"]["content"]
    assert "ありませんでした" in text


def test_build_weekly_blocks_paper():
    paper = {
        "title": "Paper",
        "hf_focus": True,
        "hf_upvotes": 120,
        "hf_date": "2026-11-18",
        "japanese_summary": "要約",
        "url": "https://arxiv.org/abs/1",
        "hf_url": "https://huggingface.co/papers/1",
        "page_id": "abcd-ef",
    }
    blocks = build_weekly_blocks([paper], "2026-11-14", "2026-11-20")
    heading = blocks[1]["heading_3"]["rich_text"][0]["text"]["content"]
    assert heading == "1. 【注目分野】Paper"
    assert "upvote 120" in blocks[2]["paragraph"]["rich_text"][0]["text"]["content"]
    assert blocks[3]["paragraph"]["rich_text"][0]["text"]["content"] == "要約"
    links = blocks[4]["paragraph"]["rich_text"]
    labels = [p["text"]["content"] for p in links if p["text"].get("link")]
    assert labels == ["arXiv", "Hugging Face", "Notion"]
    assert links[-1]["text"]["link"]["url"] == "https://www.notion.so/abcdef"


@pytest.mark.asyncio
async def test_create_weekly_page_refreshes_upvotes_and_ranks():
    publisher = MagicMock()
    publisher.query_arxiv_by_hf_date = AsyncMock(
        return_value=[
            {"page_id": "p1", "arxiv_id": "1", "title": "A", "hf_upvotes": 10},
            {"page_id": "p2", "arxiv_id": "2", "title": "B", "hf_upvotes": 20},
            {"page_id": "p3", "arxiv_id": "3", "title": "C", "hf_upvotes": 5},
        ]
    )
    publisher.update_page_properties = AsyncMock()
    publisher.get_database_parent_page_id = AsyncMock(return_value="parent")
    publisher.create_child_page = AsyncMock(return_value="new-page")
    researcher = MagicMock()
    researcher.get_papers_stats = AsyncMock(
        return_value={
            "1": HFPaperStats("1", upvotes=99, found_on_hf=True),
            "2": HFPaperStats("2", upvotes=20, found_on_hf=True),
            "3": HFPaperStats("3", upvotes=0, found_on_hf=False),
        }
    )

    page_id = await create_weekly_page(
        publisher, researcher, "db", date(2026, 11, 20), top_n=2
    )

    assert page_id == "new-page"
    publisher.query_arxiv_by_hf_date.assert_awaited_once_with(
        "db", "2026-11-14", "2026-11-20"
    )
    publisher.update_page_properties.assert_awaited_once_with(
        "p1", {"HF Upvotes": {"number": 99}}
    )
    parent, title, blocks = publisher.create_child_page.call_args.args
    assert parent == "parent"
    assert title == "今週の注目論文（2026-11-14〜2026-11-20）"
    headings = [
        b["heading_3"]["rich_text"][0]["text"]["content"]
        for b in blocks
        if b["type"] == "heading_3"
    ]
    assert headings == ["1. A", "2. B"]


@pytest.mark.asyncio
async def test_create_weekly_page_without_parent():
    publisher = MagicMock()
    publisher.query_arxiv_by_hf_date = AsyncMock(return_value=[])
    publisher.get_database_parent_page_id = AsyncMock(return_value=None)
    publisher.create_child_page = AsyncMock()
    researcher = MagicMock()
    researcher.get_papers_stats = AsyncMock()

    assert (
        await create_weekly_page(publisher, researcher, "db", date(2026, 11, 20))
        is None
    )
    researcher.get_papers_stats.assert_not_called()
    publisher.create_child_page.assert_not_called()
