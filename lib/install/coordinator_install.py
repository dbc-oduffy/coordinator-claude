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

Never imports coordinator_core: the installer runs before an engine is importable, so
its git calls stay on its own bounded `subprocess.run`.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

SCHEMA = "coordinator-install-plan/1"
RAN, SKIPPED, INHERITED, FAILED = "RAN", "SKIPPED", "INHERITED", "FAILED"

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
    "You are installing a collaboration contract, not software. You are the PM: product authority "
    "-- what to build, ship, cut. The EM (Claude) is the engineering manager: how to build it, when "
    "to dispatch, how to review. The EM acts on engineering calls without hand-holding and pushes "
    "back when it disagrees with you. Non-trivial work flows plan, enrich, review, execute, review "
    "rather than straight to code; reviewer personas are available at the cost of minutes; "
    "/workstream-start and /workstream-complete bracket a working session. You do not need to learn "
    "the machinery: brief the EM in plain language and it picks the agents. The posture question "
    "below sets how closely the EM consults you."
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

STATUS_LINE_CMD = (
    'S="$(cat "$HOME/.claude/.coordinator-plugin-root" 2>/dev/null)/bin/{script}"; '
    'python3 "$S" || python "$S"'
)


def _is_coordinator_status_line(command: str) -> bool:
    """A statusLine command that already runs a coordinator statusline: the breadcrumb form, or
    an older install's plugin-cache glob (`…/coordinator-claude/coordinator/*/bin/statusline.py`).
    Either is replaced in place; relocating one into statusline-inner.json would make the
    statusline delegate to a stale cache copy of itself."""
    normalized = command.replace("\\", "/")
    return ".coordinator-plugin-root" in normalized or (
        "coordinator" in normalized and "/bin/statusline.py" in normalized)


CONTEXT7_PLUGIN = "context7@claude-plugins-official"
CONTEXT7_MARKETPLACE = "anthropics/claude-plugins-official"
NOTEBOOKLM_NAMES = ("notebooklm-mcp", "Gemini Notebook MCP")

_MODE_ADAPTATION = {
    "auto": ("extras_on", "Presume the recommended extras and list them at the end as added."),
    "bypass": ("extras_on", "Presume the recommended extras; no mode-switch nudge."),
    "bypassPermissions": ("extras_on", "Presume the recommended extras; no mode-switch nudge."),
    "plan": ("extras_on", "Present the whole plan once, then execute without further prompts."),
    "acceptEdits": ("extras_off", "Ask per change; do not pre-install extras."),
    "default": ("extras_off", "Ask per change; do not pre-install extras."),
}
_NUDGE_MODES = {"plan", "acceptEdits", "default"}


def plugin_root() -> Path:
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    return Path(env) if env else Path(__file__).resolve().parents[2]


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


def run(argv: list[str], timeout: int = 300) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, creationflags=_no_console(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, f"{type(exc).__name__}: {exc}"
    return proc.returncode, (proc.stdout + proc.stderr).strip()


# --------------------------------------------------------------------------- decisions


@dataclass(frozen=True)
class Decision:
    id: str
    question: str
    why: str
    options: tuple
    default: object
    level: str  # required | recommended | optional


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
    return machine_profile()


def default_guard_level(profile: str) -> str:
    return "strict" if profile == "author" else "warn"


def _git_user() -> str:
    rc, out = run(["git", "config", "user.name"], timeout=10)
    return out.strip() if rc == 0 else ""


def build_decisions(permission_mode: str | None = None) -> list[Decision]:
    profile = detect_profile()
    extras_on = _MODE_ADAPTATION.get(permission_mode or "", ("extras_on", ""))[0] == "extras_on"
    extra_default = "install" if extras_on else "skip"
    return [
        Decision(
            "track_claude_home",
            "Git-track ~/.claude so your configuration is versioned and backed up?",
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
            "posture", POSTURE_QUESTION, POSTURE_WHY,
            tuple(f"{k}: {v}" for k, v in POSTURE_OPTIONS.items()), "default", "required",
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
            "strict denies; warn allows with a one-line advisory (cross-repo writes warn once per session); off is silent. Destructive-action guards stay hard. Change later: machine-local set coordinator.guard_level <level>.",
            ("strict", "warn", "off"), default_guard_level(profile), "recommended",
        ),
        Decision(
            "context7",
            "Install the Context7 plugin (live library documentation for agents)?",
            "Agents that verify API claims (docs-checker, executor, staff reviewers) guess without it. Registers the claude-plugins-official marketplace itself.",
            ("install", "skip"), extra_default, "recommended",
        ),
        Decision(
            "notebooklm",
            "Install NotebookLM (deep-research Pipeline D)?",
            "Powers deep research; pipelines A-C work without it. Needs a Google account and a one-time browser login.",
            ("install", "skip"), extra_default, "recommended",
        ),
        Decision(
            "status_lines",
            "Wire the coordinator status line and subagent status line?",
            "The main line is the only producer of the context-window sidecar the context-pressure advisory reads; subagent rows show model, effort and distance to compaction.",
            ("wire", "skip"), "wire", "recommended",
        ),
        Decision(
            "settings_env",
            "Apply the required settings.json env values?",
            "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS and CLAUDE_CODE_ENABLE_TODO_TOOLS gate Agent Teams, research pipelines and Task tools. Lands next session.",
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
            "open_claude_home",
            "Open ~/.claude in your file manager?",
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
    problems = [f"unknown decision id: {k}" for k in raw if k not in decisions]
    answers: dict = {}
    profile = raw.get("machine_profile") or decisions["machine_profile"].default
    for did, d in decisions.items():
        if did in raw:
            value = raw[did]
        elif did == "guard_level":
            value = default_guard_level(profile)
        else:
            value = d.default
        if value is None:
            if d.level == "required":
                problems.append(f"required decision has no answer and no default: {did}")
            continue
        allowed = [o.split(":")[0] for o in d.options] if did == "posture" else list(d.options)
        if allowed != ["<free text>"] and value not in allowed:
            problems.append(f"{did}: {value!r} not one of {allowed}")
        answers[did] = value
    return answers, problems


# --------------------------------------------------------------------------- steps


@dataclass
class StepResult:
    status: str
    detail: str = ""
    follow_up: str = ""


@dataclass
class Ctx:
    answers: dict
    permission_mode: str | None = None
    extras: list = field(default_factory=list)
    restart_needed: bool = False
    next_session: list = field(default_factory=list)


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
        return StepResult(FAILED, "machine-local forwarder absent (run the substrate step first)")
    try:
        from coordinator_core.machine_resolver import registry_get
        current = registry_get(key)
    except Exception:  # an engine not yet importable reads as unset; the set below decides
        current = None
    if current == value:
        return StepResult(INHERITED, f"{key} already {value}")
    rc, out = run([fwd, "set", key, value], timeout=30)
    return StepResult(RAN if rc == 0 else FAILED, f"{key}={value}" if rc == 0 else out)


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
    return StepResult(FAILED if hard else RAN, detail,
                      "install the missing tools; remediation text is in the manifest" if missing else "")


def step_engine_root(ctx: Ctx) -> StepResult:
    ok, root = _engine_root()
    if ok:
        return StepResult(INHERITED, f"engine root {root}")
    return StepResult(FAILED, "engine root does not resolve",
                      "clone the engine as a sibling of this plugin clone and register it: machine-local set repos.claude_klabauter <path>")


def step_substrate(ctx: Ctx) -> StepResult:
    ok, engine = _engine_root()
    if not ok:
        return StepResult(FAILED, "engine root does not resolve; substrate not deposited")
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin_root()))
    notes = []
    for name in ("install-substrate.py", "register-coordinator-mirror.py", "check-install-singularity.py"):
        script = Path(engine) / "coordinator" / "lib" / name
        if not script.is_file():
            return StepResult(FAILED, f"{script} not found")
        try:
            proc = subprocess.run(_py(str(script)), capture_output=True, text=True,
                                  timeout=600, env=env, creationflags=_no_console())
        except (OSError, subprocess.TimeoutExpired) as exc:
            return StepResult(FAILED, f"{name}: {exc}")
        if proc.returncode != 0:
            return StepResult(FAILED, f"{name} exited {proc.returncode}: {(proc.stdout + proc.stderr).strip()[-300:]}")
        notes.append(name)
    return StepResult(RAN, "ran " + ", ".join(notes))


def step_claude_home_repo(ctx: Ctx) -> StepResult:
    home = claude_dir()
    if any((p / ".git").exists() for p in (home, *home.parents)):
        return StepResult(INHERITED, f"{home} sits inside a git repository")
    if ctx.answers["track_claude_home"] == "skip":
        return StepResult(SKIPPED, "declined by answer", "the identity file needs a git repository at ~/.claude")
    home.mkdir(parents=True, exist_ok=True)
    rc, out = run(["git", "-C", str(home), "init"], timeout=60)
    if rc != 0:
        return StepResult(FAILED, out)
    drift = plugin_root() / "bin" / "check-gitignore-template-drift.py"
    if drift.is_file():
        run(_py(str(drift), "--apply"), timeout=60)
    return StepResult(RAN, f"git init {home}; no remote created, nothing pushed")


def step_posture(ctx: Ctx) -> StepResult:
    fwd = forwarder("write-identity-file")
    if not fwd:
        return StepResult(FAILED, "write-identity-file forwarder absent (run the substrate step first)")
    home = os.environ.get("CLAUDE_HOME") or str(Path.home())
    argv = [fwd, "--claude-home", home, "--operator-name", str(ctx.answers["operator_name"]),
            "--engagement-posture", str(ctx.answers["posture"])]
    rc, out = run(argv, timeout=60)
    return StepResult(RAN if rc == 0 else FAILED, f"posture={ctx.answers['posture']}" if rc == 0 else out)


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


def step_claude_md_seed(ctx: Ctx) -> StepResult:
    fwd = forwarder("render-template")
    if not fwd:
        return StepResult(FAILED, "render-template forwarder absent (run the substrate step first)")
    tmpl = plugin_root() / "templates" / "CLAUDE.md.tmpl"
    values = claude_md_values(ctx.answers, ctx.permission_mode)
    missing = [p for p in unresolved_placeholders(tmpl.read_text(encoding="utf-8"))
               if p.strip("{}") not in values]
    if missing:
        return StepResult(FAILED, f"template placeholders with no value: {missing}")
    out = claude_dir() / "CLAUDE.md"
    argv = [fwd, str(tmpl), "-o", str(out), "--guard-sentinel", "coordinator:claude-md-seed:v1"]
    argv += [f"{k}={v}" for k, v in values.items()]
    rc, msg = run(argv, timeout=60)
    if rc == 3:
        return StepResult(INHERITED, "hand-authored CLAUDE.md preserved")
    if rc != 0:
        return StepResult(FAILED, msg)
    left = unresolved_placeholders(out.read_text(encoding="utf-8"))
    return StepResult(FAILED, f"unresolved placeholders survive: {left}") if left else \
        StepResult(RAN, "seeded CLAUDE.md from your answers")


def step_machine_profile(ctx: Ctx) -> StepResult:
    return _machine_local_set("coordinator.machine_profile", ctx.answers["machine_profile"])


def step_guard_level(ctx: Ctx) -> StepResult:
    return _machine_local_set("coordinator.guard_level", ctx.answers["guard_level"])


def _plugin_enabled(name: str) -> bool:
    return bool(_read_json(claude_dir() / "settings.json").get("enabledPlugins", {}).get(name))


def step_context7(ctx: Ctx) -> StepResult:
    if ctx.answers["context7"] == "skip":
        return StepResult(SKIPPED, "declined by answer")
    if _plugin_enabled(CONTEXT7_PLUGIN):
        return StepResult(INHERITED, "context7 already enabled")
    claude = shutil.which("claude")
    if not claude:
        return StepResult(FAILED, "claude CLI not on PATH")
    rc, out = run([claude, "plugin", "marketplace", "add", CONTEXT7_MARKETPLACE], timeout=180)
    if rc != 0 and "already" not in out.lower():
        return StepResult(FAILED, f"marketplace add failed: {out}")
    rc, out = run([claude, "plugin", "install", CONTEXT7_PLUGIN], timeout=180)
    if rc != 0:
        return StepResult(FAILED, out)
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
    uv, nlm = shutil.which("uv"), shutil.which("nlm")
    if not nlm:
        if not uv:
            return StepResult(FAILED, "uv not on PATH", "install uv, then re-run with notebooklm=install")
        rc, out = run([uv, "tool", "install", "notebooklm-mcp-cli"], timeout=300)
        if rc != 0:
            return StepResult(FAILED, out)
        nlm = shutil.which("nlm")
    if not nlm:
        return StepResult(FAILED, "nlm not on PATH after install (open a new shell)")
    rc, out = run([nlm, "setup", "add", "claude-code"], timeout=120)
    if rc != 0:
        return StepResult(FAILED, out)
    ctx.extras.append("notebooklm")
    ctx.next_session.append("NotebookLM loads next session")
    return StepResult(RAN, "CLI installed and MCP server registered",
                      "run `nlm login` once in a terminal (browser flow) before first use")


def step_status_lines(ctx: Ctx) -> StepResult:
    if ctx.answers["status_lines"] == "skip":
        return StepResult(SKIPPED, "declined by answer")
    path = claude_dir() / "settings.json"
    doc = _read_json_strict(path)
    if doc is None:
        return StepResult(FAILED, f"{path} exists but is not a readable JSON object; left untouched",
                          "fix or remove the file, then re-run")
    wanted = {
        "statusLine": {"type": "command", "command": STATUS_LINE_CMD.format(script="statusline.py")},
        "subagentStatusLine": {"type": "command",
                               "command": STATUS_LINE_CMD.format(script="subagent-statusline.py")},
    }
    changed = []
    for key, value in wanted.items():
        current = doc.get(key)
        if current == value:
            continue
        if key == "statusLine" and isinstance(current, dict) and current.get("command") \
                and not _is_coordinator_status_line(str(current["command"])):
            inner = settings_home() / "statusline-inner.json"
            if not inner.exists():
                _write_json(inner, current)
        doc[key] = value
        changed.append(key)
    if not changed:
        return StepResult(INHERITED, "statusLine and subagentStatusLine already wired")
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
        return StepResult(FAILED, f"{settings} is not a readable JSON object; left untouched",
                          "fix or remove the file, then re-run")
    rc_c, out_c = run(_py(str(plugin_root() / "lib" / "compaction_defaults.py"),
                       "--apply", str(settings)), timeout=60)
    if rc_c != 0:
        return StepResult(FAILED, out_c.strip() or "compaction_defaults --apply failed")
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
    return StepResult(RAN if rc == 0 else FAILED, out.splitlines()[-1] if out else "")


def step_hooks_marker(ctx: Ctx) -> StepResult:
    choice = ctx.answers["hooks_marker"]
    if choice == "skip":
        return StepResult(SKIPPED, "declined by answer")
    fwd = forwarder("gen-settings-hooks")
    if not fwd:
        return StepResult(FAILED, "gen-settings-hooks forwarder absent (run the substrate step first)")
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
    return StepResult(RAN if rc == 0 else FAILED, out.splitlines()[-1] if out else "")


def step_currency(ctx: Ctx) -> StepResult:
    if ctx.answers["coordinator_currency"] == "skip":
        return StepResult(SKIPPED, "declined by answer")
    ok, engine = _engine_root()
    script = Path(engine) / "coordinator" / "lib" / "coordinator_currency.py" if ok else None
    if not script or not script.is_file():
        return StepResult(FAILED, "coordinator_currency.py not found under the engine root")
    rc, out = run(_py(str(script), "write", str(Path.cwd()), str(plugin_root())))
    return StepResult(RAN if rc == 0 else FAILED, "wrote docs/coordinator-currency.yaml" if rc == 0 else out)


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
        return StepResult(FAILED, str(exc), f"browse to {target}")
    return StepResult(RAN, f"opened {target}")


@dataclass(frozen=True)
class Step:
    id: str
    fn: Callable[[Ctx], StepResult]
    implements: tuple = ()
    exempt: str = ""  # reason this step implements no manifest entry


STEPS: tuple[Step, ...] = (
    Step("orientation", step_orientation, exempt="operator choice: the tour is not an install surface"),
    Step("system_prereqs", step_system_prereqs, ("system_prerequisites:*",)),
    Step("engine_root", step_engine_root, ("direct_deps:claude-klabauter",)),
    Step("substrate", step_substrate, exempt="deposits the settings-home forwarders every later step calls"),
    Step("settings_env", step_settings_env, ("required_local_surfaces:settings-env", "required_env_vars:*")),
    Step("claude_home_repo", step_claude_home_repo, exempt="prerequisite of the identity file"),
    Step("posture", step_posture, exempt="operator choice: recorded in the identity file"),
    Step("claude_md_seed", step_claude_md_seed, exempt="operator file seeded from answers"),
    Step("machine_profile", step_machine_profile, exempt="operator choice: machine-local setting"),
    Step("guard_level", step_guard_level, exempt="operator choice: machine-local setting"),
    Step("context7", step_context7, ("required_mcp_surfaces:context7",)),
    Step("notebooklm", step_notebooklm, ("required_mcp_surfaces:notebooklm-mcp",)),
    Step("status_lines", step_status_lines,
         ("required_local_surfaces:statusline-registration",
          "required_local_surfaces:subagent-statusline-registration")),
    Step("hooks_marker", step_hooks_marker, ("required_local_surfaces:hook-delivery",)),
    Step("coordinator_currency", step_currency, exempt="per-repo record, not a machine install surface"),
    Step("open_claude_home", step_open_claude_home, exempt="presentation only"),
)

STEP_DECISION = {"orientation": "orientation", "claude_md_seed": "posture", "claude_home_repo": "track_claude_home", "settings_env": "settings_env", "posture": "posture",
                 "machine_profile": "machine_profile", "guard_level": "guard_level",
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
            else:
                problems.append(f"step {step.id} claims {ref}, absent from the manifest")
    for entry in sorted(entries - claimed):
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
    return rc == 0, (f"engine check exited {rc}: {out[-200:]}" if rc else "engine check passed")


def detect_track() -> dict:
    """Which path the install takes: fresh | update | repair.

    fresh  : no coordinator plugin installed.
    update : installed and the published (marketplace plugin.json) version is newer; versions
             that cannot be read never count as newer.
    repair : installed, not known-newer, but the engine check fails (or the engine cannot be located).
    update (reason "already current"): installed, current and engine healthy; there is no fourth
             track value. Steps drop plugin_update but keep engine_setup + engine_check: every
             update carries the engine re-run, so the contract has one shape per track.
    """
    configure = [s.id for s in STEPS]
    present, have, market = _installed_coordinator()
    if not present:
        track, reason, steps = "fresh", "no coordinator plugin installed", ["plugin_install", *configure]
    else:
        want = _published_version(market)
        if have and want and _ver_tuple(want) > _ver_tuple(have):
            track, reason = "update", f"published {want} is newer than installed {have}"
            steps = ["plugin_update", "engine_setup", "engine_check", *configure]
        else:
            ok, detail = _engine_check()
            if not ok:
                track, reason = "repair", detail
                steps = ["engine_setup", "engine_check", *configure]
            else:
                track, reason = "update", "already current"
                steps = ["engine_setup", "engine_check", *configure]
    return {"track": track, "track_reason": reason, "track_steps": steps}


def step_plugin_install(ctx: Ctx) -> StepResult:
    return StepResult(SKIPPED, "plugin install is a harness action this script cannot perform",
                      "run: /plugin marketplace add dbc-oduffy/coordinator-claude, then /plugin install coordinator@coordinator-claude, then restart and re-run the install")


def step_plugin_update(ctx: Ctx) -> StepResult:
    if not shutil.which("claude"):
        return StepResult(FAILED, "claude CLI not on PATH", "run: /plugin update coordinator@coordinator-claude")
    _, _, market = _installed_coordinator()
    market = market or "coordinator-claude"
    rc, out = run(["claude", "plugin", "marketplace", "update", market], timeout=300)
    if rc != 0:
        return StepResult(FAILED, out[-300:] or "marketplace update failed",
                          f"run: claude plugin marketplace update {market}")
    rc, out = run(["claude", "plugin", "update", f"coordinator@{market}"], timeout=300)
    if rc == 0:
        ctx.restart_needed = True
    return StepResult(RAN if rc == 0 else FAILED, out[-300:] or "updated",
                      "" if rc == 0 else "run: /plugin update coordinator@coordinator-claude")


def step_engine_setup(ctx: Ctx) -> StepResult:
    script, why = _engine_setup_script()
    if script is None:
        return StepResult(FAILED, why, "clone the engine as a sibling of this plugin clone and register it: machine-local set repos.claude_klabauter <path>")
    rc, out = run(_py(str(script)), timeout=600)
    return StepResult(RAN if rc == 0 else FAILED, out.splitlines()[-1] if out else f"exited {rc}")


def step_engine_check(ctx: Ctx) -> StepResult:
    ok, detail = _engine_check()
    return StepResult(RAN if ok else FAILED, detail)


# Who runs each track step. A human step names the exact command the agent hands over; the agent
# never runs it itself (plugin_update reaches the harness's plugin store).
TRACK_STEP_RUNNERS = {
    "plugin_install": {"runner": "human", "handover": "/plugin marketplace add dbc-oduffy/coordinator-claude, then /plugin install coordinator@coordinator-claude"},
    "plugin_update": {"runner": "human", "handover": "/coordinator:install"},
    "engine_setup": {"runner": "agent", "handover": None},
    "engine_check": {"runner": "agent", "handover": None},
}


def track_step_runners(steps: list[str]) -> list[dict]:
    return [{"id": i, **TRACK_STEP_RUNNERS[i]} for i in steps if i in TRACK_STEP_RUNNERS]


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


def build_plan(permission_mode: str | None) -> dict:
    problems = check_manifest_drift()
    return {
        "schema": SCHEMA,
        "orientation": ORIENTATION,
        "environment": (env := {"platform": platform.system(), "plugin_root": str(plugin_root()),
                                **detect_track()}),
        "track_step_runners": track_step_runners(env["track_steps"]),
        "mode_policy": mode_policy(permission_mode),
        "decisions": [decision_json(d) for d in build_decisions(permission_mode)],
        "tour": list(TOUR),
        "steps": [{"id": s.id, "decision": STEP_DECISION.get(s.id),
                   "implements": list(s.implements) or [f"exempt: {s.exempt}"]} for s in STEPS],
        "manifest_drift": {"ok": not problems, "problems": problems},
    }


def execute(answers: dict, only: set[str] | None = None, permission_mode: str | None = None) -> dict:
    ctx = Ctx(answers=answers, permission_mode=permission_mode)
    results = []
    steps: list = [Step(i, TRACK_STEP_FNS[i], exempt="track step")
                   for i in detect_track()["track_steps"] if i in TRACK_STEP_FNS]
    steps += STEPS
    for step in steps:
        if only and step.id not in only:
            continue
        try:
            res = step.fn(ctx)
        except Exception as exc:  # a step must never abort the block
            res = StepResult(FAILED, f"{type(exc).__name__}: {exc}")
        results.append({"id": step.id, "status": res.status, "detail": res.detail,
                        "follow_up": res.follow_up})
    counts = {k: sum(1 for r in results if r["status"] == k) for k in (RAN, SKIPPED, INHERITED, FAILED)}
    return {
        "schema": "coordinator-install-result/1",
        "steps": results,
        "summary": counts,
        "tour": list(TOUR) if answers.get("orientation") == "tour-now" else [],
        "added_extras": [f"{e}: added; say the word to remove" for e in ctx.extras],
        "restart_needed": ctx.restart_needed,
        "next_session": ctx.next_session,
        "follow_ups": [r["follow_up"] for r in results if r["follow_up"]],
    }


def render_text(block: dict) -> str:
    lines = [f"{r['status']:<9} {r['id']:<22} {r['detail']}" for r in block["steps"]]
    lines += [f"ADDED     {e}" for e in block["added_extras"]]
    lines += [f"NEXT      {f}" for f in block["follow_ups"]]
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


def walk_decisions(permission_mode: str | None, stdin, stdout, custom: bool) -> dict:
    """Ask the decisions on `stdin` in plain language. Express asks only what has no default."""
    stdout.write(ORIENTATION + "\n\n")
    raw: dict = {}
    for d in build_decisions(permission_mode):
        free_text = list(d.options) == ["<free text>"]
        if not custom and (d.default is not None or not free_text):
            continue
        stdout.write(f"\n{d.question}\n{d.why}\n")
        choices = [_describe_option(d.id, o) for o in d.options] if not free_text else []
        for i, (_, label) in enumerate(choices, 1):
            stdout.write(f"  {i}. {label}\n")
        default_hint = f" [{d.default}]" if d.default is not None else ""
        while True:
            reply = _ask(f"> {'number or name' if choices else 'answer'}{default_hint}: ", stdin, stdout)
            if reply is None or (reply == "" and d.default is not None):
                if d.default is None:
                    raise SystemExit(f"no answer for required question: {d.question}")
                break
            if free_text:
                if reply:
                    raw[d.id] = reply
                    break
                continue
            values = [v for v, _ in choices]
            picked = values[int(reply) - 1] if reply.isdigit() and 0 < int(reply) <= len(values) else reply
            if picked in values:
                raw[d.id] = picked
                break
            stdout.write(f"  choose one of: {', '.join(values)}\n")
    return raw


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
                    help="human path: apply the recommended defaults, asking only for what has none")
    ap.add_argument("--custom", action="store_true",
                    help="human path: walk the decisions one at a time on stdin")
    ap.add_argument("--check-drift", action="store_true", help="fail when manifest and steps disagree")
    ap.add_argument("--only", help="comma-separated step ids to run")
    ap.add_argument("--permission-mode", default=os.environ.get("COORDINATOR_PERMISSION_MODE"),
                    help="harness permission_mode from hook input; adapts defaults")
    ap.add_argument("--format", choices=("json", "text"), default="json")
    args = ap.parse_args(argv)

    if args.check_drift:
        problems = check_manifest_drift()
        for p in problems:
            print(f"DRIFT: {p}", file=sys.stderr)
        return 1 if problems else 0

    drift = check_manifest_drift()
    if drift:
        print(json.dumps({"error": "manifest/step drift", "problems": drift}, indent=2), file=sys.stderr)
        return 3

    if args.plan or (args.i_am_agent and not args.answers):
        print(json.dumps(build_plan(args.permission_mode), indent=2))
        return 0
    if args.express and args.custom:
        ap.error("--express and --custom are alternatives")
    if not (args.answers or args.non_interactive or args.express or args.custom):
        ap.error("pass --plan, --express, --custom, --answers <file|json>, --non-interactive, or --i-am-agent")
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
    return 1 if block["summary"][FAILED] else 0


if __name__ == "__main__":
    sys.exit(main())
