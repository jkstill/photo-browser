from datetime import UTC, datetime
import unittest

from photo_browser.archive import (
    normalize_archive_path,
    parse_directory_listing,
    parse_directory_size,
    parse_directory_timestamp,
)
from photo_browser.models import ArchiveEntry, DirectoryListing


SAMPLE_LISTING = """
<!doctype html>
<html>
  <body>
    <table>
      <tr>
        <td class="display-name"><a href="./../">../</a></td>
        <td class="last-modified"></td>
        <td class="file-size"></td>
      </tr>
      <tr>
        <td class="display-name"><a href="./Trip-2025/">Trip-2025/</a></td>
        <td class="last-modified">13-Jun-2025 13:56</td>
        <td class="file-size"></td>
      </tr>
      <tr>
        <td class="display-name"><a href="./DSC_1161.JPG">DSC_1161.JPG</a></td>
        <td class="last-modified">06-Jun-2025 15:48</td>
        <td class="file-size">1.3M</td>
      </tr>
      <tr>
        <td class="display-name"><a href="./notes.txt">notes.txt</a></td>
        <td class="last-modified">06-Jun-2025 15:49</td>
        <td class="file-size">282B</td>
      </tr>
    </table>
  </body>
</html>
"""


class ArchiveParsingTests(unittest.TestCase):
    def test_path_normalization_rejects_traversal(self) -> None:
        with self.assertRaises(Exception):
            normalize_archive_path("../secret")

    def test_parse_directory_size(self) -> None:
        self.assertEqual(parse_directory_size("22.0k"), 22528)
        self.assertEqual(parse_directory_size("282B"), 282)
        self.assertIsNone(parse_directory_size(""))

    def test_parse_directory_timestamp(self) -> None:
        self.assertEqual(
            parse_directory_timestamp("13-Jun-2025 13:56"),
            datetime(2025, 6, 13, 13, 56, tzinfo=UTC),
        )
        self.assertIsNone(parse_directory_timestamp("13-Sep-30828 19:48"))

    def test_parse_directory_listing(self) -> None:
        entries = parse_directory_listing(SAMPLE_LISTING, "Trees/Trees-TV-Park-2025-06-06")
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0].path, "Trees/Trees-TV-Park-2025-06-06/Trip-2025")
        self.assertTrue(entries[0].is_dir)
        self.assertTrue(entries[1].is_image)
        self.assertEqual(entries[1].size_bytes, 1363148)
        self.assertEqual(entries[2].name, "notes.txt")

    def test_directory_listing_media_classification(self) -> None:
        photo = ArchiveEntry(name="still.jpg", path="gallery/still.jpg", is_dir=False)
        video = ArchiveEntry(name="clip.avi", path="gallery/clip.avi", is_dir=False)
        text = ArchiveEntry(name="notes.txt", path="gallery/notes.txt", is_dir=False)
        listing = DirectoryListing(path="gallery", directories=[], files=[photo, video, text])

        self.assertTrue(video.is_video)
        self.assertTrue(video.is_media)
        self.assertEqual([entry.name for entry in listing.media_files], ["still.jpg", "clip.avi"])
        self.assertEqual([entry.name for entry in listing.other_files], ["notes.txt"])



if __name__ == "__main__":
    unittest.main()
