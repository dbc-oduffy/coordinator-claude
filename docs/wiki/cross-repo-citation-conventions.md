# Cross-Repo Citation Conventions

> How to cite file:line locations across the 5-repo install chain so successors can grep and find what you meant.

## Citation format

Cross-repo line citations use a repo qualifier:

```
<repo>:<path>:<line>
```

Examples:
- `project-rag:mcp/graph/extractor.py:2980`
- `claude-klabauter:coordinator/bin/verify-coverage:142` (executable surface migrated from DoE-claude, commit b644d5a9)
- `example-game-repo-control:src/tools/manage_blueprint.py:51`

**Foreign spec-backlink id form.** A spec-backlink citing a peer repo's plan or deliverable uses the minted id, repo-qualified: `<repo>:pln-<slug>-<hash>` / `<repo>:dlv-<slug>-<hash>` — e.g. `claude-klabauter:pln-claude-klabauter-deliverable-spine-fact-a1b2c3`. This composes with the `<repo>:<path>:<line>` form above without ambiguity: no repo-relative path begins `pln-`/`dlv-`, so the segment after the colon disambiguates itself. It is **not** the `<repo>@<sha>` vendor-pin form below (§ Vendor / submodule SHA pins) — that form is scoped to build-consumed SHAs, a different convention entirely. `pln-` is preferred over `dlv-` at authoring time (`dlv-` is group-stamped across plan/handoff/completion-entry and can be ambiguous; `plan_id` is plan-scoped) — see `rag-bait-conventions.md § 3` for the full rule.

**What the id form does NOT cover.** Only plans and deliverables mint an id. A spec-backlink citing
a wiki page, memo, roadmap `OVERVIEW.md`, or sidecar stays in path form, pointed where the file
lives NOW (`coordinator/docs/wiki/…`, `cross-repo/archive/…` once actioned,
`archive/specs/<YYYY-MM>/…` once archived). A cited plan lacking `plan_id` gets one minted instead —
archival is the event the id survives. A citation resolving nowhere is surfaced, never redirected:
basename matching retargets a plan citation at a same-named handoff, and a confidently wrong
backlink beats no backlink for damage.

## Why bare `<path>:<line>` is wrong

Bare `<path>:<line>` is ambiguous across the install chain — multiple peer repos can have a file at the same relative path (e.g. `bin/setup.sh`, `docs/wiki/cleanup-sweep-hazards.md`). A successor grepping a bare citation either:

- finds the wrong file in the local repo and acts on stale lines, or
- finds nothing and assumes the citation is stale, when it actually pointed elsewhere.

The repo qualifier fixes this. Grep then targets the right repo.

## When to qualify — two co-equal rules

**Cross-repo citations** (handoffs, lessons, plans, decision records that may be read from a different repo) — ALWAYS qualify with `<repo>:<path>:<line>`. The qualifier is for human disambiguation across the install chain; no automated rewrite covers this case.

**Intra-coordinator citations** in wiki/skill/command/agent prose under `plugins/coordinator/` may use the dev-tree-rooted path (`plugins/coordinator/<...>`) directly. The publish-time hook (the `depersonalize` percolation-store hook, run via claude-klabauter's `coordinator_core.percolate.engine` from `setup/percolate-hooks/coordinator-claude/post-rsync/`) normalizes these to the publish-tree form (`plugins/coordinator/<...>` or `plugins/<plugin>/<...>`) idempotently. Authors do not qualify these — the rewrite is the contract. (Note: this means dev-form paths inside fenced code blocks in this wiki also get rewritten. To preserve a literal dev-form path for documentation purposes, use prose framing — `the plugins/coordinator-claude/... form` — rather than a fenced code block.)

Additional qualifications:
- **Doctrine-path citations MUST be DoE-repo-qualified** — `DoE-claude coordinator/docs/wiki/<name>.md`, never bare `coordinator/docs/wiki/<name>.md`. The receiver's `~/.claude` live-install does not carry `docs/wiki/` (source-only in the DoE clone — see `state-placement-law.md § Taxonomy — What Goes Where`), so a bare citation greps clean against an empty result and reads as premise-false doctrine — one step from a wrong stand-down. The naming collision is the trap: `~/.claude/plugins/coordinator-claude` and the DoE-claude source repo share the string "coordinator-claude" but are not the same tree.
- Optional in commit messages within a single repo (context is implicit).
- ALWAYS qualify in the central structured queue in claude-klabauter at `$(python3 <claude-klabauter>/coordinator/lib/coordinator-state-root.py --central)/improvement-queue/` (cross-repo by construction; entries tagged `queue_scope: central` — see `state-placement-law.md`).
- Coordinator **script** citations (an invocation, not a `file:line` location) follow a separate rule — see `claude-code-platform-gotchas.md` § "Coordinator scripts are on PATH". In short: invokable extensionless commands are cited by **bare name** (`fan-out-dispatch`, not `bin/fan-out-dispatch.py`); `bin/X` survives only for launcher-run interpreter scripts and data files. Both forms are PATH-namespace — never resolve them against the current repo's `./bin/`.

## Plugin-wiki vs publish-native-wiki authoring — a third rule pair

**Plugin-wiki authoring vs publish-repo-wiki authoring is a third rule pair.** Plugin-side wikis are authored against meta-repo paths and persona names; the publish pipeline rewrites both at sync time. Publish-side wikis (allowlisted) are authored against publish-tree paths and depersonalized names directly — they bypass the sync pipeline's rewrite layer because they were never in dev form. When citing across the boundary: a plugin wiki referring to a publish-native wiki cites the post-sync path (`docs/wiki/task-tier-guidance.md` from the publish-repo root); a publish-native wiki referring to a plugin wiki cites the post-sync path on the publish side (`plugins/coordinator/docs/wiki/X.md`).

The allowlist (`setup/percolate-hooks/coordinator-claude-toplevel-wiki/post-rsync/publish-native-allowlist.txt`) is the registry of files with publish-native authorship. Files not on the allowlist are treated as plugin-sourced and will be overwritten on the next sync. See `docs/wiki/plugin-extraction-and-distribution.md` § Auxiliary Sync for the full mechanism.

Spec backlink: `archive/specs/2026-05/2026-05-18-publish-repo-toplevel-wiki-sync.md` § Chunk 3.

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

Pinning by branch (`main`, `work/...`) is a re-bisect hazard — a future drift can't be located to a specific commit. SHA pins also make `sync-plugin-wiki.py` and similar mirror tools idempotent.

## Coordination memo BEFORE shipping cross-repo changes

If a change in repo A will land before/with consumers in peers B and C, write a one-line coordination memo in the central structured queue (claude-klabauter — `$(python3 <claude-klabauter>/coordinator/lib/coordinator-state-root.py --central)/improvement-queue/`, via `coordinator-queue-append --schema improvement-queue --queue-scope central` — see `state-placement-law.md`) or the active handoff *before* the producing commit — not after. The memo names the producer SHA (once landed), the consumer repos, and the migration order.

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

## Cross-repo property claims need a spec-backlink, not just a citation

**Any DoE prose asserting an internal property of a peer repo's op — locking behaviour,
ordering, atomicity, gating, timing, or any other "runs under X" / "is guarded by Y" claim —
must carry a spec-backlink to the peer source that governs the claim.** This is stricter than
§ When to qualify above: a bare `<repo>:<path>:<line>` citation locates the file, but a property
claim needs the *decision* that makes the claim true, because the property — not the location —
is what the next ratified change to that op invalidates.

**Motivating incident:** `coordinator/skills/workstream-complete/SKILL.md` asserted (in two
places) that `post_commit_stamp_and_ship` runs "under the same `ceremony_lock` the commit itself
holds." The claim was stale the day it was written — claude-klabauter's DEC-3 removed the lock
from that path the same day, and nothing linked the prose to the governing source, so it rotted
silently. A second, uncited copy of the same false claim was found only by an independent sweep.
Governing source: `claude-klabauter coordinator_core/ops/ceremony/wsc_tail.py:217-220`, ratified in
`claude-klabauter docs/plans/2026-07-22-wsc-tail-sub-2s-invoke-budget.md § DEC-1/DEC-3/C3`.

**Compliant form:**
```
<!-- spec-backlink: claude-klabauter coordinator_core/ops/ceremony/wsc_tail.py:217-220 (DEC-3, 2026-07-22) — steps 5c/5d run UNLOCKED; step 5a commit lock is the only ceremony_lock on the live path -->
```

Required fields, all four — omitting any one degrades the backlink to an un-recoverable citation:
- **repo** — which peer repo governs the claim.
- **path:line-range** — where the governing code lives today. Line ranges drift; this is the
  weakest field and is expected to go stale.
- **ratifying decision id + date**, where one exists (`DEC-N`, `DR-NNN`, a dated plan section) —
  this is what survives line drift: a stale line range is still recoverable by re-locating the
  decision, but a stale line range with no decision id is just a dead pointer.
- **one-line property statement** — the specific claim being relied on, in the author's own
  words. This is the second survivor: even if both the line range and the decision id go stale,
  the property statement tells a future reader what to go re-verify and against what mental
  model.

**Relationship to other backlink conventions.** This is a cross-repo sibling of the in-tree
"Spec Backlink" convention in `rag-bait-conventions.md § 3` (which points source-code comments at
a minted `pln-`/`dlv-` id in the *same* repo). The id form is heal-independent by construction:
an id does not change when the plan file moves, so there is nothing for a path-rewrite pass to
rewrite. It is deliberately **not** the "Cross-repo provenance backlinks in source comments"
anti-pattern in `rag-bait-conventions.md § Anti-Patterns` — that anti-pattern is about *port*
provenance (`// port of <peer-repo>:<sha>`) in source code, which has no heal pass and belongs in
the commit message instead. A property-claim spec-backlink is different in kind: it grounds a
*standing doctrine assertion* about another repo's behavior, in doctrine prose (SKILL.md, wiki),
not source code — there is no commit message to carry it, and unlike a port-provenance comment it
is expected to be re-verified, not merely historical.

## Manifest paths: grep the repo, not the installed tree

When verifying a manifest field (skill path, agent path, hook script) lives where the manifest claims, grep the **source repo's working tree**, not the installed `~/.claude/plugins/` copy. The installed copy is downstream of the publish pipeline (claude-klabauter `coordinator/bin/publish.py`) and may lag the repo by days; the manifest contract is against repo paths.

```bash
# Right — verifying skill manifest against source
rg "^path:" plugins/coordinator/skills/*/SKILL.md

# Wrong — verifying against the installed mirror
rg "^path:" ~/.claude/plugins/coordinator/skills/*/SKILL.md
```

Installed-tree verification masks pre-publish drift: a manifest that's wrong in the repo but right in the install will pass the wrong-tree check and ship broken.

## Sweeping `~/.claude/plugins` refs: classify source-claim vs runtime-install-home per reference

In a coordinator→DoE cutover sweep, the same literal path — `~/.claude/plugins/coordinator-claude` — serves **two roles**, and a sweep that treats them uniformly deletes live behavior:

- **Stale SOURCE / authoring claim** — text asserting that the coordinator source *lives* under `~/.claude/plugins/`. This is the naming-collision trap (see § When to qualify): the source is the DoE-claude clone, not the live-install. **Reword** to name the DoE-claude clone.
- **Legitimate OSS / marketplace RUNTIME install-home** — a path that genuinely resolves against the installed plugin tree at runtime (e.g. an OSS auto-push-hook fallback that reads its own installed copy). **Preserve verbatim**, exactly like a `platform-localize`/`AGENT.md` runtime reference.

Apply the discriminator **per reference**, not per file — a single chunk can mix both roles. The tell for a runtime-home is that some live code path reads the installed copy through that literal; the tell for a source-claim is that the sentence is *describing where the source is authored*. The Director of Engineering caught a cutover chunk that would have deleted the OSS auto-push hook fallback by rewriting a runtime-home as if it were a stale source ref. Classify before rewording or removing.

## Single-token path format for cross-repo integrators

When a downstream integrator (scout, executor, or worker) needs to act on a file across multiple repos, format paths as a single token `<repo>:<path>` — not split across columns or stitched from separate fields. Integrators that split-and-rejoin lose alignment under concurrent fan-out.

```
Right: coordinator-claude:plugins/coordinator/skills/learn-lessons/SKILL.md
Wrong: repo=coordinator-claude  path=plugins/.../SKILL.md  (two fields, must rejoin)
```

The line-citation form `<repo>:<path>:<line>` is the same shape with the line tail appended. Tools that grep for the qualifier prefix work uniformly on both.

## Grep ratified cross-repo DRs before authoring a new hookspec

Before drafting a new hookspec or seam interface, grep the peer-repo ratified DRs and coordination memos from recent days. Authoring without this check produces collisions: e.g., drafting `project_rag_declare_kind_sources` while a peer repo's already-ratified `project_rag_register_corpus_provider` (D-5) covers the same seam. The prior-art-checker catches the collision after the draft exists; this discipline catches it before. One grep run against `docs/decisions/` and `state/handoffs/` in each peer repo is sufficient.

## Donor-module excision: check consumer imports before celebrating the split

After excising a donor module from a repo, grep consumers for `from <excised_module>.` imports before declaring the split complete. Module-top imports break the consumer at load time, not at first use — a green unit-test suite on the donor side does not prove the consumer is intact. The post-split smoke is a green import test run against the consumer (`python -c "import <consumer_module>"`), not just the donor. Source: project-rag-ue-addon excision post-mortem.

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
     Generator: claude-klabauter `coordinator/bin/decode-claude-projects-dir.py`
     Source: ~/.claude/projects/
     Refresh: /update-docs Phase 15 (cwd-gated, ~/.claude only)
     Last refreshed: 2026-05-14
-->
...candidates...
<!-- END repo-registry-candidates -->
```

## Sibling-layout convention for vendored code

> **Runtime `repos.*` discovery.** The MUST-use-sibling-layout contract codified below is the **port-time cleanup discipline** (absolute-path sweep at extraction) — unchanged. At runtime, `repos.<slug>` discovery is governed by the 4-rung ladder in `machine-local-registry.md` §4c (SSOT: `project-rag/docs/wiki/cross-machine-path-resolution-contract.md`); the blind sibling-relative walk is **not a runtime rung**. Marker-autodiscovery (§4c rung 2) satisfies the original "no forced cutover" intent without requiring sibling-layout compliance or operator seeding. See `machine-local-registry.md` and `plugin-extraction-and-distribution.md § 11`. The `EXAMPLE_GAME_REPO_ROOT` → `MACHINE_LOCAL_<KEY>` note remains accurate.

**Incomplete migrations leak absolute paths into vendored code; `../sibling/...` is the contract for sibling repos.** When a repo is split into peer/sibling repos that live in the same parent directory (e.g. `<drive>:/project-rag/` and `<drive>:/project-rag-ue-addon/` — `X:/`, `C:/`, `D:/` etc. are all illustrative; substitute the host's actual root prefix), any cross-repo reference in vendored code, scripts, or docs MUST use a `../<sibling-repo-name>/...` relative path — never an absolute path like `<drive>:/...` or `/c/Users/.../`. <!-- abs-path-ok: enumerating illustrative drive-letter literals, not a claim about any real checkout -->

Two reasons:

- (a) Absolute paths break for any developer with a different layout (CI, peer machines, anyone else picking up the repo).
- (b) Absolute paths fail the depersonalize/sanitize hooks at publish time even when those hooks know about the substring keys.

**Port-time discipline:** at every repo split, grep the vendored tree for absolute repo prefixes (`<drive>:/`, `/c/`, `/Users/`, `/home/` — substitute the host's actual root prefix so e.g. `C:/`, `D:/` matches aren't missed) and rewrite to `../sibling/...`. The sibling-layout convention is the contract — document it in the source repo's README so consumers don't fight it. <!-- abs-path-ok: enumerating illustrative drive-letter literals, not a claim about any real checkout -->

Source: `project-rag-ue-addon:state/lessons.md:121`.

Runtime alternative: for consumers that cannot rely on sibling-layout (triangular graphs, multi-drive setups, deterministic-location requirements), prefer the machine-local registry — see `machine-local-registry.md` and `plugin-extraction-and-distribution.md § 11` for the full discovery preference order.

## Doc-links across a `copy_install` boundary — absolute URLs, not relative paths

> Distinct from § Sibling-layout convention for vendored code above. That rule governs **script/code paths** between sibling repos that live in the same parent dir (`../sibling/...` is the contract there). THIS rule governs **markdown doc-links** that cross a `copy_install` mirror boundary — a different surface with the opposite remedy. The two do not conflict: keep `../sibling/...` for vendored code paths; use absolute GitHub URLs for doc-links across a `copy_install` boundary.

**Plugin docs that link to repo-level files (`docs/`, `archive/`) via relative paths resolve only while the plugin sits inside its origin repo.** Once the plugin is `copy_install`-mirrored into a consumer tree (only `plugin/` is copied — sibling `docs/` and `archive/` directories are NOT), every such relative link dangles regardless of `../` depth. No amount of path-walking fixes it: the link's target was never copied alongside the plugin.

The failure is doubly silent because the two reference-validators disagree across the boundary:

- The **source-repo** checker passes — it resolves the link in the source layout, where `docs/` and `archive/` do exist beside the plugin (and the source checker may not even scan READMEs).
- The **consumer-repo** `validate-references` flags the same link as broken — the target directory is absent in the mirrored tree.

So a link that is green at author time ships broken to every `copy_install` consumer, and only the downstream repo surfaces it.

**Fix: cite repo-level files with an absolute `github.com/<org>/<repo>/blob/main/<path>` URL, not a relative path,** whenever the linking doc is inside a `copy_install`-mirrored plugin and the target lives outside the mirrored `plugin/` subtree. This matches the existing `doctor.md` precedent and survives percolation intact — an absolute URL resolves identically in the source repo and in every consumer mirror.

**How to decide:** before writing a relative `../docs/...` or `../archive/...` link from inside a plugin doc, ask "does the `copy_install` mirror carry the target?" If the target is outside the copied `plugin/` subtree, the relative link will dangle downstream — use the absolute GitHub blob URL. Intra-plugin links (target also inside the mirrored subtree) stay relative; they travel with the plugin.

## Peerless installs — env-var opt-in for peer-repo paths

Most installs place `~/.claude`, the publish target (`X:/coordinator-claude`), and peer dev repos (`E:/dev/example-game-workbench-repo`, etc.) such that sibling-relative paths (`$PLUGIN_ROOT/../../example-game-workbench-repo/...`) resolve correctly. Sync scripts default to this layout. <!-- foreign-path-ok: illustrating a real-world Windows install layout, the subject of this section -->

The `~/.claude/` install on a Windows user-profile root (`C:\Users\<name>\.claude\`) is structurally peerless: there is no sibling-capable parent, and no companion dev folder lives next to it. Sync scripts that assume a sibling peer silently skip verification on this install (skip-if-absent guard — looks fine, never actually checks the peer copy). <!-- foreign-path-ok: illustrating the real Windows profile-root path shape, the subject of this section -->

**Rule:** keep sibling-relative as the default in scripts (matches every normal-layout deployment). Deviant installs opt in via an explicit env var:

```bash
# Default: sibling-relative (correct for most installs)
EXAMPLE_GAME_REPO_ROOT="${EXAMPLE_GAME_REPO_ROOT:-../example-game-workbench-repo}"

# Override for peerless installs (e.g. C:/-rooted ~/.claude): <!-- foreign-path-ok: illustrative Windows-root example, the subject of this snippet -->
# export EXAMPLE_GAME_REPO_ROOT=/x/example-game-workbench-repo
```

**Do NOT rewrite the sibling default in scripts that ship to normal-layout deployments** — fixing the `C:/` edge case by hardcoding an absolute path breaks what already works everywhere else. <!-- abs-path-ok: naming the historical drive-letter literal this sentence critiques, not a claim about any real checkout -->

Source: `state/lessons/` § "C:/-rooted `~/.claude` is structurally peerless" (claude-coordinator). <!-- foreign-path-ok: quoting the lesson's own section title, which names the Windows path shape it documents -->

