"""PreToolUse(Bash|PowerShell) hook: make the repo-setup precondition
"never target ~/.claude" an executable refusal, not prose.

THE DEFECT THIS CLOSES: ``coordinator/skills/repo-setup/SKILL.md`` line 37
already NAMES ``~/.claude`` (Claude Central, the ``example-doctrine-mirror-repo-v3`` backup
tree) as a non-target root -- but that line is prose the orchestrating agent
reads and can misapply, and ~/.claude carried a stray repo-setup scaffold as
a result (``state/bug-backlog/2026-08-15-repo-setup-scaffolded-claude-as-a-
projec-7439cdca3aa3.yaml``). ``coordinator:new-project`` delegates its own
onboarding half back to this same skill (SKILL.md line 15), so one guard at
this seam covers both entry points without a second, drifting copy of the
same predicate.

SEAM CHOICE. The actual scaffold-writing mechanism
(``coordinator_core.install.scaffold_structure``, invoked via
``python3 -m coordinator_core.install.scaffold_structure``) and the
target-root resolver it depends on
(``"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/
repo-setup-args-and-register" resolve-target-root``) are BOTH engine-plane
code -- this repo holds no standing cross-repo commit grant to edit them
(``docs/decisions/DR-127-...``). This hook is therefore
authored DoE-resident, on the Bash/PowerShell command SURFACE, mirroring the
precedent ``guard-doctrine-surface-bash-write.py`` already sets for "the
predicate is plugin-resident permanently, so the guard is plugin-resident
too, even though the thing it protects is invoked via a Bash command
touching engine-owned code": it denies the Bash/PowerShell command BEFORE
the engine-side scaffold CLI (or its target-root resolver) ever runs,
regardless of which entry point issued it.

DETECTION STRATEGY. Fires only when the command text names one of the
scaffold-mechanism CLIs (``repo-setup-args-and-register`` or
``coordinator_core.install.scaffold_structure`` / ``scaffold_structure``).
The candidate target root is: an explicit ``--root``/``--target`` flag value
if the command carries one (resolved against the payload's ``cwd`` if
relative), else the payload's own ``cwd`` (mirrors SKILL.md's own "$_TARGET_
ROOT ... defaults to $(pwd)" resolution rule). PATH-SHAPE ROBUSTNESS: never
a string compare. The candidate and Claude Home are both resolved to real,
canonical, case-normalized paths via ``pathlib.Path.resolve()`` (which
follows NTFS junctions on Windows since Python 3.8, unlike
``os.path.islink()`` -- ``~/.claude/machine-local`` is one such junction and
must never be mistaken for "not a link, so not worth resolving") before
comparison.

CLAUDE HOME RESOLUTION -- never ``os.path.expanduser`` naively, which
ignores a monkeypatched ``HOME`` in a way that has clobbered a real
``.doe-root`` in this repo's own install history
(``docs/wiki/...windows-subprocess-exec-traps`` lineage). Resolution order,
explicit and testable via an injected env mapping: ``CLAUDE_CONFIG_DIR``
(if set, IS the Claude Home) -> ``HOME`` (POSIX) -> ``USERPROFILE``
(Windows), each joined with ``.claude`` for the latter two. No fallback to
``Path.home()`` -- an unresolvable Claude Home means this hook has nothing
to compare against, so it fails OPEN (allow) rather than guessing.

LEADING ``cd``/``Set-Location`` HANDLING. When no ``--root``/``--target``
flag is present, the candidate is no longer unconditionally the payload's
``cwd`` -- a leading ``cd <path> &&``/``cd <path> ;`` (or PowerShell
``Set-Location``/``sl``, optionally with ``-Path``) prefix is treated as the
effective cwd for candidate resolution instead, mirroring what the shell
would actually do before the scaffold command runs. Handles a quoted or
unquoted path, ``~`` and ``$HOME``/``${HOME}``/``%USERPROFILE%``/
``$env:USERPROFILE`` shorthand (via ``_expand_home_shorthand``), and both
``&&`` and ``;`` separators. Only a SINGLE leading ``cd`` is honored (the
command must start with it, modulo leading whitespace) -- a `cd` appearing
later in a `;`-chained command, or a second `cd` after the first, is
out of scope; see NEGATIVE-SPEC below.

NEGATIVE-SPEC -- ``--batch`` mode is deliberately UNHANDLED. Batch mode
reads repo paths from ``~/.claude/working-repos.yaml`` at runtime and loops
the single-repo flow per listed repo; this hook cannot see that list
without executing the very command it is trying to gate, so a
``--batch``-shaped command is never denied by this hook on the strength of
its own command text alone (it carries no ``--root``/``--target`` naming
``~/.claude`` and its ``cwd`` is wherever the batch runner itself was
launched from, not the per-repo target). Closing that gap is a
``working-repos.yaml`` data-hygiene concern (never list ``~/.claude`` as a
working repo), not a command-classification one -- named here rather than
silently out of scope.

NEGATIVE-SPEC -- only ONE leading ``cd``/``Set-Location`` is honored. A
command chaining a SECOND ``cd`` after the first (``cd a && cd b && python3
-m coordinator_core.install.scaffold_structure``), or one buried mid-command
rather than at the very start, is not walked -- the candidate resolves
against the FIRST ``cd``'s target only. Closing that fully would mean
simulating shell cwd-tracking across the whole command, which is out of
scope for a cheap pre-execution text classifier; a command shaped this way
is not denied by this hook on the strength of its own text alone.

Contract (mirrors ``guard-doctrine-surface-bash-write.py``): reads
PreToolUse JSON from stdin, exit 0 = allow (silent), exit 2 = BLOCK (stderr
message shown to the user). Any failure to decode stdin JSON, a missing/
non-string ``tool_input.command``, an unresolvable Claude Home, or any
exception while resolving paths fails OPEN -- this hook must never brick an
ordinary Bash/PowerShell call.

Spec backlink: state/bug-backlog/2026-08-15-repo-setup-scaffolded-claude-as-
a-projec-7439cdca3aa3.yaml
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _message_envelope import Message, compose, render  # noqa: E402

_COMMAND_TOOL_NAMES = ("Bash", "PowerShell")

#: Identifiers naming the engine-plane scaffold mechanism (see module
#: docstring "SEAM CHOICE"). Review: code-reviewer (Finding 3) -- a bare
#: substring test denied a command that merely MENTIONS one of these
#: strings (a `grep scaffold_structure ...`, a `git log --grep=...`) without
#: invoking it, when cwd happened to be Claude Home. `_names_scaffold_
#: mechanism` below requires the marker to appear in an INVOKED-program-ish
#: position, not merely anywhere in the text.
_SCAFFOLD_MECHANISM_MARKERS = (
    "repo-setup-args-and-register",
    "coordinator_core.install.scaffold_structure",
    "scaffold_structure",
)

#: ``--root <val>`` / ``--target <val>`` (also ``--root=val``), tolerating a
#: single- or double-quoted value. Mirrors SKILL.md's own documented flag
#: pair (``--root``, alias ``--target``).
_ROOT_FLAG_RE = re.compile(r"--(?:root|target)(?:=|\s+)(\"[^\"]*\"|'[^']*'|\S+)")

#: A leading ``cd <path> &&``/``cd <path> ;`` or PowerShell
#: ``Set-Location``/``sl`` (optionally ``-Path``) prefix -- see module
#: docstring "LEADING cd/Set-Location HANDLING". Must anchor the START of
#: the command (modulo leading whitespace); only ONE such prefix is
#: recognized (see NEGATIVE-SPEC).
_LEADING_CD_RE = re.compile(
    r"""^\s*(?:cd|Set-Location|sl)\s+(?:-Path\s+)?
        ("[^"]*"|'[^']*'|\S+)
        \s*(?:&&|;)""",
    re.IGNORECASE | re.VERBOSE,
)


def _resolve_claude_home(env: "dict[str, str]") -> "str | None":
    """Canonical, resolved path to Claude Home, or ``None`` if unresolvable.

    Never ``os.path.expanduser`` -- see module docstring. Order: an explicit
    ``CLAUDE_CONFIG_DIR`` IS the Claude Home; otherwise ``HOME``/
    ``USERPROFILE`` joined with ``.claude``."""
    config_dir = env.get("CLAUDE_CONFIG_DIR")
    if config_dir:
        try:
            return str(Path(config_dir).resolve())
        except OSError:
            pass
    for key in ("HOME", "USERPROFILE"):
        val = env.get(key)
        if not val:
            continue
        try:
            return str((Path(val) / ".claude").resolve())
        except OSError:
            continue
    return None


def _expand_home_shorthand(raw: str, env: "dict[str, str]") -> str:
    """Expand a literal leading ``~`` or ``$HOME``/``${HOME}``/``%USERPROFILE%``
    token in ``raw`` against ``env`` -- this hook inspects the command text
    BEFORE any shell ever runs it, so a POSIX shell's own tilde/variable
    expansion has not happened yet by the time ``tool_input.command`` is
    read. Falls back to ``raw`` unchanged when the referenced variable is
    absent from ``env``, or no such shorthand is present."""
    home = env.get("HOME") or env.get("USERPROFILE")
    if raw.startswith("~") and home:
        return home + raw[1:]
    for token in ("${HOME}", "$HOME", "%USERPROFILE%", "$env:USERPROFILE"):
        if raw.startswith(token) and home:
            return home + raw[len(token) :]
    return raw


def _names_scaffold_mechanism(cmd: str) -> bool:
    """True iff ``cmd`` invokes (not merely mentions) one of
    ``_SCAFFOLD_MECHANISM_MARKERS`` -- see Finding 3 in this module's
    docstring history. A marker occurrence counts as "invoked" when it sits
    at the very start of the command, immediately follows a ``python3 -m``
    / ``python -m`` module flag, or is preceded by a quote or a path
    separator (i.e. it names a program/module/path being RUN). A marker
    that appears only as plain text elsewhere -- a ``grep`` pattern, a
    ``--grep`` value, a comment -- does not count, so a command that merely
    mentions the marker string is not ruled IN for the (denying) path
    classification below."""
    for marker in _SCAFFOLD_MECHANISM_MARKERS:
        start = 0
        while True:
            idx = cmd.find(marker, start)
            if idx == -1:
                break
            if idx == 0:
                return True
            prefix = cmd[:idx]
            if prefix[-1] in "\"'/\\":
                return True
            if re.search(r"-m\s+$", prefix):
                return True
            start = idx + 1
    return False


def _leading_cd_target(cmd: str, cwd: "str | None", env: "dict[str, str]") -> "str | None":
    """The effective cwd after a leading ``cd``/``Set-Location`` prefix, or
    ``None`` if ``cmd`` doesn't open with one -- see module docstring
    "LEADING cd/Set-Location HANDLING"."""
    match = _LEADING_CD_RE.match(cmd)
    if not match:
        return None
    raw = _expand_home_shorthand(match.group(1).strip("'\""), env)
    candidate = Path(raw)
    if not candidate.is_absolute() and cwd:
        candidate = Path(cwd) / candidate
    return str(candidate)


def _extract_candidate_root(cmd: str, cwd: "str | None", env: "dict[str, str]") -> "str | None":
    """The path this command would resolve ``$_TARGET_ROOT`` to, per
    SKILL.md's own "Target-root resolution" preamble: an explicit
    ``--root``/``--target`` value (resolved against ``cwd`` if relative);
    else a leading ``cd``/``Set-Location`` prefix's target (resolved against
    ``cwd`` if relative -- see ``_leading_cd_target``); else ``cwd`` itself
    when neither is present."""
    match = _ROOT_FLAG_RE.search(cmd)
    if match:
        raw = _expand_home_shorthand(match.group(1).strip("'\""), env)
        candidate = Path(raw)
        if not candidate.is_absolute() and cwd:
            candidate = Path(cwd) / candidate
        return str(candidate)
    cd_target = _leading_cd_target(cmd, cwd, env)
    if cd_target is not None:
        return cd_target
    return cwd


def is_denied_repo_setup_claude_home(
    cmd: str, cwd: "str | None", env: "dict[str, str]"
) -> bool:
    """The whole predicate, isolated from stdin/exit-code plumbing so it is
    directly unit-testable. Returns True (deny) iff ``cmd`` invokes the
    scaffold mechanism AND its resolved candidate target root is Claude
    Home."""
    if not _names_scaffold_mechanism(cmd):
        return False

    claude_home = _resolve_claude_home(env)
    if not claude_home:
        return False  # cannot resolve what to compare against -- fail open

    candidate = _extract_candidate_root(cmd, cwd, env)
    if not candidate:
        return False  # no cwd and no explicit flag -- nothing to compare

    try:
        resolved_candidate = str(Path(candidate).resolve())
    except OSError:
        return False  # unresolvable candidate path -- fail open

    return resolved_candidate == claude_home


#: No wiki anchor. The obvious target (`docs/wiki/doe-altitude-and-shared-
#: infra.md`) is a fleet-private page outside `SEED_WIKIS`, so it 404s for
#: every reader this hook actually reaches -- a sibling repo's checkout or an
#: OSS install, which is where `repo-setup` runs. The prose below therefore
#: carries the whole diagnosis inline (what ~/.claude is, why it is not a
#: target, and the command that IS) rather than pointing at further reading
#: the denied caller cannot open. Do not re-add a citation here without first
#: promoting its target into the seed allowlist; a pointer that 404s is worse
#: than none, because it reads as an answer.


def _compose_deny_message() -> Message:
    prose = (
        "BLOCKED: repo-setup's scaffold cannot target ~/.claude (Claude "
        "Central / example-doctrine-mirror-repo-v3) -- it is a backup repo, not a working "
        "tree, and DoE-claude is already its own project. Run repo-setup "
        "against the DoE-claude clone instead: "
        "/repo-setup --root <path-to-DoE-claude>."
    )
    return compose(prose)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0  # nothing to classify -- fail open

    if data.get("tool_name") not in _COMMAND_TOOL_NAMES:
        return 0

    tool_input = data.get("tool_input")
    cmd = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(cmd, str) or not cmd:
        return 0

    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else None

    try:
        denied = is_denied_repo_setup_claude_home(cmd, cwd, dict(os.environ))
    except Exception:
        return 0  # any resolution failure -- fail open, never brick the call

    if not denied:
        return 0

    sys.stderr.buffer.write((render(_compose_deny_message()) + "\n").encode("utf-8"))
    return 2


if __name__ == "__main__":
    sys.exit(main())
