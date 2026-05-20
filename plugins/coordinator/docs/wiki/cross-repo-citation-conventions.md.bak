# Cross-Repo Citation Conventions

> How to cite file:line locations across the 5-repo install chain so successors can grep and find what you meant.

## Citation format

Cross-repo line citations use a repo qualifier:

```
<repo>:<path>:<line>
```

Examples:
- `project-rag:mcp/graph/extractor.py:2980`
- `coordinator-claude:plugins/coordinator/bin/verify-coverage.js:142`
- `holodeck-control:src/tools/manage_blueprint.py:51`

## Why bare `<path>:<line>` is wrong

Bare `<path>:<line>` is ambiguous across the install chain — multiple peer repos can have a file at the same relative path (e.g. `bin/setup.sh`, `docs/wiki/cleanup-sweep-hazards.md`). A successor grepping a bare citation either:

- finds the wrong file in the local repo and acts on stale lines, or
- finds nothing and assumes the citation is stale, when it actually pointed elsewhere.

The repo qualifier fixes this. Grep then targets the right repo.

## When to qualify — two co-equal rules

**Cross-repo citations** (handoffs, lessons, plans, decision records that may be read from a different repo) — ALWAYS qualify with `<repo>:<path>:<line>`. The qualifier is for human disambiguation across the install chain; no automated rewrite covers this case.

**Intra-coordinator citations** in wiki/skill/command/agent prose under `plugins/coordinator/` may use the dev-tree-rooted path (`plugins/coordinator/<...>`) directly. The publish-time hook (`bin/depersonalize-for-publish.sh`, invoked from `setup/percolate-hooks/coordinator-claude/post-rsync/10-depersonalize.sh`) normalizes these to the publish-tree form (`plugins/coordinator/<...>` or `plugins/<plugin>/<...>`) idempotently. Authors do not qualify these — the rewrite is the contract. (Note: this means dev-form paths inside fenced code blocks in this wiki also get rewritten. To preserve a literal dev-form path for documentation purposes, use prose framing — `the plugins/coordinator-claude/... form` — rather than a fenced code block.)
<!-- Review: code-reviewer — folded the code-block caveat inline so an author who stops at the contract statement still sees it. Previously the note was a separate paragraph after "Additional qualifications". -->

Additional qualifications:
- Optional in commit messages within a single repo (context is implicit).
- ALWAYS qualify in `~/.claude/tasks/coordinator-improvement-queue.md` (cross-repo by construction).

## Plugin-wiki vs publish-native-wiki authoring — a third rule pair

**Plugin-wiki authoring vs publish-repo-wiki authoring is a third rule pair.** Plugin-side wikis are authored against meta-repo paths and persona names; the publish pipeline rewrites both at sync time. Publish-side wikis (allowlisted) are authored against publish-tree paths and depersonalized names directly — they bypass the sync pipeline's rewrite layer because they were never in dev form. When citing across the boundary: a plugin wiki referring to a publish-native wiki cites the post-sync path (`docs/wiki/task-tier-guidance.md` from the publish-repo root); a publish-native wiki referring to a plugin wiki cites the post-sync path on the publish side (`plugins/coordinator/docs/wiki/X.md`).

The allowlist (`setup/percolate-hooks/coordinator-claude-toplevel-wiki/post-rsync/publish-native-allowlist.txt`) is the registry of files with publish-native authorship. Files not on the allowlist are treated as plugin-sourced and will be overwritten on the next sync. See `docs/wiki/plugin-extraction-and-distribution.md` § Auxiliary Sync for the full mechanism.

Spec backlink: `docs/plans/2026-05-18-publish-repo-toplevel-wiki-sync.md` § Chunk 3.

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
rg "^path:" plugins/coordinator/skills/*/SKILL.md

# Wrong — verifying against the installed mirror
rg "^path:" ~/.claude/plugins/coordinator/skills/*/SKILL.md
```

Installed-tree verification masks pre-publish drift: a manifest that's wrong in the repo but right in the install will pass the wrong-tree check and ship broken.

## Single-token path format for cross-repo integrators

When a downstream integrator (scout, executor, or worker) needs to act on a file across multiple repos, format paths as a single token `<repo>:<path>` — not split across columns or stitched from separate fields. Integrators that split-and-rejoin lose alignment under concurrent fan-out.

```
Right: coordinator-claude:plugins/coordinator/skills/learn-lessons/SKILL.md
Wrong: repo=coordinator-claude  path=plugins/.../SKILL.md  (two fields, must rejoin)
```

The line-citation form `<repo>:<path>:<line>` is the same shape with the line tail appended. Tools that grep for the qualifier prefix work uniformly on both.

## Grep ratified cross-repo DRs before authoring a new hookspec

Before drafting a new hookspec or seam interface, grep the peer-repo ratified DRs and coordination memos from recent days. Authoring without this check produces collisions: e.g., drafting `project_rag_declare_kind_sources` while a peer repo's already-ratified `project_rag_register_corpus_provider` (D-5) covers the same seam. The prior-art-checker catches the collision after the draft exists; this discipline catches it before. One grep run against `docs/decisions/` and `tasks/handoffs/` in each peer repo is sufficient.

## Donor-module excision: check consumer imports before celebrating the split

After excising a donor module from a repo, grep consumers for `from <excised_module>.` imports before declaring the split complete. Module-top imports break the consumer at load time, not at first use — a green unit-test suite on the donor side does not prove the consumer is intact. The post-split smoke is a green import test run against the consumer (`python -c "import <consumer_module>"`), not just the donor. Source: 2026-05-17 project-rag-ue-addon excision post-mortem.

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

## Sibling-layout convention for vendored code

> **2026-05-19 amendment — runtime preference order.** The MUST-use-sibling-layout contract codified below is the port-time cleanup discipline (absolute-path sweep at extraction). At runtime, machine-local is the preferred primary discovery mechanism, with sibling-relative as the documented fallback (belt-and-suspenders). The two are NOT co-equal: registry first, sibling second, because not every script can run on sibling convention (daemon-invoked tooling with no sibling-relative anchor; scripts vendored into one repo but invoked from another; deterministic-location-needing consumers). The ad-hoc env-var opt-in for peerless installs (e.g. `HOLODECK_REPO_ROOT`) is superseded by the `MACHINE_LOCAL_<KEY>` override on the unified registry contract. See `machine-local-registry.md` and `plugin-extraction-and-distribution.md § 11`.

**Incomplete migrations leak absolute paths into vendored code; `../sibling/...` is the contract for sibling repos.** When a repo is split into peer/sibling repos that live in the same parent directory (e.g. `<drive>:/project-rag/` and `<drive>:/project-rag-ue-addon/` — `X:/`, `C:/`, `D:/` etc. are all illustrative; substitute the host's actual root prefix), any cross-repo reference in vendored code, scripts, or docs MUST use a `../<sibling-repo-name>/...` relative path — never an absolute path like `<drive>:/...` or `/c/Users/.../`.

Two reasons:

- (a) Absolute paths break for any developer with a different layout (CI, peer machines, anyone else picking up the repo).
- (b) Absolute paths fail the depersonalize/sanitize hooks at publish time even when those hooks know about the substring keys.

**Port-time discipline:** at every repo split, grep the vendored tree for absolute repo prefixes (`<drive>:/`, `/c/`, `/Users/`, `/home/` — substitute the host's actual root prefix so e.g. `C:/`, `D:/` matches aren't missed) and rewrite to `../sibling/...`. The sibling-layout convention is the contract — document it in the source repo's README so consumers don't fight it.

Source: `project-rag-ue-addon:tasks/lessons.md:121` (2026-05-16).

Runtime alternative: for consumers that cannot rely on sibling-layout (triangular graphs, multi-drive setups, deterministic-location requirements), prefer the machine-local registry — see `machine-local-registry.md` and `plugin-extraction-and-distribution.md § 11` for the full discovery preference order.

## Peerless installs — env-var opt-in for peer-repo paths

Most installs place `~/.claude`, the publish target (`X:/coordinator-claude`), and peer dev repos (`E:/dev/claude-unreal-holodeck`, etc.) such that sibling-relative paths (`$PLUGIN_ROOT/../../claude-unreal-holodeck/...`) resolve correctly. Sync scripts default to this layout.

The `~/.claude/` install on a Windows user-profile root (`C:\Users\<name>\.claude\`) is structurally peerless: there is no sibling-capable parent, and no companion dev folder lives next to it. Sync scripts that assume a sibling peer silently skip verification on this install (skip-if-absent guard — looks fine, never actually checks the peer copy).

**Rule:** keep sibling-relative as the default in scripts (matches every normal-layout deployment). Deviant installs opt in via an explicit env var:

```bash
# Default: sibling-relative (correct for most installs)
HOLODECK_REPO_ROOT="${HOLODECK_REPO_ROOT:-../claude-unreal-holodeck}"

# Override for peerless installs (e.g. C:/-rooted ~/.claude):
# export HOLODECK_REPO_ROOT=/x/claude-unreal-holodeck
```

**Do NOT rewrite the sibling default in scripts that ship to normal-layout deployments** — fixing the C:/ edge case by hardcoding an absolute path breaks what already works everywhere else.

Source: `tasks/lessons.md` § "C:/-rooted `~/.claude` is structurally peerless" (2026-05-18, claude-coordinator).

