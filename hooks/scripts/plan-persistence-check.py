#!/usr/bin/env python3
"""PostToolUse(ExitPlanMode) naked-Python port of plan-persistence-check.sh.

Purpose: reads the approved plan from tool_response.plan, copies it to
docs/plans/<YYYY-MM-DD>-<slug>.md in the project repo, stages it with
`git add` (NEVER commits — committing from a hook child process bypasses all
PreToolUse commit-safety matchers). Emits additionalContext pre-filling the
exact scoped commit command and the subagent-review-artifact reminder.

Spec backlink: docs/plans/2026-06-18-plan-persistence-hook-automation.md

Self-contained naked-Python port (W5 straggler): no claude-klabauter op exists for this
hook (checked coordinator_core/hooks + coordinator_core/ops — neither has a
plan-persistence equivalent), so the full decision logic is ported directly
here rather than authored as a thin claude-klabauter-delegating stub.

Activation predicate (graceful cross-repo no-op) — identical to the bash oracle:
  - tool_name must be ExitPlanMode
  - tool_response.plan must be non-empty
  - tool_response.isAgent must NOT be true (a subagent's internal ExitPlanMode
    is not a PM-approved plan; canonicalizing it would pollute docs/plans/)
  - repo root must be discoverable (CLAUDE_PROJECT_DIR or git rev-parse)
  - EITHER docs/plans/ OR docs/README.md must exist at the effective target
    (Never auto-creates docs/plans/ in an arbitrary repo.)

Slug-collision policy (DENY-shaped guard, preserved carefully):
  - Byte-identical → idempotent no-op (no write, no re-stage, no dup README entry)
  - Content differs → emit collision additionalContext, do NOT overwrite, exit 0
    ("COLLISION: ... Hook did NOT overwrite." — this is the one branch where the
    hook actively refuses a write it would otherwise perform; every other guard
    is a silent no-op, this one talks back so the agent doesn't lose the plan.)

Contract (mirrors the bash hook it replaces):
  stdin   — PostToolUse JSON (tool_name, tool_response, cwd, ...)
  stdout  — one hookSpecificOutput JSON envelope on write/idempotent/collision;
            NOTHING on any early-exit guard
  exit 0  — always (advisory/deny is conveyed via stdout content, never exit code)

Graceful degradation — every guard and every filesystem/git failure falls
through to a silent exit 0. A missing repo, missing docs/ convention, or a
failed write must never crash the hook or block the agent's turn.

"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from _message_envelope import compose, render  # noqa: E402

#: Wiki section carrying the relocated idempotent/collision/persisted
#: explanation and the subagent-review-artifact rationale -- see
#: docs/plans/2026-08-02-guard-message-character-cap.md § C6 and this
#: hook's own relocation fragment
#: (state/relocations/guard-message-cap/plan-persistence-check.py.md).
_WIKI_ANCHOR = "coordinator/docs/wiki/guard-message-concision.md#plan-persistence-check"


# ---------------------------------------------------------------------------
# stdin
# ---------------------------------------------------------------------------


def _read_stdin() -> str:
    """Safe stdin read — never blocks when run interactively with no piped input.

    Portable equivalent of the bash oracle's `timeout 2 cat` guard (no `timeout`
    binary dependency, no subprocess spawn): an interactive tty has no piped
    JSON to read, so treat it as empty input, which the guards below turn into
    a silent no-op — identical outcome to the bash guard, no hang either way.
    """
    try:
        if sys.stdin.isatty():
            return ""
        return sys.stdin.read()
    except Exception:
        return ""


def _parse_input(raw: str) -> dict:
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# claude-klabauter root resolution — ladder: explicit env -> <settings-home>/machine-local/
# .claude-klabauter-root pointer file (A-F5, added to match the retired bash oracle's Rung 1.5,
# checked BEFORE the registry) -> <settings-home>/machine-local/registry.local.toml
# (checked before the tracked registry.toml baseline) -> registry.toml ->
# sibling-dir marker, fail to None. See preuse-write-dispatch.py /
# coordinator-reminder.py::_resolve_claude_klabauter_root for full rationale.
# ---------------------------------------------------------------------------


_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import resolve_claude_klabauter_root as _resolve_claude_klabauter_root  # noqa: E402
except Exception:
    # Defensive fallback -- a hook script copied/deployed WITHOUT its
    # sibling _engine_root.py (e.g. an isolated test harness, or a
    # partial deploy) must still fail-open rather than crash on import.
    def _resolve_claude_klabauter_root() -> str | None:
        return None


def _claude_home_dir() -> Path:
    """Resolved ~/.claude directory, matching lib/claude-home/_claude_home.py's
    home_dir() precedence (CLAUDE_HOME -> HOME -> USERPROFILE -> Path.home())
    without importing that module (keeps this hook self-contained).

    (A-F4, P2) Mirrors the canonical home_dir()'s fail-LOUD behavior on a
    set-but-empty or non-absolute CLAUDE_HOME: raises ValueError instead of
    silently falling through to HOME/USERPROFILE. CLAUDE_HOME isolates
    test/CI sandboxes from the real ~/.claude — a broken override must never
    silently route a plan write into the real docs/plans/. The caller
    (main(), via _is_meta_repo()) catches this ValueError and fails OPEN
    THE WHOLE HOOK (returns 0, no action) rather than guessing a home.
    """
    claude_home = os.environ.get("CLAUDE_HOME")
    if claude_home is not None:
        if not claude_home:
            raise ValueError("CLAUDE_HOME is set but empty")
        p = Path(claude_home)
        if not p.is_absolute():
            raise ValueError(f"CLAUDE_HOME must be an absolute path; got {claude_home!r}")
        return p / ".claude"
    home = os.environ.get("HOME")
    if home and Path(home).is_absolute():
        return Path(home) / ".claude"
    userprofile = os.environ.get("USERPROFILE")
    if userprofile and Path(userprofile).is_absolute():
        return Path(userprofile) / ".claude"
    return Path.home() / ".claude"


def _canon(p: Path | str) -> str:
    try:
        return os.path.normcase(os.path.realpath(str(p)))
    except Exception:
        return os.path.normcase(str(p))


def _is_meta_repo(repo_root: str) -> bool:
    return _canon(repo_root) == _canon(_claude_home_dir())


# ---------------------------------------------------------------------------
# git helpers
# ---------------------------------------------------------------------------


def _git_toplevel(cwd: str | None) -> str | None:
    args = ["git"]
    if cwd:
        args += ["-C", cwd]
    args += ["rev-parse", "--show-toplevel"]
    try:
        # Timeout 2s (not 10s): a local `git rev-parse` is a millisecond op.
        # repo_root resolution chains up to 3 of these calls + up to 2
        # _git_add calls; at 10s each the worst-case sequential sum (~50s)
        # blows past this hook's 15s hooks.json timeout. Same reasoning as
        # the runtime-tripwire-em-check 10->3 fix. (A-F1, P1 C8)
        proc = subprocess.run(  # popup-intentional-last-resort
            args, capture_output=True, text=True, timeout=2
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    out = proc.stdout.strip()
    return out or None


def _git_add(repo_root: str, target: Path) -> None:
    try:
        # Timeout 2s — see _git_toplevel's comment (A-F1, P1 C8).
        subprocess.run(  # popup-intentional-last-resort
            ["git", "-C", repo_root, "add", "--", str(target)],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# slug derivation
# ---------------------------------------------------------------------------


def _derive_slug(plan_content: str) -> str:
    h1_line = None
    for line in plan_content.splitlines():
        if line.startswith("# "):
            h1_line = line
            break

    if h1_line is not None:
        h1_text = h1_line[2:]  # strip leading "# " (matches bash ${H1_LINE#\# })
        h1_lower = h1_text.lower()
        # tr -cs 'a-z0-9' '-' : squeeze runs of non-[a-z0-9] into a single hyphen
        h1_slug = re.sub(r"[^a-z0-9]+", "-", h1_lower)
        slug = h1_slug.strip("-")
        slug = slug[:60]
        # Re-trim trailing hyphens after truncation (truncation can re-introduce
        # a trailing hyphen run) — mirrors the bash oracle's explicit re-trim.
        slug = slug.rstrip("-")
        return slug

    # Timestamp fallback (UTC, matches bash `date -u +%H%M%S`).
    return "plan-" + datetime.now(timezone.utc).strftime("%H%M%S")


def _local_day() -> str:
    """Local calendar day, YYYY-MM-DD — matches bash `date -I` (local TZ)."""
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# JSON output helpers
# ---------------------------------------------------------------------------


def _emit(additional_context: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": additional_context,
        }
    }
    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n")


def _compose_idempotent_context(target_name: str, slug: str):
    """Pure composer for the byte-identical re-fire branch. Routes through
    `_message_envelope.compose` (C6, char-cap conversion): the diagnosis is
    the only counted prose, the copy-paste commit command rides in the
    exempt `alternative` slot, and the full subagent-review-artifact
    explanation this message used to carry inline has relocated to
    `_WIKI_ANCHOR` -- see this hook's relocation fragment
    (state/relocations/guard-message-cap/plan-persistence-check.py.md).
    Returns a `Message`, not flattened text -- `main()` calls `render()` at
    the emit call site, mirroring guard-review-integrator-sidecar-intake.py."""
    commit_cmd = (
        f"git add -- docs/plans/{target_name} && "
        f'git commit -m "plan: {slug}" -- docs/plans/{target_name}'
    )
    return compose(
        "PLAN ALREADY PERSISTED (byte-identical) -- commit if not "
        "committed yet, and write subagent review artifacts to disk "
        "before compaction.",
        alternative=commit_cmd,
        anchor=_WIKI_ANCHOR,
    )


def _compose_collision_message(target_path):
    """Pure composer for the slug-collision branch. Routes through
    `compose` -- the colliding path rides in `alternative` (exempt from the
    cap) instead of being interpolated into the counted prose. Returns a
    `Message`; see `_compose_idempotent_context` for the render() split."""
    return compose(
        "Plan-slug collision: a DIFFERENT plan already exists at this "
        "path. Not overwritten -- resolve manually before committing.",
        alternative=str(target_path),
        anchor=_WIKI_ANCHOR,
    )


def _compose_persisted_context(target_name: str, commit_cmd: str):
    """Pure composer for the successful-persist branch. Routes through
    `compose` -- same relocation rationale as `_compose_idempotent_context`.
    Returns a `Message`; see `_compose_idempotent_context` for the render()
    split. `target_name` is unused now the path lives only in
    `commit_cmd`/`alternative` -- kept in the signature for call-site
    parity with the other two composers."""
    return compose(
        "PLAN PERSISTED and staged -- commit now, and write subagent "
        "review artifacts to disk before compaction loses them.",
        alternative=commit_cmd,
        anchor=_WIKI_ANCHOR,
    )


def main() -> int:
    raw = _read_stdin()
    data = _parse_input(raw)

    tool_name = data.get("tool_name") or ""
    if not isinstance(tool_name, str):
        tool_name = str(tool_name)

    tool_response = data.get("tool_response")
    if not isinstance(tool_response, dict):
        tool_response = {}

    plan_content = tool_response.get("plan", "") or ""
    if not isinstance(plan_content, str):
        plan_content = str(plan_content)
    # The bash oracle extracts PLAN_CONTENT via `$(...)` command substitution
    # (`PLAN_CONTENT=$(printf '%s' "$INPUT" | jq -r ...)`), which UNCONDITIONALLY
    # strips ALL trailing newlines from the captured value — a bash quirk, not a
    # deliberate design choice, but one that is byte-visible in the written plan
    # file and must be replicated for oracle parity (a plan ending in \n\n would
    # otherwise round-trip through this hook with a discrepant trailing newline,
    # or — if the plan is newlines-only — the bash guard below treats it as
    # empty where a naive port would not).
    plan_content = plan_content.rstrip("\n")

    is_agent_raw = tool_response.get("isAgent", False)
    is_agent = str(is_agent_raw).lower() == "true"

    cwd = data.get("cwd", "") or ""
    if not isinstance(cwd, str):
        cwd = str(cwd)

    # --- Guard: only act on ExitPlanMode ---
    if tool_name != "ExitPlanMode":
        return 0

    # --- Guard: skip subagent plan-mode ---
    if is_agent:
        return 0

    # --- Guard: plan must be non-empty ---
    if not plan_content:
        return 0

    # --- Resolve repo root ---
    # Priority: CLAUDE_PROJECT_DIR (explicit) -> git -C cwd -> git from PWD
    repo_root = None
    claude_project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if claude_project_dir and Path(claude_project_dir).is_dir():
        repo_root = _git_toplevel(claude_project_dir)
    if not repo_root and cwd and Path(cwd).is_dir():
        repo_root = _git_toplevel(cwd)
    if not repo_root:
        repo_root = _git_toplevel(None)

    # --- Guard: must be in a git repo ---
    if not repo_root:
        return 0

    # --- Placement law (AC7): route plan write-target through coordinator seam ---
    docs_plans_dir = Path(repo_root) / "docs" / "plans"
    docs_readme = Path(repo_root) / "docs" / "README.md"
    plans_git_root = repo_root

    # (A-F4, P2) A set-but-empty or non-absolute CLAUDE_HOME is a config error,
    # not a silent-fallback case — fail open the whole hook rather than risk
    # comparing repo_root against a guessed-wrong ~/.claude and mis-routing a
    # plan write. See _claude_home_dir() docstring for the full rationale.
    try:
        is_meta = _is_meta_repo(repo_root)
    except ValueError:
        return 0

    if is_meta:
        claude_klabauter_root = _resolve_claude_klabauter_root()
        if claude_klabauter_root:
            docs_plans_dir = Path(claude_klabauter_root) / "docs" / "plans"
            docs_readme = Path(claude_klabauter_root) / "docs" / "README.md"
            plans_git_root = claude_klabauter_root

    # --- Guard: repo must have opted into the docs convention ---
    if not docs_plans_dir.is_dir() and not docs_readme.is_file():
        return 0

    # --- Derive slug from first H1 ---
    slug = _derive_slug(plan_content)

    # --- Build target path ---
    today = _local_day()
    target_name = f"{today}-{slug}.md"
    target_path = docs_plans_dir / target_name

    # --- Ensure docs/plans/ exists ---
    if not docs_plans_dir.is_dir():
        try:
            docs_plans_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            return 0

    # --- Slug-collision check ---
    if target_path.is_file():
        try:
            existing = target_path.read_text(encoding="utf-8")
        except Exception:
            existing = ""
        if existing == plan_content:
            # Byte-identical -> idempotent no-op (no write, no re-stage).
            idempotent_ctx = render(_compose_idempotent_context(target_name, slug))
            _emit(idempotent_ctx)
            return 0
        else:
            # Content differs -> collision; do NOT overwrite.
            collision_msg = render(_compose_collision_message(target_path))
            _emit(collision_msg)
            return 0

    # --- Write plan to target ---
    # newline="" preserves the bash oracle's raw `printf '%s' > file` byte
    # behavior — no LF->CRLF translation on Windows (golden-diff parity).
    try:
        with target_path.open("w", encoding="utf-8", newline="") as fh:
            fh.write(plan_content)
    except Exception:
        return 0

    # --- Stage with explicit path (NEVER git add -A or git add .) ---
    _git_add(plans_git_root, target_path)

    # --- Idempotently insert a Plans-section line into docs/README.md ---
    readme_modified = False
    if docs_readme.is_file():
        readme_line = f"- [`{target_name}`]({'docs/plans/' + target_name})"
        try:
            existing_readme = docs_readme.read_text(encoding="utf-8")
        except Exception:
            existing_readme = ""
        if target_name not in existing_readme:
            try:
                with docs_readme.open("a", encoding="utf-8", newline="") as fh:
                    fh.write(f"\n{readme_line}\n")
                readme_modified = True
                _git_add(plans_git_root, docs_readme)
            except Exception:
                pass

    # --- Emit additionalContext ---
    rel_target = f"docs/plans/{target_name}"
    rel_readme = "docs/README.md"
    if plans_git_root != repo_root:
        if readme_modified:
            commit_cmd = (
                f'git -C "{plans_git_root}" add -- {rel_target} {rel_readme} && '
                f'git -C "{plans_git_root}" commit -m "plan: {slug}" -- {rel_target} {rel_readme}'
            )
        else:
            commit_cmd = (
                f'git -C "{plans_git_root}" add -- {rel_target} && '
                f'git -C "{plans_git_root}" commit -m "plan: {slug}" -- {rel_target}'
            )
    else:
        if readme_modified:
            commit_cmd = (
                f"git add -- {rel_target} {rel_readme} && "
                f'git commit -m "plan: {slug}" -- {rel_target} {rel_readme}'
            )
        else:
            commit_cmd = (
                f"git add -- {rel_target} && "
                f'git commit -m "plan: {slug}" -- {rel_target}'
            )

    additional_ctx = render(_compose_persisted_context(target_name, commit_cmd))
    _emit(additional_ctx)

    return 0


if __name__ == "__main__":
    sys.exit(main())
