"""check-launch-shape — assert the Windows `claude` launch chain is direct-child.

WHAT THIS PROTECTS. On Windows the interactive ``claude.exe`` must be a DIRECT
child of the invoking shell. Any intermediate ``cmd.exe`` or ``python.exe``
corrupts the console input mode: xterm focus-report sequences (ESC[I / ESC[O,
DECSET 1004) stop being consumed and leak into the input stream as literal
``[I``/``[O``, keystrokes misroute to a phantom row, and the host shell's prompt
is left corrupted after the session exits. The only mitigation available to an
operator hitting it is disabling the ``claude`` shim, which silently strips the
coordinator plugin from every session on the box — so a defect here presents as
"the entire operating system is gone", not as a rendering glitch.

WHY IT IS A SEPARATE PROBE rather than a manifest entry. The install manifest's
``system_prerequisites`` declares what must be PRESENT to install (git, python,
pwsh). This is not a prerequisite; it is a post-install invariant about how two
correctly-present artifacts resolve against each other on PATH. Those are
different questions, and folding this into the prerequisite list would answer
neither well.

SCOPE — the claude-klabauter/DoE dogfood shape only. The ``--doe-root`` seam exists only
where a DoE-claude clone and a claude-klabauter clone are both present and the
`claude` shim passes the pointer on every launch. OSS coordinator-claude and
Claude-klabauter installs never take that path, so this SKIPs rather than FAILs
when the rendered launcher pair is absent.

Naked Python, single process, no subprocess fan-out: this runs on a machine that
pays a severe per-spawn tax and is shared with many concurrent sessions.

No DoE-relative paths: every path this probe touches (the launcher pair, the
shim) is resolved from PATH or `$CLAUDE_HOME`/home at runtime, on the machine
being probed — never from this file's own on-disk location — so no adaptation
was needed for its move from DoE-claude into claude-klabauter
(docs/plans/2026-09-18-doe-holds-no-scripts.md § Path resolution, "session
repo"/"doctrine asset" classes do not apply here).

Exit codes: 0 = PASS or SKIP, 1 = FAIL (a real launch-shape defect).

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W2-C5.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_LAUNCHER_PS1 = "claude-doe.ps1"
_LAUNCHER_CMD = "claude-doe.cmd"
_LAUNCHER_BARE = "claude-doe"


def _path_dirs() -> "list[Path]":
    seen, out = set(), []
    for raw in os.environ.get("PATH", "").split(os.pathsep):
        raw = raw.strip().strip('"')
        if not raw:
            continue
        p = Path(raw)
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _shim_path() -> "Path | None":
    home = Path(os.environ.get("CLAUDE_HOME") or Path.home())
    cand = home / ".claude" / "shell" / "claude-doe-shim.ps1"
    return cand if cand.is_file() else None


def _check_no_shadow(failures: "list[str]") -> "Path | None":
    """The first PATH directory offering a `claude-doe` must be the one that
    also carries `claude-doe.ps1`.

    This is the defect that actually shipped: claude-klabauter's substrate generated a
    generic `claude-doe` + `claude-doe.cmd` forwarder pair into settings-home
    bin, which is PATH-prepended ahead of ~/.local/bin, so it shadowed the
    purpose-built launcher and every bare `claude-doe` ran the TUI three hops
    deep. Fixed at source, but PATH order is machine state — it can regress
    from a reordering that touches no coordinator file at all, which is exactly
    why this is a live probe and not a template assertion.
    """
    real: "Path | None" = None
    for d in _path_dirs():
        try:
            has_ps1 = (d / _LAUNCHER_PS1).is_file()
            has_any = has_ps1 or (d / _LAUNCHER_CMD).is_file() or (d / _LAUNCHER_BARE).is_file()
        except OSError:
            continue
        if not has_any:
            continue
        if has_ps1:
            real = d
            break
        failures.append(
            f"a `claude-doe` in {d} shadows the real launcher: it offers no "
            f"{_LAUNCHER_PS1}, so first-hit resolution reaches a generic forwarder "
            "that nests the interactive TUI under cmd.exe and python.exe. Remove it, "
            "or place the directory holding the real launcher pair earlier on PATH."
        )
        return None
    return real


def _enclosing_group(text: str, anchor: str) -> "str | None":
    """The balanced ``(...)`` group CONTAINING ``anchor``.

    Structural, not a fixed-width window. A window measured in characters from
    an anchor is a false-PASS generator: any reformat that pushes the defect
    past the window silently turns a FAIL into a PASS, and the reformat that
    does it is ordinary — a line continuation plus a few comment lines is
    enough. Measured: a 400-character window reported PASS on a shim that had
    been reverted to the broken first-hit form.
    """
    i = text.find(anchor)
    if i < 0:
        return None
    depth = 0
    start = None
    for j in range(i, -1, -1):
        c = text[j]
        if c == ")":
            depth += 1
        elif c == "(":
            if depth == 0:
                start = j
                break
            depth -= 1
    if start is None:
        return None
    depth = 0
    for k in range(start, len(text)):
        c = text[k]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start : k + 1]
    return None


def _group_after(text: str, anchor: str) -> "str | None":
    """The first balanced ``(...)`` group at or after ``anchor``."""
    i = text.find(anchor)
    if i < 0:
        return None
    j = text.find("(", i)
    if j < 0:
        return None
    depth = 0
    for k in range(j, len(text)):
        c = text[k]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[j : k + 1]
    return None


def _check_shim_scans(shim: Path, failures: "list[str]") -> None:
    text = shim.read_text(encoding="utf-8", errors="replace")
    if "claude-doe.ps1" not in text:
        failures.append(
            f"{shim} never looks for {_LAUNCHER_PS1}: it falls through to `& claude-doe`, "
            "which PATHEXT-resolves to claude-doe.CMD and interposes a cmd.exe."
        )
        return
    group = _enclosing_group(text, "Get-Command claude-doe")
    if group is None:
        failures.append(
            f"{shim} has no parseable `Get-Command claude-doe` expression — it cannot be "
            "confirmed to scan PATH for the real launcher."
        )
        return
    if "Select-Object -First 1" in group:
        failures.append(
            f"{shim} takes the FIRST resolved claude-doe rather than scanning for the "
            f"directory that actually contains {_LAUNCHER_PS1}. A shadowing forwarder "
            "earlier on PATH then wins and the launch nests."
        )


def _check_launcher_consumes_doe_root(launcher_dir: Path, failures: "list[str]") -> None:
    ps1 = launcher_dir / _LAUNCHER_PS1
    text = ps1.read_text(encoding="utf-8", errors="replace")
    # The balanced group, not a split on the first ")". The array is routinely
    # written one element per line with trailing comments, and any ")" in a
    # comment truncated the old split early — which silently dropped the tail of
    # the array, including the element being looked for. Measured: a multi-line
    # $selfFlags carrying --doe-root reported PASS.
    group = _group_after(text, "$selfFlags")
    if group is not None and "--doe-root" in group:
        failures.append(
            f"{ps1} lists --doe-root among its self-terminating flags, so a --doe-root "
            "launch — the shape the `claude` shim uses on EVERY launch — delegates the "
            "whole INTERACTIVE launch to the Python wrapper and nests claude.exe under "
            "python.exe. --doe-root must be consumed and folded into --print-plugin-dir."
        )


def main(argv: "list[str]") -> int:
    if os.name != "nt":
        print("[check-launch-shape] SKIP: Windows-only (the corruption is a Win32 console behaviour)")
        return 0

    failures: "list[str]" = []
    launcher_dir = _check_no_shadow(failures)

    if launcher_dir is None and not failures:
        print(
            "[check-launch-shape] SKIP: no rendered claude-doe launcher pair on PATH — "
            "not the claude-klabauter/DoE dogfood shape"
        )
        return 0

    if launcher_dir is not None:
        _check_launcher_consumes_doe_root(launcher_dir, failures)

    shim = _shim_path()
    if shim is not None:
        _check_shim_scans(shim, failures)

    if failures:
        print("[check-launch-shape] FAIL: the interactive claude.exe would not be a direct child of the shell")
        for f in failures:
            print(f"  - {f}")
        print(
            "  Reference: coordinator/docs/wiki/windows-process-spawn-and-console.md "
            "§ Interactive launch (DoE-claude)"
        )
        return 1

    where = launcher_dir if launcher_dir is not None else "(no launcher dir)"
    print(f"[check-launch-shape] PASS: claude.exe launches as a direct child (launcher: {where})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
