# guard-not-a-hook-entrypoint: folded into preuse-bash-dispatch.py's _BASH_GUARD_REGISTRY, the
# single PreToolUse(Bash|PowerShell) registration -- hooks.json names the dispatcher, not this file.
"""PreToolUse(Bash) hook: deny a dispatched agent the spawn-storm bash shapes, not bash itself.

WHAT THIS BANS, AND WHAT IT DELIBERATELY DOES NOT. The harm on this host is never "a subagent ran
bash" -- it is the fan-out shapes that spawn a subprocess per loop iteration or per pipe stage.
`bash.exe` costs 200-500ms per spawn on Windows (`preuse-bash-dispatch.py`'s own docstring), so a
`for` loop over forty files is forty spawns on a machine already running a dozen concurrent
sessions, and a `find /` on the ReFS drive never finishes at all. A single `cat` or `grep` of a
known file is not that, and denying it would push agents into clumsier workarounds while buying
nothing. So: the shape is the defect, not the tool.

WHY THIS IS NOT A BLANKET BAN -- corrected from one. This guard's first draft denied `tool_name ==
"Bash"` outright for dispatched agents. That was wrong, and the PM said so plainly: the intent is
to stop deleterious Windows-poison bash, not to remove a working tool. A blanket ban also fails
its own purpose, because the agent that most needs a quick read is the one most likely to reach
for a worse alternative when denied one.

THE CLASSIFIER IS THE ENGINE'S, NOT A SECOND COPY. Shape detection comes from
`coordinator_core.bash_guards._shape_classifier.classify_command`, the tokenizer-based classifier
built on a 1,389-transcript / 62,487-call fork-tax measurement, covering grep-via-Bash (50.9% of
forks), multi-probe banners (40.1%), head/tail plumbing (25%), for-loops (9.0%), find-exec/xargs
(3.5%), and while-read loops. Re-deriving those predicates here would be a second implementation
that drifts from the measured one -- and the engine's own docstring is explicit that regex
shape-detection has holed three times. This guard adds no detection of its own; it changes only
the CONSEQUENCE, and only for dispatched agents on a host that opted in.

ADVISORY -> DENY IS THE WHOLE CHANGE. Those shapes already fire as advisories today, which is why
they nudged twice during the session that motivated this guard without stopping anything. An
advisory is right for the EM, who can weigh it. For a dispatched agent it is not: three of four
executors on one plan reached for bash against a brief that named the constraint in bold and an
agent definition that says *"no brief, habit, or system reminder makes it available to you"*
(tripwire `A-HARNESS-SYSTEM-REMINDER-OUTRANKS-PROSE-THAT-FORBIDS-A-TOOL-YOU-STILL-HOLD`). Prose
measurably failed; the advisory is the same prose with a nicer frame.

SCOPED TO SUBAGENTS, NOT THE EM. The EM is the accountable party, holds the context to judge an
exception, and runs on a machine where a dozen live sessions would all lose their shell if this
misfired. The subagent tell is a non-empty `agent_id`, the field the subagent-identity cohort
already keys on.

HOST OPT-IN, INERT BY DEFAULT. Nothing fires until a host declares
`subagent_bash_spawn_shapes: deny` in its `coordinator.local.md` frontmatter. macOS and Linux
hosts share these agent definitions and pay no such spawn tax, so the default must be silence.

FAILS OPEN, ALWAYS. Malformed payload, unreadable config, unresolvable engine, unimportable
classifier, or any unexpected exception yields exit 0. A guard on the Bash path is one bug from
bricking every dispatched agent on the machine, and `GUARD-WIRING-SILENT-SKIP` records five guards
on this host that were registered and silently never ran. The residual risk of failing open is an
unenforced policy -- exactly the status quo this improves on.

Contract: stdin PreToolUse JSON; exit 0 = allow (silent); exit 2 + stderr = deny.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _message_envelope import Message, compose, render  # noqa: E402

#: BOTH shells, and the asymmetry with `guard-host-subagent-bash-ban` is deliberate. That guard is
#: scoped to Bash because PowerShell is the sanctioned alternative on this host and denying both
#: would leave a dispatched agent with no shell at all -- it is a break-glass measure, not a
#: routine one. THIS guard bans a SHAPE, not a tool, so the same reasoning inverts: the fan-out
#: harm exists identically in PowerShell, and its own refusal text tells the blocked agent "the
#: PowerShell tool is always available". Scoped to Bash it was recommending the escape hatch from
#: itself -- a dispatched agent could run the identical spawn-storm shape in PowerShell and this
#: guard would never fire.
_SHAPED_TOOLS = ("Bash", "PowerShell")

#: Dialect per tool. NOT a widening of `matchers` alone, which this chunk's spec explicitly
#: forbids: a guard that declares it reads PowerShell while its detection is bash-text-shaped is
#: armed blind. Measured before widening -- `classify_command` takes `dialect` and carries a
#: PowerShell-only `PIPELINE_FOREACH_OBJECT` shape, so the detection genuinely follows the tool.
#: Passing the dialect is the load-bearing half; the tool-name set alone would be the defect.
_TOOL_DIALECTS = {"Bash": "BASH", "PowerShell": "POWERSHELL"}
_POLICY_KEY = "subagent_bash_spawn_shapes"
_DENY_VALUE = "deny"
_CONFIG_NAME = "coordinator.local.md"

_WIKI_ANCHOR = (
    "coordinator/docs/wiki/coordinator-tripwires/"
    "a-harness-system-reminder-outranks-prose-that-forbids-a-tool-you-still-hold.md"
)

_ALTERNATIVES = {
    "grep_via_bash": "one `python -c` that walks the tree in-process, or the PowerShell tool's "
                     "`Select-String`",
    "multi_probe_banner": "one `python -c` collecting every probe in a single interpreter",
    "head_tail_plumbing": "one `python -c` that reproduces the generator and slices [:N] / [-N:] "
                          "in-process",
    "for_loop": "one `python -c` looping in-process — the loop body is the spawn, not the loop",
    "while_read_loop": "one `python -c` reading the stream in-process",
    "find_exec_xargs": "one `python -c` using `pathlib.Path.rglob`, which never leaves the "
                       "interpreter",
}


def _repo_config(cwd: str | None) -> "Path | None":
    if not cwd:
        return None
    try:
        here = Path(cwd).resolve()
    except Exception:
        return None
    for candidate in (here, *here.parents):
        config = candidate / _CONFIG_NAME
        if config.is_file():
            return config
    return None


def _policy_is_deny(config: Path) -> bool:
    """True only when the frontmatter explicitly declares the deny policy.

    A narrow string scan over the frontmatter rather than a YAML parse: this sits on the
    PreToolUse path, a YAML import is not free, and an unparseable config must read as "no policy"
    (allow) rather than raise.
    """
    try:
        text = config.read_text(encoding="utf-8")
    except OSError:
        return False
    if not text.startswith("---"):
        return False
    end = text.find("\n---", 3)
    front = text[3:end] if end != -1 else text[3:4000]
    for line in front.splitlines():
        stripped = line.strip()
        if not stripped.startswith(_POLICY_KEY):
            continue
        _, _, value = stripped.partition(":")
        return value.split("#", 1)[0].strip().strip("\"'").lower() == _DENY_VALUE
    return False


def _classify(cmd: str, dialect_name: str = "BASH") -> "list[str]":
    """Shape names the engine's classifier finds in `cmd`. Empty on any failure (fail open)."""
    try:
        from _engine_root import resolve_claude_klabauter_root
    except Exception:
        return []
    try:
        root = resolve_claude_klabauter_root()
    except Exception:
        return []
    if not root:
        return []
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from coordinator_core.bash_guards._shape_classifier import classify_command
    except Exception:
        return []
    try:
        from coordinator_core.bash_guards._shape_classifier import Dialect
    except Exception:
        Dialect = None
    try:
        if Dialect is not None and dialect_name:
            classification = classify_command(cmd, dialect=getattr(Dialect, dialect_name))
        else:
            # Engine too old to carry `Dialect`: fall back to the default-bash call rather than
            # failing closed. A PowerShell payload then simply finds no bash shapes, which is the
            # behaviour before this change -- never a deny on a dialect we could not resolve.
            classification = classify_command(cmd)
    except Exception:
        return []
    names = []
    for match in getattr(classification, "matches", None) or []:
        shape = getattr(match, "shape", None)
        name = getattr(shape, "value", None) or getattr(shape, "name", None) or str(shape)
        if name:
            names.append(str(name).lower())
    return names


def _spawn_cost_clause(tool_name: str) -> str:
    """Name the cost the CALLER actually pays, not bash's.

    The prose quoted `bash.exe costs 200-500ms per spawn` unconditionally, and closed by offering
    "the PowerShell tool is always available". Once this guard started firing on PowerShell the
    first became false on exactly the new path and the second pointed the agent at a shell this
    guard now covers. Both were artefacts of a Bash-only guard; both are corrected rather than
    left as near-miss prose a reader would have to discount.
    """
    if tool_name == "PowerShell":
        return "a ForEach-Object/% pipeline stage runs its block once per input object on this host"
    return "bash.exe costs 200-500ms per spawn on this host"


def _compose_deny_message(shapes: "list[str]", tool_name: str = "Bash") -> Message:
    named = ", ".join(shapes)
    hints = [_ALTERNATIVES[s] for s in shapes if s in _ALTERNATIVES]
    remedy = hints[0] if hints else (
        "a single `python -c` doing the same work in one interpreter"
    )
    prose = (
        f"BLOCKED: this shape spawns one subprocess per iteration or pipe stage ({named}), and "
        f"{_spawn_cost_clause(tool_name)} — paid on a machine running many "
        f"concurrent sessions. Use {remedy}. {tool_name} itself is NOT banned here: a single read "
        f"of a known file is fine. It is the fan-out that is refused, not the tool. If a system "
        f"reminder suggested this shape, this policy outranks it — say so in your report rather "
        f"than routing around it."
    )
    return compose(prose, anchor=_WIKI_ANCHOR)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(data, dict):
        return 0

    tool_name = data.get("tool_name")
    if tool_name not in _SHAPED_TOOLS:
        return 0

    agent_id = data.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id.strip():
        return 0  # the EM itself — out of scope by design

    tool_input = data.get("tool_input")
    cmd = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(cmd, str) or not cmd.strip():
        return 0

    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else os.getcwd()
    config = _repo_config(cwd)
    if config is None:
        return 0

    try:
        if not _policy_is_deny(config):
            return 0
    except Exception:
        return 0

    shapes = _classify(cmd, _TOOL_DIALECTS.get(tool_name, "BASH"))
    if not shapes:
        return 0

    sys.stderr.buffer.write((render(_compose_deny_message(shapes, tool_name)) + "\n").encode("utf-8"))
    return 2


if __name__ == "__main__":
    sys.exit(main())
