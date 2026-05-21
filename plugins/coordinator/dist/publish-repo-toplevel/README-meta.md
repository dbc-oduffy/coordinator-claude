# publish-repo-toplevel — Source-of-Truth for Publish-Repo Top-Level Files

<!-- spec backlink: docs/plans/2026-05-21-back-percolate-publish-repo-orphans.md § Chunk 2 -->

## What this directory is

This directory is the **Claude Central source-of-truth** for the eight top-level files that
appear at the root of the OSS publish repo (`X:/coordinator-claude/`):

- `README.md` — user-facing project README
- `CHANGELOG.md` — release history
- `CONTRIBUTING.md` — contributor guide
- `CODE_OF_CONDUCT.md` — community standards
- `COMMERCIAL.md` — commercial licensing terms
- `PRIVACY.md` — privacy policy
- `SECURITY.md` — security disclosure policy
- `LICENSE` — OSS license (no extension)

**Edit these files here, not in the publish repo.** The publish repo is a percolation target;
direct edits there bypass the planning/review/doctrine pipeline and drift silently.

## Percolation

Sync source → publish repo via:

```
bash setup/publish.sh coordinator-claude-publish-repo-toplevel
```

A post-rsync depersonalize hook fires automatically on every sync, removing persona names
and local paths before any content reaches the publish repo.

## Naming note

This file is named `README-meta.md` (not `README.md`) to avoid colliding with the
publish-repo's user-facing `README.md`, which is content, not meta-documentation.

## Flat namespace

`dist/publish-repo-setup/` and `dist/publish-repo-toplevel/` are siblings in a flat
namespace under `dist/`. Future additions (e.g. `dist/publish-repo-workflows/`) extend
the flat list — do not nest under an existing member.

## Doctrine reference

`docs/wiki/plugin-extraction-and-distribution.md § Publish-Repo Content Authoring`
