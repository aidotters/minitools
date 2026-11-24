"""HF Daily Papers からの論文選定のテスト"""

from minitools.processors.hf_daily_selector import (
    build_daily_selection,
    is_focus_paper,
    rank_weekly,
    sanitize_tags,
    select_top_papers,
    to_paper_dict,
)


def _item(
    pid, upvotes, comments=0, title="A paper", summary="", keywords=None, **extra
):
    paper = {
        "id": pid,
        "title": title,
        "summary": summary,
        "upvotes": upvotes,
        "ai_keywords": keywords or [],
        "authors": [{"name": "Alice"}, {"name": "Bob"}],
        "publishedAt": "2026-11-19T12:00:00.000Z",
    }
    paper.update(extra)
    return {"paper": paper, "numComments": comments}


def test_select_top_papers_filters_sorts_and_limits():
    items = [
        _item("1", 5),
        _item("2", 30),
        _item("3", 12, comments=1),
        _item("4", 12, comments=5),
        _item("2", 30),  # 重複
        _item("5", 50),
    ]
    selected = select_top_papers(items, min_upvotes=10, max_papers=3)
    assert [i["paper"]["id"] for i in selected] == ["5", "2", "4"]


def test_select_top_papers_ignores_bad_items():
    items = [{"paper": {}}, {"foo": 1}, _item("1", "many"), _item("2", 10)]
    assert [i["paper"]["id"] for i in select_top_papers(items, 10, 7)] == ["2"]


def test_sanitize_tags():
    tags = sanitize_tags(
        ["LLM", "llm", "a, b", "  spaced   out  ", "", 3, "x" * 150, "f", "g"]
    )
    assert tags[0] == "LLM"
    assert "a  b".replace("  ", " ") in tags
    assert "spaced out" in tags
    assert len(tags) == 5
    assert all(len(t) <= 100 and "," not in t for t in tags)


def test_is_focus_paper_uses_word_boundaries():
    assert is_focus_paper(_item("1", 1, title="Agentic coding"), ["agentic"])
    assert is_focus_paper(_item("1", 1, keywords=["RAG"]), ["RAG"])
    assert not is_focus_paper(_item("1", 1, title="Fragile drag"), ["RAG"])
    assert not is_focus_paper(_item("1", 1, title="Vision"), [""])


def test_to_paper_dict_maps_fields():
    item = _item(
        "2611.00001",
        42,
        title="  Big\n Model ",
        summary="Line1\nLine2",
        keywords=["LLM", "reasoning"],
        ai_summary=" HF summary ",
        githubRepo="https://github.com/x/y",
        githubStars=7,
    )
    d = to_paper_dict(item, "2026-11-20", ["LLM"])
    assert d["title"] == "Big Model"
    assert d["abstract"] == "Line1 Line2"
    assert d["authors"] == "Alice, Bob"
    assert d["url"] == "https://arxiv.org/abs/2611.00001"
    assert d["hf_url"] == "https://huggingface.co/papers/2611.00001"
    assert d["published"] == "2026-11-19"
    assert d["hf_upvotes"] == 42
    assert d["hf_ai_summary"] == "HF summary"
    assert d["hf_keywords"] == ["LLM", "reasoning"]
    assert d["hf_focus"] is True
    assert d["hf_date"] == "2026-11-20"
    assert d["github_url"] == "https://github.com/x/y"
    assert d["github_stars"] == 7


def test_to_paper_dict_without_github():
    d = to_paper_dict(_item("1", 10, githubRepo=""), "2026-11-20", [])
    assert "github_url" not in d and "github_stars" not in d
    assert d["hf_focus"] is False


def test_build_daily_selection():
    items = [_item("1", 3), _item("2", 20), _item("3", 15)]
    papers = build_daily_selection(items, "2026-11-20", 10, 7, ["LLM"])
    assert [p["arxiv_id"] for p in papers] == ["2", "3"]


def test_rank_weekly():
    papers = [{"hf_upvotes": 5}, {"hf_upvotes": None}, {"hf_upvotes": 50}]
    ranked = rank_weekly(papers, top_n=2)
    assert [p["hf_upvotes"] for p in ranked] == [50, 5]
