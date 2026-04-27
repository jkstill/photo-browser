# Photo Browser

This repository contains a small Flask application that fronts a static photo archive served as HTML directory listings. By default it points at `http://poirot:4242`, but the upstream URL is configurable through environment variables.

## Features

- Browse archive directories with breadcrumb navigation.
- View photos in a paginated grid.
- Open a full-size photo view with previous and next navigation.
- Search folders and image filenames across a cached archive index.
- Sort directory contents and search results by name, date, or size.
- Download photos and non-image files through the app.

## Configuration

Environment variables:

- `PHOTO_ARCHIVE_BASE_URL`: upstream archive root. Default: `http://poirot:4242`
- `PHOTO_BROWSER_HOST`: bind host. Default: `0.0.0.0`
- `PHOTO_BROWSER_PORT`: bind port. Default: `8080`
- `PHOTO_BROWSER_REQUEST_TIMEOUT_SECONDS`: upstream timeout. Default: `15`
- `PHOTO_BROWSER_BROWSE_PAGE_SIZE`: photos per directory page. Default: `24`
- `PHOTO_BROWSER_SEARCH_PAGE_SIZE`: results per search page. Default: `40`
- `PHOTO_BROWSER_INDEX_TTL_SECONDS`: search index cache lifetime. Default: `3600`
- `PHOTO_BROWSER_MAX_INDEX_ENTRIES`: cap for indexed folders and photos. Default: `5000`
- `PHOTO_BROWSER_SECRET_KEY`: Flask secret key

## Local Run

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
photo-browser
```

Then open `http://127.0.0.1:8080`.

## Tests

```bash
python3 -m unittest
```

## Systemd

Example deployment artifacts live in [`deploy/`](deploy):

- `deploy/photo-browser.service`
- `deploy/photo-browser.env.example`
