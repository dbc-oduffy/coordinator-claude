---
segment_id: persistence
class: protected
order: 8
situation: persistence
---
No peer roster or reachability fact is persisted. Two carve-outs: the send log
(`build_send_digest` appends to the session-scoped `group-em-send-log.jsonl`, so a new Group
EM starts with an empty cooldown), and the engine's box holder record: relaying the PM's word
(`[PM via G-EM <name> <sid8> <ISO>]`, record first) and clearing a needs-PM flag
(`gem-triage-turn-intent`); contract page §§ 2–4. Tripwire: `A-PM-VIA-G-EM-RELAY-QUOTES-AND-POINTS`.

A `/group-em` session **is** that repo's Driver while it runs; build no registry. Re-read peer
state immediately before acting on it, **never** via a second entry op in one wake.

### Gating granularity — entry AND per send

**Entry stays PM-gated.** **The send is gated separately, per send:** the
`ask-before-external-action` question lives there, justified by **cost to the receiver**.

### Standing check

**Confirm this session still holds the nomination**: `<plugin-root>/bin/group-em-nomination.py who
--repo <root> --json` (read-only). Never re-run `group-em-enter.py` for this — it re-claims and
re-arms the send digest's cooldowns.
