# Cross-Platform Invocation Parity

<!-- spec-backlink: docs/plans/2026-07-21-macos-first-class-invocation.md -->

**Purpose.** An entrypoint's *invocation path* — the mechanism an OS uses to turn "run this
file" into a running process — is a per-OS artifact, distinct from the entrypoint's behavior
once running. A platform-targeted migration can regress an OS's invocation path while leaving
behavior identical and every other signal green (tests pass, the code is correct, the author's
own OS runs it fine). This wiki codifies the invariant that prevents that regression from
shipping silently, and the incident that proved it needs to be a test, not a hope. See also
`cross-platform-shell-portability.md` (bash-version / BSD-coreutils code portability) and
`bash-on-windows-gotchas.md` (the `python3`-shebang carve-out this doctrine licenses) — distinct,
paired disciplines; cross-reference all three.

---

## The principle

**A platform-targeted change must not regress another platform's invocation path.** Every
executable entrypoint ships an invocation path for every supported OS — shebang + exec-bit for
Unix, a launcher for Windows — and parity between the two is enforced by a red test, not by
hoping someone dogfoods the other OS before it ships.

This is deliberately narrower than "cross-platform behavioral parity" (the ops an entrypoint
runs must already behave identically once invoked — that is a different, already-covered
concern). Invocation parity is about the *launch* layer only: can the OS start the process at
all.

## The two-path model

| OS | Invocation mechanism | What breaks it |
|----|----------------------|----------------|
| Unix (macOS/Linux) | Shebang (`#!/usr/bin/env python3`) as line 1 + `100755` exec bit in the git index | Missing/wrong shebang line; exec bit lost (a plain working-tree `chmod +x` is silently reset by `core.fileMode=false` on Windows clones — the *index* mode is what ships, stamp it with `git update-index --chmod=+x`) |
| Windows | A co-located launcher (`.cmd`/`.ps1`) resolved via `PATHEXT` when the entrypoint is invoked bareword from `cmd.exe` | Missing launcher; launcher drifts out of sync with the target it wraps |

**The two-sided invariant.** For a `python3`-shebang + `.cmd` entrypoint, both halves are
independently load-bearing:

1. **`.cmd`-coverage licenses the shebang.** On Windows, a bareword-from-`cmd.exe` invocation
   never consults the shebang at all — `PATHEXT` resolution finds the `.cmd` first — so a
   `python3` shebang on line 1 is safe (not merely tolerated) *only* under guaranteed `.cmd`
   coverage. Without that coverage the same shebang exec-127s on a stock Windows Python install
   (`python3` is frequently absent; only `python`/`py` are guaranteed).
2. **No-bareword-`.py`-through-git-bash is the second, equally load-bearing half.** A caller that
   invokes the entrypoint as a bareword `.py` from inside a git-bash shell context (a ceremony
   `.md` shell block, a skill, a hook) *does* read and honor the shebang — the `.cmd` does not
   rescue a `.py`-suffixed bareword from a bash context. A caller violating this exec-127s with
   no `.cmd` to save it. This is the CAT3 trap: the safety property of invariant (1) is
   conditional on callers respecting invariant (2), not unconditional.

Both invariants are test-enforced, not merely documented — a two-layer gate: layer (a) asserts
every entrypoint's shebang + exec-bit + `.cmd` triple; layer (b) asserts no caller invokes a
`coordinator/bin/*.py` entrypoint as a bareword inside a shell block. Documentation without teeth
is exactly what let the incident below ship unnoticed.

## The generator-owns-both rule

The two paths must be emitted by **one generator, one call per entrypoint** — never two
independently-maintained emitters that can drift apart. `gen-launcher-shim.py` is that
generator: it owns Unix-enablement (shebang + exec-bit stamping) symmetric with `.cmd`/`.ps1`
emission, idempotently. Splitting the two into separate tools recreates the exact failure mode
this doctrine exists to prevent — one side gets a feature, an install-time fix, or a bugfix, and
the other silently doesn't.

## The W4a incident (cautionary precedent)

The `debash(W4a)` wave (`b5a4192c`) renamed 109 `coordinator/bin/*.sh` polyglot trampolines to
pure-Python `.py` files and generated a Windows `.cmd` launcher for every one — but built **no
Unix invocation path at all**. Result: **109/109 Windows `.cmd` launchers, 0/109 Unix paths.**
None of the 109 carried a shebang (line 1 was `from __future__ import annotations`), and 35/109
had also lost their exec bit. Every coordinator ceremony that invoked a renamed trampoline
bareword, or via `subprocess.run(["bash", <.py>])`, was broken on macOS/Linux from the moment the
wave landed. It went unnoticed until a macOS `/workday-start` Step 0 aborted — weeks later.

**The defect was the asymmetry itself, not any single file.** The pre-W4a files were `#!/bin/sh`
polyglots that ran on all three OSes; the migration silently kept only the Windows half of the
replacement. Nothing — no test, no doctrine principle with teeth — caught it, because the
project's own dev machine is Windows-primary and the Unix path was never exercised in that loop.
A Windows-first wave that strips the Unix path is a parity regression, and it is catchable *only*
by a test that runs on (or reasons about) the other OS — dogfooding the other OS is not a
substitute for that test, because dogfooding is exactly the step that didn't happen here for
weeks.

## The python3-shebang reconciliation

`bash-on-windows-gotchas.md` bans a `python3` shebang on a `/bin/` script, because a bareword
Windows invocation of a shebang-only file (no `.cmd`) exec-127s on a stock python.org install.
That ban's premise — no guaranteed `.cmd` coverage — does not hold for the class this doctrine
governs: a pure-`.py` entrypoint with a generator-guaranteed co-located `.cmd`. See
`bash-on-windows-gotchas.md` for the full discriminant (which shape is my entrypoint → which rule
applies) and the two-invariant carve-out text.

## Terminal state — single target shape, not two coexisting classes

**PM ruling.** There is no operator-bareword-human-caller surface for
`coordinator/bin` CLIs — humans do not invoke them directly — so there is nothing for a permanent
polyglot class to preserve. The single target shape for every `coordinator/bin` entrypoint is
**pure-Python `python3`-shebang + `.cmd`**, invoked only via an explicit Python interpreter
(ceremony/shell contexts) or the `.cmd` (Windows `cmd.exe`) — never bareword-through-a-shell,
never a bash/git-bash wrapper.

The ~16 remaining `#!/bin/sh` polyglot CLIs (the ones the claude-klabauter
`block_bin_polyglot_break.py`/`block-bin-polyglot-break.sh` guard used to protect, until it was
removed in claude-klabauter `f3b8b513` — the polyglot invariant it enforced is retired) are **legacy
debt on the kill-bash roadmap**, not a coequal permanent class held open-ended. The polyglot shape
was a crutch for shell-invoking a Python tool; since nothing should shell-invoke these bareword,
the crutch has no remaining job. Any current git-bash reliance on one of the ~16 is a bug to gut,
not a surface to preserve.

`cross-repo-memo` is named the first migration candidate: its logic migrates to pure Python on
Claude-klabauter with a thin CLI/`.cmd` front, no bash wrapper. That rewrite is a separate claude-klabauter-routed
workstream (§ Cross-repo write discipline — code/install-surface changes route via
`cross-repo-memo` + PM-relay, never a direct DoE write to claude-klabauter), not folded into the plan that
ratified this doctrine.

## Forward obligation across the DR-047 boundary

The invocation-parity invariant (Unix shebang+exec-bit path symmetric with the `.cmd` launcher,
generator-owned) is a **preserved forward obligation**, not a DoE-implementation-only detail. If
`claude-klabauter` later extracts the bin-generation/install surface under DR-047, the invariant
travels with the surface — it does not lapse on extraction. Any DoE→claude-klabauter relay of this
obligation is a doctrine-seeding forward-notice (not a bug report), routed via
Claude-klabauter `coordinator/bin/cross-repo-memo` + PM-relay per `CLAUDE.md § Cross-repo
write discipline`.

## The reader-side half — what the docs tell an operator to TYPE {#reader-side-invocation}

*[universal] Every rule above this line is addressed to an **author** shipping an entrypoint.
None is addressed to a **reader** invoking one, and that gap hits every Windows operator on
first contact.*

Doctrine, skills, and snippets historically cited coordinator binaries in the bareword form
(POSIX-host only):

```
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/<cmd>"
```

**On Windows PowerShell that is not executable.** The extensionless file is a shebang script, and
`CreateProcess` never reads a shebang. The error names neither the cause nor the fix:

```
InvalidOperation: Cannot run a document in the middle of a pipeline:
C:\Users\<you>\.coordinator-claude-settings\bin\install-health-run.
```

**Use the `.cmd` twin** — one exists beside every entry, and `BIN-ENTRYPOINT-NEEDS-CMD-TWIN`
enforces that it does (verified at the time of writing: 371 extensionless entries, 373 `.cmd`,
zero missing twins):

```powershell
& "$HOME\.coordinator-claude-settings\bin\install-health-run.cmd"
```

Git Bash resolves the bareword form fine; this is a PowerShell/`cmd.exe` issue specifically, and
PowerShell is the documented shell on a **P0 primary platform**.

**Why this section exists at all — the generalisable point.** The hazard was already covered three
times over (`BIN-ENTRYPOINT-NEEDS-CMD-TWIN`, `WINDOWS-PYTHON-SHEBANG`, `POSIX-EXEC-ASSUMPTION-GUARD`),
and this wiki — which owns the subject — contained the string "PowerShell" zero times. The guards
correctly ensured the `.cmd` twin *exists*; nothing changed what the docs *show you to type*.
**Guard coverage was mistaken for documentation coverage.** A hazard can be thoroughly enforced on
the producing side and still hit every consumer on first contact, because enforcement answers *"did
we ship it right?"* and nobody asked *"does the reader know what to run?"*

**Resolved.** The durable fix named as "its own sized piece of work" above is
`coordinator/snippets/resolve-coordinator-bin.md`'s precedence ladder: rung 0 / Shape W is now the
canonical citation form on a PowerShell host (the `.cmd` twin invoked via the call operator, as
shown above), and the bareword/`${...}` form above is retained only as the POSIX-host rung. New
doctrine cites the snippet rather than restating either form. Evidence: DoE-claude
`state/2026-08-07-oduffy-pc-install-dogfood-friction-log.md` § F5.

## See also

- `cross-platform-shell-portability.md` — code-level bash/BSD-coreutils portability (a different
  layer: whether a script *runs correctly* once invoked, not whether it can be *launched*).
- `bash-on-windows-gotchas.md` — the `python3`-shebang ban and its `.cmd`-coverage carve-out.
- `install-surface-completeness.md` — the broader "works on every machine" doctrine this wiki is
  the invocation-layer instance of; § Windows-chmod commit mechanic for the exec-bit-in-index
  detail.
- `docs/decisions/DR-076-cross-platform-invocation-parity.md` — the ratifying decision record.
