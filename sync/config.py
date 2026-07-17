"""Configuration for the Notion → Mintlify sync worker."""
from __future__ import annotations

# Notion root pages. Each becomes a top-level Mintlify navigation group.
# Add new roots here to expose more sections of the KB.
ROOTS: list[dict] = [
    {
        "page_id": "372a50e0dca3819cb181da31c6c4e11f",
        "group": "Screen",
        "slug": "screen",
    },
    {
        "page_id": "372a50e0dca381bbacf8e0160de43592",
        "group": "Interviews",
        "slug": "interviews",
    },
]

# Article page layout mode.
# "custom" = fully AI-first: no sidebar, no TOC, no footer. Users navigate
# exclusively through the AI chatbot and its citations. This is intentional —
# see plan file, Q3.
ARTICLE_MODE = "custom"

# Skip Notion pages whose title (case-insensitive) contains any of these
# substrings. Used to exclude giant pages (e.g., monthly release notes with
# 30+ 50-MB GIFs) that blow past GitHub's 100 MB per-file / repo bloat limits.
# Content of skipped pages can be published separately (e.g., via a CDN-hosted
# blog) if needed.
EXCLUDED_TITLE_PATTERNS: list[str] = [
    "release notes",
]

# Where MDX files are written, relative to repo root.
DOCS_DIR = "docs"
IMAGES_DIR = "images"
STATE_FILE = ".sync-state.json"

# Notion API
NOTION_API_VERSION = "2022-06-28"
NOTION_API_BASE = "https://api.notion.com/v1"

# Retry policy for rate-limited endpoints (attachments in Pylon publisher use this same idea).
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 30

# Truncate the auto-generated description (from first paragraph) to this length.
DESCRIPTION_MAX_LEN = 160
