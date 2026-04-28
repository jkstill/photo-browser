from datetime import UTC, datetime
import unittest

import httpx

from photo_browser.app import create_app
from photo_browser.config import AppConfig
from photo_browser.models import ArchiveEntry, DirectoryListing


class FakeStreamResponse:
    def __init__(self, chunks: list[bytes], headers: dict[str, str], status_code: int = 200) -> None:
        self._chunks = chunks
        self.headers = httpx.Headers(headers)
        self.status_code = status_code
        self.closed = False

    def iter_bytes(self):
        for chunk in self._chunks:
            yield chunk

    def close(self) -> None:
        self.closed = True


class AppVideoPlaybackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(
            AppConfig(
                archive_base_url="http://example.test/",
                host="127.0.0.1",
                port=8090,
                request_timeout_seconds=5.0,
                browse_page_size=24,
                search_page_size=40,
                index_ttl_seconds=3600,
                max_index_entries=5000,
                secret_key="test-key",
            )
        )
        self.client = self.app.test_client()
        self.archive_client = self.app.extensions["photo_browser"]["archive_client"]
        timestamp = datetime(2025, 6, 6, 15, 48, tzinfo=UTC)
        self.image_entry = ArchiveEntry(
            name="still.jpg",
            path="folder/still.jpg",
            is_dir=False,
            modified_at=timestamp,
            size_bytes=2048,
        )
        self.video_entry = ArchiveEntry(
            name="clip.mp4",
            path="folder/clip.mp4",
            is_dir=False,
            modified_at=timestamp,
            size_bytes=4096,
        )

        def fake_list_directory(path: str = "") -> DirectoryListing:
            if path == "folder":
                return DirectoryListing(path="folder", directories=[], files=[self.video_entry, self.image_entry])
            return DirectoryListing(path=path, directories=[], files=[])

        self.archive_client.list_directory = fake_list_directory

    def tearDown(self) -> None:
        self.archive_client.close()

    def test_video_detail_view_renders_custom_controls(self) -> None:
        response = self.client.get("/photo/folder/clip.mp4")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("<video", page)
        self.assertIn("data-mute", page)
        self.assertIn("data-seek", page)
        self.assertIn("player.js", page)

    def test_media_proxy_forwards_range_requests(self) -> None:
        captured: dict[str, str | None] = {}
        fake_response = FakeStreamResponse(
            chunks=[b"abc"],
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": "3",
                "Content-Range": "bytes 0-2/9",
                "Content-Type": "video/mp4",
            },
            status_code=206,
        )

        def fake_stream_asset(path: str, *, range_header: str | None = None) -> FakeStreamResponse:
            captured["path"] = path
            captured["range_header"] = range_header
            return fake_response

        self.archive_client.stream_asset = fake_stream_asset
        response = self.client.get("/media/folder/clip.mp4", headers={"Range": "bytes=0-2"})

        self.assertEqual(response.status_code, 206)
        self.assertEqual(captured["path"], "folder/clip.mp4")
        self.assertEqual(captured["range_header"], "bytes=0-2")
        self.assertEqual(response.headers["Content-Range"], "bytes 0-2/9")
        self.assertEqual(response.headers["Accept-Ranges"], "bytes")
        self.assertEqual(response.get_data(), b"abc")
        self.assertTrue(fake_response.closed)
