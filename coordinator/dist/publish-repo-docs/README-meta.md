# publish-repo-docs — Source-of-Truth for Claude-Central-authored Publish-Repo `docs/` Files

## What this directory is

This directory is the **Claude Central source-of-truth** for top-level files in the OSS
publish repo's `docs/` directory (`X:/coordinator-claude/docs/`) that we author here and
percolate outward.

**Today it controls exactly one file:**

- `agent-install.md` — the agent-facing install playbook (audience: Claude or another coding
  agent doing the install, not a human).

Every *other* top-level file in the publish repo's `docs/` (`README.md`, `architecture.md`,
`safety.md`, `customization.md`, `getting-started.md`, `ci-pipeline.md`, `contracts.md`,
`gitignore-policy.md`, `pretooluse-deny-contract.md`) is still **authored publish-repo-side**
and is NOT controlled here. They are listed in `.percolate-ignore` so the flat-mirror's
delete-not-in-source pass leaves them untouched — and `.percolate-ignore` is the
**authoritative** list: when a new top-level `docs/` file appears publish-repo-side, add it
*there* (this prose enumeration may lag). See that file's header for the mechanism.

**Edit `agent-install.md` here, not in the publish repo.** The publish repo is a percolation
target; direct edits there bypass the planning/review/doctrine pipeline and drift silently.

## Why this is a separate corner from `publish-repo-toplevel`

`publish-repo-toplevel/` flat-mirrors to the publish repo **root**; this corner flat-mirrors
to the publish repo's **`docs/` subdirectory**. They are distinct flat-mirror targets with
distinct dest paths, so they cannot share a source dir. `docs/wiki/` has its own dedicated
target (`coordinator-claude-toplevel-wiki`); this corner does NOT touch it — the depersonalize
hook here is maxdepth-1 scoped to avoid the overlap.

## Percolation

Sync source → publish repo via:

```
bash setup/publish.sh coordinator-claude-publish-repo-docs
```

A post-rsync depersonalize hook fires automatically on every sync
(`setup/percolate-hooks/coordinator-claude-publish-repo-docs/post-rsync/10-depersonalize.sh`),
removing persona names and local paths before any content reaches the publish repo. It is
maxdepth-1 scoped — top-level `docs/` files only, never the subdirectories owned by other targets.

## Naming note

This file is named `README-meta.md` (not `README.md`) to avoid colliding with the publish
repo's own `docs/README.md`, which is content, not meta-documentation. Both this file and
`docs/README.md` are protected by `.percolate-ignore`.

## Flat namespace

`dist/publish-repo-setup/`, `dist/publish-repo-toplevel/`, and `dist/publish-repo-docs/` are
siblings in a flat namespace under `dist/`. Future additions extend the flat list — do not
nest under an existing member.

## Doctrine reference

`docs/wiki/plugin-extraction-and-distribution.md § Publish-Repo Content Authoring`
