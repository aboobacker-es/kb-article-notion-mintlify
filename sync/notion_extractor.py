"""Walk the Notion page tree starting from configured root pages.

Notion structures pages via two mechanisms:
  1. `child_page` blocks — hard-nested pages
  2. `mention` blocks / rich-text hrefs pointing at other Notion pages

Both need to be followed. Some pages are referenced from multiple places (a
Screen article may also be linked from an Interviews page); we deduplicate by
page ID and record the first-discovery parent as the canonical location in Git.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from .notion_client import NotionClient

# Notion page URLs come in these shapes:
#   https://www.notion.so/<workspace>/<slug>-<32hex>
#   https://www.notion.so/<32hex>
#   https://notion.so/<32hex>
#   https://app.notion.com/p/<32hex>
#   Bare page IDs (36-char UUID) from `mention.page.id` responses
# We only extract IDs from strings that look like Notion references — never
# arbitrary URLs that happen to contain 32 hex chars (e.g., Pylon KB URLs).
_HEX32 = re.compile(r"[0-9a-f]{32}")
_NOTION_HOSTS = ("notion.so", "notion.site", "notion.com")


def extract_page_id(url_or_href: str | None) -> str | None:
    if not url_or_href:
        return None
    s = url_or_href.strip()
    normalized = s.replace("-", "")
    # Bare UUID/hex (from mention.page.id — no scheme, no slashes)
    if "://" not in s and "/" not in s:
        m = _HEX32.fullmatch(normalized)
        return m.group(0) if m else None
    # Only trust hex extraction inside recognised Notion hosts
    if not any(host in s for host in _NOTION_HOSTS):
        return None
    m = _HEX32.search(normalized)
    return m.group(0) if m else None


def canonical_id(page_id: str) -> str:
    """Notion IDs come as either dashed (36-char UUID) or bare (32-char hex). Normalize to bare."""
    return page_id.replace("-", "").lower()


def slugify(title: str) -> str:
    s = title.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s-]+", "-", s)
    return s.strip("-") or "untitled"


@dataclass
class PageNode:
    page_id: str                 # bare 32-hex
    title: str
    slug: str                    # slugified title
    parent_id: str | None        # bare 32-hex of parent page in the walked tree, or None for roots
    root_slug: str               # "screen" or "interviews"
    depth: int                   # 0 = root
    last_edited_time: str        # ISO-8601 from Notion
    git_path: str = ""           # e.g. "docs/screen/getting-started/introduction.mdx" — filled after tree is walked
    blocks: list[dict] = field(default_factory=list)   # lazy-fetched
    order: int = 0               # order among siblings (for docs.json navigation)


def _page_title(page: dict) -> str:
    props = page.get("properties", {})
    title_prop = props.get("title") or props.get("Name") or {}
    spans = title_prop.get("title", [])
    return "".join(s.get("plain_text", "") for s in spans).strip() or "Untitled"


def _iter_page_refs(block: dict) -> Iterable[str]:
    """Yield 32-hex page IDs referenced by this block's rich text (mentions or hyperlinks to Notion pages)."""
    t = block.get("type")
    if not t:
        return
    payload = block.get(t, {})
    rich = payload.get("rich_text") or payload.get("caption") or []
    for span in rich:
        if span.get("type") == "mention":
            mention = span.get("mention", {})
            if mention.get("type") == "page":
                pid = mention.get("page", {}).get("id")
                canon = extract_page_id(pid)
                if canon:
                    yield canon
        href = span.get("href")
        pid = extract_page_id(href)
        if pid:
            yield pid


def walk_tree(client: NotionClient, roots: list[dict]) -> dict[str, PageNode]:
    """BFS over Notion pages starting from each configured root.

    Returns a dict mapping canonical page ID → PageNode. Every node has its final
    `git_path` filled in.
    """
    nodes: dict[str, PageNode] = {}
    failed: set[str] = set()
    queue: list[tuple[str, str | None, str, int]] = []  # (page_id, parent_id, root_slug, depth)

    for root in roots:
        rid = canonical_id(root["page_id"])
        queue.append((rid, None, root["slug"], 0))

    order_counter: dict[tuple[str | None, str], int] = {}

    while queue:
        page_id, parent_id, root_slug, depth = queue.pop(0)
        if page_id in nodes or page_id in failed:
            continue

        try:
            page_meta = client.get_page(page_id)
        except Exception as e:
            print(f"[warn] could not fetch page {page_id}: {e}")
            failed.add(page_id)
            continue

        if page_meta.get("object") != "page" or page_meta.get("archived"):
            continue

        title = _page_title(page_meta)

        # Skip pages matching an exclusion pattern (e.g., huge release-notes pages).
        # Import here to avoid a top-of-file circular concern.
        from . import config as _cfg
        title_lower = title.lower()
        if any(pat.lower() in title_lower for pat in _cfg.EXCLUDED_TITLE_PATTERNS):
            print(f"[skip] excluded by title pattern: {title!r}")
            failed.add(page_id)   # reuse failed set so links to this page don't re-queue
            continue

        slug = slugify(title)

        # Give each page a stable order among its siblings.
        order_key = (parent_id, root_slug)
        order_counter[order_key] = order_counter.get(order_key, -1) + 1
        order = order_counter[order_key]

        node = PageNode(
            page_id=page_id,
            title=title,
            slug=slug,
            parent_id=parent_id,
            root_slug=root_slug,
            depth=depth,
            last_edited_time=page_meta.get("last_edited_time", ""),
            order=order,
        )
        nodes[page_id] = node

        # Fetch blocks to discover linked/nested pages.
        try:
            blocks = list(client.get_block_children(page_id))
        except Exception as e:
            print(f"[warn] could not fetch blocks for {page_id} ({title!r}): {e}")
            blocks = []
        node.blocks = blocks

        # Discover children: both child_page blocks and page references in rich text.
        for block in blocks:
            btype = block.get("type")
            if btype == "child_page":
                queue.append((canonical_id(block["id"]), page_id, root_slug, depth + 1))
            else:
                for referenced_id in _iter_page_refs(block):
                    if referenced_id not in nodes:
                        queue.append((referenced_id, page_id, root_slug, depth + 1))

    # Assign git paths using the discovered parent chain.
    _assign_git_paths(nodes, roots)
    return nodes


def _assign_git_paths(nodes: dict[str, PageNode], roots: list[dict]) -> None:
    root_ids = {canonical_id(r["page_id"]): r for r in roots}

    def path_for(node: PageNode) -> str:
        parts: list[str] = []
        cur: PageNode | None = node
        while cur is not None and cur.page_id not in root_ids:
            parts.append(cur.slug)
            cur = nodes.get(cur.parent_id) if cur.parent_id else None
        parts.reverse()
        if node.page_id in root_ids:
            return f"docs/{node.root_slug}/index.mdx"
        return f"docs/{node.root_slug}/" + "/".join(parts) + ".mdx"

    for node in nodes.values():
        node.git_path = path_for(node)
