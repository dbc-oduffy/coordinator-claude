---
name: percolate
description: Dry-run then confirm publish of files from a working source tree to a named publish-repo target. Wraps publish.sh with gate + CI smoke.
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

<!-- spec backlink: archive/specs/2026-05/2026-05-08-formalize-percolation-spec2-push-to-publish-skill.md -->

Wraps the existing `publish.sh` + publish-repo CI gate into a single deterministic invocation: dry-run first, PM-confirm when changes are significant, real run, optional CI smoke, unified summary. Hook scripts registered under `setup/percolate-hooks/<target>/{pre-rsync,post-rsync,pre-ci}/` run at the corresponding boundaries — this skill does not name specific hooks; it runs whatever's registered.

**Announce at start:** "Running `/percolate <target>` — dry-run → confirm → publish."

## When to Use / When NOT to Use

**Use `/percolate` when:**
- Publishing files from a working source tree to a registered publish-repo target (any name listed in your `publish-targets.sh`).
- You want a dry-run diff + PM-confirm gate before any real rsync.
- You want CI smoke to run automatically after publish.

**Do NOT use `/percolate` when:**
- Publishing ALL targets at once — run `bash ~/.claude/setup/publish.sh` directly for multi-target.
- You need to edit `publish-targets.sh` or add a new target — Branch 0 will walk setup automatically. Manual edit of `publish-targets.sh` also works.
- You want to commit or push changes in the publish repo — this skill does not manage the publish repo's git state.

## Step Sequence

### Branch 0 — First-Run Setup (idempotent gate)

**Run this branch before Step 1 on every invocation.** It silently skips when the target is already fully configured; it walks setup when any piece is missing.

**Gate check — all three conditions must be true to skip:**

1. `<target>` argument is provided AND appears in `setup/publish-targets.sh`.
2. `<source_dir>/.percolate-ignore` exists (resolve `<source_dir>` from the matching TARGETS entry's third pipe-separated field).
3. Hook directories `setup/percolate-hooks/<target>/pre-rsync/`, `post-rsync/`, and `pre-ci/` all exist.

```bash
# Gate check — source publish-targets.sh and test conditions
bash -c '
  source setup/publish-targets.sh 2>/dev/null || { echo "MISSING_TARGETS"; exit 0; }
  TARGET="<target>"
  src_dir=""
  for t in "${TARGETS[@]}"; do
    IFS="|" read -r name mode src dest <<< "$t"
    if [[ "$name" == "$TARGET" ]]; then src_dir="$src"; break; fi
  done
  [[ -z "$src_dir" ]] && { echo "MISSING_TARGET_ENTRY"; exit 0; }
  [[ ! -f "${src_dir}/.percolate-ignore" ]] && { echo "MISSING_IGNORE"; exit 0; }
  for hp in pre-rsync post-rsync pre-ci; do
    [[ ! -d "setup/percolate-hooks/$TARGET/$hp" ]] && { echo "MISSING_HOOK_DIR:$hp"; exit 0; }
  done
  echo "CONFIGURED"
'
```

**On `CONFIGURED`:** silent skip — proceed directly to Step 1 (Pre-Flight).

**On any other output:** walk `docs/wiki/percolate-setup.md` (plugin-relative path) inline, following Steps 1–5 of that procedure. After the setup procedure completes, continue to Step 1 below.

The setup wiki is the single source of truth for the interactive procedure (target registration, `.percolate-ignore` audit-and-classify, grey-zone `AskUserQuestion`, hook scaffolding, and drift detection). Do not duplicate its steps here — walk it inline.

---

### Step 0.5 — Resolve PERCOLATE_ROOT

**Run this once per invocation, before Step 1.** Every subsequent step resolves `setup/` relative to `PERCOLATE_ROOT`, not a hardcoded `~/.claude` literal — this skill runs correctly both from a repo-local percolate-root clone and from a shared `~/.claude` install. Source the runtime-root resolver via the standard trusted-root sourcing preamble:

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
source "${_cc_root}/lib/coordinator-percolate-runtime-root.sh"
PERCOLATE_ROOT="$(coordinator_percolate_runtime_root)" || exit 1
```

`PERCOLATE_ROOT` now holds the directory containing `setup/publish.sh` — resolved via the four-rung chain (`$COORDINATOR_PERCOLATE_ROOT` override → repo-local cwd git root → shared `${CLAUDE_HOME:-$HOME}/.claude` install → hard error). Every `setup/...` path referenced in Branch 0 and Steps 1/2/2c/2d/4/5/5a below is `"$PERCOLATE_ROOT/setup/..."` — not a literal `~/.claude/setup/...`.

---

### Step 1 — Pre-Flight: Verify Target Exists

Source `"$PERCOLATE_ROOT/setup/publish-targets.sh"` in a sub-shell and extract all registered target names:

```bash
bash -c "
  source \"\$PERCOLATE_ROOT/setup/publish-targets.sh\"
  for t in \"\${TARGETS[@]}\"; do
    IFS='|' read -r name rest <<< \"\$t\"
    echo \"\$name\"
  done
"
```

If `<target>` is not in the list, print the registered targets and exit non-zero. Do not proceed.

```
Error: target '<target>' is not registered in publish-targets.sh.
Registered targets:
  <target-a>
  <target-b>
  ...
```

### Step 2 — Dry Run

Execute the dry-run and capture stdout + exit code. Pass output through to console.

```bash
bash "$PERCOLATE_ROOT/setup/publish.sh" --dry-run <target>
```

If exit code is non-zero, jump to Step 7 (failure stop).

Parse the dry-run stdout to determine:
- Whether any deletions are present (lines matching `deleting` or `del.` in rsync summary).
- Total file count touched (lines not prefixed with a directory marker).
- Whether any sensitive paths are touched: `CLAUDE.md`, `settings.json`, files under `hooks/`, files under `agents/`.
- **`.percolate-ignore` policy state:** if the dry-run output contains `No .percolate-ignore found at <source>`, surface this as a non-blocking nudge to the PM: _"`.percolate-ignore` is missing — currently publishing everything. Re-run `/percolate <target>` — Branch 0 will detect and walk the setup wiki."_ The publish proceeds normally regardless; the nudge is informational.

#### Step 2a — Coverage-drift detection

After the dry-run, resolve `<source_dir>` from the matching TARGETS entry's third pipe-separated field, then list source files newer than `.percolate-ignore`:

```bash
find "<source_dir>" -type f -newer "<source_dir>/.percolate-ignore" 2>/dev/null | head -20
```

(`find -newer` is portable across BSD and GNU; no `stat -c %Y` needed. If the ignore file is missing, this yields nothing — coverage-drift is silent until the file exists.)

If the result is non-empty, surface under a "Coverage drift since policy last reviewed:" panel. If empty, skip the panel entirely (no noise on a quiet run).

For a user-visible "last reviewed" date, optionally prepend:

```bash
date -r "<source_dir>/.percolate-ignore" '+%Y-%m-%d' 2>/dev/null
```

(BSD/GNU compatible — works on macOS and Linux.)

The panel is informational. PM reviews and either decides "yes these should publish" (no action) or "these should be denied" (manually edit `.percolate-ignore`). `/percolate` does NOT auto-add patterns.

#### Step 2b — Impact-radius gut-check

Above the Step 3 confirmation gate, render a structured framing of the dry-run scope:

```
Impact radius:
  Top directories: <dir1> (N), <dir2> (N), ...   (top 5 by file count)
  File types:      md=N, sh=N, py=N, other=N
  Sensitive paths: CLAUDE.md, settings.json, hooks/, agents/  [or: (none)]
```

Compute by parsing the dry-run stdout lines (`UPDATE: <path>`, `NEW: <path>`):

- **Top directories:** strip filename, count occurrences of each top-level + second-level directory (e.g. `coordinator/skills`, `coordinator/docs/wiki`); emit top 5.
- **File types:** group by extension `.md`, `.sh`, `.py`, everything else as `other`.
- **Sensitive paths:** match each path against `CLAUDE.md`, `settings.json`, `hooks/*`, `agents/*`. List unique hits; if none, render `(none)`.

This panel renders in EVERY dry-run (including no-op runs — empty values render as `(none)`). The point is to make impact visible BEYOND the mechanical file list — answer "what's about to ship and is any of it inappropriate?" at a glance.

#### Step 2c — Content-leakage scan

`.percolate-ignore` is a STRUCTURAL filter (categories of paths). It cannot catch CONTENT leaks that accumulate through normal authoring: a name slipping into a wiki body, a peer-repo reference embedded in a snippet, a machine name in a code comment, a token pasted into an example. Those need a per-publish scan.

**This step runs on EVERY `/percolate` invocation, not opt-in.** It is fast (bounded grep over the about-to-publish file set), deterministic, and emits a structured panel that feeds the Step 3 gate.

**Build the file set:** parse the dry-run stdout for `UPDATE: <path>` and `NEW: <path>` lines (rel-paths from rsync). Resolve each to absolute via `<source_dir>/<rel_path>`. The scan grep targets only these files — not the full source tree.

**Run the scan in three severity tiers.** Each tier's regex set is pre-defined; do NOT skip any tier.

```bash
# Build the file list from dry-run stdout — example.
grep -E '^\s*(UPDATE|NEW):' "$DRYRUN_LOG" | awk '{print $2}' | \
  while read -r rel; do echo "<source_dir>/$rel"; done > /tmp/percolate-scan-files.txt

# Tier HIGH — credential / secret shapes. Blocks publish on any hit.
tr '\n' '\0' < /tmp/percolate-scan-files.txt | xargs -0 grep -nIE \
  "(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|xox[bpars]-[A-Za-z0-9-]{10,}|ya29\.[A-Za-z0-9_-]{20,}|-----BEGIN [A-Z ]+PRIVATE KEY-----)" \
  2>/dev/null

# Tier MEDIUM — PM/EM identity, internal paths, peer-repo names. Surfaces to PM gate.
#
# OPERATOR IDENTITY TOKENS (machine codenames, home path, org slug): these live in
# setup/.percolate-identity (gitignored, machine-local). The publish.sh Phase-4 audit
# consumes them via PERSONAL_REVIEW_PATTERNS using perl_match (PCRE). This Step 2c
# scan intentionally does NOT inline those tokens: grep -E on macOS/BSD does not
# support \b word-boundaries reliably (GNU extension), so \bmymachine\b patterns
# would silently fail to match. The two detection surfaces are kept separate by
# design — see "Why Tier MEDIUM and publish.sh PERSONAL_REVIEW_PATTERNS are separate"
# note below.
#
# IMPORTANT — FAIL LOUD if setup/.percolate-identity is unconfigured:
# Before running the MEDIUM grep below, check whether the operator's identity token
# file exists AND is populated. If it is absent or PERSONAL_REVIEW_PATTERNS is empty,
# machine-slug detection relies entirely on the publish.sh Phase-4 audit. publish.sh
# itself emits a WARNING for coordinator-claude* mirror targets in
# this case; this Step 2c check runs earlier (EM-layer, before the real publish) so you
# catch it at dry-run time. Surface a visible warning so the operator knows the
# identity-token net is down:
#
#   identity_file="$PERCOLATE_ROOT/setup/.percolate-identity"
#   if [[ ! -f "$identity_file" ]]; then
#     echo "  NOTE: setup/.percolate-identity not found — machine-slug detection"
#     echo "        (PERSONAL_REVIEW_PATTERNS in publish.sh Phase-4) is UNCONFIGURED."
#     echo "        Copy setup/.percolate-identity.example → .percolate-identity and"
#     echo "        populate PERSONAL_REVIEW_PATTERNS with your machine codenames."
#     echo "        This Step 2c scan covers generic shapes only; operator-specific"
#     echo "        tokens are NOT scanned until .percolate-identity is in place."
#   else
#     _prp_count=$(bash -c 'source "$1" 2>/dev/null; echo ${#PERSONAL_REVIEW_PATTERNS[@]}' _ "$identity_file" 2>/dev/null || echo 0)
#     if [[ "${_prp_count:-0}" -eq 0 ]]; then
#       echo "  NOTE: setup/.percolate-identity exists but PERSONAL_REVIEW_PATTERNS is"
#       echo "        empty — machine-slug detection is effectively unconfigured."
#       echo "        Populate PERSONAL_REVIEW_PATTERNS with your machine codenames."
#     fi
#   fi
#
# The generic shapes below catch ~/.claude internal paths, /x/ and drive-letter
# peer-repo paths, and email addresses — no operator-specific literals ship here.
# See docs/wiki/percolate-setup.md.
tr '\n' '\0' < /tmp/percolate-scan-files.txt | xargs -0 grep -nIE \
  "(~/\\.claude/(tasks|projects|memory|plans)/|/x/[a-z-]+|[XxCc]:/[a-z-]+|@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}\\b)" \
  2>/dev/null

# Tier LOW — informational only. Renders in panel without forcing gate.
# 40-char hex commit SHAs (excluding lockfile contexts), "First Officer" outside doctrine files.
tr '\n' '\0' < /tmp/percolate-scan-files.txt | xargs -0 grep -nIE \
  "(\\b[0-9a-f]{40}\\b|First Officer Doctrine)" \
  2>/dev/null
```

**Peer-repo name extension:** if the central state repo-registry (`$(coordinator_state_root --central)/repo-registry.md`, example-orchestration-hub-resident — see `docs/wiki/state-placement-law.md`) exists, extract the registered repo names (one regex-quoted alternation). Add to MEDIUM tier as a fourth alternation — peer-repo names should not appear verbatim in publish content unless the publish target IS that repo.

```bash
if [[ -f "$(coordinator_state_root --central)/repo-registry.md" ]]; then
  # Extract repo names; format depends on registry schema (see docs/wiki/repo-registry.md)
  PEER_REPOS=$(awk '/^- name:/ {print $3}' "$(coordinator_state_root --central)/repo-registry.md" | \
    grep -v "^$(<target>)$" | paste -sd'|' -)
  if [[ -n "$PEER_REPOS" ]]; then
    tr '\n' '\0' < /tmp/percolate-scan-files.txt | xargs -0 grep -nIE "\\b($PEER_REPOS)\\b" 2>/dev/null
  fi
fi
```

**Render the panel above the Step 3 gate:**

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
- HIGH ≥1: print panel, abort with non-zero exit, do NOT proceed to Step 3 gate. Direct PM to fix the leak in source before re-running.
- MEDIUM ≥1: panel rendered, gate FORCED to fire (PM confirmation required even if file count <10), confirmation prompt notes the MEDIUM count.
- LOW ≥1 OR all clean: panel rendered for transparency; does not change gate-fire logic.

**Hook escape:** if a `<source_dir>/.percolate-scan-allowlist` file exists, treat each line as a `file:line` exemption (e.g. for a wiki that legitimately documents an example secret format). The exemption MUST be the exact file:line; pattern matches don't auto-allowlist. Exemptions are reviewed during percolation setup (see `docs/wiki/percolate-setup.md` § Drift Detection), not here.

**False-positive caveat:** the regex set is intentionally broad. `Dónal` matches any first-name use (intended). Refining is the EM's call when integrating findings — but defaulting to "surface and let PM judge" beats "silently miss a real leak."

**Why Tier MEDIUM and publish.sh `PERSONAL_REVIEW_PATTERNS` are separate detection surfaces (not unified):** the Director of Engineering F3 asked whether these two surfaces could share one per-operator token source (`setup/.percolate-identity`). The answer is: **no, kept separate — regex-dialect incompatibility is the binding reason.** The SKILL.md Tier MEDIUM scan is an EM-run bash procedure using `grep -nIE`; `grep -E` on macOS/BSD does not support `\b` word-boundary assertions (a GNU grep extension). Operator machine-slug tokens like `\bmymachine\b` would silently fail to match on macOS. The publish.sh audit uses `perl_match` (full PCRE, universally portable) which handles `\b` correctly on all platforms. Unifying the token source would require either (a) switching SKILL.md to `perl -ne` (changing an EM-procedure into a different execution shape) or (b) accepting that the SKILL.md scan would miss word-boundary-sensitive tokens on macOS. Neither is better than keeping the surfaces separate with clear documentation. **Decision: keep separate; the durable identity-token net is the publish.sh Phase-4 audit (`PERSONAL_REVIEW_PATTERNS`), not this inline scan.** The inline scan is a fast generic-shape first pass; the Phase-4 audit is the authoritative per-operator leak oracle. (Decision doc: `docs/plans/2026-06-24-coordinator-oss-personal-data-hardening.md` § C4 / F3.)

#### Step 2d — Inverse-drift detection

The publish repo can accumulate commits the source doesn't have: another EM on the machine may hand-fix a bug directly in dest, a release-time edit may land there first, or a previous percolate cycle may have been followed by ad-hoc patching. Overwriting those commits silently regresses real fixes. This step surfaces them BEFORE the gate.

**Anchor resolution.** `publish.sh` writes a marker on every successful real run at `$PERCOLATE_ROOT/setup/percolate-state/<target>.lastsync` containing the dest HEAD SHA at sync time. Read it; the contents are the `<since>` ref.

```bash
marker="$PERCOLATE_ROOT/setup/percolate-state/<target>.lastsync"
if [[ -f "$marker" ]]; then
  since_ref="$(cat "$marker")"
  anchor_mode="marker"
else
  since_ref=""   # fall back to 30-day window
  anchor_mode="30day-fallback"
fi
```

**Build the rel-path filter** from the dry-run stdout (same set as Step 2c — files about to be overwritten). Resolve relative to dest root (the 4th pipe-separated field of the matching TARGETS entry).

**Run `git log` in dest** scoped to those paths:

```bash
cd "<dest>"
if [[ "$anchor_mode" == "marker" ]]; then
  # Validate the marker SHA still exists in dest (could have been force-pushed/rebased)
  if git rev-parse --verify "$since_ref" &>/dev/null; then
    git log --no-merges --format='%h %ad %s' --date=short \
      "$since_ref..HEAD" -- $(cat /tmp/percolate-scan-files.txt | sed "s|^<dest>/||")
  else
    anchor_mode="marker-stale"
    git log --no-merges --since='30 days ago' --format='%h %ad %s' --date=short \
      -- $(cat /tmp/percolate-scan-files.txt | sed "s|^<dest>/||")
  fi
else
  git log --no-merges --since='30 days ago' --format='%h %ad %s' --date=short \
    -- $(cat /tmp/percolate-scan-files.txt | sed "s|^<dest>/||")
fi
```

**Render the panel above the Step 3 gate** when output is non-empty:

```
Inverse drift — dest commits touching files about to be overwritten:
  anchor: <marker SHA> [or: 30-day fallback (no marker)] [or: marker-stale (SHA not in dest history)]
  <abbrev-sha> <date> <subject>
  <abbrev-sha> <date> <subject>
  ...
  → Read each commit's diff before proceeding. If it's a real fix, back-port to source FIRST,
    then re-run /percolate. Confirming below will OVERWRITE these changes.
```

If output is empty, skip the panel entirely.

**Dismiss two structural false positives before alarming** — neither is lost work: a **CRLF-only** commit (source is CRLF, dest is LF-normalized — verify with `diff --strip-trailing-cr <dest-file> <source-file>`; empty = no content change), and a **release/version landing** (a prior percolation echo — source is the origin and has since moved ahead = forward drift). Only a non-CRLF, non-release change authored directly in dest is real drift. **Never use a raw `diff <dest> <source>` as the signal** — dest content has passed through `publish-time-transform.sh` (identity scrub) and so always differs; the git-log-since-marker above is the reliable signal.

**Gate behaviour:** ≥1 *real* (non-CRLF, non-release) inverse-drift commit forces the Step 3 gate to fire (same severity as MEDIUM content-leak), and the gate prompt notes the count. Does NOT auto-abort — PM decides whether to back-port first or proceed.

**Marker-stale caveat:** if the stored SHA no longer exists in dest history (force-push, rebase, repo reinit), the 30-day fallback runs and `anchor_mode: marker-stale` renders. PM should re-percolate to refresh the anchor afterward.

**First-run caveat:** on the very first `/percolate` after this step ships, no marker exists — 30-day fallback runs once and may be noisy. Subsequent runs are anchored precisely.

### Step 3 — PM Confirmation Gate

**Gate fires iff any of:**
- Dry-run output contains a deletion.
- Dry-run touches ≥10 files.
- Dry-run touches a sensitive path (`CLAUDE.md`, `settings.json`, `hooks/`, `agents/`).
- Step 2c content-leakage scan reported ≥1 MEDIUM hit (PM/EM identity, internal path, peer-repo name). HIGH hits aborted before reaching this step; MEDIUM hits force the gate even if all other conditions are absent.
- Step 2d inverse-drift detection reported ≥1 *real* (non-CRLF, non-release) dest commit touching files about to be overwritten.

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

Execute the real publish and capture stdout + exit code. Pass all output through to console.

```bash
bash "$PERCOLATE_ROOT/setup/publish.sh" <target>
```

If exit code is non-zero, jump to Step 7 (failure stop).

Scan stdout for lines containing `REVIEW WARNING`. If any are found, surface them verbatim to the PM:

```
Phase 4 audit found REVIEW items — acknowledge before next publish:
  WARNING: REVIEW ...
```

These warnings are advisory (non-blocking); the publish succeeded.

### Step 5 — Optional CI Smoke

Resolve the destination path by sourcing `publish-targets.sh` and reading the 4th pipe-separated field of the matching TARGETS entry:

```bash
bash -c "
  source \"\$PERCOLATE_ROOT/setup/publish-targets.sh\"
  for t in \"\${TARGETS[@]}\"; do
    IFS='|' read -r name mode src dest <<< \"\$t\"
    if [[ \"\$name\" == \"<target>\" ]]; then
      echo \"\$dest\"
      exit 0
    fi
  done
  exit 1
"
```

(Match-and-exit pattern: the loop returns exit 0 only when the target is found and its dest path emitted on stdout. Non-matching iterations would otherwise set the loop's last-evaluated exit code to 1, even with the right stdout — that breaks `&&` chains in the calling step.)

#### Step 5a — Pre-CI hooks

Before running `run-all-checks.py`, discover and invoke any registered `pre-ci` hooks for this target. Hooks live at `$PERCOLATE_ROOT/setup/percolate-hooks/<target>/pre-ci/*.sh` (lexical order, numeric prefixes order execution). Each hook receives `<dest>` as `$1`. Non-zero exit aborts; jump to Step 7.

```bash
hooks_dir="$PERCOLATE_ROOT/setup/percolate-hooks/<target>/pre-ci"
if [[ -d "$hooks_dir" ]]; then
  for hook in "$hooks_dir"/*.sh; do
    [[ -e "$hook" ]] || continue   # nullglob guard
    echo "  → pre-ci/$(basename "$hook")"
    bash "$hook" "<dest>" </dev/null || exit 1
  done
fi
```

If no `pre-ci` directory exists or it's empty, skip silently.

#### Step 5b — CI smoke

If `<dest>/.github/scripts/run-all-checks.py` exists, run CI with cwd at the repo root:

```bash
# python3-first interpreter resolution — `python` is absent on modern macOS / many
# Linux (only python3); `python3` is absent on Windows/pyenv (only python). Fail loud
# if neither exists rather than silently skipping CI.
PY="$(command -v python3 || command -v python)"; [ -n "$PY" ] || { echo "no python3/python on PATH" >&2; exit 1; }
cd "<dest>" && "$PY" .github/scripts/run-all-checks.py
```

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
3. A one-line manual-recovery hint naming the exact `bash` or `python` command the PM can re-run by hand.

Example:

```
Step 4 failed — real run exited 1.

stderr:
  rsync: [sender] read error: Connection reset by peer (104)

Manual recovery:
  bash ~/.claude/setup/publish.sh <target>
```

Do not continue to subsequent steps after a failure.

**Post-rsync hook failure → torn-write recovery:** If a `post-rsync` hook (e.g. `10-depersonalize.sh`) failed mid-way, the destination is partially mutated — some files synced and post-processed, others synced but un-processed. Recovery: fix the hook, re-invoke `/percolate <target>`. The sync is idempotent (rsync re-applies unchanged files), and post-rsync hooks must be re-runnable (depersonalize already is — `--check` + `--fix` is idempotent). Do NOT panic and revert the destination — re-running is the correct path.

**Pre-ci hook failure → CI not run, destination consistent:** Same destination state as a successful publish; only CI smoke was skipped. Re-invoke `/percolate <target>` Step 5 manually (run-all-checks.py) after fixing the hook to retry CI.

## What This Skill Does NOT Do

- Does **not** name specific hook scripts — `publish.sh` discovers `setup/percolate-hooks/<target>/<hook-point>/*.sh` by convention and runs whatever's registered.
- Does **not** modify `publish.sh`, `publish-targets.sh`, or any source file — invocation orchestration only.
- Does **not** commit or push in the publish repo — the publish repo's git state is the PM's responsibility.
- Does **not** publish multiple targets in one invocation — single target per run.
- Does **not** edit `publish-targets.sh` to "fix" a missing target — exits with the target list instead.
- Does **not** run autonomously or skip the dry-run + PM-confirm gate, even when invoked from another skill or hook.

## Common Mistakes

- **Forgetting the target argument.** `/percolate` with no argument exits with the registered target list — same as an unknown target.
- **Expecting automatic git operations in the publish repo.** After a successful publish, run `git add / commit / push` in the publish repo manually or via a separate workflow.
- **Treating PASS-WITH-WARNINGS as a failure.** Phase 4 REVIEW lines are advisory — they flag personal-data patterns that warrant human review but do not block the publish.
