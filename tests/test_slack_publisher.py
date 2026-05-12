"""Tests for SlackPublisher (focused on daily digest formatter)."""

from minitools.publishers.slack import SlackPublisher


def _sample_articles() -> list[dict]:
    return [
        {
            "title": f"記事 {i}",
            "summary": f"これは記事{i}の要約です。",
            "url": f"https://example.com/article{i}",
            "importance_score": 9.0 - i * 0.5,
        }
        for i in range(10)
    ]


def test_format_daily_digest_basic():
    """通常ケース: ヘッダ・「今日のまとめ」・スコア・要約・URL が含まれる"""
    slack = SlackPublisher()
    articles = _sample_articles()
    msg = slack.format_daily_digest(
        date="2026-05-09",
        articles=articles,
        daily_summary="本日は AI 業界で複数の発表があった。",
    )

    assert "*📰 Google Alerts Daily Digest (2026-05-09)*" in msg
    assert "*📝 今日のまとめ*" in msg
    assert "本日は AI 業界で複数の発表があった。" in msg
    assert "*🏆 今日の重要記事 Top 10*" in msg
    # スコアは小数1桁
    assert "[9.0]" in msg
    # 各記事タイトルが太字 (`*1. ...*` 形式)
    assert "*1. 記事 0*" in msg
    # 全記事の URL が含まれる
    for a in articles:
        assert a["url"] in msg
    # 番号付き
    assert "1. " in msg
    assert "10. " in msg


def test_format_daily_digest_without_summary():
    """daily_summary が空文字のときは「今日のまとめ」セクションを省略"""
    slack = SlackPublisher()
    msg = slack.format_daily_digest(
        date="2026-05-09",
        articles=_sample_articles(),
        daily_summary="",
    )
    assert "*📰 Google Alerts Daily Digest (2026-05-09)*" in msg
    assert "今日のまとめ" not in msg
    assert "*🏆 今日の重要記事 Top 10*" in msg


def test_format_daily_digest_empty_articles():
    """0件のときは「本日該当記事なし」を返し、まとめセクションを含めない"""
    slack = SlackPublisher()
    msg = slack.format_daily_digest(
        date="2026-05-09",
        articles=[],
        daily_summary="無視されるサマリ",
    )
    assert "*📰 Google Alerts Daily Digest (2026-05-09)*" in msg
    assert "本日該当記事なし" in msg
    assert "今日のまとめ" not in msg
    assert "無視されるサマリ" not in msg


def test_format_daily_digest_score_formatting():
    """スコアが小数1桁でフォーマットされる"""
    slack = SlackPublisher()
    msg = slack.format_daily_digest(
        date="2026-05-09",
        articles=[
            {
                "title": "T",
                "summary": "S",
                "url": "https://example.com/x",
                "importance_score": 7,
            }
        ],
    )
    assert "[7.0]" in msg
