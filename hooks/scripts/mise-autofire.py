"""UserPromptExpansion auto-fire hook for `/mise-en-place` run-id minting
(naked Python, no bash) -- the mise-side twin of `pickup-autofire.py`.

Purpose: when the EM types `/mise-en-place` (or any command whose bare verb
is `mise-en-place`), this hook fires ahead of `UserPromptSubmit`, mints a
fresh Phase-0 run id via the engine plane's `backlog-grind-assemble
mint-run-id mise-en-place` CLI, immediately briefs that same id back through
`backlog-grind-assemble brief mise-en-place --run-id <minted>`, and injects
both the minted id (plus the inventory path it implies, and the brief's
decision object) as `additionalContext` -- so the EM's own turn already has
an engine-issued run id in hand rather than inventing one by convention.

Both calls are READ-ONLY. Unlike `pickup-autofire.py`'s twin surface (which
auto-fires a mutating `apply` half on a clear coast), this hook has NO
mutating half and must never grow one: `mint-run-id` and `brief` are the
entire surface it touches. Phase 6 (the mutating cadence-close step) stays
an EM-driven invocation quoting the minted id, exactly as before this hook
existed -- see the cross-repo memo cited below for the boundary this was
built against.

Co-fires with `pickup-autofire.py`, by design and without conflict: that
hook's `_BATON_GRAB_COMMAND_NAMES` also matches `mise-en-place`, because
batons handed to `/mise` are a grab too (`skills/pickup/SKILL.md` §
Multi-Artifact Grab). It briefs the baton paths carried in `command_args`;
this one mints the run id the cadence itself needs. Two `additionalContext`
blocks on one prompt is the expected shape, not a double-fire bug -- neither
hook reads or writes what the other computes.

Contract (mirrors `pickup-autofire.py`):
  stdin   -- UserPromptExpansion JSON (command_name, command_args,
             command_source, cwd, expansion_type, session_id, prompt_id, ...)
  stdout  -- one `hookSpecificOutput` JSON envelope with `additionalContext`
             when a mise-en-place verb was matched and a mint+brief pair
             could be computed; NOTHING otherwise (silent pass -- an
             unrelated command, or a total transport failure, produces no
             output)
  exit 0  -- always. This hook is advisory only and never blocks the EM's
             own prompt.

Cross-repo provenance: the engine plane's commit `339470fd6bd7` shipped
`mint-run-id <cadence>` as a sibling subcommand to `brief`/`apply` on the
same `backlog-grind-assemble` trampoline; the consumer contract this hook
relies on is pinned in
`cross-repo/inbox/2026-08-04-claude-klabauter-em-mint-run-id-verb-shipped.md`:

  - `inventory_path` is repo-relative POSIX on every platform, never
    machine-absolute -- it is the path the id IMPLIES, not a path that
    exists yet.
  - The verb is read-only and specifically never creates
    `state/mise-inventory/`. That directory's ABSENCE is the engine's own
    Phase-0-vs-Phase-6 self-gate; this hook must not create it either, not
    as a side effect, not "helpfully" -- there is no filesystem-touching
    code anywhere in this module.
  - A cadence no reader claims is a usage error (exit 2) -- only
    `mise-en-place` claims it today, which is also the only verb this hook
    matches, so that failure mode is never actually reachable from here; it
    still degrades to silent pass per this module's fail-open discipline
    rather than assuming the exit code.
  - A minted id is by construction accepted by the very next
    `brief mise-en-place --run-id <minted>` -- confirmed live at authoring
    time; the brief call is not expected to reject its own freshly-minted
    input, but its failure still degrades to silent pass like every other
    step.

Safety envelope, each clause load-bearing:
  (a) NEVER fires a mutating call. There is no `apply`-equivalent anywhere
      in this module; `mint-run-id` and `brief` are both read-only per the
      memo above, and that is the whole surface this hook touches.
  (b) Hook errors / timeouts / transport failures degrade to silent pass and
      NEVER block `/mise-en-place` -- every subprocess call and every JSON
      decode in this module is wrapped to fail open, and `main()` never
      raises. A failed mint means the EM mints by hand, exactly today's
      behaviour.
  (c) `additionalContext` never exceeds `_CONTEXT_BUDGET_CHARS` (10,000).
      Over budget, the rendered text is hard-truncated as a last resort --
      this hook's payload is small and fixed-shape (an id, a path, one
      decision object), so no priority-ladder degrade is needed the way
      `pickup-autofire.py`'s N-baton render requires.
  (d) `async: false` semantics: the minted id and briefed decision must land
      in the SAME turn the EM's prompt is being expanded into -- an async
      fire would compute the mint after the EM has already acted on the
      prompt, which defeats the purpose entirely.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# --- Constants ---------------------------------------------------------------

# The bare verb this hook reacts to. Deliberately the SAME literal value
# `pickup-autofire.py` uses for its own `_BATON_GRAB_COMMAND_NAMES` member --
# not a second, independently-chosen convention for what counts as the
# mise-en-place command name.
_MISE_COMMAND_NAMES = frozenset({"mise-en-place"})

# The only cadence `mint-run-id`/`brief` are called with from this hook --
# matches the one verb `_MISE_COMMAND_NAMES` gates on. The dispatch seam
# itself is cadence-agnostic per the memo; this hook is not -- it exists for
# exactly one cadence today.
_CADENCE = "mise-en-place"

_CONTEXT_BUDGET_CHARS = 10_000

_MINT_TIMEOUT_SECONDS = 12
_BRIEF_TIMEOUT_SECONDS = 12

# Windows console-subprocess discipline: `python.exe` is a CONSOLE-subsystem
# child. `getattr` resolves to 0 (no-op) on every non-Windows platform.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _normalize_command_name(name: str | None) -> str:
    """Normalize a raw `command_name` payload value to its bare verb.

    Identical shape to `pickup-autofire.py::_normalize_command_name` --
    strips any `<namespace>:` prefix by taking the segment after the LAST
    `:`, so both the namespaced plugin-slash-command shape
    (`"coordinator:mise-en-place"`) and a bare typed/projectSettings verb
    normalize to the same string before the membership test. Returns `""`
    for `None`/non-`str` input.
    """
    if not isinstance(name, str):
        return ""
    return name.rsplit(":", 1)[-1]


# --- COORDINATOR_SETTINGS_HOME resolution (mirrors pickup-autofire.py) ------


def resolve_settings_home() -> Path:
    """Resolve the coordinator-claude settings-home root.

    Precedence: an explicit `COORDINATOR_SETTINGS_HOME` override is used
    AS-IS; otherwise `CLAUDE_HOME` (or `HOME`) joined with the fixed
    `.coordinator-claude-settings` suffix. Bit-for-bit the same precedence
    as `pickup-autofire.py::resolve_settings_home` -- kept as an independent
    copy (not a shared import) because hook scripts in this directory are
    each self-contained single-file modules loaded by path, not package
    members with a shared internal import surface.
    """
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override:
        return Path(override)
    base = os.environ.get("CLAUDE_HOME") or str(Path.home())
    return Path(base) / ".coordinator-claude-settings"


# --- Shared forwarder resolution ---------------------------------------------
_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _forwarder_resolve import forwarder_argv as _forwarder_argv
    from _forwarder_resolve import resolve_forwarder as _resolve_forwarder
except Exception:
    # Defensive fallback -- a deploy missing its sibling _forwarder_resolve.py must
    # degrade to the pre-existing extensionless-only behaviour (which the caller
    # already treats as a fail-open transport failure), never crash on import.
    def _resolve_forwarder(bin_dir, name):  # type: ignore[misc]
        candidate = bin_dir / name
        return candidate if candidate.is_file() else None

    def _forwarder_argv(script_path, tail=()):  # type: ignore[misc]
        return [sys.executable, str(script_path), *tail]


def resolve_backlog_grind_assemble_bin(settings_home: Path) -> Path | None:
    """Resolve the installed `backlog-grind-assemble` forwarder under
    `settings_home`.

    Returns the extensionless script or the native `.exe`, whichever the install
    carries, or None when neither is found -- the caller treats a None return as a
    transport failure and fails open.

    Probing the extensionless name alone (what this did) resolved nothing on a
    Windows box carrying the native-forwarder generation, so this autofire simply
    stopped firing there, silently.

    Negative-spec: still does NOT resolve `bin/backlog-grind-assemble.cmd` -- see
    `_forwarder_resolve`'s negative-spec for why (`CreateProcess` cannot launch
    one, and the two variants this DOES probe already cover every platform).
    """
    return _resolve_forwarder(settings_home / "bin", "backlog-grind-assemble")


def backlog_grind_assemble_argv(script_path: Path, tail: list[str]) -> list[str]:
    """Build the subprocess argv for invoking the resolved forwarder.

    The interpreter prefix is decided by which variant resolved, not assumed: an
    extensionless naked-Python script requires it, a native `.exe` must be launched
    bare. See `_forwarder_resolve.forwarder_argv`.
    """
    return _forwarder_argv(script_path, tail)


# --- Subprocess invocation (fail-open) ---------------------------------------


class _TransportFailure(Exception):
    """Raised internally when a `backlog-grind-assemble` invocation could
    not be completed at all (binary unresolvable, spawn failure, or
    timeout) -- as opposed to the target CLI running and returning a
    non-zero business exit code (e.g. an unclaimed cadence), which still
    yields usable stdout/stderr and is not a transport failure from this
    hook's point of view, though this hook treats BOTH the same way
    (silent pass) since it has no use for a partial mint/brief result."""


def _run_backlog_grind_assemble(
    script_path: Path, tail: list[str], timeout: float
) -> subprocess.CompletedProcess:
    """Run the resolved forwarder. Raises `_TransportFailure` on ANY
    failure to complete the subprocess (spawn error, timeout) -- never lets
    a raw OSError/TimeoutExpired escape, since every caller must be able to
    fail open.
    """
    argv = backlog_grind_assemble_argv(script_path, tail)
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise _TransportFailure(str(exc)) from exc


def decode_mint_payload(stdout: str) -> dict | None:
    """Parse `mint-run-id`'s stdout into its `{"inventory_path", "run_id"}`
    dict, or None on ANY shape mismatch (unparseable JSON, non-dict, or a
    dict missing either required key with a non-empty string value) --
    fail-open, never raises.
    """
    try:
        obj = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    run_id = obj.get("run_id")
    inventory_path = obj.get("inventory_path")
    if not (isinstance(run_id, str) and run_id):
        return None
    if not (isinstance(inventory_path, str) and inventory_path):
        return None
    return {"run_id": run_id, "inventory_path": inventory_path}


def decode_brief_payload(stdout: str) -> dict | None:
    """Parse `brief`'s stdout into its decision-object dict, or None on any
    shape mismatch (unparseable JSON, or a non-dict top level) -- fail-open,
    never raises.
    """
    try:
        obj = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


# --- additionalContext rendering ---------------------------------------------


def render_additional_context(run_id: str, inventory_path: str, brief: dict) -> str:
    """Render the `additionalContext` string: the engine-minted run id and
    the inventory path it implies (labelled as engine-issued, not
    EM-guessed), followed by the brief's own `narration`/`next_move` prose
    when present, then the full decision object as JSON evidence.

    Hard-truncates at `_CONTEXT_BUDGET_CHARS` as a last resort -- this
    payload is small and fixed-shape (unlike `pickup-autofire.py`'s N-baton
    render, there is no priority ladder to degrade through here).
    """
    lines = [
        f"Mise-en-place run id (engine-minted, not EM-guessed): {run_id}",
        f"Inventory path this id implies (does not exist yet): {inventory_path}",
    ]

    narration = brief.get("narration")
    if isinstance(narration, str) and narration:
        lines.append(narration)

    next_move = brief.get("next_move")
    if isinstance(next_move, str) and next_move:
        lines.append(f"Next move: {next_move}")

    try:
        lines.append("Brief decision object:\n" + json.dumps(brief, indent=2, sort_keys=True))
    except (TypeError, ValueError):
        pass

    rendered = "\n\n".join(lines)
    return rendered[:_CONTEXT_BUDGET_CHARS]


# --- Entry point --------------------------------------------------------------


def main(stdin_text: str | None = None) -> int:
    try:
        raw = stdin_text if stdin_text is not None else sys.stdin.read()
    except Exception:
        return 0  # fail-open -- stdin unreadable

    try:
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    command_name = _normalize_command_name(payload.get("command_name"))
    if command_name not in _MISE_COMMAND_NAMES:
        return 0  # not a mise-en-place invocation -- silent pass

    settings_home = resolve_settings_home()
    script_path = resolve_backlog_grind_assemble_bin(settings_home)
    if script_path is None:
        return 0  # transport failure -- CLI unresolvable, fail open

    try:
        mint_result = _run_backlog_grind_assemble(
            script_path, ["mint-run-id", _CADENCE], _MINT_TIMEOUT_SECONDS
        )
    except _TransportFailure:
        return 0

    if mint_result.returncode != 0:
        return 0  # e.g. unclaimed cadence -- fail open, EM mints by hand

    minted = decode_mint_payload(mint_result.stdout)
    if minted is None:
        return 0  # malformed mint output -- fail open

    run_id = minted["run_id"]
    inventory_path = minted["inventory_path"]

    try:
        brief_result = _run_backlog_grind_assemble(
            script_path,
            ["brief", _CADENCE, "--run-id", run_id],
            _BRIEF_TIMEOUT_SECONDS,
        )
    except _TransportFailure:
        return 0

    if brief_result.returncode != 0:
        return 0  # fail open -- brief could not be computed for this id

    brief = decode_brief_payload(brief_result.stdout)
    if brief is None:
        return 0  # malformed brief output -- fail open

    additional_context = render_additional_context(run_id, inventory_path, brief)
    if not additional_context:
        return 0

    try:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptExpansion",
                        "additionalContext": additional_context,
                    }
                }
            )
        )
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
