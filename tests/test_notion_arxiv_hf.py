"""NotionPublisher の HF 項目まわりのテスト"""

from unittest.mock import MagicMock, patch

import pytest

from minitools.publishers.notion import (
    ARXIV_HF_PROPERTIES,
    NotionPublisher,
    _arxiv_page_summary,
)


@pytest.fixture
def publisher():
    with patch.dict("os.environ", {"NOTION_API_KEY": "test-key"}):
        pub = NotionPublisher(source_type="arxiv")
    pub.client = MagicMock()
    return pub


def test_build_arxiv_properties_hf_fields(publisher):
    props = publisher._build_arxiv_properties(
        {
            "title": "T",
            "url": "https://arxiv.org/abs/1",
            "hf_upvotes": 30,
            "hf_url": "https://huggingface.co/papers/1",
            "github_url": "https://github.com/x/y",
            "github_stars": 3,
            "hf_ai_summary": "sum",
            "hf_keywords": ["LLM", "agents"],
            "hf_focus": False,
            "hf_date": "2026-11-20",
        }
    )
    assert props["HF Upvotes"] == {"number": 30}
    assert props["HF URL"] == {"url": "https://huggingface.co/papers/1"}
    assert props["GitHub"] == {"url": "https://github.com/x/y"}
    assert props["GitHub Stars"] == {"number": 3}
    assert props["HF要約"]["rich_text"][0]["text"]["content"] == "sum"
    assert props["タグ"] == {"multi_select": [{"name": "LLM"}, {"name": "agents"}]}
    assert props["注目分野"] == {"checkbox": False}
    assert props["HF掲載日"] == {"date": {"start": "2026-11-20"}}


def test_build_arxiv_properties_without_hf(publisher):
    props = publisher._build_arxiv_properties({"title": "T"})
    assert not set(props) & set(ARXIV_HF_PROPERTIES)


@pytest.mark.asyncio
async def test_ensure_arxiv_properties_adds_missing(publisher):
    publisher.client.databases.retrieve.return_value = {
        "properties": {"タイトル": {}, "HF Upvotes": {}}
    }
    assert await publisher.ensure_arxiv_properties("db") is True
    added = publisher.client.databases.update.call_args.kwargs["properties"]
    assert "HF Upvotes" not in added
    assert set(added) == set(ARXIV_HF_PROPERTIES) - {"HF Upvotes"}


@pytest.mark.asyncio
async def test_ensure_arxiv_properties_noop_and_failure(publisher):
    publisher.client.databases.retrieve.return_value = {
        "properties": dict.fromkeys(ARXIV_HF_PROPERTIES, {})
    }
    assert await publisher.ensure_arxiv_properties("db") is True
    publisher.client.databases.update.assert_not_called()

    publisher.client.databases.retrieve.side_effect = ValueError("boom")
    assert await publisher.ensure_arxiv_properties("db") is False


@pytest.mark.asyncio
async def test_get_database_parent_page_id(publisher):
    publisher.client.databases.retrieve.return_value = {
        "parent": {"type": "page_id", "page_id": "parent-1"}
    }
    assert await publisher.get_database_parent_page_id("db") == "parent-1"
    publisher.client.databases.retrieve.return_value = {
        "parent": {"type": "workspace", "workspace": True}
    }
    assert await publisher.get_database_parent_page_id("db") is None


def _page(pid, upvotes):
    return {
        "id": pid,
        "properties": {
            "タイトル": {"type": "title", "title": [{"plain_text": f"Paper {pid}"}]},
            "日本語訳": {"type": "rich_text", "rich_text": [{"plain_text": "要約"}]},
            "URL": {"type": "url", "url": f"https://arxiv.org/abs/2611.0000{pid}"},
            "HF URL": {"type": "url", "url": None},
            "HF Upvotes": {"type": "number", "number": upvotes},
            "HF掲載日": {"type": "date", "date": {"start": "2026-11-18"}},
            "注目分野": {"type": "checkbox", "checkbox": True},
        },
    }


def test_arxiv_page_summary():
    s = _arxiv_page_summary(_page("1", 12))
    assert s["page_id"] == "1"
    assert s["title"] == "Paper 1"
    assert s["japanese_summary"] == "要約"
    assert s["arxiv_id"] == "2611.00001"
    assert s["hf_upvotes"] == 12
    assert s["hf_date"] == "2026-11-18"
    assert s["hf_focus"] is True


@pytest.mark.asyncio
async def test_query_arxiv_by_hf_date_paginates(publisher):
    publisher.client.databases.query.side_effect = [
        {"results": [_page("1", 5)], "has_more": True, "next_cursor": "c1"},
        {"results": [_page("2", 9)], "has_more": False, "next_cursor": None},
    ]
    pages = await publisher.query_arxiv_by_hf_date("db", "2026-11-14", "2026-11-20")
    assert [p["page_id"] for p in pages] == ["1", "2"]
    calls = publisher.client.databases.query.call_args_list
    assert "start_cursor" not in calls[0].kwargs
    assert calls[1].kwargs["start_cursor"] == "c1"
    flt = calls[0].kwargs["filter"]["and"]
    assert flt[0]["date"] == {"on_or_after": "2026-11-14"}
    assert flt[1]["date"] == {"on_or_before": "2026-11-20"}
