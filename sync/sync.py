"""Notion → Mintlify sync orchestrator.

Two-pass:
  Pass 1: BFS-walk both root pages, build id → git_path map.
  Pass 2: For each page changed since last sync, fetch nested block children,
          render MDX, and write to Git.

Also regenerates docs.json navigation from the walked tree, and removes MDX
files for pages that have disappeared from Notion since the last sync.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from . import config
from .notion_client import NotionClient
from .notion_extractor import PageNode, walk_tree, canonical_id
from .mdx_serializer import (
    Serializer,
    extract_description,
    fetch_block_children_recursively,
    notion_icon,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


def load_state() -> dict:
    p = REPO_ROOT / config.STATE_FILE
    if not p.exists():
        return {"pages": {}}
    return json.loads(p.read_text())


def save_state(state: dict) -> None:
    p = REPO_ROOT / config.STATE_FILE
    p.write_text(json.dumps(state, indent=2, sort_keys=True))


def build_docs_json_navigation(nodes: dict[str, PageNode]) -> list[dict]:
    """Regenerate the docs.json `navigation.groups` array from the walked tree."""
    root_ids = {canonical_id(r["page_id"]): r for r in config.ROOTS}

    # Group pages by root_slug and depth
    groups_out: list[dict] = []
    for r in config.ROOTS:
        rid = canonical_id(r["page_id"])
        pages_in_root = [
            n for n in nodes.values()
            if n.root_slug == r["slug"] and n.page_id != rid
        ]
        pages_in_root.sort(key=lambda n: (n.depth, n.order, n.slug))
        page_paths = [n.git_path.removesuffix(".mdx") for n in pages_in_root]
        # If the root itself has body content, include its index.mdx first
        root_node = nodes.get(rid)
        if root_node and root_node.blocks:
            page_paths.insert(0, root_node.git_path.removesuffix(".mdx"))
        groups_out.append({"group": r["group"], "pages": page_paths})
    return groups_out


def update_docs_json(nodes: dict[str, PageNode]) -> None:
    p = REPO_ROOT / "docs.json"
    docs = json.loads(p.read_text())
    docs["navigation"]["groups"] = build_docs_json_navigation(nodes)
    p.write_text(json.dumps(docs, indent=2) + "\n")


def sync(dry_run: bool = False, force: bool = False) -> None:
    client = NotionClient()
    print(f"[sync] walking Notion tree from {len(config.ROOTS)} root(s)…")
    nodes = walk_tree(client, config.ROOTS)
    print(f"[sync] discovered {len(nodes)} page(s)")

    # Build id → git_path map for link rewriting
    id_to_path = {pid: node.git_path for pid, node in nodes.items()}

    state = load_state()
    prev = state.get("pages", {})
    updated, created, skipped, failed = 0, 0, 0, 0

    images_root = str(REPO_ROOT / config.IMAGES_DIR)
    os.makedirs(images_root, exist_ok=True)

    # Track which pages we visit this run (for deletion detection).
    seen_ids: set[str] = set()

    for pid, node in nodes.items():
        seen_ids.add(pid)
        prev_entry = prev.get(pid, {})
        prev_time = prev_entry.get("last_edited_time")
        needs_sync = force or prev_time != node.last_edited_time or not (REPO_ROOT / node.git_path).exists()
        if not needs_sync:
            skipped += 1
            continue

        try:
            # Fetch nested children (needed for toggles, tables, nested lists)
            fetch_block_children_recursively(client, node.blocks)

            # Fetch page metadata again for icon (walk_tree already got last_edited_time via get_page)
            page_meta = client.get_page(pid)
            icon = notion_icon(page_meta)

            serializer = Serializer(client, id_to_path, images_root)
            description = extract_description(node.blocks, id_to_path)
            mdx = serializer.render_page(node, description, icon)

            out_path = REPO_ROOT / node.git_path
            out_path.parent.mkdir(parents=True, exist_ok=True)
            existed = out_path.exists()
            if dry_run:
                print(f"[dry-run] would write {node.git_path} ({len(mdx)} chars)")
            else:
                out_path.write_text(mdx)
                print(f"[sync] {'update' if existed else 'create '} {node.git_path}  ({node.title!r})")
            if existed:
                updated += 1
            else:
                created += 1

            state["pages"][pid] = {
                "title": node.title,
                "git_path": node.git_path,
                "last_edited_time": node.last_edited_time,
            }
        except Exception as e:
            print(f"[error] failed to sync {pid} ({node.title!r}): {e}")
            failed += 1

    # Deletion detection
    deleted = 0
    for pid in list(prev.keys()):
        if pid not in seen_ids:
            entry = prev[pid]
            gp = entry.get("git_path")
            if gp:
                path = REPO_ROOT / gp
                if path.exists() and not dry_run:
                    path.unlink()
                    print(f"[sync] delete {gp}  (removed from Notion)")
                deleted += 1
            state["pages"].pop(pid, None)

    # Regenerate docs.json navigation
    if not dry_run:
        update_docs_json(nodes)
        save_state(state)

    print(f"[sync] done — created={created}, updated={updated}, skipped={skipped}, deleted={deleted}, failed={failed}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Notion pages to Mintlify MDX")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing files")
    parser.add_argument("--force", action="store_true", help="Re-sync all pages regardless of last_edited_time")
    args = parser.parse_args()
    sync(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    main()
