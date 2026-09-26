"""Pure predicate for the hook-script-deregistration guard: does this commit
delete (or rename away) a script under `coordinator/hooks/scripts/` while
HEAD's `coordinator/hooks/hooks.json` still registers it, without also
removing that registration in the same commit?

THE HAZARD. `coordinator/hooks/hooks.json` is read once at session start and
cached (`HOOKS-JSON-REGISTRATION-STALENESS`). Every already-running session
keeps invoking whatever script hooks.json named at boot, whatever the
working tree does afterward. A working-tree deletion of a registered script,
committed without a matching hooks.json edit, therefore does not fail
loudly at the point of harm -- it degrades every booted session's next call
into that script's fail-open banner (`_hook_boot.py`), silently dropping
whatever guard the script provided until someone reads the banner and
notices. `state/bug-backlog/2026-07-29-deleting-a-registered-hook-script-is-
an-e9b2e6b3a200.yaml` is the row this closes; a commit-time parity test
(`test_hook_registrations_fail_open.py::test_every_referenced_hook_script_
exists`) already catches the WORKING-TREE half of this (a script hooks.json
names that is not on disk) -- this module is the other half: DENY the
commit that creates that state in the first place, rather than merely
detecting it after the fact on whoever next runs pytest.

WHY registration is read from HEAD, not the working tree. The question this
guard answers is "does this commit remove coverage a RUNNING SESSION relies
on" -- a running session's cached roster is HEAD's hooks.json as of its last
boot/reload, not whatever is mid-edit in the working tree. A script hooks.json
never registered (e.g. a scratch probe, or one already deregistered on a
prior commit) is not this hazard at all.

WHY a rename counts as a deletion. `git diff --raw -M` reports a rename as
one row carrying both paths, but the OLD name is exactly as gone from disk
under that filename as a straight delete -- a session's cached registration
still names the vanished old path either way. Only the OLD path is checked;
the new path is an ordinary add, not this hazard.

Negative-spec: this module never shells out to `git` and never reads a
filesystem path -- the wrapper (`guard-hook-script-deregistration-
precommit.py`) owns both, exactly as `_phantom_staged_deletion.py` and
`_doctrine_surface_netting.py` split their own untested git-facing wrapper
from a directly-unit-tested pure predicate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

STATUS_DELETE = "D"
STATUS_RENAME = "R"

#: (`test_hook_registrations_fail_open.py`'s `_SCRIPT_TOKEN_RE`) -- not a
_SCRIPT_TOKEN_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}(/[\w./-]+\.py)")

#: `${CLAUDE_PLUGIN_ROOT}` resolves to `coordinator/` (the plugin root) --
#: see `test_hook_registrations_fail_open.py`'s `_PLUGIN_ROOT = _HOOKS_DIR.parent`.
_PLUGIN_ROOT_REPO_RELATIVE = "coordinator"


@dataclass(frozen=True)
class Finding:

    path: str

    def render(self) -> str:
        return f"{self.path} -- removed from disk, still registered in hooks.json"


def parse_name_status_z(raw: str) -> "list[tuple[str, str, Optional[str]]]":
    fields = [f for f in raw.split("\0") if f != ""]
    rows: "list[tuple[str, str, Optional[str]]]" = []
    i = 0
    while i < len(fields):
        status = fields[i]
        if not status:
            i += 1
            continue
        code = status[0]
        if code in (STATUS_RENAME, "C"):
            if i + 2 >= len(fields):
                break
            rows.append((code, fields[i + 1], fields[i + 2]))
            i += 3
            continue
        if i + 1 >= len(fields):
            break
        rows.append((code, fields[i + 1], None))
        i += 2
    return rows


def vacated_paths(rows: Iterable["tuple[str, str, Optional[str]]"]) -> "list[str]":
    vacated: "list[str]" = []
    for status, old, new in rows:
        if status == STATUS_DELETE:
            vacated.append(old)
        elif status == STATUS_RENAME and new is not None and new != old:
            vacated.append(old)
    return vacated


def extract_registered_scripts(hooks_json_text: str) -> "set[str]":
    """Every `coordinator/hooks/scripts/<name>.py`-shaped path hooks.json's
    text registers via the `${CLAUDE_PLUGIN_ROOT}` token, as a repo-root-
    relative path comparable against `git diff` output. Textual, not a JSON
    walk -- identical extraction to the registration-parity test's own
    `_SCRIPT_TOKEN_RE`, so this guard and that test never disagree about
    what counts as "registered"."""
    return {
        _PLUGIN_ROOT_REPO_RELATIVE + rel
        for rel in _SCRIPT_TOKEN_RE.findall(hooks_json_text)
    }


def classify(
    rows: Iterable["tuple[str, str, Optional[str]]"],
    *,
    head_hooks_json_text: Optional[str],
    hooks_json_touched: bool,
    staged_hooks_json_text: Optional[str],
) -> "list[Finding]":
    if not head_hooks_json_text:
        return []

    head_registered = extract_registered_scripts(head_hooks_json_text)
    if not head_registered:
        return []

    if hooks_json_touched:
        still_registered_after = (
            extract_registered_scripts(staged_hooks_json_text)
            if staged_hooks_json_text
            else set()
        )
    else:
        still_registered_after = head_registered

    findings: "list[Finding]" = []
    for path in vacated_paths(rows):
        if path in head_registered and path in still_registered_after:
            findings.append(Finding(path=path))
    return findings


def render_report(findings: "list[Finding]", override_env: str) -> str:
    lines = [
        f"BLOCKED: this commit removes {len(findings)} hook script(s) that "
        "HEAD's coordinator/hooks/hooks.json still registers, without also "
        "removing the registration in this commit.",
        "",
        "Every already-running session cached its hook roster from hooks.json at",
        "boot and keeps invoking whatever it named then. Deleting the script out",
        "from under a live registration silently degrades those sessions' next",
        "call into a fail-open banner -- the guard the script provided is gone",
        "with no signal until someone reads it.",
        "",
    ]
    lines += [f"  {f.render()}" for f in findings]
    lines += [
        "",
        "Deregister and delete in the SAME commit: stage the hooks.json edit that",
        "removes this entry alongside the script deletion.",
        "",
        f"If the deregistration is genuinely landing separately, set {override_env}=1 "
        "for this commit.",
    ]
    return "\n".join(lines)
