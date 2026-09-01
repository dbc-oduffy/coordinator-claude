# Install command — residue

Rationale, history, worked examples, and troubleshooting stripped from
`coordinator/commands/install.md` to keep that command body to executable
procedure. Organized by the install-doc heading it was cut from.

## You are here / cold-machine bootstrap


`uninstall.md` is the tested, symmetric counterpart — it reverses every
out-of-repo surface this install writes (settings.json hook block, shell
shim/wrapper, machine-local registry keys, venv, `.doe-root` pointer,
`~/.claude/bin/` forwarders, plugin wiring), snapshot-independent. A new
surface added to install gets a matching removal step there in the same change.

## Step Zero — preflight

`repos.claude_klabauter` is a hard precondition `setup.py --preflight` cannot
work around — it calls `_resolve_claude_klabauter_root()` before anything else runs.
This is a prerequisite the coordinator install path itself does not write;
its authoritative writer is `claude-klabauter`'s own installer
(`register_claude_klabauter_root()`), never chained from here. `first-run` can seed it
opportunistically but is interactive/opt-out — don't rely on it.

`--preflight` is a superset of `--check`: manifest-dependency probes AND
environment-prerequisite probes through one tabling + NDJSON emitter. Probe
library: `coordinator_core.install.prereq_probe` (native Python, claude-klabauter),
read-only SSOT that never mutates. An `inconclusive` result is advisory WARN.

**`clone_auth` interactive script:**
```
clone_auth probe: no GitHub auth found.
Offer: run `gh auth login` to authenticate now? [Y/n]
  → Y: runs `gh auth login`; re-probes; proceeds on pass.
  → N: re-run with --accept-no-git-auth to skip this gate, or configure auth manually first.
```
`--non-interactive` with no auth/no `--accept-no-git-auth`: FAIL-LOUD, no TTY
to run the offer (exit-90 spirit, matches the manifest hard-dep non-TTY
pattern). `--check-only` never blocks — reports what would happen only.

**PowerShell host (#03).** `pwsh` 7+ is the only supported PowerShell host.
Windows PowerShell 5.1 (`powershell.exe`) is **out of scope** — not a fallback,
not a compatibility target; a 5.1-only failure never blocks a release. The probe
currently WARNs rather than blocking on absent/below-7 `pwsh` (claude-klabauter
`prereq_probe.py` `probe_pwsh`, severity `advisory`), so nothing yet enforces
this at install.

`normalize-env` is idempotent, consent-gated: enumerates each mutation,
requires explicit per-mutation acceptance, blast-radius-last ordered. Windows:
every mutation backs up, `--restore` reverts. macOS: offers-only except the
single consent-gated bash-login-shell reconstruction. Linux: offers-only.

## Requirements — claude-klabauter detail

`claude-klabauter` is NOT auto-discovered: it's an engine repo with no
`.claude-plugin/marketplace.json` marker, so rung-2 marker-autodiscovery can
never resolve it. Remediation if `claude-klabauter`'s own `scripts/setup.py`
hasn't been run: `machine-local set repos.claude_klabauter /path/to/claude-klabauter`.
`claude-klabauter` is currently private; the maintainer grants access on
request, same model as `project-rag`.

## Structural fork — the three states in full

- **`pristine`** — Claude Code never run here. No caveat needed; nothing to
  merge or collide with.
- **`used-vanilla`** — Claude Code run, but nothing opinionated configured
  (no git, no plugins, no coordinator infra — just session history and/or a
  hand-edited `CLAUDE.md`). Surface a light, non-alarming note:

  > **Existing Claude Code usage detected (no custom setup).** Installing the
  > coordinator on top — your sessions and any `CLAUDE.md` edits are
  > preserved, not overwritten. Re-running is safe. Use `--check-only` to preview.

  Do NOT show the collision/merge warning — there's nothing opinionated to
  collide with, and this state must not read as a clobber risk.
- **`configured`** — opinionated, deliberately-customized home. Surface:

  > **Existing `~/.claude` setup detected.** This installs from zero; merge is
  > yours. Re-running is safe; it skips anything already present. Use
  > `--check-only` to see state without changes.

  Do NOT offer a merge engine or selective-adoption UI.

`track=` is a backward-compat binary alias (`configured → B`, else `A`) for
older callers only — never key new logic on it.

## 1a.0 bash version — full detail

Scripts resolve via `#!/usr/bin/env bash` — the gate reads PATH-resolved
bash, not `/bin/bash`. Not a `--preflight` probe: the Python install path
doesn't source bash, so `setup.py --preflight`'s probe order carries no
`bash_version` entry. The gate lives in the engine's first-run install path,
drives the macOS brew-bash offer, contributes no preflight row. The
`probe-prereq bash-version` subcommand this section once described was never
wired to a caller and was removed — don't reintroduce a reference to it.

`coordinator-safe-commit` uses `local -n` namerefs (4.3+) and hard-aborts on
4.0–4.2 — every commit would fail, hence fail-loud there too, not just <4.

**Login-shell orphan detection (macOS, post-offer).** If
`probe_shell_login_env` reports the login shell is bash but `~/.bash_profile`
lacks `~/.local/bin` (where `claude` lives):

> **claude will vanish in a fresh terminal** because your bash login shell's
> `~/.bash_profile` does not include `~/.local/bin`. This does NOT mean you
> need to change your login shell back to zsh — the existing
> `~/.bash_profile` is simply missing the PATH entry. Run `normalize-env` to
> reconstruct it.

No `chsh` is offered, implied, or executed — this repairs an already-bash
login shell, never creates one. Offer C's `case` statement and
`normalize-env`'s reconstruction share one fixed dedup-marker comment in the
appended brew-shellenv block, so a re-run detects and stands down rather than
duplicating.

**Invoking-shell bash≥4 verification.** The login-shell offers (A/B/C) repair
the login shell; the Claude Code Bash tool's invoking-shell resolution is a
separate, undocumented mechanism (no `settings.json` override exists) that
can still land on zsh or bash 3.2 even after Offer C succeeds. When that
happens, a coordinator lifecycle skill sourcing a bash≥4-guarded lib aborts
mid-flow with an opaque `requires bash >=4 (found unknown)` error — a silent
trap discovered later. Historical example: `coordinator/lib/strangler-facade.sh`,
killed 2026-07-21/22 in the bash-kill campaign; no lifecycle skill sources a
bash-4-guarded lib live any more, but the risk class persists for any future
bash lib. The probe is physics-irreducible — it reports on the shell that
invoked IT, a child process cannot observe the invoking shell's own version —
and stayed claude-klabauter-resident rather than porting.

No SessionStart advisory re-checks drift later (a `chsh` back to zsh, a new
terminal profile) — boot carries only the fast orientation injector. This
install-time check is the sole enforcement point. The durable fix — migrating
guarded-lib `source` callsites behind the `cc_invoke` seam — is tracked on
the engine's Python track, not here.

This step writes no out-of-repo state, so it has no `uninstall.md`
counterpart and is deliberately absent from the install/uninstall
surface-symmetry list — that absence is not a gap.

## 1a.1–1a.3 git steps — rationale

**Git-config hardening.** `gc.auto 0` disables auto-gc entirely, removing
both the detached GC child that orphans `.git/index.lock` on Git-for-Windows
and the foreground repack a killed session could abandon half-written (see
H21, `concurrent-em-hazards.md`); ceremony-triggered `git maintenance run`
plus the stale-lock/tmp-pack reaper CLI replace what auto-gc did.
`core.checkStat minimal` ignores NTFS-unstable `ctime/ino/dev` fields causing
phantom-dirty tree. `gc.auto` is per-repo scoped (global would change auto-gc
in unrelated repos); `core.checkStat minimal` is machine-wide and benign
everywhere. The
writer also neutralizes the Windows git-help browser launch (Git for Windows
ships no `man`, so `git help`/`--help` hijacks the default browser) —
machine-wide, Windows-only, skipped when the operator already set
`web.browser`.

**Operator `~/.claude` git-hook gates.** Installs both legs — sending-side
`pre-commit` gate registry, receiving-side `post-merge`/`post-checkout`
gates. Self-guards to the meta-repo identity, no-ops cleanly when `~/.claude`
isn't a git repo. Today's markers: `check-no-illegal-paths`,
`coordinator-precommit-foreign-platform-check`,
`coordinator-precommit-settings-tracking-check` (sending side),
`coordinator-postsync-marker-resync-check` (receiving side).
This is the OSS-user analogue of `/repo-setup` § 3f.5.5 — `/coordinator:install`
is the surface every operator runs against their own `~/.claude`, while
`/repo-setup` only fires it against scaffolded consumer *project* repos.

**Git-LFS enablement.** Proactive "cover it before they get there" — a
harmless, idempotent global config write even for operators who never clone
an LFS repo (e.g. project-rag-ue-addon, example-game-repo with `.uasset`/`.umap`).
Doesn't depend on `first-run` having run. `git_lfs` preflight row treats LFS
enabled only when BOTH the binary is present AND the global filter is wired
(a bare `filter.lfs.clean` key can survive a partial/aborted install). The
meta-repo `~/.claude` itself LFS-tracks nothing, so no materialization runs
here.

## 1b.1 python3 App-Execution-Alias stub

On Windows, bare `python3` resolves by default to a Microsoft Store
App-Execution-Alias — a 0-byte stub that errors on run and is invisible to
Git Bash, so a bare presence check reads "present" while every invocation
fails. Phase 3's `install-substrate.py` places a real `python3.exe`
(hardlink/copy of console `python.exe`) beside the resolved interpreter and
offers orphan-stub deletion. It does not prepend that directory to PATH, so
precedence over `WindowsApps` is not guaranteed — a known Windows shell-PATH
gotcha, not something this installer step controls. The probe resolves `python3` on PATH: not-found → not_found;
resolves and runs `--version` → ready; resolves but errors on `--version` →
the stub.

## 1c.2/1c.3 pwsh / Windows Terminal — per-platform install commands

- macOS: `brew install powershell` — **formula, not cask** (the legacy
  `--cask powershell` was removed from homebrew-cask; ships as a
  homebrew-core formula depending on `dotnet`). Requires brew.
- Linux: `sudo snap install powershell --classic` if `snap` present, else
  doc pointer (distro package repos vary too much for one command).
- Windows: `winget.exe install --id Microsoft.PowerShell --source winget
  --accept-package-agreements --accept-source-agreements`. New-shell caveat:
  lands under `…\WindowsApps` (or the WinGet `Links` shim dir), NOT on the
  current shell's PATH — report "open a NEW shell," not bare `ready`.
- Windows Terminal: `winget.exe install --id Microsoft.WindowsTerminal
  --source winget --accept-package-agreements --accept-source-agreements`.
  Same new-shell caveat. Absent winget → point at Microsoft Store or
  https://aka.ms/terminal.

## 1d NotebookLM (Pipeline D)

Pipeline D is powered by an external, OSS, user-installed MCP server —
jacob-bd/gemini-notebook-mcp-cli, server name `notebooklm-mcp` — not a
coordinator carrier plugin; nothing in coordinator's own `enabledPlugins`
gates it. `nlm login` (step 2 of the walk) drives a real Chrome window over
the DevTools protocol in a live foreground console — cannot be automated or
backgrounded; the installer hands this step to the operator.

## 1f Global CLAUDE.md integration

`coordinator/CLAUDE.md` doesn't exist; content lives in an EM-only snippet
folded into global doctrine at `~/.claude/CLAUDE.md`. Doctrine reaches the main EM
session via a SessionStart hook when the plugin is enabled, not an `@`
import — see `coordinator/templates/CLAUDE.md.tmpl` § Coordinator Operating
Doctrine ("Do NOT re-add an `@import`"). A stale
`@~/.claude/plugins/coordinator/CLAUDE.md` import should
be flagged for removal — the target doesn't exist.

## Phase 2 — operator identity, full detail

**Schema.** `version: 1` with `operator_name` present → use stored value.
`version:` > 1 → fail-loud, unsupported schema. `version: 1` with
`operator_name` missing, or `version:` absent → treat as absent.
`--reconfigure` forces re-asking regardless.

**Personal-layer seed rationale.** Without this seed, the
`coordinator/templates/CLAUDE.md.tmpl § Flag Severity → global CLAUDE.md §
Flag Severity` cross-reference resolves to nothing (content lives in the
EM-only operating snippet, § How to Decide). The write
primitive (`render-template`'s `--guard-sentinel` flag) owns the
never-clobber decision directly — no richer classifier layer behind it:
absent-or-seed-carrying output → writes (exit 0); non-empty output lacking
the sentinel → refuses (exit 3), preserving hand-authored content across
every re-run.

## Engagement posture capture — full detail

Materializes into the invocation repo's EM-only channel
(`.claude/em-context.md`), never the operator's global `~/.claude/CLAUDE.md`
— the global file is read by every dispatched subagent, and posture prose
about the operator↔EM working relationship has no audience there (a
dispatched subagent has no operator). This is a mandatory gate: asked on
every run lacking a persisted value, interactive or `--non-interactive`
alike. There is no skip-injection mode — opting out means not running the
installer. Persistence exists purely for re-run ergonomics, never to bypass
the first-run gate.

**Full posture question (framed as depersonalized archetypes, never a named
individual — this ships to end users, AC9):**

*"How do you want the coordinator EM to work with you day to day?"*
- **Precision** — "I want to be consulted often and closely, before things
  change, not just told after — whether that means reviewing diffs and
  weighing in on refactor mechanics, or simply wanting to see and approve
  what's about to change for my users before it ships." Fits either a
  hands-on technical founder or a non-technical founder who still wants to
  be asked before a change lands.
- **Default** — "The standard First Officer partnership — the EM acts on
  engineering calls autonomously, surfaces tradeoffs before forks, and
  expects me to engage on planning and product direction." Today's default;
  most operators want this.
- **Substrate-free** — "Brief me at milestones, minimize interruptions,
  surface only ship/product-level gates — I don't want engineering detail in
  my inbox." Fits a milestone-briefed executive who owns the vision, not the
  diffs.

These three anchors select engagement DISTANCE — how closely the operator
wants to work day to day — the only axis in play. They are NOT a
technical-skill selector: an operator who can't read a diff and never wants
to still belongs on precision if they want to be asked before things change.
Picking a farther anchor to avoid engineering detail, when the operator
actually wants closer involvement, routes them to the opposite of their own
preference.

**Conflict handling (Step 3b-3).** Detect-then-fail-loud, never silent-pick
between an identity-file value and a per-repo `coordinator.local.md`
override — surface both values named, stop, don't write the overlay while
unresolved.

**Gitignore append rationale.** The overlay lands inside a working tree that
may be shared, and plenty of projects deliberately track `.claude/`. A
committed `em-context.md` stops being one operator's posture and becomes
everyone's — the EM channel resolves that path for *whoever* opens the repo,
so a teammate's session would silently adopt the posture of whoever installed
first. Same defect this whole channel exists to prevent, displaced from
dispatched subagents to colleagues. `check-ignore` is the right test rather
than grepping `.gitignore` directly — the path may already be covered by a
broader existing rule (e.g. a repo ignoring `.claude/` wholesale), and
appending a redundant line is noise. An ignore rule does not untrack an
already-committed path — check `git ls-files --error-unmatch`, and if
tracked, tell the operator to `git rm --cached` it.

**Reaching repos onboarded later.** `engagement_posture` persists
per-machine; the overlay it drives lands per-repo. A repo onboarded later via
`coordinator:repo-setup` doesn't automatically pick up the persisted
posture — the expected route is for repo-setup to render the overlay itself
at onboarding, reading the already-persisted value, no re-asking. A later
posture change updates only the repo the operator is standing in; repos
onboarded earlier keep their prior overlay until something re-renders them —
a known, bounded gap (a stale overlay is still valid, just not current), not
corruption. The helper swaps its managed block in place rather than
appending, so re-rendering never produces a duplicate.

## Phase 3 — machine-local substrate, full detail

**Install-substrate helper.** Deliberately NOT a settings-home forwarder —
it's the step that WRITES those forwarders, so it can't depend on one
existing yet. Preserves operator-customized files with one-line notices;
skips Windows checks on non-Windows. Installs 6 bin/ artifacts (3
`machine-local`, 3 `claude-home` — shims prevent "Select an app" pickers on
extensionless scripts).

**`claude` CLI on PATH.** Closes the most common desktop-app onboarding
failure: installing plugins inside the Claude Code desktop app, then opening
a terminal and finding `claude` unrecognized (the CLI dir was never on the
shell PATH).

**Install-health orchestrator.** Iterates `bin/install-health/*.sh`
lexicographically, each in an isolated subprocess, aggregates the failure
count — does NOT abort on first failure (partial completeness beats total
bail). Adding a new completion script is a directory drop, no doc edit
required. Ownership split: the orchestrator and its glob-wiring contract stay
doctrine-plane; individual drop-ins are engine-plane. The two bash drop-ins
(`check-windows-ssh-binary.sh`, `ensure-python3-exe-shim.sh`) were killed
outright (PM directive: delete first, memo the engine team to cover the
replacement) rather than held pending a port.

**Windows Defender exclusion offer.** Measured `bash.exe` spawn p90 285ms →
19.5ms with process exclusions on the hot dispatch path. This is a genuine
security-posture tradeoff, not a pure win — a compromised copy of an
excluded interpreter would execute unscanned. Default is DECLINED; skips
silently on non-Windows, on missing pwsh, or when not elevated. Rollback:
`Remove-MpPreference -ExclusionProcess "<path>"` (elevated) per excluded
path — a no-op on a path never excluded.

**Venv provisioning (Step 6).** `bin/ensure-coordinator-venv.sh` doesn't
exist — provisioning is native, in-process inside
`coordinator_core.install.substrate`'s `_c10a_steps` (via `ensure_venv`),
already run as part of Phase 3 Step 1. Built at install time, not deferred to
first bin invocation — stdlib-only hot-path bins (`mint-deliverable-id`,
`coordinator-doc-new`) run on bare system python and never touch the pin;
only the dependency-bearing surface (`pydantic`/`psutil`-backed ops)
resolves through it. Remediation for a broken
venv (e.g. doctor probe P-5): re-run Phase 3 Step 1 — `_c10a_steps` is
idempotent and mutex-protected; there's no narrower venv-only flag.
`_c10a_steps` retains a fallback venv with a WARN when one exists, failing
hard only when no safe fallback is available.


**3.5c settings.json hook block.** Wires all `type: command` entries from
`hooks.json` (skipping `mcp_tool` entries — in-process ops, not settings.json
rails) with baked registry-absolute paths into the doctrine-plane clone.
Idempotent — re-running over an already-seeded `settings.json` produces a
no-op diff. Exit codes (preserved from the retired trampoline, never
conflated): `0` success (incl. kill-switch no-op), `1` generator business
error, `3` CLAUDE_KLABAUTER_ROOT/import transport failure — an outage must never be
misread as success or a business error. **Boot semantics:** `settings.json`
hook definitions hot-reload mid-session, but a SessionStart hook fires only
at boot — an already-running session won't fire a newly-seeded one. Do NOT
imply SessionStart hooks fire mid-session; that false claim has misled
installers before.

**3.5c-2 marketplace enabledPlugins seed.** Merge-never-clobber against the
effective merged view (`settings.json` ∪ `settings.local.json`) — an
explicit `true`/`false` on a key in either file wins, the seeder never
overwrites it. Seeds enablement only — never runs a marketplace-add, and
isn't evidence the plugin is registered: `enabledPlugins[...] = true` can be
true while the named plugin was never added to a marketplace and has no
manifest/commands/hooks reachable, which reads as "installed" to a
membership check while the SessionStart hook never runs and the daemon never
autostarts.

**3.5d thin `~/.claude/plugins/` shape.** Under the maximalist shape,
`~/.claude/plugins/` holds pointer/config entries and harness-native `bin/`
artifacts — it does NOT hold plugin source bytes. Byte-copying plugin source
to `~/.claude/plugins/coordinator-claude/` is the failed
directory-marketplace shape (runtime-proven FAIL) — don't do this.
`settings.local.json` hooks do NOT fire (runtime-proven).

**Sandbox clean-install test harness** (`bin/install-sandbox-check.py`)
validates in two tiers: filesystem tier (automated — thin shape, cloned dir,
wrapper, hook block, no byte-copy) and running-in-Claude-Code tier (deferred,
hardware/editor-gated — live skill/agent resolution via `--plugin-dir`, hooks
firing at boot, `CLAUDE_PLUGIN_ROOT` unset). The second tier requires a real
Claude Code boot against the sandbox and cannot run inside a subagent — the
EM or PM must launch interactively to complete it.

## Step 7.5 — install singularity gate

Two recognized canonical shapes: pre-cutover (`~/.claude/plugins/coordinator-claude`)
and maximalist post-W4.2 (doctrine-plane clone via
`plugin.mirrors.coordinator-claude.live_path`, with
`~/.claude/plugins/coordinator-claude` absent — the live_path is the sole
reachable tree). In both cases exactly one distinct canonical tree is
expected; a stray second tree (a rogue `~/coordinator-claude` clone, a stale
worktree) is always an accidental split. Also catches a doubled
`.claude/.claude` venv pin and a `.claude`-suffixed `CLAUDE_HOME`. A single
explicitly-exported `COORDINATOR_CLONE`/`COORDINATOR_ROOT` dev-loop override
is exempt. This is the install-time twin of doctor probe P-18.

## Phase 4 — meta-repo doctrine, gitignore probe rationale

Probes all three of `coordinator-setup-state.yaml`, `settings.json`, and
`bin/` — not just the first — since the latter two break a second machine
rather than merely clutter it. A gitignore rule alone does not fix an
already-tracked path (git keeps updating whatever is in the index
regardless), so when the offer is accepted, also check
`git ls-files --error-unmatch` per newly-ignored path and offer
`git rm -r --cached` where tracked — report the "ignore added but still
tracked" case explicitly rather than `covered`, since an inert rule reads as
protection while the leak continues. The installer never creates a remote or
pushes — that's the operator's deliberate call, not a setup side effect, on
a directory that may still contain untriaged per-machine state.

## Phase 5 — project-local, fast_test_cmd detail

Run by `/workday-complete` Step 1 and `/workweek-complete` Step 2 via
`cs_resolve_fast_test_cmd`. Resolution order: `COORDINATOR_FAST_TEST_CMD` env
var → the key → skip-with-notice. Must be a single command — no
`&&`/`;`/pipe chaining; multi-step validation goes in a wrapper script that
accumulates exit codes explicitly, so a mid-list failure still returns
non-zero and later runners still run.

## Phase 6 — optional steps, detail

**1Password GitHub auth.** Wires GitHub auth + SSH commit signing through the
1Password SSH agent (port 443, `op-ssh-sign` signing) — the recommended
standard for interactive dev machines. Fully opt-in, no-ops cleanly on
machines without 1Password. Headless machines should keep token HTTPS
(`gh auth setup-git`) instead. Backs up `~/.ssh/config` before editing and
verifies `git ls-remote` before keeping a remote change.

**Persona customization.** Customizing is reversible by re-running this
install step. Exclude claude-klabauter's `coordinator/bin/publish-time-transform-py`
from search-replace — it carries the canonical `NAME_TO_ROLE` table and must
not be altered.

**Percolation setup.** A repo is a percolation source when
`coordinator/bin/publish.py` exists AND a `setup/` directory exists. Target
registry resolution order: `setup/publish-targets.portable` (primary) →
machine-local registry → legacy `setup/publish-targets.sh`.

## Phase 7 — status report, terminal-message gate

A driver (human or autonomous agent) reading the terminal output must not be
able to come away believing the install is fully complete while orientation
is outstanding — the closing message must foreground the outstanding
restart+walkthrough step while `orientation` is `PENDING`, and only switch to
plain success framing once `orientation_completed` is recorded. This is the
enforcement half of "elective-when, not optional-whether" — skipping the
guided tour is a legitimate in-the-moment choice, but the heading and closing
message must not read as "skip freely, no cost."

The guided tour (four movements — Orient, Make it yours, Test drive, Point it at a project) is a
conversation calibrated to the operator's background, not a recital: cover
First Officer doctrine, the plan→enrich→review→execute→review pipeline, the
reviewer personas, workday/workweek cadence, and where doctrine lives; then
co-author `~/.claude/CLAUDE.md` with the operator rather than dumping the
whole customization menu; then run `/workstream-start` on a real repo through
a small real plan to close the loop; then close by onboarding their first
project — `/coordinator:repo-setup` for an existing repo,
`/coordinator:new-project` for a new one. The tour does not end without one
of those two having run. If the operator would rather learn by
doing, point them at `/workstream-start` and stand down gracefully.

## Engagement posture — exact question text

*"How do you want the coordinator EM to work with you day to day?"*

- **Precision** — "I want to be consulted often and closely, before things
  change, not just told after — whether that means reviewing diffs and
  weighing in on refactor mechanics, or simply wanting to see and approve
  what's about to change for my users before it ships."
- **Default** — "The standard First Officer partnership — the EM acts on
  engineering calls autonomously, surfaces tradeoffs before forks, and
  expects me to engage on planning and product direction." Today's default;
  most operators want this.
- **Substrate-free** — "Brief me at milestones, minimize interruptions,
  surface only ship/product-level gates — I don't want engineering detail in
  my inbox."

These three anchors select engagement DISTANCE, never technical skill — an
operator who can't read a diff and never wants to still belongs on precision
if they want to be asked before things change.

## Phase 7 — exact closing-message text

While `orientation` is `PENDING`:

> "Setup wired your environment. Next required step — restart Claude Code,
> then say 'walk me through the coordinator' to finish tailoring it to you."

Once `orientation_completed` is recorded:

> "You're all set up — say 'walk me through the coordinator,' or tell me what
> you want to build."

**Standing sign-off note**, included verbatim in every next-steps block (not
`--check-only`):

> Your `~/.claude` is the surface you evolve — git-track it and back it up;
> the coordinator plugin source lives in the doctrine-plane clone
> (`repos.doe_claude`), resolved live via `claude-doe`. Bare `claude` works
> via the installed `claude()` shim — it reads the `.doe-root` pointer and
> delegates to `claude-doe` automatically. If not yet active in your current
> shell, run `claude-doe` directly or open a new terminal. Never copy plugin
> source into `~/.claude/plugins/`.

**Bootstrap offer**, interactive, not `--check-only`, when
`~/.claude/working-repos.yaml` has N>0 repos: *"Or, if you have a project
ready: `/coordinator:repo-setup`."*

## Per-step status-row vocabulary (bookkeeping detail, not judgment)

Every step in the body reports a status row into the Phase 7 summary table.
The exact value-set per step (e.g. `doe_clone: ready | cloned | would clone |
skipped | failed`) is mechanical output-to-label mapping the tool itself
already prints or implies from its exit code — not restated per step in the
body. Two rows worth flagging for a reader assembling the table by hand:

- `home_state: <pristine|used-vanilla|configured>` is always the FIRST row
  (from the structural-fork probe).
- `orientation: PENDING | completed | skipped (--check-only)` is mandatory in
  every non-`--check-only` run — never silently absent.
