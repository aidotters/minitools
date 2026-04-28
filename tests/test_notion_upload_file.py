"""Tests for NotionPublisher.upload_file (File Upload API)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from minitools.publishers.notion import NotionPublisher


@pytest.fixture
def publisher(monkeypatch):
    monkeypatch.setenv("NOTION_API_KEY", "test-key")
    return NotionPublisher(source_type="arxiv")


@pytest.fixture
def small_image(tmp_path: Path) -> Path:
    img = tmp_path / "test.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    return img


class TestUploadFile:
    @pytest.mark.asyncio
    async def test_upload_file_success(self, publisher, small_image):
        """正常系: file_uploads.create + multipart POST が成功する"""
        # Notion API response (step 1)
        create_resp = {
            "id": "uuid-123",
            "upload_url": "https://api.notion.com/v1/file_uploads/uuid-123/send",
        }

        # httpx mock for step 2 (multipart POST)
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_post_resp)

        with (
            patch.object(
                publisher, "_retry_api_call", new=AsyncMock(return_value=create_resp)
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            upload_id = await publisher.upload_file(small_image)

        assert upload_id == "uuid-123"
        mock_client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upload_file_size_limit(self, publisher, tmp_path):
        """5MB 超の画像は警告 + None を返す"""
        big_image = tmp_path / "big.png"
        big_image.write_bytes(b"0" * (5 * 1024 * 1024 + 1))

        result = await publisher.upload_file(big_image)
        assert result is None

    @pytest.mark.asyncio
    async def test_upload_file_api_error(self, publisher, small_image):
        """ステップ2のAPIエラーでリトライし、最終的に None を返す"""
        create_resp = {
            "id": "uuid-err",
            "upload_url": "https://api.notion.com/v1/file_uploads/uuid-err/send",
        }

        # httpx raises on every attempt
        import httpx

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 500
        mock_post_resp.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "500 Error", request=MagicMock(), response=mock_post_resp
            )
        )

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_post_resp)

        with (
            patch.object(
                publisher, "_retry_api_call", new=AsyncMock(return_value=create_resp)
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            upload_id = await publisher.upload_file(small_image)

        assert upload_id is None
        # 3 回リトライ
        assert mock_client.post.await_count == 3

    @pytest.mark.asyncio
    async def test_upload_file_mime_guess(self, publisher, small_image):
        """mime_type=None 時に推定される"""
        create_resp = {
            "id": "uuid-mime",
            "upload_url": "https://example.com/upload",
        }

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_post_resp)

        captured_args: dict = {}

        async def _capture_retry(func, **kwargs):
            # 実関数を呼び出して body を確認
            captured_args["func"] = func
            return create_resp

        with (
            patch.object(publisher, "_retry_api_call", new=_capture_retry),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            upload_id = await publisher.upload_file(small_image, mime_type=None)

        assert upload_id == "uuid-mime"
        # multipart POST の files 引数で MIME が設定されている
        call_kwargs = mock_client.post.await_args.kwargs
        # files=(filename, fp, mime_type) の形
        files = call_kwargs.get("files") or mock_client.post.await_args.args
        # files の MIME は image/png
        assert "image/png" in str(files)
