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
