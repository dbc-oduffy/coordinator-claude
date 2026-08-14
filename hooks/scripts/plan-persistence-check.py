#!/usr/bin/env python3
"""PostToolUse(ExitPlanMode) naked-Python port of plan-persistence-check.sh.

Purpose: reads the approved plan from tool_response.plan and persists it to
docs/plans/<YYYY-MM-DD>-<slug>.md in the project repo, NEVER committing —
committing from a hook child process bypasses all PreToolUse commit-safety
matchers. Emits additionalContext pre-filling the exact scoped commit command
and the subagent-review-artifact reminder.

Spec backlink: docs/plans/2026-06-18-plan-persistence-hook-automation.md

Two write paths, in preference order:
  1. The engine's `plan.persist_capture` op, via its `coordinator/bin/
     plan-capture-persist.py` trampoline — scaffolds a schema-compliant
     artifact (engine-written frontmatter, plan_id, deliverable_id,
     sizing_object reverse FK). It is expected to supersede a raw dump
     this hook already wrote for the same body — that reconciliation is
     the engine's responsibility and is not verified by this file or its
     tests.
  2. Fallback: the verbatim raw write below. Reached whenever the routed path
     is unavailable for any reason — the fail-open contract the engine side
     deliberately delegates here. Its worst case is a captured-but-gate-
     invisible plan, i.e. the pre-routing status quo; never plan loss.

The activation predicate, meta-repo routing, `additionalContext` emit, and the
no-git-add negative spec are shared by both paths.

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
    """Resolved ~/.claude directory.

    Sourced from the engine's canonical resolver — `coordinator/lib/
    claude-home/_claude_home.py`'s `home_dir()`, reached zero-subprocess via
    the importable seam `coordinator/lib/claude_home_shim.py`
    (`resolve_home_base()`) — when the engine root is resolvable on this
    machine. Mirrors `project-orientation.py::_claude_home()`'s
    resolve-root-then-sys.path-insert-then-import pattern (A-F4/P2
    follow-up, home-resolution-gate-family C6), not a local
    `coordinator/lib/` import: the shim lives in the engine repo, not this
    doctrine repo.

    Falls back to a hand-rolled ladder identical in precedence/behavior
    (CLAUDE_HOME -> HOME -> USERPROFILE -> Path.home()) if the engine root
    or the shim is unreachable for any reason (missing/unresolvable engine
    checkout, import failure, etc.) — this hook must never raise or block
    on an absent engine checkout.

    (A-F4, P2) Mirrors the canonical home_dir()'s fail-LOUD behavior on a
    set-but-empty or non-absolute CLAUDE_HOME: raises ValueError instead of
    silently falling through to HOME/USERPROFILE. CLAUDE_HOME isolates
    test/CI sandboxes from the real ~/.claude — a broken override must never
    silently route a plan write into the real docs/plans/. The caller
    (main(), via _is_meta_repo()) catches this ValueError and fails OPEN
    THE WHOLE HOOK (returns 0, no action) rather than guessing a home.

    Verified (2026-08-08): the engine's canonical `home_dir()` reproduces
    this fail-loud contract byte-for-byte — a set-but-empty CLAUDE_HOME and
    a non-absolute CLAUDE_HOME both raise ValueError there too (see its
    docstring / body). The ValueError from the shim call below is
    deliberately NOT swallowed by the broad except below — only
    resolution/import failures (missing engine, ImportError, etc.) fall
    through to the local ladder; a genuine fail-loud ValueError from the
    canonical resolver propagates to the caller exactly as the local ladder
    would have raised it.
    """
    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
        if claude_klabauter_root:
            claude_klabauter_lib = str(Path(claude_klabauter_root) / "coordinator" / "lib")
            if claude_klabauter_lib not in sys.path:
                sys.path.insert(0, claude_klabauter_lib)
            from claude_home_shim import resolve_home_base as _seam_resolve_home

            return _seam_resolve_home() / ".claude"
    except ValueError:
        raise
    except Exception:
        pass

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


# Negative spec — this hook takes NO git index lock, by PM ruling (2026-08-07).
# It formerly ran `git add` on the plan and on docs/README.md, i.e. two
# `.git/index.lock` acquisitions per plan write, from a hook, on a tree shared
# with live peer sessions. The staging bought protection against an untracked
# plan being swept (concurrent-em-hazards.md H18/H24); the ruling is that that
# clobber risk is preferable to the lock traffic, since the EM commits the plan
# from the prefilled command moments later. Do not reintroduce a `git add` here
# — not with a retry, not with `--no-optional-locks`. Persist to disk, print the
# command, take no lock.


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


def _commit_cmd(plans_git_root: str, repo_root: str, rel_paths: list[str], slug: str) -> str:
    """Prefilled scoped-commit command for the persisted plan (and README row).

    Cross-repo (meta-repo routing sent the write into the engine checkout) gets
    an explicit `git -C "<root>"` prefix; same-repo keeps the bare form.
    """
    paths = " ".join(rel_paths)
    if plans_git_root != repo_root:
        return (
            f'git -C "{plans_git_root}" add -- {paths} && '
            f'git -C "{plans_git_root}" commit -m "plan: {slug}" -- {paths}'
        )
    return f'git add -- {paths} && git commit -m "plan: {slug}" -- {paths}'


def _compose_idempotent_context(commit_cmd: str):
    """Pure composer for the byte-identical re-fire branch. Routes through
    `_message_envelope.compose` (C6, char-cap conversion): the diagnosis is
    the only counted prose, the copy-paste commit command rides in the
    exempt `alternative` slot, and the full subagent-review-artifact
    explanation this message used to carry inline has relocated to
    `_WIKI_ANCHOR` -- see this hook's relocation fragment
    (state/relocations/guard-message-cap/plan-persistence-check.py.md).
    Returns a `Message`, not flattened text -- `main()` calls `render()` at
    the emit call site, mirroring guard-review-integrator-sidecar-intake.py."""
    return compose(
        "PLAN ALREADY PERSISTED (byte-identical) -- commit if not "
        "yet done, route the body through coordinator:sizing to close "
        "it out, and write review artifacts to disk.",
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


def _compose_persisted_context(commit_cmd: str):
    """Pure composer for the successful-persist branch. Routes through
    `compose` -- same relocation rationale as `_compose_idempotent_context`.
    Returns a `Message`; see `_compose_idempotent_context` for the render()
    split.

    The plan is on disk and UNTRACKED -- the hook no longer stages it (see the
    no-index-lock negative spec). Until the prefilled command runs, the plan is
    the untracked-deliverable shape a peer's sweep can delete, so the headline
    asks for the commit now rather than merely offering it."""
    return compose(
        "PLAN PERSISTED, not staged -- commit it now; a peer sweep can "
        "delete it until it lands. Route the body through coordinator:sizing "
        "to close it out. Write review artifacts to disk.",
        alternative=commit_cmd,
        anchor=_WIKI_ANCHOR,
    )


#: Bounded budget for the engine-side `plan.persist_capture` call. The
#: PostToolUse(ExitPlanMode) entry in hooks.json declares `"timeout": 15`
#: (verified 2026-08-13); repo-root resolution ahead of this point chains up to
#: three 2s `git rev-parse` calls, leaving ~9s of headroom. The engine call is
#: one `coordinator-doc-new` subprocess spawn plus text processing, so 5s is
#: generous while keeping the worst-case sum (~11s) inside the declared budget.
_PERSIST_CAPTURE_TIMEOUT_S = 5


def _routed_persist(plan_content: str, plans_git_root: str) -> dict | None:
    """Scaffold a schema-compliant plan via the engine's `plan.persist_capture`.

    Returns the op's parsed result dict, or None when the routed path is
    unavailable for ANY reason. None is the fail-open signal: the caller falls
    back to the raw verbatim write, whose worst case is exactly the pre-routing
    status quo (a captured-but-gate-invisible plan), never plan loss.

    Fail-open is this hook's responsibility by the seam's design — the engine
    CLI is an ordinary fail-loud op and makes no such guarantee itself.
    """
    engine_root = _resolve_claude_klabauter_root()
    if not engine_root:
        return None
    trampoline = Path(engine_root) / "coordinator" / "bin" / "plan-capture-persist.py"
    if not trampoline.is_file():
        return None
    try:
        proc = subprocess.run(  # popup-intentional-last-resort
            [sys.executable or "python3", str(trampoline), "--repo-root", plans_git_root],
            input=plan_content,
            capture_output=True,
            text=True,
            timeout=_PERSIST_CAPTURE_TIMEOUT_S,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        return None
    if not isinstance(result, dict) or result.get("status") not in (
        "ok",
        "idempotent",
        "collision",
    ):
        return None
    return result


def _append_readme_row(docs_readme: Path, readme_row: str) -> bool:
    """Idempotently append the engine-supplied Plans-section row. Same
    contract as the raw-write path's own append — only the link target
    differs (the engine emits the correct `plans/...` prefix)."""
    if not readme_row or not docs_readme.is_file():
        return False
    try:
        existing = docs_readme.read_text(encoding="utf-8")
    except Exception:
        return False
    if readme_row.strip() in existing:
        return False
    try:
        with docs_readme.open("a", encoding="utf-8", newline="") as fh:
            fh.write(f"\n{readme_row.rstrip()}\n")
    except Exception:
        return False
    return True


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

    # --- Routed persist (preferred): schema-compliant scaffold via the engine ---
    # A verbatim body written to docs/plans/<date>-<slug>.md carries no
    # frontmatter, so it has no plan_id / deliverable_id / sizing_object and is
    # invisible to every frontmatter-driven gate. The engine op scaffolds a real
    # artifact instead (and supersedes a raw dump this hook already wrote for the
    # same body). Any failure falls through to the raw write below.
    routed = _routed_persist(plan_content, plans_git_root)
    if routed is not None:
        status = routed.get("status")
        if status == "collision":
            _emit(render(_compose_collision_message(routed.get("path") or target_path)))
            return 0
        routed_path = routed.get("path")
        if routed_path:
            rel_paths = [routed_path]
            if _append_readme_row(docs_readme, routed.get("readme_row") or ""):
                rel_paths.append("docs/README.md")
            cmd = _commit_cmd(plans_git_root, repo_root, rel_paths, slug)
            composer = (
                _compose_idempotent_context
                if status == "idempotent"
                else _compose_persisted_context
            )
            _emit(render(composer(cmd)))
            return 0

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
            idempotent_ctx = render(
                _compose_idempotent_context(
                    _commit_cmd(plans_git_root, repo_root, [f"docs/plans/{target_name}"], slug)
                )
            )
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

    # Deliberately NOT staged — see the no-index-lock negative spec above.

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
            except Exception:
                pass

    # --- Emit additionalContext ---
    rel_paths = [f"docs/plans/{target_name}"]
    if readme_modified:
        rel_paths.append("docs/README.md")
    commit_cmd = _commit_cmd(plans_git_root, repo_root, rel_paths, slug)

    additional_ctx = render(_compose_persisted_context(commit_cmd))
    _emit(additional_ctx)

    return 0


if __name__ == "__main__":
    sys.exit(main())
