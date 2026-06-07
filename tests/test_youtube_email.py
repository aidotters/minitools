"""Tests for youtube-mail-digest: URL抽出/正規化/dedup, ProcessedStore,
字幕フォールバック, 要約パース, 出力トグル解決, オーケストレーション。"""

import sys

import pytest

import scripts.youtube_mail_digest as ymd
from minitools.collectors.youtube import YouTubeCollector, parse_subtitle_to_text
from minitools.collectors.youtube_email import (
    VideoRef,
    extract_video_id,
    extract_youtube_urls,
    normalize_youtube_url,
)
from minitools.processors.youtube_summary import (
    Summary,
    YouTubeSummarizer,
    _parse_summary_response,
)
from minitools.publishers.slack import SlackPublisher
from minitools.utils.processed_store import ProcessedStore
from scripts.youtube_mail_digest import resolve_outputs
from tests.conftest import MockLLMClient


class TestExtractVideoId:
    """動画 ID 抽出ロジック"""

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtube.com/watch?v=dQw4w9WgXcQ&t=10s", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ?si=abcdef", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/live/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ],
    )
    def test_valid_urls(self, url, expected):
        """各種 YouTube URL から動画 ID を抽出"""
        assert extract_video_id(url) == expected

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/watch?v=dQw4w9WgXcQ",  # 別ドメイン
            "https://www.youtube.com/feed/subscriptions",  # 動画でない
            "https://www.google.com/url?q=foo",
            "not a url",
            "",
        ],
    )
    def test_invalid_urls(self, url):
        """YouTube 動画 URL でないものは None"""
        assert extract_video_id(url) is None


class TestNormalizeYoutubeUrl:
    """URL 正規化ロジック"""

    def test_tracking_params_removed(self):
        """トラッキングパラメータを除去し watch 形式へ統一"""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=xyz&feature=share"
        assert (
            normalize_youtube_url(url) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )

    def test_youtu_be_converted_to_watch(self):
        """youtu.be 短縮 URL を watch 形式へ変換"""
        assert (
            normalize_youtube_url("https://youtu.be/dQw4w9WgXcQ")
            == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )

    def test_non_youtube_returns_none(self):
        assert normalize_youtube_url("https://example.com/foo") is None


class TestExtractYoutubeUrls:
    """HTML 本文からの URL 抽出・重複除去"""

    def test_extract_mixed_links(self):
        """watch / youtu.be / shorts が混在する HTML から全抽出"""
        html = """
        <html><body>
          <a href="https://www.youtube.com/watch?v=aaaaaaaaaaa">video A</a>
          <a href="https://youtu.be/bbbbbbbbbbb?si=zzz">video B</a>
          <a href="https://www.youtube.com/shorts/ccccccccccc">short C</a>
          <a href="https://example.com/other">other</a>
        </body></html>
        """
        urls = extract_youtube_urls(html)
        assert urls == [
            "https://www.youtube.com/watch?v=aaaaaaaaaaa",
            "https://www.youtube.com/watch?v=bbbbbbbbbbb",
            "https://www.youtube.com/watch?v=ccccccccccc",
        ]

    def test_dedup_same_video_multiple_representations(self):
        """同一動画の複数表記は1件に集約される"""
        html = """
        <a href="https://www.youtube.com/watch?v=aaaaaaaaaaa&t=1">A1</a>
        <a href="https://youtu.be/aaaaaaaaaaa">A2</a>
        <a href="https://www.youtube.com/embed/aaaaaaaaaaa">A3</a>
        """
        urls = extract_youtube_urls(html)
        assert urls == ["https://www.youtube.com/watch?v=aaaaaaaaaaa"]

    def test_empty_html(self):
        assert extract_youtube_urls("") == []


class TestProcessedStore:
    """processed.json による per-profile 重複管理"""

    def test_filter_new_excludes_processed(self, tmp_path):
        """処理済み動画が filter_new で除外される"""
        store = ProcessedStore(path=str(tmp_path / "processed.json"))
        refs = [
            VideoRef(url="u1", video_id="aaaaaaaaaaa"),
            VideoRef(url="u2", video_id="bbbbbbbbbbb"),
        ]
        store.mark("profileX", "aaaaaaaaaaa")
        new = store.filter_new("profileX", refs)
        assert [r.video_id for r in new] == ["bbbbbbbbbbb"]

    def test_per_profile_isolation(self, tmp_path):
        """別プロファイルでは独立して未処理扱いになる"""
        store = ProcessedStore(path=str(tmp_path / "processed.json"))
        store.mark("A", "aaaaaaaaaaa")
        refs = [VideoRef(url="u1", video_id="aaaaaaaaaaa")]
        # A では処理済み、B では未処理
        assert store.filter_new("A", refs) == []
        assert [r.video_id for r in store.filter_new("B", refs)] == ["aaaaaaaaaaa"]

    def test_save_and_reload_roundtrip(self, tmp_path):
        """save 後に再読み込みしても記録が保持される"""
        path = str(tmp_path / "processed.json")
        store = ProcessedStore(path=path)
        store.mark_many("A", ["aaaaaaaaaaa", "bbbbbbbbbbb"])
        store.save()

        reloaded = ProcessedStore(path=path)
        assert reloaded.is_processed("A", "aaaaaaaaaaa")
        assert reloaded.is_processed("A", "bbbbbbbbbbb")
        assert not reloaded.is_processed("A", "ccccccccccc")


class TestParseSubtitleToText:
    """VTT/SRT 字幕のテキスト化"""

    def test_vtt_parsing(self):
        """VTT からタイムスタンプ・タグ・ヘッダーを除去"""
        vtt = (
            "WEBVTT\n"
            "Kind: captions\n"
            "Language: en\n\n"
            "00:00:00.000 --> 00:00:02.000\n"
            "Hello <c>world</c>\n\n"
            "00:00:02.000 --> 00:00:04.000\n"
            "This is a test\n"
        )
        assert parse_subtitle_to_text(vtt) == "Hello world This is a test"

    def test_dedup_consecutive_lines(self):
        """自動字幕で重複する連続行を畳む"""
        vtt = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:02.000\n"
            "same line\n\n"
            "00:00:02.000 --> 00:00:04.000\n"
            "same line\n"
        )
        assert parse_subtitle_to_text(vtt) == "same line"

    def test_empty(self):
        assert parse_subtitle_to_text("") == ""


class TestParseSummaryResponse:
    """要約応答のパース"""

    def test_well_formed(self):
        """整形された応答から要約文とポイントを抽出"""
        resp = (
            "【要約】\n"
            "これはテスト動画の要約です。重要な話題を扱っています。\n\n"
            "【ポイント】\n"
            "- ポイントA\n"
            "- ポイントB\n"
            "・ポイントC\n"
            "1. ポイントD\n"
        )
        summary = _parse_summary_response(resp)
        assert "テスト動画の要約" in summary.text
        assert summary.points == ["ポイントA", "ポイントB", "ポイントC", "ポイントD"]

    def test_no_points_header(self):
        """ポイント見出しがなくても全体を要約として扱う"""
        summary = _parse_summary_response("ただの要約文です。")
        assert summary.text == "ただの要約文です。"
        assert summary.points == []

    def test_empty(self):
        summary = _parse_summary_response("")
        assert summary.text == ""
        assert summary.points == []


class TestTranscriptFallback:
    """get_transcript の字幕優先 / Whisper フォールバック分岐（AC-9/AC-10）"""

    def test_subtitle_path_skips_whisper(self, tmp_path, monkeypatch):
        """字幕がある場合は Whisper を起動せず source=subtitle"""
        collector = YouTubeCollector(output_dir=str(tmp_path))

        monkeypatch.setattr(collector, "fetch_subtitles", lambda url: "字幕テキスト")
        monkeypatch.setattr(
            collector,
            "get_video_info",
            lambda url: {"title": "T", "uploader": "U", "duration": 10},
        )

        called = {"process_video": False}

        def _fail_process(url):
            called["process_video"] = True
            return {"transcript": "whisper text"}

        monkeypatch.setattr(collector, "process_video", _fail_process)

        result = collector.get_transcript("https://youtu.be/aaaaaaaaaaa")
        assert result is not None
        assert result["source"] == "subtitle"
        assert result["transcript"] == "字幕テキスト"
        assert called["process_video"] is False  # Whisper 非起動

    def test_fallback_to_whisper_when_no_subtitle(self, tmp_path, monkeypatch):
        """字幕がない場合は Whisper にフォールバックし source=whisper"""
        collector = YouTubeCollector(output_dir=str(tmp_path))

        monkeypatch.setattr(collector, "fetch_subtitles", lambda url: None)
        monkeypatch.setattr(
            collector,
            "process_video",
            lambda url: {
                "url": url,
                "title": "T",
                "author": "U",
                "duration": 10,
                "transcript": "whisper text",
            },
        )

        result = collector.get_transcript("https://youtu.be/bbbbbbbbbbb")
        assert result is not None
        assert result["source"] == "whisper"
        assert result["transcript"] == "whisper text"


class TestYouTubeSummarizer:
    """要約生成（MockLLMClient）"""

    @pytest.mark.asyncio
    async def test_summarize_with_mock(self):
        """LLM 応答から Summary を生成"""
        mock = MockLLMClient(
            chat_response=("【要約】\nこれは要約です。\n\n【ポイント】\n- A\n- B\n")
        )
        summarizer = YouTubeSummarizer(llm_client=mock)
        summary = await summarizer.summarize("文字起こし本文", title="タイトル")
        assert isinstance(summary, Summary)
        assert "要約です" in summary.text
        assert summary.points == ["A", "B"]
        # generate が呼ばれている
        assert len(mock.generate_calls) == 1

    @pytest.mark.asyncio
    async def test_empty_transcript(self):
        """空の文字起こしは空 Summary（LLM 非呼び出し）"""
        mock = MockLLMClient()
        summarizer = YouTubeSummarizer(llm_client=mock)
        summary = await summarizer.summarize("")
        assert summary.text == ""
        assert summary.points == []
        assert len(mock.generate_calls) == 0


class TestFormatYoutubeDigest:
    """Slack ダイジェスト整形"""

    def test_empty_videos(self):
        """動画ゼロ件は1メッセージで「なし」を返す"""
        pub = SlackPublisher()
        messages = pub.format_youtube_digest([])
        assert len(messages) == 1
        assert "ありませんでした" in messages[0]

    def test_contains_title_url_points(self):
        """タイトル・URL・ポイントがメッセージに含まれる"""
        pub = SlackPublisher()
        videos = [
            {
                "title": "動画タイトル",
                "author": "チャンネル名",
                "url": "https://www.youtube.com/watch?v=aaaaaaaaaaa",
                "summary": "これは要約です。",
                "points": ["ポイント1", "ポイント2"],
            }
        ]
        messages = pub.format_youtube_digest(videos)
        joined = "\n".join(messages)
        assert "動画タイトル" in joined
        assert "https://www.youtube.com/watch?v=aaaaaaaaaaa" in joined
        assert "ポイント1" in joined
        assert "これは要約です" in joined

    def test_splits_long_list(self):
        """長い動画リストは複数メッセージに分割される"""
        pub = SlackPublisher()
        videos = [
            {
                "title": f"動画{i}",
                "author": "ch",
                "url": f"https://www.youtube.com/watch?v={'x' * 11}",
                "summary": "要" * 500,
                "points": ["ポイント"] * 5,
            }
            for i in range(10)
        ]
        messages = pub.format_youtube_digest(videos, max_message_length=1000)
        assert len(messages) > 1


class TestResolveOutputs:
    """出力先トグルの解決（AC-6/7/8）"""

    def test_both_enabled(self):
        """両方有効"""
        assert resolve_outputs(True, True, False, False) == (True, True)

    def test_slack_only_via_profile(self):
        """プロファイルで notion=False → Slackのみ（AC-6）"""
        assert resolve_outputs(True, False, False, False) == (True, False)

    def test_notion_only_via_profile(self):
        """プロファイルで slack=False → Notionのみ（AC-7）"""
        assert resolve_outputs(False, True, False, False) == (False, True)

    def test_no_notion_override(self):
        """--no-notion で Notion を上書き無効化（AC-6）"""
        assert resolve_outputs(True, True, False, True) == (True, False)

    def test_no_slack_override(self):
        """--no-slack で Slack を上書き無効化（AC-7）"""
        assert resolve_outputs(True, True, True, False) == (False, True)

    def test_both_disabled(self):
        """両方無効"""
        assert resolve_outputs(True, True, True, True) == (False, False)


# --- オーケストレーション統合テスト用の Fake/Recorder ---


class _FakeConfig:
    def __init__(self, profiles):
        self._profiles = profiles

    def get(self, key, default=None):
        if key == "youtube_mail_digest.profiles":
            return self._profiles
        return default


class _FakeEmailCollector:
    def __init__(self, sender):
        self.sender = sender

    def collect(self, hours_back=24, date=None):
        return [
            VideoRef(
                url="https://www.youtube.com/watch?v=aaaaaaaaaaa",
                video_id="aaaaaaaaaaa",
                email_date="2026-06-07",
                source_subject="S",
            ),
            VideoRef(
                url="https://www.youtube.com/watch?v=bbbbbbbbbbb",
                video_id="bbbbbbbbbbb",
                email_date="2026-06-07",
                source_subject="S",
            ),
        ]


class _FakeYTCollector:
    def __init__(self, output_dir=None, whisper_model=None):
        pass

    def get_transcript(self, url):
        # 1本目は字幕、2本目は Whisper を模す
        if "aaaaaaaaaaa" in url:
            return {
                "url": url,
                "title": "A",
                "author": "chA",
                "duration": 1,
                "transcript": "text A",
                "source": "subtitle",
            }
        return {
            "url": url,
            "title": "B",
            "author": "chB",
            "duration": 1,
            "transcript": "text B",
            "source": "whisper",
        }


class _FakeSummarizer:
    def __init__(self, provider=None):
        pass

    async def summarize(self, transcript, title=""):
        return Summary(text=f"要約:{title}", points=["p1", "p2"])


class _FakeStore:
    def __init__(self, path=None):
        self.marked = []
        self.save_count = 0

    def filter_new(self, profile, refs):
        return list(refs)

    def mark_many(self, profile, ids):
        self.marked.append((profile, list(ids)))

    def save(self):
        self.save_count += 1


def _setup_orchestrator(monkeypatch, profiles, argv):
    """main_async の依存を Fake/Recorder に差し替え、記録用オブジェクトを返す"""
    notion_created = []
    slack_created = []

    class _RecNotion:
        def __init__(self, source_type=None):
            self.calls = []
            notion_created.append(self)

        async def create_child_page(self, parent_page_id, title, blocks):
            self.calls.append((parent_page_id, title))
            return "pageid"

    class _RecSlack:
        def __init__(self, webhook_url=None):
            self.entered = False
            self.sent = []
            slack_created.append(self)

        async def __aenter__(self):
            self.entered = True
            return self

        async def __aexit__(self, *args):
            return False

        def format_youtube_digest(self, videos, date=None):
            return [f"msg:{len(videos)}"]

        async def send_messages(self, messages, webhook_url=None):
            self.sent.append(messages)
            return True

    store = _FakeStore()

    monkeypatch.setattr(ymd, "get_config", lambda: _FakeConfig(profiles))
    monkeypatch.setattr(ymd, "YouTubeEmailCollector", _FakeEmailCollector)
    monkeypatch.setattr(ymd, "YouTubeCollector", _FakeYTCollector)
    monkeypatch.setattr(ymd, "YouTubeSummarizer", _FakeSummarizer)
    monkeypatch.setattr(ymd, "NotionPublisher", _RecNotion)
    monkeypatch.setattr(ymd, "SlackPublisher", _RecSlack)
    monkeypatch.setattr(ymd, "ProcessedStore", lambda *a, **k: store)
    monkeypatch.setattr(sys, "argv", argv)

    return {
        "store": store,
        "notion_created": notion_created,
        "slack_created": slack_created,
    }


class TestOrchestrator:
    """プロファイルループ・出力ルーティング・mark タイミング（AC-6/7/8/13/14）"""

    @pytest.mark.asyncio
    async def test_both_outputs(self, monkeypatch):
        """両出力有効: Notion 2件・Slack 1送信・mark は gather 後に1回"""
        monkeypatch.setenv("WH", "http://hook")
        profiles = [
            {
                "name": "P",
                "from": "x@y",
                "notion_parent_page_id": "PID",
                "slack_webhook_env": "WH",
                "slack": True,
                "notion": True,
            }
        ]
        rec = _setup_orchestrator(monkeypatch, profiles, ["youtube-mail-digest"])
        await ymd.main_async()

        assert len(rec["notion_created"]) == 1
        assert len(rec["notion_created"][0].calls) == 2  # 2動画分の子ページ
        assert len(rec["slack_created"]) == 1
        assert rec["slack_created"][0].sent == [["msg:2"]]  # 1回の送信
        # mark は gather 後に1回（per-video ではない）
        assert rec["store"].marked == [("P", ["aaaaaaaaaaa", "bbbbbbbbbbb"])]
        assert rec["store"].save_count == 1

    @pytest.mark.asyncio
    async def test_slack_only_skips_notion(self, monkeypatch):
        """Slackのみ: NotionPublisher が構築されない（AC-6）"""
        monkeypatch.setenv("WH", "http://hook")
        profiles = [
            {
                "name": "P",
                "from": "x@y",
                "notion_parent_page_id": "PID",
                "slack_webhook_env": "WH",
                "slack": True,
                "notion": False,
            }
        ]
        rec = _setup_orchestrator(monkeypatch, profiles, ["youtube-mail-digest"])
        await ymd.main_async()

        assert rec["notion_created"] == []  # Notion クライアント未構築
        assert len(rec["slack_created"]) == 1
        assert rec["slack_created"][0].sent == [["msg:2"]]

    @pytest.mark.asyncio
    async def test_notion_only_skips_slack(self, monkeypatch):
        """Notionのみ: Slack コンテキストに入らない（AC-7）"""
        profiles = [
            {
                "name": "P",
                "from": "x@y",
                "notion_parent_page_id": "PID",
                "slack_webhook_env": "WH",
                "slack": False,
                "notion": True,
            }
        ]
        rec = _setup_orchestrator(monkeypatch, profiles, ["youtube-mail-digest"])
        await ymd.main_async()

        assert len(rec["notion_created"]) == 1
        assert len(rec["notion_created"][0].calls) == 2
        assert rec["slack_created"] == []  # Slack 未構築

    @pytest.mark.asyncio
    async def test_dry_run_no_outputs_no_mark(self, monkeypatch):
        """dry-run: Notion/Slack 送信なし・mark なし（AC-15）"""
        profiles = [
            {
                "name": "P",
                "from": "x@y",
                "notion_parent_page_id": "PID",
                "slack_webhook_env": "WH",
                "slack": True,
                "notion": True,
            }
        ]
        rec = _setup_orchestrator(
            monkeypatch, profiles, ["youtube-mail-digest", "--dry-run"]
        )
        await ymd.main_async()

        assert rec["notion_created"] == []  # 保存しない
        # Slack はプレビュー整形のため context に入るが send はしない
        for s in rec["slack_created"]:
            assert s.sent == []
        assert rec["store"].marked == []  # mark しない
        assert rec["store"].save_count == 0
