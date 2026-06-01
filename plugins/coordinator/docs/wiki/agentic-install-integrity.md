---
title: Agentic Install Integrity
created: 2026-05-28
author: coordinator-em
status: current
kind: wiki
spec-backlink: docs/plans/2026-05-28-shared-install-divergence-primitive-lift.md § C4
related:
  - coordinator/bin/check-install-divergence.py
  - coordinator/bin/install-sentinel-write
  - setup/tests/contract/install_divergence_contract.json
  - docs/wiki/live-install-drift-audit.md
  - docs/wiki/install-surface-completeness.md
  - docs/wiki/cross-repo-handshake-doctrine.md
keywords:
  - byte-divergence classifier
  - install integrity
  - version.txt sentinel
  - semantic divergence
  - plugin-spawned state
  - doctrine-version sentinel
  - agentic install
---

# Agentic Install Integrity

**Purpose.** Operator-facing reference for the coordinator's byte-divergence classifier, the
`version.txt` sentinel format, and the three known deferred extensions to byte-divergence
detection. Authored under the "agentic install integrity" framing: byte-divergence catches the
class of install corruption that a blind reinstall would silently destroy, but it is not the
complete picture. This wiki names what it catches, what it does not, and the falsifiable
triggers for the three extensions that are parked pending real instances.

---

## What the Byte-Divergence Classifier Solves

The coordinator's live-install propagation model is intentionally manual: plugins are authored in
the meta-repo and published outward via `setup/publish.sh`; per-machine installs are separate
checkpoints that an operator explicitly refreshes. In this model, a consumer can accumulate local
edits to skills, docs, or config before they realize a new version has been published. When a
refresh runs, the naive approach — `rm -rf` then copy — silently destroys those edits. The
byte-divergence classifier is the gate that prevents this.

`coordinator/bin/check-install-divergence.py` performs a **three-way blob-SHA diff** across
three states: (1) the baseline — the source tree at the SHA recorded in `<install-root>/version.txt`
(what the consumer received when they last installed); (2) the live install — what the consumer's
disk looks like now (which may include hand-edits); (3) the incoming source — the source tree at
the current HEAD (what a fresh install would copy in). Files that have changed in BOTH the live
install AND the incoming source are **consumer-modified**: the consumer edited them and the source
also wants to overwrite them — the gate returns exit code 3 (divergence detected) and surfaces a
per-file diff so the consumer can decide. Files changed only in the incoming source are
**forward-safe**: the consumer has not touched them and a reinstall can proceed without loss.
This is the same classification logic as a three-way git merge applied to an install tree.

The tool ships at `coordinator/bin/check-install-divergence.py` (lifted from
`project-rag/project_rag_scripts/lib/check_install_divergence.py`, verbatim-on-contract per the
plan). The machine-readable contract — exit codes, JSON stdout schema, CLI flags — is pinned at
`setup/tests/contract/install_divergence_contract.json`. The sentinel writer that produces the
baseline anchor is at `coordinator/bin/install-sentinel-write`. For the full picture of how
copy_install drift is detected and remediated in the drift-audit primitives, see
`live-install-drift-audit.md`.

---

## Sentinel Format Spec

<!-- LOAD-BEARING: downstream consumers (addon-em, holodeck-em) bind to this format. -->
<!-- Do not change this section without bumping setup/tests/contract/install_divergence_contract.json -->

**File location.** `<install-root>/version.txt`

**Content format.** Exactly ONE line: 40 lowercase hexadecimal characters (a git SHA), followed
by a single LF byte (`\n`). No other content. No trailing spaces. No BOM.

```
e3b0c44298fc1c149afbf4c8996fb92427ae41e4\n
```

**Encoding.** UTF-8. Because the content is pure ASCII hexadecimal, the encoding is
incidentally irrelevant — the constraint matters only to rule out accidental BOM injection by
tools that write UTF-16 or Windows-BOM-UTF-8 by default.

**Line ending.** LF (`\n`), not CRLF. This is the gitattributes-neutral choice for a
single-line data file: cross-platform tools that validate the sentinel use `strip()` before
regex check, but the writer-of-record (`install-sentinel-write`) writes LF unconditionally.

**Writer-of-record.** `coordinator/bin/install-sentinel-write` is the canonical writer.
Other writers are welcome if they meet the format. The format is simple enough that any
caller can produce it correctly without importing the writer:

```bash
git -C "$source_dir" rev-parse HEAD > "$install_root/version.txt"
```

```python
(pathlib.Path(install_root) / "version.txt").write_text(sha + "\n", encoding="utf-8")
```

**Validator regex.** `^[0-9a-f]{40}$` — applied after `strip()`. Any content that does not
match is treated as a malformed sentinel by `check-plugin-drift.sh` (which emits
`[warn] version.txt malformed` and exits 0 — not drift, but not parseable either).

**Machine-readable contract anchor.** `setup/tests/contract/install_divergence_contract.json`
carries the sentinel format alongside the classifier's exit codes and JSON stdout schema. It is
the single-page binding contract for downstream consumers (holodeck-em, addon-em, or any future
consumer in any sibling repo) to import as a smoke check. The JSON key is `sentinel_format`.

**Doctor surface for absence.** `check-plugin-drift.sh` emits `[info] <plugin>: copy_install —
no version.txt sentinel (installer did not write one; see holodeck memo)` when the sentinel is
absent. This output IS the doctor surface for the absence case — it is honest degraded state,
not a probe failure. No separate gap-detection logic is needed.

**`source_is_live` caveat does not apply.** `version.txt` lives in the published/receiver tree,
not the central source tree. The `install-surface-completeness.md` § State-Files caveat (state-files
whose sole writer is the install ceremony never exist on `source_is_live` machines) does not
apply here: there is no install ceremony on a `source_is_live` machine, and the classifier is not
run against `source_is_live` plugins (`check-plugin-drift.sh` treats them as structural no-ops).

---

## Three Deferred Extensions to Byte-Divergence Detection

Byte-divergence is a necessary but not sufficient check for agentic install integrity. Three
failure modes are known but deferred: each is named here with a falsifiable revisit trigger so
future sessions do not re-derive them from scratch.

### 1. Semantic-vs-Byte Divergence on Skill Rewrites

**What byte-divergence misses.** When the source repo restructures a skill — renames steps,
splits a section, refactors prose — while preserving intent, the classifier correctly reports
"consumer-modified" for any live file the consumer has also edited. The consumer then faces a
diff between their prose customization and the new structural version of the same skill. The
classifier gives them the diff and lets them decide; it cannot tell them "the new version says
the same thing in a better structure — your edit is still valid, you just need to rebase it."
For skills with heavy consumer customization (e.g. `workstream-start.md` with project-specific
steps added), this results in a `--overwrite-modified` prompt where the consumer wants the new
structure but is afraid of losing their customization.

**Why deferred.** No instance of this failure has been observed. The falsifiable trigger is
the threshold at which the pattern becomes a recurring cost rather than an occasional
decision for the consumer.

**Revisit trigger.** When we observe **≥ 3 instances** of a consumer accepting
`--overwrite-modified` and subsequently reporting they wanted the new structure but feared losing
a locally-added lesson or project-specific step, build an LLM-judge layer that distinguishes
structural rewrites (intent preserved, prose restructured) from semantic rewrites (intent changed).
The judge would surface "this is a structural rewrite — your edit is a lesson you can re-add"
rather than presenting a raw diff.

**Partially realized 2026-05-30 (`/coordinator-update`).** The OSS-only `/coordinator-update` skill
(`coordinator/dist/oss-only-skills/coordinator-update/`) pulls this extension forward as a
PM-invoked advisory verb rather than waiting for the ≥3-instance trigger: it runs the three-way
classifier and has the consumer's own Claude judge, per `consumer_modified` file, whether the
upstream change is worth rebasing the user's edit onto (the semantic-vs-byte distinction above) —
preserve-by-default. The verb is the realization; the standalone LLM-judge *layer over the
classifier output* described here remains the deeper form if the per-file agentic judgment proves
insufficient at scale.

**What would stay the same.** Exit codes, JSON stdout schema, and the sentinel format are
unaffected — the LLM-judge is a display layer over the classifier's output, not a change to
the classifier's contract.

### 2. Plugin-Spawned State on Consumer Disk

**What byte-divergence misses.** The coordinator's skills actively write to the consumer's disk
during normal operation: `tasks/`, `tasks/handoffs/`, `docs/plans/`, `tasks/lessons.md`, memory
entries under `projects/`, fragments added to `settings.json`. None of this surface is tracked in
the byte-divergence baseline — none of it comes from `setup/publish.sh`. A reinstall that
"cleanly wipes and replaces" the source tree poses no threat to these paths. But a hypothetical
installer that is less careful — or a future plugin install ceremony that incorrectly scopes its
copy target — could walk into these paths and clobber session-continuity surface. Today we rely
on installers staying out of these paths by convention; there is no machine-enforced registry of
"these paths are owned by the agent, never touched by an installer."

This deferred extension generalizes the pattern established in `install-surface-completeness.md`
§ Plugin-spawned state (the observation that skills write state outside the published tree) into a
formal "owned-by-the-agent, never-touched-by-the-installer" path registry.

**Why deferred.** No installer has clobbered agent-owned paths in the wild. The convention is
holding. A formal registry adds ceremony without a demonstrated failure to prevent.

**Revisit trigger.** When a consumer reports a published-tree install **clobbering session-
continuity surface** (a `tasks/` directory, a `handoffs/` file, a memory entry, a `lessons.md`
entry) — even once — formalize the registry. The registry shape is: a machine-readable list of
path prefixes that no install ceremony may write into, checked at installer entry as a
precondition guard. The install-integrity wiki becomes the source-of-truth for the list.

**Adjacent prior art.** `install-surface-completeness.md` § Plugin-spawned state documents the
observation that skills write these paths. The deferred extension here is the enforcement
mechanism (registry + guard), not the observation.

### 3. Agent-Readable Doctrine-Version Sentinels at Boot

**What byte-divergence misses.** `version.txt` is a machine-facing gate used by the classifier
to decide whether a reinstall is safe. The agent itself does not read it at boot. A consumer
running with skills N commits behind the published tree has no signal that their install is
stale — they are operating from outdated doctrine without knowing it. A doctrinal flip (e.g. a
rule reversal, a renamed skill step, a changed gate condition) that the published tree carries
will silently disagree with the consumer's stale live install until they explicitly check for
drift or notice a discrepancy in agent behavior.

**Why deferred.** The sentinel exists post-this-plan (written by `install-sentinel-write` as part
of C3). Consumption at boot is the parked extension: we have the data; we have not built the
reader. The `/workday-start` Step 1.10 Addon Health already surfaces `[drift]` when the sentinel
mismatches — the probe is there; the question is whether to surface a softer "N versions behind,
here is the changelog link" nudge at workstream-start as well.

**Revisit trigger.** When a consumer reports a **doctrinal flip silently disagreeing with their
stale install** — specifically, an agent that behaved one way on their machine and a different way
on a colleague's more-current install, traced to a skill version delta — build a
`/workday-start` probe that reads each plugin's `version.txt`, compares against the source HEAD
(if reachable via the local registry's `source_path`), and surfaces a human-readable nudge when
N ≥ threshold commits behind.

**Partially realized 2026-05-30 (`/coordinator-update`).** The OSS-only `/coordinator-update` skill
consumes the `version.txt` sentinel (planted install-side by `install.sh`, see § Install-Side) and
checks online for the latest published release tag — the "am I behind?" half of this extension,
realized as a PM-invoked verb. The *automatic boot-time nudge* described here (a `/workday-start`
probe that surfaces staleness without being asked) remains the deferred form; `/coordinator-update`
is pull (the PM invokes it), not push (boot surfacing).

**Note on `post-sync-hook-doctrine.md`.** The C3 sentinel-write hook in `setup/publish.sh` is
a root-level new-file mutation (writing `version.txt` into the destination tree after sync), NOT
a per-file synced-content rewrite. The touched-list constraint in `post-sync-hook-doctrine.md`
applies to the per-file synced-content case; it does not apply here.

---

## Cross-Tool Discipline

`coordinator/bin/check-install-divergence.py` and `coordinator/bin/check-plugin-drift.sh` share
the same core idiom for blob-SHA computation:

```bash
git hash-object --path <relpath> <file>
```

Both tools apply this idiom with gitattributes normalization semantics — the `--path` flag
causes git to apply the correct filter (e.g. `text=auto`, `eol=lf`) before hashing, so
comparisons are gitattributes-symmetric between source and live. This means the idiom is
sensitive to gitattributes configuration: a changed `.gitattributes` rule can flip a comparison
result without any file content changing.

**Rule: change one → review the other.** If you modify the blob-SHA comparison logic in
`check-install-divergence.py` (e.g. changing the `--path` argument, adding filter flags,
changing the normalization semantics), review the same section in `check-plugin-drift.sh:134-215`
for the equivalent change. The same obligation runs in the other direction. Per the plan, the
project-rag source classifier (`project-rag/project_rag_scripts/lib/check_install_divergence.py`)
carries the same cross-tool discipline note pointing back at `check-plugin-drift.sh` as its
cousin — the bidirectional review obligation spans the repo boundary.

**Machine-readable contract anchor.** `setup/tests/contract/install_divergence_contract.json` is
the single-page pinning of the classifier's public contract surfaces: exit codes (0/2/3),
JSON stdout schema, CLI flags, and sentinel format. Downstream consumers (holodeck-em, addon-em,
future consumers in sibling repos) can import this fixture as a smoke check to confirm the
contract has not drifted. Cite this file — not inline docstring assertions — as the discoverability
anchor when describing the classifier's contract to a new consumer.

**Known Limitation #2 closure.** `live-install-drift-audit.md` § Known Limitations #2 documented
that `holodeck` and `game-dev` report `[info] no sentinel` because the holodeck installer was
gated on `requires_plugin_source_index: true` in the plugin manifest (set only for
`holodeck-control`). This plan (`2026-05-28-shared-install-divergence-primitive-lift.md`) ships the
`install-sentinel-write` primitive and wires it publish-side (C3). **Closing Known Limitation #2
for the holodeck trio is install-ceremony work in holodeck — not publish-side work in coordinator.**
The holodeck installer must invoke `install-sentinel-write` at the end of its copy step to plant
the sentinel for `holodeck` and `game-dev`; that is scoped to holodeck's install plan (C6 memo
routes the guidance). The publish-side C3 sentinel addresses a different surface (OSS-clone
consumers who `git pull` the publish-repo directly).

**DR-137 and adjacent prior art.** Decision Record DR-137 (`holodeck-plugin-remains-git-tracked.md`)
and the shipped `2026-05-28-forward-drift-probe-content-equivalence.md` plan (commit 6ae3493b)
are adjacent prior art: `check-plugin-drift.sh` now performs content-equivalence fallback when
`sentinel != source HEAD`, so the sentinel-write primitive in this plan feeds a reader that can
already distinguish "git-propagated current content with stale sentinel" from "genuinely stale
install." Our writer feeds an already-richer reader.

---

## Writer Location: Who Calls `install-sentinel-write`

The `coordinator/bin/install-sentinel-write` CLI is a shared primitive. Invocation is the
responsibility of whoever owns the write surface. Two writer locations exist with different
semantics, and both are legitimate:

### Publish-Side (C3 wire-in in `setup/publish.sh`)

`setup/publish.sh` invokes `install-sentinel-write` after every successful real (non-dry-run)
sync. The semantic is: **"this OSS publish-repo received content from source meta-repo at SHA X,
at publish time."**

This sentinel is useful for the **OSS consumer who `git pull`s the publish-repo directly into
`~/.claude/`** — the `source_is_live`-by-git-pull case. When they pull a newer version of
coordinator-claude, the sentinel in the publish-repo records what HEAD the published content came
from. The classifier can then classify whether a `--force` reinstall from the publish-repo is
safe relative to their local edits.

This is NOT the same as "when was this installed on this machine." An OSS consumer who clones
the publish-repo and runs install separately will get the publish-side sentinel — which records
when the meta-repo published, not when the consumer installed.

### Install-Side (Canonical Per `live-install-drift-audit.md` § `copy_install` Mode)

A downstream consumer's install ceremony invokes `install-sentinel-write` **at copy time**.
The semantic is: **"this live install was installed from source HEAD X."** This is what the
classifier semantically expects when classifying a `--force` re-install: the baseline is
"what SHA was the source at the time the consumer last installed."

Per `live-install-drift-audit.md` § `copy_install` Mode — Mechanism and Rationale, the installer
writes `version.txt` at copy time; the probe compares to `git -C <source_path> rev-parse HEAD`.

**Downstream plugins with their own `copy_install` script** (holodeck, addon-em, future consumers)
are the canonical writers for THEIR install-side sentinel. Coordinator ships the tool; we
recommend (not direct) that consumers invoke `install-sentinel-write` at the end of their copy
step.

### Why the Two Semantics Overlap Only in One Case

The two writer locations produce semantically identical sentinels ONLY when the consumer's
install ceremony is "run `git pull` on the publish-repo." In that case, the publish-time SHA and
the install-time SHA are the same git HEAD, and both sentinels agree. For any other install path
(a downstream `copy_install` script, a separate artifact distribution, a staged install from a
fork), the publish-side sentinel and the install-side sentinel diverge and must be maintained
independently.

**Practical guidance for new downstream consumers:**

1. If you `git pull` the publish-repo directly into your live install: the publish-side C3
   sentinel covers you. No additional wiring needed.
2. If you run a `copy_install` script that copies from a source repo: invoke
   `install-sentinel-write --path <live_path> --source <source_git_root>` at the end of your
   copy step. This is the sentinel the drift probe (`check-plugin-drift.sh`) and the classifier
   (`check-install-divergence.py`) are designed to read.
3. **Closing `live-install-drift-audit.md` Known Limitation #2 for the holodeck trio** is
   install-ceremony work in the holodeck repo, not publish-side work in coordinator. The guidance
   has been sent via the C6 cross-repo memo; holodeck-em lands it with holodeck's implementation
   context.

---

## Cross-References

- [`live-install-drift-audit.md`](./live-install-drift-audit.md) — canonical reference for
  copy_install drift detection primitives; § Known Limitations #2 is the gap this plan closes
  on the publish-side (install-side closure is holodeck-side); § Canonical Primitives documents
  the `[info] no sentinel` and `[warn] version.txt malformed` probe outputs.
- [`install-surface-completeness.md`](./install-surface-completeness.md) — universal rule for
  install-surface writes; § Plugin-spawned state is the established observation the deferred
  extension in § 2 generalizes from; § State-Files / source_is_live caveat is explicitly NOT
  triggered by version.txt (which lives in the published/receiver tree).
- [`cross-repo-handshake-doctrine.md`](./cross-repo-handshake-doctrine.md) — § Carve-out:
  bare-SHA sentinels for content-equivalence (copy_install) names this wiki as the
  canonicalization authority that justifies the bare-SHA exception to the inline-assertion rule;
  this wiki is the forward-reference target of that carve-out.
- [`post-sync-hook-doctrine.md`](./post-sync-hook-doctrine.md) — touched-list constraint for
  per-file synced-content rewrites; does NOT apply to the C3 sentinel-write hook (root-level
  new-file mutation, separate note in § 3 deferred extension above).
