# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""coordinator-session-loe.py — Read helper: compute LoE (Level of Effort)
metrics for a coordinator session and emit a t-shirt size.

Port of: coordinator-session-loe.sh (DoE b644d5a9, 2026-07-22).
Reads three signals for a given session (total agent
dispatches, Opus-model dispatches, EM token consumption) and applies the
threshold table below (mirrors coordinator/config/loe-thresholds.yaml) to
produce a t-shirt size. Consumed by /workstream-complete, /handoff, and
chain-aggregation.

Spec backlink: docs/plans/2026-05-19-completion-log-phase2-loe-and-handoff-ledger.md
  § Chunk 2 — coordinator-session-loe.sh read helper.
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md (Wave E3-c)

Session-id resolution: tiers 1-3 only (COORDINATOR_SESSION_ID ->
CLAUDE_SESSION_ID -> CLAUDE_CODE_SESSION_ID), mirroring the repoint pattern
established by bin/append-plan-session.py. Tier 4 (the
.git/coordinator-sessions/.current-session-id sentinel + concurrent-session
ambiguity guard, owned by coordinator-session.sh) is intentionally NOT ported
here per the frontier note for this chunk — do NOT edit
coordinator/lib/coordinator-session.sh (Wave S owns it). Modern Claude Code
(>= ~2.1.150) always sets CLAUDE_CODE_SESSION_ID, so this covers the
steady-state case; every shipping caller of this script also passes
--session-id explicitly, so the sentinel fallback is not load-bearing for any
known call site.

Concurrency posture:  read-only against per-session sentinel files — safe
  under concurrent reads; single-writer per session_id (the hook that appends
  dispatched-agents.txt). No locking needed on the read side.
Idempotency posture:  deterministic given a fixed session_id and fixed
  dispatched-agents.txt contents; same input -> same output every invocation.
Resume strategy:      stateless — re-running on the same session yields
  identical output as long as the sentinel files haven't changed.

Negative-spec: does NOT source coordinator-session.sh and does NOT spawn a
  shell (repo-root resolution runs via repo_identity.resolve_checked_repo_root(),
  which shells out to `git rev-parse` via subprocess.run() with an argv list).
"""
from __future__ import annotations

import json
import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from repo_identity import resolve_checked_repo_root  # noqa: E402

_SESSION_ID_ENV_TIERS = (
    "COORDINATOR_SESSION_ID",
    "CLAUDE_SESSION_ID",
    "CLAUDE_CODE_SESSION_ID",
)

# Format: (tier, ad_threshold, od_threshold, token_threshold)
# Ordered from HIGHEST to LOWEST so we return on first match.
# Mirrors config/loe-thresholds.yaml exactly (dogfood-fix 2026-05-19: S.od
# raised from 0 to 1, M.od 1->2, to keep XS structurally reachable under
# any-criterion semantics).
_TSHIRT_TABLE = (
    ("XL", 50, 6, 1_000_000),
    ("L", 30, 3, 600_000),
    ("M", 15, 2, 300_000),
    ("S", 5, 1, 150_000),
    ("XS", 0, 0, 50_000),
)

_USAGE = """Usage: coordinator-session-loe.py [OPTIONS]

Options:
  --session-id <sid>           Session UUID (default: resolve from env)
  --format <json|yaml-frontmatter|tsv>
                               Output format (default: json)
  --include-children           Sum descendant sessions (for chain aggregation)
  -h, --help                   Show this help

Output JSON example:
  {"agent_dispatches": 26, "opus_dispatches": 4, "em_tokens": 482000, "tshirt": "L"}

yaml-frontmatter example:
  loe:
    agent_dispatches: 26
    opus_dispatches: 4
    em_tokens: null
    tshirt: "L"
"""


def _resolve_session_id() -> str:
    for var in _SESSION_ID_ENV_TIERS:
        val = os.environ.get(var, "")
        if val:
            return val
    return ""


def _resolve_git_root() -> str | None:
    """Resolve the repo root via the checked resolver (repo_identity).

    READER classification (DR-277 / plan C5): MISMATCH is advisory only --
    warn to stderr and proceed with the resolved root. UNRESOLVED never
    refuses (AC4). Returns None only when no root at all resolves (caller
    maps this to "not inside a git repo", exit 1 -- matching pre-existing
    behavior).
    """
    root, verdict = resolve_checked_repo_root(explicit_root=None)
    if verdict["verdict"] == "MISMATCH":
        print(verdict["message"], file=sys.stderr)
    return root


def _count_session(sessions_base: str, sid: str) -> tuple[int | None, int | None]:
    """Returns (agent_dispatches, opus_dispatches); None for each when the
    dispatched-agents.txt file is absent (null-honesty, C3/AC4). A present but
    empty file yields (0, 0)."""
    agents_file = os.path.join(sessions_base, sid, "dispatched-agents.txt")
    if not os.path.isfile(agents_file):
        return None, None

    try:
        with open(agents_file, "rb") as fh:
            raw = fh.read()
    except OSError:
        return 0, 0

    # ad mirrors `wc -l` (counts '\n' bytes; a final line lacking a trailing
    # newline is not counted — matches GNU/BSD wc -l exactly).
    ad = raw.count(b"\n")

    # od mirrors `cut -f2 | grep -ci opus` over the newline-terminated lines
    # only (the same population wc -l counted above): column 2 (model field)
    # substring-matched case-insensitively against "opus". A legacy
    # single-column line has no tab, so cols[1] is absent and the whole line
    # (which never contains "opus" for a bare agentId) is checked instead —
    # same behavior as the bash oracle's no-tab-no-match fallthrough.
    od = 0
    for raw_line in raw.split(b"\n")[:ad]:
        cols = raw_line.split(b"\t")
        model_field = cols[1] if len(cols) >= 2 else raw_line
        if b"opus" in model_field.lower():
            od += 1

    return ad, od


def _sum_children(sessions_base: str, session_id: str, ad: int | None, od: int | None) -> tuple[int | None, int | None]:
    agents_dir = os.path.join(sessions_base, ".agents")
    if not os.path.isdir(agents_dir):
        return ad, od

    for dirpath, _dirnames, filenames in os.walk(agents_dir):
        if "em-session-id.txt" not in filenames:
            continue
        bp_file = os.path.join(dirpath, "em-session-id.txt")
        try:
            with open(bp_file, "r", encoding="utf-8", errors="replace") as fh:
                child_em_sid = fh.read().strip()
        except OSError:
            continue
        if not child_em_sid or child_em_sid == session_id:
            continue
        child_dir = os.path.join(sessions_base, child_em_sid)
        if not os.path.isdir(child_dir):
            continue
        if not os.path.isfile(os.path.join(child_dir, "dispatched-agents.txt")):
            continue
        c_ad, c_od = _count_session(sessions_base, child_em_sid)
        c_ad = c_ad or 0
        c_od = c_od or 0
        ad = (ad or 0) + c_ad
        od = (od or 0) + c_od

    return ad, od


def _resolve_em_tokens() -> int | None:
    input_tok = os.environ.get("CLAUDE_SESSION_INPUT_TOKENS", "")
    output_tok = os.environ.get("CLAUDE_SESSION_OUTPUT_TOKENS", "")
    if not (input_tok and output_tok):
        return None
    if not (input_tok.isdigit() and output_tok.isdigit()):
        return None
    return int(input_tok) + int(output_tok)


def _compute_tshirt(ad: int | None, od: int | None, em_tokens: int | None) -> str:
    for tier, ad_thresh, od_thresh, tok_thresh in _TSHIRT_TABLE:
        qualifies = False
        if ad is not None and ad >= ad_thresh:
            qualifies = True
        if od is not None and od >= od_thresh:
            qualifies = True
        if em_tokens is not None and em_tokens >= tok_thresh:
            qualifies = True
        if qualifies:
            return tier
    return "null"


def main(argv: list[str]) -> int:
    fmt = "json"
    include_children = False
    session_id = ""

    args = argv[1:]
    i = 0
    while i < len(args):
        tok = args[i]
        if tok == "--session-id":
            if i + 1 >= len(args):
                print("Unknown argument: --session-id requires a value", file=sys.stderr)
                return 1
            session_id = args[i + 1]
            i += 2
        elif tok == "--format":
            if i + 1 >= len(args):
                print("Unknown argument: --format requires a value", file=sys.stderr)
                return 1
            fmt = args[i + 1]
            i += 2
        elif tok == "--include-children":
            include_children = True
            i += 1
        elif tok in ("-h", "--help"):
            print(_USAGE, end="")
            return 0
        else:
            print(f"Unknown argument: {tok}", file=sys.stderr)
            return 1

    git_root = _resolve_git_root()
    if git_root is None:
        print("Error: not inside a git repo", file=sys.stderr)
        return 1
    sessions_base = os.path.join(git_root, ".git", "coordinator-sessions")

    if not session_id:
        session_id = _resolve_session_id()
    if not session_id:
        print(
            "Error: no --session-id, CLAUDE_CODE_SESSION_ID unset, and no "
            "resolvable session id. Escape hatch: export CLAUDE_SESSION_ID=<harness-id>",
            file=sys.stderr,
        )
        return 1

    agent_dispatches, opus_dispatches = _count_session(sessions_base, session_id)

    if include_children:
        agent_dispatches, opus_dispatches = _sum_children(
            sessions_base, session_id, agent_dispatches, opus_dispatches
        )

    em_tokens = _resolve_em_tokens()
    tshirt = _compute_tshirt(agent_dispatches, opus_dispatches, em_tokens)

    ad_out = agent_dispatches if agent_dispatches is not None else None
    od_out = opus_dispatches if opus_dispatches is not None else None

    if fmt == "json":
        print(
            json.dumps(
                {
                    "agent_dispatches": ad_out,
                    "opus_dispatches": od_out,
                    "em_tokens": em_tokens,
                    "tshirt": tshirt,
                },
                separators=(", ", ": "),
            )
        )
    elif fmt == "yaml-frontmatter":
        print("loe:")
        print(f"  agent_dispatches: {ad_out if ad_out is not None else 'null'}")
        print(f"  opus_dispatches: {od_out if od_out is not None else 'null'}")
        print(f"  em_tokens: {em_tokens if em_tokens is not None else 'null'}")
        print(f'  tshirt: "{tshirt}"')
    elif fmt == "tsv":
        ad_s = str(ad_out) if ad_out is not None else "null"
        od_s = str(od_out) if od_out is not None else "null"
        tok_s = str(em_tokens) if em_tokens is not None else "null"
        print(f"{session_id}\t{ad_s}\t{od_s}\t{tok_s}\t{tshirt}")
    else:
        print(f"Error: unknown format '{fmt}'. Use: json | yaml-frontmatter | tsv", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
