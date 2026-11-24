"""
HuggingFace Daily Papers から注目論文を選ぶ純粋関数群。

arxiv コマンドは、キーワード検索ではなく HF Daily Papers の upvote で
保存する論文を選ぶ。ここでは API の生データを、既存の翻訳・Notion 保存の
流れにそのまま渡せる論文 dict に変換する。
"""

import re
from typing import Any, Iterable

DEFAULT_MIN_UPVOTES = 10
DEFAULT_MAX_PAPERS = 7
DEFAULT_FOCUS_KEYWORDS = [
    "LLM",
    "large language model",
    "language model",
    "RAG",
    "retrieval-augmented",
    "retrieval augmented",
    "agent",
    "agents",
    "agentic",
    "fine-tuning",
    "finetuning",
]

# Notion multi_select の制約（名前は100文字以内・カンマ不可）
MAX_TAGS = 5
MAX_TAG_LENGTH = 100


def _upvotes(item: dict[str, Any]) -> int:
    paper = item.get("paper") or {}
    value = paper.get("upvotes", 0)
    return value if isinstance(value, int) else 0


def _num_comments(item: dict[str, Any]) -> int:
    value = item.get("numComments", 0)
    return value if isinstance(value, int) else 0


def sanitize_tags(keywords: Iterable[Any], limit: int = MAX_TAGS) -> list[str]:
    """ai_keywords を Notion の multi_select に入れられる形へ整える"""
    tags: list[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        if not isinstance(keyword, str):
            continue
        tag = keyword.replace(",", " ").strip()
        tag = re.sub(r"\s+", " ", tag)[:MAX_TAG_LENGTH].strip()
        if not tag or tag.lower() in seen:
            continue
        seen.add(tag.lower())
        tags.append(tag)
        if len(tags) >= limit:
            break
    return tags


def is_focus_paper(item: dict[str, Any], focus_keywords: Iterable[str]) -> bool:
    """タイトル・要旨・ai_keywords に注目分野の語が含まれるか"""
    paper = item.get("paper") or {}
    keywords = paper.get("ai_keywords") or []
    text = " ".join(
        [
            str(paper.get("title") or ""),
            str(paper.get("summary") or ""),
            " ".join(k for k in keywords if isinstance(k, str)),
        ]
    )
    for word in focus_keywords:
        if not word:
            continue
        pattern = r"(?<![A-Za-z0-9])" + re.escape(word) + r"(?![A-Za-z0-9])"
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    return False


def select_top_papers(
    items: list[dict[str, Any]],
    min_upvotes: int = DEFAULT_MIN_UPVOTES,
    max_papers: int = DEFAULT_MAX_PAPERS,
) -> list[dict[str, Any]]:
    """upvote が下限以上のものを多い順に最大 max_papers 件選ぶ"""
    seen_ids: set[str] = set()
    candidates = []
    for item in items:
        paper = item.get("paper") or {}
        paper_id = paper.get("id")
        if not paper_id or paper_id in seen_ids:
            continue
        if _upvotes(item) < min_upvotes:
            continue
        seen_ids.add(paper_id)
        candidates.append(item)

    candidates.sort(key=lambda i: (_upvotes(i), _num_comments(i)), reverse=True)
    return candidates[:max_papers]


def to_paper_dict(
    item: dict[str, Any],
    hf_date: str,
    focus_keywords: Iterable[str] = DEFAULT_FOCUS_KEYWORDS,
) -> dict[str, Any]:
    """Daily Papers のアイテムを、翻訳・Notion 保存に渡す論文 dict にする"""
    paper = item.get("paper") or {}
    arxiv_id = paper["id"]
    authors = paper.get("authors") or []
    author_names = [
        a.get("name", "") for a in authors if isinstance(a, dict) and a.get("name")
    ]
    title = re.sub(r"\s+", " ", str(paper.get("title") or "")).strip()
    abstract = re.sub(r"\s+", " ", str(paper.get("summary") or "")).strip()
    published = str(paper.get("publishedAt") or hf_date)[:10]

    result: dict[str, Any] = {
        "title": title,
        "url": f"https://arxiv.org/abs/{arxiv_id}",
        "abstract": abstract,
        "authors": ", ".join(author_names),
        "published": published,
        "updated": published,
        "arxiv_id": arxiv_id,
        "hf_upvotes": _upvotes(item),
        "hf_url": f"https://huggingface.co/papers/{arxiv_id}",
        "hf_ai_summary": str(paper.get("ai_summary") or "").strip(),
        "hf_keywords": sanitize_tags(paper.get("ai_keywords") or []),
        "hf_focus": is_focus_paper(item, focus_keywords),
        "hf_date": hf_date,
    }
    github_url = paper.get("githubRepo")
    if isinstance(github_url, str) and github_url.startswith("http"):
        result["github_url"] = github_url
        stars = paper.get("githubStars")
        if isinstance(stars, int):
            result["github_stars"] = stars
    return result


def build_daily_selection(
    items: list[dict[str, Any]],
    hf_date: str,
    min_upvotes: int = DEFAULT_MIN_UPVOTES,
    max_papers: int = DEFAULT_MAX_PAPERS,
    focus_keywords: Iterable[str] = DEFAULT_FOCUS_KEYWORDS,
) -> list[dict[str, Any]]:
    """選定と変換をまとめて行う"""
    focus = list(focus_keywords)
    return [
        to_paper_dict(item, hf_date, focus)
        for item in select_top_papers(items, min_upvotes, max_papers)
    ]


def rank_weekly(papers: list[dict[str, Any]], top_n: int = 10) -> list[dict[str, Any]]:
    """週の論文を upvote の多い順に top_n 件"""
    return sorted(papers, key=lambda p: p.get("hf_upvotes") or 0, reverse=True)[:top_n]
