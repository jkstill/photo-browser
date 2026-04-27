from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from urllib.parse import quote

from flask import Flask, Response, abort, render_template, request, url_for

from .archive import (
    ArchiveClient,
    ArchiveError,
    ArchiveIndex,
    archive_path_to_url,
    natural_sort_key,
    normalize_archive_path,
    sort_entries,
)
from .config import AppConfig, load_config
from .models import ArchiveEntry

SORT_OPTIONS = {
    "name": "Name",
    "date": "Date",
    "size": "Size",
}


@dataclass(frozen=True, slots=True)
class Pagination:
    items: list[ArchiveEntry]
    page: int
    per_page: int
    total: int
    total_pages: int
    start_item: int
    end_item: int

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def prev_page(self) -> int:
        return max(1, self.page - 1)

    @property
    def next_page(self) -> int:
        return min(self.total_pages, self.page + 1)


def create_app(config: AppConfig | None = None) -> Flask:
    config_obj = config or load_config()
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config_obj.secret_key

    archive_client = ArchiveClient(config_obj)
    archive_index = ArchiveIndex(
        archive_client,
        ttl_seconds=config_obj.index_ttl_seconds,
        max_entries=config_obj.max_index_entries,
    )

    app.extensions["photo_browser"] = {
        "config_obj": config_obj,
        "archive_client": archive_client,
        "archive_index": archive_index,
    }

    @app.context_processor
    def inject_helpers() -> dict[str, object]:
        def directory_href(path: str) -> str:
            return url_for("home") if not path else url_for("browse_directory", archive_path=path)

        def photo_href(path: str, **params: object) -> str:
            return url_for("photo_detail", archive_path=path, **params)

        def media_href(path: str) -> str:
            return url_for("media_proxy", archive_path=path)

        def download_href(path: str) -> str:
            return url_for("download_asset", archive_path=path)

        return {
            "config": config_obj,
            "directory_href": directory_href,
            "photo_href": photo_href,
            "media_href": media_href,
            "download_href": download_href,
            "format_timestamp": format_timestamp,
            "format_size": format_size,
            "sort_options": SORT_OPTIONS,
        }

    @app.errorhandler(ArchiveError)
    def handle_archive_error(error: ArchiveError) -> tuple[str, int]:
        return (
            render_template(
                "error.html",
                title="Archive Error",
                message=str(error),
            ),
            error.status_code,
        )

    @app.get("/")
    def home() -> str:
        return render_directory("")

    @app.get("/browse/<path:archive_path>")
    def browse_directory(archive_path: str) -> str:
        return render_directory(archive_path)

    @app.get("/photo/<path:archive_path>")
    def photo_detail(archive_path: str) -> str:
        normalized = normalize_archive_path(archive_path)
        sort_by = normalize_sort(request.args.get("sort"))
        sort_order = normalize_sort_order(request.args.get("order"))
        page_argument = request.args.get("page")
        current_page = coerce_positive_int(page_argument, 1)

        listing = archive_client.list_directory(PurePosixPath(normalized).parent.as_posix())
        photos = sort_entries(listing.photos, sort_by=sort_by, sort_order=sort_order)
        photo_map = {photo.path: index for index, photo in enumerate(photos)}
        if normalized not in photo_map:
            abort(404)

        selected = photos[photo_map[normalized]]
        current_index = photo_map[normalized]
        previous_photo = photos[current_index - 1] if current_index > 0 else None
        next_photo = photos[current_index + 1] if current_index + 1 < len(photos) else None
        return_page = ((current_index) // max(1, app_config().browse_page_size)) + 1
        effective_page = return_page if page_argument is None else current_page

        return render_template(
            "photo.html",
            title=selected.name,
            photo=selected,
            parent_path=selected.parent_path,
            breadcrumbs=build_breadcrumbs(selected.parent_path),
            previous_photo=previous_photo,
            next_photo=next_photo,
            sort_by=sort_by,
            sort_order=sort_order,
            return_page=effective_page,
            upstream_url=archive_path_to_url(config_obj.archive_base_url, selected.path, is_dir=False),
        )

    @app.get("/media/<path:archive_path>")
    def media_proxy(archive_path: str) -> Response:
        return render_media_response(archive_path, download=False)

    @app.get("/download/<path:archive_path>")
    def download_asset(archive_path: str) -> Response:
        return render_media_response(archive_path, download=True)

    @app.get("/search")
    def search() -> str:
        query = request.args.get("q", "").strip()
        sort_by = normalize_sort(request.args.get("sort"))
        sort_order = normalize_sort_order(request.args.get("order"))
        page = coerce_positive_int(request.args.get("page"), 1)
        search_index = archive_index.get_index() if query else None

        results: list[ArchiveEntry] = []
        if search_index:
            needle = query.casefold()
            results = [
                entry
                for entry in search_index.entries
                if needle in entry.name.casefold() or needle in entry.path.casefold()
            ]
            results = sort_search_results(results, query=query, sort_by=sort_by, sort_order=sort_order)

        pagination = paginate(results, page, app_config().search_page_size)
        return render_template(
            "search.html",
            title="Search",
            query=query,
            sort_by=sort_by,
            sort_order=sort_order,
            pagination=pagination,
            indexed_at=search_index.generated_at if search_index else None,
            index_truncated=search_index.truncated if search_index else False,
            index_warnings=search_index.warnings if search_index else [],
        )

    def render_directory(archive_path: str) -> str:
        normalized = normalize_archive_path(archive_path)
        listing = archive_client.list_directory(normalized)
        sort_by = normalize_sort(request.args.get("sort"))
        sort_order = normalize_sort_order(request.args.get("order"))
        page = coerce_positive_int(request.args.get("page"), 1)

        directories = sort_entries(listing.directories, sort_by=sort_by, sort_order=sort_order)
        photos = sort_entries(listing.photos, sort_by=sort_by, sort_order=sort_order)
        other_files = sort_entries(listing.other_files, sort_by=sort_by, sort_order=sort_order)
        pagination = paginate(photos, page, app_config().browse_page_size)

        current_name = "Photo Archive" if not normalized else PurePosixPath(normalized).name
        parent_path = None if not normalized else listing.path and PurePosixPath(listing.path).parent.as_posix()
        if parent_path == ".":
            parent_path = ""

        return render_template(
            "directory.html",
            title=current_name,
            current_name=current_name,
            current_path=normalized,
            parent_path=parent_path,
            breadcrumbs=build_breadcrumbs(normalized),
            directories=directories,
            pagination=pagination,
            other_files=other_files,
            sort_by=sort_by,
            sort_order=sort_order,
            upstream_url=archive_path_to_url(config_obj.archive_base_url, normalized, is_dir=True),
        )

    def render_media_response(archive_path: str, *, download: bool) -> Response:
        normalized = normalize_archive_path(archive_path)
        payload, headers = archive_client.fetch_asset(normalized)
        filename = PurePosixPath(normalized).name
        content_disposition = "attachment" if download else "inline"
        response = Response(payload, mimetype=headers["content-type"])
        response.headers["Cache-Control"] = "public, max-age=300"
        response.headers["Content-Disposition"] = (
            f"{content_disposition}; filename=\"{filename}\"; "
            f"filename*=UTF-8''{quote(filename)}"
        )
        if headers["content-length"]:
            response.headers["Content-Length"] = headers["content-length"]
        if headers["last-modified"]:
            response.headers["Last-Modified"] = headers["last-modified"]
        return response

    def app_config() -> AppConfig:
        return app.extensions["photo_browser"]["config_obj"]

    return app


def normalize_sort(value: str | None) -> str:
    return value if value in SORT_OPTIONS else "name"


def normalize_sort_order(value: str | None) -> str:
    return value if value in {"asc", "desc"} else "asc"


def coerce_positive_int(value: str | None, default: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def paginate(items: list[ArchiveEntry], page: int, per_page: int) -> Pagination:
    total = len(items)
    total_pages = max(1, ((total - 1) // per_page) + 1) if total else 1
    current_page = min(max(page, 1), total_pages)
    start_index = (current_page - 1) * per_page
    end_index = start_index + per_page
    current_items = items[start_index:end_index]

    if not total:
        return Pagination(
            items=[],
            page=1,
            per_page=per_page,
            total=0,
            total_pages=1,
            start_item=0,
            end_item=0,
        )

    return Pagination(
        items=current_items,
        page=current_page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        start_item=start_index + 1,
        end_item=min(end_index, total),
    )


def build_breadcrumbs(path: str) -> list[dict[str, str]]:
    if not path:
        return []

    crumbs: list[dict[str, str]] = []
    parts = PurePosixPath(path).parts
    for index in range(len(parts)):
        crumbs.append(
            {
                "label": parts[index],
                "path": "/".join(parts[: index + 1]),
            }
        )
    return crumbs


def format_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "Unknown"

    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size_bytes} B"


def format_timestamp(value: datetime | None) -> str:
    if value is None:
        return "Unknown"
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


def sort_search_results(
    entries: list[ArchiveEntry],
    *,
    query: str,
    sort_by: str,
    sort_order: str,
) -> list[ArchiveEntry]:
    needle = query.casefold()

    if sort_by != "name":
        return sort_entries(entries, sort_by=sort_by, sort_order=sort_order)

    reverse = sort_order == "desc"
    return sorted(
        entries,
        key=lambda entry: (
            0 if entry.name.casefold().startswith(needle) else 1,
            0 if needle in entry.name.casefold() else 1,
            natural_sort_key(entry.name),
        ),
        reverse=reverse,
    )
