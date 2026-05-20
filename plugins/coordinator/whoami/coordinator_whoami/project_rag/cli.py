"""
coordinator_whoami/project_rag/cli.py — `python -m coordinator_whoami.project_rag`
host introspection surface.

Probes local machine state and returns a structured JSON snapshot useful
for routing install decisions and debugging on-machine configuration.

Top-level output keys (schema_version 1):
    schema_version, captured_at, os, arch, gpu, python, uv,
    claude, coordinator, project, project_rag_state, addons,
    source, engine_version, project_kind

The `addons` key is populated by registered whoami contributors — addons
that implement the `project_rag_register_whoami_contributor` hookspec
(ADDON_PROTOCOL_VERSION 14). Each contributor's `probe()` result is nested
under `addons.<namespace>`.

The `source`, `engine_version`, and `project_kind` keys are native host
probes added per PM system-improvement directive 2026-05-19. They read the
project-rag source registry to identify the cwd-bound project and derive
UE engine version and project kind from its root. All three degrade to null
when standalone (no registry, no match, unexpected errors).

Persistence:
    Output is written to `whoami_profile` sub-key of
    `~/.claude/project-rag/install-profile.json` (DR-9 path). Consumers
    branch on field presence: absent `whoami_profile` means whoami has not
    run yet — not a failed probe.

Invocation:
    python -m coordinator_whoami.project_rag [--human] [--refresh] [--no-persist]

    --human      Pretty-print JSON to stdout (default: compact single-line).
    --refresh    Re-run all probes even if a recent profile exists on disk.
    --no-persist Do not write output to install-profile.json (stdout only).

Spec backlink (origin): docs/plans/2026-05-19-first-class-install-redesign.md §W3 — file lives at X:/project-rag (not imported; preserved at source).
Re-anchored backlink (this repo): docs/plans/2026-05-19-whoami-substrate-migration.md § 8 Task 2
"""
from __future__ import annotations

import json
import logging
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("coordinator_whoami.project_rag.cli")

# ---------------------------------------------------------------------------
# Schema version — bump on any top-level key addition/removal/retyping.
# ---------------------------------------------------------------------------
WHOAMI_SCHEMA_VERSION: int = 1

# ---------------------------------------------------------------------------
# Helpers — lightweight probes (no daemon spawn, no network, no torch import)
# ---------------------------------------------------------------------------

def _probe_os() -> dict[str, Any]:
    """Probe OS name, version string, and active shell."""
    name = platform.system()
    version = platform.version()

    # Normalise OS name to a short canonical form consumers can branch on.
    if name == "Windows":
        # platform.version() on Win11: "10.0.22631" — readable enough.
        pretty = name
    elif name == "Darwin":
        pretty = "macOS"
    elif name == "Linux":
        pretty = "Linux"
    else:
        pretty = name

    # Shell: honour SHELL env on POSIX; guess from COMSPEC/PSModulePath on Win.
    shell = os.environ.get("SHELL")
    if not shell and name == "Windows":
        ps_path = os.environ.get("PSModulePath", "")
        if ps_path:
            shell = "powershell"
        else:
            comspec = os.environ.get("COMSPEC", "")
            shell = Path(comspec).stem.lower() if comspec else "cmd"

    return {
        "name": pretty,
        "version": version,
        "shell": shell or "unknown",
    }


def _probe_arch() -> dict[str, Any]:
    """Probe CPU architecture; detect Apple Silicon."""
    machine = platform.machine()
    apple_silicon = (platform.system() == "Darwin") and (machine == "arm64")
    return {
        "machine": machine,
        "apple_silicon": apple_silicon,
    }


def _probe_gpu() -> dict[str, Any]:
    """Probe GPU presence via nvidia-smi (fast, no torch import).

    Returns a dict with keys: present, vendor, vram_free_mib, cuda_driver.
    On non-NVIDIA machines or when nvidia-smi is absent, present=false.
    """
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.free,driver_version",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            lines = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]  # Review: Reviewer A A-F6 — renamed l→line (single-char variable name)
            if lines:
                parts = lines[0].split(",")
                vram_free = int(parts[0].strip()) if parts[0].strip().isdigit() else None
                driver = parts[1].strip() if len(parts) > 1 else None
                return {
                    "present": True,
                    "vendor": "nvidia",
                    "vram_free_mib": vram_free,
                    "cuda_driver": driver,
                }
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError, ValueError):
        pass

    return {
        "present": False,
        "vendor": None,
        "vram_free_mib": None,
        "cuda_driver": None,
    }


def _probe_python() -> dict[str, Any]:
    """Probe invoking Python version, path, MS Store shim check, and .venv state.

    Uses the running interpreter as the invoking Python since whoami is invoked
    via `python -m coordinator_whoami.project_rag` — the invoking interpreter is
    what ran this code. MS Store shim detection: path contains WindowsApps or
    Microsoft\\WindowsApps.

    Review: code-reviewer — F5: renamed ambient_path/ambient_version → invoking_path/
    invoking_version; "ambient" was misleading under venv invocation where the
    interpreter is not the ambient system Python.
    """
    interp = sys.executable
    version = platform.python_version()

    ms_store_shim = bool(
        interp
        and (
            "WindowsApps" in interp
            or "Microsoft\\WindowsApps" in interp
            or "Microsoft/WindowsApps" in interp
        )
    )

    # .venv detection: look for a .venv adjacent to the repo root.
    # Walk up from CWD to find pyproject.toml as proxy for repo root.
    venv_present = False
    venv_python: str | None = None

    try:
        cwd = Path.cwd()
        candidate = cwd
        for _ in range(6):  # up to 6 levels up
            pyproject = candidate / "pyproject.toml"
            if pyproject.exists():
                venv_dir = candidate / ".venv"
                if venv_dir.is_dir():
                    venv_present = True
                    # Locate python executable inside the venv.
                    for rel in (
                        "Scripts/python.exe",
                        "Scripts/python",
                        "bin/python",
                        "bin/python3",
                    ):
                        venv_py = venv_dir / rel
                        if venv_py.exists():
                            venv_python = str(venv_py)
                            break
                break
            parent = candidate.parent
            if parent == candidate:
                break
            candidate = parent
    except (OSError, PermissionError):
        pass

    return {
        "invoking_version": version,
        "invoking_path": interp,
        "ms_store_shim": ms_store_shim,
        "venv_present": venv_present,
        "venv_python": venv_python,
    }


def _probe_uv() -> dict[str, Any]:
    """Probe uv presence and version via subprocess (no shell script required)."""
    try:
        result = subprocess.run(
            ["uv", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # "uv 0.4.18" → "0.4.18"
            output = result.stdout.strip()
            parts = output.split()
            version = parts[1] if len(parts) >= 2 else output
            return {"present": True, "version": version}
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return {"present": False, "version": None}


def _probe_claude() -> dict[str, Any]:
    """Probe ~/.claude.json existence and project-rag entry health.

    Reads from the CLAUDE_HOME env var if set (test-sandbox support),
    otherwise ~/.claude.json.

    Lookup order (W5 default install writes per-project, not top-level):
        1. Top-level: data["mcpServers"]["project-rag"]
        2. Per-project: data["projects"][<any>]["mcpServers"]["project-rag"]
    Returns "healthy" on the first non-None entry found in either location.

    Entry health:
        "healthy"  — mcpServers.project-rag exists with a non-empty command/args
                     (checked in top-level mcpServers first, then per-project)
        "broken"   — mcpServers.project-rag key exists but looks malformed
        "absent"   — no mcpServers.project-rag key found anywhere
        "no_file"  — ~/.claude.json does not exist
    """
    claude_home = os.environ.get("CLAUDE_HOME")
    if claude_home:
        claude_json_path = Path(claude_home) / ".claude.json"
    else:
        claude_json_path = Path.home() / ".claude.json"

    if not claude_json_path.exists():
        return {"json_present": False, "project_rag_entry": "no_file"}

    try:
        data = json.loads(claude_json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"json_present": True, "project_rag_entry": "broken"}

    def _check_entry(entry: Any) -> str | None:
        """Return health verdict for a single mcpServers entry, or None if absent."""
        if entry is None:
            return None
        command = entry.get("command") or entry.get("args")
        if not command:
            return "broken"
        return "healthy"

    # Review: code-reviewer — F1: top-level lookup misses W5 per-project install path.
    # Check top-level mcpServers first.
    mcp_servers = data.get("mcpServers") or {}
    top_level_entry = mcp_servers.get("project-rag")
    verdict = _check_entry(top_level_entry)
    if verdict is not None:
        return {"json_present": True, "project_rag_entry": verdict}

    # Fall through to per-project mcpServers (default W5 install shape).
    for proj_data in (data.get("projects") or {}).values():
        proj_mcp = (proj_data.get("mcpServers") if isinstance(proj_data, dict) else None) or {}
        per_project_entry = proj_mcp.get("project-rag")
        verdict = _check_entry(per_project_entry)
        if verdict is not None:
            return {"json_present": True, "project_rag_entry": verdict}

    return {"json_present": True, "project_rag_entry": "absent"}


def _probe_coordinator() -> dict[str, Any]:
    """Probe coordinator-claude installation state.

    Checks for the coordinator's CLAUDE.md at the standard plugin path
    under ~/.claude/plugins/coordinator-claude/.
    """
    claude_home = os.environ.get("CLAUDE_HOME")
    base = Path(claude_home) if claude_home else Path.home() / ".claude"
    coordinator_marker = base / "plugins" / "coordinator-claude" / "coordinator" / "CLAUDE.md"

    if coordinator_marker.exists():
        # Attempt to read version from the CLAUDE.md frontmatter — optional.
        version: str | None = None
        try:
            text = coordinator_marker.read_text(encoding="utf-8", errors="replace")
            # Look for "version: X.Y.Z" in frontmatter-like header.
            m = re.search(r"version:\s*([^\s\n]+)", text[:2000])
            if m:
                version = m.group(1)
        except OSError:
            pass
        return {"installed": True, "version": version}

    return {"installed": False, "version": None}


def _probe_project() -> dict[str, Any]:
    """Probe the current working directory for project kind markers.

    Checks CWD for .uproject, package.json, Cargo.toml, pyproject.toml.
    """
    cwd = Path.cwd()
    kind_markers = {
        "uproject": list(cwd.glob("*.uproject")),
        "package_json": cwd / "package.json",
        "cargo_toml": cwd / "Cargo.toml",
        "pyproject_toml": cwd / "pyproject.toml",
    }

    kinds_detected: list[str] = []
    uproject_present = bool(kind_markers["uproject"])

    if uproject_present:
        kinds_detected.append("unreal")
    if kind_markers["package_json"].exists():
        kinds_detected.append("typescript")
    if kind_markers["cargo_toml"].exists():
        kinds_detected.append("rust")
    if kind_markers["pyproject_toml"].exists():
        kinds_detected.append("python")

    return {
        "root": str(cwd),
        "kinds_detected": kinds_detected,
        "uproject_present": uproject_present,
    }


def _probe_project_rag_state() -> dict[str, Any]:
    """Probe the project-rag data directory state.

    Looks for Saved/ProjectRag/ under CWD, checks for schema_version and
    chroma collection presence.
    """
    cwd = Path.cwd()
    data_dir = cwd / "Saved" / "ProjectRag"

    if not data_dir.is_dir():
        return {
            "data_dir_present": False,
            "schema_version": None,
            "chroma_collection_present": None,
        }

    # Check for graph.db to infer schema version (quick heuristic).
    graph_db = data_dir / "graph.db"
    schema_version: int | None = None
    if graph_db.exists():
        try:
            import sqlite3
            con = sqlite3.connect(str(graph_db))
            try:
                row = con.execute(
                    "SELECT value FROM _meta WHERE key='schema_version' LIMIT 1"
                ).fetchone()
                if row:
                    schema_version = int(row[0])
            finally:
                con.close()
        except Exception:  # noqa: BLE001 — best-effort, must not crash whoami
            pass

    # Chroma collection: look for any chroma directory.
    # Review: code-reviewer — F7: iterdir() can raise OSError/PermissionError on
    # locked or ACL-restricted data dirs; wrap defensively to avoid crashing whoami.
    chroma_present: bool = False
    try:
        chroma_dirs = [d for d in data_dir.iterdir() if d.is_dir() and "chroma" in d.name.lower()]
        chroma_present = bool(chroma_dirs)
    except (OSError, PermissionError):
        chroma_present = False

    return {
        "data_dir_present": True,
        "schema_version": schema_version,
        "chroma_collection_present": chroma_present,
    }


# ---------------------------------------------------------------------------
# Addon contributor aggregation
# ---------------------------------------------------------------------------

def _collect_addon_blocks() -> dict[str, Any]:
    """Discover and dispatch all addon whoami contributors.

    Delegated to coordinator_whoami.project_rag.addons.collect_addon_blocks() per
    Task 5 of the migration. compose() still receives a dict keyed by namespace
    (legacy shape; input to cli_output.v1.json validation per O14). The R3 lift to
    first-class extras keys happens in envelope.py, which reads this output.
    """
    from coordinator_whoami.project_rag.addons import collect_addon_blocks
    return collect_addon_blocks()


# ---------------------------------------------------------------------------
# New native probes — source, engine_version, project_kind (O32-O34)
# Added per PM system-improvement directive 2026-05-19.
# All three degrade gracefully to None on registry-absent, JSON errors, or
# any unexpected exception — they MUST NOT crash the CLI when standalone.
# ---------------------------------------------------------------------------

def _find_best_registry_entry() -> dict | None:
    """Return the registry entry dict for the most-specific source covering cwd.

    Reads ~/.project-rag/projects.json (raw JSON, no project-rag import) to
    remain standalone-safe. Returns the winning entry dict on match, or None
    when: registry absent, no match, JSON decode error, or any unexpected
    exception.

    Review: Reviewer A A-F3 — extracted shared traversal; callers derive
    path/name from the returned entry to eliminate ~35 lines of duplication.
    """
    try:
        registry_path_env = os.environ.get("PROJECT_RAG_REGISTRY_PATH")
        if registry_path_env:
            registry_path = Path(registry_path_env)
        else:
            registry_path = Path.home() / ".project-rag" / "projects.json"

        if not registry_path.exists():
            return None

        raw = json.loads(registry_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("sources"), list):
            return None

        cwd = Path.cwd().resolve()
        best_entry: dict | None = None
        best_len = -1

        for entry in raw["sources"]:
            if not isinstance(entry, dict):
                continue
            path_str = entry.get("path")
            if not path_str:
                continue
            try:
                entry_path = Path(path_str).resolve()
                cwd.relative_to(entry_path)  # raises ValueError if not under entry_path
            except (ValueError, OSError):
                continue
            parts_len = len(entry_path.parts)
            if parts_len > best_len:
                best_entry = entry
                best_len = parts_len

        return best_entry
    except Exception:  # noqa: BLE001 — defensive; must not crash whoami
        return None


def _resolve_bound_project_root() -> Path | None:
    """Return the project root for the most-specific registered source covering cwd.

    Reads ~/.project-rag/projects.json directly (raw JSON, no project-rag import)
    to remain standalone-safe. Returns None when: registry absent, no match,
    JSON decode error, or any unexpected exception.
    """
    try:
        entry = _find_best_registry_entry()
        if entry is None:
            return None
        return Path(entry["path"]).resolve()
    except Exception:  # noqa: BLE001 — defensive; must not crash whoami
        return None


def _probe_source() -> str | None:
    """Probe the project-rag source registry for the cwd-bound source name.

    Reads ~/.project-rag/projects.json, enumerates registered sources, and
    returns the name of the most-specific source whose root is an ancestor of
    cwd (longest path match). Returns null on: registry absent, no match,
    JSON decode error, or any unexpected exception.

    Purpose: identify which registered project-rag source the current working
    directory belongs to, enabling downstream env-routing decisions.
    """
    try:
        entry = _find_best_registry_entry()
        if entry is None:
            return None
        return entry.get("name")
    except Exception:  # noqa: BLE001 — defensive; must not crash whoami
        return None


def _probe_engine_version() -> str | None:
    """Probe the UE EngineAssociation for the cwd-bound project.

    Finds the registered project root via the source registry, looks for a
    .uproject file in that root, reads it as JSON, and returns the
    EngineAssociation field value. Returns null on: no bound source, no
    .uproject in root, missing EngineAssociation key, JSON decode error, or
    any unexpected exception.

    Purpose: identify the UE engine version the bound project targets, enabling
    install routing and doctor probes without requiring project-rag to be imported.
    """
    try:
        project_root = _resolve_bound_project_root()
        if project_root is None:
            return None

        uproject_files = list(project_root.glob("*.uproject"))
        if not uproject_files:
            return None

        uproject_path = uproject_files[0]
        data = json.loads(uproject_path.read_text(encoding="utf-8"))
        return data.get("EngineAssociation") or None
    except Exception:  # noqa: BLE001 — defensive; must not crash whoami
        return None


def _probe_project_kind() -> str | None:
    """Probe the project kind for the cwd-bound registered source.

    Branches on file markers at the bound project root:
      - .uproject present          → "ue"
      - pyproject.toml or requirements.txt present → "python"
      - package.json present       → "typescript"
      - else                       → null

    Returns null when no source is bound or on any unexpected exception.

    Purpose: let downstream routing logic identify project type from the
    registered source root without importing project-rag or running probes.
    """
    try:
        project_root = _resolve_bound_project_root()
        if project_root is None:
            return None

        if list(project_root.glob("*.uproject")):
            return "ue"
        if (project_root / "pyproject.toml").exists() or (project_root / "requirements.txt").exists():
            return "python"
        if (project_root / "package.json").exists():
            return "typescript"
        return None
    except Exception:  # noqa: BLE001 — defensive; must not crash whoami
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compose() -> dict[str, Any]:
    """Run all host probes and return the assembled whoami JSON dict.

    Iterates registered addon whoami contributors and assembles
    `addons[<namespace>] = contributor.probe()` under the top-level
    `addons:` key. On contributor exception: records
    `{"probe_error": "<class>: <msg>", "schema_version": null}` and
    continues with remaining contributors.

    Returns:
        A dict with schema_version=1 and top-level keys per the W3 spec
        plus the three new native probes (source, engine_version, project_kind)
        added per PM system-improvement directive 2026-05-19.

    Spec backlink (origin): docs/plans/2026-05-19-first-class-install-redesign.md §W3 — file lives at X:/project-rag (not imported; preserved at source).
    Re-anchored backlink (this repo): docs/plans/2026-05-19-whoami-substrate-migration.md § 8 Task 2
    """
    return {
        "schema_version": WHOAMI_SCHEMA_VERSION,
        "captured_at": datetime.now(tz=timezone.utc).isoformat(),
        "os": _probe_os(),
        "arch": _probe_arch(),
        "gpu": _probe_gpu(),
        "python": _probe_python(),
        "uv": _probe_uv(),
        "claude": _probe_claude(),
        "coordinator": _probe_coordinator(),
        "project": _probe_project(),
        "project_rag_state": _probe_project_rag_state(),
        "addons": _collect_addon_blocks(),
        # NEW native probes added per PM 2026-05-19 system-improvement directive (R2 prep):
        "source": _probe_source(),
        "engine_version": _probe_engine_version(),
        "project_kind": _probe_project_kind(),
    }


def persist(profile: dict[str, Any]) -> Path:
    """Persist the whoami profile to ~/.claude/project-rag/install-profile.json.

    Writes into the `whoami_profile` sub-key; merges with any existing content
    in the file. `captured_at` is updated at the top level.

    Returns the path written.

    Spec backlink (origin): docs/plans/2026-05-19-first-class-install-redesign.md §W3 — file lives at X:/project-rag (not imported; preserved at source).
      ("Persistence — whoami_profile sub-key under install-profile.json")
    Re-anchored backlink (this repo): docs/plans/2026-05-19-whoami-substrate-migration.md § 8 Task 2
    """
    from coordinator_whoami.project_rag._paths import resolve_user_marker_dir

    user_dir = resolve_user_marker_dir()
    profile_path = user_dir / "install-profile.json"

    # Load existing content or start fresh.
    existing: dict[str, Any] = {}
    if profile_path.exists():
        try:
            existing = json.loads(profile_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}

    existing["whoami_profile"] = profile
    existing["captured_at"] = profile.get("captured_at", datetime.now(tz=timezone.utc).isoformat())

    profile_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = profile_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, profile_path)

    return profile_path


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Entry-point for `python -m coordinator_whoami.project_rag`."""
    import argparse
    from coordinator_whoami.project_rag.envelope import compose_envelope, persist as persist_envelope

    parser = argparse.ArgumentParser(
        prog="python -m coordinator_whoami.project_rag",
        description=(
            "Probe local machine state for project-rag install routing.\n"
            "Output is machine-readable JSON by default.\n"
            "For full diagnostics run: /project-rag:doctor"
        ),
    )
    parser.add_argument(
        "--human",
        action="store_true",
        help="Pretty-print JSON output (default: compact single-line).",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-run all probes even if a recent profile exists on disk.",
    )
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Do not write output to install-profile.json (stdout only).",
    )
    args = parser.parse_args(argv)

    # R2 (PM 2026-05-19): emit envelope-shaped JSON; persist() stores envelope shape.
    profile = compose_envelope()

    if not args.no_persist:
        try:
            written = persist_envelope(profile)
            log.debug("whoami: profile persisted to %s", written)
        except Exception as exc:  # noqa: BLE001 — persist is best-effort
            log.warning("whoami: could not persist profile: %s", exc)

    if args.human:
        print(json.dumps(profile, indent=2))
    else:
        print(json.dumps(profile))

    return 0


# Backwards-compat alias — project-rag source used `_main`; callers importing
# by name continue to work after migration.
_main = main


if __name__ == "__main__":
    sys.exit(main())
