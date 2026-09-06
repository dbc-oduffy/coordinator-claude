# Versioning Convention — coordinator-claude

> The authority named by `workweek-complete.md` Step 10 ("if the repo has
> `docs/wiki/versioning-convention.md`, that doc is the authority for *which*
> number/artifact is the canonical product version and *how* to bump it"). This
> repo has four version namespaces; without this doc the cut ceremony guessed,
> and the surfaces drifted to plugin.json 2.7.1 / marketplace.json 2.1.1 /
> CHANGELOG 2.8.1 / git tag v2.7.0 by 2026-06-22. This doc names the SSOT and the
> invariant; claude-klabauter `coordinator/bin/check-version-consistency.py`
> mechanically enforces it.

## The SSOT

**`coordinator/.claude-plugin/plugin.json` `version` is THE coordinator-claude
product version.** It is the number a user receives when they install the
`coordinator` plugin from the marketplace. Everything else tracks it.

## The four surfaces and the invariant

| Surface | Path (bundle-root-relative) | Role | Must equal SSOT? |
|---|---|---|---|
| **plugin.json** | `coordinator/.claude-plugin/plugin.json` `.version` | SSOT — the installed plugin version | — (it *is* the SSOT) |
| **marketplace.json** | `.claude-plugin/marketplace.json` `.metadata.version` | Catalog manifest version | **Yes** (PM decision: tracks the plugin version — one number to reason about) |
| **CHANGELOG** | `CHANGELOG.md` latest `## [X.Y.Z]` released section | Human release record | **Yes** (latest *released* section; `[Unreleased]` is excluded) |
| **git tag** | latest `v*` | Immutable release marker (OSS publish repo only) | **Advisory** — `~/.claude` is `source_is_live` and never tagged; the OSS repo IS tagged at `/merging-to-main` |

**Invariant (steady-state — it holds *between* releases, not only at cut):**

```
plugin.json.version == marketplace.json.metadata.version == latest-released-CHANGELOG-section
```

Between releases, plugin.json sits at the last shipped version and `[Unreleased]`
accumulates pending notes — the invariant still holds because the oracle is the
latest *released* `## [X.Y.Z]`, not `[Unreleased]`.

## How a bump moves all surfaces together

A release cut is a single atomic version move. In one commit:

1. CHANGELOG: `## [Unreleased]` → `## [X.Y.Z] — <date>` (and open a fresh empty `[Unreleased]`).
2. `coordinator/.claude-plugin/plugin.json` `.version` → `X.Y.Z`.
3. `.claude-plugin/marketplace.json` `.metadata.version` → `X.Y.Z`.
4. (At `/merging-to-main`, OSS repo only) tag `vX.Y.Z` + GitHub release.

Never move one surface without the others. The cut ceremony (`workweek-complete.md`
Step 10) stamps all of 1–3 and then runs the gate before proceeding to merge.

## Enforcement

Claude-klabauter `coordinator/bin/check-version-consistency.py` asserts the invariant, fail-loud, in both the
meta-repo source layout and the flat OSS publish layout (paths resolved relative
to `marketplace.json`). It is wired in two places so drift cannot ship:

- **`workweek-complete.md` Step 10** — after the bump, before `/merging-to-main`.
- **`setup/publish.sh`** — pre-flight; a percolation refuses to push a source tree
  whose surfaces disagree (complements the existing
  `check_marketplace_version_regression` non-regression gate in
  `setup/lib/percolate-gate.sh`).

Run it manually any time (claude-klabauter): `python coordinator/bin/check-version-consistency.py [--check-tag]`.

## Why marketplace.json tracks the plugin version

`marketplace.json` `metadata.version` is conceptually a *catalog* version (it
could bump when the plugin roster changes). The 2026-06-22 PM decision is to
collapse that axis: it always equals the coordinator plugin version. This removes
a whole independent drift surface at the cost of bumping it on coordinator-only
releases — judged worthwhile because roster changes are rare and a second
semver namespace was exactly what drifted.
