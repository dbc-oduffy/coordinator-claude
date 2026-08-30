<!-- Canonical source, read directly — NOT a synced snippet: no BEGIN sentinel, no embedding -->
<!-- consumers, not in the snippet registry (`verify-snippet-sync` exits 2 on this name). -->
<!-- Rule only. Rationale, measured door latencies and worked examples live in the DoE doctrine wiki (dev clone), page `coordinator-cli-resolution-rationale` -->

**What this is.** The ONE canonical way a skill/command/agent-prompt invokes a coordinator CLI
(`coordinator-doc-new`, `coordinator-queue-append`, etc.): through the per-CLI launcher installed
at the coordinator settings home, **by absolute path**. **Never a bareword**, on any machine, in
any state — no coordinator CLI is reliably on `$PATH`, so a bareword exits 127 unrecoverably.

**The resolution.**

    ${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/bin/<cli>

Every generator-known name installs a **native launcher** there: `<cli>.exe` on Windows (one
launcher image per name, dispatching on argv[0]), the bare extensionless name on POSIX. A `python3`
forwarder sits beside it, resolving the engine-provisioned `coordinator/bin/` and execing the CLI.

**The `${...}` shapes are the POSIX-host form, not the universal one.** PowerShell has no
`${VAR:-default}` defaulting, so Windows takes **rung 0** below. Some CLIs have no launcher at all
— see § CLIs with no launcher and rung 3.

### Precedence ladder — which shape applies

A fence needing a coordinator CLI picks the FIRST rung that applies, not "settings-home always":

0. **The host shell is PowerShell** (Windows) — use Shape W below, whatever the CLI. This rung
   outranks every rung under it: rungs 1-3 are all POSIX-shell fences, none runnable on a
   PowerShell-only host without spawning a bash first.
1. **`_mkb_bin` (or a file-local alias, e.g. `LL_BIN` in `skills/learn-lessons/SKILL.md`) is
   already resolved in this same fence** — reuse it: `"${_mkb_bin}/<cli>"`. Never add a second
   resolution mechanism to a fence that already has a working one; this form resolves every CLI,
   launcher or not. A resolver is reusable only WITHIN one fence, never across two Bash calls.
2. **Else, the CLI has a settings-home launcher** — Shape A (fence) or Shape B (prose).
3. **Else** (a no-launcher CLI per § CLIs with no launcher, no resolver in scope) — the fence
   cannot self-resolve; escalate to the dispatching EM, which resolves the engine's
   `coordinator/bin/` path and injects the literal, fully-resolved absolute invocation into the
   brief, as Shape C does. Never point a no-launcher CLI at the settings home.

### Shape W — PowerShell host (rung 0)

Invoke the `.exe` by absolute path through the call operator, on one line (pwsh 7 is the supported
floor; there is no 5.1 rung):

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-doc-new.exe" --type plan --title "<title>"`

`.exe` is the spelling for **every** settings-home CLI here, `coordinator-invoke` included — there
is no per-CLI exception to look up:

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" push.outstanding '{}' --repo "<repo-root>"`

**Do not reach for a `.cmd` sibling.** Only six pre-engine bootstrap resolvers carry one
(`claude-home`, `coordinator-settings-home`, `example-game-repo-control`, `machine-local`,
`platform-localize`, `resolve-coordinator-clone`) — they run before a launcher is usable. Elsewhere
`.cmd` is absent, and naming it fails command-not-found, reading as "this CLI does not exist."

When `$env:COORDINATOR_SETTINGS_HOME` is unset, resolve it with the named entrypoint —
`templates/bin/coordinator-settings-home` (pure-stdlib Python; one of the six, so its `.cmd` is
real). Never hand-derive the path, and never inline a `??` fallback: an inline default is a second
resolution mechanism, and hand-derivation is how a session concludes a working CLI is missing.

**Never pass a newline-bearing value as an argument through this shape.** Measured on the `.cmd`
path, where `cmd.exe` truncates at the first newline: a multi-line `--body`/`--note` arrives as
line 1 only — silently, exit 0, with a valid-looking record written. Untested on the native
launcher, so it holds for both. Use `--body-file` where the CLI has it (`cross-repo-memo`); else
scaffold the record and fill the body with Edit. Tripwire:
`A-CMD-SHIM-EATS-EVERY-LINE-BUT-THE-FIRST`.

### Shape A — inside a multi-line ```bash fence (POSIX hosts; see rung 0 first)

Invoke by fully-expanded absolute path, on one line — never an intermediate `CC_BIN` variable,
which makes the fence multi-statement. Never retag the block as ```` ```text ```` to dodge the
fence-shape gate (`NO-MULTI-LINE-SHELL-FENCE`):

```bash
"${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/bin/coordinator-doc-new" --type plan --title "<title>" --out docs/plans/...
```

Needing it twice in one fence? Repeat the full expansion each line; never hoist it into a variable.

### Shape B — a single inline invocation in prose (POSIX hosts; see rung 0 first)

    `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doc-new" --type plan --title "<title>"`

The bare extensionless path Shapes A and B prescribe IS the POSIX launcher. Never append an
extension to it there.

### Shape C — `code-reviewer` dispatch (SPECIAL — do not use A or B)

`code-reviewer`'s Bash is allowlist-confined by an engine-side guard rejecting `${...}` expansion
outright, so it cannot resolve its own CLI path. The **dispatching EM** resolves
`${COORDINATOR_SETTINGS_HOME:-~/.coordinator-claude-settings}` and injects the **literal,
fully-resolved, single-line absolute path with zero shell expansion** into its dispatch prompt:

    /home/<operator>/.coordinator-claude-settings/bin/coordinator-doc-new --type review-findings --slice <id> --scope <comma-paths>

The reviewer never sees a `${...}` form.

### The door — one launcher image, spelled differently per platform

Whether a call is served *warm* by the engine or degrades to that name's own Python CLI is a
performance axis, not a coverage one: every generator-known name gets a launcher either way —
`<cli>.exe` on Windows, the bare extensionless `<cli>` on macOS/Linux.

**The shapes disagree on spelling, and that is correct, not an inconsistency to harmonize. Never
carry either spelling across platforms** — on Windows the bare name is the co-installed POSIX
forwarder, which PowerShell runs as a *document*: an error mid-pipeline, standalone a silent no-op
with an EMPTY `$LASTEXITCODE`.

**The door is a fast path, never the only path.** On doubt it falls through to the Python
entrypoint the cold forwarder would have reached, argv unchanged. That covers a launcher **present
and unable to reach a server** — not an **absent** one: Windows fails loud (command-not-found);
POSIX silently reverts to the cold path, tell is latency, not an error. Check both the same way —
`<settings-home>/bin/door.engine-root.txt` is written only by the door install, never re-created by
its uninstall. No sidecar, no door. **Treat a missing launcher as the install defect it is**
(remedy: `python3 -m coordinator_core.install.substrate`, or `/coordinator:install`) — take the
cold path for the one call that unblocks you, then report it; never quietly adopt the cold spelling
as standing doctrine. Tripwire:
`A-DOCTRINE-SURFACE-THAT-NAMES-CMD-CONSCRIPTS-EVERY-READER-ONTO-THE-COLD-PATH`.

## CLIs with no launcher

The set is derived from `coordinator/bin/`, leaving two residues. Rung 2 applies to neither —
nothing is there to invoke, so never take the launcher path; it 404s.

**The generator gap — one CLI.** `platform-localize` installs a `.py`/`.cmd` pair only: no bare
name, no `.exe`. Take rung 1 or 3, never a different resolution mechanism.

**The publisher chain — by construction, not a gap.** `percolate-round`, `percolate-gate`,
`percolate-push`, `publish` and `coordinator-publish` produce the published engine and are
deliberately not carried into it, so no launcher is written for them and none will be. Invoke them
repo-relative out of the engine's own source checkout —
`python "<engine-root>/coordinator/bin/<cli>.py" …` — never through the settings home, and never
file the absence as an install defect.

> Portability: no GNU-isms (`sed -i`, `grep -P`, `realpath`, `mapfile`, `declare -A`).
> No wrapper CLI is invoked in this bootstrap — the launcher is execed directly by absolute path —
> so the Windows `CreateProcess`-no-`PATHEXT` / shebang trap does not apply here.
