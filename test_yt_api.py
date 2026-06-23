import unittest
import tempfile

from yt_api import build_command, is_supported_url, normalize_youtube_url


class TestYTApiHelpers(unittest.TestCase):
    out_template = f"{tempfile.gettempdir()}/%(id)s.%(ext)s"

    def test_valid_youtube_urls(self) -> None:
        self.assertTrue(is_supported_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertTrue(is_supported_url("https://youtu.be/dQw4w9WgXcQ"))

    def test_rejects_non_youtube_urls(self) -> None:
        self.assertFalse(is_supported_url("https://example.com/video"))
        self.assertFalse(is_supported_url("ftp://www.youtube.com/watch?v=test"))

    def test_normalizes_valid_urls(self) -> None:
        self.assertEqual(
            normalize_youtube_url("https://youtu.be/dQw4w9WgXcQ"),
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        self.assertEqual(
            normalize_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )

    def test_rejects_invalid_video_ids(self) -> None:
        self.assertIsNone(normalize_youtube_url("https://youtu.be/not-valid!!!"))
        self.assertIsNone(normalize_youtube_url("https://www.youtube.com/watch?v=abc"))

    def test_build_mp3_command(self) -> None:
        cmd = build_command("mp3", self.out_template)
        self.assertIn("--extract-audio", cmd)
        self.assertIn("mp3", cmd)
        self.assertIn("--batch-file", cmd)

    def test_build_mp4_command(self) -> None:
        cmd = build_command("mp4", self.out_template)
        self.assertIn("--merge-output-format", cmd)
        self.assertIn("mp4", cmd)
        self.assertIn("--batch-file", cmd)


if __name__ == "__main__":
    unittest.main()
