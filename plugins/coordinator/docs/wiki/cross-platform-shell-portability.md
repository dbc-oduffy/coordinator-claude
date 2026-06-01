# Cross-Platform Shell Portability

<!-- spec-backlink: docs/decisions/DR-061-portability-guard-spinoff.md -->
<!-- spec-backlink: docs/wiki/portable-code-substrate.md (hardcoded-path class) -->

> See also: `claude-code-platform-gotchas.md` (Windows/CRLF quirks), `portable-code-substrate.md` (the `repos.*` / machine-local **path** class), `build-for-someone-elses-machine` doctrine in `CLAUDE.md`.

**Purpose.** Coordinator ships shell scripts and hooks to consumers' machines. This is the canonical reference for *runtime-syntax* portability — the bash-version and coreutils-flavor traps that pass on the author's machine and fail on someone else's. It is distinct from the hardcoded-**path** class (`X:\…` → `repos.*`), which `portable-code-substrate.md` owns.

## Support matrix (the bar every script must clear)

| OS | Status | Worst-case assumption you must code against |
|---|---|---|
| **macOS** | **P0 — must work** | bash **≥ 4** (required — `brew install bash`, ahead of `/bin/bash` on PATH; see DR-148) **and** BSD coreutils (`sed`/`date`/`grep`/`readlink` differ from GNU — do **not** assume GNU coreutils; `brew install bash` does not provide them). |
| **Linux** | Likely, untested | Modern bash + GNU coreutils. Keep it working; we don't gate on it. |
| **Windows Git-Bash** | Must work | Author environment; CRLF + MSYS path-translation quirks (see `claude-code-platform-gotchas.md`). |

**Two independent axes (DR-148):**
1. **bash version** — Coordinator *requires* bash ≥ 4 (PM-ratified 2026-06-01, DR-148); stock `/bin/bash` 3.2 is not a supported execution target. bash-4 features are allowed **only behind** a `BASH_VERSINFO<4` fail-loud guard with a `brew install bash` hint (so a mis-provisioned Mac gets a clean error, never a cryptic abort). **Namerefs (`local -n`/`declare -n`) raise the floor to 4.3** — guard those scripts at 4.3, not 4.0 (`coordinator-safe-commit` is the live case). The 3.2-subset patterns (parallel arrays, temp-file maps — see `coordinator-session.sh`) remain available but are not mandated. `coordinator:setup` § 1a.0 checks the PATH-resolved bash version at setup time as a forward backstop to the per-script runtime guards.
2. **coreutils** — must stay **BSD-portable** regardless of bash version (we do NOT require GNU coreutils): `sed -i` / `date -d`/`%N` / `grep -P` / `realpath` / `readlink -f` have no GNU guarantee.

**Why macOS is the sharp edge:** the PM runs a Mac laptop, and a broken **SessionStart/PreToolUse hook** means Coordinator cannot boot to fix itself — a bootstrap trap. Boot-path hooks (`hooks/scripts/*.sh` registered in `hooks/hooks.json`) are invoked as `bash <path>`, so they run under whatever `bash` is first on PATH — which on a correctly-provisioned Mac is the brew bash ≥ 4.

**Reviewer posture vs. policy:** the `code-reviewer` lens assumes the *worst case* (an unguarded bash-4 construct is a finding) as a **detection** stance — that is how it catches missing guards. It does NOT contradict the require-bash-4 policy: a construct properly guarded by `BASH_VERSINFO<4` is explicitly *not* a finding.

## Construct → portable fix

| Non-portable construct | Why it breaks | Portable fix |
|---|---|---|
| `#!/bin/bash` shebang | On Mac pins stock 3.2 even if brew bash 5 exists | `#!/usr/bin/env bash` (picks up first bash on PATH) |
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

## The regression net — code-reviewer always-on lens

This doctrine is enforced as a **process safety net**, not a hope. The `code-reviewer` (and `code-reviewer-weekly`) agents carry a **Cross-platform portability lens (always-on)** that fires on any diff touching `*.sh` / `bin/*` / `hooks/**` and flags every construct in the table above. macOS being P0, a non-portable construct in a boot-path hook is **P1**; elsewhere **P2**. This is the diff-time backstop; the support matrix is the standard it enforces. Routed through the existing review pass (DR-061 enforcement layer) rather than a new hook surface.

**Empirical origin (2026-06-01):** a mechanical sweep found ~51 offender scripts (33 `declare -A`, 13 `mapfile`, 18 `realpath`, 10 `grep -P`, 8 `date`, plus shebangs/CRLF) — all latent macOS-3.2 / BSD-coreutils breakage shipping silently because no review lens looked for it. The PM had been hand-catching offenders at review time; this lens replaces that with a standing net.
