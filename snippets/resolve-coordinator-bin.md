<!-- canonical source for resolve-coordinator-bin — edit here, then run bin/verify-snippet-sync resolve-coordinator-bin --fix -->
<!-- consumers: discovered at runtime by bin/verify-snippet-sync resolve-coordinator-bin via grep for BEGIN sentinel across $PLUGIN_ROOT -->

**What this is.** The ONE canonical way a skill/command/agent-prompt invokes a coordinator CLI
(`coordinator-doc-new`, `coordinator-lesson-add`, `coordinator-queue-append`, etc.): through the
per-CLI forwarder installed at the coordinator settings home, **by absolute path**. Never a
bareword (`coordinator-doc-new --type plan`) — bareword resolution goes through `$PATH`, and
coordinator doctrine on cross-platform invocation parity already rules the target shape for this
class of invocation: **`python3`-shebang + `.cmd`, never bareword-through-a-shell.**

**Why not bareword.** A bareword resolves through `$PATH`, and no coordinator CLI is reliably on
it. This repo's `coordinator/bin/` is empty — the executable surface is provisioned by a
separate engine layer, not this repo's tree — so a `$PATH` carrying a stale entry for it resolves
to nothing and the invocation exits 127; a fresh machine, which never had the entry, fails the
same way. Neither state is recoverable by the caller. A bareword is never the answer for a
coordinator CLI, on any machine, in any state.

**The resolution.**

    ${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/bin/<cli>

Each forwarder at that path is a `#!/usr/bin/env python3` script with a `.cmd` sibling for
Windows shells; it resolves the engine-provisioned `coordinator/bin/` itself and execs the real
CLI. Invoking the forwarder by absolute path is therefore **one hop, path arithmetic only** —
no wrapper invocation, no bareword `$PATH` dependency — and works identically on macOS and
Windows.

**Relationship to no-forwarder CLIs.** One CLI (see the gap list below) has no settings-home
forwarder yet, so this snippet's resolution doesn't apply to it. There is no snippet-level
fallback for that case any more. A fence needing that CLI today cannot self-resolve; see rung 3
below.

### Precedence ladder — which shape applies

A fence needing a coordinator CLI picks the FIRST rung that applies, not "settings-home
always":

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

### Shape A — inside a multi-line ```bash fence

Invoke the forwarder by its fully-expanded absolute path directly, on one line — do not declare
an intermediate `CC_BIN` variable first. A two-line declare-then-invoke pair is itself a
multi-statement shell fence, which the fence-shape gate flags as a violation. **The fix is to
collapse to the single-line form shown below — never to retag the block as ```` ```text ````
instead.** A `text` tag is for a block that is genuinely prose nobody should execute; retagging a
live multi-line command to `text` to dodge the fence-shape gate is the exact evasion
`NO-MULTI-LINE-SHELL-FENCE` exists to extirpate, not a sanctioned escape hatch — see that
tripwire's "known blind spot" note before reading any `text` tag as license:

```bash
"${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/bin/coordinator-doc-new" --type plan --title "<title>" --out docs/plans/...
```

If the same fence needs the forwarder more than once, repeat the full expansion on each
invocation line rather than declaring a variable — the single-line constraint applies per line,
not per fence.

### Shape B — a single inline invocation in prose

Use the fully-expanded one-liner, quoted:

    `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doc-new" --type plan --title "<title>"`

(The `CLAUDE_HOME` rung is dropped inline for readability; the fence form keeps it.)

### Shape C — `code-reviewer` dispatch (SPECIAL — do not use A or B)

`code-reviewer`'s Bash is allowlist-confined by an engine-side guard which
**hard-denies any command containing `;` `&&` `||` `|` `` ` `` `$(` `>` `<` `&` or a newline**
and requires the first token to be exactly `coordinator-doc-new` or to end with a
path-separator-anchored `/coordinator-doc-new`. Neither Shape A nor Shape B survives that guard
— `${...}` expansion is shell syntax the guard rejects outright, and the quoting required to
make an expansion "safe" puts a trailing quote on the first token, which defeats the guard's
`endswith` check regardless.

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

This is a launcher-template CLI installed through a separate path from the generic
forwarder derivation, which is why it lags. Per the precedence ladder above, a fence needing
this CLI never points at the settings home (rung 2 doesn't apply — there's no extensionless
forwarder to invoke) — it reuses an already-in-scope `_mkb_bin`/`LL_BIN` (rung 1) if one exists
in the same fence, or escalates to the dispatching EM (rung 3) if not. Do not invent a different
resolution mechanism for it, and do not point it at the settings-home forwarder path — that path
404s until it gets an extensionless form, converting a diagnosable failure into a needlessly
opaque one for no benefit over rung 1, which works today.

> Portability: no GNU-isms (`sed -i`, `grep -P`, `realpath`, `mapfile`, `declare -A`).
> No wrapper CLI is invoked anywhere in this bootstrap — the forwarder is execed directly by
> absolute path — so the Windows `CreateProcess`-no-`PATHEXT` / shebang trap that a bare-name
> `.cmd`/shebang wrapper hits when invoked from a hidden-window install child does not apply here.
