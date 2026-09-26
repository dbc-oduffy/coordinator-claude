# guard-not-a-hook-entrypoint
"""Stdlib-only, static hook-plane probe: settings delivery plus plugin delivery,
every bootstrap/script path resolved against disk.

Never raises. Every broken link (an unreadable file, malformed JSON, a missing
install record, an absent bootstrap script) becomes a recorded `reason` and/or
an entry in `missing_files` instead of an exception -- callers (a SessionStart
hook, a diagnostic) can trust this module not to crash the calling process.

`armed` is a STATIC resolvability predicate -- every named bootstrap/script
path exists on disk -- not proof that a guard actually fires at runtime. An
interpreter missing at spawn time, or a hook that times out, is invisible to
this probe.
"""

from __future__ import annotations

import json
from pathlib import Path

_GUARD_EVENTS = frozenset({"PreToolUse", "PostToolUse"})

#: matches `_COORDINATOR_MARKERS` in `count_coordinator_hooks`'s caller sense --
#: the same marker set the settings-side detector this module absorbs used.
_COORDINATOR_MARKERS = ("coordinator", "guard-", "guard_")

#: A script file's recognized extensions inside a hook command or argument.
_SCRIPT_EXTENSIONS = (".py", ".sh", ".mjs", ".js")


def _load_json_dict(path: Path) -> dict:
    """Best-effort load of `path` as a JSON object. Never raises: an absent
    file, unreadable file, or malformed/non-dict JSON all resolve to `{}`."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def count_coordinator_hooks(path: Path) -> int:
    """Count coordinator-marked hook entries on PreToolUse/PostToolUse in the
    settings file at `path`. Absorbs the prior settings-only detector's rule
    verbatim so callers relying on that count keep the same answer."""
    data = _load_json_dict(path)
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return 0
    found = 0
    for event, matchers in hooks.items():
        if event not in _GUARD_EVENTS:
            continue
        if not isinstance(matchers, list):
            continue
        for matcher in matchers:
            if not isinstance(matcher, dict):
                continue
            for hook in matcher.get("hooks") or []:
                if not isinstance(hook, dict):
                    continue
                command = hook.get("command")
                if not isinstance(command, str):
                    continue
                if any(marker in command for marker in _COORDINATOR_MARKERS):
                    found += 1
    return found


def _shlex_pieces(token: str) -> list:
    """`token` split on whitespace the way a shell would -- falls back to a
    plain whitespace split on anything unparseable rather than raising."""
    import shlex

    try:
        return shlex.split(token, posix=True)
    except ValueError:
        return token.split()


def _script_tail(piece: str) -> "str | None":
    """The `<dir>/<file>` tail of `piece` if it names a script file, else None."""
    normalized = piece.replace("\\", "/").strip("'\"")
    if not normalized.endswith(_SCRIPT_EXTENSIONS):
        return None
    tail = "/".join(normalized.split("/")[-2:])
    return tail or None


def _settings_enabled_key(settings: dict) -> "str | None":
    """The `enabledPlugins` key whose plugin name (the part before `@`) is
    `coordinator` and whose value is `True`, matching whatever marketplace
    names the rest of the key. `None` if no such key is enabled."""
    enabled = settings.get("enabledPlugins")
    if not isinstance(enabled, dict):
        return None
    for key, value in enabled.items():
        if not isinstance(key, str) or value is not True:
            continue
        if key.split("@", 1)[0] == "coordinator":
            return key
    return None


def _project_disables(project_dir: Path, key: str) -> bool:
    """Whether a project-level settings file sets `enabledPlugins[key]` to
    `False`, overriding the config-level enablement."""
    for rel in ("settings.json", "settings.local.json"):
        settings = _load_json_dict(project_dir / ".claude" / rel)
        enabled = settings.get("enabledPlugins")
        if isinstance(enabled, dict) and enabled.get(key) is False:
            return True
    return False


def _resolve_install_path(config_dir: Path, key: str) -> "tuple[str | None, str]":
    """`(installPath, reason)` for the installed-plugin record keyed `key` in
    `<config_dir>/plugins/installed_plugins.json`. `installPath` is `None` on
    any failure, with `reason` naming it."""
    manifest = config_dir / "plugins" / "installed_plugins.json"
    data = _load_json_dict(manifest)
    plugins = data.get("plugins")
    records = plugins.get(key) if isinstance(plugins, dict) else None
    if not isinstance(records, list):
        return None, f"no installed-plugin record names an installPath for {key} ({manifest})"
    for record in records:
        if isinstance(record, dict) and record.get("installPath"):
            return record["installPath"], ""
    return None, f"no installed-plugin record names an installPath for {key} ({manifest})"


def _hooks_json_delivery(install_path: str) -> dict:
    """Whether `<install_path>/hooks/hooks.json` delivers PreToolUse/PostToolUse
    hooks with every `${CLAUDE_PLUGIN_ROOT}`-prefixed token resolving under
    `install_path`.

    Returns a dict with `armed`, `event_count` (guard-event hook entries),
    `missing_files`, `reason`.
    """
    result = {"armed": False, "event_count": 0, "missing_files": [], "reason": ""}
    manifest = Path(install_path) / "hooks" / "hooks.json"
    data = _load_json_dict(manifest)
    hooks = data.get("hooks")
    if not isinstance(hooks, dict) or not hooks:
        result["reason"] = f"{manifest} registers no hook event"
        return result

    referenced: set = set()
    event_count = 0
    for event, groups in hooks.items():
        if event not in _GUARD_EVENTS:
            continue
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict):
                continue
            for hook in group.get("hooks") or []:
                if not isinstance(hook, dict):
                    continue
                event_count += 1
                if hook.get("type") == "http":
                    continue
                args = hook.get("args") if isinstance(hook.get("args"), list) else []
                for token in [hook.get("command"), *args]:
                    if not isinstance(token, str):
                        continue
                    for piece in _shlex_pieces(token):
                        normalized = piece.replace("\\", "/")
                        if normalized.startswith("${CLAUDE_PLUGIN_ROOT}/"):
                            rel = normalized[len("${CLAUDE_PLUGIN_ROOT}/"):]
                            if _script_tail(rel):
                                referenced.add(rel)

    result["event_count"] = event_count
    if event_count == 0:
        result["reason"] = f"{manifest} registers no PreToolUse/PostToolUse hook"
        return result

    missing = sorted(rel for rel in referenced if not (Path(install_path) / rel).is_file())
    result["missing_files"] = missing
    if missing:
        result["reason"] = f"{manifest} names {len(missing)} absent file(s), e.g. {missing[0]}"
        return result

    result["armed"] = True
    result["reason"] = f"delivers {event_count} guard hook(s) from {manifest}"
    return result


def _plugin_delivery(config_dir: Path, project_dir: Path, plugin_dir: "Path | None") -> dict:
    """The plugin-delivery leg of the three-link walk. When `plugin_dir` is
    given (a `--plugin-dir` launch), it IS the plugin surface and the
    enablement/install-record links are skipped."""
    if plugin_dir is not None:
        return _hooks_json_delivery(str(plugin_dir))

    config_settings = _load_json_dict(config_dir / "settings.json")
    key = _settings_enabled_key(config_settings)
    if key is None:
        return {"armed": False, "event_count": 0, "missing_files": [], "reason": "coordinator plugin not enabled in config settings.json"}

    if _project_disables(project_dir, key):
        return {"armed": False, "event_count": 0, "missing_files": [], "reason": f"{key} disabled by project settings"}

    install_path, reason = _resolve_install_path(config_dir, key)
    if install_path is None:
        return {"armed": False, "event_count": 0, "missing_files": [], "reason": reason}

    return _hooks_json_delivery(install_path)


def hook_plane_verdict(config_dir: Path, project_dir: Path, plugin_dir: "Path | None" = None) -> dict:
    """The whole static hook-plane verdict: settings delivery plus plugin
    delivery, resolved against disk. Never raises.

    Returns a dict: `armed` (bool), `delivery` ("settings" | "plugin" | "both"
    | "none"), `guard_event_count` (int), `missing_files` (list[str]),
    `reason` (str).
    """
    settings_paths = [
        Path(config_dir) / "settings.json",
        Path(project_dir) / ".claude" / "settings.json",
        Path(project_dir) / ".claude" / "settings.local.json",
    ]
    settings_count = sum(count_coordinator_hooks(p) for p in settings_paths)
    settings_armed = settings_count > 0

    plugin = _plugin_delivery(Path(config_dir), Path(project_dir), plugin_dir)
    plugin_armed = plugin["armed"]

    guard_event_count = settings_count + plugin["event_count"]
    missing_files = list(plugin["missing_files"])

    if settings_armed and plugin_armed:
        delivery = "both"
    elif settings_armed:
        delivery = "settings"
    elif plugin_armed:
        delivery = "plugin"
    else:
        delivery = "none"

    armed = delivery != "none" and not missing_files

    if delivery == "none":
        reason = f"no delivery: settings ({settings_count} hook(s)); plugin: {plugin['reason']}"
    elif missing_files:
        reason = plugin["reason"]
    else:
        parts = []
        if settings_armed:
            parts.append(f"settings ({settings_count} hook(s))")
        if plugin_armed:
            parts.append(plugin["reason"])
        reason = "; ".join(parts)

    return {
        "armed": armed,
        "delivery": delivery,
        "guard_event_count": guard_event_count,
        "missing_files": missing_files,
        "reason": reason,
    }
