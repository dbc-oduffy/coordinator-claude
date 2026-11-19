"""coordinator-install: the install as a script with declared choices.

`--plan` prints every decision as one JSON document and mutates nothing. `--answers` (file or inline
JSON) executes every step deterministically and prints one structured block reporting each step as
RAN, SKIPPED (by answer), INHERITED (already true before this run) or FAILED. `--non-interactive`
takes the declared defaults; `--i-am-agent` hands the agent the full plan to answer in one pass.
`--express` (recommended defaults) and `--custom` (one plain-language question at a time on stdin)
are the human paths and end in the same block.

STEPS is the executable half of `docs/install/agent-install-manifest.json`: each step names the
manifest entries it implements, and `check_manifest_drift` fails on an entry no step implements or a
step that implements nothing without a stated reason.

Stdlib only; runs on macOS, Linux and Windows.

Never imports coordinator_core while steps run: the installer runs before an engine is importable, so
its git calls stay on its own bounded `subprocess.run`. Only `record_concluded`, after the last step,
imports it from the located engine root to stamp the setup_concluded receipt.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Callable

SCHEMA = "coordinator-install-plan/1"
RAN, SKIPPED, INHERITED, FAILED = "RAN", "SKIPPED", "INHERITED", "FAILED"
BLOCKED = "BLOCKED"  # a launch the OS code-integrity policy refused: the step's work never ran, nothing in it failed

POSTURE_QUESTION = "How do you want the coordinator EM to work with you day to day?"
POSTURE_OPTIONS = {
    "precision": (
        "I want to be consulted often and closely, before things change, not just told after -- "
        "whether that means reviewing diffs and weighing in on refactor mechanics, or simply "
        "wanting to see and approve what's about to change for my users before it ships."
    ),
    "default": (
        "The standard First Officer partnership -- the EM acts on engineering calls autonomously, "
        "surfaces tradeoffs before forks, and expects me to engage on planning and product direction."
    ),
    "substrate-free": (
        "Brief me at milestones, minimize interruptions, surface only ship/product-level gates -- "
        "I don't want engineering detail in my inbox."
    ),
}
POSTURE_WHY = (
    "These three anchors select engagement distance, never technical skill: an operator who "
    "cannot read a diff and never wants to still belongs on precision if they want to be asked "
    "before things change."
)

ORIENTATION = (
    "The first choice is your posture: how closely the EM consults you (precision, default or "
    "substrate-free), asked of you before anything else. "
    "You are installing a collaboration contract, not software. You are the PM: product authority "
    "-- what to build, ship, cut. The EM (Claude) is the engineering manager: how to build it, when "
    "to dispatch, how to review. The EM acts on engineering calls without hand-holding and pushes "
    "back when it disagrees with you. Non-trivial work flows plan, enrich, review, execute, review "
    "rather than straight to code; reviewer personas are available at the cost of minutes; "
    "/workstream-start and /workstream-complete bracket a working session. You do not need to learn "
    "the machinery: brief the EM in plain language and it picks the agents."
)

TOUR = (
    {
        "movement": 2,
        "title": "Make it yours",
        "text": (
            "Your CLAUDE.md is the contract every agent reads before it speaks to you: who decides "
            "what, how you like to be pushed back on, what done means. Editing it is the highest-"
            "leverage change you can make, and it works best done together: describe how you like to "
            "work, the EM proposes wording, you refine it, and the next session reads the result. "
            "Edit the live ~/.claude, not the folder you installed from: the plugin cache is "
            "overwritten on update, and only CLAUDE.md, em-context.md and settings are yours to edit. "
            "Ask three things and write the answers into the CLAUDE.md Owner section: your role, what "
            "this machine is for, and how you like to be spoken to (tone). Offer the one or two "
            "customizations that follow from what the operator said in the orientation, not the "
            "whole menu: rename the reviewer personas (odd spellings such as the Staff Engineer are deliberate "
            "hot-words that summon a reviewer without ambiguity), set the project type so the right "
            "specialists route, or tune the engagement posture chosen above."
        ),
    },
    {
        "movement": 3,
        "title": "Take it for a spin",
        "text": (
            "Start a fresh Claude Code session in a throwaway directory (the install session is rooted "
            "in the clone, which is never a working repo). Pick something small and real, or a scratch "
            "project, and run it through the actual machinery: /workstream-start and ask the EM to orient you; then a tiny plan "
            "(say 'let's plan it' and watch it check the plan against the code and route it to a "
            "reviewer before any code is written); then /review-code on a recent diff; then "
            "/workstream-complete to close the loop. Start at the rung matching the operator's "
            "comfort and narrate why each step happens. For the substrate-free posture, demo a "
            "brief-then-report at a milestone instead of the full ceremony."
        ),
    },
    {
        "movement": 4,
        "title": "Point it at a project",
        "text": (
            "Start a fresh Claude Code session in the repo you choose (the install session is rooted in "
            "the clone). Repo onboarding is opt-in and happens only after the test drive. Ask which repo "
            "to start with. An existing repo: run /coordinator:repo-setup from inside "
            "it. Something new: run /coordinator:new-project. If the test drive already ran in one "
            "repo, confirm that repo and set it up rather than asking again. End the tour by "
            "recording orientation_completed."
        ),
    },
)

STATUS_LINE_LAUNCHER = "statusline-launch.py"
# Quote-free, `$`-free and absolute-path-free so one git-synced settings.json value runs on every
# box: `~` is expanded by the shell Claude Code runs it through, `python` is absent on macOS and
# `python3` is a Store stub on Windows, hence the ordered fallback.
STATUS_LINE_CMD = f"python ~/.claude/{STATUS_LINE_LAUNCHER} || python3 ~/.claude/{STATUS_LINE_LAUNCHER}"


def status_line_cmd(config_dir: Path) -> str:
    """The statusLine command for a config dir: the git-synced `~/.claude` form when the launcher
    lands there, else the same shape naming the launcher's absolute path (that settings.json is not
    the synced one)."""
    try:
        home_form = config_dir.resolve() == (Path.home() / ".claude").resolve()
    except OSError:
        home_form = False
    if home_form:
        return STATUS_LINE_CMD
    launcher = (config_dir / STATUS_LINE_LAUNCHER).as_posix()
    return f"python {launcher} || python3 {launcher}"


# Written beside settings.json; reads the sibling breadcrumb so no per-box root lands in the command.
STATUS_LINE_LAUNCHER_SOURCE = '''\
"""Runs the live coordinator statusline: the root is named by the `.coordinator-plugin-root`
breadcrumb beside this file."""
import runpy
import sys
from pathlib import Path

try:
    root = (Path(__file__).resolve().parent / ".coordinator-plugin-root").read_text(encoding="utf-8").strip()
except OSError:
    root = ""
if not root:
    sys.exit("statusline-launch: .coordinator-plugin-root is missing or empty; re-run scripts/setup.py")
script = str(Path(root) / "bin" / "statusline.py")
sys.argv[0] = script
runpy.run_path(script, run_name="__main__")
'''


def _is_coordinator_status_line(command: str) -> bool:
    """A statusLine command that already runs a coordinator statusline: the launcher form, the
    older `$(cat breadcrumb)` form, or an older install's plugin-cache glob
    (`…/coordinator-claude/coordinator/*/bin/statusline.py`). Each is replaced in place;
    relocating one into statusline-inner.json would make the statusline delegate to a stale
    copy of itself."""
    normalized = command.replace("\\", "/")
    return STATUS_LINE_LAUNCHER in normalized or ".coordinator-plugin-root" in normalized or (
        "coordinator" in normalized and "/bin/statusline.py" in normalized)


CONTEXT7_PLUGIN = "context7@claude-plugins-official"
CONTEXT7_MARKETPLACE = "anthropics/claude-plugins-official"
NOTEBOOKLM_NAMES = ("notebooklm-mcp", "gemini-notebook-mcp", "Gemini Notebook MCP")

_MODE_ADAPTATION = {
    "auto": ("extras_on", "Presume the recommended extras and list them at the end as added."),
    "bypass": ("extras_on", "Presume the recommended extras; no mode-switch nudge."),
    "bypassPermissions": ("extras_on", "Presume the recommended extras; no mode-switch nudge."),
    "plan": ("extras_on", "Present the whole plan once, then execute without further prompts."),
    "acceptEdits": ("extras_off", "Ask per change; do not pre-install extras."),
    "default": ("extras_off", "Ask per change; do not pre-install extras."),
}
_NUDGE_MODES = {"plan", "acceptEdits", "default"}


def doctrine_root() -> Path | None:
    """The plugin root a provisioned DoE box records in `<claude_dir>/.coordinator-plugin-root`,
    or None when the breadcrumb is absent, empty or names a missing directory."""
    try:
        text = (claude_dir() / ".coordinator-plugin-root").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return Path(text) if text and Path(text).is_dir() else None


def plugin_root_resolution() -> tuple[Path, str]:
    """(root, source) from the three manifest-independent origins: CLAUDE_PLUGIN_ROOT, the DoE
    doctrine breadcrumb, else the clone this script sits in (`engine-clone`)."""
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env), "CLAUDE_PLUGIN_ROOT"
    doctrine = doctrine_root()
    if doctrine:
        return doctrine, "doctrine-breadcrumb"
    return Path(__file__).resolve().parents[2], "engine-clone"


def plugin_root_source() -> tuple[Path, str]:
    """(root, where it came from). With `CLAUDE_PLUGIN_ROOT` unset the root is this script's own
    `coordinator/` when it carries the install manifest, else the `coordinator/` of the DoE checkout
    the machine registry names; a DoE box's `.coordinator-plugin-root` breadcrumb wins over both. A
    script copy hosted elsewhere (klabauter) never supplies the manifest. Neither found: the script's `coordinator/`, flagged as manifest-less."""
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env), "CLAUDE_PLUGIN_ROOT"
    doctrine = doctrine_root()
    if doctrine:
        return doctrine, "doctrine breadcrumb (CLAUDE_PLUGIN_ROOT unset)"
    own = Path(__file__).resolve().parents[2]
    if manifest_path(own).is_file():
        return own, "script clone (CLAUDE_PLUGIN_ROOT unset)"
    tree = doe_tree_from_evidence() or _manifest_bearing_content_root()
    if tree and manifest_path(tree / "coordinator").is_file():
        return (tree / "coordinator",
                "DoE checkout named by the machine registry (CLAUDE_PLUGIN_ROOT unset)")
    return own, "script clone (CLAUDE_PLUGIN_ROOT unset; no install manifest found there or in a registered DoE checkout)"


def _manifest_bearing_content_root() -> Path | None:
    """A registered `repos.content_root` / `repos.doe_claude` checkout that carries the install
    manifest under `coordinator/`, with no dev-repo sentinel required; a publish mirror never counts."""
    flat = _registry_flat()
    for key in ("repos.content_root", "repos.doe_claude"):
        value = str(flat.get(key) or "").strip()
        if value and not _is_registered_publish_mirror(Path(value)) \
                and manifest_path(Path(value) / "coordinator").is_file():
            return Path(value)
    return None


def default_plugin_root_env() -> Path | None:
    """On a DoE box (breadcrumb, `.coordinator-dev-repo` tree, or registered content root) with
    `CLAUDE_PLUGIN_ROOT` unset, export the DoE plugin root so spawned children resolve it too.
    Returns the root exported, else None; an unset env on a non-DoE box stays unset."""
    if os.environ.get("CLAUDE_PLUGIN_ROOT"):
        return None
    root, source = plugin_root_source()
    own_is_doe = source.startswith("script clone (CLAUDE_PLUGIN_ROOT unset)") and is_doe_tree(root.parent)
    if not (source.startswith(("doctrine breadcrumb", "DoE checkout")) or own_is_doe):
        return None
    if not manifest_path(root).is_file():
        return None
    os.environ["CLAUDE_PLUGIN_ROOT"] = str(root)
    return root


ENGINE_TARGETS = ("main", "candidate")


def register_engine(engine_root: str | None, engine_target: str | None) -> list[str]:
    """Write `repos.claude_klabauter` / `engine.target` to the registry on a box with no engine
    yet resolvable; idempotent. Returns the `key=value` pairs asked for. ValueError on a root that
    is not an engine checkout or a target outside `ENGINE_TARGETS`."""
    pairs: dict[str, str] = {}
    if engine_root:
        root = Path(engine_root).expanduser().resolve()
        if not (root / "coordinator_core").is_dir():
            raise ValueError(f"--engine-root {root} holds no coordinator_core/; pass the engine checkout")
        pairs["repos.claude_klabauter"] = str(root)
    if engine_target:
        if engine_target not in ENGINE_TARGETS:
            raise ValueError(f"--engine-target must be one of {', '.join(ENGINE_TARGETS)}, got {engine_target!r}")
        pairs["engine.target"] = engine_target
    if "repos.claude_klabauter" in pairs and pairs["repos.claude_klabauter"] not in sys.path:
        sys.path.insert(0, pairs["repos.claude_klabauter"])
    if pairs:
        from coordinator_core.machine_resolver import registry_set
        for key, value in pairs.items():
            registry_set(key, value)
    return [f"{k}={v}" for k, v in pairs.items()]


def manifest_found() -> bool:
    return manifest_path().is_file()


def plugin_root() -> Path:
    return plugin_root_source()[0]


def settings_home() -> Path:
    env = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if env:
        return Path(env)
    return Path(os.environ.get("CLAUDE_HOME") or Path.home()) / ".coordinator-claude-settings"


def claude_dir() -> Path:
    """The harness config dir: `CLAUDE_CONFIG_DIR` (as the gauge reads it), else `~/.claude`."""
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    if override:
        return Path(override)
    return Path(os.environ.get("CLAUDE_HOME") or Path.home()) / ".claude"


def _interpreter_meets_311(path: str) -> bool:
    """Whether `path` is Python >= 3.11: the running interpreter answers from
    `sys.version_info` (no spawn); any other path is probed once."""
    if path == sys.executable:
        return sys.version_info[:2] >= (3, 11)
    try:
        proc = subprocess.run(
            [path, "-c", "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"],
            capture_output=True, timeout=10, creationflags=_no_console(),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def _py(script, *args) -> list[str]:
    """argv for running `script` under a real console python >= 3.11 (bin/lib/python_interp), never a forwarder exe.

    Raises OSError when the resolved interpreter is older than 3.11 or none
    resolves: the scripts this installer spawns need 3.11, and handing them the
    PATH `python3` that `resolve_console_python` falls back to (or a forwarder
    `sys.executable`) fails later and quieter than refusing here.
    """
    sys.path.insert(0, str(plugin_root() / "bin" / "lib"))
    try:
        from python_interp import python_argv
        argv = python_argv(str(script), *map(str, args))
    except ImportError:
        argv = None
    finally:
        sys.path.pop(0)
    interpreter = sys.executable
    if argv is None and sys.version_info[:2] >= (3, 11) and interpreter:
        argv = [interpreter, str(script), *map(str, args)]
    if argv is None or not _interpreter_meets_311(argv[0]):
        raise OSError(
            f"no console Python >= 3.11 found to run {script} "
            f"(resolved {argv[0] if argv else None!r}; sys.executable={sys.executable!r})"
        )
    return argv


def manifest_path(root: Path | None = None) -> Path:
    root = root or plugin_root()
    for cand in (root / "docs" / "install" / "agent-install-manifest.json",
                 root / "coordinator" / "docs" / "install" / "agent-install-manifest.json"):
        if cand.is_file():
            return cand
    return root / "docs" / "install" / "agent-install-manifest.json"


def forwarder(name: str) -> str | None:
    """Settings-home forwarder path for `name`, or None when absent."""
    bindir = settings_home() / "bin"
    suffixes = ("", ".exe", ".cmd") if platform.system() != "Windows" else (".exe", ".cmd", "")
    for suffix in suffixes:
        cand = bindir / (name + suffix)
        if cand.is_file():
            return str(cand)
    return None


def _no_console() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


class SpawnFailure(int):
    """Exit code `run` returns when the command never ran to completion (OSError or timeout).

    Compares equal to 127, so existing `rc != 0` callers are unchanged; `isinstance` tells it from a real exit 127.
    """


class LaunchBlocked(SpawnFailure):
    """A launch the OS refused (WinError 4551, or exit 126 with `Permission denied` under Git Bash).

    Smart App Control blocks unsigned forwarder images this way; the command's own work never ran.
    """


LAUNCH_BLOCKED_REMEDY = (
    "Smart App Control blocked an unsigned forwarder: re-run the install and choose forwarder_route=py "
    "(works with Smart App Control on), or turn Smart App Control off for the .exe route, then retry"
)
_WINERROR_CODE_INTEGRITY = 4551


def _launch_class(rc: int, out: str) -> int:
    """`rc` as a LaunchBlocked when `out` shows an exit-126 permission denial, else `rc` unchanged."""
    if rc == 126 and "permission denied" in out.lower():
        return LaunchBlocked(126)
    return rc


def run(argv: list[str], timeout: int = 300) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, creationflags=_no_console(),
        )
    except OSError as exc:
        if getattr(exc, "winerror", None) == _WINERROR_CODE_INTEGRITY:
            return LaunchBlocked(127), f"{type(exc).__name__}: {exc} (blocked by Smart App Control)"
        return SpawnFailure(127), f"{type(exc).__name__}: {exc}"
    except subprocess.TimeoutExpired as exc:
        return SpawnFailure(127), f"{type(exc).__name__}: {exc}"
    out = (proc.stdout + proc.stderr).strip()
    return _launch_class(proc.returncode, out), out


def sac_state() -> int | None:
    """Smart App Control state from the registry: 0 off, 1 enforcing, 2 evaluation; None when unreadable."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\CI\Policy") as key:
            value, _ = winreg.QueryValueEx(key, "VerifiedAndReputablePolicyState")
    except (ImportError, OSError):
        return None
    return value if isinstance(value, int) else None


def _is_windows() -> bool:
    return platform.system() == "Windows"


def default_forwarder_route() -> str:
    """`exe` only when Smart App Control reads off; enforcing, evaluation (which can promote itself) and unreadable read `py`."""
    return "exe" if sac_state() == 0 else "py"


# --------------------------------------------------------------------------- decisions


@dataclass(frozen=True)
class Decision:
    id: str
    question: str
    why: str
    options: tuple
    default: object
    level: str  # required | recommended | optional


@dataclass(frozen=True)
class Extra:
    """One optional extra: the questionnaire item and the decision it answers read this one row."""
    id: str  # decision id
    prompt: str
    leaves_out: str  # what answering `n` leaves out
    accept: str
    decline: str
    step: str = ""  # risky step whose consent an accepted answer grants
    presumed: bool = False  # a permission-mode default of `accept` counts as the operator's consent


OPTIONAL_EXTRAS: tuple[Extra, ...] = (
    Extra("track_claude_home", "Git-track ~/.claude so your configuration is versioned and backed up?",
          "~/.claude stays untracked: no versioned backup of your configuration, and the identity file has no git repository to sit in.",
          "init", "skip", step="claude_home_repo"),
    Extra("context7", "Install the Context7 plugin (live library documentation for agents)?",
          "agents that verify API claims (docs-checker, executor, staff reviewers) guess instead of reading live library docs.",
          "install", "skip", step="context7", presumed=True),
    Extra("notebooklm", "Use NotebookLM (deep-research Pipeline D)?",
          "deep-research Pipeline D is unavailable; pipelines A-C are unaffected.",
          "install", "skip", presumed=True),
    Extra("status_lines", "Wire the coordinator status line and subagent status line?",
          "no context-window sidecar, so the context-pressure advisory has nothing to read, and subagent rows disappear.",
          "wire", "skip"),
    Extra("forwarder_route", "Use the fast prebuilt .exe forwarders (the .py route is slower but works with Smart App Control on)?",
          "the .py route is used instead: slower (an interpreter start per call) but Smart App Control and UAC stay on.",
          "exe", "py"),
    Extra("open_claude_home", "Open ~/.claude in your file manager?",
          "nothing opens; browse to ~/.claude yourself to edit CLAUDE.md.",
          "open", "skip"),
)


def extra_prompt(extra_id: str) -> str:
    return next(e.prompt for e in OPTIONAL_EXTRAS if e.id == extra_id)


def detect_profile() -> str:
    """The hook-side machine-profile reader's answer: explicit registry value, else
    `author` when a registered repo carries the dev-repo sentinel. `consumer` when the
    reader cannot be loaded, matching its own fail-open value."""
    scripts = str(plugin_root() / "hooks" / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    try:
        from _machine_profile import machine_profile
    except Exception:
        return "consumer"
    profile = machine_profile()
    if profile == "author" and not _authoring_tree_exists():
        return "consumer"
    return profile


def _authoring_tree_exists() -> bool:
    """True iff the evidence or an existing `repos.*` registry path names a DoE source tree on this box."""
    if doe_tree_from_evidence():
        return True
    return any(is_doe_tree(Path(v)) for k, v in _registry_flat().items()
               if k.startswith("repos.") and isinstance(v, str) and v)


def default_guard_level(profile: str) -> str:
    """`warn` for every profile; `profile` is kept for caller-signature stability."""
    return "warn"


def _git_user() -> str:
    rc, out = run(["git", "config", "user.name"], timeout=10)
    return out.strip() if rc == 0 else ""


def build_decisions(permission_mode: str | None = None) -> list[Decision]:
    profile = detect_profile()
    extras_on = _MODE_ADAPTATION.get(permission_mode or "", ("extras_on", ""))[0] == "extras_on"
    extra_default = "install" if extras_on else "skip"
    route = [Decision(
        "forwarder_route", extra_prompt("forwarder_route"),
        "The door forwarders are unsigned, so Smart App Control blocks the .exe images. py keeps Smart App Control on and pays an interpreter start per call; exe is fastest. The default follows the Smart App Control state read from the registry.",
        ("py", "exe"), default_forwarder_route(), "recommended",
    )] if _is_windows() else []
    return [
        Decision(
            "posture", POSTURE_QUESTION, POSTURE_WHY,
            tuple(f"{k}: {v}" for k, v in POSTURE_OPTIONS.items()), None, "required",
        ),
        Decision(
            "track_claude_home", extra_prompt("track_claude_home"),
            "The identity file lives in ~/.claude and must sit inside a git repository. Creates a local repository only: no remote, no push.",
            ("init", "skip"), "init", "recommended",
        ),
        Decision(
            "orientation",
            "Take the guided tour after install?",
            "The tour explains the EM/PM contract and tailors your CLAUDE.md; it runs in this session.",
            ("tour-now", "later"), "tour-now", "recommended",
        ),
        Decision(
            "operator_name",
            "What name should the coordinator use for you?",
            "The EM addresses you by it and records it in your identity file.",
            ("<free text>",), _git_user() or None, "required",
        ),
        Decision(
            "owner_profile",
            "In a sentence or two: your role, what this machine is for, and how you like Claude to talk to you?",
            "Rendered into the Owner section of your seeded CLAUDE.md. Blank keeps a placeholder for you and the EM to fill in during the tour.",
            ("<free text>",), "", "optional",
        ),
        Decision(
            "machine_profile",
            "Is this a consumer box or an author box?",
            "Author boxes carry strict guards and fleet machinery; consumer boxes never read or write author fleet state.",
            ("consumer", "author"), profile, "recommended",
        ),
        Decision(
            "guard_level",
            "How strict should non-destructive guards be?",
            "warn is the default: a guard outside the irreversible-act floor never denies and adds at most one advisory line per event; off is silent. Irreversible-act guards stay hard. Change later: machine-local set coordinator.guard_level <level>.",
            ("strict", "warn", "off"), default_guard_level(profile), "recommended",
        ),
        *route,
        Decision(
            "context7", extra_prompt("context7"),
            "Agents that verify API claims (docs-checker, executor, staff reviewers) guess without it. Registers the claude-plugins-official marketplace itself.",
            ("install", "skip"), extra_default, "recommended",
        ),
        Decision(
            "notebooklm", extra_prompt("notebooklm"),
            "Powers deep research; pipelines A-C work without it. The installer only checks that it is registered; install it per its own README.",
            ("install", "skip"), extra_default, "recommended",
        ),
        Decision(
            "status_lines", extra_prompt("status_lines"),
            "The main line is the only producer of the context-window sidecar the context-pressure advisory reads; subagent rows show model, effort and distance to compaction.",
            ("wire", "skip"), "wire", "recommended",
        ),
        Decision(
            "settings_env",
            "Apply the required settings.json env values?",
            "Sets CLAUDE_CODE_ENABLE_TODO_TOOLS (Task tools) and FNM_LOGLEVEL=error (keeps fnm version-switch output off agent stdout) and removes the retired CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS if present. Lands next session.",
            ("apply", "skip"), "apply", "recommended",
        ),
        Decision(
            "hooks_marker",
            "Generate settings.json hooks?",
            "Plugin installs deliver hooks themselves, so auto records INHERITED and generates nothing; create forces generation on a machine without plugin delivery.",
            ("auto", "create", "skip"), "auto", "optional",
        ),
        Decision(
            "coordinator_currency",
            "Write docs/coordinator-currency.yaml into the current repo?",
            "Records which coordinator version this repo was set up against; an untracked file in the current directory. Commit it in a project repo, skip it inside the plugin clone.",
            ("write", "skip"), "skip", "optional",
        ),
        Decision(
            "agy_runtime",
            "Use the Antigravity (agy) CLI as a runtime for agent-pipe delivery on this machine?",
            "Recorded as an answer for the agent to carry; installs nothing. The default follows whether `agy` is on PATH.",
            ("use", "skip"), "use" if shutil.which("agy") else "skip", "optional",
        ),
        Decision(
            "open_claude_home", extra_prompt("open_claude_home"),
            "Shows you the files that govern your sessions (CLAUDE.md and friends) so you can edit them.",
            ("open", "skip"), "open", "optional",
        ),
    ]


def decision_json(d: Decision) -> dict:
    return {
        "id": d.id, "question": d.question, "why": d.why, "options": list(d.options),
        "default": d.default, "level": d.level,
    }


def resolve_answers(raw: dict, permission_mode: str | None, non_interactive: bool) -> tuple[dict, list[str]]:
    """Merge `raw` over declared defaults. Returns (answers, problems)."""
    decisions = {d.id: d for d in build_decisions(permission_mode)}
    problems = [f"unknown decision id: {k}" for k in raw if k not in decisions and k not in ("consent", "plan_id")]
    answers: dict = {}
    risky = {s.id for s in STEPS if s.risky}
    consent = raw.get("consent", {})
    if not isinstance(consent, dict):
        problems.append("consent must be an object of booleans keyed by risky step id")
        consent = {}
    for sid, granted in consent.items():
        if sid not in risky:
            problems.append(f"consent: {sid!r} is not a risky step ({sorted(risky)})")
        elif not isinstance(granted, bool):
            problems.append(f"consent.{sid} must be true or false")
    answers["consent"] = {k: v for k, v in consent.items() if k in risky and isinstance(v, bool)}
    if "plan_id" in raw:
        if isinstance(raw["plan_id"], str) and PLAN_ID_RE.fullmatch(raw["plan_id"]):
            answers["plan_id"] = raw["plan_id"]
        else:
            problems.append("plan_id must match [A-Za-z0-9_-]{1,64}")
    profile = raw.get("machine_profile") or decisions["machine_profile"].default
    for did, d in decisions.items():
        if did in raw:
            value = raw[did]
        elif did == "guard_level":
            value = default_guard_level(profile)
        else:
            value = d.default
        if value is None:
            if did == "posture":
                problems.append("posture: no answer; the human chooses it, and no default or inherited identity value is applied")
            elif d.level == "required":
                problems.append(f"required decision has no answer and no default: {did}")
            continue
        allowed = [o.split(":")[0] for o in d.options] if did == "posture" else list(d.options)
        if allowed != ["<free text>"] and value not in allowed:
            problems.append(f"{did}: {value!r} not one of {allowed}")
        answers[did] = value
    for extra in OPTIONAL_EXTRAS:
        if extra.presumed and extra.step in risky and answers.get(extra.id) == extra.accept:
            answers["consent"].setdefault(extra.step, True)
    return answers, problems


# --------------------------------------------------------------------------- steps


STAGES = ("host", "artifact", "load", "self-test", "inspection")


@dataclass
class StepResult:
    status: str
    detail: str = ""
    follow_up: str = ""
    stage: str = ""  # readiness stage of a FAILED result, one of STAGES
    retryable: bool = False  # True only when a subprocess invocation failed (non-zero exit, timeout, spawn error)


def _fail(stage: str, detail: str, follow_up: str = "", *, retryable: bool = False) -> StepResult:
    return StepResult(FAILED, detail, follow_up, stage, retryable)


def _fail_run(stage: str, rc: int, detail: str, follow_up: str = "") -> StepResult:
    """FAILED from a `run` result (an invocation failure, so retryable); BLOCKED when the OS refused the launch."""
    if isinstance(rc, LaunchBlocked):
        return StepResult(BLOCKED, f"{detail} (launch blocked by Smart App Control)",
                          follow_up or LAUNCH_BLOCKED_REMEDY, stage)
    if not follow_up and isinstance(rc, SpawnFailure):
        follow_up = "the command could not be launched or timed out; check the tool is installed, then retry"
    return _fail(stage, detail, follow_up, retryable=True)


@dataclass
class Ctx:
    answers: dict
    permission_mode: str | None = None
    extras: list = field(default_factory=list)
    restart_needed: bool = False
    next_session: list = field(default_factory=list)
    engine_deps_failed: str = ""  # detail of a failed engine_deps step; engine-backed steps refuse to spawn
    engine_root: str = ""  # set by step_engine_root; the receipt writer imports the setup-state module from it


def _read_json(path: Path) -> dict:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


def _read_json_strict(path: Path) -> dict | None:
    """Like `_read_json`, but None when the file exists and cannot be read as a JSON object."""
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _machine_local_set(key: str, value: str) -> StepResult:
    fwd = forwarder("machine-local")
    if not fwd:
        return _fail("artifact", "machine-local forwarder absent (run the substrate step first)")
    try:
        from coordinator_core.machine_resolver import registry_get
        current = registry_get(key)
    except Exception:  # an engine not yet importable reads as unset; the set below decides
        current = None
    if current == value:
        return StepResult(INHERITED, f"{key} already {value}")
    try:
        from coordinator_core import machine_local_spawn
    except ImportError as exc:
        return _fail("load", f"coordinator_core not importable, cannot set {key}: {exc}", retryable=True)
    cp = machine_local_spawn.run_bounded([fwd, "set", key, value])
    if cp is None:
        return _fail_run("load", SpawnFailure(127), f"machine-local set {key} could not launch or outlived its ceiling")
    out = (cp.stdout + cp.stderr).strip()
    return StepResult(RAN, f"{key}={value}") if cp.returncode == 0 else _fail_run("load", _launch_class(cp.returncode, out), out)


def step_forwarder_route(ctx: Ctx) -> StepResult:
    """Persist the chosen forwarder route in-process (the machine-local forwarder is not deposited yet)."""
    route = ctx.answers.get("forwarder_route")
    if route is None:
        return StepResult(SKIPPED, "no forwarder route choice on this platform")
    root = ctx.engine_root
    inserted = bool(root) and root not in sys.path
    if inserted:
        sys.path.insert(0, root)
    try:
        from coordinator_core.machine_resolver import registry_get, registry_set
        if registry_get(_FORWARDER_ROUTE_KEY) == route:
            return StepResult(INHERITED, f"{_FORWARDER_ROUTE_KEY} already {route}")
        registry_set(_FORWARDER_ROUTE_KEY, route)
    except Exception as exc:
        return _fail("load", f"cannot set {_FORWARDER_ROUTE_KEY}: {type(exc).__name__}: {exc}", retryable=True)
    finally:
        if inserted and root in sys.path:
            sys.path.remove(root)
    return StepResult(RAN, f"{_FORWARDER_ROUTE_KEY}={route}")


_FORWARDER_ROUTE_KEY = "coordinator.forwarder_route"


def step_orientation(ctx: Ctx) -> StepResult:
    fwd = forwarder("coordinator-setup-state")
    if ctx.answers.get("orientation") != "tour-now":
        return StepResult(SKIPPED, "orientation deferred by answer",
                          "say 'walk me through the coordinator' any time")
    if fwd:
        run([fwd, "record", "orientation_started"], timeout=30)
    return StepResult(RAN, "tour Movements 2-4 run inline after this block",
                      "run the `tour` movements in this result, in this session")


def step_system_prereqs(ctx: Ctx) -> StepResult:
    manifest = _read_json(manifest_path())
    missing = []
    for item in manifest.get("system_prerequisites", []):
        if item["id"] == "python":
            continue
        cmd = {"claude_code": "claude", "git_lfs": "git-lfs", "1password_cli": "op",
               "ue": "UnrealEditor"}.get(item["id"], item["id"])
        if item["id"] in ("longpaths", "clone_auth", "bash"):
            continue
        if not shutil.which(cmd):
            missing.append(f"{item['id']}({item['tier']})")
    hard = [m for m in missing if m.endswith("(hard)")]
    detail = "missing: " + ", ".join(missing) if missing else "all probed prerequisites present"
    follow_up = "install the missing tools; remediation text is in the manifest" if missing else ""
    return _fail("host", detail, follow_up) if hard else StepResult(RAN, detail, follow_up)


def step_engine_root(ctx: Ctx) -> StepResult:
    ok, root = _engine_root()
    if ok:
        ctx.engine_root = root
        return StepResult(INHERITED, f"engine root {root}")
    return _fail("artifact", "engine root does not resolve",
                 "clone the engine as a sibling of this plugin clone and register it: machine-local set repos.claude_klabauter <path>")


def _deps_blocked(ctx: Ctx) -> StepResult | None:
    if not ctx.engine_deps_failed:
        return None
    return _fail("load", f"engine_deps failed: {ctx.engine_deps_failed}",
                 "fix the engine_deps step, then re-run the install")


def step_engine_deps(ctx: Ctx) -> StepResult:
    script, why = _engine_setup_script()
    if script is None:
        ctx.engine_deps_failed = why
        return _fail("load", why, "clone the engine as a sibling of this plugin clone and register it: machine-local set repos.claude_klabauter <path>")
    rc, out = run(_py(str(script), "--deps-only", "--i-am-agent"), timeout=600)
    detail = out.splitlines()[-1] if out else f"exited {rc}"
    if rc == 0:
        return StepResult(RAN, detail)
    ctx.engine_deps_failed = detail
    return _fail_run("load", rc, detail, "provision the engine deps: python <engine>/scripts/setup.py --deps-only")


def step_substrate(ctx: Ctx) -> StepResult:
    blocked = _deps_blocked(ctx)
    if blocked:
        return blocked
    ok, engine = _engine_root()
    if not ok:
        return _fail("artifact", "engine root does not resolve; substrate not deposited")
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin_root()))
    notes = []
    for name in ("install-substrate.py", "register-coordinator-mirror.py", "check-install-singularity.py"):
        script = Path(engine) / "coordinator" / "lib" / name
        if not script.is_file():
            return _fail("artifact", f"{script} not found")
        try:
            proc = subprocess.run(_py(str(script)), capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=600, env=env,
                                  creationflags=_no_console())
        except (OSError, subprocess.TimeoutExpired) as exc:
            return _fail("artifact", f"{name}: {exc}", retryable=True)
        if proc.returncode != 0:
            return _fail("artifact", f"{name} exited {proc.returncode}: {(proc.stdout + proc.stderr).strip()[-300:]}",
                         retryable=True)
        notes.append(name)
    return StepResult(RAN, "ran " + ", ".join(notes))


def _claude_home_repo_inherited() -> str:
    """Detail when ~/.claude already sits inside a git repository, else ''."""
    home = claude_dir()
    return f"{home} sits inside a git repository" if any((p / ".git").exists() for p in (home, *home.parents)) else ""


def step_claude_home_repo(ctx: Ctx) -> StepResult:
    home = claude_dir()
    if detail := _claude_home_repo_inherited():
        return StepResult(INHERITED, detail)
    if ctx.answers["track_claude_home"] == "skip":
        return StepResult(SKIPPED, "declined by answer", "the identity file needs a git repository at ~/.claude")
    home.mkdir(parents=True, exist_ok=True)
    rc, out = run(["git", "-C", str(home), "init"], timeout=60)
    if rc != 0:
        return _fail_run("load", rc, out)
    drift = plugin_root() / "bin" / "check-gitignore-template-drift.py"
    if drift.is_file():
        run(_py(str(drift), "--apply"), timeout=60)
    return StepResult(RAN, f"git init {home}; no remote created, nothing pushed")


def step_posture(ctx: Ctx) -> StepResult:
    blocked = _deps_blocked(ctx)
    if blocked:
        return blocked
    fwd = forwarder("write-identity-file")
    if not fwd:
        return _fail("artifact", "write-identity-file forwarder absent (run the substrate step first)")
    home = os.environ.get("CLAUDE_HOME") or str(Path.home())
    argv = [fwd, "--claude-home", home, "--operator-name", str(ctx.answers["operator_name"]),
            "--engagement-posture", str(ctx.answers["posture"])]
    rc, out = run(argv, timeout=60)
    return StepResult(RAN, f"posture={ctx.answers['posture']}") if rc == 0 else _fail_run("load", rc, out)


_DISPATCH_BY_MODE = {
    "auto": "Dispatch subagents and make routine commits without asking first; ask only before heavyweight or hard-to-reverse actions.",
    "bypass": "Dispatch subagents and make routine commits without asking first; ask only before heavyweight or hard-to-reverse actions.",
    "bypassPermissions": "Dispatch subagents and make routine commits without asking first; ask only before heavyweight or hard-to-reverse actions.",
    "plan": "Present the whole plan once and wait for approval; after approval, dispatch subagents and commit without further prompts.",
    "acceptEdits": "Edits need no confirmation; ask before dispatching subagents, committing, or running other commands.",
    "default": "Ask before each change, including dispatching subagents and committing.",
}
_DISPATCH_BY_POSTURE = {
    "precision": "Show proposed changes before making them and consult often, including on implementation detail.",
    "default": "Act on engineering calls autonomously and surface tradeoffs before forks.",
    "substrate-free": "Report at milestones and surface only ship-level and product-level decisions.",
}


OWNER_PROFILE_PLACEHOLDER = (
    "Role, what this machine is for, and preferred tone: not yet recorded. Tell the EM and it will write them here."
)


def claude_md_values(answers: dict, permission_mode: str | None) -> dict:
    """Placeholder values for CLAUDE.md.tmpl, derived from the answers; no owner-voice prose."""
    mode = permission_mode or "default"
    posture = answers["posture"]
    dispatch = _DISPATCH_BY_MODE.get(mode, _DISPATCH_BY_MODE["default"])
    return {
        "PM_NAME": str(answers["operator_name"]),
        "OWNER_PROFILE": str(answers.get("owner_profile") or OWNER_PROFILE_PLACEHOLDER),
        "PERMISSION_MODE": mode,
        "POSTURE": f"{posture}: {POSTURE_OPTIONS[posture]}",
        "DISPATCH_AND_COMMIT_PREFERENCE": f"{dispatch} {_DISPATCH_BY_POSTURE[posture]}",
    }


def unresolved_placeholders(text: str) -> list[str]:
    import re
    return sorted(set(re.findall(r"\{\{[^}]*\}\}", text)))


#: The one DoE-presence predicate (stdlib only: steps run before any engine is importable).
#: `scripts/setup.py` loads this module by path and calls the same functions.
_DOE_EVIDENCE_REGISTRY_KEYS = (
    "repos.content_root",
    "repos.doe_claude",  # private-name-ok: compat-fallback
    "engine.working_repos.content_root",
    "plugin.mirrors.coordinator-claude.live_path",
)
_CONTENT_ROOT_POINTER_NAMES = (".coordinator-content-root", ".content-root")  # private-name-ok: compat-fallback
_DEV_CLONE_DISTINCTIVE_MARKERS = (
    "canonical-structure.yaml",
    "artifact-shape-contract",
    "cockpit-contract",
)


def _registry_dir() -> Path:
    override = os.environ.get("MACHINE_LOCAL_REGISTRY_DIR")
    return Path(override) if override else settings_home() / "machine-local"


def _registry_flat() -> dict:
    """Merged `registry.toml` + `registry.local.toml` (later wins) as dotted keys; {} when unreadable."""
    try:
        import tomllib
    except ImportError:
        return {}
    reg_dir = _registry_dir()

    def flatten(data: dict, prefix: str = "") -> dict:
        out: dict = {}
        for k, v in data.items():
            if isinstance(v, dict):
                out.update(flatten(v, f"{prefix}{k}."))
            else:
                out[f"{prefix}{k}"] = v
        return out

    def read_registry(path: Path) -> str:
        # The installer can run before an engine is importable; only then does the plain read stand.
        try:
            from coordinator_core.shared_read import read_bytes_shared
        except ImportError:
            return path.read_text(encoding="utf-8")
        return read_bytes_shared(path).decode("utf-8")

    merged: dict = {}
    for name in ("registry.toml", "registry.local.toml"):
        try:
            merged.update(flatten(tomllib.loads(read_registry(reg_dir / name))))
        except (OSError, ValueError):
            continue
    return merged


def doe_evidence_values() -> list[str]:
    """Raw values that may name the DoE tree: content-root pointer files, then `_DOE_EVIDENCE_REGISTRY_KEYS`."""
    values: list[str] = []
    for name in _CONTENT_ROOT_POINTER_NAMES:
        for base in (settings_home() / "machine-local", Path(os.environ.get("CLAUDE_HOME") or Path.home()) / ".claude"):
            try:
                values.append((base / name).read_text(encoding="utf-8").strip())
            except OSError:
                continue
    flat = _registry_flat()
    values.extend(str(flat.get(key) or "") for key in _DOE_EVIDENCE_REGISTRY_KEYS)
    return values


def _is_registered_publish_mirror(path: Path) -> bool:
    flat = _registry_flat()
    target = os.path.normcase(os.path.realpath(path))
    for key, raw in flat.items():
        if key.startswith("publish.mirrors.") and key.endswith(".path") and raw:
            mirror = os.path.normcase(os.path.realpath(str(raw))).rstrip(os.sep)
            if target == mirror or target.startswith(mirror + os.sep):
                return True
    return False


def has_doe_dev_clone_marker(path: Path) -> bool:
    """True iff `path/coordinator/` carries a DoE-only dev-clone marker (the published repo has none)."""
    coordinator_dir = path / "coordinator"
    return coordinator_dir.is_dir() and any(
        (coordinator_dir / marker).exists() for marker in _DEV_CLONE_DISTINCTIVE_MARKERS
    )


def is_doe_tree(path: Path, is_publish_mirror: Callable[[Path], bool] | None = None) -> bool:
    """True iff `path` is a DoE source tree: an existing directory that is not a registered publish
    mirror and carries the `.coordinator-dev-repo` sentinel or the dev-clone markers. Decided from
    contents, never from the directory name."""
    mirror = is_publish_mirror or _is_registered_publish_mirror
    return (
        path.is_dir()
        and not mirror(path)
        and ((path / ".coordinator-dev-repo").is_file() or has_doe_dev_clone_marker(path))
    )


def doe_tree_from_evidence(
    values: list[str] | None = None, is_publish_mirror: Callable[[Path], bool] | None = None
) -> Path | None:
    """The DoE source tree this box's evidence names, else None: first of `values`
    (default `doe_evidence_values()`) that passes `is_doe_tree`."""
    for value in (doe_evidence_values() if values is None else values):
        if value and is_doe_tree(Path(value), is_publish_mirror):
            return Path(value)
    return None


def _registry_path_keys(flat: dict) -> list[str]:
    """Registry keys whose value is a filesystem path this box is expected to hold."""
    return sorted(
        k for k, v in flat.items()
        if isinstance(v, str) and v and (
            k.startswith(("repos.", "engine.working_repos."))
            or (k.startswith("publish.mirrors.") and k.endswith(".path"))
            or (k.startswith("plugin.mirrors.") and k.endswith(".live_path"))
        )
    )


def registry_absent_paths() -> dict[str, str]:
    """`{key: path}` for every path-valued registry key whose path does not exist on this box."""
    flat = _registry_flat()
    return {k: flat[k] for k in _registry_path_keys(flat) if not Path(flat[k]).exists()}


def prune_absent_repos() -> list[str]:
    """Drop absent `repos.*` lines from `registry.local.toml` (flat quoted-key shape only, root
    section only); returns the keys removed. A repo whose path exists is never touched."""
    target = _registry_dir() / "registry.local.toml"
    absent = [k for k in registry_absent_paths() if k.startswith("repos.")]
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return []
    table = re.search(r"^\s*\[", text, re.MULTILINE)
    root, tables = (text[:table.start()], text[table.start():]) if table else (text, "")
    removed = []
    for key in absent:
        root, n = re.subn(r'^"' + re.escape(key) + r'"[ \t]*=.*\n?', "", root, flags=re.MULTILINE)
        if n:
            removed.append(key)
    if removed:
        tmp = target.with_suffix(".toml.tmp")
        tmp.write_text(root + tables, encoding="utf-8", newline="")
        os.replace(tmp, target)
    return removed


def rewrite_content_root_pointers() -> list[str]:
    """Point every existing `_CONTENT_ROOT_POINTER_NAMES` file at `repos.content_root` when it
    names another path; returns the files rewritten. Nothing is created and an absent root is no target."""
    root = str(_registry_flat().get("repos.content_root") or "").strip()
    if not root or not Path(root).exists():
        return []

    def norm(p: str) -> str:
        return os.path.normcase(os.path.normpath(p))

    rewritten = []
    for name in _CONTENT_ROOT_POINTER_NAMES:
        for base in (_registry_dir(), Path(os.environ.get("CLAUDE_HOME") or Path.home()) / ".claude"):
            ptr = base / name
            try:
                current = ptr.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if norm(current) != norm(root):
                ptr.write_text(root + "\n", encoding="utf-8", newline="\n")
                rewritten.append(str(ptr))
    return rewritten


def _is_absolute_anywhere(s: str) -> bool:
    return Path(s).is_absolute() or PureWindowsPath(s).is_absolute()


def _missing_mcp_paths(spec: dict) -> list[str]:
    """The command (resolved on PATH when bare) and absolute argument paths of an MCP spec that are absent."""
    cmd = spec.get("command")
    args = spec.get("args")
    missing = []
    if isinstance(cmd, str) and cmd:
        if not (shutil.which(cmd) or (_is_absolute_anywhere(cmd) and Path(cmd).exists())):
            missing.append(cmd)
    missing += [a for a in (args if isinstance(args, list) else []) if isinstance(a, str)
                and _is_absolute_anywhere(a) and not Path(a).exists()]
    return missing


def dangling_rag_mcp() -> list[str]:
    """One line per project-rag MCP registration whose command or absolute argument path is absent
    on this box (a bare command is resolved on PATH). Covers Claude's JSON configs and Grok's
    `config.toml` (user and cwd). Reads config files only: no spawn, no network."""
    home = Path(os.environ.get("CLAUDE_HOME") or Path.home())
    found = []
    for path in (claude_dir() / "settings.json", home / ".claude.json", Path.cwd() / ".mcp.json"):
        cfg = _read_json(path)
        projects = cfg.get("projects")
        scopes = [cfg] + [p for p in (projects.values() if isinstance(projects, dict) else []) if isinstance(p, dict)]
        for scope in scopes:
            servers = scope.get("mcpServers")
            for name, spec in (servers.items() if isinstance(servers, dict) else []):
                if "project-rag" not in name and "project_rag" not in name or not isinstance(spec, dict):
                    continue
                missing = _missing_mcp_paths(spec)
                if missing:
                    found.append(f"{path}: {name} -> {', '.join(missing)}")
    for path in (Path.home() / ".grok" / "config.toml", Path.cwd() / ".grok" / "config.toml"):
        for name, spec in _toml_mcp_servers(path):
            if "project-rag" not in name and "project_rag" not in name:
                continue
            missing = _missing_mcp_paths(spec)
            if missing:
                found.append(f"{path}: {name} -> {', '.join(missing)}")
    return sorted(set(found))


def _toml_mcp_servers(path: Path) -> list[tuple[str, dict]]:
    """(name, spec) per MCP server in a host TOML config: any top-level `*mcp*` table of named
    tables, or array of tables carrying a `name`. Unreadable or malformed TOML yields nothing."""
    import tomllib
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out: list[tuple[str, dict]] = []
    for key, val in data.items():
        if "mcp" not in key.lower():
            continue
        if isinstance(val, dict):
            out += [(n, s) for n, s in val.items() if isinstance(s, dict)]
        elif isinstance(val, list):
            out += [(str(s.get("name") or ""), s) for s in val if isinstance(s, dict)]
    return out


def registry_hygiene_report() -> dict:
    """Read-only view of what `step_registry_hygiene` acts on."""
    return {"absent_paths": registry_absent_paths(), "dangling_rag_mcp": dangling_rag_mcp(),
            "authoring_tree": _authoring_tree_exists()}


def step_registry_hygiene(ctx: Ctx) -> StepResult:
    absent = registry_absent_paths()
    pruned = prune_absent_repos()
    pointers = rewrite_content_root_pointers()
    rag = dangling_rag_mcp()
    notes = []
    if absent:
        notes.append("absent registry paths: " + ", ".join(f"{k}={v}" for k, v in absent.items()))
    if pruned:
        notes.append("pruned repos: " + ", ".join(pruned))
    if pointers:
        notes.append("rewrote content-root pointers: " + ", ".join(pointers))
    if rag:
        notes.append("dangling project-rag MCP: " + "; ".join(rag))
    if absent and not _authoring_tree_exists():
        notes.append("no authoring tree on this box: machine_profile defaults to consumer")
    follow_up = "remove or repair the dangling project-rag MCP registration" if rag else ""
    if not notes:
        return StepResult(INHERITED, "registry paths and project-rag MCP registration resolve")
    return StepResult(RAN if pruned or pointers else INHERITED, "; ".join(notes), follow_up)


def step_claude_md_seed(ctx: Ctx) -> StepResult:
    if doe_tree_from_evidence():
        return StepResult(INHERITED, "derived from global doctrine")
    fwd = forwarder("render-template")
    if not fwd:
        return _fail("artifact", "render-template forwarder absent (run the substrate step first)")
    tmpl = plugin_root() / "templates" / "CLAUDE.md.tmpl"
    values = claude_md_values(ctx.answers, ctx.permission_mode)
    missing = [p for p in unresolved_placeholders(tmpl.read_text(encoding="utf-8"))
               if p.strip("{}") not in values]
    if missing:
        return _fail("inspection", f"template placeholders with no value: {missing}")
    out = claude_dir() / "CLAUDE.md"
    argv = [fwd, str(tmpl), "-o", str(out), "--guard-sentinel", "coordinator:claude-md-seed:v1"]
    argv += [f"{k}={v}" for k, v in values.items()]
    rc, msg = run(argv, timeout=60)
    if rc == 3:
        return StepResult(INHERITED, "hand-authored CLAUDE.md preserved")
    if rc != 0:
        return _fail_run("load", rc, msg)
    left = unresolved_placeholders(out.read_text(encoding="utf-8"))
    return _fail("inspection", f"unresolved placeholders survive: {left}") if left else \
        StepResult(RAN, "seeded CLAUDE.md from your answers")


def step_machine_profile(ctx: Ctx) -> StepResult:
    return _machine_local_set("coordinator.machine_profile", ctx.answers["machine_profile"])


def step_guard_level(ctx: Ctx) -> StepResult:
    return _machine_local_set("coordinator.guard_level", ctx.answers["guard_level"])


def _plugin_enabled(name: str) -> bool:
    return bool(_read_json(claude_dir() / "settings.json").get("enabledPlugins", {}).get(name))


def _context7_needs_auth() -> bool:
    """True when the harness's `mcp-needs-auth-cache.json` holds an entry for a context7 server."""
    try:
        cache = json.loads((claude_dir() / "mcp-needs-auth-cache.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    keys = cache if isinstance(cache, dict) else {}
    return any("context7" in str(k).lower() for k in keys)


def _context7_inherited() -> str:
    """Detail when context7 is enabled and not awaiting authentication, else ''."""
    return "context7 already enabled" if _plugin_enabled(CONTEXT7_PLUGIN) and not _context7_needs_auth() else ""


#: Risky step id -> probe returning the INHERITED detail ('' when the step still has work to do).
_INHERITED_PROBES: dict[str, Callable[[], str]] = {
    "claude_home_repo": _claude_home_repo_inherited,
    "context7": _context7_inherited,
}


def step_context7(ctx: Ctx) -> StepResult:
    if ctx.answers["context7"] == "skip":
        return StepResult(SKIPPED, "declined by answer")
    if detail := _context7_inherited():
        return StepResult(INHERITED, detail)
    if _plugin_enabled(CONTEXT7_PLUGIN):
        return StepResult(SKIPPED, "context7 enabled but needs authentication",
                          "authenticate context7: run /mcp in a Claude Code session and pick context7")
    claude = shutil.which("claude")
    if not claude:
        return _fail("load", "claude CLI not on PATH")
    rc, out = run([claude, "plugin", "marketplace", "add", CONTEXT7_MARKETPLACE], timeout=180)
    if rc != 0 and "already" not in out.lower():
        return _fail_run("load", rc, f"marketplace add failed: {out}")
    rc, out = run([claude, "plugin", "install", CONTEXT7_PLUGIN], timeout=180)
    if rc != 0:
        return _fail_run("load", rc, out)
    ctx.extras.append("context7")
    ctx.next_session.append("context7 loads next session")
    return StepResult(RAN, "marketplace registered, plugin installed")


def notebooklm_registered() -> bool:
    home = Path(os.environ.get("CLAUDE_HOME") or Path.home())
    for path in (claude_dir() / "settings.json", home / ".claude.json", Path.cwd() / ".mcp.json"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if any(name in text for name in NOTEBOOKLM_NAMES):
            return True
    return False


def step_notebooklm(ctx: Ctx) -> StepResult:
    if ctx.answers["notebooklm"] == "skip":
        return StepResult(SKIPPED, "declined by answer")
    if notebooklm_registered():
        return StepResult(INHERITED, "NotebookLM MCP server already registered")
    detail = ("not registered; install it per its README (github.com/jacob-bd/gemini-notebook-mcp-cli); "
              "MCP key is `gemini-notebook-mcp` (older: `notebooklm-mcp`)")
    for key in ("notebooklm-mcp", "gemini-notebook-mcp"):
        cmd = shutil.which(key)
        if cmd:
            return StepResult(SKIPPED, detail, f"register with `claude mcp add -s user {key} -- {cmd}`")
    return StepResult(SKIPPED, detail)


def step_status_lines(ctx: Ctx) -> StepResult:
    if ctx.answers["status_lines"] == "skip":
        return StepResult(SKIPPED, "declined by answer")
    path = claude_dir() / "settings.json"
    doc = _read_json_strict(path)
    if doc is None:
        return _fail("inspection", f"{path} exists but is not a readable JSON object; left untouched",
                     "fix or remove the file, then re-run")
    value = {"type": "command", "command": status_line_cmd(path.parent)}
    current = doc.get("statusLine")
    changed = []
    launcher = path.parent / STATUS_LINE_LAUNCHER
    try:
        launcher_stale = launcher.read_text(encoding="utf-8") != STATUS_LINE_LAUNCHER_SOURCE
    except OSError:
        launcher_stale = True
    if launcher_stale:
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text(STATUS_LINE_LAUNCHER_SOURCE, encoding="utf-8", newline="\n")
        changed.append(STATUS_LINE_LAUNCHER)
    if current != value:
        if isinstance(current, dict) and current.get("command") \
                and not _is_coordinator_status_line(str(current["command"])):
            inner = settings_home() / "statusline-inner.json"
            if not inner.exists():
                _write_json(inner, current)
        doc["statusLine"] = value
        changed.append("statusLine")
    # subagentStatusLine is deprecated; DoE's AgentRow mod (coordinator/hooks/modules/agent-row.js) renders the row.
    if doc.pop("subagentStatusLine", None) is not None:
        changed.append("removed subagentStatusLine")
    if not changed:
        return StepResult(INHERITED, "statusLine already wired")
    _write_json(path, doc)
    ctx.next_session.append("status lines render next session")
    return StepResult(RAN, "wired " + ", ".join(changed))


def step_settings_env(ctx: Ctx) -> StepResult:
    if ctx.answers["settings_env"] == "skip":
        return StepResult(SKIPPED, "declined by answer")
    script = plugin_root() / "bin" / "check-settings-env.py"
    settings = claude_dir() / "settings.json"
    if not settings.exists():
        _write_json(settings, {})
    elif _read_json_strict(settings) is None:
        return _fail("inspection", f"{settings} is not a readable JSON object; left untouched",
                     "fix or remove the file, then re-run")
    rc_c, out_c = run(_py(str(plugin_root() / "lib" / "compaction_defaults.py"),
                       "--apply", str(settings)), timeout=60)
    if rc_c != 0:
        return _fail_run("load", rc_c, out_c.strip() or "compaction_defaults --apply failed")
    if out_c.strip() == "applied":
        ctx.restart_needed = True
        ctx.next_session.append("40% auto-compact default applies next session")
    rc0, _ = run(_py(str(script)), timeout=60)
    if rc0 == 0:
        return StepResult(INHERITED, "env values already correct")
    rc, out = run(_py(str(script), "--apply"), timeout=60)
    if rc == 0:
        ctx.restart_needed = True
        ctx.next_session.append("settings env values apply next session")
    detail = out.splitlines()[-1] if out else ""
    return StepResult(RAN, detail) if rc == 0 else _fail_run("load", rc, detail)


def step_hooks_marker(ctx: Ctx) -> StepResult:
    choice = ctx.answers["hooks_marker"]
    if choice == "skip":
        return StepResult(SKIPPED, "declined by answer")
    fwd = forwarder("gen-settings-hooks")
    if not fwd:
        return _fail("artifact", "gen-settings-hooks forwarder absent (run the substrate step first)")
    marker = claude_dir() / ".coordinator-hooks-enabled"
    created = False
    if choice == "create":
        created = not marker.exists()
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    rc, out = run([fwd], timeout=120)
    if "plugin delivery" in out.lower() or "plugin-side hook delivery" in out.lower():
        if created:
            marker.unlink(missing_ok=True)  # plugin delivers: a marker beside it fires every hook twice
        return StepResult(INHERITED, "plugin delivers the hooks; nothing generated")
    if "no positive marker" in out.lower():
        return StepResult(SKIPPED, "hook generation off and plugin delivery not detected",
                          "answer hooks_marker=create if hooks are not delivered by the plugin")
    detail = out.splitlines()[-1] if out else ""
    return StepResult(RAN, detail) if rc == 0 else _fail_run("load", rc, detail)


def step_currency(ctx: Ctx) -> StepResult:
    if ctx.answers["coordinator_currency"] == "skip":
        return StepResult(SKIPPED, "declined by answer")
    ok, engine = _engine_root()
    script = Path(engine) / "coordinator" / "lib" / "coordinator_currency.py" if ok else None
    if not script or not script.is_file():
        return _fail("artifact", "coordinator_currency.py not found under the engine root")
    rc, out = run(_py(str(script), "write", str(Path.cwd()), str(plugin_root())))
    return StepResult(RAN, "wrote docs/coordinator-currency.yaml") if rc == 0 else _fail_run("load", rc, out)


def _engine_root() -> tuple[bool, str]:
    rc, out = run(_py(str(plugin_root() / "hooks" / "scripts" / "_engine_root.py")), timeout=60)
    root = out.splitlines()[-1].strip() if out.strip() else ""
    return (rc == 0 and bool(root) and Path(root).is_dir()), root


def step_open_claude_home(ctx: Ctx) -> StepResult:
    if ctx.answers["open_claude_home"] == "skip":
        return StepResult(SKIPPED, "declined by answer")
    target = str(claude_dir())
    system = platform.system()
    if system == "Windows":
        argv = ["explorer", target]
    elif system == "Darwin":
        argv = ["open", target]
    else:
        opener = shutil.which("xdg-open")
        if not opener or not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            return StepResult(SKIPPED, "no file manager available", f"browse to {target}")
        argv = [opener, target]
    try:
        subprocess.Popen(argv, creationflags=_no_console(), stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except OSError as exc:
        return _fail("load", str(exc), f"browse to {target}", retryable=True)
    return StepResult(RAN, f"opened {target}")


def step_repo_home(ctx: Ctx) -> StepResult:
    """Advisory: link ~/.claude into repo_home and note a non-Dev-Drive repo_home; never FAILED."""
    root = ctx.engine_root
    if not root:
        ok, found = _engine_root()
        root = found if ok else ""
    if not root:
        return StepResult(SKIPPED, "engine root does not resolve; repo_home affordances not applied")
    inserted = root not in sys.path
    if inserted:
        sys.path.insert(0, root)
    try:
        import importlib
        aff = importlib.import_module("coordinator_core.install.repo_home_affordances")
        try:
            home = aff.resolve_repo_home()
        except Exception as exc:  # a typed refusal naming the key: advisory here
            key = getattr(exc, "key", aff.REPO_HOME_KEY)
            return StepResult(SKIPPED, f"repo_home not set ({key})", f"set {key} to enable repo_home shortcuts")
        targets = {"claude-home": claude_dir()}
        try:
            gem = importlib.import_module("coordinator_core.group_em.gem_home")
            targets[gem.DEFAULT_DIRNAME] = gem.resolve_home()
        except Exception:  # unresolvable or checkout-inside home: no group-em shortcut
            pass
        results = aff.ensure_repo_home_shortcuts(home, targets)
        advisory = aff.dev_drive_advisory(home)
    except Exception as exc:  # advisory: never aborts the block
        return StepResult(SKIPPED, f"repo_home affordances unavailable: {type(exc).__name__}: {exc}")
    finally:
        if inserted and root in sys.path:
            sys.path.remove(root)
    detail = "; ".join(f"{r.name}: {r.status}" + (f" ({r.detail})" if r.detail else "") for r in results)
    status = RAN if any(r.status == aff.CREATED for r in results) else INHERITED
    return StepResult(status, detail or "no shortcuts requested", advisory or "")


@dataclass(frozen=True)
class Step:
    id: str
    fn: Callable[[Ctx], StepResult]
    implements: tuple = ()
    exempt: str = ""  # reason this step implements no manifest entry
    risky: bool = False  # mutates beyond the settings home; needs its own consent
    optional: bool = False  # advisory or presentation-only: its FAILED never withholds the concluded receipt


STEPS: tuple[Step, ...] = (
    Step("orientation", step_orientation, exempt="operator choice: the tour is not an install surface", optional=True),
    Step("system_prereqs", step_system_prereqs, ("system_prerequisites:*",)),
    Step("engine_root", step_engine_root, ("direct_deps:claude-klabauter",)),
    Step("forwarder_route", step_forwarder_route, exempt="operator choice: machine-local setting the substrate step reads"),
    Step("engine_deps", step_engine_deps, exempt="provisions engine deps the substrate scripts import"),
    Step("substrate", step_substrate, exempt="deposits the settings-home forwarders every later step calls"),
    Step("registry_hygiene", step_registry_hygiene, exempt="repairs the machine-local registry the later steps read", optional=True),
    Step("settings_env", step_settings_env, ("required_local_surfaces:settings-env", "required_env_vars:*")),
    Step("claude_home_repo", step_claude_home_repo, exempt="prerequisite of the identity file", risky=True),
    Step("posture", step_posture, exempt="operator choice: recorded in the identity file"),
    Step("claude_md_seed", step_claude_md_seed, exempt="operator file seeded from answers"),
    Step("machine_profile", step_machine_profile, exempt="operator choice: machine-local setting"),
    Step("guard_level", step_guard_level, exempt="operator choice: machine-local setting"),
    Step("context7", step_context7, ("required_mcp_surfaces:context7",), risky=True, optional=True),
    Step("notebooklm", step_notebooklm,
         ("required_mcp_surfaces:gemini-notebook-mcp|required_mcp_surfaces:notebooklm-mcp",), optional=True),
    Step("status_lines", step_status_lines, ("required_local_surfaces:statusline-registration",)),
    Step("hooks_marker", step_hooks_marker, ("required_local_surfaces:hook-delivery",)),
    Step("coordinator_currency", step_currency, exempt="per-repo record, not a machine install surface"),
    Step("repo_home", step_repo_home, exempt="advisory: shortcuts and Dev Drive note for repo_home", optional=True),
    Step("open_claude_home", step_open_claude_home, exempt="presentation only", optional=True),
)

STEP_DECISION = {"orientation": "orientation", "claude_md_seed": "posture", "claude_home_repo": "track_claude_home", "settings_env": "settings_env", "posture": "posture",
                 "machine_profile": "machine_profile", "guard_level": "guard_level",
                 "forwarder_route": "forwarder_route",
                 "context7": "context7", "notebooklm": "notebooklm", "status_lines": "status_lines",
                 "hooks_marker": "hooks_marker", "coordinator_currency": "coordinator_currency",
                 "open_claude_home": "open_claude_home"}


# --------------------------------------------------------------------------- drift check


def manifest_entry_ids(manifest: dict) -> set[str]:
    ids: set[str] = set()
    for section in ("direct_deps", "required_mcp_surfaces", "required_local_surfaces",
                    "system_prerequisites"):
        for entry in manifest.get(section, []):
            ids.add(f"{section}:{entry['id']}")
    for name in manifest.get("required_env_vars", []):
        ids.add(f"required_env_vars:{name}")
    return ids


# A step ref whose manifest entry was renamed upstream: the renamed entry satisfies the old ref.
_MANIFEST_RENAMES = {"required_mcp_surfaces:notebooklm-mcp": "required_mcp_surfaces:gemini-notebook-mcp"}


# Manifest entries the installer deliberately no longer implements; the DoE manifest drops them later.
_DEPRECATED_MANIFEST_ENTRIES = frozenset({"required_local_surfaces:subagent-statusline-registration"})


def check_manifest_drift(manifest: dict | None = None, steps: tuple[Step, ...] = STEPS) -> list[str]:
    """Problems joining the manifest to the steps; empty means one source of truth holds."""
    manifest = _read_json(manifest_path()) if manifest is None else manifest
    entries = manifest_entry_ids(manifest)
    claimed: set[str] = set()
    problems: list[str] = []
    for step in steps:
        if not step.implements and not step.exempt:
            problems.append(f"step {step.id} implements no manifest entry and states no exemption")
        for ref in step.implements:
            if ref.endswith(":*"):
                matched = {e for e in entries if e.startswith(ref[:-1])}
                if not matched:
                    problems.append(f"step {step.id} claims {ref} but the manifest has no such entries")
                claimed |= matched
            elif ref in entries:
                claimed.add(ref)
            elif _MANIFEST_RENAMES.get(ref) in entries:
                claimed.add(_MANIFEST_RENAMES[ref])
            elif any(alt in entries for alt in ref.split("|")):
                # Trap: `a|b` names one surface under a renamed key (upstream renamed the NotebookLM
                # MCP key); the claim holds whichever spelling this manifest carries.
                claimed |= {alt for alt in ref.split("|") if alt in entries}
            else:
                problems.append(f"step {step.id} claims {ref}, absent from the manifest")
    for entry in sorted(entries - claimed - _DEPRECATED_MANIFEST_ENTRIES):
        problems.append(f"manifest entry {entry} has no implementing step")
    return problems


# --------------------------------------------------------------------------- plan / execute


_PLUGIN_KEY = "coordinator@"
_ENGINE_CHECK_TIMEOUT = 60


def _ver_tuple(v: object) -> tuple[int, ...] | None:
    try:
        return tuple(int(x) for x in str(v).strip().split("."))
    except ValueError:
        return None


def _entry_applies(e: dict, cwd: Path) -> bool:
    """A user-scope install, or a project-scope install whose projectPath contains cwd."""
    if e.get("scope") != "project":
        return True
    proj = e.get("projectPath")
    if not isinstance(proj, str):
        return False
    try:
        cwd.resolve().relative_to(Path(proj).resolve())
        return True
    except (ValueError, OSError):
        return False


def _installed_coordinator() -> tuple[bool, str | None, str | None]:
    """(present, installed version or None, marketplace name or None).

    The version is the OLDEST install that applies to this cwd (user scope plus any
    project scope containing cwd): the stalest copy the harness may load is what an
    update must reach. Never the highest across scopes -- a newer install for some
    other project says nothing about this one.
    """
    installed = _read_json(claude_dir() / "plugins" / "installed_plugins.json")
    plugins = installed.get("plugins")
    plugins = plugins if isinstance(plugins, dict) else installed
    cwd = Path.cwd()
    oldest, market, present = None, None, False
    for key, entries in plugins.items():
        if not (isinstance(key, str) and key.startswith(_PLUGIN_KEY)):
            continue
        present = True
        market = key.split("@", 1)[1]
        for e in entries if isinstance(entries, list) else []:
            if not (isinstance(e, dict) and _entry_applies(e, cwd)):
                continue
            t = _ver_tuple(e.get("version"))
            if t and (oldest is None or t < oldest):
                oldest = t
    return present, (".".join(map(str, oldest)) if oldest else None), market


def _published_version(market: str | None) -> str | None:
    root = claude_dir() / "plugins" / "marketplaces"
    cands = [root / market] if market else []
    cands += [d for d in (sorted(root.iterdir()) if root.is_dir() else []) if d not in cands]
    for d in cands:
        data = _read_json(d / ".claude-plugin" / "plugin.json")
        if data.get("name") == "coordinator" and _ver_tuple(data.get("version")):
            return str(data["version"])
    return None


def _engine_setup_script() -> tuple[Path | None, str]:
    ok, root = _engine_root()
    if not ok:
        return None, "engine root does not resolve"
    script = Path(root) / "scripts" / "setup.py"
    if not script.is_file():
        return None, f"{script} not found"
    return script, ""


def _engine_check() -> tuple[bool, str]:
    """Bounded, fail-safe `setup.py --check` against the located engine."""
    script, why = _engine_setup_script()
    if script is None:
        return False, why
    rc, out = run(_py(str(script), "--check"), timeout=_ENGINE_CHECK_TIMEOUT)
    if rc == 0:
        return True, "engine check passed"
    failed = failing_checks(out)
    if failed:
        return False, f"engine check failed: {'; '.join(failed)}"
    return False, f"engine check exited {rc}: {out[-200:]}"


def failing_checks(out: str) -> list[str]:
    """`FAIL [name] detail` lines of `setup.py --check`, each as `name: detail` (detail capped)."""
    found = []
    for line in out.splitlines():
        m = re.match(r"\s*FAIL \[([^\]]+)\]\s*(.*)", line)
        if m:
            detail = m.group(2).strip()
            found.append(f"{m.group(1)}: {detail[:100]}" if detail else m.group(1))
    return found


def _plugin_drift(market: str | None) -> tuple[list[str], list[str]]:
    """(version drift, stale cache dirs) for the coordinator plugin applicable to this cwd.

    Version drift: the clone an install entry points at (`installPath`) carries a plugin.json
    version that differs from the version the install record claims. Stale cache dirs: version
    directories under plugins/cache/<market>/coordinator that no applicable record names.
    """
    installed = _read_json(claude_dir() / "plugins" / "installed_plugins.json")
    plugins = installed.get("plugins")
    plugins = plugins if isinstance(plugins, dict) else installed
    cwd = Path.cwd()
    drift, recorded = [], set()
    for key, entries in plugins.items():
        if not (isinstance(key, str) and key.startswith(_PLUGIN_KEY)):
            continue
        for e in entries if isinstance(entries, list) else []:
            if not (isinstance(e, dict) and _entry_applies(e, cwd)):
                continue
            rec = str(e.get("version") or "")
            recorded.add(rec)
            ip = e.get("installPath")
            if not isinstance(ip, str):
                continue
            on_disk = _read_json(Path(ip) / ".claude-plugin" / "plugin.json")
            disk_v = on_disk.get("version")
            if on_disk.get("name") == "coordinator" and disk_v and str(disk_v) != rec:
                drift.append(f"install record says {rec or 'no version'} but {ip} is {disk_v}")
    stale: list[str] = []
    cache = claude_dir() / "plugins" / "cache" / (market or "coordinator-claude") / "coordinator"
    if cache.is_dir():
        stale = sorted(d.name for d in cache.iterdir() if d.is_dir() and d.name not in recorded)
    return drift, stale


def detect_track() -> dict:
    """Which path the install takes: fresh | update | repair.

    fresh  : no coordinator plugin installed and no DoE doctrine provisioned. A DoE box (the
             `.coordinator-plugin-root` breadcrumb names a live directory) with no plugin registry
             entry is update (engine healthy) or repair, never fresh, and takes no plugin step.
    update : installed and the published (marketplace plugin.json) version is newer, or the
             install record lags the clone it points at (plugin version drift); versions
             that cannot be read never count as newer.
    repair : installed, not known-newer, but the engine check fails (or the engine cannot be located).
             Version drift still adds plugin_update: repair never masks it.
    update (reason "already current"): installed, current and engine healthy; there is no fourth
             track value. Steps drop plugin_update but keep engine_setup + engine_check: every
             update carries the engine re-run, so the contract has one shape per track.
    `plugin_drift` / `stale_plugin_cache` are reported on every track; stale cache dirs are
    reported, never a step (a plugin update does not prune them).
    """
    configure = [s.id for s in STEPS]
    present, have, market = _installed_coordinator()
    drift: list[str] = []
    stale: list[str] = []
    doctrine = doctrine_root()
    doe_box = doe_tree_from_evidence() is not None
    if not present and doctrine is not None:
        ok, detail = _engine_check()
        track = "update" if ok else "repair"
        reason = (f"DoE box: doctrine provisioned at {doctrine} (no plugin registry entry); "
                  + ("already current" if ok else detail))
        steps = ["engine_setup", "engine_check", *configure]
    elif not present:
        track, reason, steps = "fresh", "no coordinator plugin installed", ["plugin_install", *configure]
        if doe_box:
            reason += "; DoE box: coordinator is delivered by the DoE checkout, so no plugin is registered by design"
    else:
        want = _published_version(market)
        drift, stale = _plugin_drift(market)
        update_steps = ["plugin_update", "engine_setup", "engine_check", *configure]
        if have and want and _ver_tuple(want) > _ver_tuple(have):
            track, reason = "update", f"published {want} is newer than installed {have}"
            steps = update_steps
        else:
            ok, detail = _engine_check()
            if not ok:
                track, reason = "repair", detail
                steps = update_steps if drift else ["engine_setup", "engine_check", *configure]
            elif drift:
                track, reason, steps = "update", "plugin version drift", update_steps
            else:
                track, reason = "update", "already current"
                steps = ["engine_setup", "engine_check", *configure]
        if drift:
            note = "plugin version drift: " + "; ".join(drift)
            reason = note if reason == "plugin version drift" else f"{reason}; {note}"
        if stale:
            reason += f"; stale plugin cache dirs: {', '.join(stale)}"
    return {"track": track, "track_reason": reason, "track_steps": steps,
            "doe_box": doe_box, "plugin_drift": drift, "stale_plugin_cache": stale}


def step_plugin_install(ctx: Ctx) -> StepResult:
    if doe_tree_from_evidence():
        return StepResult(INHERITED, "DoE box: the DoE checkout delivers coordinator, no plugin to install")
    return StepResult(SKIPPED, "plugin install is a harness action this script cannot perform",
                      "run: /plugin marketplace add dbc-oduffy/coordinator-claude, then /plugin install coordinator@coordinator-claude, then restart and re-run the install")


def step_plugin_update(ctx: Ctx) -> StepResult:
    if not shutil.which("claude"):
        return _fail("load", "claude CLI not on PATH", "run: /plugin update coordinator@coordinator-claude")
    _, _, market = _installed_coordinator()
    market = market or "coordinator-claude"
    rc, out = run(["claude", "plugin", "marketplace", "update", market], timeout=300)
    if rc != 0:
        return _fail_run("load", rc, out[-300:] or "marketplace update failed",
                         f"run: claude plugin marketplace update {market}")
    rc, out = run(["claude", "plugin", "update", f"coordinator@{market}"], timeout=300)
    if rc == 0:
        ctx.restart_needed = True
        return StepResult(RAN, out[-300:] or "updated")
    return _fail_run("load", rc, out[-300:] or "updated", "run: /plugin update coordinator@coordinator-claude")


def step_engine_setup(ctx: Ctx) -> StepResult:
    script, why = _engine_setup_script()
    if script is None:
        return _fail("load", why, "clone the engine as a sibling of this plugin clone and register it: machine-local set repos.claude_klabauter <path>")
    rc, out = run(_py(str(script)), timeout=600)
    detail = out.splitlines()[-1] if out else f"exited {rc}"
    return StepResult(RAN, detail) if rc == 0 else _fail_run("load", rc, detail)


def step_engine_check(ctx: Ctx) -> StepResult:
    ok, detail = _engine_check()
    if ok:
        return StepResult(RAN, detail)
    # "exited N" is the no-verdict path: the check crashed or timed out, so a retry can differ.
    return _fail("self-test", detail, retryable=detail.startswith("engine check exited"))


# Who runs each track step. A human step names the exact command the agent hands over; the agent
# never runs it itself (plugin_update reaches the harness's plugin store).
TRACK_STEP_RUNNERS = {
    "plugin_install": {"runner": "human", "handover": "/plugin marketplace add dbc-oduffy/coordinator-claude, then /plugin install coordinator@coordinator-claude"},
    "plugin_update": {"runner": "human", "handover": "/coordinator:install"},
    "grok_plugin_install": {"runner": "human", "handover": "grok plugin install <coordinator-claude clone> --trust"},
    "engine_setup": {"runner": "agent", "handover": None},
    "engine_check": {"runner": "agent", "handover": None},
}


_DOE_PLUGIN_INSTALL_RUNNER = {"runner": "agent", "handover": None}


def track_step_runners(steps: list[str], doe_box: bool = False) -> list[dict]:
    return [{"id": i, **(_DOE_PLUGIN_INSTALL_RUNNER if doe_box and i == "plugin_install" else TRACK_STEP_RUNNERS[i])}
            for i in steps if i in TRACK_STEP_RUNNERS]


TRACK_STEP_FNS = {"plugin_install": step_plugin_install, "plugin_update": step_plugin_update,
                  "engine_setup": step_engine_setup, "engine_check": step_engine_check}


def mode_policy(mode: str | None) -> dict:
    kind, note = _MODE_ADAPTATION.get(mode or "", ("extras_on", "Permission mode unknown: recommended defaults apply."))
    return {
        "permission_mode": mode,
        "extras": "presumed" if kind == "extras_on" else "asked",
        "note": note,
        "shift_tab_nudge": (mode in _NUDGE_MODES) if mode else False,
        "nudge_text": "Auto mode asks only about heavyweight actions; press shift-tab to switch. Said once."
        if mode in _NUDGE_MODES else None,
        "paths": {
            "express": "take every recommended default and run",
            "custom": "walk the decisions in order in plain language, one at a time",
        },
    }


PLAN_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _fresh_plan_id() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(3)


def _backup_covers() -> list[tuple[str, Path]]:
    """(backup-relative name, live path) for every file a step writes."""
    registry = Path(os.environ.get("MACHINE_LOCAL_REGISTRY_DIR") or settings_home() / "machine-local")
    return [("claude/settings.json", claude_dir() / "settings.json"),
            ("claude/CLAUDE.md", claude_dir() / "CLAUDE.md"),
            ("machine-local/registry.local.toml", registry / "registry.local.toml"),
            ("machine-local/registry.toml", registry / "registry.toml")]


def backup_block(plan_id: str) -> dict:
    return {"plan_id": plan_id, "path": str(settings_home() / "install-backups" / plan_id),
            "covers": [str(p) for _, p in _backup_covers()]}


def take_backup(plan_id: str) -> list[str]:
    """Copy each existing covered file under the backup path; a file already saved under this
    plan_id is kept, so a re-apply never overwrites the pre-install copy. Returns the names saved."""
    root = Path(backup_block(plan_id)["path"])
    saved = []
    for name, src in _backup_covers():
        dest = root / name
        if src.is_file() and not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            saved.append(name)
    return saved


# Must match the sentence inside TOUR's movement 2 verbatim; a mismatch makes the swap a silent no-op.
_OWNER_WRITE_SENTENCE = "Ask three things and write the answers into the CLAUDE.md Owner section: "
_DOE_OWNER_SENTENCE = ("Ask three things and note the answers in em-context.md, not CLAUDE.md "
                       "(on this box CLAUDE.md is derived from global doctrine and regenerated): ")


def tour() -> list[dict]:
    """TOUR, with movement 2 pointed away from the live CLAUDE.md on a DoE-derived box."""
    if not doe_tree_from_evidence():
        return list(TOUR)
    return [{**m, "text": m["text"].replace(_OWNER_WRITE_SENTENCE, _DOE_OWNER_SENTENCE)} for m in TOUR]


def answers_shape() -> dict:
    """The `--answers` document shape as `resolve_answers` accepts it."""
    risky = [s.id for s in STEPS if s.risky]
    return {
        "decision_ids": "one key per entry of `decisions`, valued as that decision's options allow",
        "consent": {"type": "object of booleans keyed by risky step id; absent or false skips the step",
                    "risky_step_ids": risky, "example": {sid: True for sid in risky}},
        "plan_id": "optional; the `backup.plan_id` of this plan, so the backup and the run share one id",
    }


HOSTS = ("claude", "grok")


def grok_plugin_registry() -> dict:
    """Is the coordinator plugin in Grok's own registry: `{"present": bool | None, "detail": str}`.

    One `grok plugin list` spawn; each output line prints a plugin id plus its local path; the
    plugin is a line whose id token (not its path) contains `coordinator`. `present` is None when the registry cannot be read.
    """
    exe = shutil.which("grok")
    if not exe:
        return {"present": None, "detail": "grok CLI not on PATH"}
    rc, out = run([exe, "plugin", "list"], timeout=30)
    if rc != 0:
        return {"present": None, "detail": f"grok plugin list exited {rc}: {out[-200:]}"}
    hit = next((ln.strip() for ln in out.splitlines() if "coordinator" in (ln.split() or [""])[0].lower()), None)
    return {"present": hit is not None, "detail": hit or "coordinator plugin not in grok plugin list"}


def build_plan(permission_mode: str | None, hosts: tuple[str, ...] = ("claude",)) -> dict:
    problems = check_manifest_drift() if manifest_found() else []
    root, source = plugin_root_source()
    if source.startswith("doctrine breadcrumb"):
        source = plugin_root_resolution()[1]
    env = {"platform": platform.system(), "plugin_root": str(root),
           "plugin_root_source": source, **detect_track()}
    if "grok" in hosts:
        grok = grok_plugin_registry()
        env["host_plugins"] = {"grok": grok}
        if grok["present"] is not True:
            env["track_steps"] = ["grok_plugin_install", *env["track_steps"]]
    return {
        "backup": backup_block(_fresh_plan_id()),
        "schema": SCHEMA,
        "orientation": ORIENTATION,
        "environment": env,
        "answers_shape": answers_shape(),
        "registry_hygiene": registry_hygiene_report(),
        "track_step_runners": track_step_runners(env["track_steps"], env["doe_box"]),
        "mode_policy": mode_policy(permission_mode),
        "decisions": [decision_json(d) for d in build_decisions(permission_mode)],
        "tour": tour(),
        "steps": [{"id": s.id, "decision": STEP_DECISION.get(s.id), "risky": s.risky,
                   "implements": list(s.implements) or [f"exempt: {s.exempt}"]} for s in STEPS],
        "manifest_drift": ({"ok": not problems, "problems": problems} if manifest_found() else
                           {"ok": None, "problems": [], "note": f"no install manifest under {root}; drift not checked"}),
    }


def _plugin_version() -> str | None:
    version = _read_json(plugin_root() / ".claude-plugin" / "plugin.json").get("version")
    return version if isinstance(version, str) else None


def record_concluded(results: list[dict], optional_ids: set[str], ctx: Ctx) -> dict:
    """Stamp the setup_concluded receipt unless a required step FAILED; returns `{written, detail}`.

    A SKIPPED required step does not withhold it (maximalist's mandatory-skip gate has no analogue here).

    The one place this installer imports coordinator_core: after every step has run, from the engine root.
    """
    blocking = [r["id"] for r in results if r["status"] in (FAILED, BLOCKED) and r["id"] not in optional_ids]
    if blocking:
        return record_withheld(f"required step failed or blocked ({', '.join(blocking)})", tuple(blocking), ctx)
    root = ctx.engine_root
    if not root:
        ok, found = _engine_root()
        root = found if ok else ""
    if not root:
        return record_withheld("engine root does not resolve", (), ctx)
    inserted = root not in sys.path
    if inserted:
        sys.path.insert(0, root)
    try:
        import importlib
        state = importlib.import_module("coordinator_core.ops.coordinator_setup_state")
        rc, sha = run(["git", "-C", root, "rev-parse", "HEAD"], timeout=10)
        receipt = state.SetupReceipt(
            phases_ran=tuple(r["id"] for r in results if r["status"] in (RAN, INHERITED)),
            phases_skipped=tuple((r["id"], r["detail"]) for r in results if r["status"] == SKIPPED),
            coordinator_version=_plugin_version(),
            engine_ref=sha if rc == 0 and sha else None,
        )
        with contextlib.redirect_stdout(sys.stderr):  # the writer prints a status line; stdout is the JSON block
            rc = state.record_setup_concluded(receipt)
    except Exception as exc:  # the receipt must never abort the install block
        return {"written": False, "detail": f"write failed: {type(exc).__name__}: {exc}"}
    finally:
        if inserted and root in sys.path:
            sys.path.remove(root)
    return {"written": rc == 0, "detail": "setup_concluded recorded" if rc == 0 else f"write failed (exit {rc})"}


def record_withheld(reason: str, blocking: tuple, ctx: Ctx) -> dict:
    """Persist a withheld run through the setup-state writer; returns `{written: False, detail}`.

    `written` stays False: no concluded receipt exists. `recorded` says whether the withheld
    record landed. Never raises; an unresolvable engine root leaves nothing recorded.
    """
    detail = f"withheld: {reason}"
    root = ctx.engine_root
    if not root:
        ok, found = _engine_root()
        root = found if ok else ""
    if not root:
        return {"written": False, "recorded": False, "detail": f"{detail}; withheld record not written (engine root does not resolve)"}
    inserted = root not in sys.path
    if inserted:
        sys.path.insert(0, root)
    try:
        import importlib
        state = importlib.import_module("coordinator_core.ops.coordinator_setup_state")
        with contextlib.redirect_stdout(sys.stderr):
            rc = state.record_setup_withheld(reason, tuple(blocking))
    except Exception as exc:  # recording must never abort the install block
        return {"written": False, "recorded": False, "detail": f"{detail}; withheld record failed: {type(exc).__name__}: {exc}"}
    finally:
        if inserted and root in sys.path:
            sys.path.remove(root)
    return {"written": False, "recorded": rc == 0, "detail": detail if rc == 0 else f"{detail}; withheld record failed (exit {rc})"}


#: The command the closing NEXT line names; the same command scripts/setup.py closes with.
UNIMATRIX_INSTALL_COMMAND = "python3 coordinator/bin/unimatrix-install.py --install"


def execute(answers: dict, only: set[str] | None = None, permission_mode: str | None = None) -> dict:
    ctx = Ctx(answers=answers, permission_mode=permission_mode)
    results = []
    steps: list = [Step(i, TRACK_STEP_FNS[i], exempt="track step")
                   for i in detect_track()["track_steps"] if i in TRACK_STEP_FNS]
    steps += STEPS
    plan_id = answers.get("plan_id") or _fresh_plan_id()
    backup = backup_block(plan_id)
    try:
        backup["saved"] = take_backup(plan_id)
    except OSError as exc:
        backup["saved"] = []
        results.append({"id": "backup", "status": FAILED, "detail": f"{type(exc).__name__}: {exc}",
                        "follow_up": "no step ran; fix the backup path and re-run", "stage": "host",
                        "retryable": False})
        steps = []
    consent = answers.get("consent") or {}
    for step in steps:
        if only and step.id not in only:
            continue
        declined = answers.get(STEP_DECISION.get(step.id, "")) == "skip"
        try:
            probe = _INHERITED_PROBES.get(step.id)
            if step.risky and not declined and consent.get(step.id) is not True and not (probe and probe()):
                res = StepResult(SKIPPED, "consent required", f"re-run with consent.{step.id}=true")
            else:
                res = step.fn(ctx)
        except Exception as exc:  # a step must never abort the block
            res = _fail("inspection", f"{type(exc).__name__}: {exc}")
        row = {"id": step.id, "status": res.status, "detail": res.detail, "follow_up": res.follow_up}
        if res.status in (FAILED, BLOCKED):
            row.update(stage=res.stage, retryable=res.retryable)
        results.append(row)
    counts = {k: sum(1 for r in results if r["status"] == k) for k in (RAN, SKIPPED, INHERITED, FAILED, BLOCKED)}
    receipt = (record_concluded(results, {s.id for s in steps if s.optional}, ctx) if not only
               else record_withheld("--only run", tuple(sorted(only)), ctx))
    return {
        "schema": "coordinator-install-result/1",
        "backup": backup,
        "steps": results,
        "summary": counts,
        "receipt": receipt,
        "tour": tour() if answers.get("orientation") == "tour-now" else [],
        "added_extras": [f"{e}: added; say the word to remove" for e in ctx.extras],
        "restart_needed": ctx.restart_needed,
        "next_session": ctx.next_session,
        "follow_ups": [r["follow_up"] for r in results if r["follow_up"]],
        "unimatrix_next": UNIMATRIX_INSTALL_COMMAND,
    }


def render_text(block: dict) -> str:
    lines = [f"{r['status']:<9} {r['id']:<22} {r['detail']}" for r in block["steps"]]
    receipt = block.get("receipt")
    if receipt:
        lines.append(f"{'RECEIPT':<9} {'setup_concluded':<22} {receipt['detail']}")
    lines += [f"ADDED     {e}" for e in block["added_extras"]]
    lines += [f"NEXT      {f}" for f in block["follow_ups"]]
    if block.get("unimatrix_next"):
        lines.append(f"NEXT      (optional) {block['unimatrix_next']}")
    for t in block.get("tour", []):
        lines.append(f"TOUR {t['movement']}   {t['title']}: {t['text']}")
    lines.append("restart needed: " + ("yes" if block["restart_needed"] else "no"))
    return "\n".join(lines)


def _ask(prompt: str, stdin, stdout) -> str | None:
    """One line from `stdin`, or None at end of input."""
    stdout.write(prompt)
    stdout.flush()
    line = stdin.readline()
    return None if line == "" else line.strip()


def _describe_option(did: str, option: str) -> tuple[str, str]:
    """(value, label) for an option; posture options carry their value before the colon."""
    if did == "posture":
        value, _, label = option.partition(": ")
        return value, f"{value}: {label}"
    return option, option


def _identity_posture() -> str | None:
    """The `engagement_posture` an earlier install recorded in the identity file; offered, never applied."""
    try:
        text = (claude_dir() / "coordinator-identity.yaml").read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"^engagement_posture:\s*['\"]?([\w-]+)", text, re.MULTILINE)
    return m.group(1) if m and m.group(1) in POSTURE_OPTIONS else None


def _ask_decision(d: Decision, stdin, stdout, default: object, refuse_eof: bool = False) -> object | None:
    """Ask one decision; the answer, or None to keep `default`. SystemExit at end of input with no
    default, or whenever `refuse_eof` (an end of input is no answer from the human)."""
    free_text = list(d.options) == ["<free text>"]
    stdout.write(f"\n{d.question}\n{d.why}\n")
    choices = [_describe_option(d.id, o) for o in d.options] if not free_text else []
    for i, (_, label) in enumerate(choices, 1):
        stdout.write(f"  {i}. {label}\n")
    default_hint = f" [{default}]" if default is not None else ""
    while True:
        reply = _ask(f"> {'number or name' if choices else 'answer'}{default_hint}: ", stdin, stdout)
        if reply is None or (reply == "" and default is not None):
            if default is None or (reply is None and refuse_eof):
                raise SystemExit(f"no answer for required question ({d.id}): {d.question}")
            return None
        if free_text:
            if reply:
                return reply
            continue
        values = [v for v, _ in choices]
        picked = values[int(reply) - 1] if reply.isdigit() and 0 < int(reply) <= len(values) else reply
        if picked in values:
            return picked
        stdout.write(f"  choose one of: {', '.join(values)}\n")


def ask_extras(permission_mode: str | None, stdin, stdout) -> tuple[dict, dict]:
    """The one numbered optional-extras questionnaire: (answers, consent).

    Each item prints what `n` leaves out; a probe-INHERITED item asks nothing. An accepted
    (answered or defaulted yes) item granting a risky step is that step's consent.
    """
    defaults = {d.id: d.default for d in build_decisions(permission_mode)}
    items = [e for e in OPTIONAL_EXTRAS if e.id in defaults]
    stdout.write(f"\nOptional extras: {len(items)} questions. Enter takes the default shown; `n` skips the item.\n")
    answers: dict = {}
    consent: dict = {}
    for n, e in enumerate(items, 1):
        stdout.write(f"\n{n}. {e.prompt}\n   n leaves out: {e.leaves_out}\n")
        probe = _INHERITED_PROBES.get(e.step)
        if probe and (detail := probe()):
            stdout.write(f"   already in place ({detail}); not asked\n")
            answers[e.id] = e.accept
            continue
        yes_by_default = defaults[e.id] == e.accept
        while True:
            reply = (_ask(f"> [{'Y/n' if yes_by_default else 'y/N'}]: ", stdin, stdout) or "").lower()
            if reply in ("", "y", "yes", "n", "no"):
                break
            stdout.write("  answer y or n\n")
        accepted = yes_by_default if reply == "" else reply in ("y", "yes")
        answers[e.id] = e.accept if accepted else e.decline
        if accepted and e.step:
            consent[e.step] = True
    return answers, consent


def walk_decisions(permission_mode: str | None, stdin, stdout, custom: bool) -> dict:
    """Ask on `stdin` in plain language: posture first, then the questions with no default
    (express) or every other decision (custom), then the extras questionnaire."""
    stdout.write(ORIENTATION + "\n\n")
    raw: dict = {}
    extra_ids = {e.id for e in OPTIONAL_EXTRAS}
    decisions = build_decisions(permission_mode)
    posture = next(d for d in decisions if d.id == "posture")
    offered = _identity_posture()
    raw["posture"] = _ask_decision(posture, stdin, stdout, offered, refuse_eof=True) or offered
    for d in decisions:
        if d.id == "posture" or d.id in extra_ids:
            continue
        free_text = list(d.options) == ["<free text>"]
        if not custom and (d.default is not None or not free_text):
            continue
        picked = _ask_decision(d, stdin, stdout, d.default)
        if picked is not None:
            raw[d.id] = picked
    extra_answers, consent = ask_extras(permission_mode, stdin, stdout)
    raw.update(extra_answers)
    if consent:
        raw["consent"] = consent
    return raw


def _stdin_can_answer() -> bool:
    """A TTY can answer a prompt; a pipe, redirect or erroring `isatty` cannot."""
    try:
        return bool(sys.stdin is not None and sys.stdin.isatty())
    except (AttributeError, ValueError, OSError):
        return False


def _load_answers(spec: str | None) -> dict:
    if not spec:
        return {}
    text = spec.strip()
    if not text.startswith("{"):
        text = Path(spec).read_text(encoding="utf-8")
    obj = json.loads(text)
    if not isinstance(obj, dict):
        raise ValueError("answers must be a JSON object keyed by decision id")
    return obj


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="coordinator-install", description=__doc__.splitlines()[0])
    ap.add_argument("--plan", action="store_true", help="print every decision as JSON; mutate nothing")
    ap.add_argument("--answers", help="answers JSON file path or inline object")
    ap.add_argument("--non-interactive", action="store_true", help="use declared defaults")
    ap.add_argument("--i-am-agent", action="store_true", help="emit the full plan for the agent to answer")
    ap.add_argument("--express", action="store_true",
                    help="human path (the default on a terminal): posture, then what has no default, then the extras questionnaire")
    ap.add_argument("--custom", action="store_true",
                    help="human path: walk the decisions one at a time on stdin")
    ap.add_argument("--check-drift", action="store_true", help="fail when manifest and steps disagree")
    ap.add_argument("--only", help="comma-separated step ids to run")
    ap.add_argument("--permission-mode", default=os.environ.get("COORDINATOR_PERMISSION_MODE"),
                    help="harness permission_mode from hook input; adapts defaults")
    ap.add_argument("--format", choices=("json", "text"), default="json")
    ap.add_argument("--engine-root", help="engine checkout to register as repos.claude_klabauter (cold box)")
    ap.add_argument("--engine-target", choices=ENGINE_TARGETS, help="engine channel to register as engine.target")
    ap.add_argument("--host", action="append", choices=HOSTS,
                    help="host whose own plugin registry the plan probes (repeatable; claude is always probed)")
    args = ap.parse_args(argv)

    if args.engine_root or args.engine_target:
        if args.plan or args.check_drift:
            ap.error("--engine-root/--engine-target write the registry; not with --plan or --check-drift")
        try:
            written = register_engine(args.engine_root, args.engine_target)
        except (OSError, ValueError, ImportError) as exc:
            print(json.dumps({"error": f"engine registration failed: {exc}"}), file=sys.stderr)
            return 2
        print("registered " + ", ".join(written), file=sys.stderr)
    default_plugin_root_env()

    if args.check_drift:
        problems = check_manifest_drift()
        for p in problems:
            print(f"DRIFT: {p}", file=sys.stderr)
        return 1 if problems else 0

    planning = args.plan or (args.i_am_agent and not args.answers)
    if planning:
        plan = build_plan(args.permission_mode, tuple(dict.fromkeys(["claude", *(args.host or [])])))
        print(json.dumps(plan, indent=2))
        return 0
    drift = check_manifest_drift() if manifest_found() and not planning else []
    if drift:
        root, source = plugin_root_source()
        print(json.dumps({"error": "manifest/step drift", "plugin_root": str(root),
                          "plugin_root_source": source, "problems": drift}, indent=2), file=sys.stderr)
        return 3
    if args.express and args.custom:
        ap.error("--express and --custom are alternatives")
    if not (args.answers or args.non_interactive or args.express or args.custom) and _stdin_can_answer():
        args.express = True
    if not (args.answers or args.non_interactive or args.express or args.custom):
        ap.error("pass --plan, --express, --custom, --answers <file|json>, --non-interactive, or --i-am-agent")
    if (args.express or args.custom) and not _stdin_can_answer():
        print(json.dumps({"error": "stdin is not a terminal; pass --answers <file|json> or --non-interactive"}),
              file=sys.stderr)
        return 2
    try:
        if args.express or args.custom:
            raw = walk_decisions(args.permission_mode, sys.stdin, sys.stdout, custom=args.custom)
            args.format = "text"
        else:
            raw = _load_answers(args.answers)
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": f"bad answers: {exc}"}), file=sys.stderr)
        return 2
    answers, problems = resolve_answers(raw, args.permission_mode, args.non_interactive)
    if problems:
        print(json.dumps({"error": "invalid answers", "problems": problems}, indent=2), file=sys.stderr)
        return 2
    only = set(args.only.split(",")) if args.only else None
    block = execute(answers, only, args.permission_mode)
    print(render_text(block) if args.format == "text" else json.dumps(block, indent=2))
    return 1 if block["summary"][FAILED] or block["summary"][BLOCKED] else 0


if __name__ == "__main__":
    sys.exit(main())
