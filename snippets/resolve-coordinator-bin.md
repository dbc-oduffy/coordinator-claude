<!-- canonical source for resolve-coordinator-bin — edit here, then run bin/verify-snippet-sync resolve-coordinator-bin --fix -->
<!-- consumers: discovered at runtime by bin/verify-snippet-sync resolve-coordinator-bin via grep for BEGIN sentinel across $PLUGIN_ROOT -->

**What this is.** The ONE canonical way a skill/command/agent-prompt invokes a coordinator CLI
(`coordinator-doc-new`, `coordinator-lesson-add`, `coordinator-queue-append`, etc.): through the
per-CLI forwarder installed at the coordinator settings home, **by absolute path**. Never a
bareword (`coordinator-doc-new --type plan`) — bareword resolution goes through `$PATH`, and
coordinator doctrine on cross-platform invocation parity already rules the target shape for this
class of invocation: **`python3`-shebang + `.cmd`, never bareword-through-a-shell.**

**Why not bareword.** No coordinator CLI is reliably on `$PATH` — the executable surface is
provisioned by a separate engine layer, not this repo's tree — so a bareword exits 127 on both a
stale machine and a fresh one, unrecoverably. Never a bareword, on any machine, in any state.

**The resolution.**

    ${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/bin/<cli>

Each forwarder at that path is a `#!/usr/bin/env python3` script with a `.cmd` sibling for
Windows shells; it resolves the engine-provisioned `coordinator/bin/` itself and execs the real
CLI. The forwarder itself is one hop, path arithmetic only — no wrapper invocation, no bareword
`$PATH` dependency.

**The `${...}` expansion above is POSIX shell syntax, and it is not portable.** PowerShell does
not implement `${VAR:-default}` defaulting at all, so on a PowerShell-only host Shape A/B are
unrunnable except by spawning a bash to expand them — which adds the processes the forwarder was
built to avoid, and subjects every `/`-leading argument to MSYS path conversion, which silently
rewrites it to a Git-install path. Windows takes **rung 0** below; the `${...}` shapes are the
POSIX-host form, not the universal one.

**Relationship to no-forwarder CLIs.** One CLI (see the gap list below) has no settings-home
forwarder yet, so this snippet's resolution doesn't apply to it. There is no snippet-level
fallback for that case any more. A fence needing that CLI today cannot self-resolve; see rung 3
below.

### Precedence ladder — which shape applies

A fence needing a coordinator CLI picks the FIRST rung that applies, not "settings-home
always":

0. **The host shell is PowerShell** (Windows) — use Shape W below, whatever the CLI. This rung
   outranks every rung under it: rungs 1-3 are all POSIX-shell fences, and none of them is
   runnable on a PowerShell-only host without spawning a bash first. Reaching for a lower rung
   on Windows is the defect this ladder exists to prevent, not a fallback.
1. **`_mkb_bin` (or a file-local alias, e.g. `LL_BIN` in `skills/learn-lessons/SKILL.md`) is
   already resolved in this same fence** — reuse it: `"${_mkb_bin}/<cli>"`. Do not introduce a
   second resolution mechanism into a fence that already has a working one; this form resolves
   every CLI, forwarder or not. (`skills/handoff/SKILL.md`'s `coordinator-doc-new` call is this
   rung — `${_mkb_bin}` is already in scope in the same fence for `read-frontmatter-field.py`, so
   reusing it there is correct, not a gap to close.)
2. **Else, the CLI has a settings-home forwarder** — use Shape A (fence) or Shape B (prose)
   below.
3. **Else** (the one no-forwarder CLI in the gap list, and no resolver already in
   scope) — the fence cannot self-resolve; escalate to the dispatching EM, which resolves the
   engine's `coordinator/bin/` path directly and injects the literal, fully-resolved absolute
   invocation into the brief — the same pattern Shape C below already uses for the
   allowlist-confined reviewer. Never point a no-forwarder CLI at the settings home.

**Why rung 1 exists.** Shell variables do not survive between separate Bash tool calls, so a
resolver is only reusable *within* one fence — never across two Bash invocations, however close
together. That per-fence scoping is exactly why rung 2 exists at all: a standalone fence that
needs only to invoke a CLI, with no resolver already in scope, gets a one-line settings-home
invocation instead of hand-deriving that resolution itself.

### Shape W — PowerShell host (rung 0)

Invoke the forwarder's `.cmd` sibling by absolute path through the call operator, on one line
(pwsh 7 is the supported floor; there is no 5.1 rung):

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-doc-new.cmd" --type plan --title "<title>"`

When `$env:COORDINATOR_SETTINGS_HOME` is unset, resolve it first with the named entrypoint —
`templates/bin/coordinator-settings-home` (pure-stdlib Python, `.ps1`/`.cmd` siblings) — and use
its output. Never hand-derive the path, and never inline a `??` fallback: the resolver is the
one sanctioned source, and an inline default is a second resolution mechanism.

No bash is spawned, so no MSYS path conversion touches the arguments — a `/`-leading operand
arrives at the CLI as written. The `.cmd` sibling resolves the interpreter and execs the
co-located Python forwarder directly, and is hardened for the Windows traps (no delayed-expansion
dependency, WindowsApps alias filtering, backslash requoting).

**Never pass a newline-bearing value as an argument through this shape.** `cmd.exe` truncates the
command line at the first newline, so a multi-line `--body`/`--note` arrives as line 1 only —
silently, exit 0, with a valid-looking record written. Use `--body-file` where the CLI has it
(`cross-repo-memo`); where it does not, scaffold the record and fill the body with Edit. Tripwire:
`A-CMD-SHIM-EATS-EVERY-LINE-BUT-THE-FIRST`.

### Shape A — inside a multi-line ```bash fence (POSIX hosts; see rung 0 first)

Invoke the forwarder by its fully-expanded absolute path, on one line — never an intermediate
`CC_BIN` variable, which makes the fence multi-statement. Collapse to the single-line form; never
retag the block as ```` ```text ```` to dodge the fence-shape gate (`NO-MULTI-LINE-SHELL-FENCE`):

```bash
"${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/bin/coordinator-doc-new" --type plan --title "<title>" --out docs/plans/...
```

If the same fence needs the forwarder more than once, repeat the full expansion on each
invocation line rather than declaring a variable — the single-line constraint applies per line,
not per fence.

### Shape B — a single inline invocation in prose (POSIX hosts; see rung 0 first)

Use the fully-expanded one-liner, quoted:

    `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doc-new" --type plan --title "<title>"`

(The `CLAUDE_HOME` rung is dropped inline for readability; the fence form keeps it.)

### Shape C — `code-reviewer` dispatch (SPECIAL — do not use A or B)

`code-reviewer`'s Bash is allowlist-confined by an engine-side guard which
**hard-denies any command containing `;` `&&` `||` `|` `` ` `` `$(` `>` `<` `&` or a newline**
and requires the first token to be exactly `coordinator-doc-new` or to end with a
path-separator-anchored `/coordinator-doc-new`. Neither Shape A nor Shape B survives it —
`${...}` expansion is shell syntax the guard rejects outright.

The confined reviewer therefore cannot resolve its own CLI path. The **dispatching EM** resolves
`${COORDINATOR_SETTINGS_HOME:-~/.coordinator-claude-settings}` itself and injects the **literal,
fully-resolved, single-line absolute path with zero shell expansion** into the reviewer's
dispatch prompt, e.g.:

    /home/<operator>/.coordinator-claude-settings/bin/coordinator-doc-new --type review-findings --slice <id> --scope <comma-paths>

Describe this in skill/agent text as: the dispatching EM resolves the settings home and injects
the literal absolute command into the reviewer's brief — the reviewer itself never sees a
`${...}` form.

## CLIs with no forwarder yet (generator gap)

The forwarder set is now derived automatically from `coordinator/bin/`, which closed this gap
for every CLI except one. `platform-localize` has a `.py`/`.cmd` pair installed but no bare
extensionless forwarder in the settings home today:

    platform-localize

A fence needing this CLI never points at the settings home (rung 2 doesn't apply — there is no
extensionless forwarder to invoke): reuse an in-scope `_mkb_bin`/`LL_BIN` (rung 1), else escalate
to the dispatching EM (rung 3). Never invent a different resolution mechanism, and never point it
at the forwarder path — that path 404s until it gets an extensionless form.

> Portability: no GNU-isms (`sed -i`, `grep -P`, `realpath`, `mapfile`, `declare -A`).
> No wrapper CLI is invoked anywhere in this bootstrap — the forwarder is execed directly by
> absolute path — so the Windows `CreateProcess`-no-`PATHEXT` / shebang trap that a bare-name
> `.cmd`/shebang wrapper hits when invoked from a hidden-window install child does not apply here.
