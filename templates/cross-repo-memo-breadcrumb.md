# cross-repo-memo — send-verb breadcrumb

> Looking for the cross-repo memo **send** verb? It is not a file in this repo.

`cross-repo-memo` is an executable that lives on your PATH — it is deliberately NOT
vendored into any consumer repo, which is why a tree-scoped search (`ls bin/`,
`find . -name 'cross-repo-memo*'`, grep) comes up empty. Ownership is mid-strangle
under DR-210 and is deliberately not stated here: the verb you invoke is the stable
seam, and nothing you do as a sender depends on which tree the source sits in today.
Confirm it is available with:

    which cross-repo-memo

## Sending a memo — draft → compose → send (preferred; body-heavy memos)

    cross-repo-memo draft <topic> --to <receiver-em> --title "<one-line summary>"
    # edit the staged draft at state/memo-outbox/<topic>.md
    # (cross-repo-memo compose <topic> reprints the path; --open execs $EDITOR)
    cross-repo-memo send <topic>

Other draft verbs: `list` (outbox drafts + age), `discard <topic>` (drop an unsent draft).

Write the body into the outbox path the CLI prints, never `%TEMP%` or a `tasks/` path.
The CLI owns that buffer; a body staged anywhere else is not what `send` reads.

`--summary` is capped at 120 characters and is checked at SEND, not at draft. `draft`
accepts an over-length summary without complaint, so the refusal arrives after the body
is written rather than when the mistake is made. Omit `--summary` and one is derived
from the body.

An empty outbox is the SENT state, not a failed send. `send` stamps the draft and parks
it under `state/memo-outbox/sent/`, out of the way of the stale-draft nudge, so the
topic is gone from the outbox listing afterwards either way. Verify a delivery against
the receiver's inbox or archive, never against a surviving local draft — reasoning the
other way once escalated a delivered, actioned memo to a PM as possibly never sent.

There is no one-shot form. `draft` -> `send` is the only way to deliver a memo; the flag-only
send form was removed, and reaching for it after a refused `send` finds nothing behind it.
Called out rather than silently dropped because an EM who remembers it will look for it.

Sent memos land in the receiver's inbox (delivery_mode: receiver-repo). The inbox root is
resolved per-receiver, not a fixed subpath: `<receiver-repo>/state/cross-repo/inbox/` when that
root exists on disk, else the legacy `<receiver-repo>/cross-repo/inbox/`. Repos are migrating to
the `state/` root one at a time, so the two answers coexist and neither is the fleet-wide truth.

Run `cross-repo-memo --list-receivers` for valid `--to` targets on this machine.
Run `cross-repo-memo --help` for the full verb + flag reference.

See your own inbox's `README.md` for the inbound side of the channel, and the full
doctrine at coordinator `coordinator/docs/wiki/cross-repo-communication.md`.
