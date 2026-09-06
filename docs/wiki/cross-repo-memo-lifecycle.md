# Cross-Repo Memo Lifecycle — Single-Surface, Receiver-Only

<!-- Extracted from cross-repo-communication.md § Cross-repo memo lifecycle (docs/plans/2026-08-30-doctrine-governance-tier-2.md C3). -->

> One surface, no dual-write, no symmetric closure (plan `docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md`).

### The single pattern

**Sender writes once, receiver closes in-place.**

1. **Sender** runs `cross-repo-memo draft <topic> --to <receiver-em-id> --title "<one-line>"`, writes the body into the printed outbox path, then runs `cross-repo-memo send <topic>`. CLI writes ONE file at `<receiver-repo>/cross-repo/inbox/YYYY-MM-DD-<from>-<topic>.md` with `status: open`, then commits that single file into the receiver's repo (see § Delivery commit — a sanctioned small exception below). Sender keeps no copy. CLI prints the receiver path — sender hands the PM that path for relay.

2. **Receiver** sees the memo — already committed, not just dirty — at their next session (`git log` on their active branch, or `git --no-optional-locks status` if the delivery commit degraded to an uncommitted write; see below). They read it, act, flip `status: open → actioned` in-place (optionally adding `decision:` and a note), then commit that flip into their repo. That second commit is the terminal state. Manual reads of `git status` on a shared tree use `git --no-optional-locks status` — the flag must sit between `git` and the subcommand or the invocation hard-fails; `git diff --cached` and `git ls-files -m` need no such flag.

### Delivery commit — a sanctioned small exception

> A memo that only sat dirty on disk was durable in name only — *visible* only once a receiver-EM happened to notice it in `git status`, and never surfaced to an EM that doesn't land a session on that device before the file gets swept up in something else. The CLI closes that gap by committing the delivered memo itself.

After the memo file is written, `cross-repo-memo` stages and commits **only that one file** in the receiver repo — an explicit `git add -- <memo-path>` then `git commit -- <memo-path>`, never `git add -A`/`git add .` (a dirty receiver tree from a concurrent EM session must never be swept into the delivery commit — same discipline as `scoped-safety-commits.md`, applied here to a repo the CLI doesn't own). This is the agree-case form (the CLI just wrote the file, so index and worktree match); it does not push; the receiver's own auto-push hook on `work/*` branches carries the commit onward.

This is a **deliberate, sanctioned exception** to "don't touch another repo's working tree" — the CLI prints a one-line explanation on every successful delivery commit, naming the receiver repo and branch, so the sending EM sees it happening rather than discovering it later as a mystery commit. The exception is narrow by construction: one file, one commit, no push, no other write to the receiver tree.

**Branch selection.** If the receiver repo is already on a normal branch (the common case), the memo commits there — no branch switch. If the receiver has **no active branch** (detached `HEAD`, or an unborn/no-commits-yet repo), the CLI skips the commit and leaves the memo written-but-uncommitted: creating a branch in a repo you do not own is a mutation the delivery exception does not cover, and the narrow one-file-one-commit shape is what makes that exception defensible. A pre-existing `main`/`master` branch is committed to as-is (branch discipline there is the receiver's to resolve, not the CLI's) with a WARNING on stderr noting it.

### `Delivered (uncommitted)` — repair it, never escalate it

The delivery commit is best-effort and never-raise: the memo is already durably written when it runs, so a commit failure must not turn a successful delivery into a failed send.

The never-raise contract holds; the commit's failure mode is legible, not silent. Three properties of the mechanism (claude-klabauter `coordinator_core`):

- **The git reason travels.** `_commit_delivered_memo` returns a frozen `CommitOutcome(committed, branch, reason)`, and `_memo_send` publishes it on the acted entry as `delivery_commit: {committed: bool, branch: str|None, reason: str|None, retried: bool}`. Top-level envelope keys are unchanged. The reason rides the *envelope*, deliberately not the helper's stderr — a headless op does not print into a foreign process's stderr.
- **One retry on `index.lock`.** Exactly one, keyed on a case-insensitive match in the reason string, fixed 0.2s delay, no loop, no config knob.
- **Exit `2` on an orphaned delivery** (untracked on read-back) — "degraded", matching claude-klabauter's `commit_pipeline.py` precedent; `1` stays setup-error, a committed delivery still exits `0`. **Read `2` from `cross-repo-memo` as delivered-but-uncommitted, never as a failed send.** No coordinator surface here shells out to the CLI, so no `set -e` caller breaks; the exposure is an EM-typed invocation rendering as a failed Bash call.

The commit can still fail. It takes the receiver's index lock, and a sibling tree under concurrent-EM load is exactly where that lock is contended. The warning naming the git error goes to a module logger with no handler on the CLI path, so it is discarded there; the sender sees the CLI's own read-back, plus the reason on the envelope:

```
Delivered (uncommitted): <path> is on disk but is not tracked in <receiver> …
```

**That line is a defect to repair, not a gate to escalate.** An untracked memo is one `git clean` from gone and neither end knows it existed. Do not hand the PM the path as an assent ask — landing a delivered memo needs no assent, because the receiver-side commit is part of sending, not a cross-repo commit in the § sense. Re-run it:

**Dispatching a memo is EM-autonomous, on the same footing as a same-repo subagent dispatch — no PM assent before `send`.** The discriminator: does the action mutate the peer's working tree or their tests (**gated** — DR-127's per-session commit assent applies), or does it add an addressed, revertible item to a queue the receiver chooses when to action (**autonomous**)? A memo is additive, addressed to a named receiver, revertible (`cs_release_memo_revert` exists), and actioned at the receiver's own discretion — it is not a mutation of the peer's tree or tests, and DR-127's cross-repo-commit gate is untouched by this. This retires an authorization-sense gate only: **hand the PM the receiver path *after* sending, for notification** (§ below, `:567`/`:759`) still stands — that is a different sense of "PM-relay" and is not what retires here. The pre-send assent is a deliberately retired young-system volume throttle, not a correctness or safety invariant — do not restore it as an oversight.

```
git -C <receiver> -c core.hooksPath="$(mktemp -d)" \
    commit -m "cross-repo: deliver <title> memo from <sender>" -- <memo-relpath>
```

`-c` must precede `commit`; after it, `-c` is `--reedit-message` and fatals against `-m`. The empty hooks dir is what the CLI itself uses — it neutralizes `pre-commit`, `prepare-commit-msg`, `commit-msg` *and* the receiver's auto-push `post-commit`, which `--no-verify` does not do.

A failure of this shape leaves no trace on either side, so past ones are still sitting in receivers' inboxes: `git --no-optional-locks status --short cross-repo/inbox/` in a sibling tree, and any `??` entry is a memo nobody has read.

**Graceful degradation — the commit is best-effort, never a send-blocker.** If branch creation itself fails, or any git subprocess in the commit sequence fails, the CLI emits a WARNING to stderr and leaves the memo written-but-uncommitted rather than failing the send — the memo is already durably on disk by the time the commit is attempted, and a commit-layer failure must not turn a successful delivery into a failed *send*. It surfaces as a **degraded** send: exit `2` plus the git reason on `delivery_commit.reason`. The send envelope is still successful and still never raises; the degradation is legible, not silent.

   **Replace the existing `status:` line — never append.** Edit the existing `status: open` line to `status: actioned`; do NOT write a second `status:` key at the bottom of the frontmatter. A duplicate YAML key leaves `grep -m1`-based tooling reading the first (stale) value, silently keeping the memo surfaced as `open` at the next `/workday-start`. Confirm exactly one occurrence after editing: `grep -c '^status:' <file>` must return `1`. See also `skills/pickup/SKILL.md` § M4 for the same rule at pickup time. *(Source: dup-key instance.)*

3. **No move, no second side — and no `sent/`.** The memo is created in `cross-repo/inbox/` and lives there as the primary record. **Return memos carrying portable findings are legitimate; ack-of-ack is not.** The test is "does new information travel?" — a return memo summarizing portable template/methodology findings discovered during receipt is legitimate; a pure acknowledgment of receiving an acknowledgment is not. `cross-repo/archive/` is the canonical closed-memo destination (flat — no `<YYYY-MM>/` subfolders, unlike handoffs); `archive/cross-repo/` (the old top-level path) is removed. **There is deliberately no `sent/` subfolder** — an EM looking to file an outbound copy finds no home for it, and the absence is the signal: the sender keeps no copy; the memo lives in the *recipient's* inbox.

   <!-- Spec backlink: cross-repo/inbox/2026-07-23-claude-klabauter-em-wsc-tail-doe-ask-list.md (Block 8) — boot_sweep is not invoked from project-orientation.py; Step 2.65 wiring removed -->
   **Archival is NOT automatic — the receiver hand-archives, and that is currently the only route.** Once a memo reaches terminal `status: actioned`, the next session boot sweeps it from `cross-repo/inbox/` → `cross-repo/archive/` via `session.boot_sweep`, fronted by claude-klabauter's native `bin/sweep-boot.py` trampoline and invoked by its own **async** SessionStart hook (`coordinator/hooks/hooks.json`, matcher `startup|compact`) — **not** in-process from `hooks/scripts/project-orientation.py`; that hook's own docstring disclaims authoring or calling any claude-klabauter op on its zero-subprocess boot path (spec-backlink: `coordinator/hooks/scripts/project-orientation.py:9-16`). `session.boot_sweep` bundles the native `fleet.archive_actioned_memos` op alongside the other boot-time sweep classes — the memo analogue of the orphan consumed-handoff sweep. **The receiver DOES hand-`git mv` it** to `cross-repo/archive/` — flat, no `<YYYY-MM>/` subfolder — in the same commit as the `actioned` flip, matching the flat destination this same section states above and the 1,885 flat memos already there. Leaving it in the inbox strands it: `session.boot_sweep`'s archival composite was killed, `sweep-boot.py` now carries `never dispatches an op` as a negative spec, and `fleet.archive_actioned_memos` was killed outright with no replacement invoker — the op module survives in the engine tree with nothing that calls it, and no CLI fronts it. Measured 2026-08-30 in DoE: 6 `actioned` memos sitting in `cross-repo/inbox/`, which is the exact failure this page's own history says the sweep was built to end. `ceremony.wsc_tail` (claude-klabauter `coordinator_core/ops/ceremony/wsc_tail.py`) fired the equivalent sweep **detached, immediately after** the Step 3 ceremony commit landed (span `postcommit.archive_sweeps_detached`) — removed with the tail (K-046), so archival now waits for the next session boot. A bare `/pickup` that never reaches workstream-complete leaves the memo in the inbox — no boot sweep collects it. The sweep skips `open`/`in_progress` (live-claimed) memos, `README.md`, and live-claimed actioned memos, and is idempotent. *(Before this, actioned memos leaked forever — dozens piled up before the manual sweep that prompted this fix. Spec: `state/handoffs/2026-06-22_232810_unified-terminal-artifact-archival-sweep.md`.)*

   **Why nothing archives during a long session.** The `session.boot_sweep` SessionStart matcher is `startup|compact` and deliberately excludes `clear` — `coordinator/hooks/hooks.json`'s own `_comment` on that hook entry states the rationale: matcher `startup|compact` "mirrors the original session-init boot_sweep coverage (not clear — a lightweight /clear is not a fresh session boundary)." A long-running session therefore never re-fires the boot sweep on its own. The gap is closed by the detached post-commit fire from `ceremony.wsc_tail` at `/workstream-complete` (above), not by the boot hook — if you're staring at an un-archived inbox mid-session, that detached fire (or the next session boot) is the mechanism to check, not a missing `clear` trigger.

### Claim-at-pickup parity with handoffs — `open → in_progress → actioned`

> Spec: `docs/plans/2026-06-21-memo-pickup-claim-lock-and-routed-plan-reconcile.md`. Closes the asymmetry where handoff-pickup had an atomic claim-lock but memo-pickup did not (the whoami collision: two sessions actioned the same memo + drove its plan in parallel).

The lifecycle has a **claim state** between `open` and `actioned`, mirroring handoff `deployment_state: in_flight`:

- **`open`** — sender wrote it; awaiting a receiver.
- **`in_progress`** — a receiver session claimed it at pickup-start (Memo Branch step **Claim the memo**, formerly M2.5): atomic `cs_claim_memo <basename> <baton-repo>` mkdir lock + a `picked_up_by` stamp (required when `in_progress`) + a `git fetch` idempotency re-read. Concurrent pickup of an `in_progress` memo is **fail-loud**, same as handoffs. The claim gate runs AFTER the whole-memo read (Read before you act, formerly M1) and premise verification (Verify premises, formerly M2) — never before, or you'd lock work you haven't read or a peer already did.
- **`actioned`** — terminal disposition written (Accept/Decline/Surface-decided/consult/fyi). Work-realizing dispositions (`accepted`/`partial`) additionally stamp `realized_by:` — see § Claim-at-pickup parity with handoffs below. The terminal flip is written by `cs_action_memo` (claude-klabauter `coordinator_core/archive_stamp.py`), which enforces claim ownership via the liveness-gated check: it stands down (fail-loud) if a different live session holds the memo claim; override `COORDINATOR_OVERRIDE_MEMO_ACTION_CLAIM=1` for a legitimate cross-session handoff.

**`plan` class — a third sibling claim.** As of 2026-06-26 (`docs/plans/2026-06-26-cs-claim-plan-execution-lock.md`), the same atomic-mkdir machinery extends to plan execution via `cs_claim_plan <slug>` (no repo-root arg — cwd-default). Acquired at `execute-plan` Phase 1.5 (before the gate graph) and at `workstream-complete` (governing-plan only, no-op on plan-less sessions). Re-entrant for the same session (covering the execute-plan → workstream-complete two-seam span); fail-loud for a different live peer. Released at the two clean terminals (`workstream-complete` terminal commit + `/handoff` deliberate PAUSE) or idle-reaped (30-min `last_activity` recency, same bound as handoff/memo). The Phase-1.5 premise reconcile is retained as a complementary layer (it catches a peer driving a disjoint chunk remainder); the plan lock is the fail-loud prevention layer above it. The no-arg session-init reaper sweeps `plan-claims` alongside `handoff-claims` and `memo-claims`.

**Claim → action → flip-or-release.** A terminal disposition releases the claim via `cs_release_artifact` (holder-identity-checked — no-op unless this session is the holder). **"Releases the claim" = the filesystem mkdir lock only, NOT the frontmatter attribution.** The `picked_up_by:` field is *preserved* on the terminal `actioned` flip — it is not cleared. The two were historically conflated; `cs_release_artifact` rm's the `.git/coordinator-sessions/*-claims/` lock dir, while `picked_up_by:` stays in the memo frontmatter as attribution-of-record (see § `realized_by` below). A **non-terminal** exit — Surface-to-PM where the session ends before the PM decides — reverts `in_progress → open` and clears the stamps FIRST, then releases the lock (ordering matters: a crash must never leave claim-freed-but-`in_progress`, which would re-admit two sessions). Dead-PID reaping (`cs_reap_stale_claims`, sweeps both `handoff-claims` and `memo-claims`) is the safety net.

**`realized_by` — the claim survives into `actioned` as a claim-of-record.** Stamping `picked_up_by` only on `in_progress` left a gap: once a memo went `actioned` and was archived, nothing recorded *who* handled it or *where* the work landed, so a second session could re-realize the same accepted memo (the example-game-repo B3 collision). On the terminal flip of a **work-realizing** disposition (`decision: accepted` or `decision: partial`), the receiver stamps `realized_by: <plan-path | commit-sha | "inline">` AND preserves `picked_up_by:`. Together they make the archived memo a claim-of-record. The value shape is schema-validated (`bin/lib/schema.js` cross-repo-memo rule): the sentinel `"inline"`, a path (contains `/`), or a hex SHA `/^[0-9a-f]{7,40}$/` — a bare prose word fails loud (detect-then-fail-loud). Decline / `consult` / `fyi` realize no work and carry no `realized_by` (schema-exempt). Two halves of the original visibility gap: (a) the archived **claim-of-record** is CLOSED by `realized_by`; (b) the visible `in_progress` window during a same-session terminal Accept — or a session PM-directed straight to realization that never runs `/pickup`'s Claim the memo step (formerly M2.5) — is NOT closed and architecturally cannot be (you cannot stamp an `in_progress` window on a session that never enters the pickup claim flow). Spec: `docs/plans/2026-06-23-memo-pickup-realization-claim-visibility.md`. The upstream collision-prevention is the `source_memo:` cross-check at `coordinator:plan` Branch B.0.

**Foreign-baton coverage boundary.** A memo claim written under a foreign `BATON_REPO` (a `~/.claude` memo picked up from a sibling-repo cwd) is NOT reached by the session-init reaper, which fires on the cwd repo — explicit `cs_release_artifact` is the primary cleanup for cross-repo memo pickup; inline dead-PID takeover on next contention is the fallback. Parity with the handoff foreign-baton boundary.

**Surfacing.** `/workday-start` surfaces `in_progress` memos with a `[CLAIMED by <picked_up_by>]` tag — visible-but-attributed, not hidden (an unsurfaced in-flight memo makes the inbox "look free mid-action"). A stale claim is reverted to `open` by the reaper, at which point normal `open` surfacing resumes.

**Routed-plan reconcile (Gap #2).** When a picked-up memo forward-points to a plan (`docs/plans/*.md` in `decision_note`/frontmatter), pickup echoes that plan's **live execution state** before dispatching — on both the `open` path (Claim the memo, formerly M2.5) and the already-`actioned` re-pickup path (Short-circuit already-actioned memos, formerly M0). Liveness uses a positive predicate (active handoff / live claim / an in-progress wave-map / a `<chunk-id>:` commit within the last 24h with no corresponding closure), not bare commit-existence — the latter cry-wolfs forever on long-shipped plans on the shared branch. See `skills/pickup/SKILL.md` § Routed-plan reconcile-and-surface.

**Pre-dispatch reconcile before executor dispatch on an accepted `ask` (cross-machine double-spend prevention).** The `cs_claim_memo` `mkdir` lock is machine-local — invisible to a second machine on the shared `work/*` branch. The only honest cross-machine claim signal is the committed `picked_up_by:`/`status:` frontmatter, which the Claim the memo step's (formerly M2.5) fetch+re-read only catches if this machine fetched *after* a peer's claim commit was pushed. On one occasion, two machines picked up the same `ask` near-simultaneously and each ran a full executor → code-reviewer → review-integrator pipeline on the identical change (correct outcome via the `open → actioned` terminal flip, but fully duplicated spend). Per `docs/plans/2026-07-09-continuity-artifact-staleness-parity.md` Fix #1, the M3 **Accept** pre-dispatch reconcile is mandated immediately before performing the work / dispatching an executor: (1) `git fetch` + re-read the memo's own `status:`/`picked_up_by:`; (2) run the same positive-liveness predicate as § Routed-plan reconcile-and-surface against the memo's topic nouns (layered on top of, not replacing, the frontmatter re-read); (3) any peer signal → surface and **stand down** until the operator confirms the peer is gone. This is a stand-down/reconcile, not a hard block — the residual race is bounded to duplicate spend, never incorrect state. This is delivered as an engine-computed `judgment_points` entry (`revalidate_at_dispatch: true`) in `pickup_assemble`'s fired decision object, not static `skills/pickup/SKILL.md` prose; see `docs/wiki/computed-skills.md` § Round-trip classification and `docs/wiki/coordinator-tripwires/memo-predispatch-standdown.md`.

**`/workstream-complete`'s `d-flip-memo-status` directive — lifecycle sweep.** At workstream end, before the final commit, `/workstream-complete` runs a cross-repo memo lifecycle sweep: it scans this repo's `cross-repo/inbox/*.md` for memos whose underlying work was completed during the session (i.e., the issue they described has been resolved), and flips their `status: open → actioned` inline with a `decision:` note. This prevents the inbox from drifting from reality — memos where the work is done should not stay `open` and surface again at the next `/workday-start` Step 1.45.

**Distill integration.** `/distill` gains a `## Cross-repo archive distillation` phase: it mines `cross-repo/archive/*.md` with `status: actioned` for evergreen knowledge (folding into wiki), then clears entries older than the configured retention threshold. `/update-docs` runs a 90-day janitorial sweep on `cross-repo/archive/` — cadence is anchored at ≥3× expected distill cadence to ensure the sweep never deletes un-mined content.

### Schema

Memo files use `plugins/coordinator/schemas/cross-repo-memo.schema.json`. Key fields:

- `from:` / `to:` — author EM id and receiver EM id (e.g. `claude-central-em`, `project-rag-em`). **`from:` is derived automatically** from the repo the CLI runs in — the inverse of receiver resolution (cwd git root → `repos.<name>` → `<name>-em`; the DoE-claude repo (`repos.doe_claude`) is `claude-central-em`). It is never hardcoded and never an EM self-identify step.
- `status:` — `open | actioned`
- `decision:` — optional note on the receiver's action, added when flipping to `actioned`
- `kind:` — optional sender-declared shape (`ask | consult | fyi | proposal`); absent is interpreted as `ask`. See § `kind` enum — sender-declared memo shape below.
- `to_repo:` — optional resolved receiver registry key. See § `to_repo` — resolvable-registry-key receiver field below.

### `to_repo` — resolvable-registry-key receiver field

<!-- src: cross-repo/inbox/2026-07-24-claude-klabauter-em-central-id-canonical-order.md "Not asked for, deliberately" -->

> Jointly-held field (PM-ratified) — see the `distill_fate` section above for the established shape this section follows.

`to:` carries a human-readable nickname — this seat alone is addressable under eight of them (`claude-central-em`, `central-em`, `central`, `doe-claude-em`, plus the `redirectAliases` set) — so a reader cannot verify by inspection that a memo landed in the right repo without already knowing the alias mapping. `to_repo:` carries a **resolvable registry key**, in the same `repos.<key>` form used fleet-wide for sibling-repo resolution (`repos.doe_claude`, `repos.claude_klabauter`, `repos.project_rag`): the addressee becomes machine-checkable, not a name the reader must already have memorized.

- **Optional, on both `cross-repo-memo.schema.json` and `archived-memo.schema.json`.** Never added to `required` — the entire pre-2026-07-24 corpus has none, and claude-klabauter does not emit it yet. Making it required would retroactively invalidate every memo on disk.
- **Disambiguates, does not replace.** `to:` remains the human-readable addressee and every existing alias stays valid. `to_repo:`, when present, is authoritative for routing: `hooks/scripts/validate-frontmatter-schema.py`'s routing-mismatch check (Chunk G) compares it against the landing repo's own registry key and decides the match on that alone — the `to:`/alias comparison is not consulted when `to_repo:` is present. Absent `to_repo:` (the common case) falls through to the pre-existing `to:`/alias comparison, unchanged.
- **Fail-open, same posture as the rest of the routing guard.** An unresolvable or absent `to_repo:` never blocks — it only ever narrows an offer to a firmer footing or leaves the existing comparison untouched.

### `distill_fate` — shared reconciliation-log stamp field with claude-klabauter

<!-- src: memo02-013 -->

> Ratified shared vocabulary (`2026-07-12-claude-klabauter-em-distill-reconciliation-log-standardization.md`): claude-klabauter runs with DoE's field as canonical on `cross-repo-memo.schema.json` — both EMs run with it.

A second, orthogonal stamp field to `status`/`decision`/`realized_by` above: `distill_fate: ephemeral | commitment | ratification`, with `in_repo_capture:` **required** whenever `distill_fate: ratification`. Where `status`/`decision`/`realized_by` record the memo's *lifecycle disposition* (did the receiver act?), `distill_fate` records the memo's *evergreen-knowledge weight* for `/distill`-class mining of `cross-repo/archive/`:

- **`ephemeral`** — routine coordination, no lasting pattern; distill sweeps skip it.
- **`commitment`** — opens a `realized_by`-tracked loop distinct from a routine ack; the memo commits one side to future work, not just a nod.
- **`ratification`** — the memo IS the record of a cross-repo decision. **Requires `in_repo_capture:`** naming the doc/wiki/DR the decision was actually written into — this closes the "memory-pointer hole" where a ratified decision lived only in the memo's prose and was never captured anywhere durable, so it evaporated the moment the memo aged out of `cross-repo/archive/`.

**Fallback for legacy memos:** un-stamped memos (pre-field) fall back to the existing #1a heuristic (infer weight from `kind` + `decision`) — this field does not retroactively invalidate older archive entries.

### CLI

Invoked per the precedence ladder in `coordinator/snippets/resolve-coordinator-bin.md` — rung 0 /
Shape W on a PowerShell host, Shape A (POSIX hosts) resolving `cross-repo-memo draft <topic> --to
<receiver-em-id> --title "<one-line>"`, then `cross-repo-memo send <topic>`. The flag-only
`--topic/--title/--body-file` send form is gone; only the discovery flags below remain.

**Discovering valid receivers — run `cross-repo-memo --list-receivers`.** That is the one canonical enumerator of every valid `--to` target on this machine. It lists `claude-central-em` first, then every registered sibling, each with its resolved path. **Do NOT discover receivers via `machine-local keys | grep '^repos\.'`:** that lists the `repos.*` siblings by their raw registry key, but `claude-central-em` resolves to the DoE-claude repo (`repos.doe_claude`) — the registry key (`doe_claude`) differs from the canonical EM id (`claude-central-em`), so raw key enumeration bypasses alias resolution. An EM reasoning from registry keys alone may invent the wrong `--to` value or hand-author a memo to the wrong path, the exact anti-pattern this CLI exists to prevent. `claude-central-em` (aliases `central-em`, `central`) is **always** a valid target, registry or no registry.

**Receiver resolution is by convention, not a hand-maintained table.** A `<receiver>-em` identity maps to the machine-local registry key `repos.<receiver, dashes→underscores>` — e.g. `project-rag-ue-addon-em → repos.project_rag_ue_addon`, `example-sim-repo-em → repos.example-sim-repo`. Any repo registered under `repos.<name>` (`machine-local set repos.<name> <path>`) is automatically a valid `<name>-em` receiver with no code change — so anyone installing the coordinator gets cross-repo delivery to their own registered repos for free. The only exceptions are identities whose doctrine name diverges from the repo's registry shortname (currently just `example-game-repo-em → repos.example_game_workbench_repo`), held in a tiny alias map in `cross-repo-memo` that does not grow with repo count.

On machines where the receiver repo is not registered, the CLI **hard-errors** (exit 1, no file written) and lists the known receivers — a dirty memo cannot be written to a repo that isn't on this machine. There is no central-only fallback in the single-surface model; route via the PM's next session in that repo instead. (`central-only` survives only as a grandfathered `delivery_mode` value in the schema for pre-existing memos; the CLI does not issue it.)

On success the CLI prints the receiver path and the relay reminder:

```
Receiver-side: <abs-path>
Hand the PM this path for relay: <abs-path>
Reminder: Hand the PM the receiver path — PM-relay is still the primary channel.
```

That reminder string is emitted by the claude-klabauter-owned CLI (`claude-klabauter` `coordinator/bin/`, execed via the DoE forwarder), not authored here. PM-relay is the correct default; a same-machine, registry-visible peer session reachable per § "Then, the sync-vs-async gate" is a second legitimate primitive when both gates pass. The printed string names only the default — read it alongside that gate, not as the exhaustive route. Updating the printed string is a claude-klabauter-side change.

(`--self-receipt` prints only the `Receiver-side:` line — no relay reminder, since the dispatcher is the receiver.)

### Send-verb discoverability from consumer trees — breadcrumb scaffold + relocation-invariant

The send verb is DoE-owned and lives **on PATH**, so it is deliberately vendored into *no* consumer repo. A consumer-repo EM going to send their first memo naturally searches their own tree (`ls bin/`, `find . -name 'cross-repo-memo*'`, grep) and finds nothing — the verb is fine (on PATH, correct owner), but it is **invisible to a tree-scoped search from where the consumer EM looks**. `which cross-repo-memo` would find it; a naive-but-reasonable search does not. This is a class problem: every consumer repo hits the same wall on first send (originating report: claude-klabauter memo `cross-repo-memo-send-discoverability`).

**Breadcrumb scaffold (the fix).** `coordinator:repo-setup` scaffolds a pointer doc at `bin/cross-repo-memo.md` into every onboarded repo (single and `--batch`) — exactly where the naive `ls bin/` / `find` search lands. It is a declared file-entry in `canonical-structure.yaml` (`template: templates/cross-repo-memo-breadcrumb.md`), materialized by the claude-klabauter `coordinator_core.install.scaffold_structure` CLI (idempotent, never clobbers). The breadcrumb redirects to the on-PATH verb with the real `draft → compose → send` lifecycle; it is NOT a shim executable — the ownership boundary keeps the verb in DoE.

**Relocation-invariant (load-bearing acceptance criterion).** Consumer-tree discoverability is a **required property of the send verb, independent of where the verb lives.** Any future relocation of the send verb — notably the strang-03 / claude-klabauter DR-210 migration into claude-klabauter's `coordinator_core/ops` — MUST preserve it: "discoverable from the consumer tree" is an explicit acceptance criterion of that migration plan, so the generalized solution does not reintroduce the blind spot at a new location. A relocation that moves the verb without carrying the breadcrumb (or an equivalent discoverability affordance) regresses this invariant and is incomplete. (The strang-03 plan is claude-klabauter-owned; claude-klabauter's EM carries this AC into that plan — captured here as DoE doctrine because DoE owns the CLI and the onboarding scaffold.)

### Receiver-ID discipline — `--list-receivers` is authoritative, never invent from the repo slug

**`--to` values come from `cross-repo-memo --list-receivers`, not from the sibling repo's name or shortname.** Receiver IDs are CLI-owned identifiers gated by a frozenset and an alias map; not every plausible `<repo>-em` string resolves, and the DoE-claude repo's inbox is `claude-central-em`, NOT `coordinator-claude-em` (that's a publish target — rejected). Inventing a `--to` value from the receiving repo's slug ("we're sending to coordinator-claude, so `--to coordinator-claude-em`") hits the rejection at executor-time and stalls delivery.

**Run the CLI at plan-write time.** When authoring a plan that includes a cross-repo memo chunk, run `cross-repo-memo --list-receivers` during plan-authoring and cite a value from its output verbatim in the brief. Neither the prior-art check nor the named-reviewer pass executes the CLI to verify the receiver enum — the only floor against an invented identifier is the plan-author dropping into a shell. (case: example-game-repo — Wave 1 executors hit frozenset rejection on `coordinator-claude-em` / `coordinator-claude-doe`; canonical was `claude-central-em`.)

### `kind` enum — sender-declared memo shape

<!-- Spec backlink: docs/plans/2026-05-30-pickup-cross-repo-memo-fork.md § Pinned interface — the `kind` enum -->

The optional `kind:` frontmatter field lets the sender declare what shape of response the memo needs. Enum membership: `ask | consult | fyi | proposal`.

| Value | Meaning | Receiver disposition |
| --- | --- | --- |
| `ask` | Sender requests the receiver *do* something (action request). Surfaces with urgency. | Adjudicate-and-own: weigh against this repo's consumers; action (→ `decision: accepted` + `decision_note`) or decline (→ `decision: declined` + `decision_note`); surface to PM only on a genuine product/tradeoff/architectural fork. |
| `consult` | Sender requests the receiver's *input or opinion* — a question, not a directive. Surfaces with urgency. | Reply-in-place: capture the response in `actioned_note` directly on the memo, then mark `status: actioned`. The sender reads the response on the same machine. No return-memo. |
| `fyi` | Informational from the **sender's** perspective; no action or response *requested*. Quiet log line at surfacing. | **Assess impact on receiver BEFORE acknowledging** — `fyi` is the sender's framing of their intent, not a verdict on your repo's exposure. Run the impact-on-receiver gate (active plans / in-flight workstreams / doctrine / hypotheses corrected) per `skills/pickup/SKILL.md` § `fyi` Step 1. Nil-impact (verified, not assumed) → `status: actioned` + `actioned_note: "noted — informational; impact-assessed nil against <what you checked>"`, no `decision` field. Material impact → re-plan, scope-adjust, surgical work, or Surface-to-PM per shape; the memo is not ack-only. |
| `proposal` | Sender presents a concrete change or recommendation for the receiver's adoption. Surfaces with urgency. | Evaluate-and-decide: assess the proposed change against this repo's current direction; adopt (→ `decision: accepted` + `decision_note` on what you'll apply), decline (→ `decision: declined` + rationale), or negotiate via a return memo. The receiver owns the adoption decision. |

**`ack` is NOT a `kind` — it is receipt-state, not a sender-declared value.** An acknowledgement is the receiver flipping `status: open → actioned` (with `decision:` + note) in-place. `ack` is never a valid `kind:` value and never a return-memo. The same rule as "don't send an ack-of-ack when the inbound was a confirmation" (§ Memo content is hypothesis — verify before acting, item 8) applies here: the `status` flip IS the receipt; authoring a separate ack memo is ceremony with no value.

**Inbound replies carrying a reply-flavored `kind` jam `archive-stamp-cli`'s `action-memo` cross-field validation — normalize on receipt.** The enum is `ask|consult|fyi|proposal` and nothing else; a sibling repo replying with `kind: consult-reply` (or `ask-reply`, `ack`) trips `archive-stamp-cli`'s `action-memo` cross-field validation, so the inbound memo cannot be transitioned `open → actioned` and stays stuck at `status: open` even though it was actioned in substance. Any cross-repo peer using a reply-flavored `kind` hits this. On receipt of such a memo, read the reply-flavored `kind` as its base kind (`consult-reply → consult`; `ack →` receipt-only) and flip the status by hand if the transition tool rejects the value; the sender-side fix is to reply with a valid enum value, since the `status` flip — not a `kind` — carries the reply semantics. *(case: claude-klabauter replied `kind: consult-reply`; the memo jammed at `status: open`.)*

**Absent `kind:` defaults to `ask` at the READER.** The CLI does not stamp a default — absence stays meaningful. Every reader (surfacing helper, `/pickup` branch) applies `ask` when the field is absent. This preserves back-compat: no pre-2026-05-30 memo is silently downgraded to a quiet `fyi` by the absence of a field it never had.

### `discharges` — the closure-signal contract for `external_gate`

<!-- src: cross-repo/inbox/2026-08-21-claude-klabauter-em-gate-closure-signal-contract.md; ruled by state/subagent-share/f6ed9dc2-6fc9-4804-9952-27e684f5f573/coordinatoreng-director-ceecede2.md -->

A `plan-tasks.schema.json` `external_gate` entry can carry a `closure_key` (`{kind, id}`,
`kind` one of `deliverable`\|`memo-thread`) naming the identity whose landing discharges it.
The discharging side emits that landing as an ordinary cross-repo memo into the WAITING
repo's `cross-repo/inbox/` — the existing channel, correct polarity: the repo that OWES the
work is the sender, the repo waiting on it is the receiver, so the record lands in the same
tree as the plan whose gate is parked. No new substrate, no `kind: discharge` memo-kind enum
member: a discharge memo travels as an ordinary memo (`ask`/`consult`/`fyi`/`proposal`), because
a new enum member is a four-site cross-repo lockstep for a surfacing convenience that
correctness must not depend on.

The memo carries a `discharges:` frontmatter block, presence-triggered completeness in the
same pattern as `scoped_to`/`distill_fate` above:

```yaml
discharges:
  closure_key:
    kind: memo-thread
    id: 2026-08-21-claude-klabauter-em-gate-closure-signal-contract.md
  evidence: 9f3c1a2
  landed_at: 2026-08-21
```

`evidence` reuses `realized_by`'s already-validated value shape — sentinel `inline`, a path, or
7-64 hex chars — so the existing validator covers it with no new rule.

**Two reader rules, both non-negotiable:**

- **Scan both `cross-repo/inbox/` and `cross-repo/archive/`.** `session.boot_sweep` moves
  actioned memos to archive automatically, and a discharge memo that has been actioned is
  still the discharge record — an inbox-only scan misses every one already swept.
- **Key on the `discharges` block alone, never on `status:`.** A census of the live
  `external_gate` corpus falsified every status-derived inference tried, five separate ways
  (archive location, terminal `status:`, sweep hygiene, deliverable-rollup presence,
  `status: actioned` polarity) — 30 archived memos still read `open`.

**A match lets a reader *propose* the `cleared: true` flip with a citation to the discharge
memo — it never performs the flip.** `cleared: true` stays the one clearing path on both
readers; the discharge record only supplies the evidence a human or a proposing tool cites.

**Ownership split.** DoE-claude owns `closure_key` on the `plan-tasks` task spine. The owning
repo of `cross-repo-memo.schema.json` owns the `discharges` block, its cross-field rule, the
emitter, and the resolver that consumes it — that schema is a generated projection whose
source of truth lives there, not here.

#### Authoring an `ask` — presume action, don't write it meek

> The send side shapes the receive side: a meek ask invites lazy handling.

When you author an `ask` memo to a sibling repo, **write it presuming action** — name what needs doing and why, in the imperative, as a fellow EM handing real work to a peer who ships. Do NOT hedge it into a suggestion-box submission: "um, maybe a backlog item?", "could be worth queueing eventually?", "low priority, no rush" are the meek shapes to avoid. A tentatively-framed ask *tells* the receiver it's backlog-tier, and the compliant response to a backlog-tier ask is to file it to a queue — the exact laundering the receive-side gate (§ Picking up a memo) forbids. The two failures are one disease: **presumed-action on the send side and action-on-receipt on the receive side are the same rule.** We ship more working code in a day than a human team ships in a month — an ask between our own repos should read as "here's what needs doing," not "here's a thing you might consider someday."

This is not a license to manufacture urgency or skip the verification the receiver owes the ask (§ Memo content is hypothesis). It is a framing discipline: state the work plainly and let the receiving EM adjudicate-and-own it (Accept / Decline / Surface-to-PM). If the ask genuinely *is* low-stakes-someday work, that is a judgment for the receiving EM to make on their own consumers' priorities — not something you pre-decide for them by wording it as deferrable. Name the work; trust the peer to adjudicate.

#### Paste hazard — no body line opens with a bare `>` before shell metacharacters

Review/plan prose crossing an EM boundary (memo bodies, review findings, plan text) must NOT open a body line with a bare `>` immediately followed by shell-special characters (e.g. `> correct?*`, `> foo | bar`, `> *.md`). As rendered markdown this is a harmless blockquote, but a line pasted into a live shell — a manual terminal paste, or an editor "send line to terminal" integration — reads the leading `>` as a redirect, and the glob/metacharacters become a literal target: with bash `failglob` off, `> correct?*` silently creates a junk file named `correct?*` that can balloon to hundreds of gigabytes before anyone notices. Prefer indenting, fencing, or rewording so no authored body line begins with `>` immediately followed by shell metacharacters.

*Motivated by an eng-director review blockquote pasted into a shell in claude-klabauter, which produced a 365 GB runaway file. Human-factors complement to the shell-init `ulimit -f` + `failglob` guards (`docs/plans/2026-07-11-shell-init-runaway-file-guards.md`).*

### `/workday-start` Step 1.45 surfacing (receiver-inbound)

A step inserted between Step 1.4 (cross-reference completed archive) and Step 1.55 (Recent Roadmap Orientation) queries **this repo's** `cross-repo/inbox/*.md`, parses frontmatter, filters to `status: open`, and surfaces:

```
Cross-repo memos awaiting your action:
- 2026-05-23 from claude-central-em: gate-check failures — open (1 day)
```

Staleness flag: `open` >7 days appends ` [STALE]`.

Cap: ≤8 entries; `(N more — see cross-repo/inbox/ for full list)` truncation beyond that.

`actioned` memos drop off the surface. The helper script is `workday-start-cross-repo-memo-surface.py`.

### Partial-ack memo unblocks the sender — send early, even when the main deliverable is in flight

A cross-repo memo's acknowledgement function is independent of the main deliverable's completion. When you have confirmed that you understand and accept an inbound request — even if implementation is still running — send a partial-ack memo immediately. The sender may be blocked waiting for any signal; a "received and in progress" ack is sufficient to unblock them. Do not wait until the work is fully closed to reply.

*Source: rag-ue-addon `state/lessons.md`.*

### Memo-lifecycle adjudication is EM work

When an inbound memo describes a situation, proposes an action, or asks a question — read the memo body and judge the right response yourself. Do not surface the memo contents to the PM as "what should I do?" The PM's job is product authority; memo adjudication (what the memo says, what the right EM response is, whether the action is already done, whether the memo is superseded) is EM work. Escalate to PM only if the memo implicates a product decision — not for "I have a memo, what do I do?" (See also § Memo content is hypothesis — verify before acting.)

*Source: example-game-repo `state/lessons.md`.*

### Picking up a memo — the adjudicate-and-own gate

<!-- Spec backlink: docs/plans/2026-05-30-pickup-cross-repo-memo-fork.md § C5 -->

**"Migrate X to the sibling" is a hypothesis — verify before treating as a move.** HEAD-verify the sibling's adoption commit exists before deleting your local copy. Trace the full import graph before pruning "migrated" files. Routine investigation frequently inverts the framing: the sibling already owns the content, it was never migrated, or the copy is legitimately shared.

**Premise-check vendored-fork references by SYMBOL, not by cited line number.** When a memo cites a line reference in a vendored or forked copy of a library (e.g. `lib/vendor/foo.py:L123`), that line number is the sender's view of THEIR fork — it is NOT a stable reference across independent forks of the same upstream. Before acting on the cited locus, grep HEAD by the FUNCTION or SYMBOL NAME, not the line. A missing symbol (`grep -n 'def the_function' <file>` returns nothing) is categorically different from "moved by N lines" — the former means the implementation doesn't exist in this fork at all, the latter means it exists but the line number drifted. Treating a symbol-absent result as a line-drift false-negative wastes a round-trip and mis-classifies the fix-locus. *(Source: a memo cited L247 in a vendored fork; the symbol had been removed from the receiver's fork entirely, but the session first tried L247 ± a few lines before checking by symbol name.)*



When `/pickup` routes to the memo branch, two existing sections in this wiki constitute the contract it invokes:

- **§ Memo-lifecycle adjudication is EM work** (immediately above) — the EM reads and judges, never routes "what should I do?" to the PM.
- **§ Memo content is hypothesis — verify before acting** — premises (fix-locus, tree-state, architectural framing) are hypothesis until checked against current disk state.

These are not new rules authored for the pickup procedure; they are existing doctrine now made reachable at the moment the EM opens a memo baton. The `/pickup` memo branch is the procedure that wires them into the pickup-time moment; the doctrine lives here.

**The calibrated stance: adjudicate-and-own.**

A memo-ask is a PEER HYPOTHESIS from the sender's EM — a suggestion from a fellow EM at another repo, not a work order. The receiving EM adjudicates and OWNS the disposition for this repo's customers and consumers:

- **Tradeoff-free ask the EM endorses** → action it; mark `status: actioned` + `decision: accepted` + `decision_note: <what was done>`.
- **Disagree, or wrong for this repo's consumers** → decline; mark `status: actioned` + `decision: declined` + `decision_note: <rationale>`.
- **Genuine product/tradeoff/architectural fork** → surface to PM for direction, then act on the answer.

**There is no fourth disposition. Filing the ask into the improvement queue is the laundering anti-pattern, not a way to handle a memo.** Moving an inbound ask from the inbox into `state/improvement-queue.md` (or the central queue, or "a separate plan for later") shuffles paper between two staging grounds, adds zero value, and silently makes a *prioritization* call — deciding the ask is not-now — that is the PM's to make, not the EM's. The inbox row clearing feels like progress; it is not. The honest exits when you can't action this session are **decline-with-architectural-rationale** or **surface-to-PM-for-priority** — never queue. "Annoying to fix right now" is not a rationale; presume action. (This is the inbound-memo instance of the general rule in `coordinator/snippets/em-operating-doctrine.md` § How to Plan and Hand Off, "Improvement Queue" (superseding coordinator/CLAUDE.md): an inbound cross-repo ask is one of the two cases hard-forbidden from the queue.)

This is the **"reviewer findings: apply, don't ratify"** framing applied to memo-asks. It is NOT "always bounce to the PM" — § Memo-lifecycle adjudication is EM work explicitly forbids "what should I do?" escalation. Escalate only when the memo implicates a product decision, not as a default.

#### Route-to-baton — inbound work inside an active baton's scope lands IN that handoff, committed

<!-- Spec backlink: cross-repo/inbox/2026-07-22-claude-klabauter-em-route-to-baton-skill-change.md (PM ruling, machine-b, 2026-07-22: "'shit relates to an active handoff' should mean editing that handoff and committing that edit, as a matter of course.") -->

When inbound work — an inbox memo, a review finding, a triage item — falls inside the scope of an **active** handoff/baton (`state/handoffs/*.md`, `status: open|claimed`), the DEFAULT action is **route-to-baton**: append a routing note into that handoff file and commit the edit immediately, as a matter of course. Not: hold the routing in session context (evaporates at session end); not: leave the source artifact as the only record (the baton's next pickup is blind to it); not: ask the PM per-instance (this ruling IS the standing authorization).

Mechanics:

1. **Append, don't restructure** — add under a dated `## Routed from inbox triage (<YYYY-MM-DD>)` heading at the end of the handoff body (extend the section if it already exists for the day): one bullet per routed item, citing the source artifact path and one line on what the baton now additionally owes.
2. **Leave the handoff frontmatter untouched** — `status`, `deployment_state`, and lineage fields are lifecycle state with their own authorized writers; a routing note is body content only.
3. **Commit the handoff edit via `ceremony.commit_v2`** (claude-klabauter, `coordinator_core/git/commit.py` :: `commit_paths`) with `paths: [<handoff>]`, subject `route-to-baton: <handoff-slug> ← <source-basename>` — it commits the tree it builds from that path alone, whether or not you staged a partial hunk, so there's nothing to classify here (→ `scoped-safety-commits.md § SC-DR-015`). The commit is the durable record; an uncommitted routing note fails the ruling.
4. **Route-then-close, in that order, in the same pass.** The routing commit must exist before the flip — never close against a capture you have not landed. Once it has landed and the baton demonstrably names the memo, resolve the memo where you routed it:

       archive-stamp-cli resolve-memo <memo> \
         --decision accepted \
         --decision-note "routed into <baton path>, which now owns this work" \
         --realized-by "<baton path>" \
         --in-repo-capture "<baton path>"

   `resolve` is `open` → `actioned` in one locked write, so triage needs no separate claim, and `in_repo_capture` is what makes the close auditable and reversible rather than a silent drop. One obligation, one home: the baton owns the work, and `memo.blitz_buckets` stops counting a memo whose work is specified elsewhere.

   Two memos do **not** close on routing: one whose capture could not be landed (stays `open`), and one carrying an unanswered question addressed to this repo's PM — a baton cannot discharge a decision, so a ruling-bearing memo stays `open` even when a baton names it.

   When `/pickup` opens the memo itself, route-to-baton is the same Accept shape by the same mechanics.

This is the opposite of queue-laundering (§ There is no fourth disposition, above): the queue is an ownerless staging ground; an active baton is a live, owned execution vehicle with a pickup path. Routing INTO the baton attaches the work to the session that will actually do it. It is also the write-side completion of reconcile-handoffs-before-inbox-triage: triage that only *reads* the batons can classify an item as in-scope yet leaves no record — the committed routing note is that record.

Surfacing ceremonies (`/workday-start` Step 1.45, `/workstream-start` § Outstanding cross-repo memos) perform both the routing write and its paired resolve at triage time. That is the one carve-out to the "`/workstream-start` surfaces, `/pickup` acts" boundary (below), and it is narrow by construction: the ceremony may close a memo *only* into a baton it just committed, with the disposition recorded. Every other memo-lifecycle fork — adjudicating an ask on its own terms, declining, superseding — still lives solely in the `/pickup` memo branch.

#### Tri-plane reroute — an ask targeting another plane's charter routes to that plane's owner

<!-- distilled: run 2026-08-06-14h38; nugget: c7-061 — durable-store→rag routing retired (claude-klabauter DR-236 superseded the prior DR); this section already carries the capability-vs-custody framing (query/retrieval-capability plane, not custody) the nugget calls for -->

Accept has a **partial + reroute** shape when the ask targets work your repo does not (or does not currently) own. The fleet work-state system decomposes into three planes, each with a single named owner (governing authority: DoE's `docs/decisions/DR-047-doe-claude-klabauter-boundary-redraw-contract-vs-e.md`, custody-vs-projection framing supplied by `claude-klabauter/docs/decisions/DR-236-state-is-disk-truth-workstate-store-is-pro.md`; routing fact mirrored in `state-placement-law.md` § Residency Is Not Ownership):

- **Artifact-shape / contract plane → coordinator-claude.** The `artifact-shape-contract`, the cockpit-contract Zod shapes, doctrine, skills. The contract never migrates.
- **Emission-write plane → claude-klabauter.** Producing/snapshotting work-state artifacts to a versioned disk emission (the `emit-cockpit-snapshot.py`-class producers (claude-klabauter); DD#2 "emission write") — and holding custody of its own disk-truth bytes; claude-klabauter's `state/` is the authoritative store for claude-klabauter's corpus.
- **Query/retrieval-capability plane → rag.** rag owns the chunker/embedder/query capability code, reading and serving over a *derived, re-projectable projection* of another plane's disk-truth — not a durable store in its own right, and not a fleet system-of-record.

An inbound `ask` can target a plane your repo does not own — most commonly an **emission-producer ask that lands on `claude-central-em` out of legacy habit**, because coordinator-claude hosted the tc-3 emission producers *before* the split that moved emission-write to claude-klabauter. The correct disposition is **neither decline** (the ask is valid work) **nor queue** (laundering, forbidden above). It is **accept-your-slice + reroute-the-rest**:

1. Realize the part *your* plane owns (e.g. a contract-shape change stays coordinator-side).
2. `cs_action_memo … --decision partial` — `decision_note` names the split and the reroute target; `realized_by` points at your slice's plan/commit.
3. **Memo the plane owner** (`cross-repo-memo draft <slug> --to <owner-em> …` then `send`) for their part, and **hand the PM the receiver path** for relay — the reroute is only real once the owner has it.
4. **Inform the original sender** of the reroute and any timeline shift via a return memo — do not let their `open`-expectation silently rot behind a plane migration they can't see.

This is durable routing, not a migration-window hack: post-migration the plane owner is permanent, so an emission-producer ask should *always* route to claude-klabauter. Worked instance: the 2026-07-04 cockpit backlog-history ask — the `backlogHistory` contract block realized coordinator-side, the recorder + emit-assembly rerouted to `claude-klabauter-em`, cockpit informed that v2.5.0 now sequences behind the emission-stack migration.

#### Adjudicate-and-own includes ceremony, not just disposition — and ceremony is the receiver's call

Once you Accept (above), a second judgment follows: how much *ceremony* does the work earn? This is the receiver's call, because **magnitude is not knowable to the sender and the sender's register does not encode it.** Under § Authoring an ask the sender writes every ask plainly and in the imperative — that rule governs sender *plainness* (don't soft-pedal real work into a suggestion-box submission), NOT how big a deal the ask is for your repo. The two rules are complementary halves of one discipline: **the sender states the work plainly; the receiver decides how big a deal it is.** Reading an imperatively-worded ask as therefore-weighty is the misread this pairing exists to prevent — a plainly-stated "move these eight documents" is mechanical, not a planning exercise.

- **Default: mechanical-direct.** Most accepted asks are surgical follow-ups. Do the work, commit it (both sides where authorized — see the carve-out below), action the memo. No plan, no round-trip, no back-and-forth.
- **Escalate to a plan ONLY on a NAMED weighty signal** — inherit [`ceremony-calibration.md`](./ceremony-calibration.md) § TL;DR: a *novel decision* (not a surgical follow-up to one already made), *instance #1* of a pattern with downstream occupancy, or *vague framing* that needs shaping first. Absent a named signal the default stands; do not manufacture ceremony to feel thorough.

**Channel and ceremony are orthogonal axes — do not conflate them.** Two independent questions govern cross-repo coordination; they are NOT a hierarchy:

- **Channel axis — *do I use the memo channel at all?* — keyed to GOVERNANCE *and* CHANGE-CLASS.** `triad-roles-doctrine.md` §208 (project-rag-ue-addon) eliminates the blocking memo channel within the same-PM/EM triad for **two narrow classes only**: (a) **break-glass / emergency** coordination, and (b) **DoE-altitude structural / doctrine seeding** (CLAUDE.md / wiki / agent-prompt edits authored from on high). For those, cross-repo coordination is *direct commits into the peer repo*; memos become after-the-fact `## Response` records, not handshakes. **Everyday cross-repo code / install-surface / contract changes route via `cross-repo-memo` + PM-relay even inside the triad** — the owning-EM-lands-with-context discipline is the default, because the cross-repo-write-without-the-owning-EM's-context hazard does not disappear under shared governance. §208 is a narrow exception, NOT a general "triad ⇒ direct-commit" default. The channel choice is settled by who owns the repos **and which class of change it is** — magnitude is the *ceremony* axis, not this one.
- **Ceremony axis — *given a memo arrived, how much process?* — keyed to MAGNITUDE,** operative only *inside* the memo channel. This is the receiver-judgment rule above.

§208 is **not** "the low-ceremony case of the receiver-judgment rule," and the receiver-judgment rule is **not** "§208 generalized." The channel axis is keyed to *class*, not magnitude: a triad EM doing a weighty **doctrine-seed** skips the memo channel (channel axis), but a triad EM doing weighty **code/install-surface** work still routes via memo + PM-relay; a non-triad EM receiving a mechanical ask still does it directly (ceremony axis). Name the axis that applies — never nest one rule inside the other, and never read "triad" as license to direct-commit code into a peer repo. (This is the exact confusion that produced the over-ceremony incident this rule fixes: a mechanical transfer was read as weighty because the channel-vs-ceremony axes were conflated.)

**Both-sides-commit carve-out — three cases (mechanical cross-repo transfers).** When an accepted mechanical ask is a *transfer* (move a document, relocate a file, hand over ownership), the receiver may need to write into the offering repo too. Scope it:

- **(i) Triad + you own both repos AND the transfer itself is one of §208's two named classes (break-glass, or DoE-altitude doctrine-seeding)** → §208 direct-commit governs (channel axis) natively; the both-sides-commit is not a separate carve-out, it falls out of §208's own regime. Triad membership and dual ownership are necessary but not sufficient — a mechanical transfer that is code/install-surface work does NOT qualify here even inside a triad (§ above: "a triad EM doing weighty code/install-surface work still routes via memo + PM-relay"); that transfer falls to case (ii) or (iii) below instead.
- **(ii) Non-triad but you hold authority over both repos** → the both-sides-commit carve-out applies as a ceremony-axis legibility aid: commit the offering-side change because you hold authority over it. This is a sanctioned cross-repo write for a *mechanical transfer*, scoped to has-authority-over-both — **not** a blanket license.
- **(iii) You lack authority over the offering repo** → the offering-side change routes per the altitude rules (§ Doctrine seeding vs code/install-surface): memo + PM-relay for code/install-surface, direct doctrine-seed for doctrine. The carve-out does not apply.

**Case (ii) instance — publish-target-where-DoE-is-sole-writer.** The canonical instance of Case (ii) is a cross-repo install-surface fix that spans the meta-repo (`~/.claude`) and its OSS publish target (`coordinator-claude`). The DoE holds authority over both: the meta-repo is the source-of-truth; the publish target is a percolation destination with no sibling EM session and no independent writer. In this configuration, a direct write to the publish target is not a surprise to any collaborator — it IS the routine DoE operation (`setup/publish.sh` percolation), and the fix cannot land at meta-repo-only without silently degrading OSS-user experience.

`state/lessons.md` (content-anchor: "Cross-repo direct write is for doctrine-seed only; code/install-surface changes route via memo + plan, even when PM-authorized [universal]") warns against generalizing PM-authorized direct writes. The publish-target instance is the named structural carve-out from that lesson's prior framing: the warning governs writes to sibling repos that have their own EM/consumers who would be surprised; it does NOT govern writes to a publish target the DoE owns and exclusively drives via `publish.sh`. Canonical plan instance: `docs/plans/2026-06-11-exec-bit-install-surface-completion.md` (exec-bit install-surface completion — direct writes to both repos, PM-authorized, no cross-repo memo required because the OSS repo is a publish target with no independent EM session).

**`/workstream-start` surfaces, `/pickup` acts.** This is an architectural boundary, not a gap: `/workstream-start` (via `workday-start-cross-repo-memo-surface.py`) provides awareness; adjudication lives solely in the `/pickup` memo branch. Teaching both entry points the same fork creates divergence risk. Its one carve-out is the route-to-baton close (§ Route-to-baton, mechanic 4) — no fork to duplicate there, since the ceremony may only resolve a memo into a baton it just committed; everything requiring a judgment call still routes to `/pickup`.

### Do-now applies to memos — a "land before X happens" ask is do-now

> The do-soon→do-now discipline governs inbound memo-asks too: an Accept IS the work, this session — not an agreement to do it before a future gate.

**Failure shape.** A sibling EM memos *"land your fix on your pushed branch before <our coupled release>."* The receiver "Accepts" in word — `decision: accepted`, *"sure, we'll do that before the release"* — and the agreement substitutes for the action. The stamp says yes; nothing lands. It reads as actioned at the next `/workday-start` while the requested fix still hasn't landed. Deferral in Accept's clothes — the laundering `realized_by` exists to stop, slipped past because *"before X"* reframed do-now work as do-before-a-gate. The anti-pattern is deferring the landing, not which ref it lands on.

**Discriminator — two independent axes; don't collapse them.** The **work-gate** (*when do I do the fix?*) is **do-now**: landing the fix on your pushed shared branch is just doing the work — a commit is not a release, and doing the work does not wait on `merge-to-main` (branch-landing is the work-gate; `merge-to-main` is the PM-owned ship/sync-gate — see `daily-branch-discipline.md § Align on branch`). The **release-gate** (*when do the coupled repos go live together?*) gates the synchronized go-live, never the landing of either half. Reading *"land before X"* as a reason to defer the *fix* conflates them.

**Release synchronization is PM-owned, like memo relay.** Shipping dependent repos *together* is a human-relay concern the PM holds. The EM does not hold back a landable fix as a private release maneuver ("I'll wait to land mine until theirs is ready") — that re-implements a gate the PM already owns. Land your half **now**; if the go-live must be synchronized, that's a one-line surface to the PM, not undone work.

**Reply mechanics** (the existing ack-of-ack / partial-ack rules, applied here):
- **Sender hasn't landed their half** → `kind: ask` return memo: *"mine is at `<SHA>`; land yours."* New info + a live request → legitimate, not ack-of-ack. The full form of *partial-ack unblocks the sender* (§ above) — send it the moment your half lands.
- **Sender already landed theirs** (verify: `git fetch` + `git branch --contains <their-SHA>`) → **no** reply memo. Stamp the inbound in place: `status: actioned`, `decision: accepted`, `realized_by: <your-SHA>`, `decision_note: "both halves landed — mine <SHA>, theirs <their-SHA>"`. The stamp is the receipt; a reply is ack-of-ack.


Premises stay hypotheses: a concurrent session may already have landed your half (§ Memo content is hypothesis; Verify premises, formerly M2). Do-now means do the verified-still-needed work now, not commit blind.

### Extension-items audit — scope-narrow inbound `ask` proposals before actioning

When an inbound `ask` memo carries a multi-item proposal table, the receiver EM must identify the load-bearing items for the **named problem statement** first. Proposal extensions ("while we're here, also flip X") ride along for free ONLY if they satisfy the same shipping discipline as the load-bearing item. Default to scope-narrowing; ratify additions one at a time.

The sender is closer to their own frustration than to the problem boundary the receiver-EM is solving. Reading an imperatively-worded proposal table as "all items are load-bearing" is the failure mode — the sender writes all items plainly (§ Authoring an ask), but plainness does not imply load-bearing. Source: repo-setup-produce-not-prescribe pickup.

### Receiver decline on substrate grounds is premise correction — send an outbound notification

When a memo is declined because the cited locus is wrong (it lives in the sender's repo, not the receiver's), the receiver-side disposition flip (`status: actioned, decision: declined`) is **not terminal** — the sender expected action; without outbound notification they will not revisit their archive for weeks.

**Rule when partial-declining on substrate-correction grounds:** dispatch an outbound `kind: ask` memo naming (a) that the receiver's substrate-check found the fix lives on the sender's side, (b) the concrete fix shape (or pointer to work already done that helps them), and (c) any evidence gathered (test invocations, grep paths). The decline is a premise-correction, not a conflict; treat the receiver as authoritative on their own substrate and hand the work back with a concrete specification.

*Complement to the general receiver-judgment rule:* the adjudicate-and-own gate covers the case where you ACCEPT; this rule covers the case where you DECLINE on substrate grounds. The obligation to notify is the same in both cases. Source: claude-home-exec-hardening pickup.

### Don't re-nag the PM about already-sent memos

Once the receiver path has been handed to the PM at send time, the sender's job is done. Do not re-list memos (or doctrine-seeding direct writes) as "pending PM-relay" or "pending your action" in later session reports, `/handoff` bodies, or session openings. The receiving repo's `/workday-start` Step 1.45 surfacing is the canonical channel; sender-side action-state knowledge goes stale silently. Operative rule lives in `skills/workstream-complete/SKILL.md` § Step 2.66.

### Grandfather cutoff

**Pre-2026-05-22 memos are grandfathered.** Step 1.45 skips memos with `created: < 2026-05-22` by design. If a pre-cutoff memo has unfinished business, re-issue via `cross-repo-memo` with `supersedes: <old-path>`.

**Disambiguation — `supersedes:` on a memo vs. on a live baton.** The `supersedes:` field means something different depending on the artifact type. Canonical contrast (verbatim, also in `docs/wiki/spinoff-handoffs.md` § `supersedes:` on a live baton):

> "`supersedes:` on a memo = terminal (paired with `superseded_by:` + `status: superseded`, wired in the `CROSS_FIELD_RULES` memo block); `supersedes:` on a live baton = conditional+live, a spine-build-time preference (never flips status, no back-pointer, wired in the `CROSS_FIELD_RULES` handoff block)."

On a **memo**, `supersedes:` is a terminal re-issue signal — the old memo is paired with `superseded_by:` and its `status:` flips to `superseded`; the old memo is dead. On a **live baton** (`kind: spinoff`), `supersedes:` is an optional spine-build-time preference used by the orientation-supersession convention (`docs/wiki/agent-install-contract.md` § Orientation-supersession); it does NOT mark any baton dead and never flips `status:`. Cross-reference: `docs/wiki/spinoff-handoffs.md` § `supersedes:` on a live baton carries the matching note.

### Worked example

Memo from `claude-central-em` to `project-rag-em`.

**Step 1 — Sender writes** (POSIX-host form, Shape A; a PowerShell host uses rung 0 / Shape W —
see `coordinator/snippets/resolve-coordinator-bin.md`)**.** Resolves `cross-repo-memo draft
gate-check-fix --to project-rag-em --title "Gate-check failures in check-plugin-drift.py —
recommended fix"`, writes the body into the printed outbox path, then `cross-repo-memo send
gate-check-fix`.

CLI writes `X:/project-rag/cross-repo/inbox/2026-05-23-claude-central-em-gate-check-fix.md` (dirty, untracked) with: <!-- foreign-path-ok: illustrative worked-example CLI output, not a live path assertion -->
```yaml
---
title: "Gate-check failures in check-plugin-drift.py — recommended fix"
from: claude-central-em
to: project-rag-em
created: 2026-05-23
status: open
---
```

CLI prints:
```
Receiver-side: X:/project-rag/cross-repo/inbox/2026-05-23-claude-central-em-gate-check-fix.md <!-- foreign-path-ok: illustrative worked-example CLI output, not a live path assertion -->
Hand the PM this path for relay: X:/project-rag/cross-repo/inbox/2026-05-23-claude-central-em-gate-check-fix.md <!-- foreign-path-ok: illustrative worked-example CLI output, not a live path assertion -->
Reminder: Hand the PM the receiver path — PM-relay is still the primary channel.
```

Sender notes the send in their workstream-complete notes. No sender-side file is created.

**Step 2 — project-rag-EM sees the dirty file** at next session open (`git status` shows `?? cross-repo/inbox/2026-05-23-claude-central-em-gate-check-fix.md`), reads it, implements the fix, then flips status in-place:
```yaml
status: actioned
decision: "Fixed gate-check exit-code handling in check-plugin-drift.py"
```
Commits: `memo: actioned 2026-05-23-gate-check-fix — accepted and implemented`

Done. Memo lives in `project-rag/cross-repo/inbox/` as the active record; once actioned it may be swept to `project-rag/cross-repo/archive/`. No further action required on either side.

