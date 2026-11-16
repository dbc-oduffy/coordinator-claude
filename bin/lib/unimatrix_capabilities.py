"""What the current Unimatrix far relay serves, and the two checks a sender makes against it.

Pure: no I/O, loadable by path. `CAPABILITIES` names the relay verbs; `skew_reason` says why a sender
cannot use an older far relay; `ingest_acked` reads the far relay's per-line receipt digest as the
ingest ack."""
from __future__ import annotations

import hashlib
from collections import Counter

CAPABILITIES = frozenset({"send-session", "receipts", "capabilities"})

UNACKED = "unconfirmed: no far receipt for this line"


def skew_reason(far_caps, needed) -> str:
    """"" when every verb in `needed` is in `far_caps`; else the named skew for the first missing verb
    (sorted order, so the line is stable). `needed` may be one verb name or an iterable of them."""
    wanted = [needed] if isinstance(needed, str) else sorted(needed)
    have = set(far_caps or ())
    for verb in wanted:
        if verb not in have:
            return f"far relay lacks {verb}; upgrade it (version skew)"
    return ""


def line_digest(line: bytes) -> str:
    """sha256 hex of `line` without its trailing newline: the digest `record_receipt` writes on the far relay."""
    return hashlib.sha256(line.rstrip(b"\n")).hexdigest()


def ingest_acked(lines, receipt_rows) -> list[tuple[bool, str]]:
    """Per input line, `(True, "")` when a reply or receipt row carries that line's digest, else `(False, error)`.

    `receipt_rows` are far `send-session` replies or `receipts` rows. A reply with `ok` false never acks
    (its own error is reported); an ok reply without a `digest`, or with one that matches no line, acks nothing.
    One row acks one line, so a line sent twice needs two rows."""
    available: Counter = Counter()
    refused: list[str] = []
    for row in receipt_rows or ():
        if not isinstance(row, dict):
            continue
        if row.get("ok") is False:
            refused.append(str(row.get("error") or UNACKED))
            continue
        digest = row.get("digest")
        if isinstance(digest, str) and digest:
            available[digest] += 1
    out: list[tuple[bool, str]] = []
    for line in lines:
        digest = line_digest(line)
        if available[digest] > 0:
            available[digest] -= 1
            out.append((True, ""))
        else:
            out.append((False, refused[0] if refused else UNACKED))
    return out
