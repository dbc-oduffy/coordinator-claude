---
title: Group-EM standing — legible, not binding
type: doctrine
status: active
---

# Group-EM standing

## The negative result

Across every production multi-agent framework — LangGraph Supervisor, AutoGen GroupChat, CrewAI
Hierarchical Process, OpenAI Agents SDK — hierarchy is enforced by **control flow**: the
supervisor holds the graph/routing/handoff list and decides what gets sent where. None of them
make hierarchy legible in a message a peer could inspect; a subordinate complies because the
supervisor controls what reaches it, not because it recognises the sender's authority. The only
research directions that put binding authority *in* a message — signed claims, delegation chains,
capability attenuation, continuous attestation (MIT Media Lab, Microsoft Agent Governance
Toolkit, AgentDID) — are research, not a production standard in any communication protocol today.

The Group EM has **no control flow** over peer sessions. Peers are independent Claude Code
sessions the Group EM cannot route, halt, or override — not its subagents. Therefore:

**Standing can be made legible. It cannot be made binding.**

## What standing does deliver

A receiving EM can establish, cheaply and without asking, that an inbound message came from the
session currently holding the sitting Group-EM nomination — a lookup, not a challenge. What the
receiver does with that fact is theirs to decide; the record carries no compulsion of its own.

This is independently backed at the harness level: the harness already refuses to let an agent
message count as user approval, grant a permission prompt, or change `CLAUDE.md`/config. The
"legible, not the PM" boundary is not merely asserted in prose — the harness enforces the adjacent
claim structurally.

## Resolve from the record, never from the message's own claim

A receiver determines standing by reading the nomination record (joined to
`~/.claude/sessions/*.json` on `sessionId`, per `coordinator/bin/group-em-nomination.py`), never
by trusting a sender's self-description inside the message body. Prompt-injected authority
claims and confused-deputy propagation — a compromised or manipulated agent asserting a role it
does not hold — are documented risks in the wider multi-agent literature; resolving from the
record rather than the claim is the mitigation available here.

The record proves who claimed the standing, not who granted it. Authority also needs proof that a
human typed `/group-em` in the holder's own session, which only the harness can stamp
(`origin.kind: human` on the holder's transcript). The engine's `read_authoritative` checks for that stamp,
and the SessionStart presence line grants the PM-delegated clause only when it is found. Any other
claimant is unverified and gets treated as an ordinary peer. Tripwire:
`GROUP-EM-AUTHORITY-REQUIRES-A-HUMAN-TYPED-ENTRY`.

## Every peer is told at boot, in one line

`assert-em-role.py` emits `G-EM active: <name> (<session prefix>)` at SessionStart, iff a live
nomination holds **this** repo — never another repo's, and never from a cache. It is identity so
an inbound claim can be weighed against something already known; it confers nothing.

No nomination, a lapsed one, or no peers all render no line — silence is the common case, not a
failed check. `name` is advisory and a rename voids it; the session id is what joins. Pinned by
`coordinator/tests/test_assert_em_role_group_em_line.py`.

## `/color` and `/rename` are a one-time act, not automation

Hooks cannot invoke `/` slash commands. Nomination therefore performs no automatic recolour and
no automatic rename — there is no hook-driven path to either. What exists instead: the nominated
session runs `/color` and `/rename` on itself once, or is launched already configured via
`claude -n`. A one-off self-configuration act at nomination time is not the same thing as prose
governing ongoing behaviour, and no artifact should imply the latter.

## Lapse, not re-bind

A `/clear` or a resumed session mints a new `sessionId` while the terminal process persists. A
standing nomination lapses across that boundary — it does not automatically re-bind to the new
session id. An operator can be sitting under a nomination that has already gone not-live with no
visible reason to suspect it; a reader resolving standing should treat lapse as the default
outcome of a restart, not an edge case.

## Entry op refusal shapes — full rationale

An unreachable engine refuses (exit 7) rather than quietly assembling in-tree, because a silent
fallback would route around an authz classification, not a latency budget — `--local` exists as
the explicit opt-in for in-tree assembly, and prints whether this tree's copies match the
engine's (`DRIFT UNKNOWN` counts as an unknown, never a match). Exit 6 means a digest arrived
under a refused standing: that engine armed cooldowns for peers the caller has no standing to
offer, so the payload is refused whole rather than salvaged, and the caller re-runs once the
mirror carries the standing-gate fix.

"Standing first, last writer wins" exists because a nomination record outlives its own session —
"someone is listed" is not "someone is coordinating," and entry never refuses over an incumbent
(there is no override flag). Re-entry by the current holder is a refresh, not a challenge.

## Owed introductions — the full argument

A displaced holder that is still running is owed a message because it may still believe it holds
the role and act on that belief; a holder that is not live has nobody to tell. A peer that does
not know who holds the crown routes its asks to the PM instead — the exact standing failure this
mode exists to absorb — and nothing in the entry payload tells a peer that on its own.

The five constraints on that introduction (name+session id+routing+"no reply wanted", never a
routing request back through the crown, content-enforced as an introduction rather than a nudge,
arming no cooldown, and tracked per session id once) each close a specific failure mode: an
acknowledgement storm, an accidental relay hop into a conversation that already has a direct PM
channel, a smuggled nudge riding a gate-exempt broadcast, a double-counted offer against the
digest, and a peer that joins the roster later never learning who holds the crown. A name is not
an identity — see the section above.

## Slot discipline: kill and cap timers

**Kill by process tree, not parent PID.** `taskkill /T` walks the Win32 parent chain only. MSYS-detached
children (bash subshells, `sleep` cap timers) survive it, hold the run's log files open, and fail the
relaunch. Kill a run by matching its tree on command line, creation time, or a job object, and census
the process table for survivors before relaunching. A kill helper that is code is claude-klabauter's portable
Python; the rule is stated here. Tripwire: `A-TREE-KILL-MUST-REACH-MSYS-CHILDREN`.

**The HOLD wait lives in the outer driver, ahead of any cap timer.** A cap timer started before a
HOLD-file wait counts down while the run is held, so the run is capped before it starts. Wait for
release first, then start the timer. Tripwire: `A-CAP-TIMER-STARTS-AFTER-THE-HOLD`.

**CPU is a slot class: at most about 2 CPU-heavy runs hold the box at once, whatever memory is free.**
CPU-heavy: builds and cooks, indexer workers and reindexes, extraction, bundle/gzip, engine publishes,
batches of headless-browser runs, and CPU model inference (its BLAS threads take every core unless
`OMP_NUM_THREADS`/`MKL_NUM_THREADS` cap them). Group EM releases waiting peers in order as a slot frees, and a
slot is held only by a live PID — a dead holder frees it. Its box `Monitor` emits `CPU HIGH` when load
holds at or above 85% for a minute and `CPU OK` when it falls below 70%; a CPU slot is released only
after `CPU OK`. Tripwire: `A-CPU-HEAVY-RUN-TAKES-A-CPU-SLOT`.

**The GPU is a slot class of one: one VRAM-heavy run holds it at a time.** VRAM-heavy: a UE editor
or cook on a hardware RHI, a GPU embedder or its sidecars, model inference. A GPU run also takes a
CPU slot. Read VRAM with `nvidia-smi --query-gpu=memory.used,memory.total --format=csv`; a run that
exhausts VRAM alone (an editor batch growing per item) is batched smaller, never re-run whole. A
software renderer (`--use-angle=swiftshader`) holds no GPU slot but rasterises on every core: pin
its root's affinity (`start /affinity F`) so the children inherit it. The shared project-rag embed
sidecars hold VRAM and respawn on the next query, so a kill frees nothing: their owner parks them with
`project_rag_scripts/park_embed_sidecars.py park --minutes N --holder <session>` (repo from
`machine-local get repos.project_rag`), which lapses on its own. Tripwire:
`A-VRAM-HEAVY-RUN-TAKES-THE-GPU-SLOT`.

**A slot END states `items=<succeeded>/<attempted>`, and an all-refused batch exits non-zero.** A
batch that refuses every item inside its loop still exits 0, so the exit code alone frees the slot
as a success. The Group EM judges a run by `items=`. Tripwire:
`A-SLOT-END-REPORTS-ITEMS-NOT-ONLY-THE-EXIT-CODE`.
