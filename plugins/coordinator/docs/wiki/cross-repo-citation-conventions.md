# Cross-Repo Citation Conventions

> How to cite file:line locations across the 5-repo install chain so successors can grep and find what you meant.

## Citation format

Cross-repo line citations use a repo qualifier:

```
<repo>:<path>:<line>
```

Examples:
- `project-rag:mcp/graph/extractor.py:2980`
- `coordinator-claude:plugins/coordinator-claude/coordinator/bin/verify-coverage.js:142`
- `holodeck-control:src/tools/manage_blueprint.py:51`

## Why bare `<path>:<line>` is wrong

Bare `<path>:<line>` is ambiguous across the install chain — multiple peer repos can have a file at the same relative path (e.g. `bin/setup.sh`, `docs/wiki/cleanup-sweep-hazards.md`). A successor grepping a bare citation either:

- finds the wrong file in the local repo and acts on stale lines, or
- finds nothing and assumes the citation is stale, when it actually pointed elsewhere.

The repo qualifier fixes this. Grep then targets the right repo.

## When to qualify

- ALWAYS qualify in handoffs, lessons, plans, and decision records that may be read from a different repo.
- Optional in commit messages within a single repo (context is implicit).
- ALWAYS qualify in `~/.claude/tasks/coordinator-improvement-queue.md` (cross-repo by construction).

## Migration patterns — one-shot cross-repo deletion

When dispatching a one-shot deletion across peer repos (e.g. "delete file `F` from all peer repos that reference it"), run a **consumer audit BEFORE dispatch**:

1. Grep each peer repo for references to `F` (imports, file:line citations, doc backlinks).
2. Enumerate consumers per repo in the dispatch brief.
3. Plan the deletion order so consumers are migrated *before* the producer is removed.

**Why:** cross-repo dispatch races make post-hoc recovery painful. Once `F` is deleted in repo A and repo B's reference breaks, the recovery requires restoring `F` (or its replacement) and re-dispatching consumer migration. Auditing first turns a fix-forward race into an ordered migration.

Format consumer audit in the dispatch brief as:

```
Consumers of F (audited 2026-MM-DD):
- project-rag:foo/bar.py:120 — imports F.helper
- coordinator-claude:plugins/.../baz.md:45 — citation backlink
```

Then the executor knows the full surface before it removes anything.

## Cross-repo provenance in commit messages

When a commit in repo A is motivated by, fixes, or supersedes work in peer repo B, name the peer in the commit body — not just the local-repo file. Bare local citations strand the next reader on the wrong grep.

Format:

```
<subject>

Cross-repo: <peer-shortname>:<path>:<line> — <one-line reason>
```

Example:

```
coordinator-safe-commit: tolerate untracked siblings under --scope-from

Cross-repo: project-rag:bin/run-enrichment.sh:88 — concurrent enricher leaves
sibling .tmp files that --scope-from must skip, not abort on.
```

`git log --grep="Cross-repo:"` then surfaces the cross-stack work; without the marker, peer-repo motivation evaporates as soon as the active branch is squashed.

## Vendor / submodule SHA pins

When a peer repo is vendored (submodule, copy-in, `git subtree`, manifest pin), cite **commit SHA**, not branch name. Branch names move silently; the SHA is what the build actually consumed.

```yaml
peer: project-rag
pinned_sha: 9d682c51
pinned_at: 2026-05-14
reason: verify-coverage hard-gate landed here; downstream consumes the gate output schema
```

Pinning by branch (`main`, `work/...`) is a re-bisect hazard — a future drift can't be located to a specific commit. SHA pins also make `bin/sync-plugin-wiki.sh` and similar mirror tools idempotent.

## Coordination memo BEFORE shipping cross-repo changes

If a change in repo A will land before/with consumers in peers B and C, write a one-line coordination memo in `~/.claude/tasks/coordinator-improvement-queue.md` or the active handoff *before* the producing commit — not after. The memo names the producer SHA (once landed), the consumer repos, and the migration order.

This is the same shape as the consumer-audit-before-deletion rule above, but for additive changes: schema bumps, manifest field additions, output format changes. Producer-first shipping without the memo creates a window where peer repos read against the old contract and don't know it.

**Stop signal:** if a peer-repo consumer would silently degrade (no error, wrong output) under the new producer, the memo MUST also include `pre-flight: <command>` — a one-liner the EM in the peer repo can run to confirm compatibility before pulling.

## Dependency claims need grep evidence, not memory

Scout briefs that assert "repo A depends on repo B for X" must cite **at least one grep hit** (import line, manifest entry, file:line reference) — not author recall. Memory-cited cross-repo dependencies hallucinate at the same rate as memory-cited API signatures: high enough that the downstream plan ships against a phantom contract.

Format the citation inline in the brief:

```
project-rag depends on coordinator-claude for the safe-commit helper:
- project-rag:bin/run-enrichment.sh:42 — invokes coordinator-safe-commit
- project-rag:tests/test_enrichment.py:88 — mocks coordinator-safe-commit shim
```

Zero-hit claims are not dependencies; they're hypotheses. Mark as such or drop.

## Manifest paths: grep the repo, not the installed tree

When verifying a manifest field (skill path, agent path, hook script) lives where the manifest claims, grep the **source repo's working tree**, not the installed `~/.claude/plugins/` copy. The installed copy is downstream of `publish.sh` and may lag the repo by days; the manifest contract is against repo paths.

```bash
# Right — verifying skill manifest against source
rg "^path:" plugins/coordinator-claude/coordinator/skills/*/SKILL.md

# Wrong — verifying against the installed mirror
rg "^path:" ~/.claude/plugins/coordinator-claude/coordinator/skills/*/SKILL.md
```

Installed-tree verification masks pre-publish drift: a manifest that's wrong in the repo but right in the install will pass the wrong-tree check and ship broken.

## Single-token path format for cross-repo integrators

When a downstream integrator (scout, executor, or worker) needs to act on a file across multiple repos, format paths as a single token `<repo>:<path>` — not split across columns or stitched from separate fields. Integrators that split-and-rejoin lose alignment under concurrent fan-out.

```
Right: coordinator-claude:plugins/coordinator-claude/coordinator/skills/learn-lessons/SKILL.md
Wrong: repo=coordinator-claude  path=plugins/.../SKILL.md  (two fields, must rejoin)
```

The line-citation form `<repo>:<path>:<line>` is the same shape with the line tail appended. Tools that grep for the qualifier prefix work uniformly on both.

## Sentinels carry preconditions inline

Cross-repo sentinel blocks (auto-generated regions marked with `<!-- BEGIN ... -->` / `<!-- END ... -->`) MUST document their refresh preconditions inside the sentinel — not in a sibling wiki the maintainer might not read.

Required inline:
- Generator script path (repo-qualified if cross-repo)
- Input source paths (what the generator reads)
- Refresh trigger (which `/update-docs` phase, or "manual: `<command>`")
- Last-refreshed timestamp

Without inline preconditions, sentinel blocks become orphan auto-generated regions that nobody knows how to regenerate. The block must self-document the contract; sibling docs decay independently.

```markdown
<!-- BEGIN repo-registry-candidates
     Generator: ${CLAUDE_PLUGIN_ROOT}/bin/decode-claude-projects-dir.sh
     Source: ~/.claude/projects/
     Refresh: /update-docs Phase 14 (cwd-gated, ~/.claude only)
     Last refreshed: 2026-05-14
-->
...candidates...
<!-- END repo-registry-candidates -->
```

