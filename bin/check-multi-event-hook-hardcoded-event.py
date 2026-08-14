"""bin/check-multi-event-hook-hardcoded-event.py — Tripwire: prevent a hook
script registered on MORE THAN ONE event in hooks.json from hardcoding the
`hookEventName` value it emits in its `hookSpecificOutput` envelope.

Purpose: Claude Code validates that hookSpecificOutput.hookEventName matches
the event that actually fired the hook, and hard-errors otherwise ("Hook
returned incorrect event name: expected 'Stop' but got 'PostToolUse'"). A
script registered on N>=2 events can only be correct for at most one of
those events if it hardcodes a single literal — it must instead echo the
incoming `hook_event_name` from its stdin payload.

Origin incident (2026-07-20, this repo): runtime-tripwire-em-check.py was
registered on Stop, UserPromptSubmit, and PostToolUse:Agent but hardcoded
`"hookEventName": "PostToolUse"`. 2 of 3 registrations hard-errored 100% of
the time whenever the advisory was non-empty — silent whenever the advisory
was empty, which is why it went unnoticed for weeks. This guard is the
ratchet against that bug class recurring.

Detection model: parse hooks.json structurally to build a map of hook
script path -> set of registered event names. For every script registered
on >=2 distinct events, resolve it on disk and scan its source for a
HARDCODED `hookEventName` assignment — the assignment TARGET must be a
quoted `hookEventName` literal (JSON key, Python dict key, or shell var
name) and the assigned VALUE must itself be a quoted string literal. An
assignment to a variable/expression (`"hookEventName": event`) is NOT
flagged — only the direct literal-to-literal shape is. This is why a
constant like `_VALID_HOOK_EVENTS = ("Stop", "UserPromptSubmit",
"PostToolUse")` sitting near the word "hookEventName" elsewhere in the same
file does not false-fire: the assignment target text immediately preceding
the `:`/`=` must be `hookEventName` itself, not some other identifier that
happens to also mention an event name string.

Comment-stripping is best-effort only (line-oriented `#`-strip for
Python/shell sources) — a `hookEventName` occurrence inside a triple-quoted
docstring or a string literal that itself contains a `#` is not reliably
excluded. This mirrors the best-effort posture of check-sh-suffix-polyglot.py
and check-machine-path-leak.py's line-scan fallback.

Usage:
    check-multi-event-hook-hardcoded-event.py [--hooks-json <path>]

    --hooks-json <path>   Explicit path to hooks.json. Defaults to
                          hooks/hooks.json resolved via
                          coordinator_data_root.data_root("hooks") (co-located,
                          then resident in the coordinator doctrine repo — hooks/ moved
                          there in the 2026-07-22 executable-surface migration; see
                          DR-047).

Exit codes:
    0 — OK: no multi-event hook script hardcodes hookEventName
    1 — VIOLATION: >=1 multi-event hook script hardcodes hookEventName
    2 — ERROR: unexpected failure (hooks.json missing/unparseable, bad argument)

Output:
    stdout — human-readable status lines
    stderr — violation details and error messages

Negative-spec (hard-won):
    - Does NOT flag a script registered on exactly one event — hardcoding is
      legitimate there (there is only one possible correct value).
    - Does NOT flag an assignment whose value is a variable/expression, only
      a literal-to-literal shape (`"hookEventName": "PostToolUse"`).
    - Does NOT crash on a command entry that references no script under
      hooks/scripts/, or a registered script missing from disk — both are
      reported as a skip/warning, never a violation, never a crash.
"""

from __future__ import annotations

import json
import os
import re
import sys

PROG = "check-multi-event-hook-hardcoded-event.py"

BIN_DIR = os.path.dirname(os.path.abspath(__file__))
COORDINATOR_DIR = os.path.dirname(BIN_DIR)

_LIB_DIR = os.path.join(BIN_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)


def _default_hooks_json() -> str:
    """Resolve the default hooks.json path via `coordinator_data_root.data_root()`'s
    co-located/DoE-resident two-rung chain, not a bare `__file__`-relative walk.

    The 2026-07-22 executable-surface migration moved this script into
    claude-klabauter while `hooks/` stayed in DoE-claude (DR-047 contract/engine
    split), so a `coordinator/hooks/hooks.json` walk relative to this file no
    longer lands anywhere. Resolved lazily (called only when no explicit
    --hooks-json is given) so an unresolvable default cannot explode at import
    time and an explicit override never pays this cost.
    """
    from coordinator_data_root import data_root

    return str(data_root("hooks") / "hooks.json")
# NOTE: the scripts dir is resolved per-run in main() as a sibling of the
# *effective* hooks.json (so an explicit --hooks-json fixture resolves its own
# scripts/), not from a module-level constant.

# Matches the script's basename as it appears embedded in a hooks.json
# command string, e.g. "...${CLAUDE_PLUGIN_ROOT}/hooks/scripts/foo.py ...".
_SCRIPT_REF_RE = re.compile(r"hooks/scripts/([A-Za-z0-9_.-]+)")

# Assignment-target-is-a-literal shape: a quoted or bare `hookEventName` key
# (JSON/Python dict key, or a shell/python variable name), followed by `:`
# or `=`, followed directly by a QUOTED STRING LITERAL value. Deliberately
# anchored on the key text immediately adjacent to the separator — this is
# what keeps `_VALID_HOOK_EVENTS = ("Stop", ...)` from matching: the
# assignment target there is `_VALID_HOOK_EVENTS`, not `hookEventName`.
_HARDCODED_ASSIGN_RE = re.compile(
    r"""['"]?hookEventName['"]?\s*[:=]\s*(['"])[A-Za-z]+\1"""
)


def _strip_comment(line: str) -> str:
    """Best-effort `#`-comment strip for Python/shell sources.

    Does not attempt to distinguish a `#` inside a string literal from a
    genuine comment marker — best-effort only, documented in the module
    docstring.
    """
    idx = line.find("#")
    if idx == -1:
        return line
    return line[:idx]


def _load_hooks_json(path):
    if not os.path.isfile(path):
        sys.stderr.write("{}: ERROR — hooks.json not found: {}\n".format(PROG, path))
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write("{}: ERROR — failed to parse {}: {}\n".format(PROG, path, e))
        return None


def _build_script_event_map(hooks_data):
    """Return {script_basename: set(event_name, ...)}.

    hooks.json structure: top-level keys are event names (Stop,
    UserPromptSubmit, PreToolUse, ...), each mapping to a list of groups,
    each group carrying a `matcher` and a `hooks` list whose entries carry
    a `command` string embedding the script path. A command referencing no
    script under hooks/scripts/ contributes nothing (gracefully skipped).
    """
    script_events = {}

    hooks_section = hooks_data.get("hooks") if isinstance(hooks_data, dict) else None
    if not isinstance(hooks_section, dict):
        return script_events

    for event_name, groups in hooks_section.items():
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict):
                continue
            entries = group.get("hooks")
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                command = entry.get("command")
                if not isinstance(command, str):
                    continue
                m = _SCRIPT_REF_RE.search(command)
                if not m:
                    continue  # no script/ reference in this command — skip
                script_name = m.group(1)
                script_events.setdefault(script_name, set()).add(event_name)

    return script_events


def _scan_script_for_hardcoded_event(abspath):
    """Return a list of (lineno, matched_text) for hardcoded hookEventName
    assignments found in the file, after best-effort comment-stripping.
    """
    violations = []
    try:
        with open(abspath, "r", encoding="utf-8", errors="replace") as fh:
            for lineno, raw_line in enumerate(fh, start=1):
                line = _strip_comment(raw_line)
                m = _HARDCODED_ASSIGN_RE.search(line)
                if m:
                    violations.append((lineno, m.group(0).strip()))
    except OSError:
        pass
    return violations


def _print_help():
    sys.stdout.write(__doc__.strip() + "\n")


def main(argv):
    hooks_json_path = None

    args = list(argv)
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("-h", "--help"):
            _print_help()
            return 0
        elif arg == "--hooks-json":
            if i + 1 >= len(args):
                sys.stderr.write("{}: --hooks-json requires a path argument\n".format(PROG))
                return 2
            hooks_json_path = args[i + 1]
            i += 2
            continue
        else:
            sys.stderr.write("{}: unknown argument: {}\n".format(PROG, arg))
            return 2
        i += 1

    if hooks_json_path is None:
        try:
            hooks_json_path = _default_hooks_json()
        except RuntimeError as exc:
            sys.stderr.write(
                "{}: ERROR — could not resolve a default hooks.json: {}\n".format(PROG, exc)
            )
            return 2

    hooks_data = _load_hooks_json(hooks_json_path)
    if hooks_data is None:
        return 2

    script_events = _build_script_event_map(hooks_data)

    # scripts/ is always a sibling of hooks.json's own directory
    # (coordinator/hooks/hooks.json -> coordinator/hooks/scripts/), whether
    # the default path or an explicit --hooks-json fixture is in play.
    scripts_dir = os.path.join(os.path.dirname(os.path.abspath(hooks_json_path)), "scripts")

    multi_event_scripts = {
        name: events for name, events in script_events.items() if len(events) >= 2
    }

    violations = []
    checked = 0

    for script_name, events in sorted(multi_event_scripts.items()):
        abspath = os.path.join(scripts_dir, script_name)
        if not os.path.isfile(abspath):
            sys.stderr.write(
                "{}: WARN — registered script not found on disk, skipping: {}\n".format(
                    PROG, abspath
                )
            )
            continue

        checked += 1
        found = _scan_script_for_hardcoded_event(abspath)
        for lineno, matched_text in found:
            violations.append((abspath, lineno, matched_text, events))

    if violations:
        for abspath, lineno, matched_text, events in violations:
            event_list = ", ".join(sorted(events))
            value_m = re.search(r"""['"]([A-Za-z]+)['"]\s*$""", matched_text)
            value = value_m.group(1) if value_m else "?"
            sys.stderr.write(
                '{}:{}: hardcoded hookEventName "{}" but registered on {} events ({})\n'.format(
                    abspath, lineno, value, len(events), event_list
                )
            )
            sys.stderr.write(
                "  Remedy: echo the incoming `hook_event_name` from the stdin JSON payload\n"
                "          instead of hardcoding a single literal — see\n"
                "          runtime-tripwire-em-check.py::_hook_event_name for the pattern.\n"
            )
        return 1

    sys.stdout.write(
        "OK — {} multi-event hook(s) checked, no hardcoded hookEventName\n".format(checked)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
