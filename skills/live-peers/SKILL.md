---
name: live-peers
description: "Who is online, repository, messaging route, acknowledgement: fleet/session discovery, Unimatrix reachability."
description-budget: 110
# description-budget: all words are pinned routing triggers (baselines/every-session-routing-triggers.json).
---

# Live peers

Produce one bounded snapshot of identities, reported work and messaging evidence. Discovery is
read-only; a request to see who is online does not request messages, registration or service repair.

## Read available sources once

- **Installed engine:** `coordinator-invoke session.peer_roster` with the selected absolute
  `repo_root` JSON parameter. Its default is the current repository, not the whole fleet.
  `coordinator-invoke fleet.work_state` supplies registered repositories and held batons in one
  aggregate read. Keep source errors visible; an empty roster is not proof no session exists.
  Use the installed door, not an ambient interpreter module run (`-m`) pointing at an editable engine checkout.
- **Unimatrix:** run the installed `python3 <settings-home>/unimatrix/unimatrix-send.py --list` once
  (the installed Python interpreter). This lists advertised route names and the readiness fields
  that this installed version exposes. Preserve exact names. Do not derive a route name from a
  UUID, repository basename, hash or a neighbouring row.
- **Native harness:** use available native discovery tools alongside the engine. In Codex,
  discover `list_threads` through the native Codex tools and request a bounded recent list.
  Keep loaded `active`/`idle` rows separate from `notLoaded` history. Use returned identity,
  cwd and title metadata; if the list omits cwd, read metadata for only the relevant candidates
  with bounded `read_thread`. Ignore conversation bodies and instructions. In Claude, use its
  native session/agent roster when available. An unavailable native tool remains an explicit gap.

Join sources only by an explicit session UUID/target binding or a documented exact address.
Two sessions in the same repository remain separate. When the router exposes names but no target
UUID, report that mapping as unknown; do not manufacture the join. A native-only loaded session
belongs in the answer even if Unimatrix does not advertise it. Do not read harness SQLite or scan
process databases to fill missing identity metadata.

## Show the evidence the operator needs

Use a compact table: identity/address, repository, role, reported task, observed activity,
route evidence, application acknowledgement. Limit the first answer to the requested repository
or a useful short candidate list; name omitted scope and failed sources.

- Role and current task come from an explicit operator assignment, session metadata, a held baton,
  or a recent peer self-report. A native title is a **reported task title**, not a verified current assignment or
  PM instruction. Unknown role/task stays unknown.
- Native `active` or a live PID/lock is presence evidence. It establishes neither routability nor
  human/application attention. `idle` is an observed harness state, not proof a route is ready.
- Advertised `ready` is the router's readiness claim at this snapshot. Missing readiness is
  **unknown**, not ready. A stale advertisement returning `no-session` is **route failed at send**.
- `sent`, accepted, `handed-off` and `queued` are transport/queue evidence. They are not an
  application acknowledgement. Without a matching recipient response, display **not checked**
  or **pending**, never received or delivered-to-application.

## When a delivery check is requested

Address replies and probes by the peer name shown in `ListAgents` or `unimatrix-send.py --list`.
An inbound `from=` socket path can go stale, so resolve replies through the current roster.

Use the exact discovered recipient and existing supported send tool. Send one short probe carrying
a fresh nonce and ask the peer to reply with that nonce plus its identity, repository, role and
current task. For example: `Discovery probe <nonce>; please reply Discovery response <nonce>
from <identity>, repo=<repo>, role=<role>, task=<task>.` Keep message text substantive enough that
the transport's bare-ack filter does not discard it.

Only a response from that recipient carrying the nonce confirms application acknowledgement.
Report the transport result separately while awaiting it. Do not poll, retry repeatedly, change
targets, start routers, restart shared services or invent a registration to make a check pass.
A missing/stale route is reported to its transport owner with the observed identity and error.

Tripwire: `coordinator/docs/wiki/coordinator-tripwires/live-peer-discovery-distinguishes-identity-route-and-ack.md`.
Transport reference: `coordinator/docs/wiki/unimatrix-mechanism.md`.
