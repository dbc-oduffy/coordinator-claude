#!/usr/bin/env python3
"""Govern the stock pyright-lsp / typescript-lsp plugins and check the pinned front binaries.

The stock plugins spawn their own pyright and typescript-language-server per session, so a
default session never reaches the warm front while they stay enabled. `--disable` flips their
`enabledPlugins` keys to false in the user-scope settings.json (clangd-lsp is never touched);
`--enable` flips them back; `--status` reports each key's state and whether ty, tsgo and
typescript-language-server resolve on PATH at the versions in lsp_front_pins.json, printing the
pinned install command for each mismatch. `--install` installs the pinned ty and tsgo and
re-verifies them (exit 1 on any mismatch or missing installer); `--doctor` prints one
`backend <tool> ...` line per front backend and exits 1 when ty or tsgo is missing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional, Sequence

_HERE = Path(__file__).resolve().parent
PINS_PATH = _HERE / "lsp_front_pins.json"

STOCK_KEYS = (
    "pyright-lsp@claude-plugins-official",
    "typescript-lsp@claude-plugins-official",
)

# (tool, pins key, binary, version argv tail, install-command template)
_BINARIES = (
    ("ty", "ty", "ty", ("--version",), "uv tool install ty=={version}"),
    ("tsgo", "tsgo", "tsgo", ("--version",), "npm install -g @typescript/native-preview@{version}"),
    (
        "typescript-language-server",
        "tsls",
        "typescript-language-server",
        ("--version",),
        "npm install -g typescript-language-server@{version}",
    ),
)

FRONT_BACKENDS = ("ty", "tsgo")

_VERSION_RE = re.compile(r"\d+(?:\.\d+)+(?:-[0-9A-Za-z.]+)?")

# (argv) -> (returncode, combined output)
Runner = Callable[[Sequence[str]], "tuple[int, str]"]


def claude_config_home(env: Optional[dict] = None) -> Path:
    """`CLAUDE_CONFIG_DIR` when set, else `~/.claude`."""
    config = (env if env is not None else os.environ).get("CLAUDE_CONFIG_DIR")
    return Path(config) if config else Path.home() / ".claude"


def settings_path(config_home: Optional[Path] = None) -> Path:
    return (config_home or claude_config_home()) / "settings.json"


def _read_settings(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {}
    data = json.loads(text) if text.strip() else {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def _write_settings(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def stock_state(path: Optional[Path] = None) -> dict[str, Optional[bool]]:
    """Stock key -> enabled bool, or None when the key is absent (the host default applies)."""
    plugins = _read_settings(path or settings_path()).get("enabledPlugins")
    plugins = plugins if isinstance(plugins, dict) else {}
    return {k: (plugins[k] if isinstance(plugins.get(k), bool) else None) for k in STOCK_KEYS}


def set_stock(enabled: bool, path: Optional[Path] = None) -> dict[str, Optional[bool]]:
    """Set exactly the stock keys to `enabled`; every other key and setting is preserved.

    Returns the prior state, so a caller can restore it.
    """
    path = path or settings_path()
    data = _read_settings(path)
    plugins = data.get("enabledPlugins")
    if not isinstance(plugins, dict):
        plugins = {}
    prior = {k: (plugins[k] if isinstance(plugins.get(k), bool) else None) for k in STOCK_KEYS}
    for key in STOCK_KEYS:
        plugins[key] = enabled
    data["enabledPlugins"] = plugins
    _write_settings(path, data)
    return prior


def load_pins(path: Optional[Path] = None) -> dict:
    return json.loads((path or PINS_PATH).read_text(encoding="utf-8"))


def _default_runner(argv: Sequence[str]) -> "tuple[int, str]":
    try:
        proc = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def binary_status(
    pins: Optional[dict] = None,
    which: Callable[[str], Optional[str]] = shutil.which,
    runner: Runner = _default_runner,
) -> list[dict]:
    """Per tool: resolved path, found version, pinned version, ok, and the install command on mismatch."""
    pins = pins if pins is not None else load_pins()
    rows = []
    for tool, pin_key, binary, tail, install in _BINARIES:
        pinned = pins[pin_key]
        resolved = which(binary)
        found = None
        if resolved:
            code, out = runner([resolved, *tail])
            if code == 0:
                versions = _VERSION_RE.findall(out)
                found = pinned if pinned in versions else (versions[0] if versions else None)
        ok = found == pinned
        rows.append(
            {
                "tool": tool,
                "path": resolved,
                "found": found,
                "pinned": pinned,
                "ok": ok,
                "install": None if ok else install.format(version=pinned),
            }
        )
    return rows


def _install_runner(argv: Sequence[str]) -> "tuple[int, str]":
    try:
        proc = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=900,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def install_backends(
    pins: Optional[dict] = None,
    which: Callable[[str], Optional[str]] = shutil.which,
    runner: Runner = _default_runner,
    install_runner: Runner = _install_runner,
) -> dict:
    """Install the pinned front backends, then re-verify them against the pins.

    Each install template is split into an argv list (never a shell string) whose first element
    is resolved through `which`. Returns `{"lines": [...], "ok": bool, "binaries": [...]}`; a
    missing installer is reported and fails the run before any install is attempted for it.
    """
    pins = pins if pins is not None else load_pins()
    lines: list[str] = []
    ok = True
    for tool, pin_key, _binary, _tail, template in _BINARIES:
        if tool not in FRONT_BACKENDS:
            continue
        argv = shlex.split(template.format(version=pins[pin_key]))
        resolved = which(argv[0])
        if not resolved:
            lines.append(f"installer {argv[0]} missing (needed for {tool})")
            ok = False
            continue
        code, out = install_runner([resolved, *argv[1:]])
        if code != 0:
            tail = out.strip().splitlines()[-1:] or [""]
            lines.append(f"install {tool} failed (exit {code}): {tail[0]}")
            ok = False
    rows = [r for r in binary_status(pins, which=which, runner=runner) if r["tool"] in FRONT_BACKENDS]
    for row in rows:
        if row["ok"]:
            lines.append(f"{row['tool']}: ok {row['found']}")
        else:
            found = row["found"] or ("not on PATH" if not row["path"] else "version unreadable")
            lines.append(f"{row['tool']}: MISMATCH {found}, pinned {row['pinned']}")
            ok = False
    return {"lines": lines, "ok": ok, "binaries": rows}


def doctor_backends(
    pins: Optional[dict] = None,
    which: Callable[[str], Optional[str]] = shutil.which,
    runner: Runner = _default_runner,
) -> dict:
    """One line per front backend; `ok` is False when any backend is unresolved (off-pin is reported, not failed)."""
    rows = [r for r in binary_status(pins, which=which, runner=runner) if r["tool"] in FRONT_BACKENDS]
    lines = []
    for row in rows:
        if not row["path"] or row["found"] is None:
            lines.append(f"backend {row['tool']} missing")
        elif not row["ok"]:
            lines.append(f"backend {row['tool']} at {row['found']}, pinned {row['pinned']}")
        else:
            lines.append(f"backend {row['tool']} ok {row['found']}")
    return {"lines": lines, "ok": all(r["path"] and r["found"] is not None for r in rows), "binaries": rows}


def project_opt_ins(project_dir: Optional[Path] = None) -> dict[str, list[str]]:
    """Stock key -> project-scope settings files that set it true. Reported, never overridden."""
    root = (project_dir or Path.cwd()) / ".claude"
    found: dict[str, list[str]] = {}
    for name in ("settings.json", "settings.local.json"):
        try:
            state = stock_state(root / name)
        except (ValueError, OSError):
            continue
        for key, value in state.items():
            if value is True:
                found.setdefault(key, []).append(str(root / name))
    return found


def status(
    settings: Optional[Path] = None,
    pins: Optional[dict] = None,
    project_dir: Optional[Path] = None,
    **kw,
) -> dict:
    path = settings or settings_path()
    return {
        "settings_path": str(path),
        "stock_plugins": {k: v for k, v in stock_state(path).items()},
        "project_opt_ins": project_opt_ins(project_dir),
        "binaries": binary_status(pins, **kw),
    }


def _render(report: dict) -> str:
    lines = [f"settings: {report['settings_path']}"]
    for key, state in report["stock_plugins"].items():
        lines.append(f"  {key}: {'absent' if state is None else ('enabled' if state else 'disabled')}")
    for key, files in report.get("project_opt_ins", {}).items():
        lines.append(f"  project opt-in: {key} enabled by {', '.join(files)}")
    for row in report["binaries"]:
        if row["ok"]:
            lines.append(f"  {row['tool']}: ok {row['found']} ({row['path']})")
        else:
            found = row["found"] or ("not on PATH" if not row["path"] else "version unreadable")
            lines.append(f"  {row['tool']}: MISMATCH {found}, pinned {row['pinned']}; install: {row['install']}")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--status", action="store_true")
    mode.add_argument("--disable", action="store_true", help="set the stock plugin keys false")
    mode.add_argument("--enable", action="store_true", help="set the stock plugin keys true")
    mode.add_argument("--install", action="store_true", help="install the pinned ty and tsgo, then verify")
    mode.add_argument("--doctor", action="store_true", help="report each front backend; exit 1 when one is missing")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.install or args.doctor:
        result = install_backends() if args.install else doctor_backends()
        print(json.dumps(result, indent=2) if args.json else "\n".join(result["lines"]))
        return 0 if result["ok"] else 1

    if args.status:
        report = status()
        print(json.dumps(report, indent=2) if args.json else _render(report))
        return 0
    prior = set_stock(enabled=args.enable)
    result = {"settings_path": str(settings_path()), "prior": prior, "set": args.enable}
    print(json.dumps(result, indent=2) if args.json else f"stock plugins set to {args.enable}; prior: {prior}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
