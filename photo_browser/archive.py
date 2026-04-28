from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
import posixpath
import re
import threading
from typing import Iterable
from urllib.parse import quote, unquote, urljoin

import httpx

from .config import AppConfig
from .models import ArchiveEntry, DirectoryListing, SearchIndex

SIZE_UNITS = {
    "B": 1,
    "K": 1024,
    "M": 1024**2,
    "G": 1024**3,
    "T": 1024**4,
}


class ArchiveError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def natural_sort_key(value: str) -> list[int | str]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value)]


def normalize_archive_path(path: str | None) -> str:
    if not path:
        return ""

    normalized = posixpath.normpath(unquote(path).strip())
    if normalized in {".", "/"}:
        return ""
    normalized = normalized.lstrip("/")
    if normalized.startswith("../") or normalized == "..":
        raise ArchiveError("Archive path traversal is not allowed.", status_code=400)
    return normalized


def archive_path_to_url(base_url: str, path: str, *, is_dir: bool) -> str:
    cleaned = normalize_archive_path(path)
    if not cleaned:
        return base_url
    encoded = quote(cleaned, safe="/")
    if is_dir and not encoded.endswith("/"):
        encoded = f"{encoded}/"
    return urljoin(base_url, encoded)


def resolve_directory_href(current_path: str, href: str) -> str | None:
    decoded = unquote(href).strip()
    if not decoded or decoded.startswith(("http://", "https://", "mailto:")):
        return None

    if decoded.startswith("./"):
        decoded = decoded[2:]

    normalized = posixpath.normpath(posixpath.join(current_path, decoded))
    if normalized in {".", ""}:
        return None
    if normalized.startswith("../") or normalized == "..":
        return None
    return normalized.lstrip("/")


def parse_directory_timestamp(value: str) -> datetime | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    return datetime.strptime(cleaned, "%d-%b-%Y %H:%M").replace(tzinfo=UTC)


def parse_directory_size(value: str) -> int | None:
    cleaned = value.strip()
    if not cleaned:
        return None

    match = re.fullmatch(r"(\d+(?:\.\d+)?)([BKMGTPbkmgpt]?)", cleaned)
    if not match:
        return None

    amount = float(match.group(1))
    unit = match.group(2).upper() or "B"
    return int(amount * SIZE_UNITS[unit])


@dataclass(slots=True)
class ParsedRow:
    href: str
    name: str
    modified_at: datetime | None
    size_bytes: int | None


class DirectoryIndexParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[ParsedRow] = []
        self._in_row = False
        self._current_td_class: str | None = None
        self._capturing_link_text = False
        self._row_href = ""
        self._link_text_parts: list[str] = []
        self._modified_text_parts: list[str] = []
        self._size_text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "tr":
            self._in_row = True
            self._current_td_class = None
            self._capturing_link_text = False
            self._row_href = ""
            self._link_text_parts = []
            self._modified_text_parts = []
            self._size_text_parts = []
            return

        if not self._in_row:
            return

        if tag == "td":
            self._current_td_class = attributes.get("class")
            return

        if tag == "a" and self._current_td_class == "display-name":
            self._row_href = attributes.get("href", "")
            self._capturing_link_text = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._capturing_link_text = False
            return

        if tag == "td":
            self._current_td_class = None
            return

        if tag != "tr" or not self._in_row:
            return

        self._in_row = False
        name = "".join(self._link_text_parts).strip()
        if not self._row_href or not name:
            return

        self.rows.append(
            ParsedRow(
                href=self._row_href,
                name=name,
                modified_at=parse_directory_timestamp("".join(self._modified_text_parts)),
                size_bytes=parse_directory_size("".join(self._size_text_parts)),
            )
        )

    def handle_data(self, data: str) -> None:
        if not self._in_row or not self._current_td_class:
            return

        if self._current_td_class == "display-name" and self._capturing_link_text:
            self._link_text_parts.append(data)
        elif self._current_td_class == "last-modified":
            self._modified_text_parts.append(data)
        elif self._current_td_class == "file-size":
            self._size_text_parts.append(data)


def parse_directory_listing(document: str, current_path: str) -> list[ArchiveEntry]:
    parser = DirectoryIndexParser()
    parser.feed(document)

    entries: list[ArchiveEntry] = []
    for row in parser.rows:
        resolved_path = resolve_directory_href(current_path, row.href)
        if not resolved_path:
            continue

        is_dir = row.href.rstrip().endswith("/")
        name = row.name.rstrip("/")
        if not name.startswith("."):
            entries.append(
                ArchiveEntry(
                    name=name,
                    path=resolved_path,
                    is_dir=is_dir,
                    modified_at=row.modified_at,
                    size_bytes=row.size_bytes,
                )
            )
    return entries


class ArchiveClient:
    def __init__(self, config: AppConfig) -> None:
        self._base_url = config.archive_base_url
        self._client = httpx.Client(
            follow_redirects=True,
            timeout=config.request_timeout_seconds,
        )

    @property
    def base_url(self) -> str:
        return self._base_url

    def close(self) -> None:
        self._client.close()

    def list_directory(self, path: str = "") -> DirectoryListing:
        normalized = normalize_archive_path(path)
        url = archive_path_to_url(self._base_url, normalized, is_dir=True)
        response = self._request(url)
        entries = parse_directory_listing(response.text, normalized)
        directories = [entry for entry in entries if entry.is_dir]
        files = [entry for entry in entries if not entry.is_dir]
        return DirectoryListing(path=normalized, directories=directories, files=files)

    def stream_asset(self, path: str, *, range_header: str | None = None) -> httpx.Response:
        normalized = normalize_archive_path(path)
        url = archive_path_to_url(self._base_url, normalized, is_dir=False)
        headers = {"Range": range_header} if range_header else None
        return self._request(url, headers=headers, stream=True)

    def _request(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        stream: bool = False,
    ) -> httpx.Response:
        try:
            request = self._client.build_request("GET", url, headers=headers)
            response = self._client.send(request, stream=stream)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            exc.response.close()
            if exc.response.status_code == 404:
                raise ArchiveError("The requested archive item was not found.", status_code=404) from exc
            raise ArchiveError("The upstream archive returned an unexpected status.") from exc
        except httpx.HTTPError as exc:
            raise ArchiveError("Unable to reach the upstream archive service.") from exc


class ArchiveIndex:
    def __init__(self, client: ArchiveClient, ttl_seconds: int, max_entries: int) -> None:
        self._client = client
        self._ttl = timedelta(seconds=ttl_seconds)
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._cached: SearchIndex | None = None

    def get_index(self) -> SearchIndex:
        with self._lock:
            if self._cached and datetime.now(tz=UTC) - self._cached.generated_at < self._ttl:
                return self._cached

        built = self._build_index()
        with self._lock:
            self._cached = built
            return built

    def _build_index(self) -> SearchIndex:
        queue = deque([""])
        visited: set[str] = set()
        entries: list[ArchiveEntry] = []
        warnings: list[str] = []
        truncated = False

        while queue:
            current_path = queue.popleft()
            if current_path in visited:
                continue
            visited.add(current_path)

            try:
                listing = self._client.list_directory(current_path)
            except ArchiveError as exc:
                warnings.append(f"{current_path or '/'}: {exc}")
                continue

            for directory in sorted(listing.directories, key=lambda item: natural_sort_key(item.name)):
                entries.append(directory)
                if len(entries) >= self._max_entries:
                    truncated = True
                    break
                queue.append(directory.path)

            if truncated:
                break

            for media_entry in sorted(listing.media_files, key=lambda item: natural_sort_key(item.name)):
                entries.append(media_entry)
                if len(entries) >= self._max_entries:
                    truncated = True
                    break

            if truncated:
                break

        return SearchIndex(
            entries=entries,
            generated_at=datetime.now(tz=UTC),
            truncated=truncated,
            warnings=warnings,
        )


def sort_entries(
    entries: Iterable[ArchiveEntry],
    *,
    sort_by: str,
    sort_order: str,
) -> list[ArchiveEntry]:
    reverse = sort_order == "desc"

    if sort_by == "date":
        return sorted(
            entries,
            key=lambda entry: (
                entry.modified_at or datetime.min.replace(tzinfo=UTC),
                natural_sort_key(entry.name),
            ),
            reverse=reverse,
        )

    if sort_by == "size":
        return sorted(
            entries,
            key=lambda entry: (entry.size_bytes or -1, natural_sort_key(entry.name)),
            reverse=reverse,
        )

    return sorted(entries, key=lambda entry: natural_sort_key(entry.name), reverse=reverse)
