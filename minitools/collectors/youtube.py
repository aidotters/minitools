"""
YouTube video collector and transcriber module.
"""

import os
import re
import glob
from pathlib import Path
from typing import Optional, Dict, Any, List

import yt_dlp

try:
    import mlx_whisper

    MLX_WHISPER_AVAILABLE = True
except ImportError:
    MLX_WHISPER_AVAILABLE = False

from minitools.utils.logger import get_logger

logger = get_logger(__name__)

# 字幕言語の優先順（日本語 → 英語）
SUBTITLE_LANG_PRIORITY = ["ja", "ja-JP", "en", "en-US", "en-GB"]


def parse_subtitle_to_text(content: str) -> str:
    """
    VTT / SRT 字幕テキストからプレーンテキストを抽出する。

    タイムスタンプ行・連番・WEBVTT ヘッダー・インラインタグ（<...>）を除去し、
    連続する重複行を畳んで連結する。

    Args:
        content: 字幕ファイルの中身（VTT または SRT）

    Returns:
        本文テキスト（空白区切り）
    """
    if not content:
        return ""

    lines: List[str] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.upper().startswith("WEBVTT"):
            continue
        if line.startswith(("NOTE", "STYLE", "Kind:", "Language:")):
            continue
        # SRT の連番行
        if line.isdigit():
            continue
        # タイムスタンプ行（00:00:00.000 --> 00:00:02.000）
        if "-->" in line:
            continue
        # インラインタグ・話者タグを除去
        line = re.sub(r"<[^>]+>", "", line)
        line = line.strip()
        if not line:
            continue
        # 直前と同一の行（自動字幕でよく重複する）はスキップ
        if lines and lines[-1] == line:
            continue
        lines.append(line)

    return " ".join(lines).strip()


class YouTubeCollector:
    """YouTube動画を収集して文字起こしするクラス"""

    def __init__(
        self,
        output_dir: str = "outputs/temp",
        whisper_model: str = "mlx-community/whisper-base",
    ):
        """
        Args:
            output_dir: 一時ファイルの出力ディレクトリ
            whisper_model: 使用するWhisperモデル
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.whisper_model = whisper_model

        if not MLX_WHISPER_AVAILABLE:
            logger.warning(
                "mlx_whisper is not installed. YouTube transcription will not be available."
            )
            logger.warning("To enable it, run: uv sync --extra whisper")

        # yt-dlpの設定
        self.ydl_opts = {
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "outtmpl": str(self.output_dir / "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
        }

        # FFmpegのパスを設定（Homebrewでインストールした場合）
        ffmpeg_path = "/opt/homebrew/bin/ffmpeg"
        if os.path.exists(ffmpeg_path):
            self.ydl_opts["ffmpeg_location"] = ffmpeg_path

    def download_audio(self, url: str) -> Optional[str]:
        """
        YouTubeから音声をダウンロード

        Args:
            url: YouTube動画のURL

        Returns:
            ダウンロードしたファイルのパス
        """
        with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
            try:
                logger.info(f"Downloading audio from {url}...")
                info = ydl.extract_info(url, download=True)
                video_id = info["id"]
                audio_file = self.output_dir / f"{video_id}.mp3"

                if audio_file.exists():
                    logger.info(f"Downloaded audio to {audio_file}")
                    return str(audio_file)
                else:
                    logger.error(f"Audio file not found: {audio_file}")
                    return None

            except Exception as e:
                logger.error(f"Error downloading audio from {url}: {e}")
                return None

    def transcribe_audio(self, audio_file: str) -> Optional[Dict[str, Any]]:
        """
        音声ファイルを文字起こし

        Args:
            audio_file: 音声ファイルのパス

        Returns:
            文字起こし結果（textキーを含む辞書）
        """
        if not MLX_WHISPER_AVAILABLE:
            logger.error("mlx_whisper is not installed. Cannot transcribe audio.")
            logger.error("To enable transcription, run: uv sync --extra whisper")
            return None

        try:
            logger.info(f"Transcribing audio from {audio_file}...")
            result = mlx_whisper.transcribe(
                audio_file, path_or_hf_repo=self.whisper_model
            )

            if result and "text" in result:
                logger.info(
                    f"Transcription completed: {len(result['text'])} characters"
                )
                return result
            else:
                logger.error("Transcription returned no text")
                return None

        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            return None

    def process_video(self, url: str) -> Optional[Dict[str, str]]:
        """
        YouTube動画をダウンロードして文字起こし

        Args:
            url: YouTube動画のURL

        Returns:
            動画情報と文字起こしテキストを含む辞書
        """
        # 動画情報を取得
        video_info = self.get_video_info(url)
        if not video_info:
            return None

        # 音声をダウンロード
        audio_file = self.download_audio(url)
        if not audio_file:
            return None

        # 文字起こし
        transcription = self.transcribe_audio(audio_file)
        if not transcription:
            return None

        # 結果をまとめる
        result = {
            "url": url,
            "title": video_info.get("title", "Unknown"),
            "author": video_info.get("uploader", "Unknown"),
            "duration": video_info.get("duration", 0),
            "transcript": transcription.get("text", ""),
            "audio_file": audio_file,
        }

        # 一時ファイルを削除（オプション）
        try:
            os.remove(audio_file)
            logger.debug(f"Removed temporary file: {audio_file}")
        except Exception as e:
            logger.warning(f"Could not remove temporary file {audio_file}: {e}")

        return result

    def get_video_info(self, url: str) -> Optional[Dict[str, Any]]:
        """
        YouTube動画の情報を取得

        Args:
            url: YouTube動画のURL

        Returns:
            動画情報の辞書
        """
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                return {
                    "id": info.get("id"),
                    "title": info.get("title"),
                    "uploader": info.get("uploader"),
                    "duration": info.get("duration"),
                    "description": info.get("description"),
                    "upload_date": info.get("upload_date"),
                    "view_count": info.get("view_count"),
                    "like_count": info.get("like_count"),
                }
            except Exception as e:
                logger.error(f"Error getting video info for {url}: {e}")
                return None

    def fetch_subtitles(self, url: str) -> Optional[str]:
        """
        yt-dlp で字幕（手動 → 自動）を取得しプレーンテキストで返す。

        優先言語（SUBTITLE_LANG_PRIORITY）を1言語ずつ試し、取得できた時点で終了する。
        日本語動画で ja を取得できれば en を取りにいかないため、不要な連続リクエスト
        による 429（Too Many Requests）を避けられる。各言語の DL は独立して試行し、
        ある言語が失敗（throttle/block）しても別言語で取得できることがある。

        取得できない場合（字幕なし／全言語 throttle／block）は None を返し、
        呼び出し側で Whisper フォールバックに回す。

        Args:
            url: YouTube動画のURL

        Returns:
            字幕テキスト。取得不可なら None。
        """
        base_opts: Dict[str, Any] = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitlesformat": "vtt",
            "outtmpl": str(self.output_dir / "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
        }
        if "ffmpeg_location" in self.ydl_opts:
            base_opts["ffmpeg_location"] = self.ydl_opts["ffmpeg_location"]

        # video_id を一度だけ解決（生成される字幕ファイル名の特定に使う）
        try:
            with yt_dlp.YoutubeDL({**base_opts, "subtitleslangs": []}) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            logger.warning(f"字幕メタ取得に失敗（Whisperへフォールバック）: {url}: {e}")
            return None
        video_id = info.get("id") if info else None
        if not video_id:
            return None

        # 優先言語を1つずつ試行。取得できたら即終了（後続言語の DL で 429 を誘発しない）
        for lang in SUBTITLE_LANG_PRIORITY:
            try:
                with yt_dlp.YoutubeDL({**base_opts, "subtitleslangs": [lang]}) as ydl:
                    ydl.download([url])
            except Exception as e:
                # この言語の DL に失敗しても、次の優先言語で取得できることがある
                logger.debug(f"字幕DL失敗 (lang={lang}): {url}: {e}")

            # 生成された字幕ファイル（{id}.{lang}.vtt）を読む
            matches = glob.glob(str(self.output_dir / f"{video_id}.{lang}.vtt"))
            text = ""
            if matches:
                subtitle_file = matches[0]
                try:
                    content = Path(subtitle_file).read_text(
                        encoding="utf-8", errors="ignore"
                    )
                    text = parse_subtitle_to_text(content)
                except OSError as e:
                    logger.warning(f"字幕ファイル読み込み失敗: {subtitle_file}: {e}")

            # この言語の生成物を掃除（取得有無に関わらず）
            for f in glob.glob(str(self.output_dir / f"{video_id}.{lang}.vtt")):
                try:
                    os.remove(f)
                except OSError:
                    pass

            if text:
                logger.info(f"字幕取得成功: {url} (lang={lang}, {len(text)} chars)")
                return text

        logger.info(f"字幕が見つかりません: {url}")
        return None

    def get_transcript(self, url: str) -> Optional[Dict[str, Any]]:
        """
        文字起こしを取得する。字幕を優先し、無ければ Whisper にフォールバック。

        Args:
            url: YouTube動画のURL

        Returns:
            {url, title, author, duration, transcript, source} の辞書。
            source は "subtitle" または "whisper"。失敗時は None。
        """
        subtitle_text = self.fetch_subtitles(url)
        if subtitle_text:
            video_info = self.get_video_info(url) or {}
            return {
                "url": url,
                "title": video_info.get("title", "Unknown"),
                "author": video_info.get("uploader", "Unknown"),
                "duration": video_info.get("duration", 0),
                "transcript": subtitle_text,
                "source": "subtitle",
            }

        # フォールバック: 音声DL + Whisper
        logger.info(f"字幕なし。Whisper にフォールバック: {url}")
        result = self.process_video(url)
        if result:
            result["source"] = "whisper"
            return result
        return None
