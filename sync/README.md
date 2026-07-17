# Notion → Mintlify sync worker

Syncs published HackerRank KB articles from Notion to this repo as MDX, so
Mintlify can render them.

## What it does

- Walks the Notion page trees starting from the roots configured in
  `sync/config.py` (currently `Screen` and `Interviews`).
- Follows both `child_page` blocks *and* Notion page URLs referenced from
  rich text (mentions or hyperlinks), so pages linked from a manual index
  are still synced.
- Converts each page's blocks to Mintlify MDX (`docs/<section>/…/<slug>.mdx`).
- Downloads embedded images to `images/<slug>/<sha1>.<ext>` (content-addressable,
  so re-syncing an unchanged image is a no-op).
- Regenerates the `navigation.groups` array in `docs.json` to match the tree.
- Tracks per-page `last_edited_time` in `.sync-state.json` for incremental sync.
- Deletes MDX files whose Notion source has been removed since the last run.

## Running locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r sync/requirements.txt
NOTION_API_KEY=<token> .venv/bin/python -m sync.sync
```

Flags:
- `--dry-run` — walk the tree and log what would change, without writing files.
- `--force` — re-sync every page regardless of `last_edited_time`.

## Running in CI

`.github/workflows/sync-notion.yml` runs the sync every 30 minutes and commits
any changes back to the repo. Store the Notion integration token in a repo
secret named `NOTION_API_KEY`.

## Files

- `sync/config.py` — root page IDs, article mode, retry policy.
- `sync/notion_client.py` — thin REST client with retry/backoff on 429/5xx.
- `sync/notion_extractor.py` — BFS tree walker + slug/id helpers.
- `sync/mdx_serializer.py` — block → MDX conversion + image download.
- `sync/sync.py` — orchestrator (two-pass: walk tree, then generate MDX).

## Known limitations

- Notion internal `file://` attachment images cannot be downloaded via the
  standard integration API. They are replaced with an HTML comment
  `<!-- IMAGE NOT AVAILABLE: … -->` and logged as a warning.
- Notion blocks that don't have a clean Mintlify equivalent (`embed`,
  `synced_block`, `child_database`, `link_preview`, `unsupported`) are
  emitted as HTML comments so the content remains visible in the raw MDX.
- If an author renames a Notion page, the slug changes → the old MDX file
  is deleted and a new one is created. External links to the old URL will
  break. Stable slugs would require adding a `Slug` property (needs a
  database, not a nested page tree).
