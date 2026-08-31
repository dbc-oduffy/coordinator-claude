#!/usr/bin/env python3
"""PostToolUse(Write|Edit|MultiEdit) AND SessionStart hook: re-derive the
live global CLAUDE.md copy AND the live `~/.claude/rules/*.md` mirror
whenever their TRACKED sources may have changed.

Why this exists — the mirror direction is TRACKED -> LIVE, not the reverse:
`global-doctrine/CLAUDE.md` (tracked, in this repo) is the authoring target;
`~/.claude/CLAUDE.md` (live, harness-loaded) is DERIVED from it. Before this
hook, nothing performed that derivation — a human had to notice
`coordinator/tests/test_global_doctrine_tracked_copy.py` go red and manually
run `cp global-doctrine/CLAUDE.md ~/.claude/CLAUDE.md`. That is exactly the
failure shape this repo's north star (`coordinator/docs/wiki/
invisible-doctrine.md`) names: a rule whose only discharge is "the operator
remembers." This hook makes the derivation automatic.

Two triggers, one hazard the Write|Edit-only original missed: the tracked
source on this shared-branch repo changes far more often via `git pull` /
`checkout` / `merge` / a peer session's commit than via a tool-mediated
Write/Edit -- none of those fire a PostToolUse event, so a Write|Edit-only
registration is structurally blind to the most common way the source
changes. SessionStart closes that gap; Write|Edit stays registered
alongside it for immediacy on the tool-mediated path.

OSS-CLOBBER HAZARD -- read `_is_dev_repo()` before touching the gate below.
`~/.claude/CLAUDE.md` and `~/.claude/rules/` are the OPERATOR'S OWN global
config. For anyone running the OSS coordinator-claude distribution they
have nothing to do with this repo, and this hook must NEVER derive into
them there. On a Write|Edit match the incidental protection was "an OSS
install has no global-doctrine/CLAUDE.md (or global-doctrine/rules/), so
the path never matches" -- SessionStart carries no file_path payload to run
that same incidental check against, so the dev-repo sentinel gate below is
load-bearing, not defense-in-depth, for that trigger. It must be impossible
by construction for a non-dev checkout to reach either mirrored target, not
merely unlikely.

The `rules/*.md` mirror is copy-in only, never prune: a file present in the
live `~/.claude/rules/` but absent from tracked `global-doctrine/rules/` is
left completely alone -- never deleted, moved, or warned-about. The
operator may keep rules files there that this repo does not own.

Contract (matches the house PostToolUse-advisory convention used by
nudge-initiative-goals-ladder.py -- exit 2 + stderr reaches the model's next
turn without blocking; exit 0 + silence is the non-firing no-op):
  stdin   -- PostToolUse JSON (tool_name, tool_input.file_path, ...) OR
             SessionStart JSON (no tool_input/file_path)
  stderr  -- one advisory line ONLY when a real derivation happened (drift
             found and corrected) or a genuine failure occurred
  exit 2  -- advisory fired: content actually changed (success) or a
             read/write failure occurred
  exit 0  -- non-firing no-op: gate failed (not the dev repo, path did not
             match, no tracked source), OR the live copy was already
             byte-identical to the tracked source (nothing to do). NOTHING
             on stdout/stderr in either sub-case -- per this repo's own
             wiki (coordinator/docs/wiki/eager-agent-calibration.md §
             "A Check That Speaks Only on Drift Is Free to Run Anywhere"),
             a check silent on the clean state costs nothing to run on
             every SessionStart across the fleet.

Fail-loud, not fail-silent, on the ONE path this hook is responsible for
(the tracked file matched, but read or write failed) -- a bare
`except Exception: pass` here would silently reintroduce the exact staleness
gap this hook exists to close (the same P1 shape recently found and fixed in
check-claude-md-size.py's unreadable-existing-file handling). Every OTHER
guard (path did not match, repo root undiscoverable, not the dev repo, live
already in sync) fails open/silent by design, per this hook's own no-op
contract above.

Portability: macOS + Windows. No subprocess/`cp` -- `shutil.copyfile` only.
Repo root is resolved from `Path(__file__)` upward (parents[3]: scripts ->
hooks -> coordinator -> repo root), never from cwd or a hardcoded path.

Spec backlink: coordinator/tests/test_global_doctrine_tracked_copy.py,
coordinator/tests/test_derive_global_doctrine_live_copy.py

Review: code-reviewer -- Finding 4: the session_start_mode branch in main()
is presently reachable only via direct/manual invocation and this file's
own tests -- no registered hooks.json entry sends this script a
SessionStart payload today, and sweep-boot.py's fold-in bypasses main()
entirely, calling _is_dev_repo() / _tracked_path() / _derive_live_copy()
directly.

Advisory prose routes through `_message_envelope.compose` (280-char
prose ceiling; see `coordinator/hooks/scripts/_message_envelope.py`). The
mirror-direction/OSS-clobber/fail-loud reasoning above is the full
explanation; each composer below carries only the diagnosis, pointing at
`_WIKI_ANCHOR` for the rest -- see this hook's own relocation fragment
(state/relocations/guard-message-cap/derive-global-doctrine-live-copy.py.md).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _message_envelope import CHANNEL_STOP, compose, emit  # noqa: E402

#: Wiki section carrying the relocated mirror-direction, OSS-clobber-hazard,
#: and fail-loud-contract explanation -- see this hook's own relocation
#: fragment (state/relocations/guard-message-cap/derive-global-doctrine-live-copy.py.md).
_WIKI_ANCHOR = (
    # Review: code-reviewer -- render() emits `f"See {anchor}."` verbatim;
    # a bare fragment produces an unresolvable citation. Full path matches
    # every other converted hook's `_WIKI_ANCHOR` shape.
    "coordinator/docs/wiki/guard-message-concision.md"
    "#derive-global-doctrine-mirror-and-fail-loud"
)


def _read_stdin() -> str:
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


def _repo_root() -> Path:
    # coordinator/hooks/scripts/<this file> -> parents[3] is the repo root.
    # Review: code-reviewer -- Finding 4: this resolves from Path(__file__),
    # i.e. from wherever ${CLAUDE_PLUGIN_ROOT} points -- the canonical plugin
    # source checkout, not necessarily the checkout backing the session's
    # cwd. A session working out of a git worktree, editing that worktree's
    # own global-doctrine/CLAUDE.md, will never match tracked_resolved
    # (pinned to the plugin-root checkout), so the hook silently no-ops for
    # that worktree -- believed correct (one canonical live doctrine
    # target), but worth knowing if a worktree edit doesn't propagate.
    return Path(__file__).resolve().parents[3]


def _tracked_path() -> Path:
    return _repo_root() / "global-doctrine" / "CLAUDE.md"


def _live_path() -> Path:
    return Path.home() / ".claude" / "CLAUDE.md"


def _tracked_rules_dir() -> Path:
    return _repo_root() / "global-doctrine" / "rules"


def _live_rules_dir() -> Path:
    return Path.home() / ".claude" / "rules"


def _tracked_rules_files() -> list[Path]:
    """Every tracked `*.md` file under `global-doctrine/rules/`, sorted for
    deterministic derivation order. Copy-in only -- the caller mirrors each
    of these into the live rules dir, and NEVER deletes a live file absent
    here (see module docstring's prune-safety contract). Returns an empty
    list on a missing directory or any read error -- fails open, matching
    every other non-owned-path guard in this module."""
    rules_dir = _tracked_rules_dir()
    try:
        if not rules_dir.is_dir():
            return []
        return sorted(p for p in rules_dir.iterdir() if p.is_file() and p.suffix == ".md")
    except Exception:
        return []


def _dev_sentinel_path() -> Path:
    return _repo_root() / ".coordinator-dev-repo"


def _is_dev_repo() -> bool:
    """OSS-clobber gate -- fail CLOSED on any uncertainty.

    `~/.claude/CLAUDE.md` is the OPERATOR'S OWN global config, not this
    repo's to write outside a doctrine-repo dev checkout. `.coordinator-dev-
    repo` is deliberately at the REPO ROOT (not under `coordinator/`) so it
    does NOT percolate to the OSS `coordinator-claude` publish -- that is
    what makes its presence a valid dev-vs-OSS discriminant rather than a
    convention an OSS user could accidentally inherit. If the sentinel is
    absent, or resolving it raises for any reason, this returns False and
    every caller below no-ops silently. Do not weaken this to a best-effort
    heuristic: an ungated derivation on an OSS install would silently
    overwrite every OSS user's personal global config, every session.
    """
    try:
        return _dev_sentinel_path().is_file()
    except Exception:
        return False


def _compose_read_failure_message(tracked: Path, exc: Exception):
    """Pure composer for a tracked-source read failure. Fail-loud contract
    rationale relocated to `_WIKI_ANCHOR`."""
    prose = f"tracked doctrine unreadable, live unchanged: {tracked}"
    return compose(prose, anchor=_WIKI_ANCHOR)


def _compose_write_failure_message(live: Path, tracked: Path, exc: Exception, source_bytes: bytes):
    """Pure composer for a live-copy write failure after a successful
    tracked-source read."""
    prose = f"live copy write failed ({len(source_bytes)}B read OK): {live}"
    return compose(prose, anchor=_WIKI_ANCHOR)


def _compose_success_message(live: Path, tracked: Path, source_bytes: bytes):
    """Pure composer for a successful tracked->live re-derivation."""
    prose = f"re-derived {live} ({len(source_bytes)}B)"
    return compose(prose, anchor=_WIKI_ANCHOR)


def _derive_live_copy(tracked: Path, live: Path) -> int:
    """Shared read/compare/write path for both invocation modes and both
    mirrored targets (the single `CLAUDE.md` and each `global-doctrine/
    rules/*.md` file) -- `tracked`/`live` are passed explicitly by the
    caller rather than hardcoded, so this one function drives every mirrored
    pair.

    Silent (return 0) when the live copy is already byte-identical to the
    tracked source -- see the module docstring's contract table and
    coordinator/docs/wiki/eager-agent-calibration.md § "A Check That Speaks
    Only on Drift Is Free to Run Anywhere". Loud (stderr + exit 2) only when
    a real derivation happens (drift found and corrected) or a read/write
    failure occurs.
    """
    # Routed through `_message_envelope.emit()` (CHANNEL_STOP) rather than
    # hand-rolling `render()` + a text-mode `sys.stderr.write()` -- `emit()`'s
    # CHANNEL_STOP branch writes via `sys.stderr.buffer.write()`, which
    # bypasses Python's Windows text-mode LF->CRLF translation (a real
    # byte-fidelity loss the hand-rolled path used to carry silently). See
    # `state/bug-backlog/2026-08-06-derive-hooks-hand-roll-stop-shape-and-lo-4c1e9a7b03d5.yaml`.
    try:
        source_bytes = tracked.read_bytes()
    except Exception as exc:
        rc = emit(_compose_read_failure_message(tracked, exc), CHANNEL_STOP)
        return rc if rc is not None else 2

    try:
        live_bytes = live.read_bytes()
    except Exception:
        live_bytes = None

    if live_bytes == source_bytes:
        # Already in sync -- nothing to do, stay silent.
        return 0

    try:
        live.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(tracked, live)
    except Exception as exc:
        rc = emit(_compose_write_failure_message(live, tracked, exc, source_bytes), CHANNEL_STOP)
        return rc if rc is not None else 2

    rc = emit(_compose_success_message(live, tracked, source_bytes), CHANNEL_STOP)
    return rc if rc is not None else 2


def main() -> int:
    raw = _read_stdin()
    data = _parse_input(raw)

    # OSS-clobber gate, applied on EVERY path through this script (defense
    # in depth on the Write|Edit path, load-bearing on SessionStart -- see
    # module docstring). Checked FIRST, before any payload interpretation.
    if not _is_dev_repo():
        return 0

    hook_event_name = data.get("hook_event_name")
    if not isinstance(hook_event_name, str):
        hook_event_name = ""

    tool_input = data.get("tool_input")
    file_path = ""
    if isinstance(tool_input, dict):
        file_path = tool_input.get("file_path", "") or ""
    if not isinstance(file_path, str):
        file_path = ""

    # Mode detection: require an explicit positive signal for SessionStart
    # mode -- never infer it from absence. A payload carrying neither a
    # recognized hook_event_name nor a usable file_path falls through to the
    # `if not file_path: return 0` no-op below, per the module's own no-op
    # contract.
    # Review: code-reviewer -- Finding 1: the prior `else: not file_path`
    # fallback treated any payload lacking BOTH fields as SessionStart,
    # which could trigger a live-copy write on a malformed/future-shaped
    # event the contract promises must be a silent no-op.
    session_start_mode = hook_event_name == "SessionStart"

    if session_start_mode:
        exit_code = 0
        tracked = _tracked_path()
        if tracked.is_file():
            exit_code = max(exit_code, _derive_live_copy(tracked, _live_path()))
        for rules_tracked in _tracked_rules_files():
            rules_live = _live_rules_dir() / rules_tracked.name
            exit_code = max(exit_code, _derive_live_copy(rules_tracked, rules_live))
        return exit_code

    # --- Existing Write|Edit payload-driven behaviour ---
    if not file_path:
        return 0

    try:
        resolved = Path(file_path).resolve()
    except Exception:
        return 0

    tracked = _tracked_path()
    try:
        tracked_resolved = tracked.resolve()
    except Exception:
        tracked_resolved = tracked

    # Review: code-reviewer -- Finding 2: this is a strict Path equality
    # comparison. Path.resolve() does not case-normalize on
    # case-insensitive-but-case-preserving filesystems (macOS APFS default,
    # Windows NTFS), so a differently-cased file_path for the same physical
    # file would fail to match here -- a fail-open miss (degrades
    # gracefully; not a false positive), left unguarded as an accepted edge
    # case. Same caveat applies to the rules-dir match added below.
    if resolved == tracked_resolved:
        return _derive_live_copy(tracked, _live_path())

    rules_dir = _tracked_rules_dir()
    try:
        rules_dir_resolved = rules_dir.resolve()
    except Exception:
        rules_dir_resolved = rules_dir

    try:
        resolved.relative_to(rules_dir_resolved)
        under_rules_dir = True
    except ValueError:
        under_rules_dir = False

    if under_rules_dir and resolved.suffix == ".md" and resolved.is_file():
        return _derive_live_copy(resolved, _live_rules_dir() / resolved.name)

    return 0


if __name__ == "__main__":
    sys.exit(main())
