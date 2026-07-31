import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fluxdl import server, subtitle_engine


class UrlValidationTests(unittest.TestCase):
    def test_accepts_http_urls(self):
        self.assertTrue(server.valid_remote_url("https://www.youtube.com/watch?v=abc"))
        self.assertTrue(server.valid_remote_url("http://example.com/video"))

    def test_rejects_non_remote_values(self):
        self.assertFalse(server.valid_remote_url(""))
        self.assertFalse(server.valid_remote_url("youtube.com/watch?v=abc"))
        self.assertFalse(server.valid_remote_url("file:///tmp/video.mp4"))
        self.assertFalse(server.valid_remote_url("javascript:alert(1)"))


class FormatOptionsTests(unittest.TestCase):
    def test_video_mp4_1080p(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(server, "DOWNLOAD_DIR", Path(folder)),
            patch.object(server.shutil, "which", return_value="/usr/bin/ffmpeg"),
        ):
            options = server.format_options("video", "1080", "mp4", False, False)
        self.assertIn("height<=1080", options["format"])
        self.assertEqual(options["merge_output_format"], "mp4")

    def test_audio_mp3_uses_ffmpeg_postprocessor(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(server, "DOWNLOAD_DIR", Path(folder)),
            patch.object(server.shutil, "which", return_value="/usr/bin/ffmpeg"),
        ):
            options = server.format_options("audio", "best", "mp3", False, False)
        self.assertEqual(options["format"], "bestaudio/best")
        self.assertEqual(options["postprocessors"][0]["preferredcodec"], "mp3")

    def test_optional_subtitles_and_thumbnail(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(server, "DOWNLOAD_DIR", Path(folder)),
            patch.object(server.shutil, "which", return_value="/usr/bin/ffmpeg"),
        ):
            options = server.format_options("video", "best", "mkv", True, True)
        self.assertTrue(options["writesubtitles"])
        self.assertTrue(options["embedthumbnail"])

    def test_without_ffmpeg_uses_single_file_video(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(server, "DOWNLOAD_DIR", Path(folder)),
            patch.object(server.shutil, "which", return_value=None),
        ):
            options = server.format_options("video", "720", "mp4", False, False)
        self.assertEqual(options["format"], "b[height<=720][ext=mp4]/b[height<=720]")
        self.assertNotIn("merge_output_format", options)


class FallbackTests(unittest.TestCase):
    def test_detects_ssl_disconnect(self):
        self.assertTrue(
            server.is_ssl_disconnect(
                "[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol"
            )
        )
        self.assertFalse(server.is_ssl_disconnect("HTTP Error 404: Not Found"))

    def test_detects_subtitle_rate_limit(self):
        self.assertTrue(
            server.is_subtitle_rate_limit(
                "Unable to download video subtitles: HTTP Error 429: Too Many Requests"
            )
        )
        self.assertFalse(server.is_subtitle_rate_limit("HTTP Error 429: Too Many Requests"))

    def test_curl_fallback_has_retry_policy(self):
        options = {}
        server.enable_curl_fallback(options)
        self.assertEqual(options["external_downloader"]["https"], "curl")
        self.assertIn("--retry-all-errors", options["external_downloader_args"]["curl"])

    def test_disable_subtitles_keeps_other_options(self):
        options = {
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["zh"],
            "format": "best",
        }
        server.disable_subtitles(options)
        self.assertNotIn("writesubtitles", options)
        self.assertEqual(options["format"], "best")


class SubtitleEngineTests(unittest.TestCase):
    def test_srt_timestamp(self):
        self.assertEqual(subtitle_engine.srt_timestamp(3661.234), "01:01:01,234")

    def test_writes_valid_srt(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "test.srt"
            subtitle_engine.write_srt(
                output,
                [{"start": 0.0, "end": 1.25, "text": " Hello   world "}],
            )
            content = output.read_text(encoding="utf-8")
        self.assertIn("00:00:00,000 --> 00:00:01,250", content)
        self.assertIn("Hello world", content)

    def test_subtitle_job_round_trip(self):
        job = subtitle_engine.SubtitleJob(
            id="abc123",
            task_id="task123",
            video_filename="video.mp4",
            video_title="Video",
            model="base",
            target="zh",
            embed=True,
        )
        restored = subtitle_engine.SubtitleJob.from_public(job.public())
        self.assertEqual(restored.task_id, job.task_id)
        self.assertTrue(restored.embed)


if __name__ == "__main__":
    unittest.main()
