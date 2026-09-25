# Migration Script Conventions

**Purpose.** Rules for scripts and campaigns that rename, relocate, restructure, or retire files, paths, contracts, and identifiers in the repo (path-rename migrations, directory reorganizations, scaffolding reshapes, contract retirements, bash→Python ports). The recurring failure modes below hit every migration that wasn't written with these in mind — most share a root cause: the migration's *scope of enumeration* was narrower than the real surface it touched.

## 1. Enumerate with `find`, not `grep --include`

**Extension allowlists in `grep --include` silently miss non-standard-extension files.** A migration that gathers its source files with `grep -r --include='*.sh' --include='*.py'` will silently skip `.bats` test runners, `.tmpl` template files, extensionless bin scripts, and any other file the author didn't enumerate. The migration completes with exit 0; the skipped files are left in the old location; downstream tooling breaks on them.

**Use `find` with explicit `-type f`** and add extension pruning only as an opt-in filter — not as the discovery mechanism:

```bash
# Wrong — silently misses .bats, .tmpl, extensionless files
grep -r --include='*.sh' --include='*.py' -l 'old_pattern' .

# Right — enumerate all files, then filter if needed
find . -type f | grep -v '.git' | while IFS= read -r f; do
    # process $f
done
```

When the migration's scope is "all scripts under path X", use `find path/X -type f` with no extension filter at all — let the script decide per-file whether to act.

**Empirical source (queue line 57):** a path-rename migration used `grep --include='*.sh' --include='*.py'` and shipped without touching `.bats` runners and extensionless bin scripts that lived alongside the renamed paths. The omission was invisible in CI because the skipped files still resolved (from the old path, which hadn't been deleted yet).

## 2. `rmdir` empty source directories before `git mv`

**`git mv` aborts when the source directory is empty.** A migration that deletes all content from a directory and then tries to `git mv dir/ newdir/` will fail: git cannot move an empty directory (git does not track empty dirs). The migration halts mid-run, leaving the repo in a partially-migrated state.

**Remove empty directories explicitly before any `git mv`** that moves a directory as a unit:

```bash
# After moving/deleting all content out of old_dir:
find old_dir -type d -empty -delete   # rmdir empties (depth-first)
# Now git mv of the remaining non-empty subtree is safe
```

If the migration moves files individually (not directories as a unit), empty-dir cleanup is still required before the final commit: git will silently leave empty dirs in the working tree, and a subsequent `git add` won't stage them (nothing to stage). Clean up with `find . -type d -empty -delete` before committing.

**Empirical source (queue line 58):** a path-rename migration moved all files out of a source dir then attempted `git mv old_dir/ new_dir/`. `git mv` aborted on the now-empty source. The migration had to be re-run with an `rmdir` step inserted before the `git mv`.

## 3. Sweep EVERY consumer before you scope, chunk, or retire

Section 1 governs the *discovery mechanism* (`find` over `grep --include`). This governs the *scope of the sweep*: a migration's blast radius is almost always wider than the named pipeline files it was scoped to, and the missed consumers fail silently — the migration exits 0 while a downstream surface goes stale, no-ops, or breaks.

**Sweep tree-wide BEFORE chunk-scoping, not after.** When a plan changes an artifact's on-disk shape/extension (e.g. `state/goals/*.md` → `*.yaml`), the chunk owning the schema change gets scoped to a handful of named files — but the OLD glob is consumed across the whole tree. Enumerate every consumer of the old shape first, then scope; consumers found after execution surface as functional breaks, not clean fast-follows. In one goal-artifact migration a hook counter kept globbing `*.md`, permanently reported zero, and silently disabled its nudge — a *live* functional break invisible at plan time.

**A "grep returns empty" retirement gate is wrong-shaped.** A literal *"grep `flight-recorder` returns empty"* contradicts kept backward-compat aliases and historical prose. Scope retirement gates to **dangling refs** (the removed schema/path) and **producers** (path construction), and *exclude* comments, tool descriptions, historical `.md` prose, and test-fixture inputs.

**On any contract flip/inversion, grep every consumer prompt for the OLD contract's verbs.** When a mechanism is retired (e.g. review self-persist retired the EM-persist step), stale *"the EM does X"* instructions survive silently in consumer surfaces — 6 persona agents still carried the pre-flip framing long after the flip, producing a live schema warning. Grep all agent prompts, snippets, and skills for the retired contract's verbs before declaring the migration done.

**The "live callers" grep must include `.md` and extensionless `bin/` files.** Coordinator command docs (`commands/*.md`), skill bodies (`skills/*/SKILL.md`), and pipeline docs embed live `bash "$script" …` invocations that **execute** when the command/skill runs — they are runtime call sites, not documentation. Filtering out `.md` hid three live callers of a migration script and produced a false *"no runtime caller"* removal premise. Likewise `--include='*.sh'` misses extensionless `bin/` producers (e.g. `coordinator-doc-new`) — add a no-include `bin/` scan or the real producer slips through. Grep `lib/`, `scripts/`, `bin/`, `hooks/`, AND `skills/`/`commands/`, then **read** each match to distinguish a live invocation from a mention.

**Grep every path SHAPE, not just the canonical one.** Scoping a migration off a hardcoded well-known path (e.g. `~/.claude/plugins/coordinator-claude/coordinator` during the maximalist cutover) by grepping only the `CLAUDE_PLUGIN_ROOT:-<path>` fallback form undercounts massively: the bare `$HOME/.claude/plugins/…` form (no `CLAUDE_PLUGIN_ROOT` prefix) is a SEPARATE shape — in the 2026-07-04 install-shape work the fallback form was 57 sites but the bare form was ~202 additional lines (4×). Grep the extension-agnostic pattern (`grep -rE '\.claude/plugins/coordinator-claude/coordinator'`), then partition by whether `CLAUDE_PLUGIN_ROOT:-` prefixes it.

## 4. Migrating source is not enough — regenerate derived artifacts and installed copies

A migration that edits only the source-of-truth leaves two other classes stale: **generated artifacts** emitted from the source, and **already-installed copies** on every machine.

- **Generated artifacts must be re-emitted, never hand-edited.** A goal migration left the generated `artifact-shape-contract.schema.json` (emitted from schema `applies_to`) stale until re-emitted — editing it by hand is the anti-pattern; re-run the emitter.
- **Installed copies need a regeneration/rollout leg.** Git-hook *generators* (e.g. `coordinator-ensure-*-hook`, `install-meta-repo-precommit-hook.py`) bake a hardcoded path into `.git/hooks/*`, so migrating source is insufficient — already-installed hooks on every machine need regeneration. This is a fleet-rollout dimension: the bare-path hooks broke live (`No such file or directory`) during the migration's own review-integration commit because the installed copy had diverged from source.

## 5. Verify the REAL production path before repointing or retiring

A caller or entry point that *looks* like the migration target may be a dead fallback, or a false-green that bridges to the very thing you meant to retire. Confirm which path production actually executes before touching it.

**Strangler facade → the caller may be dead code.** A caller-level state-routing flip (central→doctrine repo at `coordinator-queue-append`) touched only the State-1 legacy fallback, while a concurrent strangler had retargeted those CLIs through a native op (`cc_invoke → engine coordinator_core`) — the production path on any provisioned machine. Production still mis-homed. Before flipping routing at a caller, verify which execution path production takes; the empirical tell is **run the real CLI and check where the artifact LANDS**, not just that tests pass — test-green on the legacy path is necessary-not-sufficient.

**A native-looking Python entry point can subprocess-bridge to the bash you want to delete.** An installer step or `probe_*` sentinel that reads native can be a false-green: its body shells out to the candidate `.sh`. Repointing onto it does NOT decouple — the Python is a *consumer* of the bash, so deleting the bash breaks it. Before tagging any Python entry point as a "repoint here / retire the bash" target, grep its body for `subprocess` / `bash -c` / `source` referencing the candidate script. If it bridges, it is a consumer awaiting native port — keep the bash live and delete only on the owning repo's cutover-clear memo.

## 6. Renumbering ordered identifiers stales cross-references in OTHER files

Inserting a new step (e.g. `/workday-start` Step 1.10.6) and renumbering the existing steps silently staled a `Wired into: Step 1.10.7` comment in a *different* file (`check-all-shebanged-exec-bits.py`) — the executor's same-file grep missed it. When renumbering any ordered identifier (doc step numbers, enum values, AC ids), grep the OLD identifier value **repo-wide across all extensions** before declaring the renumber complete; a single-file grep is insufficient.

## 7. Corpus-wide auto-editors: mode, errexit, per-occurrence, dry-run

An idempotent auto-inserter (a `verify-*-sync --fix` over a grep-discovered set) has four load-bearing invariants, each a real shipped-then-caught bug in the `cc-root-source-guard` workstream:

1. **Preserve file mode.** `mv tmp src` strips `755→644`; use a truncate-rewrite (`cat tmp > src`) instead.
2. **Don't abort `set -e` scripts.** A bare `$(cat sentinel 2>/dev/null)` in an assignment trips `errexit`; append `|| true`.
3. **Gate per-OCCURRENCE, not per-file,** and handle indented (list-nested) markdown fences.
4. **Always dry-run the full corpus and EM-review the diff BEFORE writing.**

## 8. New transition CLI touching frontmatter? Consume the shared schema primitives

A new lifecycle/transition CLI under `coordinator/bin/` that reads or writes YAML frontmatter is almost always the Nth copy of `splitFrontmatter` / `readFmField` / `serializeYamlScalar` / `replaceFmField` / `insertFmField`. Before hand-rolling, require them from `coordinator/bin/lib/schema.js` (the write-side complement to the existing `parseFrontmatter` export). Copies drift silently: prior to consolidation there were 5 divergent variants differing in prefix-collision boundary lookahead, all-numeric/sci-notation quoting, and block-scalar guards — latent correctness bugs the divergence hid. A 6th author who greps `splitFrontmatter` should find the shared home first.

## 9. Parallel bash→Python migration campaigns — four mechanics

A wide multi-agent port campaign surfaced four load-bearing mechanics:

1. **ONE AGENT PER SCRIPT/MODULE.** Recipe "chunks" are wave-batching / file-overlap units, NOT agent-sizing units — a 6-script chunk is 6 agents. A monolith agent burned 409K tokens / 28 min and hit the StructuredOutput 5-retry emission wall.
2. **Defer centralized op-registration.** `ops/__init__.py` + `_registry_map.py` + `ipc.py::_OP_KEY_SCOPE` + `authz/classification.py` are a shared-write collision surface on a no-worktree tree — write per-chunk fragment files + do ONE serial EM merge. Every registered op needs an `OP_CLASSIFICATION` entry or the authz drift-guard goes RED.
3. **Verify PARITY, don't trust "imports clean."** A verify pass caught a silent goal-corruption-on-reinit bug that clean imports hid — golden-diff the port against the bash oracle over a REAL corpus.
4. **Budget for mid-response API drops.** At ~20-25 concurrent agents the API drops ~1-in-8 mid-response; recovery is clean (disk-persisted partial work + re-dispatch the gap) so it stays net-positive. Use plain-text agent returns for the biggest/most-complex ports to dodge the schema-emission wall.

## 10. Audit open plans for stale paths after a surface migrates, not just the tree

<!-- PROVENANCE: run 2026-08-06-14h38, derived from nugget c7-047 -->

A migration that relocates an executable surface (e.g. `coordinator/bin/` scripts to
the engine repo) can be clean in the tree — zero tracked files left at the old path — while
still leaving the *plan corpus* stale. Plans are long-lived prose snapshots; they cite the
path that was true when authored and don't self-update when the surface moves.

**Empirical source (audit taken days after the `coordinator/bin/` →
engine migration lifecycle-vocabulary overhaul landing
alongside):** 39 of 40 open plans cited `coordinator/bin/` paths against a repo that tracked
zero files there. The disagreement was plan-vs-repo, not merely plan-vs-plan — a stale audit
target found stale within days of the migration landing, because no leg of the migration swept
the plan corpus for the old path shape.

**Add a plan-corpus sweep as a migration exit leg**, alongside the tree-wide consumer sweep in
§3: grep open plans (not just source/lib/skills/commands) for the old path shape before
declaring the migration done. A migration that changes where an executable surface lives is not
complete until the plans that reference it are re-pointed or flagged stale — otherwise the next
reader (human or agent) trusts a path the repo does not have.

## 11. Gate the repoint action and the delete action separately

In a strangler migration, the repoint (switch callers onto the new implementation) and the
delete (remove the old implementation) are two independently-gatable actions, not one workstream
item. Parking both under the workstream's single most-blocked entry over-blocks the repoint,
which is often already executable, on a delete gate that has nothing to do with it. Split them:
let the repoint proceed and land on its own merits, and hold only the delete behind whatever the
delete actually needs (a cutover-clear memo, a consumer census, an owning-repo sign-off — see §5
and §12).

## 12. Subject-first relocation carries the destination repo's standards, at sub-file granularity

Moving a subject INTO a repo organized around that subject is not an exemption from that repo's
authoring standards — it is the occasion to apply them. The carry-over applies at sub-file
granularity: a relocated file can be correct by the old repo's conventions in one section and
wrong by the destination's in another, and "the file as a whole already moved" is not evidence
every section inside it now conforms. Check each section against the destination's own rules,
not just the file's new path.

## 13. Census by grepping the subject name across the tree, never by transcribing a file list

A substrate census for a port must enumerate every test file that exercises the subject by
**grepping the subject's name across the whole tree**, not by transcribing a remembered or
documented file list. A file list copied from memory or from prior docs silently omits test
files that reference the subject but were never catalogued anywhere — the port then ships
untested against them, with no error to signal the gap.

## 14. Report both the broken-site count and the already-correct-site count

Scoping a migration by counting only the broken sites leaves the already-correct sites as an
invisible denominator. Without that second count, a migration executor cannot tell "N broken
sites, done" from "N broken sites out of N+M total, M of them already correct" — and the missing
denominator can trigger an unnecessary churn rewrite of code that was never wrong. Always report
both counts together when scoping.

## 15. Derive a migration's consumer set on the old surface vocabulary, not the new token

A migration's consumer sweep must be scoped by grepping the **surface vocabulary being
changed** — the old names, paths, or shapes — never by grepping for the new token the migration
introduces. A new-token pattern is structurally blind to exactly the unmigrated consumers it
exists to catch: those consumers still use the old vocabulary by definition, so searching for the
new one returns zero hits from them every time, and the sweep reads as clean while missing its
entire target population.

## 16. Sweep a freshly-authored record's cited paths for existence before trusting its verdict

Records that cite paths rot silently against migrations: a record authored before a migration
lands can cite paths that no longer exist, and its verdict looks unchanged (an empty derivation
looks identical to a clean surface — both report nothing). Before trusting a freshly-authored
record's derivation or verdict, sweep every path it cites for existence. A record whose citations
are already dead has produced its "clean" result by finding nothing to check, not by checking and
finding nothing wrong.

## 17. A signature change's caller sweep must reach every suite, not just the ones you ran

Adding a required-keyword parameter to a shared helper is a caller-sweep obligation that a
**scoped test run structurally cannot catch** — a suite that never calls the changed helper
stays green regardless of whether its callers are broken, and the touching dispatch has no
reason to run a suite it doesn't already know is affected. The sweep for a signature change must
enumerate every caller across every suite by grep, not by running "the suites this change should
plausibly affect."

## 18. A deletion-clearing grep must include the publish mirror

A grep that clears a deletion ("no consumer references this") must include the publish mirror —
a mirror the repo percolates content into runs its **own CI over the percolated files**, and it
is write-only for content, never a gate target. A sweep scoped to the source repo alone misses
the mirror's independent read of the same files, and a deletion that looks clear against the
source repo can still break the mirror's build.

## 19. Enumerate the writers before ratifying a shared-module contract's reader

Before ratifying a shared-module contract, enumerate every existing **emitter** of the field the
contract governs, not just the reader you're about to write. Extracting a shared module is
usually framed as stopping N copies of the same code from drifting, but the real risk sits on the
other side: a second, divergent reading of the contract. A design-fork question about the
contract's shape is often already settled by four greps over the existing emitters — read them
before debating the shape in the abstract.

**Reader-side mirror:** the same enumeration failure recurs symmetrically on the reader side. A
type-specific claim written into a shared contract block is wrong for whichever consumer isn't
the type in front of you — the majority case visible while writing the block is not the contract;
enumerate every consumer of the shared block before hardcoding one type's specifics into it.

## 20. A CONTRACT_VERSION bump is a three-step release sequence, not an edit

Bumping a `CONTRACT_VERSION` constant is a three-step release sequence — a dispatched executor
can only perform step 0 (the edit itself); the remaining steps are an EM-owned wave-boundary
close-out. A plan that treats the bump as a single edit produces a **bare re-vendor silent
no-op**: the version changes but nothing downstream re-derives against it, and nothing signals
the gap. Any plan touching `CONTRACT_VERSION` must name the EM's close-out as its own explicit
step, and treat an `--ack-major` flag as a review gate to walk through deliberately, never a
keystroke to clear on the way past.
