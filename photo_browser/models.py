from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import PurePosixPath

IMAGE_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".gif",
    ".heic",
    ".heif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}


@dataclass(frozen=True, slots=True)
class ArchiveEntry:
    name: str
    path: str
    is_dir: bool
    modified_at: datetime | None = None
    size_bytes: int | None = None

    @property
    def extension(self) -> str:
        return PurePosixPath(self.name).suffix.lower()

    @property
    def is_image(self) -> bool:
        return not self.is_dir and self.extension in IMAGE_EXTENSIONS

    @property
    def parent_path(self) -> str:
        parent = PurePosixPath(self.path).parent
        return "" if str(parent) == "." else str(parent)


@dataclass(frozen=True, slots=True)
class DirectoryListing:
    path: str
    directories: list[ArchiveEntry]
    files: list[ArchiveEntry]

    @property
    def photos(self) -> list[ArchiveEntry]:
        return [entry for entry in self.files if entry.is_image]

    @property
    def other_files(self) -> list[ArchiveEntry]:
        return [entry for entry in self.files if not entry.is_image]


@dataclass(frozen=True, slots=True)
class SearchIndex:
    entries: list[ArchiveEntry]
    generated_at: datetime
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)
