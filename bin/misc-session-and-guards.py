"""misc-session-and-guards.py — small-guard-and-resolver grab-bag, ported off
DoE-claude instruction-file bash fences (M3 chunk C-MISC).

Subcommands (argv[1] selects):
    claim-classify
        Reads captured `session-claim-cli claim-plan` combined output on
        stdin, classifies it as `peer-contention` (stderr names a live
        holder) vs `infra-error` (any other non-zero), echoes the STOP
        banner + raw output to stderr, prints the classification to
        stdout, and always exits 1 — the caller (execute-plan's Phase 1.5
        Step 0) treats a claim rc!=0 as fail-loud either way; this
        subcommand only tells the EM WHICH kind of failure it is so it
        reconciles with a peer instead of mis-reporting an infra error as
        phantom contention.
        Port source: skills/execute-plan/SKILL.md Phase 1.5 Step 0 (the
        "held by session" stderr-grep branching described in prose next to
        the claim-plan invocation).

    rag-freshness-gate [--project-root PATH] [--task TEXT]
                        [--focus-files TEXT]
        Calls the co-located check-rag-state.py; if its verdict isn't
        "fresh", calls the co-located generate-repomap.py (forwarding the
        three optional args) when present, else prints a skip notice to
        stderr. Mirrors enrich-and-review/SKILL.md Phase 3's task-scoped
        repomap gate verbatim (RAG_STATE check + generate-repomap.py
        existence guard).
        Port source: skills/enrich-and-review/SKILL.md Phase 3.

    rag-staleness-survey
        Resolves the project-rag MCP server's CLI path and project root
        from ~/.claude.json (mcpServers.project-rag.args — first arg
        ending .py/cli is the CLI, the last arg is the project root), then
        invokes `<cli> staleness-survey --project-root <root> --json` and
        prints a one-line freshness nudge when verdict != "current".
        Silently no-ops (exit 0, no output) when either path can't be
        resolved or the verdict is already "current" — matches the
        source's "skip silently" contract.
        Port source: skills/workstream-start/SKILL.md § Project-RAG
        subsystem context (Freshness nudge).

    autonomous-sentinel enable --mode {mise-en-place|autonomous}
    autonomous-sentinel disable
        Writes (enable) or removes (disable) the /autonomous sentinel (see
        coordinator_core.session.autonomous_sentinel.sentinel_path —
        platform-resolved, NOT a hardcoded /tmp path) the context-pressure
        hook reads, keyed by
        coordinator_core.session.core.resolve_session_id() — the same
        resolver both commands/mise-en-place.md Phase 5 and
        commands/autonomous.md use (a bare ${SESSION_ID} is unset in slash
        command bash and previously wrote a silently-mismatched
        empty-suffix path). `enable` fails loud (exit 1) when the session
        id can't be resolved, rather than writing an empty-suffix
        sentinel. `disable` is `rm -f` semantics (idempotent, no error on
        a missing file).
        Port source: commands/mise-en-place.md Phase 5 (Signal autonomous
        mode) and commands/autonomous.md § Enable/Disable — byte-identical
        logic in both files, ported here once.

Exit codes: each subcommand documents its own contract above; there is no
shared transport-failure exit code (no coordinator_core import is required
for claim-classify or rag-freshness-gate — those are pure stdlib. The
autonomous-sentinel subcommand imports coordinator_core.session.core and
exits 3 on an unresolvable engine root / import failure, matching the
archive-stamp-cli / check-rag-state.py trampoline convention).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_BIN_DIR = Path(__file__).resolve().parent
_LIB_DIR = _BIN_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

GENERATES = []  # autonomous-sentinel writes only to the platform tempdir (autonomous_sentinel.sentinel_path); other subcommands only print/shell out

_TRANSPORT_FAIL = 3

# Windows console-subprocess discipline: every subprocess.run() below spawns
# a console-subsystem child (python.exe) — pass no_console_creationflags()
# (a no-op on non-Windows) so a headless Bash-tool-parented invocation never
# flashes a focus-stealing console window.


# ---------------------------------------------------------------------------
# claim-classify
# ---------------------------------------------------------------------------

_PEER_CONTENTION_MARKER = "held by session"


def classify_claim_error(output_text: str) -> str:
    """Classify a non-zero `session-claim-cli claim-plan` result.

    Returns "peer-contention" when stderr names a live holder (the
    session-claim-cli convention is to include the substring "held by
    session" in that case); otherwise "infra-error" (unresolvable session
    id, git-root error, or any other transport failure).
    """
    return "peer-contention" if _PEER_CONTENTION_MARKER in output_text else "infra-error"


def _cmd_claim_classify(argv: list[str]) -> int:
    del argv  # no flags — reads stdin
    output_text = sys.stdin.read()
    verdict = classify_claim_error(output_text)
    print("STOP: plan claim error — execute-plan halted.", file=sys.stderr)
    print(output_text, file=sys.stderr, end="" if output_text.endswith("\n") else "\n")
    print(verdict)
    # Source contract: rc!=0 on the claim call is ALWAYS fail-loud (exit 1)
    # regardless of which classification fires — the classification only
    # changes what the EM does next (reconcile-with-peer vs surface-infra-
    # failure), never whether execute-plan halts here.
    return 1


# ---------------------------------------------------------------------------
# rag-freshness-gate
# ---------------------------------------------------------------------------


def _parse_kv_flags(argv: list[str], flags: tuple[str, ...]) -> dict[str, str]:
    """Order-independent `--flag value` scan (mirrors archive-stamp-cli's
    --sha convention) restricted to the given flag names."""
    out: dict[str, str] = {}
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok in flags:
            if i + 1 >= len(argv):
                raise ValueError(f"{tok} requires a value")
            out[tok.lstrip("-")] = argv[i + 1]
            i += 2
        else:
            i += 1
    return out


def _cmd_rag_freshness_gate(argv: list[str]) -> int:
    try:
        opts = _parse_kv_flags(argv, ("--project-root", "--task", "--focus-files"))
    except ValueError as exc:
        print(f"misc-session-and-guards.py rag-freshness-gate: {exc}", file=sys.stderr)
        return 2

    check_rag_state = _BIN_DIR / "check-rag-state.py"
    try:
        from cc_invoke import child_env, require_dispatch_engine_on_path  # noqa: E402 (path injected at module top)
        from coordinator_core.win_portability import no_console_creationflags, no_console_passthrough_kwargs

        proc = subprocess.run(
            [sys.executable, str(check_rag_state)],
            capture_output=True,
            text=True,
            check=False,
            env=child_env(),
            **no_console_creationflags(),
        )
        rag_state = proc.stdout.strip() if proc.returncode == 0 else "unknown"
    except OSError:
        rag_state = "unknown"
    if not rag_state:
        rag_state = "unknown"

    if rag_state == "fresh":
        return 0

    generate_repomap = _BIN_DIR / "generate-repomap.py"
    if not generate_repomap.is_file():
        print(
            f"[coordinator] generate-repomap.py unresolvable at {generate_repomap} "
            "(claude-klabauter sibling resolved but file missing on disk) — "
            "task-scoped repomap skipped",
            file=sys.stderr,
        )
        return 0

    cmd = [sys.executable, str(generate_repomap)]
    if "project-root" in opts:
        cmd += ["--project-root", opts["project-root"]]
    if "task" in opts:
        cmd += ["--task", opts["task"]]
    if "focus-files" in opts:
        cmd += ["--focus-files", opts["focus-files"]]
    from coordinator_core.win_portability import no_console_creationflags, no_console_passthrough_kwargs

    return subprocess.run(cmd, check=False, **no_console_passthrough_kwargs()).returncode


# ---------------------------------------------------------------------------
# rag-staleness-survey
# ---------------------------------------------------------------------------


def _resolve_project_rag_cli_and_root() -> tuple[str | None, str | None]:
    """Mirror the `~/.claude.json` MCP-args resolution used by
    workstream-start/SKILL.md's Freshness nudge inline python3 -c calls."""
    claude_json = Path(os.path.expanduser("~/.claude.json"))
    try:
        with claude_json.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        args = data["mcpServers"]["project-rag"]["args"]
    except (OSError, ValueError, KeyError, TypeError):
        return None, None

    cli = next((a for a in args if a.endswith(".py") or a.endswith("cli")), None)
    root = args[-1] if args else None
    return cli, root


def _cmd_rag_staleness_survey(argv: list[str]) -> int:
    del argv
    cli, root = _resolve_project_rag_cli_and_root()
    if not cli or not root:
        # Source contract: "Skip silently if verdict is current, or if
        # either path could not be resolved from ~/.claude.json."
        return 0

    try:
        from cc_invoke import child_env  # noqa: E402 (path injected at module top)
        from coordinator_core.win_portability import no_console_creationflags, no_console_passthrough_kwargs

        proc = subprocess.run(
            [sys.executable, cli, "staleness-survey", "--project-root", root, "--json"],
            capture_output=True,
            text=True,
            check=False,
            env=child_env(),
            **no_console_creationflags(),
        )
    except OSError:
        return 0
    if proc.returncode != 0 or not proc.stdout.strip():
        return 0

    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        return 0

    verdict = payload.get("verdict")
    if not verdict or verdict == "current":
        return 0

    age = payload.get("age", "an unknown time ago")
    recommendation = payload.get("recommendation_command", payload.get("recommendation", ""))
    print(f"Project-RAG last scanned {age}. Verdict: {verdict}. Recommend: {recommendation}.")
    return 0


# ---------------------------------------------------------------------------
# autonomous-sentinel
# ---------------------------------------------------------------------------


def _import_resolve_session_id():
    from cc_invoke import require_dispatch_engine_on_path  # noqa: WPS433 (deferred, mirrors house style)

    require_dispatch_engine_on_path()
    from coordinator_core.session.core import resolve_session_id

    return resolve_session_id


def _import_sentinel_path():
    from cc_invoke import require_dispatch_engine_on_path  # noqa: WPS433 (deferred, mirrors house style)

    require_dispatch_engine_on_path()
    from coordinator_core.session.autonomous_sentinel import sentinel_path

    return sentinel_path


def _sentinel_path(session_id: str) -> Path:
    return _import_sentinel_path()(session_id)


def _cmd_autonomous_sentinel(argv: list[str]) -> int:
    if not argv:
        print(
            "usage: misc-session-and-guards.py autonomous-sentinel "
            "enable --mode {mise-en-place|autonomous} | disable",
            file=sys.stderr,
        )
        return 2
    action, rest = argv[0], argv[1:]

    try:
        resolve_session_id = _import_resolve_session_id()
    except RuntimeError as exc:
        print(f"misc-session-and-guards.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(
            f"misc-session-and-guards.py: coordinator_core.session.core not importable: {exc}",
            file=sys.stderr,
        )
        return _TRANSPORT_FAIL

    session_id = resolve_session_id() or ""

    if action == "enable":
        try:
            opts = _parse_kv_flags(rest, ("--mode",))
        except ValueError as exc:
            print(f"misc-session-and-guards.py autonomous-sentinel enable: {exc}", file=sys.stderr)
            return 2
        mode = opts.get("mode")
        if not mode:
            print(
                "misc-session-and-guards.py autonomous-sentinel enable: --mode "
                "{mise-en-place|autonomous} is required",
                file=sys.stderr,
            )
            return 2
        if not session_id:
            print(
                "ERROR: cannot resolve current session id (COORDINATOR_SESSION_ID / "
                "CLAUDE_SESSION_ID / CLAUDE_CODE_SESSION_ID / sentinel all empty or "
                "ambiguous) — refusing to write an empty-suffix autonomous sentinel. "
                "Set COORDINATOR_SESSION_ID explicitly, or resolve the ambiguity (see "
                "coordinator_core.session.core.resolve_session_id) and retry.",
                file=sys.stderr,
            )
            return 1
        _sentinel_path(session_id).write_text(f"{mode}\n", encoding="utf-8", newline="\n")
        print(str(_sentinel_path(session_id)))
        return 0

    if action == "disable":
        if not session_id:
            # rm -f semantics: an unresolvable session id means there is no
            # deterministic sentinel to remove — treat as a no-op success
            # rather than fail-loud (mirrors the enable/disable asymmetry
            # in commands/autonomous.md: disable is documented as a plain
            # `rm -f`, never gated on session-id resolution).
            return 0
        _sentinel_path(session_id).unlink(missing_ok=True)
        return 0

    print(f"misc-session-and-guards.py autonomous-sentinel: unknown action {action!r}", file=sys.stderr)
    return 2


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

_SUBCOMMANDS = (
    "claim-classify | rag-freshness-gate | rag-staleness-survey | "
    "autonomous-sentinel"
)


def main(argv: list[str]) -> int:
    if not argv:
        print(f"usage: misc-session-and-guards.py <subcommand> <args...>\n{_SUBCOMMANDS}", file=sys.stderr)
        return 2
    subcmd, rest = argv[0], argv[1:]

    if subcmd in ("--help", "-h", "help"):
        print(f"usage: misc-session-and-guards.py <subcommand> <args...>\n{_SUBCOMMANDS}")
        return 0

    if subcmd == "claim-classify":
        return _cmd_claim_classify(rest)
    if subcmd == "rag-freshness-gate":
        return _cmd_rag_freshness_gate(rest)
    if subcmd == "rag-staleness-survey":
        return _cmd_rag_staleness_survey(rest)
    if subcmd == "autonomous-sentinel":
        return _cmd_autonomous_sentinel(rest)

    print(f"misc-session-and-guards.py: unknown subcommand {subcmd!r}", file=sys.stderr)
    print(f"usage: misc-session-and-guards.py <subcommand> <args...>\n{_SUBCOMMANDS}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
