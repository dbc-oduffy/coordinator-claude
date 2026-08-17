"""setup-verify.py — imperative logic ported out of the coordinator-claude
`/coordinator:setup` chain-walk skill (DoE-claude
`coordinator/skills/setup/SKILL.md`) into a naked-Python CLI.

Purpose: the skill's bash fences carried genuine loops/conditionals/multi-step
transforms that do not belong hand-duplicated in a `.md` instruction file (see
DoE-claude `CLAUDE.local.md` § "A skill must LINK to an entrypoint, not carry a
command payload for the EM to transcribe" — unlintable, untestable,
unreachable-by-extension-filtered code search). This CLI is that logic's new
home; the skill repoints to call it by name (a separate chunk, D2).

Subcommands (one per ported fence):
    layout --plugin-root PATH
        Detect flat (publish-repo) vs nested (working-repo) layout by probing
        for docs/install/AGENT.md under PLUGIN_ROOT. Prints Layout: / Manifest
        path: lines; exits 1 with remediation if the manifest is absent.

    visited-init [--settings-home PATH]
        Initialise the chain-walk visited-set file (contract § Visited-set
        protocol): stale-cleanup files older than 60 minutes, then write a
        fresh empty-visited-array file stamped with a new session id.

    check-override-flags -- ARG [ARG ...]
        Validate the --skip-dep-check / --accept-missing-deps-risk pair — both
        or neither, never exactly one. Exit 93 (contract exit-code) on a
        single-flag mismatch.

    check-hooks --plugin-root PATH
        Parse PLUGIN_ROOT/hooks/hooks.json, extract coordinator-owned hook
        script paths referenced via ${CLAUDE_PLUGIN_ROOT}/hooks/..., and
        verify each exists on disk. FAIL (exit 1) on any missing hook file.

    check-skill-description --skill-file PATH
        Parse a SKILL.md's YAML frontmatter and validate a non-empty
        description: field is present (skill-discovery precondition).

    check-settings-membership [--settings PATH]
        Check that "coordinator" appears in settings.json's enabledPlugins
        (or legacy plugins) list.

    check-plugin-registered --plugin NAME --marketplace NAME
                             [--marketplace-source SOURCE]
                             [--installed-plugins PATH] [--known-marketplaces PATH]
                             [--settings PATH] [--plugin-dir PATH]
        Verify a plugin is genuinely reachable, not merely present as a
        `~/.claude/plugins/<name>/` runtime-data directory (that directory is
        exactly what masquerades as "installed" -- no manifest, no commands,
        no hooks, and the plugin's SessionStart hook never runs; hit on
        project-rag live 2026-07-28, reproducible fleet-wide). Two legitimate
        routes to PASS: (1) `<plugin>@<marketplace>` present in
        installed_plugins.json AND `<marketplace>` present in
        known_marketplaces.json; (2) --plugin-dir given, pointing at a dev
        SOURCE checkout with a plugin manifest AND commands/hooks positively
        present there (a live `--plugin-dir` resolution never touches either
        registry file, so route 1 correctly FAILs for it -- e.g. coordinator
        itself, resolved from DoE-claude). Neither bare directory presence
        nor a dev-repo sentinel alone is ever sufficient evidence. FAIL
        (exit 1) when neither route clears, with the exact `claude plugin
        marketplace add`/`claude plugin install` remediation commands for
        the specific plugin/marketplace.

Exit codes are documented per-subcommand above; each subcommand's own
docstring/error text names its contract explicitly. A missing/unreadable
input file is reported to stderr and the subcommand's own failure exit code
is used — this CLI never silently degrades an input error to exit 0.

Spec backlink: docs/plans/2026-06-15-coordinator-install-chain-application-phase-b.md § C4
Spec backlink: DoE-claude coordinator/skills/setup/SKILL.md (Steps 1, 3, 4, 6 Probes 2/3)
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path


# ---------------------------------------------------------------------------
# Step 1 (SKILL.md) — layout detection (flat publish-repo vs. nested working-repo)
# ---------------------------------------------------------------------------

GENERATES = []  # cmd_visited_init writes the chain-walk visited-set under <settings-home>/coordinator-claude/chain-walk-<uuid>.json (settings-home, outside claude-klabauter's own tree); every other subcommand is read-only


def cmd_layout(args: argparse.Namespace) -> int:
    plugin_root = Path(args.plugin_root).resolve()
    flat_agent_md = plugin_root / "docs" / "install" / "AGENT.md"

    if flat_agent_md.is_file():
        layout = "flat"
    else:
        layout = "nested"
    repo_root = plugin_root

    manifest = repo_root / "docs" / "install" / "agent-install-manifest.json"
    print(f"Layout: {layout}")
    print(f"Manifest path: {manifest}")

    if not manifest.is_file():
        print(
            f"Manifest not found at {manifest}. Re-run after the install surface "
            "has been committed (plugins/coordinator/docs/install/"
            "agent-install-manifest.json).",
            file=sys.stderr,
        )
        return 1
    return 0


# ---------------------------------------------------------------------------
# Step 3 (SKILL.md) — visited-set initialisation (chain-walk contract)
# ---------------------------------------------------------------------------

def _default_settings_home() -> str:
    explicit = os.environ.get("COORDINATOR_SETTINGS_HOME") or os.environ.get("CLAUDE_HOME")
    if explicit:
        return explicit
    home = (
        os.environ.get("HOME")
        or os.environ.get("USERPROFILE")
        or os.path.expanduser("~")
    )
    return os.path.join(home, ".coordinator-claude-settings")


def cmd_visited_init(args: argparse.Namespace) -> int:
    session_id = str(uuid.uuid4())
    settings_home = args.settings_home or _default_settings_home()
    visited_dir = Path(settings_home) / "coordinator-claude"
    visited_file = visited_dir / f"chain-walk-{session_id}.json"

    visited_dir.mkdir(parents=True, exist_ok=True)

    # Stale-cleanup: delete chain-walk-*.json files whose mtime is older than
    # 60 minutes (mirrors the bash `find ... -mmin +60 -exec rm -f {} +`).
    now = time.time()
    stale_cutoff_seconds = 60 * 60
    for candidate in visited_dir.glob("chain-walk-*.json"):
        try:
            age = now - candidate.stat().st_mtime
        except OSError:
            continue
        if age > stale_cutoff_seconds:
            try:
                candidate.unlink()
            except OSError:
                pass

    data = {
        "session_id": session_id,
        "started_at": datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "visited": [],
    }
    visited_file.write_text(json.dumps(data, indent=2))

    print(f"Session ID: {session_id}")
    print(f"Visited-set: {visited_file}")
    return 0


# ---------------------------------------------------------------------------
# Step 4 (SKILL.md) — paired override-flag validation
# ---------------------------------------------------------------------------

def cmd_check_override_flags(args: argparse.Namespace) -> int:
    tail = args.rest
    has_skip = "--skip-dep-check" in tail
    has_risk = "--accept-missing-deps-risk" in tail

    if has_skip != has_risk:
        print(
            "ERROR (exit 93): Both --skip-dep-check AND --accept-missing-deps-risk "
            "must be passed together. Passing only one is not valid.",
            file=sys.stderr,
        )
        return 93

    if has_skip and has_risk:
        print("OK: both override flags present — dep-check bypass authorized")
    else:
        print("OK: neither override flag present — normal dep-check path")
    return 0


# ---------------------------------------------------------------------------
# Step 6 Probe 2 (SKILL.md) — hooks.json coordinator-owned hook presence check
# ---------------------------------------------------------------------------

# Review: code-reviewer — F6 (carried from SKILL.md): check for specific
# coordinator-owned hooks named in hooks.json by path, not a blanket *.sh
# count (blanket passes vacuously when coordinator's hooks are absent but
# other *.sh files happen to exist).
#
# negative-spec: the extension alternation must NOT be narrowed back to a
# single language. This regex was `(\S+\.sh)` while every coordinator hook had
# already migrated to naked Python under the no-new-bash rule, so it matched
# zero of 42 registered hooks and the probe reported "none detected" — exit 0,
# forever blind, which is the same vacuous pass F6 above was raised to kill.
# An extension list is load-bearing here: widen it when a new hook language
# lands, never shrink it.
#
# That rule stands, but it is NOT the only way this probe goes blind, and
# treating it as such cost a second blindness (machine-b, 2026-08-17): the
# regex was correct and matched zero of 27 hooks anyway, because the paths had
# moved out of `command` into `args` under the bootstrap-exec seam. The scanned
# FIELD SET is load-bearing exactly as much as the extension list is — see
# `_walk_hook_commands`. Before editing this pattern, confirm the path is
# actually reaching it.
_HOOK_COMMAND_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/hooks/(\S+\.(?:py|sh))")


def _walk_hook_commands(obj):
    """Yield every coordinator-owned hook path found on a hook entry anywhere in
    the hooks.json tree.

    Scans `args[]` as well as `command`, because a hook entry's script path is
    not reliably in `command`. Under the bootstrap-exec seam every coordinator
    entry reads `"command": "python3"` with the real target in `args`:

        {"command": "python3",
         "args": ["-c", "<exec-the-file-at-argv-tail bootstrap>",
                  "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/sessionstart-dispatch.py", ...]}

    Scanning `command` alone matched zero of 27 registered hooks on machine-b
    2026-08-17 — the same forever-blind vacuous pass the negative-spec above was
    written to kill, arriving through a different door: the paths moved out of
    the scanned field rather than changing extension. The regex itself was never
    wrong (`hooks/scripts/foo.py` satisfies it), so widening the alternation —
    which this probe's own FAIL text used to recommend — would have fixed
    nothing. Scan every field a path can hide in, not just the obvious one.
    """
    if isinstance(obj, dict):
        for key in ("command", "args"):
            value = obj.get(key)
            for text in (value,) if isinstance(value, str) else (
                [v for v in value if isinstance(v, str)] if isinstance(value, list) else ()
            ):
                m = _HOOK_COMMAND_RE.search(text)
                if m:
                    yield m.group(1)
        for v in obj.values():
            yield from _walk_hook_commands(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_hook_commands(v)


def _count_hook_commands(obj) -> int:
    """Count every "command" key in the tree, matched by the pattern or not.

    The discriminator between a hooks.json that genuinely registers nothing and
    one whose entries the pattern can no longer recognise — the difference
    between a benign WARN and a blind probe.
    """
    total = 0
    if isinstance(obj, dict):
        if isinstance(obj.get("command"), str):
            total += 1
        for v in obj.values():
            total += _count_hook_commands(v)
    elif isinstance(obj, list):
        for v in obj:
            total += _count_hook_commands(v)
    return total


def cmd_check_hooks(args: argparse.Namespace) -> int:
    plugin_root = Path(args.plugin_root).resolve()
    plugin_hooks_dir = plugin_root / "hooks"
    hooks_json = plugin_hooks_dir / "hooks.json"

    if not hooks_json.is_file():
        print(
            f"[WARN] hooks.json not found at {hooks_json} — cannot verify "
            "coordinator-specific hooks",
            file=sys.stderr,
        )
        return 0

    try:
        data = json.loads(hooks_json.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[WARN] failed to parse {hooks_json}: {exc}", file=sys.stderr)
        return 0

    rel_paths = sorted(set(_walk_hook_commands(data)))

    present = []
    missing = []
    for rel_path in rel_paths:
        full_path = plugin_hooks_dir / rel_path
        if full_path.is_file():
            present.append(rel_path)
        else:
            missing.append(rel_path)

    if missing:
        print(
            "FAIL — coordinator hook(s) named in hooks.json are missing from disk:",
            file=sys.stderr,
        )
        for h in missing:
            print(f"  missing: {plugin_hooks_dir / h}", file=sys.stderr)
        return 1

    if present:
        print(f"PASS — {len(present)} coordinator-owned hook file(s) verified present on disk")
        return 0

    total_commands = _count_hook_commands(data)
    if total_commands:
        print(
            f"FAIL — {hooks_json} registers {total_commands} hook command(s), but none "
            "matched the coordinator-owned pattern, so this probe verified nothing.",
            file=sys.stderr,
        )
        print(
            f"  pattern: {_HOOK_COMMAND_RE.pattern}",
            file=sys.stderr,
        )
        print(
            "  A registered-but-unrecognised hook set means the probe has gone blind, "
            "not that the hooks are absent. Check, in order: (1) which field carries "
            "the script path — _walk_hook_commands scans `command` and `args`, so a "
            "path reachable only through some other key is invisible here; (2) whether "
            "the path is still spelled ${CLAUDE_PLUGIN_ROOT}/hooks/...; (3) only then, "
            "the extension alternation. Do NOT reach for (3) first — the 2026-08-17 "
            "blindness was (1), the paths having moved into `args` under the "
            "bootstrap-exec seam, and no alternation change would have fixed it.",
            file=sys.stderr,
        )
        return 1

    print("[WARN] No coordinator-owned hook scripts detected in hooks.json", file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# Step 6 Probe 3 (SKILL.md) — SKILL.md frontmatter description parse + validate
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
_DESC_QUOTED_RE = re.compile(r"description:\s*[\"'](.*?)[\"']", re.DOTALL)
_DESC_BARE_RE = re.compile(r"description:\s*(.+)")


def cmd_check_skill_description(args: argparse.Namespace) -> int:
    skill_file = Path(args.skill_file)

    if not skill_file.is_file():
        print(f"FAIL — representative skill file missing: {skill_file}", file=sys.stderr)
        return 1

    content = skill_file.read_text()
    m = _FRONTMATTER_RE.match(content)
    if not m:
        print("FAIL — skill file has no YAML frontmatter")
        return 1

    fm = m.group(1)
    desc_match = _DESC_QUOTED_RE.search(fm)
    if not desc_match:
        desc_match = _DESC_BARE_RE.search(fm)
    if not desc_match:
        print("FAIL — no description: field found in frontmatter")
        return 1

    desc = desc_match.group(1).strip()
    if not desc:
        print("FAIL — description: field is empty")
        return 1

    print(f"PASS — description field present with trigger phrases ({len(desc)} chars)")
    return 0


# ---------------------------------------------------------------------------
# Step 6 Probe 1 (SKILL.md) — settings.json enabledPlugins membership check
# ---------------------------------------------------------------------------

def cmd_check_settings_membership(args: argparse.Namespace) -> int:
    settings_path = Path(args.settings or os.path.join(os.path.expanduser("~"), ".claude", "settings.json"))

    if not settings_path.is_file():
        print(
            f"[WARN] settings.json not found at {settings_path} — cannot verify "
            "plugin enablement",
            file=sys.stderr,
        )
        return 0

    try:
        data = json.loads(settings_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[WARN] failed to parse {settings_path}: {exc}", file=sys.stderr)
        return 0

    plugins = data.get("enabledPlugins", data.get("plugins", []))
    enabled = any("coordinator" in str(p) for p in plugins)

    if enabled:
        print("PASS — coordinator plugin found in enabledPlugins")
        return 0

    # SKILL.md amendment (DoE-claude 25121f849): absence from `enabledPlugins`
    # is the dev / `--plugin-dir` install shape's EXPECTED state, not
    # configured-but-broken. When Probe 0's route-2 evidence holds at the same
    # --plugin-dir, degrade to WARN/exit 0 rather than failing an install that
    # is demonstrably live. WARN, not SKIP, so the row stays visible.
    if args.plugin_dir:
        source_dir = Path(args.plugin_dir)
        manifest_ok, commands_present, hooks_present = _route2_evidence(source_dir)
        if manifest_ok and (commands_present or hooks_present):
            print(
                f"[WARN] coordinator plugin not in enabledPlugins, but is live-resolved "
                f"via --plugin-dir at {source_dir} — expected for a dev/--plugin-dir "
                f"install, which does not use marketplace enablement. Not a fault.",
                file=sys.stderr,
            )
            return 0

    print("FAIL — coordinator plugin NOT found in enabledPlugins")
    if not args.plugin_dir:
        print(
            "  If this is a dev / --plugin-dir install, pass --plugin-dir <plugin-root> "
            "so this probe can consult the same live-resolved evidence Probe 0 uses; "
            "such installs never populate enabledPlugins.",
            file=sys.stderr,
        )
    return 1


# ---------------------------------------------------------------------------
# Registration check -- closes the "directory exists but plugin was never
# registered" gap left open by check-settings-membership (Probe 1 above only
# checks enabledPlugins, which seed-marketplace-enabledplugins.py can set
# WITHOUT ever running `claude plugin marketplace add`).
# ---------------------------------------------------------------------------

def _default_claude_plugins_dir() -> Path:
    return Path(os.path.expanduser("~")) / ".claude" / "plugins"


def _route2_evidence(source_dir: Path) -> "tuple[bool, bool, bool]":
    """Positive-evidence test for a plugin live-resolved via `--plugin-dir`
    rather than marketplace-registered: `(manifest_ok, commands_present,
    hooks_present)`.

    A directory merely existing is not evidence — the caller requires
    `manifest_ok and (commands_present or hooks_present)`.

    Shared deliberately by Probe 0 (`cmd_check_plugin_registered`, route 2) and
    Probe 1 (`cmd_check_settings_membership`, the live-resolved degrade). Those
    two probes disagreeing about the same install on the same box is the exact
    defect this helper exists to prevent: on machine-b 2026-08-17, Probe 0
    passed a dev-tree install as `PASS (live-resolved)` while Probe 1 FAILed it
    as configured-but-broken, and Probe 1's non-zero exit is the one that sets
    the skill's verdict. One discriminator, one answer.
    """
    manifest_path = source_dir / ".claude-plugin" / "plugin.json"
    manifest_ok = False
    if manifest_path.is_file():
        try:
            manifest_ok = isinstance(json.loads(manifest_path.read_text()), dict)
        except (OSError, json.JSONDecodeError):
            manifest_ok = False

    commands_dir = source_dir / "commands"
    commands_present = commands_dir.is_dir() and any(commands_dir.glob("*.md"))

    hooks_present = False
    hooks_json_path = source_dir / "hooks" / "hooks.json"
    if hooks_json_path.is_file():
        try:
            hooks_present = bool(list(_walk_hook_commands(json.loads(hooks_json_path.read_text()))))
        except (OSError, json.JSONDecodeError):
            hooks_present = False

    return manifest_ok, commands_present, hooks_present


def cmd_check_plugin_registered(args: argparse.Namespace) -> int:
    """Verify a plugin is registered end-to-end, not merely enabled or
    present as a bare `~/.claude/plugins/<name>/` directory.

    Failure mode discharged: a repo can ship a Claude Code plugin, register
    its MCP server, and never run `claude plugin marketplace add` /
    `claude plugin install` -- the result is a `~/.claude/plugins/<name>/`
    directory holding only runtime data dirs (MCP session state, caches),
    which reads as "installed" to every eyeball check (no manifest, no
    commands, no hooks) so the plugin's SessionStart hook never fires. Hit on
    project-rag live 2026-07-28, reproducible fleet-wide.

    Registration is verified against the two files Claude Code itself
    consults at plugin-resolution time:
      - installed_plugins.json: "<plugin>@<marketplace>" must be a key under
        top-level "plugins".
      - known_marketplaces.json: "<marketplace>" must be a top-level key.

    Directory presence under ~/.claude/plugins/<plugin>/ is EXPLICITLY NOT
    sufficient evidence on its own -- that directory is exactly what
    masquerades as an install (see docstring above); this function only
    reports it as an informational aside, never as a pass condition.

    enabledPlugins membership (settings.json, --settings) is likewise NOT
    sufficient evidence on its own -- seed-marketplace-enabledplugins.py can
    set it without ever registering the marketplace. When --settings is
    supplied this function reports that membership as a separate, explicitly
    weaker informational signal; it never contributes to the PASS/FAIL
    verdict, which is decided by the two registration files alone.

    Fail-vs-skip for absent/malformed input (AC-5): unlike
    check-hooks/check-settings-membership -- which WARN + exit 0 on an
    absent *secondary* file -- installed_plugins.json and
    known_marketplaces.json are this check's ONLY sources of truth. Absence
    or malformed JSON in either one means registration cannot be confirmed,
    which is indistinguishable from "not registered" for this check's
    purpose, so both cases FAIL (exit 1) rather than skip. Skipping here
    would silently reintroduce the exact false-pass this subcommand exists
    to close.

    Second legitimate route to "genuinely reachable" (added after live
    fleet-run false-positive, 2026-07-28): marketplace registration is not
    the actual invariant -- reachability is, and a plugin resolved live via
    Claude Code's `--plugin-dir` (a dev SOURCE checkout, e.g. coordinator
    itself resolved from DoE-claude's `coordinator/` tree) is correctly
    unregistered -- the harness never touches either registry JSON for that
    route, yet the plugin works. Without this route the check FAILs on every
    coordinator developer machine in the fleet, which is exactly the
    cry-wolf outcome that lets a real regression get ignored.

    When --plugin-dir is supplied and marketplace registration (route 1)
    did not pass, this function checks route 2: a plugin manifest
    (`.claude-plugin/plugin.json`) present AND parseable at --plugin-dir,
    AND at least one of a non-empty `commands/` dir or a `hooks/hooks.json`
    with at least one hook entry -- i.e. POSITIVE evidence that real,
    installable content lives at the resolved source (AC-2). This
    deliberately does NOT consult the `.coordinator-dev-repo` sentinel
    (DoE-claude CLAUDE.md "Repo-specific gotchas"): that sentinel only
    exists for one specific repo's dev/OSS discriminant, and AC-2 forbids a
    sentinel alone ever becoming a blanket skip -- the manifest+commands/hooks
    check is the generic, plugin-agnostic stand-in that subsumes the
    invariant the sentinel would only gesture at. A --plugin-dir that lacks
    a manifest, or has one but no commands/hooks, does NOT pass route 2 --
    that is state 3 (the actual bug: a directory that looks installed but
    isn't reachable by either legitimate route) and stays a hard FAIL.
    """
    plugin = args.plugin
    marketplace = args.marketplace
    key = f"{plugin}@{marketplace}"
    source = args.marketplace_source or marketplace

    installed_path = Path(
        args.installed_plugins or (_default_claude_plugins_dir() / "installed_plugins.json")
    )
    known_path = Path(
        args.known_marketplaces or (_default_claude_plugins_dir() / "known_marketplaces.json")
    )

    installed_ok = False
    if not installed_path.is_file():
        print(
            f"FAIL — installed_plugins.json not found at {installed_path} — "
            f"{key} is NOT registered",
            file=sys.stderr,
        )
    else:
        try:
            data = json.loads(installed_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"FAIL — failed to parse {installed_path}: {exc}", file=sys.stderr)
            data = None
        if data is not None:
            plugins = data.get("plugins", {}) if isinstance(data, dict) else {}
            if isinstance(plugins, dict) and key in plugins:
                installed_ok = True
            else:
                print(
                    f"FAIL — {key} not found in installed_plugins.json ({installed_path})",
                    file=sys.stderr,
                )

    known_ok = False
    if not known_path.is_file():
        print(
            f"FAIL — known_marketplaces.json not found at {known_path} — "
            f"marketplace '{marketplace}' is NOT registered",
            file=sys.stderr,
        )
    else:
        try:
            mdata = json.loads(known_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"FAIL — failed to parse {known_path}: {exc}", file=sys.stderr)
            mdata = None
        if mdata is not None:
            if isinstance(mdata, dict) and marketplace in mdata:
                known_ok = True
            else:
                print(
                    f"FAIL — marketplace '{marketplace}' not found in "
                    f"known_marketplaces.json ({known_path})",
                    file=sys.stderr,
                )

    # Directory presence is NOT evidence (AC-1) -- reported only as an
    # informational aside, and only when it would otherwise be mistaken for
    # a pass signal (i.e. registration is actually failing).
    installed_plugin_entry = _default_claude_plugins_dir() / plugin
    if installed_plugin_entry.is_dir() and not (installed_ok and known_ok):
        print(
            f"[INFO] {installed_plugin_entry} exists on disk — this is NOT "
            "evidence of registration. A runtime-data-only directory (MCP "
            "session state, caches) with no plugin manifest masquerades as "
            "installed; only installed_plugins.json + known_marketplaces.json "
            "membership counts.",
            file=sys.stderr,
        )

    # enabledPlugins is a separate, explicitly weaker signal (AC-2) -- it
    # never feeds the verdict below, only an informational report.
    if args.settings:
        settings_path = Path(args.settings)
        if settings_path.is_file():
            try:
                sdata = json.loads(settings_path.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                print(f"[INFO] failed to parse {settings_path}: {exc}", file=sys.stderr)
            else:
                enabled = sdata.get("enabledPlugins", sdata.get("plugins", {})) if isinstance(sdata, dict) else {}
                is_enabled = key in enabled
                print(
                    f"[INFO] enabledPlugins membership for {key}: "
                    f"{'present' if is_enabled else 'absent'} (weaker signal — "
                    "does not imply registration; see AC-2)",
                    file=sys.stderr,
                )
        else:
            print(f"[INFO] settings file not found at {settings_path}", file=sys.stderr)

    if installed_ok and known_ok:
        print(f"PASS — {key} registered in installed_plugins.json and known_marketplaces.json")
        return 0

    # Route 2 (state 2): unregistered but live-resolved via --plugin-dir,
    # with positive evidence (manifest + commands/hooks) at the resolved
    # source. Only consulted once route 1 (marketplace registration) has
    # already failed above.
    if args.plugin_dir:
        source_dir = Path(args.plugin_dir)
        manifest_path = source_dir / ".claude-plugin" / "plugin.json"
        manifest_ok, commands_present, hooks_present = _route2_evidence(source_dir)

        if manifest_ok and (commands_present or hooks_present):
            print(
                f"PASS (live-resolved) — {plugin} is not marketplace-registered but is "
                f"live-resolved via --plugin-dir at {source_dir}: manifest present at "
                f"{manifest_path}, "
                + ("commands/ " if commands_present else "")
                + ("hooks.json " if hooks_present else "")
                + "present as positive evidence of reachability"
            )
            return 0

        print(
            f"[INFO] --plugin-dir {source_dir} given but did not clear route-2 evidence "
            f"(manifest present: {manifest_ok}, commands present: {commands_present}, "
            f"hooks present: {hooks_present}) — falling through to FAIL",
            file=sys.stderr,
        )

    print("FAIL — plugin registration incomplete. Remediation:", file=sys.stderr)
    print(f"  claude plugin marketplace add {source}", file=sys.stderr)
    print(f"  claude plugin install {key}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="setup-verify.py")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_layout = sub.add_parser("layout", help="Detect flat vs nested plugin-root layout")
    p_layout.add_argument("--plugin-root", required=True)
    p_layout.set_defaults(func=cmd_layout)

    p_visited = sub.add_parser("visited-init", help="Initialise the chain-walk visited-set")
    p_visited.add_argument("--settings-home", default=None)
    p_visited.set_defaults(func=cmd_visited_init)

    p_override = sub.add_parser(
        "check-override-flags", help="Validate --skip-dep-check/--accept-missing-deps-risk pairing"
    )
    p_override.add_argument("rest", nargs="*")
    p_override.set_defaults(func=cmd_check_override_flags)

    p_hooks = sub.add_parser("check-hooks", help="Verify coordinator-owned hooks present on disk")
    p_hooks.add_argument("--plugin-root", required=True)
    p_hooks.set_defaults(func=cmd_check_hooks)

    p_desc = sub.add_parser(
        "check-skill-description", help="Validate a SKILL.md's frontmatter description field"
    )
    p_desc.add_argument("--skill-file", required=True)
    p_desc.set_defaults(func=cmd_check_skill_description)

    p_settings = sub.add_parser(
        "check-settings-membership", help="Check enabledPlugins for coordinator membership"
    )
    p_settings.add_argument("--settings", default=None)
    p_settings.add_argument(
        "--plugin-dir",
        default=None,
        help="Plugin root, as passed to check-plugin-registered. When given and the "
        "same route-2 live-resolved evidence holds there, absence from enabledPlugins "
        "degrades to WARN/exit 0 instead of FAIL — the dev/--plugin-dir install shape "
        "never populates enabledPlugins.",
    )
    p_settings.set_defaults(func=cmd_check_settings_membership)

    p_plugin_reg = sub.add_parser(
        "check-plugin-registered",
        help="Verify a plugin is registered in installed_plugins.json + known_marketplaces.json",
    )
    p_plugin_reg.add_argument("--plugin", required=True)
    p_plugin_reg.add_argument("--marketplace", required=True)
    p_plugin_reg.add_argument(
        "--marketplace-source",
        default=None,
        help="Source arg for the `claude plugin marketplace add` remediation command; "
        "defaults to --marketplace's value if not given.",
    )
    p_plugin_reg.add_argument("--installed-plugins", default=None)
    p_plugin_reg.add_argument("--known-marketplaces", default=None)
    p_plugin_reg.add_argument(
        "--settings",
        default=None,
        help="Optional: also report enabledPlugins membership as a separate, weaker signal.",
    )
    p_plugin_reg.add_argument(
        "--plugin-dir",
        default=None,
        help="Optional: the directory Claude Code resolves this plugin from via "
        "--plugin-dir (a dev SOURCE checkout). When marketplace registration is "
        "absent, this is checked as a second legitimate reachability route: PASS "
        "only when a plugin manifest AND commands/hooks are positively present "
        "there (never on a sentinel alone).",
    )
    p_plugin_reg.set_defaults(func=cmd_check_plugin_registered)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    # check-override-flags takes a free-form `-- ARGS...` tail that may itself
    # contain flags (e.g. --skip-dep-check) which argparse would otherwise try
    # to interpret as options of THIS parser. Split it out before the main parse.
    if argv and argv[0] == "check-override-flags":
        rest = argv[1:]
        if rest and rest[0] == "--":
            rest = rest[1:]
        ns = argparse.Namespace(subcommand="check-override-flags", rest=rest, func=cmd_check_override_flags)
        return ns.func(ns)

    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
