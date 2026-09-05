# No New Bash Surfaces — Fleet Directive for Consumer Repos

<!-- spec-backlink: cross-repo/archive/2026-07-21-project-rag-em-debash-must-be-fleet-propagated.md -->
<!-- ratified 2026-07-21 (PM): elevates de-bash from coordinator-internal migration to a propagated fleet directive. -->

**Purpose.** De-bash — porting structural bash off the shell interpreter and onto a repo's own
first-class runtime — was a **coordinator-INTERNAL** migration: it is how the coordinator's own
hooks and scripts moved off bash. Nothing propagated the *rule* downward, so every consumer repo
independently
(1) hit a real local problem a `.sh` would solve, (2) wrote the bash wrapper, (3) mandated it
in its own CLAUDE.md, and (4) then paid the claude-klabauter subagent-indirection guard's collateral tax
on **every** subagent in that repo, forever, until someone noticed. This wiki is the
consumer-facing directive that stops the independent-reinvention loop. It is the downstream
half of `cross-platform-shell-portability.md`, which owns the coordinator's own runtime-syntax
portability.

**Audience.** Every repo that installs / consumes the coordinator plugin (project-rag, example-game-repo,
project-rag-ue-addon, example-sim-repo, example-repo, cockpit, example-os-repo, …). Not the coordinator's own
internal surfaces — those are already on the claude-klabauter Python track (`cross-platform-shell-portability.md`).

## The directive

1. **No new shell-interpreter-invoked file surfaces.** If you are reaching for a `.sh` to wrap
   tooling, that is the smell. Build the surface in your own repo's first-class runtime instead —
   for the coordinator itself that realization is **python-native / claude-klabauter-compliant**, but the
   invariant every consumer repo owes is the runtime choice, not that specific language. This
   applies especially to surfaces a subagent will invoke, and to anything you would then
   *mandate* in your CLAUDE.md.

2. **Existing bash migrates** off the shell interpreter and onto your repo's first-class
   runtime — on the claude-klabauter track that means python-native, the same engine-ification
   pattern the coordinator used on its own hooks. Sequence real bootstrap/pre-Python bash
   (settings-home helpers, install scripts, doctor probes) as a plan against the claude-klabauter track
   rather than blind-porting in a direction you will re-port.

3. **Rationale consumers can see.** The claude-klabauter subagent-indirection guard
   (`coordinator_core/bash_guards/block_subagent_destructive_action.py`) denies
   `<interpreter> <file>` for subagents, but only for a specific, deliberately narrow interpreter
   set: `_SHELL_FILE_INTERPRETERS` (line 406 as of claude-klabauter `37e6d9cd1e99`) is `{bash, sh, zsh}`,
   and python is excluded on purpose. The wider wrapper-probe regex, `_WRAPPER_PROBE_RE` (lines
   388-390, same SHA), matches
   `bash|sh|zsh|python3?|env|xargs` — so a `python3 <file>` invocation is probed but never
   denied on the file-interpreter path, and `node` is not even in the probe pattern, let alone
   the deny set. This is a legitimate anti-smuggling measure (a subagent could otherwise hide a
   denied `git`/`rm` behind one layer of `bash <script>`), and the guard's own docstring names
   the collateral honestly: a legitimate `bash run-tests.sh` is denied too. So **a bash wrapper
   taxes every subagent in your repo**; a python-native surface does not — not because the guard
   is blind to interpreters generally, but because it is scoped, on purpose, to the shell trio a
   bash-wrapper habit actually produces. Any other first-class runtime (python-native, node, or
   otherwise) sits outside that scope on the same terms. The guard is right — the fix is
   upstream of it, in not seeding the bash surface.

4. **There is an irreducible FLOOR — bash is allowed and expected pre-interpreter.** "No new
   bash" is not "no bash, ever": the thing that *finds and launches* python cannot itself be
   python-you-cannot-yet-run. Your migration taxonomy needs FLOOR as a real bucket alongside
   PORT / DELETE+REPOINT / WINDOWS-GATE — do not bucket FLOOR files as PORT, and don't try to
   port them; you'll be re-porting forever. The coordinator system keeps exactly **one** FLOOR
   bash file — `lib/spawn-hidden.sh` (now claude-klabauter `coordinator/lib/spawn-hidden.sh`, not
   this repo's own `coordinator/lib/`) — plus one pure-python launcher *generator*
   (claude-klabauter `coordinator/bin/gen-launcher-shim.py`). Interpreter resolution itself no
   longer needs a FLOOR shim at all: it went the other direction, from bash FLOOR to a plain
   resolution contract (`COORDINATOR_PYTHON` env → `machine-local get coordinator.python` →
   PATH fallback — see `machine-local-registry.md § coordinator.python resolution contract`).
   That is the entire pre-interpreter surface. Target
   shape: shrink bash to that FLOOR, bake the resolved interpreter path at install time, and
   make everything above the resolution line your repo's first-class runtime — plain python on
   the coordinator's own track, whatever the equivalent realization is on yours.

   The practical test before bucketing a file: **does this run AFTER an interpreter is
   resolvable?** If yes → PORT. If no → FLOOR. Cold-bootstrap orchestrators (install/setup
   scripts) need this check applied explicitly, not assumed portable — bucket them
   VERIFY-near-floor rather than waving them through as FLOOR by default.

   VENDOR the resolver pattern per repo — do not couple to a coordinator runtime surface. A
   shared runtime resolver library is an explicitly ratified NON-GOAL (see `windows-cmd-shims.md`
   § Non-goals, "Shape β"): it inverts the Central authoring-time direction and creates a
   runtime dependency for every consumer.

5. **FLOOR need not be bash — SHIM is the non-bash pre-interpreter bucket.** FLOOR exists because
   *something* has to find and launch the interpreter before "python-native" applies; it does not
   follow that the something is bash. Where a repo's hooks are exec-form (no shell `source`s a
   library into them — see item 1), the constraint that pins the coordinator's own FLOOR to bash
   (`resolve-python.sh` sourcing into a shell hook) does not hold, and the pre-interpreter surface
   can itself be non-shell: e.g. a `python3`-shebang, stdlib-only, venv-fenced POSIX launcher
   paired with a generated `.cmd`/`.ps1` Windows twin, both emitted by one generator so they
   cannot drift. Bucket this shape **SHIM**, not FLOOR and not PORT — it sits where FLOOR sits in
   the migration taxonomy (pre-interpreter, not portable-away) but does not carry the "bash is
   allowed here" license FLOOR grants. The practical test: if the pre-interpreter surface can be
   built with zero shell interpreter involved for your repo's constraints, it is SHIM; if a shell
   `source` or a bootstrap-time shell dependency is genuinely irreducible (as it still is for the
   coordinator's own hooks), it is FLOOR. (Fed back by project-rag as its reference-leg
   consumer-migration finding, 2026-07-29 — see `## Reference leg` below.)

## Why this is a directive, not a preference

The tax is structural and recurs by construction. It is not a bug in any one repo — it is a
fleet pattern that reappears in each consumer independently until de-bash is a rule consumers
*follow*, not merely an effort the coordinator ran on itself. Windows/PC is the primary machine
and audience, where every bash process spawn also pays a brutal fork/exec tax (`coordinator.local.md`).

## Windows console-flash (popup) safety — deliberately de-emphasized

The coordinator built console-flash suppression machinery — `lib/spawn-hidden.sh`, a `pythonw`
preference that formerly lived in the now-retired `resolve-python.sh` FLOOR shim (interpreter
resolution has since moved off bash entirely — see the FLOOR note above), and the
`bin/verify-no-console-flash.py` merge-gate linter (now claude-klabauter
`coordinator/lib/spawn-hidden.sh`, `coordinator/bin/verify-no-console-flash.py`). **PM ruling, 2026-07-21: in practice the guard caused about as many
problems as it solved.** Console popups were a genuine annoyance, but the bash bloat retained
to justify the guard was the worse problem.

Therefore: **killing bash outranks preserving popup-safety when the two are in tension.** If a
clean python-native port costs you perfect flash suppression, take the port. Do NOT stand up a
heavyweight flash-suppression gate that fights your de-bash, and do NOT treat popup-safety as a
hard preservation requirement.

**Keep exactly one thing — it is a correctness bug, not cosmetics.** Never route a spawn that
reads a **live stdin pipe** (e.g. a PreToolUse hook receiving tool-call JSON) through `pythonw`.
A console-less parent can hand it a null stdin handle; a bare `except` around the stdin read
then swallows the error and exits 0 — **silently disabling the gate**. `pythonw` is safe only
where the caller controls stdin (heredoc / `/dev/null` / args-only). This is the
`--stdin-mode=safe|pipe` distinction in `spawn-hidden.sh` (now claude-klabauter
`coordinator/lib/spawn-hidden.sh`).

Reference, not mandate: true suppression requires the `CREATE_NO_WINDOW` flag (`0x08000000`) at
the *parent* `CreateProcess` / `subprocess(creationflags=…)` call — a shell launcher cannot set
it, and PowerShell's `-WindowStyle Hidden` is create-then-hide, not suppression. Use it where
it's free on python-side spawns you already control; do not contort a port to achieve it.

## Packageability framing

This is a **conformance expectation**, stated here as doctrine now (a validated manifest field
is deferred to a future plan — see `agent-install-contract.md` § No subagent-hostile bash
wrappers): a packageable consumer repo *declares no subagent-hostile bash wrappers*. Adopt it in
your own CLAUDE.md and treat a new `.sh` wrapper as a review finding, not a style nit — the same
posture `code-reviewer` already applies to GNU-isms under the shell portability lens.

## Reference leg

**project-rag** volunteered as the first consumer-repo reference leg (ratified) — it
retired its own test-running bash wrapper this session and is proving the consumer-side migration
pattern end-to-end, feeding back what the directive needs to actually say. Tracked as a cross-repo
commitment under `state/cross-repo-commitments/`.

## Concrete migration cases — extirpation sweep, 2026-07-24

<!-- spec-backlink: run 2026-08-06-14h38, nuggets c7-011, c7-012 -->
<!-- source: 2026-07-24-extirpate-orphaned-claude-central-publish-shell-e664de.md -->

Worked examples from a single sweep, useful as a bucketing template for future de-bash passes:

- **`.sh` is a Windows bash-tax vector regardless of shebang** — the extension itself is what
  triggers the tax, not just shell content. `source` is the one exception: it is not a spawn, so
  a `source`d `.sh` does not pay the same fork/exec cost a spawned one does.
- **Ratified FLOOR survivors:** `claude-machine-local.sh` and `claude-doe-shim.sh` are kept as
  zero-fork, sourced-into-parent irreducibles — they are never spawned, only sourced, so the
  Windows tax does not apply to them.
- **Killed:** `platform-localize.sh` (orphan, nothing referenced it) and `mint-deliverable-id.sh`
  (a genuine Windows footgun as a spawned `.sh`) — the latter renamed extensionless (POSIX side)
  plus a paired `.cmd` (Windows side), per the SHIM/generator pattern in item 5 above, rather than
  ported wholesale.
- **Not orphaned — a real gap closed:** the pre-CI leak guard's `.sh`-only AC2b
  (extensionless-shebang sniff) had been deferred from the declarative port, not dropped
  deliberately. It was ported to a new `extensionless-shebang-absent` guard-kind in the claude-klabauter
  engine for full parity (no more defer) before the dual bash/declarative path was deleted —
  a reminder to check "deferred" vs "orphaned" before deleting a dual-path bash surface, since a
  narrower-than-intended port can hide as an apparent orphan.

## Aftermath — stale `bin/` targets from de-bash migrations, 2026-07-26

<!-- spec-backlink: run 2026-08-06-14h38, nugget c7-053 -->
<!-- source: 2026-07-26-stale-bin-plan-repair-sweep-54dacd.md -->

De-bash migrations that delete or relocate `coordinator/bin`/`coordinator/lib` targets leave
plans citing the old paths — a predictable downstream cost of this directive, not a one-off. A
sweep against pre-existing plan citations found the true count of plans with dead
`coordinator/bin`/`lib` targets (20) running well above the initial audit estimate (13); 16 were
repaired across four batches (one mid-sweep crash left a narrowing half-applied, caught and
re-blocked before landing), and one was left deliberately dead
(`ceremony-invoke-concurrency-resilience` — the plan's target mechanism itself was deleted
substrate, so repair would misrepresent it as live). When de-bashing a surface with existing plan
references, budget for a citation sweep as part of the migration, not an afterthought — audit
estimates for this class of sweep have undercounted before.

## See also

- `cross-platform-shell-portability.md` — the coordinator's OWN runtime-syntax portability (the internal half).
- `cross-platform-invocation-parity.md` — python-shebang + `.cmd`, never bareword-through-a-shell (DR-076).
- `agent-install-contract.md` § No subagent-hostile bash wrappers — the packageability clause.
- `windows-cmd-shims.md` — launcher/interpreter-resolution mechanics and the Shape β non-goal (shared runtime resolver library).
