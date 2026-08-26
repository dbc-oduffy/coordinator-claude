# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""handoff-loe-summary.py — Read helper: compute the /handoff Session Ledger
row in one call.

Naked-Python port of the "Get LoE metrics" bash block in
coordinator/skills/handoff/SKILL.md § Session Ledger (2026-07 debash
campaign, chunk HO-2). That block invoked `coordinator-session-loe.py
--format json`, scraped four fields back out of the JSON via
`grep -o`/`sed`/`tr` (a round-trip through text the engine already emits as
structured JSON), pulled the last 20 commit short SHAs via `git log`, and
stamped a UTC timestamp — all so the EM could hand-fill the Session Ledger
placeholder cells. This CLI does the same computation directly against
coordinator-session-loe.py's Python functions (no JSON-then-grep, no
subprocess round-trip for the LoE leg).

Purpose UPDATED 2026-07-25 (format-divergence fix): `coordinator-doc-new`'s
handoff scaffold stopped emitting a `| Field | Value |` table and now emits
a one-line-append slot (`YYYY-MM-DD | <sid6> | <tshirt> | <Nd / No> |
<summary>`) — see `coordinator_core.session_ledger.aggregate_chain_loe`'s
`_ONELINE_RE`/`format_oneline_row`. This script's OLD docstring (retained
above for provenance) described hand-filling Field/Value cells; that slot
no longer exists in the scaffold (3 archived handoffs still use it, ~30+
live handoffs use the one-liner), so this CLI now emits the ready-to-
paste/append one-line row directly (via `format_oneline_row`, the single
place that assembles this grammar — see that function's docstring) instead
of leaving the EM to hand-map JSON fields into a table that isn't there.
The full JSON object (session_id, agent_dispatches, opus_dispatches,
em_tokens, tshirt, commits, created) is UNCHANGED and still emitted by
default — `em_tokens` and `commits` have no slot in the one-line grammar,
so they are NOT silently dropped, only left out of the pasteable row; use
`--row-only` when only the paste-ready line itself is wanted.

Session-id resolution mirrors the bash block exactly: the 4-tier resolver
(`coordinator_core.session.core.resolve_session_id`, COORDINATOR_SESSION_ID
-> CLAUDE_SESSION_ID -> CLAUDE_CODE_SESSION_ID -> engine sentinel), falling
back to the literal string "unknown" the bash block used
(`SID="${SID:-unknown}"`) when nothing resolves.

Spec backlink: archive/specs/2026-05/2026-05-19-completion-log-phase2-loe-and-handoff-ledger.md
  § Chunk 4 (plan lines 162-188) — original Session Ledger bash block.
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md (Wave HO-2).

Concurrency posture:  read-only against per-session sentinel files (via the
  co-located coordinator-session-loe.py) and `git log` — safe under
  concurrent reads, no locking needed.
Idempotency posture:  deterministic given a fixed session_id and fixed
  dispatched-agents.txt/git history; re-running yields identical LoE and
  commit fields (only `created` legitimately varies run-to-run).
Resume strategy:      stateless — this CLI holds no state of its own.

Negative-spec: does NOT parse coordinator-session-loe.py's stdout as text —
  it loads that script as a module (hyphenated filename precludes a dotted
  import, hence importlib.util.spec_from_file_location) and calls its
  functions directly, keeping the LoE computation single-sourced in one
  place rather than re-derived here.
Negative-spec: does NOT hand-format the one-line-append row itself — it
  imports and calls `format_oneline_row` from
  `coordinator_core.session_ledger.aggregate_chain_loe` (best-effort; see
  `_format_oneline_row`), keeping the grammar single-sourced there rather
  than re-derived as a third copy here.
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import os
import subprocess
import sys
from types import ModuleType

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))

_LIB_DIR = os.path.join(_BIN_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root, require_dispatch_engine_on_path  # noqa: E402


def _no_console_kw() -> dict:
    """Lazily resolve claude_klabauter_root onto sys.path, then splat the canonical
    no-console-window kwarg. ``{}`` on any resolution failure (fail-open)."""
    try:
        claude_klabauter_root = require_dispatch_engine_on_path()
        from coordinator_core.win_portability import no_console_creationflags

        return no_console_creationflags()
    except Exception:
        return {}

# Fallback LoE fields, mirroring the bash block's error-handling ladder:
# `LOE=$(... 2>/dev/null || echo '{"agent_dispatches":0,"opus_dispatches":0,
# "em_tokens":null,"tshirt":"XS"}')`. A handoff must never fail to write
# because LoE computation broke, so any failure below degrades to this.
_FALLBACK_LOE = {
    "agent_dispatches": 0,
    "opus_dispatches": 0,
    "em_tokens": None,
    "tshirt": "XS",
}


def _load_session_loe_module() -> ModuleType:
    """Load the co-located coordinator-session-loe.py by file path (its
    hyphenated filename precludes `import coordinator_session_loe`) and
    return the loaded module object, giving access to its
    _resolve_git_root/_count_session/_sum_children/_resolve_em_tokens/
    _compute_tshirt helpers without a subprocess spawn."""
    path = os.path.join(_BIN_DIR, "coordinator-session-loe.py")
    spec = importlib.util.spec_from_file_location("coordinator_session_loe", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module spec for {path!r}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _resolve_session_id_via_engine(claude_klabauter_root: str) -> str:
    """Mirrors the bash block's
    `PYTHONPATH="$_handoff_claude_klabauter_root" python3 -c "from
    coordinator_core.session.core import resolve_session_id; ..."` line, as
    a plain in-process call rather than a child `python3 -c` spawn."""
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.session.core import resolve_session_id

    return resolve_session_id() or ""


def _loe_metrics(session_id: str, include_children: bool) -> dict:
    """Compute agent_dispatches/opus_dispatches/em_tokens/tshirt for
    session_id, falling back to _FALLBACK_LOE on any failure (no repo, no
    coordinator-session-loe.py, or any exception raised while computing) —
    the same "compute-or-fall-back-to-XS" contract the bash block's
    `|| echo '{...}'` implemented."""
    try:
        mod = _load_session_loe_module()
        git_root = mod._resolve_git_root()
        if git_root is None:
            return dict(_FALLBACK_LOE)
        sessions_base = os.path.join(git_root, ".git", "coordinator-sessions")
        agent_dispatches, opus_dispatches = mod._count_session(sessions_base, session_id)
        if include_children:
            agent_dispatches, opus_dispatches = mod._sum_children(
                sessions_base, session_id, agent_dispatches, opus_dispatches
            )
        em_tokens = mod._resolve_em_tokens()
        tshirt = mod._compute_tshirt(agent_dispatches, opus_dispatches, em_tokens)
        return {
            "agent_dispatches": agent_dispatches if agent_dispatches is not None else 0,
            "opus_dispatches": opus_dispatches if opus_dispatches is not None else 0,
            "em_tokens": em_tokens,
            "tshirt": tshirt,
        }
    except Exception:
        return dict(_FALLBACK_LOE)


def _recent_commits(limit: int) -> str:
    """Best-effort last-`limit` commit short SHAs, space-separated. Mirrors
    `git log --oneline -N --format="%h" | tr '\\n' ' ' | sed 's/ $//'`;
    returns "" (never raises) on any git failure — no repo, no commits yet,
    or git itself missing."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", f"-{limit}", "--format=%h"],
            capture_output=True,
            text=True,
            **_no_console_kw(),
        )
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return " ".join(result.stdout.split())


def _utc_now_iso() -> str:
    """Mirrors `date -u +"%Y-%m-%dT%H:%M:%SZ" || date +"%Y-%m-%dT%H:%M:%SZ"`
    — Python's UTC clock needs no BSD-vs-GNU `date` fallback ladder."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_SUMMARY_PLACEHOLDER = "<one-line summary — fill in>"


def _format_oneline_row(
    claude_klabauter_root: str | None,
    session_id: str,
    tshirt: str,
    agent_dispatches: int,
    opus_dispatches: int,
    created: str,
) -> str | None:
    """Best-effort emit of the ready-to-paste Session Ledger row via
    `coordinator_core.session_ledger.aggregate_chain_loe.format_oneline_row`
    (the single authoritative formatter — see that function's docstring;
    this CLI does NOT hand-format a second copy of the grammar).

    Returns `None` (never raises) if `claude_klabauter_root` is unresolved or the
    formatter module isn't importable — mirrors `_loe_metrics`'s "never
    fail a handoff over a convenience field" fallback philosophy. The
    caller decides how to surface a `None` (the default JSON output emits
    it as `null`; `--row-only` mode treats it as a hard usage error, since
    printing nothing at all would be silently unhelpful there).
    """
    if not claude_klabauter_root:
        return None
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    try:
        from coordinator_core.session_ledger.aggregate_chain_loe import format_oneline_row
    except ImportError:
        return None
    return format_oneline_row(
        created=created,
        session_id=session_id,
        tshirt=tshirt,
        agent_dispatches=agent_dispatches,
        opus_dispatches=opus_dispatches,
        summary=_SUMMARY_PLACEHOLDER,
    )


_USAGE = """Usage: handoff-loe-summary.py [OPTIONS]

Computes the /handoff Session Ledger fields in one call: LoE metrics
(agent_dispatches, opus_dispatches, em_tokens, tshirt), the resolved
session id, recent commit SHAs, and a UTC creation timestamp. Emits one
JSON object on stdout, including a ready-to-paste `oneline_row` field
matching the `coordinator-doc-new` scaffold's one-line-append grammar
(`YYYY-MM-DD | <sid6> | <tshirt> | <Nd / No> | <summary>`; the summary
cell is always the literal placeholder below — prose is the EM's to fill
in, not computable here).

Options:
  --session-id <sid>      Session UUID (default: resolve via the 4-tier
                           chain — COORDINATOR_SESSION_ID -> CLAUDE_SESSION_ID
                           -> CLAUDE_CODE_SESSION_ID -> engine sentinel;
                           falls back to the literal "unknown" if nothing
                           resolves)
  --include-children      Sum descendant sessions into the LoE counts
                           (chain-aggregation flavor)
  --commit-limit <N>      Number of recent commit SHAs to include
                           (default: 20)
  --row-only              Print ONLY the ready-to-paste one-line row (no
                           JSON wrapper) — for direct `>> handoff.md`
                           redirection. Exits 1 if the row can't be
                           computed (the engine root unresolved or the
                           formatter module isn't importable).
  -h, --help               Show this help

Output JSON example:
  {"session_id": "...", "agent_dispatches": 26, "opus_dispatches": 4,
   "em_tokens": null, "tshirt": "L", "commits": "abc1234 def5678 ...",
   "created": "2026-07-23T10:00:00Z",
   "oneline_row": "2026-07-23 | abc123 | L | 26d / 4o | <one-line summary — fill in>"}

Output --row-only example:
  2026-07-23 | abc123 | L | 26d / 4o | <one-line summary — fill in>
"""


def main(argv: list[str]) -> int:
    args = argv[1:]
    session_id_arg: str | None = None
    include_children = False
    commit_limit = 20
    row_only = False

    i = 0
    while i < len(args):
        tok = args[i]
        if tok == "--session-id":
            if i + 1 >= len(args):
                print("handoff-loe-summary: --session-id requires a value", file=sys.stderr)
                return 1
            session_id_arg = args[i + 1]
            i += 2
        elif tok == "--include-children":
            include_children = True
            i += 1
        elif tok == "--commit-limit":
            if i + 1 >= len(args):
                print("handoff-loe-summary: --commit-limit requires a value", file=sys.stderr)
                return 1
            try:
                commit_limit = int(args[i + 1])
            except ValueError:
                print(
                    f"handoff-loe-summary: invalid --commit-limit value {args[i + 1]!r}",
                    file=sys.stderr,
                )
                return 1
            i += 2
        elif tok == "--row-only":
            row_only = True
            i += 1
        elif tok in ("-h", "--help"):
            print(_USAGE, end="")
            return 0
        else:
            print(f"handoff-loe-summary: unknown argument {tok!r}", file=sys.stderr)
            return 1

    # Resolved once, unconditionally, non-fatally — needed both for the
    # session-id auto-resolution ladder below (only when no explicit
    # --session-id) and for `_format_oneline_row`'s dotted import of
    # aggregate_chain_loe (needed regardless of how session_id was
    # obtained). A failure here degrades both to their own fallbacks
    # (empty session_id -> "unknown"; oneline_row -> None) rather than
    # aborting the whole command.
    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
    except RuntimeError:
        claude_klabauter_root = None

    session_id = session_id_arg
    if not session_id:
        if claude_klabauter_root is not None:
            try:
                session_id = _resolve_session_id_via_engine(claude_klabauter_root)
            except (RuntimeError, ImportError):
                session_id = ""
        else:
            session_id = ""
    session_id = session_id or "unknown"

    loe = _loe_metrics(session_id, include_children)
    commits = _recent_commits(commit_limit)
    created = _utc_now_iso()

    oneline_row = _format_oneline_row(
        claude_klabauter_root, session_id, loe["tshirt"], loe["agent_dispatches"], loe["opus_dispatches"], created
    )

    if row_only:
        if oneline_row is None:
            print(
                "handoff-loe-summary: --row-only requires "
                "coordinator_core.session_ledger.aggregate_chain_loe.format_oneline_row "
                "to be importable, and it isn't (the engine root unresolved or the module "
                "failed to import)",
                file=sys.stderr,
            )
            return 1
        print(oneline_row)
        return 0

    print(
        json.dumps(
            {
                "session_id": session_id,
                "agent_dispatches": loe["agent_dispatches"],
                "opus_dispatches": loe["opus_dispatches"],
                "em_tokens": loe["em_tokens"],
                "tshirt": loe["tshirt"],
                "commits": commits,
                "created": created,
                "oneline_row": oneline_row,
            },
            separators=(", ", ": "),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
