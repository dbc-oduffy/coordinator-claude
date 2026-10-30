---
segment_id: passes
class: protected
order: 7
situation: passes
---
### Read pass (gem-13)

The classify ladder lives in `read_pass.py` beside this file, invoked through § Entry's op:
`build_roster(repo_root)` (classified population), `build_candidate_roster(repo_root)` (paused-only
shortlist).

### Send pass (gem-14)

`send_pass.py` turns `build_roster`'s **full** population into **one digest per invocation**
(`build_send_digest`). It selects and throttles; **it does not send.**
**`roster` IS NOT THE POPULATION — it is the shortlist**, `build_candidate_roster`'s output.
`undischarged_obligations: None` means no ledger exists, never that the peer owes nothing.

**Compare `roster_considered` (entry's enumerated count) against the room, never `len(roster)`:**
smaller than the sessions you know are running is `unknown`, never quiet (remit § The roster is
not the population). Two settling reads: `claude agents --json`, and `python3 -m
coordinator_core.group_em.idle_report --repo-root <root> --group-em-session-id <your sid>`
(omitting the id degrades offer-log suppression silently).

**Ledger rows can arrive from the engine plane** via
`state/subagent-share/<sid>/obligations-inbound.jsonl`; this plane is the ledger's sole writer.
Contract: `coordinator/docs/wiki/cross-repo-communication/obligations-inbound-intake.md`.
Tripwire: `A-SECOND-WRITER-TO-A-REWRITTEN-FILE-LOSES-ROWS-SILENTLY`.

**Procedure, per invocation:**

1. § Entry's op already built both plus a `baseline` delta. **Act on that payload — never re-run
   the entry op**; `build_send_digest` arms cooldowns as it emits.
2. Present it (`suppressed`: held; `truncated`: next wake; `unrecorded`: cooldown write failed).
3. **Per entry you intend to message, declare both gates in prose before sending:**
   - **GATE 1 (owner live?).** Owner live on the box → `SendMessage`; a memo only for an owner
     with no live session, or as its record.
   - **GATE 2 (receiver).** Cheaper to them now than later? No instrument; judge from the peer.
   - **Either gate unclear → `SendMessage`.**
4. **Re-resolve the address from the SESSION ID just before sending; a refusal is a refusal.**
   `coordinator_core.group_em.send_pass.resolve_addressee(repo_root, peer_session_id)` returns the
   name that session answers to now, or `None` — do not send on `None`. **`repo_root` is the
   PEER's repo, not yours** (a peer in another repo resolves `None` against yours). Resolve from
   the id, never validate the name. Tripwire: `A-PEER-NAME-IS-NOT-A-STABLE-ADDRESS`.

**Never loop over `entries` sending.**

**A `PAUSED:away` peer is never offered**, reported as `never-send-reason`. Tripwire:
`A-PAUSED-ROSTER-IS-NOT-A-NUDGE-LIST`.
