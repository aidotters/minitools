"""
「今週の注目論文」ページの組み立て。

その週に保存した HF 注目論文を upvote の多い順に並べ、Notion の子ページの
本文ブロックにする。ブロックの組み立ては純関数にしてテストしやすくしている。
"""

from datetime import date, timedelta
from typing import Any

from minitools.processors.hf_daily_selector import rank_weekly

WEEKLY_PAGE_TITLE = "今週の注目論文"
MAX_TEXT_LENGTH = 2000


def week_range(end: date, days: int = 7) -> tuple[str, str]:
    """end を含む直近 days 日の範囲（YYYY-MM-DD・両端含む）"""
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def weekly_title(start: str, end: str) -> str:
    return f"{WEEKLY_PAGE_TITLE}（{start}〜{end}）"


def _text(content: str, link: str | None = None) -> dict[str, Any]:
    text: dict[str, Any] = {"content": content[:MAX_TEXT_LENGTH]}
    if link:
        text["link"] = {"url": link}
    return {"type": "text", "text": text}


def _paragraph(parts: list[dict[str, Any]]) -> dict[str, Any]:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": parts}}


def build_weekly_blocks(
    papers: list[dict[str, Any]], start: str, end: str
) -> list[dict[str, Any]]:
    """ランキング済みの論文リストから本文ブロックを作る"""
    blocks: list[dict[str, Any]] = [
        _paragraph(
            [
                _text(
                    f"{start}〜{end} に保存した HF 注目論文を、"
                    "Hugging Face の upvote が多い順に並べています。"
                )
            ]
        )
    ]
    if not papers:
        blocks.append(_paragraph([_text("この週に保存した論文はありませんでした。")]))
        return blocks

    for i, paper in enumerate(papers, 1):
        mark = "【注目分野】" if paper.get("hf_focus") else ""
        title = paper.get("title") or "タイトルなし"
        blocks.append(
            {
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": [_text(f"{i}. {mark}{title}")]},
            }
        )
        blocks.append(
            _paragraph(
                [
                    _text(
                        f"upvote {paper.get('hf_upvotes') or 0}"
                        f"　HF掲載日 {paper.get('hf_date') or '-'}"
                    )
                ]
            )
        )
        summary = paper.get("japanese_summary") or ""
        if summary:
            blocks.append(_paragraph([_text(summary)]))

        links: list[dict[str, Any]] = []
        for label, url in (
            ("arXiv", paper.get("url")),
            ("Hugging Face", paper.get("hf_url")),
            ("GitHub", paper.get("github_url")),
            ("Notion", _notion_page_url(paper.get("page_id"))),
        ):
            if url:
                if links:
                    links.append(_text("　"))
                links.append(_text(label, url))
        if links:
            blocks.append(_paragraph(links))
    return blocks


def _notion_page_url(page_id: str | None) -> str | None:
    if not page_id:
        return None
    return f"https://www.notion.so/{page_id.replace('-', '')}"


async def create_weekly_page(
    publisher: Any,
    researcher: Any,
    database_id: str,
    end: date,
    top_n: int = 10,
) -> str | None:
    """
    週の論文を集め、upvote を取り直して子ページを作る

    Args:
        publisher: NotionPublisher
        researcher: 開いた状態の HFPapersResearcher（upvote の取り直し用）
        database_id: arXiv DB の ID
        end: 週の最終日（この日を含む7日間）
        top_n: 載せる件数

    Returns:
        作成したページ ID（作れなかったら None）
    """
    from minitools.utils.logger import get_logger

    logger = get_logger(__name__)
    start, end_str = week_range(end)
    papers = await publisher.query_arxiv_by_hf_date(database_id, start, end_str)
    logger.info(f"週次ランキング: {start}〜{end_str} の論文 {len(papers)} 件")

    # 掲載日以降も upvote は伸びるので、ランキング前に取り直す
    ids = [p["arxiv_id"] for p in papers if p.get("arxiv_id")]
    if ids:
        stats = await researcher.get_papers_stats(ids)
        for paper in papers:
            stat = stats.get(paper.get("arxiv_id"))
            if not stat or not stat.found_on_hf:
                continue
            if stat.upvotes != paper.get("hf_upvotes"):
                paper["hf_upvotes"] = stat.upvotes
                await publisher.update_page_properties(
                    paper["page_id"], {"HF Upvotes": {"number": stat.upvotes}}
                )

    ranked = rank_weekly(papers, top_n)
    parent_id = await publisher.get_database_parent_page_id(database_id)
    if not parent_id:
        logger.error("arXiv DB の親ページが見つからないため週次ページを作れません")
        return None
    page_id = await publisher.create_child_page(
        parent_id,
        weekly_title(start, end_str),
        build_weekly_blocks(ranked, start, end_str),
    )
    if page_id:
        logger.info(f"週次ページを作成しました: {page_id}")
    return page_id
