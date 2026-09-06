---
title: CLAUDE.md Surfaces — Which File Is the Global One?
created: 2026-07-22
author: doe-em
status: active
kind: wiki
related:
  - coordinator/docs/wiki/external-plugin-live-resolution.md
  - coordinator/docs/wiki/percolate-setup.md
  - coordinator/docs/wiki/install-surface-completeness.md
  - coordinator/docs/wiki/state-placement-law.md
keywords:
  - CLAUDE.md
  - the (now-removed) meta-repo local-doctrine file
  - global doctrine
  - plugin-dir
  - percolate
  - publish-targets allowlist
  - operator identity
---

# CLAUDE.md Surfaces — Which File Is the Global One?

> Disambiguation wiki for the CLAUDE.md-class files a DoE session can have live at once, and
> the structural traps that make it easy to mix them up. Written after both the PM and the EM
> independently formed a wrong model of "the global file" on 2026-07-22 — no tooling caught
> either error, only reading the files did.

> **`coordinator/CLAUDE.md` does not exist on disk — do not treat it as a live surface.** Its
> doctrine content is split between `global-doctrine/CLAUDE.md` (ALL-AGENTS content) and
> `coordinator/snippets/em-operating-doctrine.md` (EM-only channel). The table row and Trap A
> below are kept so a reader who encounters a stale citation to `coordinator/CLAUDE.md` understands
> where its content actually lives, not because the trap still applies to a live file. The live
> count is **four** surfaces, one trap (Trap B, OSS publication gating, applies to
> `global-doctrine/CLAUDE.md`'s mirror relationship). See `CLAUDE.md § Architecture` (this repo's
> root file) for the current count.

## The (formerly five, now four) surfaces

| File | Bytes | Scope | Load mechanism | Owner |
|---|---|---|---|---|
| `~/.claude/CLAUDE.md` | 28,331 | **Global** — every session on the machine, regardless of cwd | Harness auto-load | Operator, hand-maintained |
| `the (now-removed) meta-repo local-doctrine file` | 10,219 | Global, private (fleet sibling map lives here) | Harness auto-load | Operator, hand-maintained |
| `<repo>/CLAUDE.md` (e.g. `DoE-claude/CLAUDE.md`) | 32,144 | That repo only | Project auto-load, cwd-gated | Repo |
| `<repo>/the (now-removed) meta-repo local-doctrine file` (e.g. `claude-klabauter/the (now-removed) meta-repo local-doctrine file`) | varies | That repo only, private | Project auto-load, cwd-gated | Repo |
| `DoE-claude/coordinator/CLAUDE.md` | **DELETED** | DoE-claude only, and only after a `coordinator/` file is Read — reached no sibling-repo session at all | nested-`CLAUDE.md` lazy load (ordinary ancestor-chain walk on Read, unrelated to `--plugin-dir`) | Retired; content split to `global-doctrine/CLAUDE.md` + `coordinator/snippets/em-operating-doctrine.md` |

> **Figures drift — re-measure before citing.** Every byte count in this table has already gone
> stale twice (2026-07-22 → 2026-07-27, across two different rows, from routine edits by other
> sessions). These five files are hand-evolved and edited independently and often; treat every
> number here as a snapshot at time of writing, not a live value. Re-run `wc -c` on the actual
> paths before relying on a figure for anything load-bearing (e.g. a context-budget argument) —
> don't trust this table's cache.

> **DoE-claude's own the (now-removed) `the (now-removed) meta-repo local-doctrine file` does not exist.** The generic
> `<repo>/the (now-removed) meta-repo local-doctrine file` row above still describes a real, live surface CLASS — most sibling
> repos (`claude-klabauter` included) still split their operating posture into a separate
> the (now-removed) `the (now-removed) meta-repo local-doctrine file` alongside `CLAUDE.md`. DoE-claude itself is the exception: its content is
> merged into `DoE-claude/CLAUDE.md`, so a stale citation of `DoE-claude/the (now-removed) meta-repo local-doctrine file
> § <heading>` resolves against a section of `DoE-claude/CLAUDE.md` instead. This has no bearing on
> `the (now-removed) meta-repo local-doctrine file` (global, still live) or on any other
> repo's the (now-removed) `the (now-removed) meta-repo local-doctrine file` — both rows in the table above are otherwise unaffected.

`DoE-claude/CLAUDE.md` is the same *class* of document as `claude-klabauter/CLAUDE.md` — a **project**
file, not a global candidate, despite DoE-claude being the coordinator doctrine-authoring repo.
**Never copy `DoE-claude/CLAUDE.md` over `~/.claude/CLAUDE.md`** — different classes; if the idea
looks attractive, diff them first. Copying would delete `~/.claude/CLAUDE.md`'s § Owner, §
Communication Style, and First Officer Doctrine — none of which exist in the project file. (Engagement
posture is deliberately absent from `~/.claude/CLAUDE.md` on either side of this comparison — it
renders per-repo into `.claude/em-context.md` instead; see § Known gap below.)

## Trap A — `coordinator/CLAUDE.md` is not plugin-delivered at all; it's nested-`CLAUDE.md` lazy load, DoE-only

<!-- spec backlink: docs/research/spike-verdicts/2026-07-27-plugin-claude-md-delivery.md -->

The believable-but-wrong model this trap used to describe was: "`--plugin-dir` shims
`coordinator/CLAUDE.md` into every coordinator session, fleet-wide." A 2026-07-27 spike
(`docs/research/spike-verdicts/2026-07-27-plugin-claude-md-delivery.md`) falsified that model
directly, with a live cross-repo probe. The corrected model:

**`--plugin-dir` does NOT deliver `CLAUDE.md`.** Per the official plugins-reference docs
(confirmed by `claude plugin validate`'s own warning), a plugin-root `CLAUDE.md` is explicitly
*not* loaded as project context — plugin instructions are meant to ship as a skill instead. This
was never a gap in our tooling; it's documented behaviour we had misread.

**The real mechanism is ordinary nested-`CLAUDE.md` lazy loading** — the same ancestor-chain walk
that applies to any subdirectory `CLAUDE.md` in any project, with zero plugin involvement:

- **Trigger:** the harness loads `coordinator/CLAUDE.md` only when a session **Reads a file
  somewhere under `coordinator/`** — not at session boot, not on Grep, not for an untouched
  sibling directory. Reading pulls in the *whole ancestor chain* of `CLAUDE.md` files above the
  read file, of which `coordinator/CLAUDE.md` happens to be one link.
- **Scope:** this only fires in a session whose **cwd is DoE-claude**. There is no path by which
  reading a file under `coordinator/` from a *different repo's* working tree would pull this file
  in — the ancestor chain a nested-load walks is rooted at the session's own cwd, not at
  wherever `--plugin-dir` happens to point.
- **Consequence — the one that matters most:** `coordinator/CLAUDE.md` reaches **no sibling-repo
  session, ever.** Verified live: a `claude-klabauter` session, launched via the real `claude-doe`
  invocation with the coordinator plugin confirmed loaded (its slash command available), returned
  NOT-PRESENT on a verbatim-recall probe for a sentence that exists only in
  `coordinator/CLAUDE.md`. The plugin loading is real and confirmed; the doctrine text riding
  along with it is not — those are two independent facts this trap used to collapse into one.
- **Durability:** per the harness docs, a nested `CLAUDE.md` does not survive `/compact` the way
  a project-root `CLAUDE.md` does. So even inside DoE-claude, after the first `coordinator/` Read
  has pulled it in, it can silently evaporate on the next compaction — "loaded once" is not
  "loaded for the session."

**Why the old model was believable.** `--plugin-dir` genuinely *does* deliver `skills/`,
`agents/`, `commands/`, `hooks/`, and `lib/` fleet-wide live from this repo (see
`external-plugin-live-resolution.md` — that mechanism is correctly described there and needs no
correction). Every DoE-claude session also happens to Read a `coordinator/`-rooted file almost
immediately (a skill, an agent prompt), so the nested-load fires early enough to look
indistinguishable from a boot-time plugin injection — from inside DoE-claude, the two mechanisms
produce the same *symptom* (doctrine present) by two entirely different *causes* (one fleet-wide
and mechanical, one repo-scoped and read-triggered). The `claude-doe` exec chain itself is
correctly described elsewhere in this wiki and is not in question: `~/.local/bin/claude-doe`
does end in `exec claude --plugin-dir "$DOE_COORDINATOR" …`, and that flag is what delivers the
five surfaces named above — it is simply not what delivers this one.

**Consequence for the fleet, not just for DoE-claude:** sibling-repo EMs (`claude-klabauter`,
`project-rag`, and any other repo running the coordinator plugin) have been operating this whole
time with the coordinator operating doctrine **absent from their context**, regardless of how
long the plugin has been loaded for them. Whatever behavioural consistency the fleet has actually
shown came from each repo's own `CLAUDE.md` and the global `~/.claude/CLAUDE.md`, not from this
file. How coordinator *should* deliver always-on doctrine fleet-wide — a skill (invocation-gated,
not always-on), a `SessionStart` hook emitting `additionalContext` (always-on but a ~40KB payload
per session/subagent), or per-repo `@import` (works today, costs N repos of duplication) — is an
open, unratified engineering question with real tradeoffs on every candidate shape. That's a
`/shape`-then-PM call, not something this wiki resolves.

## Trap B — OSS publication is gated by the publish-targets ALLOWLIST, not `.percolate-ignore`

Percolation (`coordinator/` → the OSS `coordinator-claude` mirror) is governed by **two
independent layers**, and only one of them decides wiki/file *admission*:

- **`coordinator/.percolate-ignore`** — structural leak-denial. It says explicitly, in its own
  header (per DR-080), that it is NOT the boundary deciding which `docs/wiki/*.md` files reach the
  mirror.
- **The per-file ALLOWLIST**, field 7 of the `coordinator-claude|mirror` row in
  `~/.claude/setup/publish-targets.portable`. Verified 2026-07-22, that field is exactly:
  `bin,lib,hooks,skills,agents,commands,docs/wiki/daily-branch-discipline.md,docs/wiki/docs-checker-pre-review.md,docs/wiki/prior-art-checker.md,docs/wiki/rag-bait-conventions.md,docs/wiki/scoped-safety-commits.md,docs/wiki/tiered-context-loading.md,docs/wiki/workday-workweek-cadence.md,.claude-plugin,cockpit-contract/schema`.

`CLAUDE.md` is absent from that field → **`coordinator/CLAUDE.md` does NOT reach the OSS mirror**,
despite being the doctrine every coordinator session runs on. Corollary: this wiki you're reading
is also not on that allowlist, so it does not publish OSS either — it stays DoE-internal doctrine
until someone deliberately adds it.

## The regression of record — cold-install clobber (`~/.claude` commit `6563b3d`)

Underneath the two traps above sits a realised defect, not just a naming confusion. Commit
`6563b3d` in the `~/.claude` meta-repo (2026-07-21, "doctrine: recover rich global CLAUDE.md +
the (now-removed) meta-repo local-doctrine file from .example-doctrine-mirror-repo backup") records a cold install on the Windows PC that
re-initialized `~/.claude` and rendered stripped-down installer TEMPLATES over the evolved
originals — `CLAUDE.md` regressed from a 25.7KB evolved file to a 2.9KB posture seed. It survived
only because an out-of-band `.example-doctrine-mirror-repo` backup happened to exist to recover from.

**This wiki documents the trap; it does not fix the installer.** The installer-side fix (making a
cold install non-destructive to hand-evolved global doctrine) is Piece 3 of the spinoff this wiki
was authored under — out of scope here.

## Known gap — operator identity is not reproduced by any install path

`~/.claude/CLAUDE.md` carries nothing posture-shaped at all — no `render-posture-overlay.py`
managed block, no `## Posture` heading. The engagement-posture overlay renders instead into the
CONSUMER repo's own `.claude/em-context.md`, delivered to that repo's main session only via the
`assert-em-role.py` SessionStart hook's `REPO`-rooted manifest slot — never into `~/.claude/CLAUDE.md`,
which every dispatched subagent also reads and has no business carrying posture prose. § Owner and
§ Communication Style — the operator-identity content that does still live in `~/.claude/CLAUDE.md`
— are reproduced by **nothing** on any install path. A fresh machine install reproduces the
operating doctrine but not the operator. This is a known gap, owned by Piece 3 of the spinoff; it
is not fixed here.

## Quick answer

*"Which file is the global one?"* → `~/.claude/CLAUDE.md` (and its the (now-removed) `the (now-removed) meta-repo local-doctrine file` sibling).
machine-global and never fleet-wide. `coordinator/CLAUDE.md` in particular is narrower than it
machine-global and never fleet-wide. `coordinator/CLAUDE.md` in particular is narrower than it
looks: it isn't even reliably DoE-wide (nested-load only fires after a `coordinator/` Read, and
can evaporate on `/compact`), and it is structurally unreachable from any repo that isn't
DoE-claude — see Trap A above.

## Global doctrine mirror — Piece 2 of the topology spinoff

A sixth surface exists alongside the five above: `DoE-claude/global-doctrine/CLAUDE.md` and
`DoE-claude/global-doctrine/the (now-removed) meta-repo local-doctrine file`, a tracked, byte-identical in-repo mirror of
`~/.claude/CLAUDE.md` and `the (now-removed) meta-repo local-doctrine file`. It is **not** a sixth CLAUDE.md-class
source of instructions — it does not auto-load, it is not `--plugin-dir`'d, no session reads it
as doctrine. It is a passive backup, and it exists for one specific reason: `~/.claude` cannot be
trusted to hold its own history.

**Why a mirror in a different repo, and not "just rely on `~/.claude`'s own git history".** This
spinoff's own challenge note initially argued Piece 2 might be redundant — "`~/.claude` is itself
a git repo with a remote, so a mirror elsewhere is redundancy, not the primary backup." Verified
2026-07-22, that argument does not survive contact with the facts:

- `~/.claude` has only 8 commits, the first (`78ef394`, "chore: initialize Claude Central") dated
  2026-07-20 — one day before the clobber described below.
- At that initial commit, `CLAUDE.md` was **2,945 bytes** — the stripped installer template, not
  the evolved ~27KB file the operator had actually been running under. The repo's history
  therefore *begins from the already-clobbered state*: a cold install re-initialized the git repo
  along with the directory it lives in.
- Neither `~/.claude`'s local history nor its `origin` remote ever contained the evolved doctrine.
  Recovery in commit `6563b3d` (see § The regression of record above) came entirely from the
  `.example-doctrine-mirror-repo` out-of-band backup — a copy living **outside `~/.claude`'s blast radius**. That
  backup was the only survivor; `~/.claude` itself contributed nothing to its own recovery.

The conclusion this drives: a mirror is only worth building if it can **survive a re-initialization
of `~/.claude` itself** — a scenario that already happened once. That rules out anywhere under
`~/.claude`, and it rules out relying on `~/.claude`'s own git remote. It requires a **different
repo with an independent git history**, which is exactly what `DoE-claude/global-doctrine/` is:
even if `~/.claude` is deleted, force-pushed over, or cold-re-installed tomorrow, the mirror's
history in DoE-claude is untouched.

**Direction of truth (load-bearing, do not invert).** `global-doctrine/CLAUDE.md` is
authoritative — it is the **authoring** surface. `~/.claude/CLAUDE.md` is the **derived** live copy
the harness loads. On conflict, `global-doctrine/` wins. The drift probe's `--sync` flag only ever
copies mirror → `~/.claude`; the reverse direction — restoring the tracked copy FROM `~/.claude`
after a mirror loss — is a deliberate manual recovery action, never automated.

> **The tracked copy is where doctrine is authored**, and an enforcement envelope keys on it: the
> `derive-global-doctrine-live-copy.py` PostToolUse hook (re-derives `~/.claude` on every write to
> the tracked file, fail-loud), `coordinator/tests/test_global_doctrine_tracked_copy.py`, and the
> CLAUDE.md admission gate (`hooks/scripts/_claude_md_ledger.py` — `GOVERNED_AUTHORING_SURFACES`
> names the tracked surface). `~/.claude/CLAUDE.md` carries **no byte cap and no heading admission
> ledger**. That asymmetry is the whole argument: an edit made live is an edit that never passed
> the gate.
>
> Automating `~/.claude` → mirror would make the *ungated* live copy a second place doctrine could
> be "corrected" from, laundering an unclassified edit into the authoring copy. The mirror also
> lives in a different repo with independent git history, so a re-initialization of `~/.claude`
> cannot destroy it — it is the original, not the copy.

**Agents never cite the tracked path.** Every agent has already loaded `~/.claude/CLAUDE.md` before
it reaches any skill, and the two files are byte-identical by construction. A skill or agent prompt
that points a reader at `global-doctrine/CLAUDE.md §` is sending them on a multi-hop path
resolution (settings-home → which repo? → subfolder) to re-read text that was structurally
unavoidable at boot — and the path does not resolve at all on an OSS install, where
`global-doctrine/` never ships. Cite the section by name alone (`§ Flag Severity`), never the path.
`guard-prompt-surface-citations.py` is the write-time advisory / detection seam for the general
case; `coordinator/tests/test_prompt_surfaces_cite_resolvably.py`'s ratchet is what actually
enforces it.

**Placement is load-bearing: repo ROOT, never under `coordinator/`.** `coordinator/` is the
percolation SOURCE directory for the OSS `coordinator-claude` publish mirror; the operator's
global doctrine carries personal identity content (§ Owner: name, background, personal framing)
that must never reach that publish target. Verified 2026-07-22 against
`~/.claude/setup/publish-targets.portable`: the `coordinator-claude|mirror` row's per-file
ALLOWLIST (field 7) enumerates only paths relative to `coordinator/` (the declared SOURCE_DIR) —
`bin,lib,hooks,skills,agents,commands,docs/wiki/<enumerated-list>,.claude-plugin,
Cockpit-contract/schema`. A repo-root `global-doctrine/` directory sits structurally outside that
SOURCE_DIR and so cannot be matched by any allowlist entry, publish invocation, or
`.percolate-ignore` pattern rooted there — DoE-claude being a private repo, tracking this content
at the repo root is safe; the OSS mirror is the only real exposure risk, and it is structurally
unreachable.

**Drift probe.** claude-klabauter `coordinator/bin/check-global-doctrine-mirror.py` byte-compares
each mirrored file against its `~/.claude` counterpart, wired into `/workday-start` Step
1.10.63. Silent no-op (exit 0) when `global-doctrine/` does not exist — this probe ships under
`coordinator/bin/` (on the OSS publish allowlist), so it reaches every OSS install, and absence
of the mirror there
is the expected state, not a regression to nag about. On drift it fails loud: both absolute paths,
both byte sizes, a capped `difflib` excerpt, and an explicit pointer to `--sync` as the
remediation (`~/.claude` ← mirror, never the reverse). A mirrored pair absent on **both** sides is
a not-in-play skip, not drift — `CLAUDE.local.md` is the live instance of that case, and treating
it as drift is what made this probe report a spurious hit on every `/workday-start` until
2026-07-31.
