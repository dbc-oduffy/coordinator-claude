# Linux cloud dogfood — doctrine-side friction log

**Date:** 2026-09-05
**Host:** Claude Code Cloud container. Ubuntu 24.04.4, x86_64, 4 vCPU / 16 GB, running as `root`
with `HOME=/root`, repos at `/home/user/…` (**not** under `HOME`). Python 3.11.15, git 2.43.0,
node 22.22.2, jq 1.7, bash 5.2.21, `claude` CLI 2.1.261. **No `gh`, no PowerShell, no interactive
TTY, and — structurally — no session restart.**

This is the doctrine half of a joint pass. The engine half, with the four patches landed and the
full finding list, is `claude-klabauter/docs/reference/linux-cloud-dogfood-friction.md`.
**No patches are proposed in this repo.** Every finding below is either a documentation
reconciliation or a consequence of the restart gate, and both are the maintainers' calls.

---

## What worked

The plugin **installs cleanly on Linux from the public marketplace**, non-interactively, in a
container, as root:

```
$ claude plugin marketplace add dbc-oduffy/coordinator-claude
√ Successfully added marketplace: coordinator-claude (declared in user settings)
$ claude plugin install coordinator@coordinator-claude
√ Successfully installed plugin: coordinator@coordinator-claude (scope: user)
$ claude plugin list
  > coordinator@coordinator-claude   Version: 4.1.0   Scope: user   Status: √ enabled
```

`installed_plugins.json` is written correctly, and the engine's later
`register_live_plugin_root` step repointed it at the live clone
(`PASS [plugin] coordinator@coordinator-claude now resolves live`). Home resolution is correct
under a root `HOME` with repos outside it — `templates/bin/machine-local` and
`templates/bin/coordinator-settings-home` both walk `CLAUDE_HOME → HOME → USERPROFILE` properly,
and `lib/home_resolution_lint.py` is a real AST guard against regressions there. Nothing in the
core loop needed `bash`, `jq`, or `gh`.

---

## D1 — The restart is load-bearing, and it is the whole story here — BLOCKER

`INSTALL.md` Step 2 is titled "The restart (load-bearing gate)". `hooks/hooks.json:2` states the
mechanism without hedging:

> REGISTRATIONS IN THIS FILE ARE READ AT SESSION START AND CACHED: adding or removing an entry
> here reaches NO already-running session until it runs `/reload-plugins` or restarts.

So on this host the plugin is installed and inert. Concretely, and each of these was confirmed
rather than assumed:

- No `/coordinator:*` slash command exists in the running session, so Steps 3, 5 and 6 of the
  documented sequence (`/coordinator:install`, `/coordinator:setup`, `/coordinator:repo-setup`)
  cannot be invoked at all.
- `${CLAUDE_PLUGIN_ROOT}` — used in every hook command and across 90+ skill and command files — is
  only expanded for a plugin the harness loaded at startup. Unexpanded, every hook `args` entry is
  a literal non-path.
- `commands/install.md` records that the install surface's live tier "CANNOT run inside a
  subagent — the EM or PM must launch `claude --plugin-dir <sandbox>/coordinator` interactively",
  which needs a second interactive process this environment does not have either.

**Nothing here is a bug.** It is a documented, deliberate design that a restart-less environment
cannot satisfy. The suggestion is narrow: **say so in INSTALL.md.** A short "environments this
install model does not support (and why)" note would save an agent in a CI runner, a container, or
a cloud session from walking six steps to discover step 2 is a wall.

## D2 — With no restart, every Bash guard is silently absent — worth stating loudly

`hooks/hooks.json` wires `PreToolUse(Bash|PowerShell)` through an HTTP forwarder to a local engine
endpoint, and the file's own comment is explicit that a dead forwarder "is not a deny here — it is
a connection refusal … which this path FAILS OPEN on, silently disarming every guard behind it
fleet-wide."

Fail-open is the right call and is not in question. What is worth surfacing is that **a container
install's default state is fail-open**: the plugin is enabled, `claude plugin list` says so, and
none of the destructive-`rm` / destructive-git / `--no-verify` guards are running. The README
already states loudly that a doctrine-only install has none of these guarantees; this is the
adjacent case — engine *and* plugin both installed, guards still absent, and nothing says so.

## D3 — `--non-interactive` cannot complete an unattended install — FRICTION

Setting the restart aside entirely, `/coordinator:install --non-interactive` fails loud on three
prompts with no environment-variable or flag defaults: operator identity
(`commands/install.md:131`, "`--non-interactive` with none stored: fail-loud"), engagement posture
(`:167`), and project type (`:350`, "fails loud (no safe default)"). An unattended install on a
fresh box therefore aborts partway through by design. If unattended installs are meant to be
supported, these three want `COORDINATOR_OPERATOR_*`-style inputs.

Related: the restart instructions ask the human to press **Shift+Tab** to cycle into auto-accept
mode (`INSTALL.md:259-262`) "so the install runs without a prompt on every action". No headless
equivalent (`--permission-mode`, a settings.json key) is named.

## D4 — `gh` is documented three different ways — FRICTION

| Source | Says |
|---|---|
| `INSTALL.md` § Requirements | **Required** — "backs clone auth and merge/release ceremonies. Authenticate before installing (`gh auth login`)." |
| `README.md` § Prerequisites | **Optional** — "Only needed for the merge/release ceremonies; the setup probe treats it as advisory, not a blocker." |
| `skills/setup/SKILL.md` | "demoted from hard; WARN does not block" |
| `bin/doctor-probes.toml` | "hard prereq" |

`gh` is absent on this box and nothing in the install or the core planning/execution loop needed
it. The merge/release scripts (`bin/merge-gate-and-pr.py`, `bin/percolate-push.py`,
`bin/orphan-branch-sweep.py`, `bin/merge-recovery-and-tag-cut.py`) genuinely do. The README's
framing matches observed behaviour; INSTALL.md and `doctor-probes.toml` are the two that want
updating. Note also that `gh auth login` is itself interactive, so listing it as a hard
prerequisite makes an unattended install impossible on that ground alone.

## D5 — Pipeline findings that live on this side of the seam

Both were reproduced against the engine but are doctrine's call, so they are named here too. Full
evidence in the engine-side log at **F11** and **F12**.

- **The sizing lobby's two halves do not join.** `sizing-assemble` computes a route and writes
  nothing; `coordinator-doc-new --type sizing-object` writes an object with hardcoded `tshirt: XS`
  / `route: dispatch` defaults and accepts no flag to receive the computed route. The route is
  transcribed by hand between them — in the lobby that is the system's own front door, and by the
  system's own standard ("that has relocated the transcription, not discharged it") this is the
  highest-value thing on either list to close.
- **The plan scaffold accepts a sizing object that routes away from planning.** An unedited object
  carrying `route: dispatch` and `premise.evidence: PLACEHOLDER` was accepted by
  `coordinator-doc-new --type plan --sizing-object`, which scaffolded the plan and flipped the
  object `draft → routed` — although `skills/plan/SKILL.md` Branch A says `route: dispatch` means
  "plan is not the room". The skill is candid that the wall is EM behaviour and that *absence* is
  unenforceable; a **contradicting** route is not absence, and is one comparison away from a
  refusal by the same tool that already hard-refuses a missing `--sizing-object`.

---

## What this does not claim

One host, one pass, one day. Nothing here is a claim about macOS or Windows. The plugin's tree is
large enough that "no evidence found" is not "no such case exists" — the sweeps that produced these
findings were broad but not exhaustive, and where a conclusion rests on reading rather than running
it is called out in the engine-side log.
