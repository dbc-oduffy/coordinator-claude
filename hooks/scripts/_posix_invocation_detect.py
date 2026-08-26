"""Detection predicate: does a text payload prescribe a POSIX-only shell
invocation reaching a coordinator-CLI forwarder?

Purpose: `coordinator/snippets/resolve-coordinator-bin.md` rung 0 rules that
a PowerShell host takes Shape W (the `.cmd` sibling via the call operator),
never Shape A/B's `${VAR:-default}` shell-parameter-expansion form -- rungs
1-3 are POSIX-shell fences unrunnable on a PowerShell-only host without
spawning a bash first (see that snippet's own "Why not bareword" and rung-0
sections). This module is the ONE shared predicate for "does this text carry
that retired shape", imported by both the write-time advisory hook
(`guard-posix-invocation-doctrine-write.py`, warn-only, never blocks) and the
BIG-RED test assertion (`test_no_command_fences_in_doctrine.py`, hard-fails)
so a hook and a test can never disagree about what counts as a violation --
see docs/plans/2026-08-18-retire-posix-invocation-doctrine.md chunk C4's own
brief: "a hook and a test that disagree about what a violation is are worse
than either alone."

Deliberately narrow, not a shell parser. This is a targeted predicate for
ONE shape: a POSIX `${VAR:-...}` parameter expansion (with balanced nested
braces, e.g. `${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/...}`)
whose text reaches a `/bin/<cli>` forwarder suffix within a short trailing
window on the same line. It does not attempt the full H1-H5 fence/tag/
indentation classification machinery `test_no_command_fences_in_doctrine.py`
already owns for the wider "command fence in doctrine" gate -- that
machinery answers "is this a transport payload at all"; this module answers
the narrower, orthogonal question "does this specific text carry the
retired POSIX-expansion-to-forwarder shape", regardless of whether it sits
in a fence, an indented block, or bare prose.
"""

from __future__ import annotations

import re
from typing import NamedTuple

#: Opens on a POSIX shell parameter-expansion-with-default: `${VAR:-`. Only
#: the outer opening is matched here; `_balanced_brace_end` walks forward
#: from the `{` to find the true close, so a nested `${INNER:-...}` default
#: value does not prematurely terminate the outer expansion (the shape
#: `resolve-coordinator-bin.md` itself documents:
#: `${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}`).
_EXPANSION_OPEN_RE = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*:-")

#: A forwarder invocation suffix: `/bin/<cli-name>`. Matched in the text
#: immediately following the expansion's closing brace, within
#: `_TRAILING_WINDOW` characters -- this is what tells a POSIX-shell default
#: expansion used for some unrelated purpose apart from a shape that
#: actually resolves the coordinator settings home down to a CLI forwarder.
_BIN_CLI_RE = re.compile(r"/bin/([A-Za-z0-9_.-]+)")

#: Generous enough to span the `/.coordinator-claude-settings` suffix
#: `resolve-coordinator-bin.md`'s own Shape A/B examples carry between the
#: expansion's close and the `/bin/<cli>` segment, narrow enough that an
#: unrelated `${...}` expansion elsewhere on a long line/paragraph does not
#: spuriously pair with an unrelated `/bin/` mention far downstream.
_TRAILING_WINDOW = 200

#: A Shape W invocation: the PowerShell call operator (`&`) applied to a
#: quoted path ending `\bin\<cli>.cmd` -- `resolve-coordinator-bin.md` rung
#: 0's own documented form, e.g.
#: `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-doc-new.cmd" ...`.
#: The path prefix before `\bin\` varies (`$env:COORDINATOR_SETTINGS_HOME`,
#: `$HOME\.coordinator-claude-settings`, ...) so only the `\bin\<cli>.cmd`
#: suffix inside the quotes is pinned; `<cli>` is captured so a same-CLI
#: pairing (see `_has_nearby_shape_w_sibling`) can be checked structurally,
#: never by matching prose like "PowerShell hosts use Shape W".
_SHAPE_W_RE = re.compile(r'&\s*"[^"\n]*\\bin\\([A-Za-z0-9_.-]+?)\.cmd"')

#: Line-distance window a POSIX invocation is allowed to pair with a
#: same-CLI Shape W sibling before the POSIX hit is treated as unaccompanied
#: (a true violation). `coordinator/commands/install.md`'s 21 correctly-
#: paired invocations sit 5-6 lines from their Shape W sibling (the POSIX
#: form under a ```bash fence, then a "PowerShell host (rung 0):" line, then
#: the Shape W form) -- 8 lines clears that with margin. `skills/percolate/
#: SKILL.md` states Shape W once in prose ("every CLI below takes its `.cmd`
#: sibling...") 12 lines above its `percolate-round` POSIX invocation, and
#: relies on a "per the note above" cross-reference rather than a structural
#: sibling for either of its two POSIX invocations -- 8 lines does not reach
#: that 12-line gap, so both stay flagged as the true positives they are.
_SIBLING_LINE_WINDOW = 8


class PosixInvocationHit(NamedTuple):
    """One matched POSIX-only invocation. `start`/`end` are character
    offsets into the scanned text (half-open range); `text` is the matched
    substring, `cli` is the forwarder basename `/bin/` resolved to (e.g.
    `coordinator-doc-new`)."""

    start: int
    end: int
    text: str
    cli: str


def _balanced_brace_end(text: str, open_idx: int) -> int:
    """Index of the `}` matching the `{` at `text[open_idx]`, tracking
    nested-brace depth so an inner `${...}` default value does not
    prematurely close the outer expansion. Returns -1 if `text[open_idx]`
    is not `{`, or no matching close is found before the end of `text`."""
    if open_idx < 0 or open_idx >= len(text) or text[open_idx] != "{":
        return -1
    depth = 0
    i = open_idx
    n = len(text)
    while i < n:
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _line_of(text: str, offset: int) -> int:
    """1-indexed line number containing character `offset` in `text`."""
    return text.count("\n", 0, offset) + 1


def _shape_w_lines_by_cli(text: str) -> "dict[str, list[int]]":
    """`{cli: [line_no, ...]}` for every Shape W invocation in `text`,
    keyed by the CLI basename it names -- used to check whether a POSIX
    hit for that same CLI sits within `_SIBLING_LINE_WINDOW` lines of one."""
    by_cli: "dict[str, list[int]]" = {}
    for m in _SHAPE_W_RE.finditer(text):
        by_cli.setdefault(m.group(1), []).append(_line_of(text, m.start()))
    return by_cli


def _has_nearby_shape_w_sibling(
    hit_line: int, cli: str, shape_w_lines: "dict[str, list[int]]"
) -> bool:
    """True if `text` carries a Shape W invocation of the SAME `cli` within
    `_SIBLING_LINE_WINDOW` lines of `hit_line`. Matching on CLI name means a
    Shape W block for one CLI can never launder an unrelated POSIX
    invocation for a different CLI (see `POSIX_SCOPE_TREES`' percolate-gate
    case, which has no Shape W sibling naming it and stays flagged
    regardless of window)."""
    return any(
        abs(line - hit_line) <= _SIBLING_LINE_WINDOW
        for line in shape_w_lines.get(cli, ())
    )


def find_posix_forwarder_invocations(text: str) -> "list[PosixInvocationHit]":
    """Every POSIX-only `${VAR:-...}` shell expansion in `text` whose text
    reaches a `/bin/<cli>` forwarder suffix within `_TRAILING_WINDOW` chars
    of the expansion's close -- Shape A/B (POSIX-host rungs 1-2), the shape
    `resolve-coordinator-bin.md` rung 0 now ranks below Shape W on any
    PowerShell host. Returns `[]` for text carrying no such pairing (an
    ordinary `${VAR:-default}` used for something other than resolving a
    settings-home CLI forwarder is not flagged -- only the specific
    expansion-then-forwarder pairing is).

    A nested inner expansion (e.g. `${CLAUDE_HOME:-$HOME}` inside the outer
    `${COORDINATOR_SETTINGS_HOME:-...}` default value) also independently
    satisfies the regex and would otherwise pair with the SAME downstream
    `/bin/<cli>` suffix, double-reporting one invocation as two hits. A hit
    whose opening `$` falls strictly inside an already-accepted hit's span
    is dropped -- only the outermost expansion for a given forwarder
    pairing is reported.

    SIBLING-AWARE: rungs 1-3 remain legitimate, REQUIRED POSIX-host forms
    (macOS/Linux are first-class, P0) -- the doctrine this predicate
    enforces is "no POSIX-ONLY invocation", not "no POSIX invocation at
    all". A POSIX hit is dropped (not reported) when `text` also carries a
    Shape W invocation of the SAME `cli` within `_SIBLING_LINE_WINDOW`
    lines -- the documented rung-ladder pattern of showing both forms side
    by side (see `coordinator/commands/install.md`, which pairs all 21 of
    its POSIX invocations with an adjacent Shape W block and must report
    zero hits). A prose cross-reference ("PowerShell hosts use Shape W per
    the note above") does NOT satisfy this -- only a structural, same-CLI
    Shape W invocation within the window does; see
    `_has_nearby_shape_w_sibling`."""
    shape_w_lines = _shape_w_lines_by_cli(text)
    raw: "list[PosixInvocationHit]" = []
    for m in _EXPANSION_OPEN_RE.finditer(text):
        open_idx = m.start() + 1  # index of the '{' immediately after '$'
        close_idx = _balanced_brace_end(text, open_idx)
        if close_idx == -1:
            continue
        window_start = close_idx + 1
        window_end = min(len(text), window_start + _TRAILING_WINDOW)
        bin_match = _BIN_CLI_RE.search(text, window_start, window_end)
        if bin_match is None:
            continue
        cli = bin_match.group(1)
        if _has_nearby_shape_w_sibling(_line_of(text, m.start()), cli, shape_w_lines):
            continue
        end = bin_match.end()
        raw.append(
            PosixInvocationHit(
                start=m.start(),
                end=end,
                text=text[m.start() : end],
                cli=bin_match.group(1),
            )
        )
    hits: "list[PosixInvocationHit]" = []
    for hit in raw:
        if any(prior.start < hit.start < prior.end for prior in hits):
            continue
        hits.append(hit)
    return hits


def has_posix_forwarder_invocation(text: str) -> bool:
    """True if `text` carries at least one hit of
    `find_posix_forwarder_invocations` -- the cheap boolean form the
    write-time advisory hook uses (it only needs to know whether to warn,
    not enumerate every hit)."""
    return bool(find_posix_forwarder_invocations(text))
