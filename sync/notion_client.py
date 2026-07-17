"""Thin Notion REST API client with retry."""
from __future__ import annotations

import os
import time
from typing import Any, Iterator

import requests

from . import config


class NotionClient:
    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("NOTION_API_KEY") or os.environ.get("NOTION_TOKEN")
        if not self.token:
            raise RuntimeError("NOTION_API_KEY environment variable is required")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": config.NOTION_API_VERSION,
            "Content-Type": "application/json",
        })

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{config.NOTION_API_BASE}{path}"
        for attempt in range(1, config.MAX_RETRIES + 1):
            r = self.session.request(method, url, timeout=30, **kwargs)
            if r.status_code == 429 or r.status_code >= 500:
                if attempt < config.MAX_RETRIES:
                    time.sleep(config.RETRY_BACKOFF_SECONDS * attempt)
                    continue
            r.raise_for_status()
            return r.json()
        r.raise_for_status()
        return {}

    def get_page(self, page_id: str) -> dict:
        return self._request("GET", f"/pages/{page_id}")

    def get_block_children(self, block_id: str) -> Iterator[dict]:
        """Yield all child blocks of a block (auto-paginates)."""
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            data = self._request("GET", f"/blocks/{block_id}/children", params=params)
            for block in data.get("results", []):
                yield block
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
