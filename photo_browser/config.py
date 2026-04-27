from __future__ import annotations

from dataclasses import dataclass
import os


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value else default


@dataclass(frozen=True, slots=True)
class AppConfig:
    archive_base_url: str
    host: str
    port: int
    request_timeout_seconds: float
    browse_page_size: int
    search_page_size: int
    index_ttl_seconds: int
    max_index_entries: int
    secret_key: str


def load_config() -> AppConfig:
    archive_base_url = os.getenv("PHOTO_ARCHIVE_BASE_URL", "http://poirot:4242").strip()
    if not archive_base_url:
        raise ValueError("PHOTO_ARCHIVE_BASE_URL must not be empty.")

    normalized_url = archive_base_url.rstrip("/") + "/"
    return AppConfig(
        archive_base_url=normalized_url,
        host=os.getenv("PHOTO_BROWSER_HOST", "0.0.0.0"),
        port=_int_env("PHOTO_BROWSER_PORT", 8090),
        request_timeout_seconds=_float_env("PHOTO_BROWSER_REQUEST_TIMEOUT_SECONDS", 15.0),
        browse_page_size=_int_env("PHOTO_BROWSER_BROWSE_PAGE_SIZE", 24),
        search_page_size=_int_env("PHOTO_BROWSER_SEARCH_PAGE_SIZE", 40),
        index_ttl_seconds=_int_env("PHOTO_BROWSER_INDEX_TTL_SECONDS", 3600),
        max_index_entries=_int_env("PHOTO_BROWSER_MAX_INDEX_ENTRIES", 5000),
        secret_key=os.getenv("PHOTO_BROWSER_SECRET_KEY", "change-me"),
    )
