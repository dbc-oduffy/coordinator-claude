---
name: percolate
description: "Dry-run, then confirm-publish files to a repo target, gated by CI."
triggers:
  - /percolate
  - percolate
  - publish to publish repo
  - push to publish repo
  - sync meta to publish
  - ship plugin updates
argument-hint: "<target>"
version: 1.0.0
---

# /percolate — Publish Files to a Publish-Repo Target

Wraps the existing `publish.py` + publish-repo CI gate into a single deterministic invocation: dry-run first, PM-confirm when changes are significant, real run, optional CI smoke, unified summary. Per-target transform/inject/guard phases are declared in `setup/percolate-hooks/percolate-store.yaml`'s `hooks:`/`inject:`/`guards:` entries and dispatched in-process by `publish.py` against `coordinator_core.percolate.engine` at the corresponding boundaries — this skill does not name specific phases; it runs whatever's declared for the target.

**Announce at start:** "Running `/percolate <target>` — dry-run → confirm → publish."

## When to Use / When NOT to Use

**Use `/percolate` when:**
- Publishing files from a working source tree to a registered publish-repo target (any name listed in your `publish-targets.portable`).
- You want a dry-run diff + PM-confirm gate before any real rsync.
- You want CI smoke to run automatically after publish.

**Do NOT use `/percolate` when:**
- Publishing ALL targets at once — run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-publish"` directly (no target argument) for multi-target. (`publish.py` self-bootstraps its own `sys.path` off `Path(__file__)` — see its module docstring — so no external `PYTHONPATH` juggling is needed when it's invoked via the settings-home forwarder.)[^1]
- You need to edit `publish-targets.portable` or add a new target — Branch 0 will walk setup automatically. Manual edit of `publish-targets.portable` also works.
- You want to commit or push changes in the publish repo — this skill does not manage the publish repo's git state.

## Step Sequence

### Branch 0 — First-Run Setup (idempotent gate)

**Run this branch before Step 1 on every invocation.** It silently skips when the target is already fully configured; it walks setup when any piece is missing.

**Gate check — both conditions must be true to skip:**

1. `<target>` argument is provided AND appears in the resolved target set (`setup/publish-targets.portable`, resolved via `coordinator/lib/percolate/targets.py`'s `load_targets`).
2. `<source_dir>/.percolate-ignore` exists (resolve `<source_dir>` via `load_targets`, same mechanism `publish.py` itself uses).

Per-target hook subdirectories under `setup/percolate-hooks/<target>/` (`pre-rsync/`, `post-rsync/`, `pre-ci/`) are NOT gated here — they're vestigial now that the percolate engine consumes the declarative `percolate-store.yaml` and runs the pre-ci guard inside `publish.py` rather than via shell hook scripts.

Run the gate check via `percolate-gate`'s `branch0-gate` subcommand — it resolves the target row through the engine's own `load_targets` and confirms `.percolate-ignore` presence: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/percolate-gate" branch0-gate <target> --percolate-root "$PERCOLATE_ROOT"` (`$PERCOLATE_ROOT` is resolved in Step 0.5, below — run that step first if it isn't already set).

On success the command prints `CONFIGURED:<source_dir>` and exits 0 — capture `<source_dir>` for reuse later (Step 2a's coverage-drift scan resolves the identical path, so there's no need to re-derive it). On any failure it exits 1 and prints one reason line per failed check: `MISSING_TARGETS` / `MISSING_TARGET_ENTRY` / `MISSING_IGNORE`.

`CONFIGURED` = the command printed `CONFIGURED:<source_dir>` and exited 0. Any other output means walk setup.

**On `CONFIGURED`:** silent skip — proceed directly to Step 1 (Pre-Flight).

**On any other output:** walk `percolate-setup-procedure.md` (this skill's own directory — a sibling of this file) inline, following its Steps 1–5. After the setup procedure completes, continue to Step 1 below.

That sidecar is the single source of truth for the interactive procedure (target registration, `.percolate-ignore` audit-and-classify, grey-zone `AskUserQuestion`, hook scaffolding, and drift detection). Do not duplicate its steps here — walk it inline.

---

### Step 0.5 — Resolve PERCOLATE_ROOT

**Run this once per invocation, before Step 1.** Every subsequent step resolves `setup/` relative to `PERCOLATE_ROOT` (the DoE-claude clone root), not a hardcoded `~/.claude` literal — this skill runs correctly both from a repo-local percolate-root clone and from a shared `~/.claude` install.

Resolve it from the `.doe-root` pointer and assign the result to `PERCOLATE_ROOT`: read `${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/machine-local/.doe-root` (settings-home rung), falling back to `${CLAUDE_HOME:-$HOME}/.claude/.doe-root` when the first is missing or empty. Fail loud if the result is empty or not a directory on disk: re-run `coordinator:install`.

`PERCOLATE_ROOT` holds the DoE-claude clone root; every `setup/...` path referenced in Branch 0 and Steps 1/2/2c/2d/4/5/5a below is `"$PERCOLATE_ROOT/setup/..."` — not a literal `~/.claude/setup/...`.

Every `coordinator/bin/...` CLI invoked below (`percolate-gate`, `publish`) is reached directly through the settings-home forwarder seam (`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/<cli>"`) — no separate claude-klabauter root resolution is needed for those calls; the forwarders self-bootstrap. The one exception is the peer-repo-name extension in Step 2c, which calls the claude-klabauter-resident `coordinator/lib/coordinator-state-root.py` — a `lib/` resolver, not a forwarded `bin/` CLI, so it is **not** reachable via the settings-home seam. That step resolves the claude-klabauter root via the standard `repos.claude_klabauter` registry lookup (`$REPO_CLAUDE_KLABAUTER`, or `machine-local get repos.claude_klabauter`) at the point of use, same as `commands/cruft-sweep.md` Step 0 does for its own central-state read.

### Step 0.6 — Depersonalize / registry-codename-leak-guard coverage check

For every publish target, the depersonalize content-transform runs fail-closed inside `coordinator_core.percolate.engine` (`run_content_transform_sweep()`), and the registry-codename-leak guard runs inside `coordinator_core.ops.percolate_run`, both driven by the `no-residual-pattern` / `registry_codenames` guard entries declared per target in `setup/percolate-hooks/percolate-store.yaml`. `/percolate` is not gated on this leg — proceed to Step 1. To confirm or extend guard coverage for a target, read that target's `no-residual-pattern` entries and `registry_codenames` keys in `percolate-store.yaml`, not this step.

---

### Step 1 — Pre-Flight: Verify Target Exists

Resolve the registered target set via `load_targets` (same library `publish.py` itself calls — `publish-targets.sh` no longer exists) by enumerating registered target names: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/percolate-gate" list-targets --percolate-root "$PERCOLATE_ROOT"`.

It prints every resolved target's name, one per line. If `<target>` is not in the list, print the registered targets and exit non-zero. Do not proceed.

```
Error: target '<target>' is not registered (resolved via setup/publish-targets.portable).
Registered targets:
  <target-a>
  <target-b>
  ...
```

### Step 2 — Dry Run

Execute the dry-run and capture stdout + exit code, teed to `/tmp/percolate-dryrun-stdout.txt` (the assembler's input below) as well as the console: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-publish" --dry-run <target> | tee /tmp/percolate-dryrun-stdout.txt`.

If exit code is non-zero, jump to Step 7 (failure stop).

Run the parse assembler over the captured stdout — one call computes every field Steps 2/2b/2c below consume (deletions, touched-file count, sensitive-path hits, the impact-radius breakdown, and the absolute scan-file-list), replacing the reader-performed stdout-parsing this step used to narrate:

`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/percolate-parse-dryrun" parse-dryrun --stdout-file /tmp/percolate-dryrun-stdout.txt --source-dir "<source_dir>"`

Capture its JSON envelope as `$PARSE_RESULT` (`<source_dir>` is the value already captured from Branch 0's `percolate-gate branch0-gate` output). Read from `$PARSE_RESULT.preflight`:
- Whether any deletions are present → `step2_has_deletions`.
- Total file count touched → `step2_file_count`.
- Whether any sensitive paths are touched (`CLAUDE.md`, `settings.json`, `hooks/`, `agents/`) → `step2_sensitive_paths`.
- **`.percolate-ignore` policy state:** if `step2_percolate_ignore_missing` is `true`, surface this as a non-blocking nudge to the PM: _"`.percolate-ignore` is missing — currently publishing everything. Re-run `/percolate <target>` — Branch 0 will detect and walk the setup wiki."_ The publish proceeds normally regardless; the nudge is informational.

**`bin`/`lib` delete check (target `coordinator-claude`).** Read this step's `DELETE` set before proceeding, but read it knowing the deletion paths are guarded — the earlier form of this warning (restricted source resolves `bin`/`lib` to empty, per-file loop silently strips real mirror content) was written against pre-fix behaviour and is retired:

- **A destination top-level dir absent from the restricted source is FATAL, not swept.** `sync_mirror` treats it as an orphan and aborts with `SystemExit(3)`; the only override is `COORDINATOR_OVERRIDE_ORPHAN_SWEEP=1`. A source dir that **exists but is empty** is a *different* guard with a *different* failure and a *different* override — `EmptySourceMassDeleteError`, overridden by `COORDINATOR_OVERRIDE_EMPTY_SOURCE_PRUNE` — so do not expect the orphan abort to catch it. Both downgrade to a warning under `--dry-run`: **a clean dry-run is not proof the real run won't abort.**
- **Ignore-driven per-file deletion is non-destructive by construction.** The Phase-2 per-file delete loop consults the *same* ignore matcher the Phase-1 copy consulted, so an ignored file is neither copied nor deleted — the two phases are symmetric. The only deletions that loop can produce are allowlist narrowing at deep-path granularity (the intended seed mechanism) and genuine upstream removal.
- **The top-level orphan sweep is the one asymmetric deleter** — it `rmtree`s whole top-level dirs and does *not* consult the ignore matcher. That is precisely what the `SystemExit(3)` abort above exists to gate, and why the symmetry argument covers the per-file loop only.

**A large `DELETE` count can be correct.** Narrowing an over-wide mirror back to the ratified wiki seed deletes the difference wholesale — that is the mechanism working, not a fault. **Do not add a proportional delete-threshold guard as a remedy:** it would abort exactly the intended seed-narrowing republish, and the engine already carries a mass-deletion guard on the top-level orphan sweep. The real protection is the Step 3 confirmation gate, which fires on both the deletions-present and ≥10-files-touched conditions.

**Wiki-seed check (targets that publish `docs/wiki/`, e.g. `coordinator-claude`, `coordinator-claude-toplevel-wiki`).** The OSS mirror ships a **curated wiki SEED, not the whole `docs/wiki/` tree** — a bare `docs/wiki` allowlist entry is drift, not a fix. Before treating this dry-run's wiki entries as correct: **verify against THIS dry-run's would-publish set, never by reading the allowlist config** — a config that "looks narrow" proves nothing if the actual write-set disagrees. Grep the dry-run stdout for `docs/wiki/` (and toplevel-wiki basenames) and confirm the count matches the ratified seed (**27 published total, all 27 carrying via the two `publish-targets.portable` allowlist rows** — the set enumerated in `SEED_WIKIS` in `coordinator/tests/test_publish_seed_wiki_allowlist.py`, which is the authoritative count; `task-tier-guidance.md` publishes from source like every other seed entry, not via a destination-reading preserve hook). **A mismatch is corrected in the prose that disagrees, never by narrowing the rows** — narrowing the allowlist to make a smaller number "match" deletes real wiki files from a live public mirror. **THE TRAP:** two independent rows in `publish-targets.portable` publish wikis (`coordinator-claude|mirror` and `coordinator-claude-toplevel-wiki|flat-mirror`) — both must stay narrowed, or narrowing only one changes nothing observable in the mirror. If this dry-run's wiki count doesn't match the seed, STOP — do not proceed to Step 3 — and widen/narrow only via a ratified seed-widening amendment, never an opportunistic add.

#### Step 2a — Coverage-drift detection

After the dry-run, reuse the `<source_dir>` value captured from Branch 0's `percolate-gate branch0-gate` output (same resolution — no need to re-derive it), then list source files newer than `.percolate-ignore`: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/percolate-gate" coverage-drift "<source_dir>" --limit 20`.

(Prints one path per line, files newer than `.percolate-ignore`'s mtime, capped at `--limit`. If the ignore file is missing, this prints nothing — coverage-drift is silent until the file exists.)

If the result is non-empty, surface under a "Coverage drift since policy last reviewed:" panel. If empty, skip the panel entirely (no noise on a quiet run).

For a user-visible "last reviewed" date, optionally prepend the ignore file's mtime: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/percolate-gate" ignore-mtime "<source_dir>"` (prints `YYYY-MM-DD`; exits 1 if `.percolate-ignore` is missing).

The panel is informational. PM reviews and either decides "yes these should publish" (no action) or "these should be denied" (manually edit `.percolate-ignore`). `/percolate` does NOT auto-add patterns.

#### Step 2b — Impact-radius gut-check

Above the Step 3 confirmation gate, render a structured framing of the dry-run scope:

```
Impact radius:
  Top directories: <dir1> (N), <dir2> (N), ...   (top 5 by file count)
  File types:      md=N, sh=N, py=N, other=N
  Sensitive paths: CLAUDE.md, settings.json, hooks/, agents/  [or: (none)]
```

Read `$PARSE_RESULT.preflight.step2b_impact_radius` (computed by the same Step 2 assembler call — `top_directories`, `file_types`, `sensitive_paths`) and render its fields directly into the panel; no separate parse.

This panel renders in EVERY dry-run (including no-op runs — empty values render as `(none)`). The point is to make impact visible BEYOND the mechanical file list — answer "what's about to ship and is any of it inappropriate?" at a glance.

#### Step 2c — Content-leakage scan

`.percolate-ignore` is a STRUCTURAL filter (categories of paths). It cannot catch CONTENT leaks that accumulate through normal authoring: a name slipping into a wiki body, a peer-repo reference embedded in a snippet, a machine name in a code comment, a token pasted into an example. Those need a per-publish scan.

**This step runs on EVERY `/percolate` invocation, not opt-in.** It is fast (bounded scan over the about-to-publish file set), deterministic, and emits a structured panel that feeds the Step 3 gate. The three-tier scan (HIGH credential shapes / MEDIUM identity+internal-path+peer-repo shapes / LOW informational) plus the redaction and identity-file unconfigured-warning logic all now live in `percolate-gate`'s `scan-secrets` subcommand — the skill only builds the input file list and passes the identity/peer-repo paths.

**Build the file set:** write `$PARSE_RESULT.preflight.step2c_scan_file_list` (already-resolved absolute paths, computed by the Step 2 assembler call above) one per line to `/tmp/percolate-scan-files.txt`.

**Resolve the two optional inputs, then run the scan:**
- `--identity-file "$PERCOLATE_ROOT/setup/.percolate-identity"` — the operator's machine-codename token file (gitignored, machine-local). If absent or empty, `scan-secrets` itself prints the "machine-slug detection is UNCONFIGURED" warning; no separate check is needed here.
- `--peer-repos-file "<central-state>/repo-registry.md"`, where `<central-state>` is `"${COORDINATOR_PYTHON:-$(machine-local get coordinator.python)}" "<claude-klabauter-root>/coordinator/lib/coordinator-state-root.py" --central` (interpreter resolved via the `COORDINATOR_PYTHON` env → `machine-local get coordinator.python` fallback chain shown in the command; `<claude-klabauter-root>` resolved via `$REPO_CLAUDE_KLABAUTER` / `machine-local get repos.claude_klabauter` — see Step 0.5). Omit the flag if `<central-state>/repo-registry.md` doesn't exist there.

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/percolate-gate" scan-secrets --files /tmp/percolate-scan-files.txt --identity-file "$PERCOLATE_ROOT/setup/.percolate-identity" --peer-repos-file "<central-state>/repo-registry.md" --target <target>`

**Render the panel above the Step 3 gate** (the command already prints exactly this shape to stdout — pass it through as-is):

```
Content-leakage scan:
  HIGH (credential/secret shapes — BLOCKS publish):
    <file>:<line>: <verbatim line, secret token redacted to first 4 + ellipsis>
    [or: (none)]
  MEDIUM (identity / internal paths / peer-repo names — surfaces to gate):
    <file>:<line>: <verbatim line>
    [or: (none)]
  LOW (informational — commit SHAs, doctrine language):
    N hits across M files [or: (none)]
```

**Severity behaviour:**
- HIGH ≥1: `scan-secrets` exits 2 — print the panel, abort, do NOT proceed to Step 3 gate. Direct PM to fix the leak in source before re-running.
- MEDIUM ≥1: panel rendered, gate FORCED to fire (PM confirmation required even if file count <10), confirmation prompt notes the MEDIUM count.
- LOW ≥1 OR all clean: panel rendered for transparency; does not change gate-fire logic.

**Hook escape:** if a `<source_dir>/.percolate-scan-allowlist` file exists, treat each line as a `file:line` exemption (e.g. for a wiki that legitimately documents an example secret format). The exemption MUST be the exact file:line; pattern matches don't auto-allowlist. Exemptions are reviewed during percolation setup, not here.

**False-positive caveat:** the regex set is intentionally broad. `Dónal` matches any first-name use (intended). Refining is the EM's call when integrating findings — but defaulting to "surface and let PM judge" beats "silently miss a real leak."

**Why Tier MEDIUM and publish.py `PERSONAL_REVIEW_PATTERNS` are separate detection surfaces (not unified):** kept separate — regex-dialect incompatibility is the binding reason. `percolate-gate scan-secrets`'s MEDIUM tier runs on Python `re`, which supports `\b` word-boundary assertions natively, but the pattern SET is kept identical to the bash-era scan for parity, and the two surfaces remain independently maintained: `scan-secrets` is a fast generic-shape first pass over the about-to-publish file set; the `publish.py` Phase-4 audit (`PERSONAL_REVIEW_PATTERNS`, PCRE via `perl_match`) is the authoritative per-operator leak oracle.[^2]

#### Step 2d — Inverse-drift detection

The publish repo can accumulate commits the source doesn't have: another EM on the machine may hand-fix a bug directly in dest, a release-time edit may land there first, or a previous percolate cycle may have been followed by ad-hoc patching. Overwriting those commits silently regresses real fixes. This step surfaces them BEFORE the gate.

Run it via `percolate-gate`'s `inverse-drift` subcommand, which resolves the lastsync-marker-vs-30-day-fallback anchor (`$PERCOLATE_ROOT/setup/percolate-state/<target>.lastsync`, falling back to a 30-day window when the marker is absent or stale) and runs the scoped `git log` in dest in one call, over the same file list built in Step 2c:

`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/percolate-gate" inverse-drift <target> --percolate-root "$PERCOLATE_ROOT" --dest "<dest>" --files /tmp/percolate-scan-files.txt`

(`<dest>` is resolved the same way as Step 5, below — the 4th field of the matching `load_targets` row.)

It prints `anchor_mode: marker|30day-fallback|marker-stale` on the first line, then — only when the scoped `git log` finds ≥1 commit — the panel below:

```
Inverse drift — dest commits touching files about to be overwritten:
  anchor: <marker SHA> [or: 30-day fallback (no marker)] [or: marker-stale (SHA not in dest history)]
  <abbrev-sha> <date> <subject>
  <abbrev-sha> <date> <subject>
  ...
  → Read each commit's diff before proceeding. If it's a real fix, back-port to source FIRST,
    then re-run /percolate. Confirming below will OVERWRITE these changes.
```

If the command's output is only the `anchor_mode:` line, skip the panel entirely.

**Dismiss two structural false positives before alarming** — neither is lost work: a **CRLF-only** commit (source is CRLF, dest is LF-normalized — verify with `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/percolate-gate" crlf-diff <dest-file> <source-file>`; exit 0 = no content change once line-endings are normalized, non-zero prints the residual diff), and a **release/version landing** (a prior percolation echo — source is the origin and has since moved ahead = forward drift). Only a non-CRLF, non-release change authored directly in dest is real drift. **Never use a raw `diff <dest> <source>` as the signal** — dest content has passed through the depersonalize content-transform (Step 0.6) and so always differs; the git-log-since-marker signal from `percolate-gate inverse-drift` above is the reliable one.

**Gate behaviour:** ≥1 *real* (non-CRLF, non-release) inverse-drift commit forces the Step 3 gate to fire (same severity as MEDIUM content-leak), and the gate prompt notes the count. Does NOT auto-abort — PM decides whether to back-port first or proceed.

**Marker-stale caveat:** if the stored SHA no longer exists in dest history (force-push, rebase, repo reinit), the 30-day fallback runs and `anchor_mode: marker-stale` renders. PM should re-percolate to refresh the anchor afterward.

**First-run caveat:** on the very first `/percolate` after this step shipped, no marker exists — 30-day fallback runs once and may be noisy. Subsequent runs are anchored precisely.

### Step 3 — PM Confirmation Gate

Re-run the parse assembler, now passing the real Step 2c/2d counts, to resolve the gate-fire predicate as a decision object rather than a reader-evaluated OR-chain:

`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/percolate-parse-dryrun" parse-dryrun --stdout-file /tmp/percolate-dryrun-stdout.txt --source-dir "<source_dir>" --medium-leak-count <step-2c-MEDIUM-count> --inverse-drift-count <step-2d-real-count>`

Branch on the returned envelope's `gates.step3_gate_fires`: `true` → the gate fires — a `jp_step3_percolate_confirmation_gate` judgment point is present in `judgment_points[]`, its `evidence` field naming which of the five conditions fired (deletion present; ≥10 files touched; a sensitive path — `CLAUDE.md`, `settings.json`, `hooks/`, `agents/` — touched; ≥1 MEDIUM content-leak hit from Step 2c; ≥1 real inverse-drift commit from Step 2d) — surface that evidence in the confirmation prompt below. `false` → skip straight to Step 4, no prompt.

**Zero-changes case:** if dry-run reports no files to transfer ("sending incremental file list" with no file entries, or rsync reports 0 files), skip the gate AND Step 4. Proceed directly to Step 5. The Step 6 summary reports `real-run: skipped (no-op)`.

**Gate prompt format:**

```
Dry-run summary for target '<target>':
  added:   N
  modified: N
  deleted:  N

First 10 paths:
  <path>
  <path>
  ... (N more)

Proceed with real publish? [y/N]
```

Wait for PM confirmation. On anything other than `y` / `yes`, exit 0 with "Publish cancelled."

**When gate does NOT fire:** proceed to Step 4 without prompting.

### Step 4 — Real Run

Execute the real publish and capture stdout + exit code. Pass all output through to console: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-publish" <target>`.

If exit code is non-zero, jump to Step 7 (failure stop).

Scan stdout for lines containing `REVIEW WARNING`. If any are found, surface them verbatim to the PM:

```
Phase 4 audit found REVIEW items — acknowledge before next publish:
  WARNING: REVIEW ...
```

These warnings are advisory (non-blocking); the publish succeeded.

### Step 5 — Optional CI Smoke

Resolve the destination path via `load_targets` (`publish-targets.sh`'s bash array is gone; the portable topology's dest is a registry sigil that only `load_targets` — the same library `publish.py` itself calls — resolves to an absolute path).

Resolve the single target's dest path via the same `list-targets` subcommand, scoped with `--target`: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/percolate-gate" list-targets --percolate-root "$PERCOLATE_ROOT" --target <target>`.

Match-and-exit pattern: exits non-zero when the target isn't found among the resolved rows; the dest path is the only line on stdout when found.

The pre-ci guard runs declaratively inside the engine (`publish.py`'s `dispatch_percolate_pre_ci`) as part of the real run in Step 4 — there is no separate hook-script execution step here.

#### CI smoke

If `<dest>/.github/scripts/run-all-checks.py` exists, run CI with cwd at the repo root. Resolve the interpreter via the `coordinator.python` resolution contract (`COORDINATOR_PYTHON` env → `machine-local get coordinator.python` → PATH fallback), fail loud if none resolves, then run `"$PY" .github/scripts/run-all-checks.py` with cwd at `<dest>`.

Capture exit code. Surface full output to console. If the script does not exist, skip silently — not every target has CI.

If exit code is non-zero, jump to Step 7 (failure stop).

### Step 6 — Unified Summary

Print a 4-line summary regardless of run path:

```
/percolate <target> — <VERDICT>
  dry-run:   exit <N>  (<file-count> files)
  real-run:  exit <N>  [or: skipped (no-op)]
  ci-smoke:  exit <N>  [or: n/a (no run-all-checks.py)]
```

**Verdict tiers:**
- **PASS** — all exits 0 AND no Phase 4 REVIEW lines surfaced.
- **PASS-WITH-WARNINGS** — all exits 0 AND Phase 4 REVIEW lines were present. The EM should acknowledge before the next publish cycle.
- **FAIL** — any non-zero exit.

### Step 7 — Stop on First Failure

When any step fails, print:
1. The failing step number and command.
2. The verbatim stderr output (or the relevant portion).
3. A one-line manual-recovery hint naming the exact command the PM can re-run by hand.

Example:

```
Step 4 failed — real run exited 1.

stderr:
  rsync: [sender] read error: Connection reset by peer (104)

Manual recovery:
  "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-publish" <target>
```

Do not continue to subsequent steps after a failure.

**Post-rsync transform failure → torn-write recovery:** If the engine's post-rsync phase (depersonalize / path-rewrite / substitute / guard, as declared in `percolate-store.yaml`) failed mid-way, the destination is partially mutated — some files synced and post-processed, others synced but un-processed. Recovery: fix the issue at the `percolate-store.yaml` declaration or `coordinator_core.percolate.engine` level, then re-invoke `/percolate <target>`. The sync is idempotent (rsync re-applies unchanged files), and the post-rsync transform phases are re-runnable (depersonalize's `--check`/`--fix` behavior is idempotent). Do NOT panic and revert the destination — re-running is the correct path.

**Pre-ci guard failure → CI not run, destination consistent:** Same destination state as a successful publish; only CI smoke was skipped. Re-invoke `/percolate <target>` Step 5 manually (run-all-checks.py) after fixing the underlying issue to retry CI.

## What This Skill Does NOT Do

- Does **not** name specific hook scripts — there are none. `publish.py` reads the declared `hooks:` list per target from `percolate-store.yaml` and dispatches those phases in-process against `coordinator_core.percolate.engine`; it does not discover or shell out to any `setup/percolate-hooks/<target>/<hook-point>/*.sh` file.
- **Depersonalize and registry-codename-leak coverage are engine-native, not hook-scripted.** For every publish target, the depersonalize content-transform runs inside `coordinator_core.percolate.engine` (`run_content_transform_sweep()`), and the registry-codename-leak guard runs inside `coordinator_core.ops.percolate_run`, both driven by the `no-residual-pattern` / `registry_codenames` guard entries declared per target in `setup/percolate-hooks/percolate-store.yaml`. See that file's target entries to confirm or extend guard coverage.
- Does **not** modify `publish.py`, `publish-targets.portable`, or any source file — invocation orchestration only.
- Does **not** commit or push in the publish repo — the publish repo's git state is the PM's responsibility.
- Does **not** publish multiple targets in one invocation — single target per run.
- Does **not** edit `publish-targets.portable` to "fix" a missing target — exits with the target list instead.
- Does **not** run autonomously or skip the dry-run + PM-confirm gate, even when invoked from another skill or hook.

## Common Mistakes

- **Forgetting the target argument.** `/percolate` with no argument exits with the registered target list — same as an unknown target.
- **Expecting automatic git operations in the publish repo.** After a successful publish, run `git add / commit / push` in the publish repo manually or via a separate workflow.
- **Treating PASS-WITH-WARNINGS as a failure.** Phase 4 REVIEW lines are advisory — they flag personal-data patterns that warrant human review but do not block the publish.

## Provenance Notes

[^1]: `publish.py` and `coordinator/lib/percolate/` migrated to claude-klabauter wholesale.
[^2]: Raised by the Director of Engineering (F3): whether the Step 2c MEDIUM tier and `publish.py`'s `PERSONAL_REVIEW_PATTERNS` audit could share one per-operator token source (`setup/.percolate-identity`). The original macOS/BSD `grep -E` limitation that motivated the split no longer applies now that `scan-secrets`'s MEDIUM tier runs on Python `re`, but the pattern SET stays identical to the bash-era scan for parity.
