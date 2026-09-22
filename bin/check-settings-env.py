"""check-settings-env — assert `settings.json`'s `env` block carries the VALUES the manifest requires.

WHY THIS EXISTS. DoE-claude's `templates/settings-manifest.md` § Environment Variables names the
env values every machine needs, and several of them gate whether a tool exists at all — not how it
behaves. A wrong value does not error: the tool is simply absent from the model's surface, and the
session reports the capability as missing from this build. `/coordinator:install` checked only
whether the key was PRESENT, so a key present at the wrong value passed every gate.

That is not hypothetical. `DR-187` ratified `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS="1"` as standing
and its plan updated all eight doctrine surfaces, but the live `settings.json` was never flipped
back from `"0"`; `CLAUDE_CODE_ENABLE_TODO_TOOLS` — manifest-required on all machines since Claude
Code v2.1.233 stopped shipping `Task*` by default on Opus 4.8 / Sonnet 5 / Fable 5 / Mythos 5 — was
absent entirely. Every session on the box ran without the task-graph while every doctrine surface
said it was on, and the presence-only check reported healthy throughout.

REPORT-ONLY BY DEFAULT. Without `--apply` this prints and sets its exit code; it never writes
`settings.json`. `--apply` writes only the rows marked `all_machines` — a value the manifest states
identically for every host. Machine-specific rows are NEVER auto-written, because their correct
value is a property of the host, not of the manifest: `CLAUDE_CODE_USE_POWERSHELL_TOOL` at `"0"` on
a Windows host under a standing no-Bash directive removes the only command-issuing tool, which is
an outage, not a cosmetic setting (`DR-143`, superseding DR-113 clause 1). Those rows are checked
and reported, never repaired.

WHY VALUES LIVE HERE AND NOT IN THE MANIFEST. The manifest's cells carry prose conditions a parser
would have to guess at ("`"1"` on a Windows host under a no-Bash directive; unset elsewhere"). The
executable spec is `_SPEC` below; DoE-claude `tests/test_settings_env_manifest_parity.py` pins it
against the manifest table so the two cannot drift apart silently in either direction — the manifest
itself stays a published doctrine asset in DoE-claude, resolved through the plugin root, never
copied here.

Zero-spawn: stdlib only, no subprocess. Safe to run at a cadence on a box carrying a dozen-plus
concurrent EM sessions.

EFFECTIVE VALUES, ACROSS BOTH FILES. `settings.local.json` is Local scope and outranks
`settings.json`'s User scope, so this reads both and judges what the session actually gets. Reading
only the user file would report a value nothing uses — the same presence-vs-value mistake one file
over. A wrong value inherited from the local file is reported as unrepairable here, naming the file
that has to change: writing the user file cannot override it.

Exit codes: 0 = every required value matches (or `--apply` repaired every repairable one).
1 = at least one required value is wrong or missing. 2 = usage/environment error (settings.json
unreadable or not JSON).

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W2-C5.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from pathlib import Path


class _Row:
    """One manifest env row: what it must be, whether `--apply` may write it, and why it matters."""

    def __init__(
        self,
        name: str,
        *,
        required: str | None,
        all_machines: bool,
        gates: str,
        forbidden: tuple[str, ...] = (),
        windows_only: bool = False,
    ) -> None:
        self.name = name
        self.required = required
        self.all_machines = all_machines
        self.gates = gates
        self.forbidden = forbidden
        self.windows_only = windows_only


_SPEC_CACHE: tuple[_Row, ...] | None = None


def _spec() -> tuple[_Row, ...]:
    """`_SPEC`'s lazy build -- deferred out of module scope so instantiating `_Row` objects is
    not a module-body-inertness violation (`coordinator_core.warm.serve_classifier`). Cached: the
    rows are static, so every caller after the first gets the same tuple back."""
    global _SPEC_CACHE
    if _SPEC_CACHE is None:
        _SPEC_CACHE = (
            _Row(
                "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS",
                required="1",
                all_machines=True,
                gates="Agent Teams, the deep-research pipelines, and the Task* task-graph they block on",
            ),
            _Row(
                "CLAUDE_CODE_ENABLE_TODO_TOOLS",
                required="1",
                all_machines=True,
                gates="TaskCreate/TaskGet/TaskList/TaskUpdate in a main session on v2.1.233+ models",
            ),
            _Row(
                "CLAUDE_CODE_USE_POWERSHELL_TOOL",
                required=None,
                all_machines=False,
                gates="the PowerShell tool's availability (pinned, not inherited from a progressive rollout)",
                forbidden=("0",),
                windows_only=True,
            ),
        )
    return _SPEC_CACHE


def __getattr__(name: str) -> object:
    """PEP 562 module `__getattr__` -- `module._SPEC` (the shape
    `test_arrival_check_settings_env.py` reads via `importlib.util.module_from_spec`) resolves
    here to `_spec()`'s build, without binding `_SPEC` itself at module scope."""
    if name == "_SPEC":
        return _spec()
    raise AttributeError(f"module 'check-settings-env' has no attribute {name!r}")


def _default_settings_path() -> Path:
    """`$CLAUDE_HOME`-or-home joined with `.claude/settings.json`.

    `CLAUDE_HOME` overrides the HOME parent, not the `.claude` directory itself — the convention
    every other resolver in this tree uses, and the one `dist/publish-repo-setup/install.py` writes.
    """
    base = os.environ.get("CLAUDE_HOME") or str(Path.home())
    return Path(base) / ".claude" / "settings.json"


def _local_sibling(path: Path) -> Path:
    """`settings.local.json` beside `settings.json` — Local scope, which OUTRANKS User scope."""
    return path.with_name("settings.local.json")


def _load_env_block(path: Path, *, required: bool = True) -> dict[str, str]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        if required:
            raise SystemExit(f"check-settings-env: cannot read {path}: not found")
        return {}
    except OSError as exc:
        raise SystemExit(f"check-settings-env: cannot read {path}: {exc}")
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"check-settings-env: {path} is not valid JSON: {exc}")
    env = doc.get("env") or {}
    if not isinstance(env, dict):
        raise SystemExit(f"check-settings-env: {path} has a non-object `env` block")
    return {str(k): str(v) for k, v in env.items()}


def _applies_here(row: _Row) -> bool:
    return not row.windows_only or platform.system() == "Windows"


def _evaluate(
    env: dict[str, str], local_env: dict[str, str] | None = None
) -> list[dict[str, object]]:
    """One finding per row whose EFFECTIVE value is wrong, missing, or forbidden. Ordered as `_SPEC`.

    Effective, not as-written: `settings.local.json` is Local scope and outranks `settings.json`'s
    User scope, so a var set in both is decided by the local file. Reading only `settings.json`
    reports a value nothing in the session actually uses — the same presence-vs-value mistake this
    script exists to catch, one file over. A wrong value inherited from the local file is reported
    `repairable: False`: writing the user file cannot override it, so the repair must land there.
    """
    local_env = local_env or {}
    findings: list[dict[str, object]] = []
    for row in _spec():
        if not _applies_here(row):
            continue
        from_local = row.name in local_env
        actual = local_env[row.name] if from_local else env.get(row.name)
        if row.required is not None:
            if actual == row.required:
                continue
            findings.append(
                {
                    "var": row.name,
                    "kind": "missing" if actual is None else "wrong-value",
                    "actual": actual,
                    "expected": row.required,
                    "repairable": row.all_machines and not from_local,
                    "source": "settings.local.json" if from_local else "settings.json",
                    "gates": row.gates,
                }
            )
        elif actual is not None and actual in row.forbidden:
            findings.append(
                {
                    "var": row.name,
                    "kind": "forbidden-value",
                    "actual": actual,
                    "expected": f"anything but {'/'.join(row.forbidden)}",
                    "repairable": False,
                    "source": "settings.local.json" if from_local else "settings.json",
                    "gates": row.gates,
                }
            )
    return findings


def _apply(path: Path, findings: list[dict[str, object]]) -> list[str]:
    """Write the repairable findings back, preserving every other key and the file's 2-space shape."""
    repairable = [f for f in findings if f["repairable"]]
    if not repairable:
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc.setdefault("env", {})
    for finding in repairable:
        doc["env"][str(finding["var"])] = str(finding["expected"])
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    return [str(f["var"]) for f in repairable]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check-settings-env",
        description="Assert settings.json's env block matches the settings-manifest values.",
    )
    parser.add_argument(
        "--settings",
        type=Path,
        default=None,
        help="settings.json path (default: $CLAUDE_HOME-or-~ joined .claude/settings.json)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the all-machines rows back; machine-specific rows are never auto-written",
    )
    parser.add_argument("--json", action="store_true", help="emit findings as JSON on stdout")
    args = parser.parse_args(argv)

    path = args.settings or _default_settings_path()
    local = _local_sibling(path)

    def _current() -> list[dict[str, object]]:
        return _evaluate(_load_env_block(path), _load_env_block(local, required=False))

    findings = _current()

    applied: list[str] = []
    if args.apply and findings:
        applied = _apply(path, findings)
        findings = _current()

    if args.json:
        print(
            json.dumps(
                {
                    "settings": str(path),
                    "settings_local": str(local) if local.exists() else None,
                    "applied": applied,
                    "findings": findings,
                },
                indent=2,
            )
        )
    else:
        for var in applied:
            print(f"applied: {var} set to the manifest value in {path}")
        if not findings:
            print(f"check-settings-env: OK — every required env value matches ({path})")
        for finding in findings:
            actual = finding["actual"]
            shown = "unset" if actual is None else f'"{actual}"'
            print(f'{finding["var"]}: {shown}, expected {finding["expected"]} — {finding["kind"]}')
            print(f'    gates {finding["gates"]}')
            if finding["source"] == "settings.local.json":
                print(
                    f"    set in {local.name}, which outranks {path.name} — "
                    "fix it there; writing the user file cannot override it"
                )
            elif not finding["repairable"]:
                print("    machine-specific: not auto-written, set it by hand on this host")

    if findings:
        print(
            "\nEnv values are read at process start: a repair applies to sessions started after it.",
            file=sys.stderr,
        )
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
