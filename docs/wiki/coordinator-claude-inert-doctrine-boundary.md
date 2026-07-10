# coordinator-claude: the inert/executing boundary

> **Purpose:** this page is the durable reference for what the `coordinator-claude` OSS
> consumer bundle is allowed to ship. Every future percolation/publish change to
> `coordinator/.percolate-ignore` or `coordinator/templates/setup/publish.sh` should consult
> this classification before adding or removing a path from the consumer bundle — it exists so
> the boundary rule is looked up, not re-derived, each time someone touches the publish seam.
> Spec backlink: `archive/specs/2026-07/2026-07-09-v3split-02-coordinator-claude-inert-doctrine-packaging.md`
> (chunk C1; boundary manifest is AC1/AC5). <!-- Review: code-reviewer — plan was archived
> mid-session by fleet automation; repointed from the docs/plans/ path to its archive location. -->

## Boundary classification

### Background

The `coordinator-claude` consumer bundle is what a marketplace consumer receives under
`~/.claude/plugins/coordinator-claude/` after a publish. Today that publish byte-copies the
**full** coordinator source tree modulo `.percolate-ignore`'s narrow, specific exclusions
(test dirs, a couple of identity/provenance scripts, two UE bootstrap scripts) — it does not
exclude `bin/`, `hooks/`, or `lib/` as a *class*. The result is that a consumer install carries
~620 executing scripts (`*.sh`/`*.py`/`*.js` under `bin/`, `hooks/`, `lib/`, plus extensionless
shebang executables) that the consumer never needs and should not host, per the wave-0 gate's
settled two-path architecture: DoE/contributors resolve coordinator source live via
`--plugin-dir` (outside `~/.claude`); consumers get a marketplace byte-copy that is
**inert doctrine only**.

This section enumerates every top-level path class the consumer publish currently emits and
classifies each into one of three buckets, with the one-line rule that produced the label.

### The three-way taxonomy

**(a) INERT DOCTRINE** — harness-discovery-resolved markdown/JSON/config that the Claude Code
harness *loads and reads*, never executes as a program:

| Path | Why inert |
|---|---|
| `skills/` | Skill markdown + supporting assets; harness reads `SKILL.md` frontmatter and body, never `exec`s it. |
| `agents/` | Subagent persona markdown; loaded as prompt text. |
| `commands/` | Slash-command markdown; loaded as prompt text. |
| `.claude-plugin/plugin.json` | Minimal manifest (name/version/description/author/repository/keywords) — confirmed on disk to carry no `hooks`/`bin`/`commands` fields; pure metadata the harness parses, not a script. |
| Top-level doctrine `*.md` (`CLAUDE.md`, `routing.md`, `capability-catalog.md`, `capability-catalog.example-game-repo.md`, `em-operating-model.md`, `README.md`, etc.) | Prose the harness or the model reads for context; no execution semantics. |
| `docs/wiki/` | This very page and its siblings — reference doctrine, read-only. |

**Rule:** if the harness's *only* interaction with the file is parse-and-load (frontmatter,
JSON, prose) and the file is never handed to an interpreter or invoked as a command, it is
inert doctrine and belongs in the consumer bundle.

**(b) EXECUTING MACHINERY** — files that run as programs, under any of the three
top-level directories the coordinator source tree uses for tooling:

| Path class | Detection |
|---|---|
| `bin/*.sh`, `bin/*.py`, `bin/*.js`, `bin/*.ps1`, `bin/*.cmd` | Extension-glob: these extensions are unambiguous interpreter targets. |
| `hooks/*.sh` (and other extensions per the same glob set) | Same — hook scripts the harness invokes at lifecycle points declared in `hooks/hooks.json`. |
| `lib/*.sh` (and other extensions) | Same — shared shell/script libraries `source`d by `bin/`/`hooks/` scripts. |
| Extensionless shebang executables, e.g. `coordinator/bin/cross-repo-memo`, `coordinator/bin/coordinator-doc-new`, `coordinator/bin/claude-doe`, `coordinator/lib/claude-home/claude-home` | Verified present on disk 2026-07-09, each `chmod +x` with a `#!` first line. Extension-glob alone MISSES these — an extensionless-shebang sniff (`head -n1 file | grep -q '^#!'` over dotless basenames) is required as the second detection pass. This is why AC2 mandates both passes: extension-glob is a necessary but not sufficient detector. |

**Rule:** if the file is ever handed to an interpreter (`bash file.sh`, `python3 file.py`,
`node file.js`, or invoked directly via its executable bit + shebang), it is executing
machinery. A consumer bundle carrying these ships code that either does nothing useful (no
runtime that shells out to it) or — worse — becomes the execution-under-`~/.claude` surface
the wave-0 gate flagged as the risk to avoid.

**(c) AMBIGUOUS-CONFIG-IS-DATA** — inert data/config files that are, in isolation, harmless
non-executing JSON/TOML/markdown/text, but are physically colocated *under* a machinery
directory (`bin/`, `hooks/`, `lib/`) as an adjunct to the scripts that consume them.

**The resolving rule, stated explicitly:** such data strips **WITH** its machinery. It is an
adjunct to code that is gone once the machinery class-strip lands — it carries no standalone
consumer value, because nothing in the consumer bundle will ever read it once the script that
consumed it is absent. This is not a "keep it just in case" case; it is a "the only reader of
this file no longer ships" case.

Verified examples on disk (2026-07-09, each confirmed to exist before citing here):

| Path | Confirmed | Consumed by |
|---|---|---|
| `coordinator/bin/doctor-probes.toml` | `-rw-r--r-- 19636 bytes` | a `bin/` diagnostic script (machinery-adjunct config) |
| `coordinator/bin/lib/model-pricing.json` | `-rw-r--r-- 814 bytes` | a `bin/` cost-estimation script |
| `coordinator/bin/example-orchestration-hub-4th-class-ref-manifest.md` | `-rw-r--r-- 22767 bytes` | a `bin/` reference-resolution script |
| `coordinator/bin/repomap/requirements-repomap.txt` | `-rw-r--r-- 70 bytes` | a `bin/repomap/` Python tool's pip requirements |
| `coordinator/hooks/hooks.json` | `-rw-r--r-- 16831 bytes` | the harness hook-discovery manifest — references ~53 hook script entries under `hooks/`; once `hooks/` strips, this manifest would declare hooks pointing at absent scripts, so it must strip too (this is the AC3 manifest-reconciliation case, not a free pass — see below) |

**Reconciliation note on `hooks/hooks.json` specifically:** this file is doubly disqualified —
it is both physically under the stripped `hooks/` directory (rule above: strips with its
machinery) AND, independently, a dangling-reference hazard if it somehow survived the
directory strip while its referenced scripts did not. Both reasons converge on the same
outcome: it must not ship. `plugin.json`, by contrast, needs no reconciliation — verified on
disk to carry no `hooks`/`bin` fields, so there is nothing in it that could dangle.

### The protected-inert-dir-under-machinery-name rule

A directory can share a machinery basename (`bin`, `hooks`, or `lib`) while still being
consumer doctrine that MUST survive the strip. The verified example:

**`skills/new-project/templates/next-app/src/lib/`** — this is a Next.js project template
bundled inside the `new-project` skill. Its path happens to end in `lib/` (a Next.js
convention for shared frontend utilities), but it has nothing to do with coordinator's own
`lib/` tooling directory. It is inert doctrine (a template file a skill hands to a
scaffolded project) that lives several levels below the top-level `skills/` root. Confirmed
present on disk 2026-07-09 (`utils/` subdirectory under it).

**This is exactly why the machinery-exclusion mechanism must be root-anchored, not
basename-anywhere.** A naive `.percolate-ignore` rule of bare `lib/` (no leading slash) matches
`is_ignored()`'s existing any-depth semantics — `rel_path == */lib/*` — which would also match
`skills/new-project/templates/next-app/src/lib/*` and silently strip an inert template dir as
collateral damage. The fix (tracked separately as chunk C2a of this same plan) is to extend
`is_ignored()` with a **leading-slash root-anchor form**: a pattern written `/bin/` matches
*only* `rel_path == bin/*` — the plugin's own top-level machinery directory — never `*/bin/*`
at arbitrary depth. Bare `dir/` (no leading slash) keeps its existing any-depth semantics
unchanged; the root-anchor form is additive, not a redefinition of prior entries. The consumer
bundle's exclusion of `bin/`, `hooks/`, `lib/` (chunk C2 of this plan) uses this root-anchored
form (`/bin/`, `/hooks/`, `/lib/`), never the bare basename-anywhere form, so that
`skills/new-project/templates/next-app/src/lib/` and any other skill-embedded dir that happens
to share a machinery basename survive intact.

**Rule, stated once for lookup:** basename collision with a machinery directory name is not
sufficient to classify a path as machinery. Only *root position* (the path IS the plugin's
own top-level `bin/`, `hooks/`, or `lib/`) makes a directory a machinery directory subject to
the strip.

### Summary table

| Class | Ships to consumer? | Example |
|---|---|---|
| (a) Inert doctrine | Yes | `skills/`, `agents/`, `commands/`, `.claude-plugin/plugin.json`, top-level `*.md`, `docs/wiki/` |
| (b) Executing machinery | No | `bin/*.sh`, `hooks/*.sh`, `lib/*.sh`, extensionless shebang executables (`bin/cross-repo-memo`, etc.) |
| (c) Ambiguous-config-is-data | No — strips with its machinery | `bin/doctor-probes.toml`, `bin/lib/model-pricing.json`, `bin/example-orchestration-hub-4th-class-ref-manifest.md`, `bin/repomap/requirements-repomap.txt`, `hooks/hooks.json` |
| Protected inert dir under a machinery-shaped name | Yes — root-anchor protects it | `skills/new-project/templates/next-app/src/lib/` |

## Settled wave-0 finding

The wave-0 "cheap empirical read-vs-execute probe" that this plan's stub asked for is
recorded at `state/roadmap/v3split/wave-0-guard-probe-finding.md` — but that file lives
under `state/roadmap/`, a roadmap-substrate directory that does not publish or percolate
to any consumer surface. This wiki page is the durable public record of the finding; the
roadmap file is the working note that produced it.

**The finding, summarized:**

The Anthropic self-modification alert is real and Anthropic-side. It fires when Claude
edits its own settings/config under `~/.claude` — an agent-authored live edit to the
harness's own configuration surface. This is a **distinct** mechanism from local Claude
Code permission prompts (the everyday interruption that `bypassPermissions` silences):
bypass turns off the local permission firewall, it does **not** turn off the server-side
self-modification alert. The two are frequently conflated; they are not the same guard.

This distinction resolves into the two-path architecture this plan packages:

- **DoE / contributors** resolve coordinator source live via `--plugin-dir` — the doctrine
  source (CLAUDE.md, skills, hooks, bin) lives in the DoE git repo, **outside** `~/.claude`.
  Live-editing it during a session is editing a normal repo, not Claude changing its own
  `~/.claude` settings, so no alert fires.
- **Consumers** get a marketplace byte-copy of **inert doctrine only** (skills/agents/docs;
  no executing hooks/bin). The install is a one-time harness operation (`/plugin install`),
  not Claude self-editing; consumers consume the doctrine, they don't live-edit it — no
  self-modification surface, and (per the boundary classification above) no
  execution-under-`~/.claude` surface either.

## Read-vs-execute methodology

The stub's proposed method for settling the guard question was a **provocation
experiment**: deliberately drop an inert markdown file and an executable script under a
scratch `~/.claude/plugins/` path, and observe whether the guard fires on read/list
access alone vs. only on execution.

**This provocation experiment was deliberately NOT run.** The method itself — writing to
and executing under `~/.claude` to see whether the guard trips — is exactly the class of
action the whole effort exists to avoid triggering. A "scratch" subpath does not escape
this: the monitored surface is `~/.claude` as a whole, not a subpath carve-out.

Instead, the question was settled via two non-provocative inputs:

1. **PM firsthand evidence** — direct operator knowledge of what the self-modification
   alert actually fires on (self-edit of settings, not read/list access).
2. **The accepted 2026-07-08 alert-surface escalation** —
   `cross-repo/archive/2026-07-08-example-market-data-repo-em-install-batons-dotclaude-alert-surface-escalation.md`,
   `status: actioned`, `decision: accepted` — which established `~/.claude` as a
   monitored surface where even reads/writes generate noise, and drove the
   `install-baton-rendezvous-off-dotclaude` spinoff to move routine workflow off
   `~/.claude` entirely.

Reading these two together, and correcting the initial over-broad any-access reading
against the PM's firsthand distinction (self-modification vs. permission-prompt), settled
the classification without ever running the provocation itself. This is the
methodological point worth recording: **when the experiment to answer a question would
itself cause the harm the question is trying to avoid, the answer is settled by
firsthand evidence and existing accepted doctrine, not by running the experiment.**

## accept-edits amplification

**Question:** does `accept-edits`-mode sensitivity change the consumer-bundle picture —
i.e., does a more permissive local mode widen the set of consumer-side risks this plan
needs to guard against?

**Answer: no change to the inert-doctrine consumer bundle decision.** Consumers neither
self-modify `~/.claude` config nor execute the inert bundle — the marketplace byte-copy
is parsed/loaded doctrine (skills, agent prompts, docs), never handed to an interpreter
(see the Boundary classification above). `accept-edits` sensitivity governs how
permissively a *live, executing* session treats file writes and command execution; it has
no purchase on a bundle that contains no executing surface to begin with.

Where `accept-edits` amplification IS a live concern is the **DoE session itself** —
contributors editing coordinator source live via `--plugin-dir`, where `accept-edits`
governs how much friction stands between the agent and a self-modifying edit. That
concern is handled by the DoE bypass posture (the local permission firewall discussed in
§ Settled wave-0 finding above), not by anything this plan's consumer-bundle packaging
controls. Keep the two surfaces distinct: DoE-session amplification is a bypass-posture
question; consumer-bundle packaging is a "does the bundle execute at all" question, and
the answer to the latter is no regardless of `accept-edits` mode.

## Prior-art corroboration

Two independent pieces of corroborating evidence, beyond the wave-0 finding itself, that
the executing-machinery exclusion (bucket (b) above) is the right call:

**(a) `bin/` exclusion incidentally closes a narrow existing percolation.**
`coordinator/bin/publish-time-transform.sh` currently DOES percolate today as part of the
`bin/` tree — it is invoked by a meta-repo-side wrapper hook at
`setup/percolate-hooks/coordinator-claude/post-rsync/10-transform.sh`. This is a
dev-tool script (a publish-time source transform), not consumer-facing doctrine, and it
has no business shipping in a consumer's `~/.claude/plugins/coordinator-claude/`. Because
this plan strips `bin/` as a class rather than enumerating individual scripts, this one
narrow prior percolation closes as a side effect of the class-strip — it did not need its
own separate carve-out or exclusion rule.

**(b) A second, independent reason `--plugin-dir` is unfit for consumers, beyond the
self-modification alert.** Even setting the alert question aside entirely: plugin-declared
hooks do **not** fire under `--plugin-dir` resolution at all — this is a confirmed harness
bug, tracked upstream as bug #38699, documented in
`coordinator/docs/wiki/external-plugin-live-resolution.md`. This means `--plugin-dir` was
never a viable consumer delivery mechanism regardless of the alert-surface question — a
consumer install resolved via `--plugin-dir` would silently lose all hook-driven behavior.
The two reasons are independent and mutually reinforcing: the self-modification alert
rules out `--plugin-dir` for consumers on a monitoring-surface basis, and bug #38699 rules
it out again on a pure functionality basis. Either alone would be sufficient; together
they leave no ambiguity that consumers need the marketplace-byte-copy-of-inert-doctrine
path, not live `--plugin-dir` resolution.

## v3split-06 soft-seam

Cluster-2's v3split-06 chunk contains a selector else-branch that validates its consumer
resolution logic against this inert-doctrine package — i.e., once this plan lands, v3split-06
exercises the packaged consumer bundle as part of its own selector-correctness check.

**This dependency is validation-time, not a blocking build gate on this work.** v3split-02
(this plan) does not wait on v3split-06, and v3split-06's validation pass is downstream
consumption of this plan's output, not a precondition this plan must satisfy before
shipping. The seam is soft: v3split-06 will validate against whatever inert-doctrine
package exists on disk when it runs, and this plan is what makes that package correct to
validate against — but the ordering is "this ships, then that validates," not "that must
pass before this ships."
