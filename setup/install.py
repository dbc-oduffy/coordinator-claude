#!/usr/bin/env python3
# install.py — coordinator-claude installer.
#
# Copies plugins to ~/.claude and registers them in Claude Code's JSON config
# files.
#
# Usage:
#   setup/install.py [--non-interactive] [--plugins coordinator,web-dev,...]
#
# --non-interactive  Skip prompts; install default-on plugins only
# --plugins LIST     Comma-separated list of plugins to install (coordinator
#                     always included)
#
# DELIBERATELY SELF-CONTAINED — not a claude-klabauter direct-import trampoline (unlike
# most other bash-to-Python ports in this migration). This file percolates
# verbatim into the standalone OSS `coordinator-claude` publish repo
# (`setup/install.py` there — see dist/publish-repo-setup/README.md), which
# ships to third-party end users with NO `claude-klabauter` sibling clone, no
# `coordinator_core`, and no `.claude-klabauter-root` machine-local pointer. A
# `from coordinator_core.ops... import main` trampoline would resolve the
# live-working-tree engine root — COORDINATOR_ENGINE_ROOT — successfully on a
# Claude-Central/DoE developer machine but raise/exit-1 for EVERY OSS
# consumer — silently bricking the installer that
# is, by definition, the very first thing a fresh user runs. Same reasoning
# as `dev-sync.py` (this directory) — see that file's header for the fuller
# version of this argument. There is accordingly no "transport failure" exit
# code carve-out (Porter-brief-addendum §3b) — this script has no transport;
# every subprocess it shells to is a sibling file in the SAME repo tree.
#
# Port source: this file (bash oracle, git history pre-2026-07-17).
# Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md
#     (BIG_PORT Wave C — install).
#
# bash 4.3+ is still required ON THE MACHINE (not by this script itself) —
# `coordinator-safe-commit`, installed by copy_plugins() below, uses
# `local -n` namerefs (bash 4.3+ only) and is invoked on essentially every
# commit thereafter. check_prerequisites() below probes for it and fails
# loud with brew remediation, matching the bash oracle's own top-of-script
# admission gate (policy: DR-148-require-bash4-on-macos) — just performed as
# an ordinary prerequisite check instead of a script-execution precondition,
# since THIS script no longer needs bash to run.
#
# Negative-spec (faithful to the bash oracle, not "fixed" here):
#   - Unknown CLI flags are silently ignored (no default/else case), matching
#     the original `for arg in "$@"; do case "$arg" in ... esac; done` loop.
#   - `--plugins` / `--profile` with no following value is a fail-loud usage
#     error (mirrors the oracle's `set -u` "unbound variable" abort on a
#     shifted-past-end `$1`), not a silent empty-string default.
#   - `native_path()` drops the bash oracle's `cygpath -w` preference (an
#     external-tool call) in favor of a pure-Python regex translation of the
#     same two path shapes (`/c/...` MSYS, `/mnt/c/...` WSL) it falls back to
#     — functionally equivalent for the paths this installer ever builds
#     (all under $HOME), narrower than cygpath's full UNC/relative coverage.

from __future__ import annotations

import importlib.util
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_NO_CONSOLE = {"creationflags": _CREATE_NO_WINDOW} if os.name == "nt" else {}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Plugin manifest schema (plugin.json with .claude-plugin/ layout,
# marketplace.json with metadata.pluginRoot) was stable by 2.0.0. We
# warn-don't-fail below this floor.
CLAUDE_CLI_MIN_VERSION = "2.0.0"

# Plugin metadata: (name, default, source_kind, description)
#
# default values:
#   on       — installed by default, included in non-interactive runs
#   off      — not installed by default, can be selected via --plugins or prompt
#   optional — NOT installed by default and NOT shown in main interactive list.
#              Prompted for separately as an opt-in add-on.
#
# source_kind values:
#   local  — plugin source is plugins/<name>/ in this repo; copied to install dir
#   npm    — plugin source is an npm package per marketplace.json; not copied,
#            registration in the marketplace manifest is sufficient
#   github — plugin source is a separate github repo; installed separately
#
# Versions are read dynamically from each plugin's plugin.json at install
# time. Non-local plugins have no local plugin.json; tracked only in the
# marketplace manifest.
PLUGIN_REGISTRY: List[Tuple[str, str, str, str]] = [
    ("coordinator", "on", "local", "Core pipeline and workflow skills (always enabled)"),
    ("web-dev", "on", "local", "Front-End and UX reviewers"),
    ("data-science", "on", "local", "Data Science reviewer"),
    ("deep-research", "on", "local", "Multi-agent deep research pipelines (web/repo/structured)"),
    ("game-dev", "off", "local", "Game Dev reviewer (Unreal Engine)"),
    ("notebooklm", "optional", "npm", "Media research via NotebookLM (Python add-on, launched via uvx)"),
]

USAGE = """Usage: setup/install.py [OPTIONS]

  --profile NAME          Install a preset plugin bundle (mutually exclusive
                          with --plugins):
                            core      coordinator only — minimal footprint
                            standard  coordinator, web-dev, data-science
                                      (excludes deep-research; opt in via
                                      --profile full or explicit --plugins)
                            full      coordinator, deep-research, web-dev,
                                      data-science, game-dev
  --non-interactive       Skip prompts; install default-on plugins only.
  --plugins LIST          Comma-separated list of plugins to install
                          (coordinator always included). Use --profile for
                          common presets; --plugins for fine-grained control.
  --install-notebooklm    Opt in to the NotebookLM add-on (Python/uvx add-on).
  --no-notebooklm         Skip the NotebookLM add-on prompt.
  --enable-codex          Opt in to the codex-review-gate skill (requires
                          the external openai/codex-plugin-cc plugin).
  --no-codex              Skip the codex-review-gate prompt.
  --name-personas         Force-prompt for persona naming at end of install
                          (even in non-interactive mode, where it is
                          otherwise skipped).
  --no-naming             Skip the persona-naming prompt entirely.
  -h, --help              Show this help.
"""


class UsageError(RuntimeError):
    """Raised on a CLI-usage error (bad flag value, conflicting flags,
    unknown profile) — main() converts this to a printed message + exit 1,
    matching the bash oracle's `echo "ERROR: ..."; exit 1` shape."""


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------


def detect_platform() -> str:
    """Mirrors the bash oracle's `uname -s` case + /proc/version WSL sniff,
    generalized to also recognize a native (non-MSYS) Windows Python."""
    system = platform.system()
    if system == "Linux":
        try:
            with open("/proc/version", "r", encoding="utf-8", errors="replace") as f:
                if "microsoft" in f.read().lower():
                    return "wsl"
        except OSError:
            pass
        return "linux"
    if system == "Darwin":
        return "darwin"
    if system.startswith(("MINGW", "MSYS", "CYGWIN")) or os.name == "nt":
        return "gitbash"
    return "unknown"


def native_path(path: str, plat: str) -> str:
    """Convert a POSIX-shaped path to the native OS path format required by
    JSON config files. See module header negative-spec re: cygpath."""
    if plat == "gitbash":
        m = re.match(r"^/([A-Za-z])/(.*)$", path)
        if m:
            drive, rest = m.groups()
            return f"{drive.upper()}:\\" + rest.replace("/", "\\")
        return path
    if plat == "wsl":
        m = re.match(r"^/mnt/([a-zA-Z])/(.*)$", path)
        if m:
            drive, rest = m.groups()
            return f"{drive.upper()}:\\" + rest.replace("/", "\\")
        return path
    return path


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


class Args:
    def __init__(self) -> None:
        self.non_interactive = False
        self.plugins_arg = ""
        self.profile_arg = ""
        # "" = ask (or skip in non-interactive), True/False = explicit override.
        self.notebooklm_opt: Optional[bool] = None
        self.codex_opt: Optional[bool] = None
        self.naming_opt: Optional[bool] = None
        self.help = False


def parse_args(argv: List[str]) -> Args:
    args = Args()
    i = 0
    n = len(argv)
    while i < n:
        a = argv[i]
        if a == "--non-interactive":
            args.non_interactive = True
        elif a.startswith("--plugins="):
            args.plugins_arg = a[len("--plugins="):]
        elif a == "--plugins":
            i += 1
            if i >= n:
                raise UsageError("--plugins: missing value")
            args.plugins_arg = argv[i]
        elif a.startswith("--profile="):
            args.profile_arg = a[len("--profile="):]
        elif a == "--profile":
            i += 1
            if i >= n:
                raise UsageError("--profile: missing value")
            args.profile_arg = argv[i]
        elif a == "--install-notebooklm":
            args.notebooklm_opt = True
        elif a == "--no-notebooklm":
            args.notebooklm_opt = False
        elif a == "--enable-codex":
            args.codex_opt = True
        elif a == "--no-codex":
            args.codex_opt = False
        elif a == "--name-personas":
            args.naming_opt = True
        elif a == "--no-naming":
            args.naming_opt = False
        elif a in ("-h", "--help"):
            args.help = True
            return args
        # else: silently ignored — matches the bash oracle's no-default-case loop.
        i += 1
    return args


def resolve_profile_alias(args: Args) -> None:
    """--profile is a thin alias over --plugins. Profiles are pinned (not
    computed dynamically) so future registry additions don't silently expand
    "full"."""
    if not args.profile_arg:
        return
    if args.plugins_arg:
        raise UsageError(
            "--profile and --plugins are mutually exclusive.\n"
            "       Use --profile for preset bundles or --plugins for a custom list."
        )
    if args.profile_arg == "core":
        args.plugins_arg = "coordinator"
    elif args.profile_arg == "standard":
        args.plugins_arg = "coordinator,web-dev,data-science"
    elif args.profile_arg == "full":
        args.plugins_arg = "coordinator,deep-research,web-dev,data-science,game-dev"
    else:
        raise UsageError(
            f"Unknown profile '{args.profile_arg}'.\n"
            "       Valid profiles: core, standard, full"
        )
    print(f"Profile '{args.profile_arg}' resolved to --plugins {args.plugins_arg}")
    print("")


# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------


def version_ge(a: str, b: str) -> bool:
    """True if dotted version string ``a`` >= ``b``, comparing up to 3
    numeric components (missing/non-numeric-suffixed components treat as 0).
    Pure-Python re-derivation of the bash oracle's `sort -V` / manual-compare
    dual path — collapsed to one path since Python needs no external `sort`
    probe."""

    def parts(v: str) -> List[int]:
        comps = v.split(".")
        out = []
        for idx in range(3):
            c = comps[idx] if idx < len(comps) else "0"
            m = re.match(r"^[0-9]*", c)
            digits = m.group(0) if m else ""
            out.append(int(digits) if digits else 0)
        return out

    return parts(a) >= parts(b)


def _run(argv: List[str], timeout: int) -> Optional[subprocess.CompletedProcess]:
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            **_NO_CONSOLE,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def check_bash_admission_gate(platform_name: str) -> None:
    """Probe for bash >= 4.3 on the machine (not for running THIS script —
    for `coordinator-safe-commit` and other still-bash tooling installed by
    copy_plugins() below). Warn-loud, non-fatal: unlike the bash oracle
    (which could not even parse past its own top-of-script guard on bash 3.2
    without aborting), a missing/old bash here does not block a Python-only
    install — it degrades the bash-dependent surfaces installed alongside it."""
    bash_path = shutil.which("bash")
    version_ok = False
    detected = "not found"
    if bash_path:
        proc = _run([bash_path, "-c", 'echo "${BASH_VERSINFO[0]}.${BASH_VERSINFO[1]}"'], timeout=10)
        if proc is not None and proc.returncode == 0:
            detected = proc.stdout.strip() or "unknown"
            m = re.match(r"^(\d+)\.(\d+)$", detected)
            if m:
                major, minor = int(m.group(1)), int(m.group(2))
                version_ok = (major, minor) >= (4, 3)
    if version_ok:
        print(f"bash       : {detected} (>= 4.3)")
        return
    print(f"WARNING: bash 4.3+ not detected on this machine (detected: {detected}).")
    print("         coordinator-safe-commit (invoked on essentially every commit)")
    print("         requires bash 4.3+ and will abort cryptically without it.")
    if platform_name == "darwin":
        print("         macOS ships bash 3.2 as /bin/bash. Install a current bash:")
        print("             brew install bash")
    print("         Continuing install — fix bash before your first commit.")
    print("")


def check_prerequisites(non_interactive: bool, platform_name: str) -> Tuple[bool, bool, str]:
    """Returns (uv_present, jq_present, uv_version). Exits (raises
    SystemExit) on a hard-fail prerequisite (claude CLI missing)."""
    if shutil.which("claude") is None:
        print("ERROR: Claude Code CLI not found on PATH.")
        print("Install from: https://docs.anthropic.com/en/docs/claude-code")
        sys.exit(1)

    claude_version = ""
    claude_path = shutil.which("claude")
    if claude_path:
        proc = _run([claude_path, "--version"], timeout=10)
        raw = proc.stdout if proc is not None else ""
        m = re.search(r"\d+\.\d+\.\d+", raw or "")
        if m:
            claude_version = m.group(0)
    if claude_version:
        if version_ge(claude_version, CLAUDE_CLI_MIN_VERSION):
            print(f"claude CLI : {claude_version} (>= {CLAUDE_CLI_MIN_VERSION})")
        else:
            print(f"WARNING: claude CLI version {claude_version} is below recommended floor {CLAUDE_CLI_MIN_VERSION}.")
            print("         Plugin manifest schema may not be supported. Continuing anyway.")
    else:
        print("WARNING: could not parse claude --version output. Continuing.")

    check_bash_admission_gate(platform_name)

    jq_present = shutil.which("jq") is not None
    if not jq_present:
        print("")
        print("WARNING: jq not found on PATH.")
        print("Hook scripts degrade gracefully for basic JSON parsing, but")
        print("some hook scripts use jq for JSON parsing.")
        print("")
        print("Install jq:")
        print("  macOS:   brew install jq")
        print("  Linux:   sudo apt install jq  (or your distro's package manager)")
        print("  Windows: winget install jqlang.jq")
        print("")
        if non_interactive:
            print("Continuing without jq (non-interactive mode).")
        else:
            jq_confirm = _prompt("Continue without jq? [y/N]: ", "N")
            if not re.match(r"^[Yy]$", jq_confirm):
                print("Install jq and re-run the installer.")
                sys.exit(1)

    uv_present = shutil.which("uv") is not None
    uv_version = ""
    if uv_present:
        uv_path = shutil.which("uv")
        proc = _run([uv_path, "--version"], timeout=10) if uv_path else None
        raw = proc.stdout if proc is not None else ""
        m = re.search(r"\d+\.\d+\.\d+", raw or "")
        if m:
            uv_version = m.group(0)
    if uv_present:
        print(f"uv         : {uv_version or 'present'}")
    else:
        print("uv         : not found (only required for the NotebookLM add-on)")

    optional_missing: List[str] = []
    if shutil.which("shellcheck") is None:
        if platform_name == "darwin":
            optional_missing.append("shellcheck — lints .sh files on commit (brew install shellcheck)")
        elif platform_name in ("linux", "wsl"):
            optional_missing.append(
                "shellcheck — lints .sh files on commit (sudo apt install shellcheck  # or your distro's pkg-manager)"
            )
        else:
            optional_missing.append("shellcheck — lints .sh files on commit (winget install koalaman.shellcheck)")

    # `shutil.which` with an explicit `path=` covers the ~/bin fallback portably: it applies
    # PATHEXT on Windows and the execute bit on POSIX. A raw `os.access(..., X_OK)` cannot --
    # on Windows X_OK collapses to F_OK, so any readable file named `scc` reads as present.
    scc_present = (
        shutil.which("scc") is not None
        or shutil.which("scc", path=str(Path.home() / "bin")) is not None
    )
    if not scc_present:
        if platform_name == "darwin":
            optional_missing.append("scc — code statistics in session orientation (brew install scc)")
        elif platform_name in ("linux", "wsl"):
            optional_missing.append(
                "scc — code statistics in session orientation (go install github.com/boyter/scc/v3@latest  # or your distro's pkg-manager)"
            )
        else:
            optional_missing.append("scc — code statistics in session orientation (winget install BenBoyter.scc)")

    if optional_missing:
        print("")
        print("OPTIONAL: These tools enhance coordinator functionality but are not required:")
        for tool in optional_missing:
            print(f"  - {tool}")
        print("")
        print("All features degrade gracefully without them.")

    return uv_present, jq_present, uv_version


def _prompt(message: str, default: str) -> str:
    """`input()` wrapper matching bash `read -r -p "$message"` + `${var:-default}`
    fallback semantics — including EOF-on-closed-stdin, which bash's `read`
    treats as an empty response (falls to default)."""
    try:
        response = input(message)
    except EOFError:
        response = ""
    return response or default


# ---------------------------------------------------------------------------
# Plugin source-kind helpers
# ---------------------------------------------------------------------------


def plugin_field(name: str, field: int) -> Optional[str]:
    """field: 0=name, 1=default, 2=source_kind, 3=description (0-indexed;
    bash oracle is 1-indexed via `cut -f`)."""
    for entry in PLUGIN_REGISTRY:
        if entry[0] == name:
            return entry[field]
    return None


def read_plugin_version(name: str, repo_root: str) -> str:
    """Read version from plugin.json for local plugins. Empty string for
    non-local plugins or if plugin.json is missing/unparseable."""
    source_kind = plugin_field(name, 2)
    if source_kind != "local":
        return ""
    plugin_json = Path(repo_root) / "plugins" / name / ".claude-plugin" / "plugin.json"
    if not plugin_json.is_file():
        return ""
    try:
        with open(plugin_json, "r", encoding="utf-8") as f:
            return json.load(f).get("version", "") or ""
    except (OSError, json.JSONDecodeError):
        return ""


# ---------------------------------------------------------------------------
# Plugin selection
# ---------------------------------------------------------------------------


class InstallState:
    """Mutable install-run state — the Python analog of the bash oracle's
    script-global variables (SELECTED, COLLISIONS, PERMS_APPENDED, ...)."""

    def __init__(self) -> None:
        self.selected: Dict[str, bool] = {}
        self.collisions: List[str] = []
        self.skipped_nonlocal: List[str] = []
        self.perms_appended: List[str] = []
        self.notebooklm_installed = False
        self.codex_installed = False
        self.plugins_target = ""


def build_default_selection(state: InstallState) -> None:
    for name, default, _kind, _desc in PLUGIN_REGISTRY:
        state.selected[name] = default == "on"
    state.selected["coordinator"] = True


def apply_plugins_arg(state: InstallState, plugins_arg: str) -> None:
    for name, _default, _kind, _desc in PLUGIN_REGISTRY:
        state.selected[name] = False
    state.selected["coordinator"] = True

    for plugin in plugins_arg.split(","):
        plugin = re.sub(r"\s", "", plugin)
        if plugin in state.selected:
            state.selected[plugin] = True
        elif plugin:
            print(f"WARNING: Unknown plugin '{plugin}' in --plugins list — skipping.")


def interactive_selection(state: InstallState) -> None:
    print("Select plugins to install:")
    print("")
    print("  [*] coordinator    — Core pipeline and workflow skills (always enabled)")

    for name, default, _kind, description in PLUGIN_REGISTRY:
        if name == "coordinator":
            continue
        if default == "optional":
            continue
        prompt_default = "Y" if default == "on" else "n"
        choice = _prompt(f"  [{prompt_default}] {name} — {description} [Y/n]: ", prompt_default)
        state.selected[name] = bool(re.match(r"^[Yy]$", choice))
    print("")


def prompt_codex_addon(state: InstallState, args: Args, non_interactive: bool) -> None:
    if args.codex_opt is True:
        state.codex_installed = True
        print("codex-review-gate skill: enabled (--enable-codex)")
        print("")
        return
    if args.codex_opt is False:
        state.codex_installed = False
        print("codex-review-gate skill: skipped (--no-codex)")
        print("")
        return

    if non_interactive:
        state.codex_installed = False
        print("codex-review-gate skill: skipped (non-interactive default).")
        print("  Re-run with --enable-codex to add it later.")
        print("")
        return

    if sys.stdin.isatty():
        print("")
        print("Optional add-on:")
        print("  codex-review-gate — Run Codex (openai/codex-plugin-cc) as an")
        print("  independent-model second-opinion review in /workweek-complete and")
        print("  /bug-sweep --codex-verify. Requires the codex-plugin-cc plugin")
        print("  installed and the Codex CLI authenticated separately.")
        choice = _prompt("Install the codex-review-gate skill? [y/N]: ", "N")
        if re.match(r"^[Yy]$", choice):
            state.codex_installed = True
        else:
            state.codex_installed = False
            print("Skipped. Re-run setup or pass --enable-codex to add it later.")
        print("")
    else:
        state.codex_installed = False
        print("codex-review-gate skill: skipped (no TTY for prompt).")
        print("  Re-run with --enable-codex to add it later.")
        print("")


def prompt_optional_addons(state: InstallState, args: Args, non_interactive: bool) -> None:
    """Prompt for opt-in add-ons. Currently: notebooklm."""
    if "notebooklm" not in state.selected:
        return

    if args.notebooklm_opt is True:
        state.selected["notebooklm"] = True
        state.notebooklm_installed = True
        print("NotebookLM add-on: enabled (--install-notebooklm)")
        print("")
        return
    if args.notebooklm_opt is False:
        state.selected["notebooklm"] = False
        print("NotebookLM add-on: skipped (--no-notebooklm)")
        print("")
        return

    if args.plugins_arg and state.selected["notebooklm"]:
        state.notebooklm_installed = True
        print("NotebookLM add-on: enabled (via --plugins)")
        print("")
        return

    if non_interactive:
        state.selected["notebooklm"] = False
        print("NotebookLM add-on: skipped (non-interactive default).")
        print("  Re-run with --install-notebooklm to enable later.")
        print("")
        return

    if sys.stdin.isatty():
        print("")
        print("Optional add-on:")
        print("  notebooklm — Media research via NotebookLM (Python package, launched via uvx)")
        print("  Resolved on enable by Claude Code from the marketplace manifest.")
        choice = _prompt("Install the NotebookLM optional add-on? [y/N]: ", "N")
        if re.match(r"^[Yy]$", choice):
            state.selected["notebooklm"] = True
            state.notebooklm_installed = True
        else:
            state.selected["notebooklm"] = False
            print("Skipped. Re-run setup or pass --install-notebooklm to enable later.")
        print("")
    else:
        state.selected["notebooklm"] = False
        print("NotebookLM add-on: skipped (no TTY for prompt).")
        print("  Re-run with --install-notebooklm to enable later.")
        print("")


def select_plugins(state: InstallState, args: Args, non_interactive: bool) -> None:
    build_default_selection(state)

    if args.plugins_arg:
        apply_plugins_arg(state, args.plugins_arg)
    elif not non_interactive:
        interactive_selection(state)
    # else: non-interactive with no --plugins arg => use defaults (already set)

    prompt_optional_addons(state, args, non_interactive)
    prompt_codex_addon(state, args, non_interactive)


def check_notebooklm_prereqs(state: InstallState, uv_present: bool) -> None:
    if not state.selected.get("notebooklm"):
        return
    if not uv_present:
        print("ERROR: NotebookLM add-on selected but 'uv' not found on PATH.")
        print("       The notebooklm-mcp server runs via")
        print("       'uvx --from notebooklm-mcp-cli notebooklm-mcp' (a Python package;")
        print("       uvx ships with uv and auto-fetches the package on first run).")
        print("       Install uv:")
        print("         macOS/Linux: curl -LsSf https://astral.sh/uv/install.sh | sh")
        print("         macOS:       brew install uv")
        print("         Windows:     winget install astral-sh.uv")
        print("")
        print("Re-run setup without --install-notebooklm (or answer 'n' at the prompt)")
        print("to skip the add-on, or install uv and re-run.")
        sys.exit(1)


def prompt_naming_addon(args: Args, non_interactive: bool, script_dir: Path) -> None:
    """Optional persona-naming prompt. Resolution order mirrors
    prompt_codex_addon (see bash oracle comment)."""
    if args.naming_opt is False:
        return
    if args.naming_opt is not True and non_interactive:
        return
    if args.naming_opt is not True and not sys.stdin.isatty():
        return

    naming_script = script_dir / "name-personas.py"

    print("")
    print("Optional: persona naming")
    print("  You'll be working with seven role-distinct reviewer agents (the Staff Engineer,")
    print("  the Game Dev Reviewer, etc.). Some people find it easier to think of them as")
    print("  named collaborators — others prefer role labels alone. Naming is optional.")
    print("")
    naming_choice = _prompt("Name your reviewers now? [y/later/N]: ", "N")

    if re.match(r"^([Yy]|[Yy][Ee][Ss])$", naming_choice):
        if not naming_script.is_file():
            print(f"  Could not find {naming_script} — run it manually whenever you'd like.")
            print("")
            return
        print("")
        print("  Naming flow: enter a name for each role, or press Enter to keep the role label as-is.")
        print("")
        roles = [
            "the Staff Engineer",
            "the Ambition Advocate",
            "the VP-Product Reviewer",
            "the Game Dev Reviewer",
            "the Front-End Reviewer",
            "the UX Reviewer",
            "the Data Science Reviewer",
        ]
        naming_args: List[str] = []
        for role in roles:
            chosen_name = _prompt(f"  Name for {role}? (Enter to skip): ", "")
            if chosen_name:
                naming_args.extend([role, chosen_name])
        if not naming_args:
            print("")
            print("  No names entered — leaving role labels in place.")
            print("  Run setup/name-personas.py whenever you'd like.")
            print("")
        else:
            print("")
            print("  Binding names via setup/name-personas.py...")
            print("")
            # Review: code-reviewer (Finding 5, 2026-07-17) — A2 hardening
            # applies uniformly (no carve-out): timeout as a hang backstop
            # + stdin=DEVNULL (name-personas.py does no stdin reads of its
            # own — all names were already collected via _prompt above), while
            # stdout stays inherited so the script's own progress output
            # still reaches the user directly.  # popup-safe-env-suppressed
            subprocess.run(
                [sys.executable, str(naming_script), *naming_args],
                timeout=120,
                stdin=subprocess.DEVNULL,
                **_NO_CONSOLE,
            )
    elif re.match(r"^([Ll]|[Ll][Aa][Tt][Ee][Rr])$", naming_choice):
        print("  Run setup/name-personas.py whenever you'd like.")
        print("")
    else:
        print("  Skipped. Reviewers remain role-distinct under their role labels.")
        print("")


# ---------------------------------------------------------------------------
# File copy
# ---------------------------------------------------------------------------


def _chmod_shebanged_files(root: Path) -> None:
    """Shebang-scan: chmod +x every file under `root` whose first 2 bytes
    are '#!'. Spec backlink: docs/plans/2026-06-11-exec-bit-install-surface-completion.md § Chunk 7."""
    for dirpath, _dirnames, filenames in os.walk(root):
        for fname in filenames:
            fpath = Path(dirpath) / fname
            try:
                with open(fpath, "rb") as f:
                    head = f.read(2)
            except OSError:
                continue
            if head == b"#!":
                try:
                    st = fpath.stat()
                    os.chmod(fpath, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                except OSError:
                    pass


def copy_plugins(state: InstallState, repo_root: str, claude_dir: str) -> None:
    plugins_target = str(Path(claude_dir) / "plugins" / "coordinator-claude")
    state.plugins_target = plugins_target
    os.makedirs(plugins_target, exist_ok=True)

    print("Copying plugins...")
    for name, _default, source_kind, _desc in PLUGIN_REGISTRY:
        if not state.selected.get(name):
            continue

        if source_kind != "local":
            print(f"  SKIP: {name} (source_kind={source_kind} — registered via marketplace, not copied)")
            state.skipped_nonlocal.append(name)
            continue

        src = Path(repo_root) / "plugins" / name
        dest = Path(plugins_target) / name

        if not src.is_dir():
            print(f"  ERROR: source directory missing for local plugin '{name}': {src}")
            sys.exit(1)

        if dest.is_dir():
            backup = Path(str(dest) + ".bak")
            if backup.exists():
                shutil.rmtree(backup, ignore_errors=True)
            shutil.move(str(dest), str(backup))
            print(f"  BACKUP: {name} (existing -> {backup.name})")
            state.collisions.append(name)

        shutil.copytree(src, dest)
        print(f"  OK: {name}")

        # codex-review-gate is bundled inside the coordinator plugin but is
        # an opt-in add-on — strip it when the user didn't opt in.
        if name == "coordinator" and not state.codex_installed:
            codex_skill = dest / "skills" / "codex-review-gate"
            if codex_skill.is_dir():
                shutil.rmtree(codex_skill)
                print("  STRIPPED: coordinator/skills/codex-review-gate (opt in via --enable-codex)")

    print("Fixing exec bits on installed plugin shebanged files...")
    _chmod_shebanged_files(Path(plugins_target))

    copy_marketplace_manifest(state, repo_root)
    print("")


def copy_marketplace_manifest(state: InstallState, repo_root: str) -> None:
    src = Path(repo_root) / ".claude-plugin" / "marketplace.json"
    dest_dir = Path(state.plugins_target) / ".claude-plugin"
    dest = dest_dir / "marketplace.json"

    if not src.is_file():
        print("  WARN: marketplace.json not found in repo — plugins may not load")
        return

    dest_dir.mkdir(parents=True, exist_ok=True)

    selected_names = {name for name, _d, _k, _de in PLUGIN_REGISTRY if state.selected.get(name)}

    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "metadata" in data and "pluginRoot" in data["metadata"]:
        del data["metadata"]["pluginRoot"]

    new_plugins = []
    for p in data.get("plugins", []):
        if p.get("name") not in selected_names:
            continue
        src_field = p.get("source")
        if isinstance(src_field, str) and src_field.startswith("./plugins/"):
            p["source"] = "./" + src_field[len("./plugins/"):]
        new_plugins.append(p)
    data["plugins"] = new_plugins

    _atomic_write_json(dest, data)

    print(f"  OK: marketplace manifest ({len(selected_names)} plugins)")


def _atomic_write_json(dest: Path, data: dict) -> None:
    tmp = str(dest) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, dest)


# ---------------------------------------------------------------------------
# Setup/ percolation mechanism delivery
# ---------------------------------------------------------------------------
#
# Delivers the publish/percolation scripts from the just-copied coordinator
# plugin templates into ~/.claude/setup/. Single source of truth for the file
# list: coordinator/lib/setup-templates-manifest.py (plain Python module of
# list constants — bash-invocation-tax port, retiring the former
# setup-templates-manifest.sh + bounded `bash -c 'source ...; printf ...'`
# subprocess read). Imported directly via a scoped sys.path insert rather
# than duplicated inline, per that manifest's own "edit HERE and nowhere
# else" contract. The manifest module has no claude-klabauter/coordinator_core
# dependency, so this import works unmodified in both the DoE-claude dev
# checkout and the standalone OSS publish repo this file percolates into
# (see this file's own header — DELIBERATELY SELF-CONTAINED).


def _read_setup_templates_manifest(plugins_target: str) -> Optional[Any]:
    lib_dir = str(Path(plugins_target) / "coordinator" / "lib")
    manifest_path = Path(lib_dir) / "setup-templates-manifest.py"
    if not manifest_path.is_file():
        return None
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)

    module_name = "setup_templates_manifest"
    if module_name in sys.modules:
        del sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, manifest_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def deliver_setup_templates(plugins_target: str, claude_dir: str, repo_root: str) -> None:
    setup_src = Path(plugins_target) / "coordinator" / "templates" / "setup"
    setup_dest = Path(claude_dir) / "setup"

    if not setup_src.is_dir():
        print(f"  SKIP: ~/.claude/setup/ delivery (coordinator templates/setup/ not present at {setup_src})")
        return

    manifest = _read_setup_templates_manifest(plugins_target)
    if manifest is None:
        manifest_path = Path(plugins_target) / "coordinator" / "lib" / "setup-templates-manifest.py"
        print(f"  ERROR: setup-templates-manifest.py not found at {manifest_path}", file=sys.stderr)
        print("  ERROR: ~/.claude/setup/ percolation mechanism will NOT be installed.", file=sys.stderr)
        print("  ERROR: This indicates a corrupt or incomplete coordinator plugin copy.", file=sys.stderr)
        print("  ERROR: Reinstall the coordinator plugin and re-run the installer.", file=sys.stderr)
        sys.exit(1)

    setup_files = list(manifest.SETUP_TEMPLATE_FILES)
    setup_hook_files = list(manifest.SETUP_TEMPLATE_HOOK_FILES)

    setup_dest.mkdir(parents=True, exist_ok=True)
    print("Delivering ~/.claude/setup/ percolation scripts...")
    for f in setup_files:
        src_file = setup_src / f
        dest_file = setup_dest / f
        if not src_file.is_file():
            print(f"  WARN: template missing — {src_file} (skipping)")
            continue
        if dest_file.is_file():
            print(f"  KEEP: setup/{f} (operator-preserved)")
        else:
            shutil.copy2(src_file, dest_file)
            print(f"  OK:   setup/{f}")

    for hf in setup_hook_files:
        (setup_dest / hf).parent.mkdir(parents=True, exist_ok=True)
        hooks_src = setup_src / hf
        hooks_dest = setup_dest / hf
        if hooks_src.is_file():
            if hooks_dest.is_file():
                print(f"  KEEP: setup/{hf} (operator-preserved)")
            else:
                shutil.copy2(hooks_src, hooks_dest)
                print(f"  OK:   setup/{hf}")
        else:
            print(f"  WARN: template missing — {hooks_src} (skipping)")

    print("Fixing exec bits on installed setup shebanged files...")
    _chmod_shebanged_files(setup_dest)
    print("")

    # Install the OSS publish-repo pre-commit exec-bit drift gate. Offer-shape:
    # prints and continues on foreign hook; never blocks install on failure.
    hook_installer = Path(repo_root) / "coordinator" / "bin" / "install-publish-repo-precommit-hook.py"
    print("Installing OSS exec-bit pre-commit gate...")
    if hook_installer.is_file():
        try:
            subprocess.run(
                [sys.executable, str(hook_installer), repo_root],
                capture_output=True,
                timeout=60,
                stdin=subprocess.DEVNULL,
                **_NO_CONSOLE,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


# ---------------------------------------------------------------------------
# JSON registration
# ---------------------------------------------------------------------------


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def register_marketplace(claude_dir: str, plugins_target: str, plat: str, timestamp: str) -> None:
    marketplace_file = Path(claude_dir) / "plugins" / "known_marketplaces.json"
    native_plugins_dir = native_path(plugins_target, plat)

    data: dict = {}
    if marketplace_file.exists():
        with open(marketplace_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        shutil.copy2(marketplace_file, str(marketplace_file) + ".bak")

    data["coordinator-claude"] = {
        "source": {"source": "directory", "path": native_plugins_dir},
        "installLocation": native_plugins_dir,
        "lastUpdated": timestamp,
    }
    marketplace_file.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(marketplace_file, data)
    print("  OK: known_marketplaces.json updated")


def register_installed_plugins(
    state: InstallState, claude_dir: str, repo_root: str, plat: str, timestamp: str
) -> None:
    installed_file = Path(claude_dir) / "plugins" / "installed_plugins.json"
    plugins_target_native = native_path(state.plugins_target, plat)

    selected_versions: Dict[str, str] = {}
    for name, _default, source_kind, _desc in PLUGIN_REGISTRY:
        if not state.selected.get(name):
            continue
        if source_kind != "local":
            continue
        version = read_plugin_version(name, repo_root)
        if not version:
            print(f"  WARN: could not read version for {name} from plugin.json — using 0.0.0")
            version = "0.0.0"
        selected_versions[name] = version

    data: dict = {}
    if installed_file.exists():
        with open(installed_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        shutil.copy2(installed_file, str(installed_file) + ".bak")

    data["version"] = 2
    if "plugins" not in data:
        data["plugins"] = {}

    for name, version in selected_versions.items():
        key = f"{name}@coordinator-claude"
        install_path = os.path.join(plugins_target_native, name)
        data["plugins"][key] = [
            {
                "scope": "user",
                "installPath": install_path,
                "version": version,
                "installedAt": timestamp,
                "lastUpdated": timestamp,
            }
        ]

    installed_file.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(installed_file, data)
    print(f"  OK: installed_plugins.json updated ({len(selected_versions)} plugins)")


def register_settings(state: InstallState, claude_dir: str, plat: str) -> None:
    settings_file = Path(claude_dir) / "settings.json"
    native_plugins_dir = native_path(state.plugins_target, plat)

    selected_names = [name for name, _d, _k, _de in PLUGIN_REGISTRY if state.selected.get(name)]

    data: dict = {}
    if settings_file.exists():
        with open(settings_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        shutil.copy2(settings_file, str(settings_file) + ".bak")

    if "enabledPlugins" not in data:
        data["enabledPlugins"] = {}
    for name in selected_names:
        data["enabledPlugins"][f"{name}@coordinator-claude"] = True

    if "extraKnownMarketplaces" not in data:
        data["extraKnownMarketplaces"] = {}
    data["extraKnownMarketplaces"]["coordinator-claude"] = {
        "source": {"source": "directory", "path": native_plugins_dir}
    }

    if "permissions" not in data:
        data["permissions"] = {}
    if "allow" not in data["permissions"]:
        data["permissions"]["allow"] = []
    if "defaultMode" not in data["permissions"]:
        data["permissions"]["defaultMode"] = "auto"
    for tool in ["Edit", "Write"]:
        if tool not in data["permissions"]["allow"]:
            data["permissions"]["allow"].append(tool)
            state.perms_appended.append(tool)

    # THE CANARY IS WRITTEN BY THE SAME ACT THAT ENABLES THE HOOKS NEEDING IT.
    # `COORDINATOR_PROBE_CANARY` is the interpolated half of the http override
    # channel's veto discriminator (`hooks.json`'s X-Coordinator-Env-Canary).
    # Unset, that header interpolates to the empty string, which is
    # byte-identical to what an `httpHookAllowedEnvVars` setting produces when
    # it vetoes the registration -- so the forwarder reads a permanent veto and
    # DENIES EVERY BASH CALL for the life of the session, naming a setting the
    # box does not have.
    #
    # The launchers (`claude-doe`, and the two Windows launcher templates) each
    # setdefault it, so the guarantee cannot live only there: a bare `claude` --
    # an OSS install, a container, a CI runner, Claude Code on the web -- has no
    # launcher at all, and would enable the hooks above and brick its own shell
    # on first use. Writing it HERE is what makes that unreachable, and this is
    # the cold path by construction: it runs before any session exists, so
    # unlike `/coordinator:install`'s `check-settings-env.py --apply` leg it
    # does not depend on the very tool its own absence would deny.
    #
    # Only when unset -- an operator who pinned a different value keeps it, and
    # a re-run is a no-op, matching the blocks above.
    if not isinstance(data.get("env"), dict):
        data["env"] = {}
    if not data["env"].get("COORDINATOR_PROBE_CANARY"):
        data["env"]["COORDINATOR_PROBE_CANARY"] = "1"

    settings_file.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(settings_file, data)
    print("  OK: settings.json updated")


# ---------------------------------------------------------------------------
# Install-side version sentinel
# ---------------------------------------------------------------------------


def write_install_sentinel(plugins_target: str, repo_root: str) -> None:
    """Plants $CLAUDE_DIR/plugins/coordinator-claude/version.txt (40-hex SHA)
    immediately after copy_plugins so /coordinator-update has a baseline
    anchor. WARN-don't-FAIL posture — never exits non-zero on sentinel
    failure; the coordinator install still succeeded."""
    bin_dir = Path(plugins_target) / "coordinator" / "bin"
    # Extensionless vs .py varies by install vintage (the POSIX-exec drain
    # renames bin entrypoints to .py); probe both rather than pinning one.
    writer = next(
        (c for c in (bin_dir / "install-sentinel-write", bin_dir / "install-sentinel-write.py") if c.is_file()),
        bin_dir / "install-sentinel-write",
    )
    if not writer.is_file():
        print(f"WARNING: install-sentinel-write not found at {writer} — version.txt NOT written.")
        print("         The coordinator install succeeded; re-run the installer to plant the")
        print("         update baseline, or run /coordinator-update for the first time without it.")
        return
    try:
        proc = subprocess.run(
            [sys.executable, str(writer), "--path", plugins_target, "--source", repo_root],
            capture_output=True,
            text=True,
            timeout=30,
            stdin=subprocess.DEVNULL,
            **_NO_CONSOLE,
        )
        ok = proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        ok = False
    if ok:
        print(f"  OK: version.txt (update baseline) written at {plugins_target}/version.txt")
    else:
        print("WARNING: install-sentinel-write exited non-zero — version.txt may be incomplete.")
        print("         The coordinator install succeeded; /coordinator-update will degrade")
        print("         to baseline-free two-way mode on first run.")
    print("")


# ---------------------------------------------------------------------------
# Machine-local substrate via install-substrate.sh --setup-only
# ---------------------------------------------------------------------------


def seed_machine_local_substrate(plugins_target: str, claude_dir: str) -> None:
    substrate = Path(plugins_target) / "coordinator" / "lib" / "install-substrate.sh"
    if not substrate.is_file():
        print(f"  WARN: install-substrate.sh not found at {substrate} — skipping machine-local substrate seed", file=sys.stderr)
        return
    print("Seeding machine-local substrate (install-substrate.sh --setup-only)...")
    env = dict(os.environ)
    env["CLAUDE_HOME"] = str(Path(claude_dir).parent)
    env["CLAUDE_PLUGIN_ROOT"] = str(Path(plugins_target) / "coordinator")
    try:
        proc = subprocess.run(
            [sys.executable, str(substrate), "--setup-only"],
            env=env,
            timeout=300,
            stdin=subprocess.DEVNULL,
            **_NO_CONSOLE,
        )
        ok = proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        ok = False
    if not ok:
        print(
            "  WARN: install-substrate.sh --setup-only exited non-zero — machine-local layer "
            "may be incomplete (validate_installation will FAIL on the missing artifacts)",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_installation(state: InstallState, claude_dir: str) -> None:
    print("Validating installation...")
    errors = 0

    for name, _default, source_kind, _desc in PLUGIN_REGISTRY:
        if state.selected.get(name) and source_kind == "local":
            if (Path(state.plugins_target) / name).is_dir():
                print(f"  OK: plugin dir exists — {name}")
            else:
                print(f"  FAIL: plugin dir missing — {state.plugins_target}/{name}")
                errors += 1

    marketplace_file = Path(claude_dir) / "plugins" / "known_marketplaces.json"
    if marketplace_file.is_file():
        try:
            with open(marketplace_file, "r", encoding="utf-8") as f:
                d = json.load(f)
            assert "coordinator-claude" in d
            print("  OK: known_marketplaces.json has coordinator-claude entry")
        except (OSError, json.JSONDecodeError, AssertionError):
            print("  FAIL: known_marketplaces.json missing coordinator-claude entry")
            errors += 1

    manifest = Path(state.plugins_target) / ".claude-plugin" / "marketplace.json"
    if manifest.is_file():
        print("  OK: marketplace manifest exists")
    else:
        print(f"  FAIL: marketplace manifest missing — {manifest}")
        errors += 1

    installed_file = Path(claude_dir) / "plugins" / "installed_plugins.json"
    if installed_file.is_file():
        found = 0
        try:
            with open(installed_file, "r", encoding="utf-8") as f:
                d = json.load(f)
            plugins = d.get("plugins", {})
            found = sum(1 for k in plugins if k.endswith("@coordinator-claude"))
        except (OSError, json.JSONDecodeError):
            found = 0
        print(f"  OK: installed_plugins.json has {found} coordinator-claude plugin(s)")

    coordinator_update_skill = Path(state.plugins_target) / "coordinator" / "skills" / "coordinator-update"
    if coordinator_update_skill.is_dir():
        print("  OK: coordinator-update skill present")
    else:
        print(f"  FAIL: coordinator-update skill missing — {coordinator_update_skill}")
        print("        Re-run the installer to restore it.")
        errors += 1

    for ml_artifact in ("machine-local/registry.toml", "bin/machine-local"):
        if (Path(claude_dir) / ml_artifact).exists():
            print(f"  OK: machine-local {ml_artifact} present")
        else:
            print(f"  FAIL: machine-local {ml_artifact} missing — {claude_dir}/{ml_artifact}")
            print("        Re-run the installer; if it persists, run install-substrate.sh --setup-only directly.")
            errors += 1

    if errors > 0:
        print("")
        print(f"ERROR: {errors} validation error(s) detected. Installation is incomplete.")
        print("Review the FAIL lines above; backups (.bak) of any modified JSON files were preserved.")
        sys.exit(1)
    print("")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def print_summary(state: InstallState, repo_root: str, plat: str) -> None:
    print("Installation summary")
    print("====================")
    print("")
    print(f"Target: {state.plugins_target}")
    print("")
    print("Plugins installed:")
    for name, _default, source_kind, _desc in PLUGIN_REGISTRY:
        if not state.selected.get(name):
            continue
        if source_kind == "local":
            version = read_plugin_version(name, repo_root)
            print(f"  + {name} ({version})")
        else:
            print(f"  + {name} (registered via {source_kind}, not copied)")
    print("")

    if state.perms_appended:
        print("Settings changes:")
        print(f"  Added {', '.join(state.perms_appended)} to permissions.allow")
        print("")

    if state.collisions:
        print("Existing plugin directories were preserved as <name>.bak:")
        for c in state.collisions:
            print(f"  - {c}.bak")
        print("")

    if state.skipped_nonlocal:
        print("Plugins registered via marketplace (no local copy):")
        for s in state.skipped_nonlocal:
            print(f"  - {s}")
        print("")

    if "notebooklm" in state.selected:
        if state.notebooklm_installed:
            print("NotebookLM add-on: installed")
        else:
            print("NotebookLM add-on: skipped (run setup again or enable manually to add)")
        print("")

    if state.codex_installed:
        print("codex-review-gate skill: installed")
        print("  Requires openai/codex-plugin-cc + 'codex login' to actually run.")
    else:
        print("codex-review-gate skill: skipped (re-run with --enable-codex to add)")
    print("")

    sentinel = Path(state.plugins_target) / "version.txt"
    if sentinel.is_file():
        print(f"Update baseline: version.txt written at {sentinel}")
        print("  Run /coordinator-update to check for upstream changes later.")
    else:
        print("Update baseline: version.txt NOT written (writer missing — re-run installer to plant it).")
    print("")

    print("Next steps:")
    print("  1. Open ~/.claude as your working directory in Claude Code:")
    print("       cd ~/.claude")
    if plat == "darwin":
        print("     (Hidden directory tip: in Finder press Cmd+Shift+G and type ~/.claude)")
    elif plat == "gitbash":
        print("     (Hidden directory tip: in File Explorer type %USERPROFILE%\\.claude in the address bar)")
    elif plat in ("linux", "wsl"):
        print("     (Hidden directory tip: in your file manager choose View → Show Hidden Files)")
    print("  2. Restart Claude Code.")
    print("  3. To take a guided tour, say: walk me through the coordinator")
    print("     Or jump straight in with: /workstream-start")
    print("")

    print("Hit a rough edge getting this working? Patch it — then send the fix back.")
    print("A script-only install was whack-a-mole across machines, so we lean on agents")
    print("and on you: open a PR, file an issue, or paste a rough note. Don't polish it —")
    print("what you changed and why is worth more to us than clean code. Details:")
    print("  https://github.com/dbc-oduffy/coordinator-claude/blob/main/CONTRIBUTING.md")
    print("")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: List[str]) -> int:
    try:
        args = parse_args(argv)
        if args.help:
            print(USAGE)
            return 0
        resolve_profile_alias(args)
    except UsageError as exc:
        print(f"ERROR: {exc}")
        return 1

    plat = detect_platform()

    claude_dir = ""
    if plat in ("linux", "darwin", "gitbash", "wsl", "unknown"):
        claude_dir = str(Path.home() / ".claude")

    script_path = Path(os.path.abspath(__file__))
    repo_root = str(script_path.parent.parent)

    print("coordinator-claude installer")
    print("============================")
    print("")
    print(f"Platform : {plat}")
    print(f"Repo root: {repo_root}")
    print(f"Claude dir: {claude_dir}")
    print("")

    uv_present, _jq_present, _uv_version = check_prerequisites(args.non_interactive, plat)
    print(f"Python     : {sys.executable}")
    print("")

    state = InstallState()
    select_plugins(state, args, args.non_interactive)

    check_notebooklm_prereqs(state, uv_present)

    if not args.non_interactive and not args.plugins_arg:
        confirm = _prompt("Proceed with installation? [Y/n]: ", "Y")
        if not re.match(r"^[Yy]$", confirm):
            print("Cancelled.")
            return 0
        print("")

    copy_plugins(state, repo_root, claude_dir)
    deliver_setup_templates(state.plugins_target, claude_dir, repo_root)
    seed_machine_local_substrate(state.plugins_target, claude_dir)
    write_install_sentinel(state.plugins_target, repo_root)

    print("Registering JSON config files...")
    timestamp = _timestamp()
    register_marketplace(claude_dir, state.plugins_target, plat, timestamp)
    register_installed_plugins(state, claude_dir, repo_root, plat, timestamp)
    register_settings(state, claude_dir, plat)
    print("")

    validate_installation(state, claude_dir)
    print_summary(state, repo_root, plat)
    prompt_naming_addon(args, args.non_interactive, script_path.parent)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        sys.exit(1)
