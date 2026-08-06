#!/usr/bin/env python3
"""SessionStart hook: assert EM identity to the main coordinator session.

Separate from project-orientation.py on purpose (design decision, not a
re-litigable choice): orientation content is staleness-nudged and
suppressible (`COORDINATOR_REPOMAP_STATUS_OFF` et al., and the whole banner
degrades quietly on a missing cache) — a role assertion riding the same
channel would inherit that suppressibility, and a role assertion that can be
silently switched off is worse than none at all. This hook has exactly one
job, unconditionally: tell the main session it is the EM.

Why this needs to exist at all: the always-loaded doctrine corpus
(formerly `coordinator/CLAUDE.md`, retired 2026-07-27 and split into
`global-doctrine/CLAUDE.md` (all-agents) and `coordinator/snippets/
em-operating-doctrine.md` (EM-only)) was rewritten into role-neutral
system terms as part of the computed-skills frontage work, so it no
longer itself tells the reader "you are the EM". `snippets/agent-role-em.md`
is the single source of truth for that assertion — this hook's only
responsibility is delivering it into the main session's context via the
SessionStart `additionalContext` channel, unconditionally, every session.

Delivery is by an ORDERED MANIFEST of EM-only snippets (`_EM_SNIPPET_MANIFEST`
below), not a single hardcoded path — `agent-role-em.md` stays the terse
~2.1 KB role assertion it is named for; a second manifest entry,
`em-operating-doctrine.md`, carries fuller EM-addressed operating doctrine
that does not belong crammed into the role-assertion file (growing
`agent-role-em.md` itself would mislead by its own name). Snippets are
concatenated in manifest order into one `additionalContext` emission. The
manifest is the extension point for future EM-only channels — add an entry
here, not a second hook.

Manifest entries resolve against one of two roots, named per entry:

- `PLUGIN` — relative to `<plugin_root>/snippets/`. Fleet-wide doctrine
  shipped by coordinator itself; the same bytes reach every repo.
- `REPO` — relative to the CONSUMER REPO's root. This is the slot a
  consumer repo uses to put its own EM-only content into this channel
  without forking the hook: drop a file at the declared path and it is
  delivered, last, into the same emission.

Why the REPO slot exists at all: audience-narrowing beats stating content
in full, and stating it in full beats relocating it to a wiki nobody
reloads. Without a consumer-repo slot, a repo trying to move EM-only
content OUT of its always-loaded `CLAUDE.md` had no narrower channel to
move it INTO, and the only remaining move was relocation — the weakest
option — dressed up as a discharge. This slot is the missing rung.

Trust boundary: the REPO slot's file is repo-local content delivered into
the repo's own main session, exactly like that repo's `CLAUDE.md`. It
introduces no trust level the session did not already have.

Degradation is deliberately ASYMMETRIC by root. A missing PLUGIN entry is
a broken install and emits a loud per-entry banner. A missing REPO entry
is the overwhelmingly common case — most repos will never define one — so
absence is silent and the emission is byte-identical to a build without
the slot. A REPO file that EXISTS but cannot be read is not absence; that
is a real defect and banners loudly.

Main-session-only by construction: SessionStart-class hooks fire only for
the main session, never for an `Agent`-tool dispatch (that's the harness
property this hook relies on, not something it re-checks — see hooks.json's
registration comment for this entry, whose matcher enumerates every
SessionStart source the harness emits, so the channel re-fires at every
fresh-context boundary rather than only at cold start). No additional
is-main-session guard is layered on top here.

Path resolution mirrors project-orientation.py: this file's own location
(`Path(__file__)`), never cwd, never a hardcoded absolute path — must work
on a machine this was never authored on.

Contract: SessionStart hooks MUST exit 0 unconditionally (harness contract,
same as project-orientation.py). A missing manifest entry degrades to a
loud, visible per-entry error banner emitted as additionalContext (so the
gap is diagnosable in-session) rather than a silent empty emission or a
non-zero exit that could wedge session boot -- the OTHER manifest entries
still deliver; one missing snippet must not silently swallow the rest.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths: this file is at <plugin_root>/hooks/scripts/assert-em-role.py
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parent
_HOOKS_DIR = _SCRIPTS_DIR.parent
_PLUGIN_ROOT = _HOOKS_DIR.parent  # <plugin_root>/coordinator
_SNIPPETS_DIR = _PLUGIN_ROOT / "snippets"

# Ordered manifest of EM-only snippets delivered into the main session's
# SessionStart additionalContext, concatenated in this order. Each entry is
# (root, relative_path) where root is _ROOT_PLUGIN (resolved under
# _SNIPPETS_DIR) or _ROOT_REPO (resolved under the consumer repo root). See
# module docstring for why this is a manifest rather than a single hardcoded
# path, why agent-role-em.md is not grown to carry the second entry's
# content, and why the two roots degrade differently on a missing file.
_ROOT_PLUGIN = "PLUGIN"
_ROOT_REPO = "REPO"

_EM_SNIPPET_MANIFEST = [
    (_ROOT_PLUGIN, "agent-role-em.md"),
    (_ROOT_PLUGIN, "em-operating-doctrine.md"),
    (_ROOT_REPO, ".claude/em-context.md"),
]

# A consumer-repo EM-context file this large is a signal the repo is using
# the channel as a dumping ground rather than as the narrow EM-only surface
# it is for. Oversize content is still delivered in full -- silently
# truncating a repo's doctrine would be worse than the bloat -- but it
# banners so the growth is visible to the session it is costing.
_REPO_SNIPPET_SOFT_CAP_BYTES = 32_768


def _consumer_repo_root(payload: dict) -> Path | None:
    """Resolve the CONSUMER repo's root -- the anchor for _ROOT_REPO entries.

    Deliberately NOT Path(__file__)-based: that resolves the plugin tree,
    which for an installed plugin is a different repo entirely (and for the
    plugin's own dev checkout is only coincidentally the same one). The
    consumer root is whatever repo this main session actually opened in.

    Order: the harness's own project-dir env var, then the session payload's
    cwd, then the process cwd; from that starting point, walk up to the
    nearest ancestor containing .git so a session opened in a subdirectory
    still resolves the repo root. Returns None if nothing resolves -- an
    unresolvable root is treated as "no repo entry", never as an error.
    """
    candidates = [
        os.environ.get("CLAUDE_PROJECT_DIR"),
        payload.get("cwd"),
    ]
    start = None
    for candidate in candidates:
        if candidate:
            try:
                start = Path(candidate).resolve()
            except OSError:
                continue
            break
    if start is None:
        try:
            start = Path.cwd().resolve()
        except OSError:
            return None

    for directory in (start, *start.parents):
        if (directory / ".git").exists():
            return directory
    return start


def _read_stdin(timeout: float = 2.0) -> str:
    """Bounded stdin read -- mirrors project-orientation.py::_read_stdin()
    (a bare sys.stdin.read() has no timeout and can hang this SessionStart
    hook indefinitely on Windows)."""
    box = {"data": ""}

    def _read() -> None:
        try:
            box["data"] = sys.stdin.read()
        except Exception:
            box["data"] = ""

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout)
    return box["data"]


def _w(text: str) -> None:
    """Write raw UTF-8 bytes to stdout -- NOT print()/sys.stdout.write().

    Windows text-mode stdout translates LF to CRLF; mirrors
    project-orientation.py::_w()'s byte-parity convention.
    """
    sys.stdout.buffer.write(text.encode("utf-8"))


def _compose_missing_snippet_banner(rel_path: str, snippet_path: Path, exc: Exception, root: str) -> str:
    """One of the two manifest-entry error banners (module docstring's
    "loud, visible per-entry error banner"): the snippet file is absent or
    unreadable. `root` is `_ROOT_PLUGIN`/`_ROOT_REPO` and selects which of
    the two closing sentences applies -- extracted as a pure, separately-
    named function (not inline in `main()`) so a measurement harness can
    call it directly without going through `main()`'s stdin/exit-code
    plumbing; see docs/plans/2026-08-02-guard-message-character-cap.md,
    chunk C1's "Measurement mechanism" section."""
    del snippet_path  # already implied by rel_path; not repeated in the tightened prose
    if root == _ROOT_PLUGIN:
        return (
            f"assert-em-role: {rel_path} MISSING ({exc}) -- EM role not "
            f"fully asserted; restore coordinator/snippets/{rel_path}.\n\n"
        )
    return (
        f"assert-em-role: {rel_path} unreadable ({exc}) -- its content was "
        f"not delivered this session.\n\n"
    )


def _compose_oversize_repo_banner(rel_path: str, byte_len: int) -> str:
    """The third manifest-entry error banner: a REPO-slot snippet that
    exceeds `_REPO_SNIPPET_SOFT_CAP_BYTES`. Delivered in full regardless
    (module docstring: "silently truncating a repo's doctrine would be
    worse than the bloat"); this banner only makes the growth visible.
    Extracted as a pure function for the same reason as
    `_compose_missing_snippet_banner` above."""
    return (
        f"assert-em-role: {rel_path} is {byte_len}B, over the "
        f"{_REPO_SNIPPET_SOFT_CAP_BYTES}B soft cap. Delivered anyway -- "
        f"consider a wiki for content this large.\n\n"
    )


def main(argv: list) -> int:
    del argv  # no flags -- this hook takes no arguments

    payload = {}
    try:
        raw = _read_stdin(2.0)
        if raw:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                payload = parsed
    except Exception:
        pass  # a malformed payload only costs the REPO slot, never the PLUGIN ones

    repo_root = _consumer_repo_root(payload)

    _w("\n")
    for root, rel_path in _EM_SNIPPET_MANIFEST:
        if root == _ROOT_PLUGIN:
            snippet_path = _SNIPPETS_DIR / rel_path
        else:
            if repo_root is None:
                continue  # unresolvable consumer root == no repo entry, silently
            snippet_path = repo_root / rel_path
            # Absence is the common case for the repo slot and must stay
            # silent; only an existing-but-unreadable file is a defect.
            if not snippet_path.exists():
                continue

        try:
            snippet_text = snippet_path.read_text(encoding="utf-8")
        except OSError as exc:
            _w(_compose_missing_snippet_banner(rel_path, snippet_path, exc, root))
            continue  # one missing manifest entry must not swallow the rest

        if root == _ROOT_REPO and len(snippet_text.encode("utf-8")) > _REPO_SNIPPET_SOFT_CAP_BYTES:
            _w(_compose_oversize_repo_banner(rel_path, len(snippet_text.encode("utf-8"))))

        _w(snippet_text)
        _w("\n")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
