"""Serialize a Notion page's block list into a Mintlify MDX document.

Mapping table (see plan file):
  paragraph/text                       -> markdown paragraph with inline rich text
  heading_1/2/3                        -> ##/###/#### (H1 is reserved for the frontmatter title)
  bulleted_list_item/numbered_list_item -> - / 1.
  code                                 -> ```lang fenced block
  callout                              -> <Note>/<Tip>/<Warning>/<Info>/<Danger> based on color+icon
  image                                -> <Frame><img/></Frame>
  video                                -> <Frame><video/></Frame>
  table + table_row                    -> GFM markdown table
  toggle                               -> <Accordion title="...">...</Accordion>
  bookmark                             -> <Card title="..." href="..." />
  divider                              -> ---
  quote                                -> > ...
  child_page                           -> emitted as a link (the child gets its own MDX file)
  embed/synced_block/database views    -> skipped with a comment
"""
from __future__ import annotations

import hashlib
import os
import re
import urllib.parse
from typing import Callable, Iterable

import requests

from . import config
from .notion_client import NotionClient
from .notion_extractor import PageNode, canonical_id, extract_page_id

# ------- rich text -------

def _escape_mdx(text: str) -> str:
    """Escape characters that would be interpreted as MDX/JSX."""
    return text.replace("{", "\\{").replace("}", "\\}").replace("<", "\\<").replace(">", "\\>")


def rich_text_to_md(rich: list[dict], id_to_path: dict[str, str]) -> str:
    """Convert Notion rich_text spans to markdown with inline formatting."""
    out: list[str] = []
    for span in rich:
        if span.get("type") == "equation":
            expr = span.get("equation", {}).get("expression", "")
            out.append(f"${expr}$")
            continue
        plain = span.get("plain_text", "")
        if not plain:
            continue
        text = _escape_mdx(plain)
        ann = span.get("annotations", {})
        if ann.get("code"):
            text = f"`{plain}`"  # code spans preserve the raw text
        else:
            if ann.get("bold"):
                text = f"**{text}**"
            if ann.get("italic"):
                text = f"*{text}*"
            if ann.get("strikethrough"):
                text = f"~~{text}~~"

        href = span.get("href")
        # Notion page mentions carry the target via `mention.page.id`, not always via href.
        mention = span.get("mention") or {}
        if mention.get("type") == "page":
            href = mention.get("page", {}).get("id") or href

        if href:
            target_id = extract_page_id(href)
            if target_id and target_id in id_to_path:
                # Rewrite Notion page URL → Mintlify path (strip .mdx and 'docs/' prefix; Mintlify serves at root)
                path = id_to_path[target_id]
                path = re.sub(r"^docs/", "/", path).removesuffix(".mdx")
                text = f"[{text}]({path})"
            elif href.startswith("http"):
                text = f"[{text}]({href})"
        out.append(text)
    return "".join(out)


# ------- images -------

def _download_and_cache_image(url: str, images_root: str, page_slug: str) -> str | None:
    """Download an image and store it as images/<page_slug>/<sha1>.<ext>. Returns a repo-relative path."""
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
    except Exception as e:
        print(f"[warn] image download failed: {url[:80]}... : {e}")
        return None
    content = r.content
    ext = _infer_ext(url, r.headers.get("Content-Type", ""))
    digest = hashlib.sha1(content).hexdigest()[:16]
    subdir = os.path.join(images_root, page_slug)
    os.makedirs(subdir, exist_ok=True)
    path = os.path.join(subdir, f"{digest}{ext}")
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(content)
    return "/" + os.path.relpath(path).replace(os.sep, "/")


def _infer_ext(url: str, content_type: str) -> str:
    ct = content_type.split(";")[0].strip().lower()
    ct_map = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
        "video/mp4": ".mp4",
    }
    if ct in ct_map:
        return ct_map[ct]
    url_path = urllib.parse.urlparse(url).path
    _, dot, tail = url_path.rpartition(".")
    if dot and 2 <= len(tail) <= 5:
        return "." + tail.lower().split("?")[0]
    return ".bin"


# ------- callout mapping -------

_CALLOUT_MAP = {
    # Notion colors → Mintlify component
    "blue": "Note", "blue_background": "Note",
    "green": "Tip", "green_background": "Tip",
    "yellow": "Warning", "yellow_background": "Warning", "orange": "Warning", "orange_background": "Warning",
    "red": "Danger", "red_background": "Danger", "pink": "Danger", "pink_background": "Danger",
    "purple": "Info", "purple_background": "Info", "gray": "Info", "gray_background": "Info", "default": "Note",
}

def _callout_component(callout: dict) -> str:
    color = callout.get("color", "default")
    return _CALLOUT_MAP.get(color, "Note")


# ------- block serialization -------

class Serializer:
    def __init__(self, client: NotionClient, id_to_path: dict[str, str], images_root: str):
        self.client = client
        self.id_to_path = id_to_path
        self.images_root = images_root

    def render_page(self, node: PageNode, description: str, icon: str | None = None) -> str:
        """Render the full MDX (frontmatter + body) for one page.
        The AI-first layout (hide sidebar, hide search, fullscreen assistant on
        landing) is applied globally by docs/styles.css and docs/assistant-autoopen.js
        — Mintlify auto-loads any .css/.js in the content directory. We deliberately
        do NOT inject inline <style> or <script> tags here; Mintlify strips them
        during MDX processing."""
        frontmatter = self._frontmatter(node.title, description, icon)
        body = self._render_blocks(node.blocks, node.slug, indent=0)
        return frontmatter + "\n" + body.rstrip() + "\n"

    def _frontmatter(self, title: str, description: str, icon: str | None) -> str:
        lines = ["---",
                 f'title: "{_yaml_escape(title)}"',
                 f'description: "{_yaml_escape(description)}"',
                 f'mode: "{config.ARTICLE_MODE}"']
        if icon:
            lines.append(f'icon: "{icon}"')
        lines.append("---")
        return "\n".join(lines) + "\n"

    def _render_blocks(self, blocks: list[dict], page_slug: str, indent: int) -> str:
        out: list[str] = []
        i = 0
        n = len(blocks)
        while i < n:
            block = blocks[i]
            btype = block.get("type")
            if btype in ("bulleted_list_item", "numbered_list_item"):
                # Group consecutive list items of the same kind.
                group: list[dict] = []
                while i < n and blocks[i].get("type") == btype:
                    group.append(blocks[i])
                    i += 1
                out.append(self._render_list(group, btype, page_slug, indent))
                continue
            out.append(self._render_block(block, page_slug, indent))
            i += 1
        return "\n\n".join(x for x in out if x.strip())

    def _render_block(self, block: dict, page_slug: str, indent: int) -> str:
        btype = block.get("type")
        payload = block.get(btype, {})
        if btype == "paragraph":
            text = rich_text_to_md(payload.get("rich_text", []), self.id_to_path)
            return text if text.strip() else ""
        if btype == "heading_1":
            return "## " + rich_text_to_md(payload.get("rich_text", []), self.id_to_path)
        if btype == "heading_2":
            return "### " + rich_text_to_md(payload.get("rich_text", []), self.id_to_path)
        if btype == "heading_3":
            return "#### " + rich_text_to_md(payload.get("rich_text", []), self.id_to_path)
        if btype == "code":
            lang = payload.get("language", "text")
            text = "".join(s.get("plain_text", "") for s in payload.get("rich_text", []))
            return f"```{lang}\n{text}\n```"
        if btype == "callout":
            comp = _callout_component(payload)
            text = rich_text_to_md(payload.get("rich_text", []), self.id_to_path)
            return f"<{comp}>\n{text}\n</{comp}>"
        if btype == "quote":
            text = rich_text_to_md(payload.get("rich_text", []), self.id_to_path)
            return "\n".join(f"> {line}" for line in text.split("\n"))
        if btype == "divider":
            return "---"
        if btype == "image":
            return self._render_image(payload, page_slug)
        if btype == "video":
            return self._render_video(payload, page_slug)
        if btype == "bookmark":
            url = payload.get("url", "")
            cap = rich_text_to_md(payload.get("caption", []), self.id_to_path) or url
            return f'<Card title="{_attr_escape(cap)}" href="{_attr_escape(url)}" />'
        if btype == "toggle":
            title = rich_text_to_md(payload.get("rich_text", []), self.id_to_path)
            children = block.get("_children", [])
            inner = self._render_blocks(children, page_slug, indent + 1)
            return f'<Accordion title="{_attr_escape(title)}">\n{inner}\n</Accordion>'
        if btype == "table":
            return self._render_table(block, page_slug)
        if btype == "child_page":
            title = payload.get("title", "")
            target_id = canonical_id(block["id"])
            path = self.id_to_path.get(target_id)
            if path:
                url = re.sub(r"^docs/", "/", path).removesuffix(".mdx")
                return f"- [{title}]({url})"
            return f"- {title}"
        if btype in ("bulleted_list_item", "numbered_list_item"):
            # Occurs when a list item is a child of a toggle/table/etc. Emit as a single item.
            marker = "-" if btype == "bulleted_list_item" else "1."
            text = rich_text_to_md(payload.get("rich_text", []), self.id_to_path)
            return f"{marker} {text}"
        if btype in ("synced_block", "embed", "child_database", "link_preview", "unsupported"):
            return f"{{/* Skipped Notion block: {btype} */}}"
        return f"{{/* Unhandled Notion block: {btype} */}}"

    def _render_list(self, items: list[dict], btype: str, page_slug: str, indent: int) -> str:
        marker = "-" if btype == "bulleted_list_item" else "1."
        lines: list[str] = []
        pad = "  " * indent
        for it in items:
            payload = it.get(btype, {})
            text = rich_text_to_md(payload.get("rich_text", []), self.id_to_path)
            lines.append(f"{pad}{marker} {text}")
            for child in it.get("_children", []):
                rendered = self._render_block(child, page_slug, indent + 1)
                if rendered.strip():
                    lines.append("")
                    for line in rendered.split("\n"):
                        lines.append(f"{pad}  {line}")
        return "\n".join(lines)

    def _render_image(self, payload: dict, page_slug: str) -> str:
        url = payload.get("file", {}).get("url") or payload.get("external", {}).get("url", "")
        caption = rich_text_to_md(payload.get("caption", []), self.id_to_path)
        alt = caption or "image"
        if payload.get("type") == "file" and not url:
            return "{/* IMAGE NOT AVAILABLE: internal Notion attachment */}"
        if url.startswith("http"):
            local = _download_and_cache_image(url, self.images_root, page_slug)
            if local:
                if caption:
                    return f'<Frame caption="{_attr_escape(caption)}">\n  <img src="{local}" alt="{_attr_escape(alt)}" />\n</Frame>'
                return f'<Frame>\n  <img src="{local}" alt="{_attr_escape(alt)}" />\n</Frame>'
        return f"{{/* IMAGE NOT AVAILABLE: {url} */}}"

    def _render_video(self, payload: dict, page_slug: str) -> str:
        url = payload.get("external", {}).get("url") or payload.get("file", {}).get("url", "")
        if "youtube.com" in url or "youtu.be" in url:
            return f'<iframe width="100%" height="400" src="{_attr_escape(url)}" frameBorder="0" allowFullScreen />'
        if url.startswith("http"):
            local = _download_and_cache_image(url, self.images_root, page_slug)
            if local:
                return f'<Frame>\n  <video autoPlay muted loop>\n    <source src="{local}" />\n  </video>\n</Frame>'
        return f"{{/* VIDEO NOT AVAILABLE: {url} */}}"

    def _render_table(self, block: dict, page_slug: str) -> str:
        payload = block.get("table", {})
        has_header = payload.get("has_column_header", False)
        rows = block.get("_children", [])
        if not rows:
            return "{/* empty table */}"
        text_rows: list[list[str]] = []
        for row in rows:
            cells = row.get("table_row", {}).get("cells", [])
            text_rows.append([rich_text_to_md(cell, self.id_to_path) or " " for cell in cells])
        if not text_rows:
            return ""
        ncols = max(len(r) for r in text_rows)
        for r in text_rows:
            while len(r) < ncols:
                r.append(" ")
        lines: list[str] = []
        if has_header:
            lines.append("| " + " | ".join(text_rows[0]) + " |")
            lines.append("|" + "|".join(["---"] * ncols) + "|")
            body_rows = text_rows[1:]
        else:
            lines.append("| " + " | ".join([" "] * ncols) + " |")
            lines.append("|" + "|".join(["---"] * ncols) + "|")
            body_rows = text_rows
        for r in body_rows:
            lines.append("| " + " | ".join(r) + " |")
        return "\n".join(lines)


def _yaml_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')

def _attr_escape(s: str) -> str:
    return s.replace('"', '&quot;')


def fetch_block_children_recursively(client: NotionClient, blocks: list[dict]) -> None:
    """Populate a `_children` list on any block that has_children (needed for toggles, tables, nested lists)."""
    for block in blocks:
        if not block.get("has_children"):
            continue
        try:
            children = list(client.get_block_children(block["id"]))
        except Exception as e:
            print(f"[warn] could not fetch children of block {block['id']}: {e}")
            children = []
        block["_children"] = children
        fetch_block_children_recursively(client, children)


def extract_description(blocks: list[dict], id_to_path: dict[str, str]) -> str:
    """Grab the first paragraph as the SEO description; truncate."""
    for block in blocks:
        if block.get("type") == "paragraph":
            text = rich_text_to_md(block["paragraph"].get("rich_text", []), id_to_path)
            plain = re.sub(r"[*_`\[\]]|\(.*?\)", "", text).strip()
            if plain:
                if len(plain) > config.DESCRIPTION_MAX_LEN:
                    plain = plain[: config.DESCRIPTION_MAX_LEN - 1].rstrip() + "…"
                return plain
    return ""


def notion_icon(page: dict) -> str | None:
    icon = page.get("icon") or {}
    if icon.get("type") == "emoji":
        return icon.get("emoji")
    return None


def _iter_all_blocks(blocks: Iterable[dict]) -> Iterable[dict]:
    for b in blocks:
        yield b
        yield from _iter_all_blocks(b.get("_children", []))
