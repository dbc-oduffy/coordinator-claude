---
segment_id: entry
class: protected
order: 5
situation: entry
---
**Typing `/group-em` fires entry:** `hooks/scripts/group-em-autofire.py` runs the entry op and
injects standing, roster, digest and baseline. **Context absent = entry did not happen** (the hook
fails open): run `<plugin-root>/bin/group-em-enter.py --repo <root> --session-id <your sid>` and
find out why. **`--session-id` is required** (exit 2 without it). Every `<plugin-root>/bin/` CLI is
plugin-local: resolve per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`.

**Exit 5: refused standing** — a live or unaccounted-for incumbent holds the role;
`roster`/`digest`/`baseline`/`teammates` are absent. Payload shape:
`coordinator_core/ops/group_em_enter.py`'s module docstring.

Never import `read_pass` / `send_pass` directly.

**Last writer wins:** entry never refuses over an incumbent; holder re-entry is a refresh.

### Owed sends, all exempt from § Send pass's gates

**A displaced holder still running is OWED a message this turn** (`displaced_holder`,
`displaced_holder_live` in the entry context; not live = nobody to tell).

**The owed message also tells it to release its watch:** TaskStop its watch shell, confirm the
subprocess is gone, never re-arm under the lost role.

**INTRODUCE YOURSELF TO EVERY LIVE SESSION ON THE BOX, ONCE** — § Box-wide notice computes the
recipients and text. Skip only a `PAUSED:away` peer; re-resolve each addressee before sending
(§ Send pass step 4).

1. **Say four things and stop:** who you are (name, session id); that you hold the Group EM
   standing for this repo; what to route to you; **that no reply is wanted**.
2. **Never ask peers to route their PM reports through you** ("the PM is typing into that session"
   is unobservable); key it to something CHECKABLE, such as **a session answering a question just
   asked in this exchange**.
3. **It asks nothing** (no question mark), **arms no cooldown and is not an offer.** Only
   `build_send_digest` emitting an entry arms a peer's throttle.
4. **Once per PEER, tracked by session id AND name**; on ambiguity re-introduce.
   `_record_introduction` in `coordinator/bin/group-em-box-notice.py` makes the set durable in the
   send log.
