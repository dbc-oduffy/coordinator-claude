# Cross-Platform Shell Portability

<!-- spec-backlink: docs/decisions/DR-061-portability-guard-spinoff.md -->
<!-- spec-backlink: docs/wiki/portable-code-substrate.md (hardcoded-path class) -->

> See also: `claude-code-platform-gotchas.md` (Windows/CRLF quirks), `portable-code-substrate.md` (the `repos.*` / machine-local **path** class), `build-for-someone-elses-machine` doctrine in `CLAUDE.md`, `cross-platform-ci-discipline.md` (CI-measurement enforcement — the sibling discipline to this wiki's code-portability scope).

**Purpose.** Coordinator ships shell scripts and hooks to consumers' machines. This is the canonical reference for *runtime-syntax* portability — the bash-version and coreutils-flavor traps that pass on the author's machine and fail on someone else's. It is distinct from the hardcoded-**path** class (`X:\…` → `repos.*`), which `portable-code-substrate.md` owns.

## Support matrix (the bar every script must clear)

| OS | Status | Worst-case assumption you must code against |
|---|---|---|
| **macOS** | **P0 — must work** | bash **≥ 4** (required — `brew install bash`, ahead of `/bin/bash` on PATH; see DR-148) **and** BSD coreutils (`sed`/`date`/`grep`/`readlink` differ from GNU — do **not** assume GNU coreutils; `brew install bash` does not provide them). |
| **Linux** | Likely, untested | Modern bash + GNU coreutils. Keep it working; we don't gate on it. |
| **Windows Git-Bash** | Must work | Author environment; CRLF + MSYS path-translation quirks (see `claude-code-platform-gotchas.md`). |

**Two independent axes (DR-148):**
1. **bash version** — Coordinator *requires* bash ≥ 4 (PM-ratified 2026-06-01, DR-148); stock `/bin/bash` 3.2 is not a supported execution target. bash-4 features are allowed **only behind** a `BASH_VERSINFO<4` fail-loud guard with a `brew install bash` hint (so a mis-provisioned Mac gets a clean error, never a cryptic abort). **Namerefs (`local -n`/`declare -n`) raise the floor to 4.3** — guard those scripts at 4.3, not 4.0 (`coordinator-safe-commit` is the live case). The 3.2-subset patterns (parallel arrays, temp-file maps — see `coordinator-session.sh`) remain available but are not mandated. `coordinator:install` § 1a.0 checks the PATH-resolved bash version at setup time as a forward backstop to the per-script runtime guards.
2. **coreutils** — must stay **BSD-portable** regardless of bash version (we do NOT require GNU coreutils): `sed -i` / `date -d`/`%N` / `grep -P` / `realpath` / `readlink -f` have no GNU guarantee.

**Why macOS is the sharp edge:** the PM runs a Mac laptop, and a broken **SessionStart/PreToolUse hook** means Coordinator cannot boot to fix itself — a bootstrap trap. Boot-path hooks (`hooks/scripts/*.sh` registered in `hooks/hooks.json`) are invoked as `bash <path>`, so they run under whatever `bash` is first on PATH — which on a correctly-provisioned Mac is the brew bash ≥ 4.

**Reviewer posture vs. policy:** the `code-reviewer` lens assumes the *worst case* (an unguarded bash-4 construct is a finding) as a **detection** stance — that is how it catches missing guards. It does NOT contradict the require-bash-4 policy: a construct properly guarded by `BASH_VERSINFO<4` is explicitly *not* a finding.

## PATH vs login shell (DR-148)

DR-148's bash-≥4 requirement is about the **PATH-resolved interpreter**, not about login-shell identity. The mechanism is already stated in this wiki's support matrix:

> *"Boot-path hooks (`hooks/scripts/*.sh` registered in `hooks/hooks.json`) are invoked as `bash <path>`, so they run under whatever `bash` is first on PATH — which on a correctly-provisioned Mac is the brew bash ≥ 4."*

`bash <script>` PATH-resolves at invocation time. An operator whose login shell is zsh (the macOS default) satisfies DR-148 fully if brew bash ≥ 4 is ahead of `/bin/bash` on PATH — the login shell identity is irrelevant to which interpreter hook invocations land on.

**Login-shell == bash is neither required nor recommended.** Switching the macOS login shell to brew bash via `chsh` is a separate, unrelated operation. It is not a valid remediation step for DR-148, and doing it has documented side effects: macOS bash reads `~/.bash_profile` on login instead of the zsh rc files (`~/.zshrc`, `~/.zprofile`) where PATH additions typically live. An absent or minimal `~/.bash_profile` silently orphans those entries from every fresh terminal.

**If a user is already on a bash login shell, env reconstruction is mandatory.** The coordinator detects this state and offers to reconstruct `~/.bash_profile` by snapshotting the intact prior-shell (zsh) PATH — consent-gated and backed-up per the `normalize-env.sh` mutation contract. Coordinator never proactively offers to initiate the login-shell switch; it only remediates operators who have already made that change.

Cross-reference: `install-surface-completeness.md § Worked example: brew bash on macOS (2026-06-15)` for the full incident account and the snapshot-not-enumerate reconstruction approach; `docs/decisions/DR-148-require-bash4-on-macos.md § Amendment 2026-06-25` for the policy ruling.

## Construct → portable fix

| Non-portable construct | Why it breaks | Portable fix |
|---|---|---|
| `#!/bin/bash` shebang | On Mac pins stock 3.2 even if brew bash 5 exists | `#!/usr/bin/env bash` (picks up first bash on PATH). **Exception — git hooks** run under arbitrary git clients (incl. GitHub Desktop's bash-less MinGit), so they use `#!/bin/sh` + a `command -v bash` guard instead — see § Git hooks must run under MinGit. |
| `declare -A` / `local -A` (assoc arrays) | **bash 4+** — FATAL on 3.2 (errors, aborts) | Refactor: parallel indexed arrays + lookup fn, `case` dispatch, or `key=val` temp file. **OR** guard the whole block with `if (( BASH_VERSINFO[0] < 4 )); then …; fi` |
| `local -n` / `declare -n` (namerefs) | **bash 4.3+** — FATAL below 4.3 (`invalid option`) | Pass by value + `eval`/printf-to-caller, or refactor to avoid the indirection. **OR** guard with `if (( BASH_VERSINFO[0] < 4 \|\| (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] < 3) )); then …; fi`. Note: namerefs raise a script's floor to **4.3**, not 4.0 — `coordinator-safe-commit` is the live example (DR-148). |
| `mapfile` / `readarray` | bash 4+ | `arr=(); while IFS= read -r line; do arr+=("$line"); done < <(cmd)` |
| `${var^^}` / `${var,,}` | bash 4+ case-conversion | `tr '[:lower:]' '[:upper:]'` / `tr '[:upper:]' '[:lower:]'` |
| `&>>` (append both streams) | bash 4+ | `>> file 2>&1` |
| `;;&` / `;&` case fall-through | bash 4+ | restructure `case` |
| `${arr[-1]}` negative index | bash 4.3+ | `${arr[${#arr[@]}-1]}` |
| `wait -n` | bash 4.3+ | poll PIDs explicitly |
| `grep -P` (PCRE) | absent in BSD/macOS grep | `grep -E` with POSIX ERE (`\d`→`[0-9]`, `\s`→`[[:space:]]`, `\w`→`[[:alnum:]_]`); `awk`/`perl` if look-around needed |
| `realpath`, `readlink -f` | stock macOS has neither (`readlink` has no `-f`) | `_portable_realpath` helper (below), or a `realpath \|\| readlink -f \|\| echo` chain whose `\|\| echo` fallback is genuinely safe for the logic |
| `sed -i 's/…/…/'` | GNU `sed -i` vs BSD `sed -i ''` are **mutually incompatible** | temp file: `sed '…' "$f" > "$f.tmp" && mv "$f.tmp" "$f"` |
| `date +%s%N` (nanoseconds) | BSD `date` has no `%N` → emits literal `N` | `"$PYTHON_BIN" -c 'import time;print(int(time.time()*1e9))'`; or `"$(date +%s)-$$-$RANDOM"` if only uniqueness is needed |
| `date -d '<string>'` (GNU parse) | BSD uses `date -v` / `-j -f` | Python `datetime`, or chain `date -d … \|\| date -jf …` |
| `exec python "$0" "$@"` in a polyglot trampoline | `/usr/bin/python` removed in macOS 12.3+; not on `PATH` on many Linux distros | `exec "$(command -v python3 \|\| command -v python \|\| command -v py)" "$0" "$@"` — three-way probe, single exec. **NEVER** chain `exec X \|\| exec Y`: `exec` failure is fatal in sh and does NOT fall through to `\|\|`. |
| `bash <script>` or `bash "$hooks_dir/$hook"` subprocess call | bare `bash` PATH-resolves to `/bin/bash` 3.2 on macOS even when parent is bash 5+ | Replace with `"$BASH" <script>` — `$BASH` is the path of the currently-executing interpreter and forwards to children. Apply to every subprocess invocation inside bash-4+ scripts. |
| Heredoc inside `"$(…)"` with interior pipe: `VAR="$(cmd <<'EOF' … EOF \| filter)"` | bash 3.2 fails to parse this combination with cryptic "unexpected EOF" at file end — the double-quote + heredoc + pipe combination is the trigger; bash 4+ handles it fine | Hoist the heredoc to its own `$()` then herestring the result: `BODY=$(cat <<'EOF' … EOF); VAR=$(cmd <<<"$BODY" \| filter)`. Note: a `BASH_VERSINFO` guard inside the failing script is unreachable (guard can't execute if the script can't parse). | 
| Apostrophe inside bash single-quoted embedded scripts (`awk`/`sed`/`python`) | A `'` inside `awk '...'` terminates the bash string silently mid-script; the whole invocation then fails to parse, often surfacing only as a test sweep failure rather than a parse error at edit time | Rephrase the comment to avoid `'` (e.g., `loop-2 tail` not `loop 2's tail`), or escape: `'\''`. Scan all inserted comment text for apostrophes before saving. |
| `date -r FILE` (file-mtime read) | GNU-only; BSD/macOS `date -r` reads the arg as **epoch seconds**, not a filename → a `\|\| echo 0` fallback then silently zeroes the mtime and bypasses every threshold check (cooldowns, stale-cleanup) | Portable mtime helper: `stat -f %m "$f" 2>/dev/null \|\| stat -c %Y "$f" 2>/dev/null \|\| date -r "$f" +%s 2>/dev/null` (BSD `stat -f` first, GNU `stat -c` second, `date -r` last). Caught in 3 sites by meta-repo /bug-sweep C4 2026-06-14. |
| `sed 's/old/<value-with-slashes>/'` (templated substitution) | A substitution VALUE containing `/` (a path, URL, regex) collides with the `s///` delimiter → pattern breaks or substitutes wrong text | Prefer bash parameter expansion for templated substitution (`"${str/old/new}"`); if `sed` is required, pick a delimiter absent from the value (`s|old|new|`). 2026-06-17 project-rag. |

**NOT a problem (do not "fix"):** bare `mktemp`, `mktemp -d`, `mktemp <tmpl-with-XXXXXX>` (all portable); `grep -E`/`grep -oE` (POSIX ERE); plain `date +%s` / `date -u` / `date +%Y-%m-%d`; `sed` without `-i`.

```bash
# Portable realpath — works on stock macOS (no realpath / no readlink -f) and Linux
_portable_realpath() {
  if command -v realpath >/dev/null 2>&1; then realpath "$1"; return; fi
  if readlink -f "$1" >/dev/null 2>&1; then readlink -f "$1"; return; fi
  if [ -d "$1" ]; then (cd "$1" 2>/dev/null && pwd)
  else (cd "$(dirname "$1")" 2>/dev/null && printf '%s/%s\n' "$(pwd)" "$(basename "$1")"); fi
}
```

CRLF: a `#!/usr/bin/env bash\r` shebang is fatal on Linux/Mac (kernel looks for `bash\r`). Normalize with `sed 's/\r$//'` (temp-file form). `.gitattributes` pins `*.sh eol=lf`.

## CRLF from subprocess stdout in `while read` loops

Python on Windows opens stdout in **text mode** by default, emitting `\r\n` line endings. Command substitution `$(...)` strips one trailing `\n` but does NOT strip embedded or trailing `\r`. `IFS= read -r` does NOT strip `\r` either. Result: every captured value carries a trailing carriage return — `"$parent/coordinator-claude\r/docs/..."` → file-not-found, silently.

**Severity-inverting shape.** The last item in a list often appears to succeed (its `\n` was eaten by `$()`, leaving a clean value), while all earlier items fail with a `\r`-corrupted path. This makes the failure look partial or benign — hard dependencies drop while a trailing leaf survives.

**Evidence:** `python3 -c "print('a\nb')" | od -c` on Windows → `a \r \n b \r \n`.

**Fixes — belt-and-suspenders, in priority order:**

1. **Strip `\r` at the loop (always-safe, bash 3.2+):**
   ```bash
   while IFS= read -r dep_id; do
       dep_id=${dep_id%$'\r'}   # strip trailing CR; $'\r' is portable to bash 3.2+
       use "$parent/$dep_id/..."
   done <<< "$dep_ids"
   ```
   `$'\r'` is a bash ANSI-C quote; it is portable to bash 3.2+ and is the canonical in-loop defense.

2. **Force binary newline at the Python source:**
   ```python
   # Write raw LF bytes — text-mode translation never fires
   sys.stdout.buffer.write(("\n".join(ids)).encode())
   ```
   Or reconfigure the stream: `sys.stdout.reconfigure(newline='\n')`.
   **`PYTHONUTF8=1` is NOT sufficient** — it changes the character encoding (UTF-8 vs system codec), not the newline translation mode. Text-mode CRLF survives even with `PYTHONUTF8=1` set.

3. **Pipe through `tr -d '\r'` before `read` (coarse fallback):**
   ```bash
   dep_ids=$(... python3 -c "..." ... | tr -d '\r')
   ```
   Portable on all platforms; `tr` is POSIX. Use when you cannot change the Python source.

**Regression test.** Feed CRLF-laden input (`$'foo\r\nbar\r\nbaz\r'`) through the loop and assert all three items are captured correctly — a test that feeds clean input only does not catch this trap. The severity-inverting shape means a single-item smoke test is especially dangerous: test with at least two items so the first-item failure is observable.

**Empirical origin (2026-06-22):** caught on a Windows 11 Git-Bash fresh-install dogfood of the example-game-repo/coordinator install chain. Carriage returns in Python's text-mode stdout silently dropped hard dependencies (`install-project-rag.md` baton) from bootstrap seed loops — upstream items got `\r`-corrupted paths, the trailing leaf appeared to succeed, and the install proceeded missing its load-bearing upstream steps.

> See also: `§ EOL normalization — index-first, not worktree-strip-first` for bulk CRLF→LF index remediation; `claude-code-platform-gotchas.md` for Windows CRLF quirks in other surfaces.

## sh+ps1 singleton guard must share primitive AND path

Two cross-platform scripts guarding one host-global singleton must use the SAME lock primitive AND the same lock path. Sharing only the path but using different primitives (e.g., `flock` on POSIX vs. `New-Object System.IO.FileStream` on Windows) does not achieve mutual exclusion — each platform's primitive is invisible to the other. Apply: for every cross-platform singleton guard, verify both legs use the same lock path AND that the primitive semantics are mutually visible.

## .sh/.ps1 mirror fix to ONE leg silently leaves the defect live on the other platform

A `.sh`/`.ps1` mirror fix applied to ONE leg silently leaves the defect live on the other platform. Any edit to one leg of a paired sh/ps1 must touch both legs in the same commit. Apply: grep for the `.ps1` counterpart whenever editing a `.sh` script (and vice versa); verify the fix is symmetric before committing.

## Cross-script orphan helpers — both legs define the function; only one calls it

When adding a paired helper function to both legs of a sh/ps1 mirror, grep BOTH directions: (1) function-exists on each leg AND (2) orchestrator-actually-invokes on each leg. It is routine to define the helper on both legs but forget to wire the call on one leg. Apply: after adding a helper to both legs, grep for the call site on each leg explicitly.

## The regression net — code-reviewer always-on lens

This doctrine is enforced as a **process safety net**, not a hope. The `code-reviewer` (and `code-reviewer-weekly`) agents carry a **Cross-platform portability lens (always-on)** that fires on any diff touching `*.sh` / `bin/*` / `hooks/**` and flags every construct in the table above. macOS being P0, a non-portable construct in a boot-path hook is **P1**; elsewhere **P2**. This is the diff-time backstop; the support matrix is the standard it enforces. Routed through the existing review pass (DR-061 enforcement layer) rather than a new hook surface.

**Empirical origin (2026-06-01):** a mechanical sweep found ~51 offender scripts (33 `declare -A`, 13 `mapfile`, 18 `realpath`, 10 `grep -P`, 8 `date`, plus shebangs/CRLF) — all latent macOS-3.2 / BSD-coreutils breakage shipping silently because no review lens looked for it. The PM had been hand-catching offenders at review time; this lens replaces that with a standing net.

## Marketplace first-run traps on stock macOS

A clean Mac (stock `/bin/bash` 3.2, no perl 5.34+, no `python3` symlink in some installs) is the sharpest first-run surface in the marketplace experience. Four reliably-firing traps observed 2026-06-11 on a `/coordinator:repo-setup` Phase 4 walk-through:

1. **Bespoke-repo `CLAUDE.md` false positive.** Phase 4 verification probe treats a project-shaped `CLAUDE.md` as a missing-marker.
2. **`/update-docs` invoked against an empty repo is a no-op pipeline.** No source files = no doc work; the skill needs an empty-repo short-circuit, not a polite traversal.
3. **`/workstream-start` fails under stock bash 3.2** (associative-array use) before the user sees the welcome flow.
4. **`coordinator_whoami` ModuleNotFoundError** on the Phase 4 binding probe on any fresh machine without the package installed (now fixed via the Phase 3 self-install, DR-148-adjacent).

A first-run that hits any of these emits a cryptic error before the user has any model of what coordinator IS. Marketplace UX consideration: the bash-3.2 fail-loud guard with `brew install bash` remediation (DR-148) is what converts trap #3 from "Coordinator is broken" into "Coordinator told me what to do." Apply the same discipline to traps #1, #2, #4.

## Construct → portable fix — additional rows (2026-06-14)

Extend the existing portable-fix table (preserve existing rows; the entries below extend the coreutils-flavor axis that was under-served):

| Construct | Failure on macOS / BSD | Portable fix |
|---|---|---|
| `sort -V` (version sort) | GNU sort extension; BSD `sort` on macOS lacks `-V` → silent comparison failure (`sort -V -C` returns non-zero, every version compare evaluates `false`) | Hand-roll per-component compare: split on `.`, numeric-compare each. Do NOT trust a `sort -V -C 2>/dev/null` fallback — the comment may claim a per-component implementation that does not exist (`install.sh:249` regression 2026-05-30). |
| BSD `sed` `\s` in BRE (`s/.*"version"\s*:\s*"\([^"]*\)".*/\1/p`) | BSD `sed` BRE does not recognize `\s` → entire pattern fails silently, captured group is empty | Use `[[:space:]]` POSIX class. Audit every BRE sed expression for `\s`, `\d`, `\w`, `\b`. |
| BSD `sed` `\?` in BRE (`sed 's/^# \?//'`) | GNU BRE extension; BSD `sed` treats `\?` as literal `?` → output corrupted (`--help` text malformed) | `sed 's/^#[[:space:]]\{0,1\}//'` — explicit POSIX BRE repetition. |
| BSD `grep` `\|` BRE alternation (`grep -qi "virtualenv\|pip"`) | GNU BRE extension; BSD `grep` treats `\|` as literal pipe → match never fires → silent logic bug (not parse error). Live case 2026-05-30: `refresh-plugin-live-install.sh:828` misidentified venv tool, picked uv path on a pip venv. | ERE: `grep -qiE "virtualenv\|pip"` (no `\` escapes). Or `awk` for complex alternation. |
| `grep -P` with `\b` word boundary | PCRE absent from BSD grep; `grep -E` POSIX ERE has no word-boundary syntax | `perl -ne 'print if /pattern/'` — portable `\b` support and faster than awk emulation. (`setup/publish.sh:242` 2026-06-01.) |
| `timeout <secs> <cmd>` / `gtimeout` | GNU coreutils; **absent from BSD coreutils** — `command -v timeout` → not found on stock macOS. A bare `timeout <n> <cmd>` in a guarded branch (`command -v timeout … then … else …`) is portable because the timeout-absent branch never executes the command; a raw, unguarded `timeout <n> <cmd>` at top-level fails with `command not found` on macOS. When the error is silently swallowed (e.g., `timeout 10 cmd \|\| true`), the fallback runs the inner command **unbounded** — the real portability hazard. | `cs_timeout <secs> -- <cmd...>` from `lib/coordinator-watchdog.sh` (source the lib; delegates to `timeout`/`gtimeout` when present, background-kill sentinel fallback otherwise; mirrors GNU timeout's exit-124 contract). See tripwire `RAW-TIMEOUT-UNGUARDED` in `coordinator-tripwires.md`. For a single site, a `if command -v timeout …; then timeout … else <fallback>; fi` guard is also acceptable when the fallback is bounded by other means. |

**Long-running loops with no internal ceiling** should use `cs_watchdog_check` (from the same `lib/coordinator-watchdog.sh`) rather than a single outer `cs_timeout` wrapper — `cs_watchdog_check` runs inside the caller's shell (no backgrounding), preserves shell-variable accumulators across iterations, and also detects stalls (no-progress bail). Call at the top of each loop body: `cs_watchdog_check <ceiling_secs> <stall_count> <interval_secs> <probe_cmd...>`. See the lib header for the full signature and return-code contract.

**D-state / `setsid`-absent caveat.** A process wedged in uninterruptible disk-IO (D-state) cannot be SIGKILLed by the kernel — neither `cs_timeout` nor GNU `timeout` can guarantee termination in that case. Additionally, `setsid` (which enables killing the entire process group) is absent on macOS, so process-group kill is not an available escalation. The guarantee for `cs_timeout` is "bail and return control to the caller"; it is NOT "the child process is guaranteed to be gone." The `cs_watchdog_check` cooperative primitive carries the same caveat.

## Implicit interpreter prerequisites on clean macOS

The brew-bash-ahead-of-PATH (DR-148) covers the bash interpreter. Two other interpreters that scripts routinely assume are present have regressed on clean macOS in the 2026 timeframe:

- **Perl.** macOS 12.3 Monterey removed bundled `/usr/bin/perl` from new installs. Scripts that use `perl` for non-trivial regex (`name-personas.sh` `to_slug` / collision audit / `replace_in_prose`; the `grep -P` → `perl -ne` substitution row above) must `command -v perl` at the top and fail loud with a remediation (`brew install perl` or `xcode-select --install` for the Apple-bundled fallback). Without the preflight, the script aborts mid-run with `command not found` after partial state writes.
- **`python3`.** Stock Windows python.org installs ship `python.exe` and `py.exe` but NOT `python3.exe`. Modern Linux (Ubuntu 22.04+, Fedora 36+, Arch) ships only `python3`. macOS 12.3+ ships only `python3` (no `python`) unless `pyenv` / brew Python is installed. **No single bare interpreter name is portable across all three platforms.** This is the design pressure behind the polyglot trampoline (`bash-on-windows-gotchas.md §9`) and the `lib/resolve-python.sh` resolver.

The cross-product means a clean Mac + a stock Windows + a modern Linux do not share *any* common Python interpreter name. Hardcoding one ships a script that works on the author's box and silently exec-127s for every other operator.

## Python resolver — never bare `python3` on Windows

In any runtime script that fires from a hook chain, MCP probe, or install path on Windows, do not write bare `python3 -c "..."`. The bare name resolves in three competing subsystems whose precedence is non-obvious:

1. **`PATHEXT`-aware lookup** finds `python3.cmd` shim (see `windows-cmd-shims.md`) or `python3.exe` on PATH.
2. **AppX App-Execution-Alias** lookup runs *independently* of PATH on shell-execute callers; an orphaned `%LOCALAPPDATA%\Microsoft\WindowsApps\python3.exe` reparse stub pops the "Install Python" picker without falling through to PATH. The shim is never reached.
3. **MSYS PATH inheritance** may put `WindowsApps` ahead of the real Python — `command -v python3` from Git-Bash returns the stub path, non-empty, so a naive `command -v python3 || command -v python` guard "succeeds" with the stub and then the stub fires the picker.

**Use the resolver lib.** Source `lib/resolve-python.sh` (coordinator) / `scripts/lib/select-python.sh` (project-rag); they encode the WindowsApps exclusion and the `py.exe` Python-Launcher precedence:

```bash
case "$_path" in
    */WindowsApps/*|*\\WindowsApps\\*) continue ;;
esac
```

**Linux symmetry.** `#!/usr/bin/env python` (no `3`) fails on Ubuntu 22.04+ which ships only `python3`. The polyglot trampoline (`bash-on-windows-gotchas.md §9`) is the unified fix: `command -v python3 || command -v python || command -v py` — picks whichever the platform ships. Hard-coding any single name regresses one of the three platforms.

**Detection on operator's machine** (`/coordinator:setup` Step 3c health probe):
```powershell
Get-Item "$env:LOCALAPPDATA\Microsoft\WindowsApps\python3.exe" -Force -ErrorAction SilentlyContinue |
  Select-Object Name, Length, Target, LinkType
```
Length 0 + LinkType ReparsePoint + no Target ⇒ orphan stub. `Remove-Item -Force`. If Store Python reinstalls, the stub regenerates; re-clean.

## False-positive triage taxonomy (portability audits)

A mechanical portability-grep over the meta-repo (the 2026-06-01 audit, ~51 raw hits across `declare -A` / `mapfile` / `realpath` / `grep -P` / `date` / shebangs) needs a triage filter before it generates real fix-tickets, or the audit drowns the reviewer in noise. Constructs that LOOK non-portable but are NOT:

- **Already-guarded bash-4 use.** Any script whose first lines include `(( BASH_VERSINFO[0] < 4 ))` exits cleanly on 3.2 with the brew-remediation message (DR-148 carve-out). These are correct. Live exemplars: `decode-claude-projects-dir.sh:15`, `orphan-branch-sweep.sh:16`, `publish-time-transform.sh:78`.
- **`read -ra` is bash 2.x**, not 4.0+. Don't flag it.
- **C-style `for (( i=1; i<=n; i++ ))` is bash 3.2.** Don't flag it.
- **The portable-realpath chain** `realpath || readlink -f || echo "$PWD"` is a safe fallback per the master construct table; flagging `realpath` in isolation misses the chain.
- **Constructs inside comment text or `echo` strings** — non-executable; grep with `-v '^\s*#'` and `-v 'echo'` before triaging.
- **BSD-portable `date -d ... || date -jf ...` chains** — the `||` fallback is the fix; do not flag the GNU half.

**Triage discipline:** every audit report ships two columns — `RAW HITS` and `TRIAGED`. The delta is the work. Treating raw hits as the work item is the recurring noise-source; the 2026-06-01 sweep delivered 4 real fixes plus 12 triaged-out false positives in `report-3.md` alone.

## Refactor vs. guard — choosing per script

Two valid responses to a bash-4-only construct, picked per-script not by edict:

- **Refactor to the bash-3.2 subset** when the construct is one or two associative arrays used as immutable lookup tables. Pattern: `mktemp` a temp file, `printf 'key=val\n'`, `_lookup() { grep -qxF "key=val" "$tmpfile"; }`. See `verify-dist-publish-repo-sync.sh` for the canonical refactor (assoc array → tempfile set + `grep -qxF` helper, bash-4 guard removed). Refactor cost: ~5-20 LOC; risk: low (covered by the script's own tests).
- **Add a fail-loud bash-4 guard** when the construct is structural — 5+ assoc arrays, 2+ namerefs, `-v` membership tests scattered through helpers. Pattern: the DR-148 guard with `brew install bash` remediation at the top, exit code chosen per the DR-148 § "Bash-guard exit-code principle" table. See `coordinator-safe-commit` for the canonical guard placement. Refactor cost would be ~80-150 LOC of risky churn on the most load-bearing commit helper; guard cost: ~10 LOC + an executor-side prereq.

The decision principle: **emulate when emulation is small and local; gate when the script's whole shape is bash-4.** A script that lives at coordinator's critical path (commit helpers, boot-path hooks) prefers the gate so its main path stays clean; a script with one peripheral assoc array prefers the refactor so a Mac without brew bash still gets useful work done.

The 2026-06-01 sweep applied this principle: `coordinator-safe-commit` got a gate (`report-2`); `verify-dist-publish-repo-sync.sh` got a refactor (`report-4`). Same audit; opposite responses; both correct.

## Exec-bit install hazard on macOS

A script committed at git mode `100644` (no exec bit) on a Windows author's box ships with the exec bit cleared. On macOS / Linux a `bash <path>` invocation still works; a `./path` or shebang-direct invocation **fails with ENOEXEC, which macOS reports as `Undefined error: 0`** — one of the more famously unhelpful error messages in the platform. The script never runs; the operator has no clue why.

Recurring shape: Windows `core.fileMode=false` + a path-restricted `git commit -- <files>` resets the exec bit in the index. A boot-hook script that should fire on every session start silently never runs on the next Mac clone.

**Fix at the source, not on the consumer machine.** Set exec bit explicitly on the canonical script set at write-time:
```bash
git update-index --chmod=+x bin/<script>
```
Then commit. The OSS install-surface (DR-151) productizes this — `bin/install-sentinel-write` carries a check + fix at install time as a safety net. Cross-link: `install-surface-completeness.md § Exec-bit doctrine`; DR-151.

This is not a runtime-syntax portability issue, but it shares the failure shape with the cluster (cryptic error on Mac, silent on Windows author's box, root cause invisible to the user). Wiki cross-link kept here so the next portability sweep grepping for "macOS silent failure" lands on it.

## Git hooks must run under MinGit (GitHub Desktop), not just full Git for Windows

**MinGit is bundled inside GitHub Desktop and ships `sh`, `dash`, and `env` — but NOT `bash`.** A hook shim with a `#!/usr/bin/env bash` or `#!/bin/bash` shebang causes every GUI commit made through GitHub Desktop to fail:

```
error: cannot run /usr/bin/env: No such file or directory
error: cannot spawn .git/hooks/prepare-commit-msg: No such file or directory
```

or, when `env` is present but `bash` is not:

```
/usr/bin/env: 'bash': No such file or directory
```

**Which hooks are affected.** `pre-commit` is skipped by git on merge commits, so merge-aborting failures always come from `prepare-commit-msg` or `commit-msg`. A failing `prepare-commit-msg` hook aborts the entire commit with the message "Not committing merge; use 'git commit' to complete the merge" — appearing to users as if the merge itself is broken. Full Git-for-Windows (used in terminals and by Claude Code) ships `bash` on PATH and is unaffected; the failure is GitHub Desktop-specific.

**The rule for coordinator hook shims:**

```sh
#!/bin/sh
# <purpose description>
# POSIX-sh + bash guard — GitHub Desktop's MinGit lacks bash; skip cleanly there.
command -v bash >/dev/null 2>&1 || exit 0
exec bash "$HOME/.claude/plugins/coordinator/bin/<helper>" "$@"
```

Two key properties:
1. `#!/bin/sh` — resolves to a POSIX shell that every git distribution ships (MinGit, full Git-for-Windows, macOS `/bin/sh`, Linux `/bin/sh`).
2. `command -v bash >/dev/null 2>&1 || exit 0` — graceful skip when bash is absent. This is correct for coordinator hooks: a GUI commit from GitHub Desktop carries no coordinator session id and needs no auto-push, so the skip is behaviour-preserving, not a loss.

**Generators** (`coordinator-ensure-prepare-commit-msg-hook`, `coordinator-ensure-post-commit-hook`) emit this portable shim on fresh install, and self-heal a stale `#!/usr/bin/env bash` canonical shim to the portable form when the hook body matches exactly the old single-exec-line shape — conservatively, to avoid clobbering foreign/LFS hooks that happen to also invoke the helper.

**Append paths** (foreign hooks that the generator amends rather than replaces) wrap helper calls in a `command -v bash` guard: `{ command -v bash >/dev/null 2>&1 && bash "$HOME/.../<helper>"; } || true` (or `&` variant for backgrounded post-commit), so a MinGit pre-commit that reaches the appended block also exits cleanly.

**Adding a new git hook.** Any new coordinator-emitted git hook MUST use `#!/bin/sh` as the shebang and include `command -v bash >/dev/null 2>&1 || exit 0` immediately after the comment header. It MUST also be registered in `bin/tests/test-hook-shims-portable.sh` (Part A registry + Part B detection), which enforces both portability and registration completeness — a new emitter absent from the registry fails the test suite with a clear diagnostic.

## GNU multiline-sed slurp idiom — portability net gap

The `code-reviewer` portability lens (and the `portability-sweep` tool) check `sed -i`, `date -d`/`%N`, `grep -P`, and `stat -c` — but NOT the GNU multiline-sed label/branch construct `:a;N;$!ba`. This is a distinct BSD-divergence class: BSD/macOS `sed` requires a newline (not `;`) between a label definition and the next command — the `;` separator works only in GNU `sed`.

**Empirical origin (2026-06-17 mac-portability-audit):** `block-no-verify.sh` used `sed ':a;N;$!ba;s/...'` to slurp whole input. macOS `sed` emitted "unused label" to stderr on every `git commit`, silently corrupting hook output. The script had zero offenders on the existing checklist (guarded `sed -i`, no `date -d`); the slurp pattern was the escapee.

**Rule:** treat `sed ':label;N;$!b...'` (and similarly `sed ':l;N;$!bl'`) as a BSD-portability finding at P2 in non-boot-path scripts, P1 in boot-path hooks.

**Portable replacements for whole-input slurp:**
- `tr '\n' '\x01'` then substitute, then `tr '\x01' '\n'` back — portable on all platforms.
- `awk '{printf "%s ", $0} END {print ""}` — portable; awk is universally available.
- `perl -0777 -pe 's/pattern/replacement/gs'` — portable where perl is present (see § Implicit interpreter prerequisites; add `command -v perl` preflight).

**code-reviewer portability lens addition:** flag any `sed` invocation whose substitution string contains `\n` OR whose label/branch pattern matches `:.*;N;.*b` as a probable GNU-sed slurp.

## Non-script surfaces — portability audit scope gap

Cross-platform audits scoped to `*.sh` / `bin/*` / hooks miss whole-OS assumptions baked into non-script surfaces. Scripts themselves are guarded (DR-148 + BSD-coreutils discipline); the defect class shifts to runtime command / path / shell unconditionally hardcoded to one OS inside JSON config, install manifests, and skill/command/agent markdown that embeds commands.

**Empirical origin (2026-06-17 notebooklm-mcp memo pickup + xplat config/markdown sweep):** `notebooklm/.mcp.json` hardcoded `cmd /c notebooklm-mcp` (Windows-only shell) → `ENOENT` on every macOS boot. A follow-on sweep found `cruft-sweep.md`'s Explore dispatch prompt hardcoding `X:\` / `E:\dev\` Windows paths, and `workday-start.md` using GNU `date -d` with no BSD fallback. Zero of these were `.sh` files; the existing script-portability checklist never looked at them.

**Defect taxonomy:** *conditional* OS handling (an `if [[ "$OSTYPE" == "darwin"* ]]` branch, or a `cmd /c … || npx …` fallback chain) is the goal — GOOD. *Unconditional* single-OS assumption is the bug.

**Three non-script surfaces to audit for portability:**

1. **`.mcp.json` `command`/`args` fields.** Prefer bare `npx <package>` or a plain binary name over `cmd /c <name>`. Every in-house npm MCP server that works via `npx` needs no Windows-shell wrapper. When a wrapper is genuinely required, guard with a platform-conditional MCP config (two files or a runtime-swap install step) rather than hardcoding `cmd /c`.

2. **Install manifests `cmd`/`probe` fields.** Same principle — bare binary or `npx`, not `cmd /c`.

3. **Skill / command / agent markdown command-embeds and dispatch-prompt bodies.** Inline shell snippets, `bin/…` invocations, and path examples in prose must avoid hardcoded drive letters (`X:\`, `E:\dev\`) and GNU-only CLI flags. When a snippet is platform-conditional by design, say so explicitly (e.g., "Windows only:").

**code-reviewer portability lens addition:** flag any `.mcp.json` `command` value matching `cmd /c` or `cmd.exe`; flag any markdown command-embed containing `X:\`, `E:\dev\`, or `date -d` without a BSD fallback annotation.

## PATH guarantee validity — name the mechanism, probe per-OS

A cross-platform PATH or install guarantee must name the MECHANISM (harness injection vs installer write vs shell-profile sourcing) and be verified per-OS. A bare "guaranteed on PATH" assertion with no mechanism named is almost always a Windows-true claim that silently fails on POSIX.

**Empirical origin (2026-06-18 macOS machine-local fix):** `portable-code-substrate.md` and `claude-code-platform-gotchas.md` both asserted that `~/.claude/bin` is "guaranteed on PATH for every Claude Code session across all POSIX shells." The assertion was false on macOS — the Claude Code harness injects only `plugins/*/bin`; `~/.claude/bin` reaches PATH solely via the Windows installer's explicit PATH write (`install-substrate.sh` Step 3b). As a result, every plugin CLI shim in `~/.claude/bin` (including the example-game-repo-control forwarder) was `command not found` by bare name on macOS. The fix used the proven lever (a forwarder file placed in the harness-injected plugin `bin/`), NOT a macOS profile edit.

**Rule:** When documenting a PATH, bin-visibility, or install guarantee:
1. Name the mechanism: harness injection / installer `PATH` write / shell-profile sourcing / symlink in a standard location.
2. State which OS(es) the mechanism applies to.
3. For any OS where the mechanism does not apply, name the alternate or document that it is unsupported.

A guarantee that is only installer-provisioned on one OS is a portability trap — "guaranteed" invites callers to omit the fallback they'd otherwise write.

## EOL normalization — index-first, not worktree-strip-first

Bulk CRLF→LF worktree stripping kills the Git-for-Windows `autocrlf` nag only when the index is already pure LF. A mixed or CRLF index (LFS-heavy repo, older repo without `.gitattributes`, e.g. example-sim-repo) shows thousands of files "modified" post-strip because the worktree now differs from the un-normalized index.

**Rule:** before running any fleet-wide CRLF→LF strip:
1. Survey the index: `git ls-files --eol` — watch for `i/mixed` or `i/crlf` in the index column. An `i/lf` result means the index is already normalized and strip-then-stage is safe.
2. If the index is not pure LF, normalize the index first with `git add --renormalize`, then commit, then strip the worktree.
3. The durable fix is a committed `.gitattributes` with `* text=auto eol=lf` — this survives a fresh clone under `system autocrlf=true` and makes future strips a no-op. Local `core.autocrlf=false` is belt-and-suspenders only; it does not protect a fresh clone.

## Allowlist-comment markers — match the embedded interpreter's comment syntax

When a guard tolerates a trailing allowlist annotation (e.g. `# verify-no-console-flash: allow <reason>`), the marker text is parsed by the guard's regex, not by a shell. But when the annotated line is `node -e '<source>'` or `python -c "<source>"`, the comment lands INSIDE the embedded interpreter's string and is parsed BY THAT INTERPRETER at runtime.

- **JavaScript** (`node -e`) does not accept `#` as a line comment — it parses as a syntax error or an experimental private-field token.
- **Python** (`python -c`) does accept `#` as a comment.
- **Shell-trailing** (comment placed after a closing quote, outside the interpreter string) works for any interpreter.

**Empirical origin (queue 2026-06-15, ~/.claude):** Wave A annotated 5 `node -e '...'` sites with leading `#`, producing 5 broken scripts (`audit-roadmap.sh`, `test-self-claim-refresh-queries.sh`, `test-ensure-vscode-readonly.sh`, `claude-ue-bootstrap.sh`, and one other). The guard's regex matched the marker text and reported `OK`; the scripts were broken at runtime.

**Rule:** When dispatching an annotation executor over a multi-language tree, the brief MUST specify:
- `node -e` / `node --` contexts: use `//` prefix for the allowlist marker (e.g. `// verify-no-console-flash: allow <reason>`).
- `python -c` / heredoc contexts: `#` is fine.
- Comment placed after the closing quote (shell-trailing): works for any interpreter and is the safest placement when the string content is long.

The guard's `_is_suppressed` check is typically regex-only on the marker text, agnostic to comment prefix — so a `//`-prefixed marker satisfies the regex AND is valid JS.

## A `*/` sequence inside a `/* */` block comment terminates it — wildcard glob paths are a common trigger

Two agents independently hit this trap writing a glob like `state/roadmap/*/OVERVIEW.md` inside a `/* */` block comment — the `*/` substring terminates the comment at that point, causing cascading parse errors (12 in one case). Both fixed it by replacing the wildcard with a placeholder (`<slug>`, `<name>`, `<star>`). The mechanism: a literal `*/` sequence (asterisk immediately followed by slash) inside a JS/TS `/* … */` block comment **closes the comment at that point**, making everything after it unparseable. Note that `*.ts` inside `/* *.ts */` does NOT terminate the comment — only the two-char `*/` sequence matters, not the presence of a wildcard alone.

**Rule:** when documenting a glob or wildcard path inside a `/* */` block comment, either switch to a line comment (`//`) or render the wildcard as a placeholder (`<slug>`, `<name>`, `<star>`) — never a literal asterisk-slash sequence.

## Python subprocess invocation — sibling-path fallback mandatory on Windows

A Python CLI that invokes a sibling executable via `subprocess.run(['bare-name', ...])` will fail on Windows even when the sibling is on bash's PATH. Python uses the Windows process PATH (no bash-shim hookup) and raises `FileNotFoundError` for a name that bash can resolve without issue.

**Empirical origin (structured-queue C17/C18, 2026-06-15):** `migrate-bug-backlog.py` failed this way on Windows; the sibling migrators (`migrate-debt-backlog.py`, `migrate-improvement-queue-project.py`) that carried a `_find_sibling_script()` helper ran clean. One entry was hand-migrated as a workaround; C18 ported the fallback.

**Rule:** Any Python CLI that invokes a sibling executable via `subprocess` ships with a sibling-path fallback:

```python
import subprocess
from pathlib import Path

def _find_sibling_script(name: str) -> str:
    """Return bare name if resolvable; fall back to Path(__file__).parent / name."""
    import shutil
    if shutil.which(name):
        return name
    candidate = Path(__file__).parent / name
    if candidate.exists():
        return str(candidate)
    raise FileNotFoundError(f"{name!r} not found on PATH or alongside {__file__}")

subprocess.run([_find_sibling_script('migrate-debt-backlog.py'), ...], check=True)
```

Add this pattern to the polyglot-trampoline convention checklist for coordinator CLIs. Do not defer it to a follow-up — `FileNotFoundError` on Windows is silent until first production use.

## Bash `cmd - <<HEREDOC` empties stdin when the command reads its program from stdin

When a command reads its *program* from stdin (a bare `-` script arg: `bash -`, `python -`, `psql -f -`), do NOT also feed it data via a heredoc OR a here-string — the two stdin sources collide and the inner read silently sees empty stdin. The canonical broken form is `cmd - <<HEREDOC … <<< "$x"` (heredoc supplies the program, here-string is meant to supply data) — stdin is consumed by the program-read, and `$x` never arrives. The gate built on it is *inert*: it returns its no-op verdict regardless of input.

**Safe form:** `printf '%s' "$x" | cmd -c "$SCRIPT"` — pass the program via `-c` (an argument, not stdin), leaving stdin free for the piped data.

**Empirical origin (2026-06-09, project-rag):** a `phase06-whoami` gate using `cmd - <<HEREDOC … <<< "$x"` had been inert since its C3 extraction — every invocation read empty stdin and returned the same verdict. **Detection pattern:** a behavioural test that feeds three distinct inputs and asserts three distinct verdicts (a no-op detector) catches a gate that collapses every input to one output; a single-input smoke test does not.

## Cross-platform security-flag mirror must replicate env init-reset, not just the waiver check

When mirroring a security flag / safety guard between a `.sh` and `.ps1` leg, replicate **the full guard sequence** — including any environment init-reset the guard depends on — not just the visible waiver/override check. A leg that copies the waiver check but omits the env init-reset passes with the flag set but fails (or silently no-ops) under a bare environment. Add a **bare-env-no-flag regression test** that exercises the guard with no env vars set, on both legs.

**Why the init-reset is easy to miss:** in bash a shell variable is forgeable via inherited env unless explicitly reset at startup; when the PS1 mirror bridges the flag through `$env:` (PowerShell function scope cannot share locals), the env var *becomes* the trust surface and the startup clobber (`$env:X='false'`) becomes load-bearing — yet a diff that only compares the waiver logic between legs never shows it. Diff the init-reset, not just the check.

**Empirical origin (2026-06-17, project-rag):** a bash→PS1 security-flag mirror copied the waiver check but not the env init-reset; the bare-environment path diverged between legs until the regression test pinned it.

## Sourceable shell helpers must not self-locate via `BASH_SOURCE` alone

A helper script meant to be `source`d must NOT resolve its own directory from `BASH_SOURCE` alone — `${BASH_SOURCE[0]}` is **empty** when the file is sourced under `bash -c`, so the self-location silently resolves to the wrong path (or empty). Use a fallback chain:

1. explicit override env var (e.g. `MYTOOL_ROOT`),
2. `BASH_SOURCE`-if-it-names-an-existing-file,
3. cwd marker-file probe,
4. `git rev-parse --show-toplevel`.

**Test by sourcing under `bash -c`** (`bash -c 'source ./helper.sh; …'`), not only by direct execution — direct execution populates `BASH_SOURCE` and hides the defect.

**Empirical origin (2026-06-17, example-game-workbench-repo):** a sourceable helper self-located via `BASH_SOURCE` alone and broke when sourced under `bash -c` (empty `BASH_SOURCE`).

## Windows console-popup — a Claude-Code-headless-bash-parent condition, hooks-first

On Windows, a console-subsystem child (`python.exe` incl. `.venv/Scripts/python.exe`, `powershell.exe`, `netstat.exe`, `cmd.exe`) spawned from the **headless Claude Code Bash-tool parent** calls `AllocConsole()` and pops a focus-stealing window per invocation. This is **specifically** a Claude-Code-headless-parent condition — outside Claude Code (a real terminal, CI, a normal shell) the terminal IS the console and the same child does not pop. `git.exe` is GUI-subsystem and exempt.

**DoE ruling (2026-06-19): hooks-first.** Because the condition lives at the bash-tool parent, the fix lives there too — three coordinator layers + a reach layer, NOT a native venv-binary shim (dropped as redundant within the popup scope; it would carry an `rustc` operator-host dependency and a first-party-binary AV surface for zero popup-scope gain):

- **Layer 0** — `hooks/scripts/nudge-windows-console-popup.sh` (PreToolUse `Bash`, allow+advisory): offers the popup-safe form when a Bash command spawns a bare console child. **Windows-self-gated** — silent on macOS/Linux AND WSL2 (WSL python is a Linux ELF, no `AllocConsole`; nagging it would be fight-the-hook).
- **Layer 0'** — `hooks/scripts/nudge-windows-subprocess-popup.sh` (PreToolUse `Write|Edit|MultiEdit`, deny-with-offer): blocks authoring a console-subprocess spawn that lacks `CREATE_NO_WINDOW`/`creationflags`/`-WindowStyle Hidden` into `.sh`/`.py`/`.ps1`/`.psm1`. **Deny on all platforms** (authored code ships to Windows regardless of the authoring host), with a **throwaway-path exemption** — `*/tasks/*` and `*/state/scratch/*` are session-scratch that never ships, so the deny does not fire there (2026-06-20, Option A). Deny is justified because the **portable** suppression one-liner `creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)` is universally available at authoring time. **Caveat (2026-06-20 fix):** the offer must show the `getattr` form, NOT a bare `0x08000000` / `subprocess.CREATE_NO_WINDOW` — the integer/attribute is Windows-only and raises `ValueError` off-Windows, so complying with a bare-form offer breaks the author's own host. See § Platform-conditional guard taxonomy.
- **Layer 1** — per-repo tripwire `tests/templates/test_no_bare_console_subprocess.py`, onboarded via `/coordinator:repo-setup`.
- **Reach** — `agents/executor.md` + `agents/enricher.md` negative-spec, so doctrine arrives at the executor before it writes the call.

**Two canonical suppression markers (all layers), honored identically across C1/C2/C4:**
- `# popup-intentional-last-resort` — the console popup occurs and is accepted (pythonw fallback or genuine console need).
- `# popup-safe-env-suppressed` — the popup is suppressed at this site by env-var means and is therefore safe.

Both markers are env-agnostic. Place with the comment prefix correct for the host file, OUTSIDE any embedded interpreter string (see § Allowlist-comment markers). The env-var-NAME-based structural escape (e.g. `FOR_DISABLE_CONSOLE_CTRL_HANDLER=...`) is project-rag-local and is NOT adopted into the universal coordinator hooks — it is numerical-stack-specific. The deep in-repo catalog of the two-axis suppression (subsystem byte + Fortran-RTL env vars) lives in project-rag's `intel-fortran-rtl-console-popup.md`; the registry entry is `coordinator-tripwires.md § WINDOWS-CONSOLE-POPUP`. Plan: `docs/plans/2026-06-19-windows-console-popup-coordinator-doctrine.md`.

## Cross-platform safe filename components

<!-- spec-backlink: docs/plans/2026-06-30-cross-platform-file-naming-helper.md -->

**The canonical safe timestamp form for filenames is `YYYY-MM-DDTHH-MM-SSZ` (UTC, hyphenated, colon-free)** — e.g. `2026-05-06T14-23-07Z`, NOT `2026-05-06T14:23:07Z`. ISO-8601's standard colon separators are illegal in Windows filenames.

**NTFS-illegal characters:** `:` `?` `*` `<` `>` `|` `"` `\` `/` plus ASCII control characters (U+0000–U+001F) plus a trailing `.` or ` ` (dot or space).

**Why `:` is the acute hazard.** The colon is the Windows Alternate Data Stream (ADS) separator. When a colon-named file is committed from a non-Windows machine, Windows substitutes U+F03A (a Private Use Area lookalike for `：`) producing unreadable paths — AND a colon-named path committed to git cannot be checked out on Windows AT ALL, blocking `git checkout` of the entire working tree for every Windows collaborator. This is not a runtime preference; it is a hard tree-poison that lands the instant the commit is pushed.

**Deterministic primitive — `bin/coordinator-safe-name`.** Shell consumers call this helper directly:

- `bin/coordinator-safe-name timestamp` — emits a safe `YYYY-MM-DDTHH-MM-SSZ` UTC timestamp for use in filenames.
- `bin/coordinator-safe-name slug "<title>"` — slugifies a title to `[a-z0-9-]+`.
- `bin/coordinator-safe-name check "<name>"` — exits non-zero and prints the offending chars if `<name>` contains NTFS-illegal characters.

The canonical illegal-charset source of truth for shell consumers lives in `bin/lib/coordinator-safe-name.sh`.

**Python-side reference implementations (already-correct — cite, do not churn):**

- `_ts_for_filename` in `bin/coordinator-lesson-promote` — strips `:` and replaces `+` with `-` in the ISO timestamp before using it in a filename.
- `_slug_from_title` in `bin/coordinator-doc-new` — whitelist generator: `[a-z0-9-]` only.

These two functions are independent, pre-date the shell helper, and are NOT refactored into it. They are the correct Python-side pattern for their respective call sites; do not replace them with calls to the shell helper.

**Discriminator — filename vs. content.** Only timestamps and slugs that land in a **filename or directory name** are the hazard. ISO-8601-with-colons inside file **content** or YAML frontmatter values (`created:`, `generated_at:`, handoff `dispatched_at:`) is correct RFC-compliant ISO-8601 and MUST be left alone. Converting colons in frontmatter values to hyphens is a bug, not a fix.

**Empirical origin.** `agents/prior-art-checker.md` ~L251 and `agents/plan-coverage-checker.md` § Edit Discipline independently encode the `T14-23-07Z` form and cite the U+F03A substitution hazard — these are the prior-art instances from which the above is condensed.

## Platform-conditional guard taxonomy — three classes, three stances

A guard that protects against a platform-specific failure mode must pick its stance from *which kind* of risk it guards. Three classes, each with one correct stance. Misclassifying produces either fight-the-hook friction (a guard nagging where the risk cannot occur) or a silent protection hole (a guard going quiet where the risk is live). Empirical origin: the 2026-06-20 project-rag-ue-addon memo — a Write/Edit hook hard-denied a popup-safe `.py` on macOS, and its offered fix (`creationflags=0x08000000`) itself crashed on macOS.

1. **Runtime-platform-specific risk** — the bad thing happens when the code *runs*, on one platform only. → **Self-gate to that platform; silent no-op (exit 0) elsewhere.** The risk literally cannot occur off-platform, so any output is fight-the-hook. *Model: `nudge-windows-console-popup.sh` (C1) — Windows-self-gated, silent on macOS/Linux/WSL.*

2. **Authoring-time cross-platform risk** — code authored on platform A misbehaves when it later *runs* on platform B. → The guard may **fire on all platforms** (the authored bytes ship regardless of the current host), but:
   - (a) the offered remediation MUST be **verified-portable on the host that receives the message** — a deny-with-offer is legitimate *only* when complying does not break the author's own host. (The 2026-06-20 bug: the offer was `creationflags=0x08000000`, which raises `ValueError` off-Windows. Fix: `creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)`.)
   - (b) **exempt throwaway, non-shipping paths** (`*/tasks/*`, `*/state/scratch/*`) — session-scratch never reaches a Windows operator, so the authoring rationale does not apply and a deny there is pure friction.
   - (c) treat the **commit/CI tripwire as *a* backstop, not *the* backstop** — it is platform-neutral by construction, but in practice it is opt-in (`/repo-setup` *offers* it) and currently **scans only `*.sh`** (`tests/templates/test_no_bare_console_subprocess.py` delegates `.py`/`.ps1` back to the C2 hook). So do NOT downgrade an authoring guard to advisory-on-non-target on the assumption the tripwire will catch the gap — for `.py`/`.ps1` it will not unless the tripwire is first extended and made non-optional.
   - (d) **the remediation *shape* scales with call-site count — name both forms.** The portable inline offer `creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)` is canonical for a *single* spawn or a one-line hook paste: introducing a helper module there is heavier than the bug it fixes, so the deny-with-offer keeps the `getattr`-0 form. But once the same suppression repeats across a tree (rule of thumb: more than a handful of sites — example-game-repo carries ~40), prefer an **omit-the-key helper** over pasting `getattr`-0 N times:
     ```python
     # scripts/lib/subprocess_flags.py  (vendor + SHA-parity-test across copies)
     def no_console_creationflags() -> dict:
         """{"creationflags": CREATE_NO_WINDOW} on Windows, else {}. No-op on POSIX."""
         return {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
     subprocess.run([...], **no_console_creationflags())
     ```
     Both forms are behaviorally identical on Windows. Off-Windows the helper spreads nothing — every call site reads platform-naive (no spurious `creationflags=0` kwarg) and there is no reliance on POSIX `Popen` accepting `creationflags` at all (defensive, not merely conventional). When the helper is vendored into multiple packages, lock the copies with a SHA-parity test (example-game-repo: `tests/install/test_vendored_primitives_parity.py`) so they cannot drift. `getattr`-0 pasted at 40 sites is the outcome to steer away from. (Origin: 2026-06-20 example-game-repo-em consult, after their own tree swept nil on the parent taxonomy ask.)
   *Model: `nudge-windows-subprocess-popup.sh` (C2) — deny on all platforms, throwaway-path exempt, portable offer.* A second instance: the `.mcp.json` `cmd /c` wrapper (§ above) — authored anywhere, ENOENTs at runtime on macOS; advisory-with-portable-offer (`npx <pkg>`) is the right stance.

3. **Universal-safety guard** — the protection is platform-neutral (e.g. `block-destructive-rm`, `block-blanket-git-add`). → **No gating.** Coreutils divergence (`realpath`/`stat -c`/`date -d`) is handled by **fallback chains**, not by platform branches. *Self-gating a universal guard would create a platform where the safety net is off.*

   **Path-charset / illegal-filename guard is class-3 (not class-2), with NO directory exemption.** A guard that rejects filenames containing NTFS-illegal characters (`:`, `?`, `*`, `<`, `>`, `|`, `"`, `\`, `/`) belongs here, not in class-2, for one decisive reason: an illegal filename committed to git poisons the working tree for every Windows checkout regardless of which subdirectory it lives in. Unlike class-2 authoring-time risks (whose `*/tasks/*` / `*/state/scratch/*` exemption is justified because "session-scratch content never executes on another platform"), `tasks/` is git-tracked — a colon-named file under `tasks/` blocks `git checkout` on Windows exactly as a colon-named file under `docs/` does. The exemption rationale does not apply; there is no exemption. The illegal-path guard must be fail-closed on all directories without exception. See § Cross-platform safe filename components for the full illegal-charset list and the `bin/coordinator-safe-name` primitive.

**The load-bearing rule that generalizes beyond the popup hook:** *a deny-with-offer is only legitimate when the offer is verified-portable on the host that receives the deny.* This is the same precondition as `offer-git-c-over-cd.sh`'s "universal prompt-free equivalent safe to force" — when the offer is NOT universal on the receiving host, the correct shape is allow+advisory, not deny.

## hooks.json `command` strings run via `sh` on Unix but PowerShell on Windows — no single-line guard ports

A hook `command` string in `hooks.json` is parsed by **`sh` on macOS/Linux and by PowerShell on Windows** — the two shells share almost no guard syntax. `2>/dev/null` vs `2>$null`, `command -v` vs `Get-Command`, `||` vs `-or` — none of it ports in a single line, so a "clever" self-guarding one-liner is a fiction on one of the two platforms.

**Rule:** register **one bash entry** for a cross-platform hook (bash covers both `sh` and Git-Bash) and drop the PowerShell sibling unless *bare-Windows-without-Git-Bash* is a load-bearing target for that specific hook. A parallel pwsh command string is not free — it is a second surface that silently diverges from the bash leg (§ `.sh`/`.ps1` mirror fix to ONE leg). Maintain the second leg only when a real bare-Windows consumer needs it. *(project-rag.)*

## Test-code portability — green on CI/Linux, red on a dev Mac

A test green on CI/Linux but red on your Mac is suspect for two portability defects **in the test code itself** before you suspect your diff:

1. **A test helper hardcoding `PYTHON=python`** fails on any host where only `python3` is on PATH (modern Linux, macOS 12.3+). Resolve `python3` first (§ Python resolver), even in test scaffolding.
2. **Comparing a `.resolve()`'d expected path against an un-resolved tempfile result string** fails on macOS, where `/var` is a symlink to `/private/var`: `Path(tempfile.mkdtemp())` returns `/var/...` but `expected.resolve()` returns `/private/var/...`. Resolve **both** sides or **neither** — never one. The asymmetry is invisible on Linux (no `/var` symlink) and Windows, so it surfaces only on the Mac lane.

*(project-rag-ue-addon.)* Paired measurement discipline: `cross-platform-ci-discipline.md` § the macOS lane.

## Hardcoded build-target flags are a dark-on-Mac trap that surfaces only under real compilation

Any compile-flags artifact (a `compile_flags.txt`, a `.clangd` `CompileFlags`, a synthesized argv) fed to a **real compiler** — `clangd`'s cross-TU preamble build, not just a `-Wno-everything` libclang stub — must select `-target` / platform-defines by **host OS**, and must be validated on macOS specifically. The libclang stub path swallows a wrong `-target` and returns *something*; `clangd`'s real preamble build fails **silently** (empty results, not a loud error), so a Windows-authored flag set looks fine in unit tests and yields zero completions on a Mac. Validate LSP compile flags against the real compiler on the target OS, never against the stub. *(project-rag-ue-addon.)*
