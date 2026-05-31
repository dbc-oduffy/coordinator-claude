---
title: Slash-command helper extraction discipline
created: 2026-05-27
type: doctrine
related:
  - plugins/coordinator-claude/coordinator/agents/code-reviewer.md
  - plugins/coordinator-claude/coordinator/docs/wiki/install-surface-completeness.md
---

<!-- spec-backlink: archive/specs/2026-05-27-cqcs-cluster2-review-pipeline-calibration.md § Entry 121 — code-reviewer path-resolution sub-lens -->

# Slash-Command Helper Extraction Discipline

## Purpose

When a coordinator command's body is mechanically extracted into shell helper scripts
(`commands/lib/**.sh`, `lib/**.sh`, or any sourced helper), two defect classes emerge
reliably that survive a clean diff read: **invented variable names** and **dev-tree-only
path resolution**. This wiki names both, explains the failure mode, and gives the
verification pattern.

The `code-reviewer` agent's **Spec completion lens → Path-resolution on extracted helpers**
sub-lens enforces this discipline at review time. This wiki is the RAG-bait authority
surface that lens links delegates to.

## Defect class 1 — Invented variable names from mechanical extraction

Mechanical extraction rewrites inline logic into parameterized functions. The rewriter
must invent parameter names and local variable names that did not exist in the original
inline body. Two failure shapes:

1. **Undeclared variable references.** The rewriter uses `$SOME_VAR` that was never
   declared in the helper — it was implicit context in the original inline body (e.g., a
   variable set earlier in the calling script that the helper now receives as a positional
   but the positional was omitted). Result: the helper silently expands to empty string
   or fails on `set -u` environments.

2. **Unbalanced quoting.** Inline bodies frequently use bareword variable references that
   work in the original context. When extracted, the quoting discipline changes (e.g.,
   the helper is sourced from a different shell or called with `bash -c`), and unbalanced
   quotes that were benign inline cause parse failures.

**Verification: `bash -n` over every touched `*.sh`.** Syntax errors from both classes
surface under `bash -n` (dry-run parse, no execution). Run it over every file in the
extraction set — not just the new helpers but also the calling scripts, since callers
change when helpers are introduced. Missing `bash -n` evidence on a multi-helper
extraction is **P2** in the code reviewer's severity scale.

## Defect class 2 — Dev-tree vs. marketplace-install-layout path resolution

The coordinator plugin runs in two environments:

- **Dev-tree:** the plugin source lives at `~/.claude/plugins/coordinator-claude/` and
  `${CLAUDE_PLUGIN_ROOT}` resolves to that directory.
- **Marketplace install:** the plugin is installed at
  `~/.claude/plugins/<marketplace-slug>/<plugin-slug>/` — a different path depth.

A helper that computes a path as `${CLAUDE_PLUGIN_ROOT}/commands/lib/some-helper.sh`
may work in-repo during development but fail post-install because `${CLAUDE_PLUGIN_ROOT}`
resolves to a different root. The failure is **silent** — the path just does not exist at
runtime; no syntax error, no lint warning.

**Common pattern to check:** any `${CLAUDE_PLUGIN_ROOT}`-relative path in an extracted
helper must be verified to resolve correctly under the actual marketplace install layout.
The safe pattern is: construct paths relative to the helper's own `$( cd "$(dirname
"${BASH_SOURCE[0]}")" && pwd )` rather than trusting that an ambient
`${CLAUDE_PLUGIN_ROOT}` is set to the plugin root. A path-prefix that resolves in
dev-tree but not install-layout is **P1** — it ships broken to every installer other than
the author.

## Smoke-test loop pattern

For extraction waves that touch many helpers, a lightweight smoke-test loop catches both
classes before commit:

```bash
# Syntax check every new/modified helper
find commands/lib/ lib/ -name '*.sh' -newer <reference-file> | xargs bash -n

# Install-layout path check: resolve each ${CLAUDE_PLUGIN_ROOT}-relative path
# from a simulated install root (substitute your plugin's install path)
SIMULATED_ROOT="$HOME/.claude/plugins/coordinator/coordinator-claude"
grep -rh 'CLAUDE_PLUGIN_ROOT' commands/lib/ lib/ | \
  sed 's/.*CLAUDE_PLUGIN_ROOT\///' | \
  sed 's/[^a-zA-Z0-9_./\-].*//' | \
  while read -r rel; do
    [ -e "${SIMULATED_ROOT}/${rel}" ] || echo "MISSING in install layout: $rel"
  done
```

The loop is not required infrastructure — it is a reference pattern for an extraction
author to run locally before committing. A CI-grade harness tying `${CLAUDE_PLUGIN_ROOT}`
to a fully simulated marketplace install layout is a separate infra workstream (see
`archive/specs/2026-05-27-cqcs-cluster2-review-pipeline-calibration.md` § Out-of-scope).

## Review surface

The **Path-resolution on extracted helpers** sub-lens in `agents/code-reviewer.md`
§ Spec completion lens is the enforcement point. The lens fires when:
- the diff extracts slash-command bodies into helper scripts, OR
- the diff introduces `${CLAUDE_PLUGIN_ROOT}` / plugin-root path interpolation.

Missing `bash -n` evidence on a multi-helper extraction → **P2**.
A path-prefix that resolves in dev-tree but not install-layout → **P1**.

Empirical basis: 2026-05-21 slash-command-helper-extraction wave.
