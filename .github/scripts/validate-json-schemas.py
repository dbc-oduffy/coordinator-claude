#!/usr/bin/env python3
"""Validate structure of critical JSON config files."""

import json
import sys
import pathlib


def err(errors: list, file: str, msg: str):
    errors.append(f"{file}: {msg}")


def validate_settings(path: pathlib.Path, errors: list):
    """Validate settings.json structure."""
    name = str(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        err(errors, name, f"invalid JSON: {e}")
        return

    if not isinstance(data, dict):
        err(errors, name, "top level must be an object")
        return

    # enabledPlugins: required, values must be booleans
    plugins = data.get("enabledPlugins")
    if plugins is None:
        err(errors, name, "missing required key 'enabledPlugins'")
    elif not isinstance(plugins, dict):
        err(errors, name, "'enabledPlugins' must be an object")
    else:
        for key, val in plugins.items():
            if not isinstance(val, bool):
                err(errors, name, f"enabledPlugins['{key}'] must be a boolean, got {type(val).__name__}")

    # permissions.deny: optional, but if present must be array of strings
    perms = data.get("permissions")
    if perms is not None:
        if not isinstance(perms, dict):
            err(errors, name, "'permissions' must be an object")
        else:
            deny = perms.get("deny")
            if deny is not None:
                if not isinstance(deny, list):
                    err(errors, name, "'permissions.deny' must be an array")
                else:
                    for i, item in enumerate(deny):
                        if not isinstance(item, str):
                            err(errors, name, f"permissions.deny[{i}] must be a string, got {type(item).__name__}")


def validate_known_marketplaces(path: pathlib.Path, errors: list):
    """Validate known_marketplaces.json structure.

    Expected: object keyed by marketplace name, each value has:
      - source: {source: "github"|"directory", repo?: str, path?: str}
      - installLocation: str
      - lastUpdated: str (ISO 8601)
    """
    name = str(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        err(errors, name, f"invalid JSON: {e}")
        return

    if not isinstance(data, dict):
        err(errors, name, "top level must be an object")
        return

    for mp_name, mp in data.items():
        prefix = f"marketplace '{mp_name}'"
        if not isinstance(mp, dict):
            err(errors, name, f"{prefix}: must be an object")
            continue

        # source
        source = mp.get("source")
        if source is None:
            err(errors, name, f"{prefix}: missing required key 'source'")
        elif not isinstance(source, dict):
            err(errors, name, f"{prefix}: 'source' must be an object")
        else:
            src_type = source.get("source")
            if src_type not in ("github", "directory"):
                err(errors, name, f"{prefix}: source.source must be 'github' or 'directory', got '{src_type}'")
            elif src_type == "github" and not isinstance(source.get("repo"), str):
                err(errors, name, f"{prefix}: source.repo required (string) when source is 'github'")
            elif src_type == "directory" and not isinstance(source.get("path"), str):
                err(errors, name, f"{prefix}: source.path required (string) when source is 'directory'")

        # installLocation
        if not isinstance(mp.get("installLocation"), str):
            err(errors, name, f"{prefix}: missing or invalid 'installLocation' (must be string)")

        # lastUpdated
        if not isinstance(mp.get("lastUpdated"), str):
            err(errors, name, f"{prefix}: missing or invalid 'lastUpdated' (must be string)")


def validate_installed_plugins(path: pathlib.Path, errors: list):
    """Validate installed_plugins.json structure.

    Expected: {version: int, plugins: {key: [array of install records]}}
    Each record has: scope, installPath, version, installedAt, lastUpdated (all strings).
    """
    name = str(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        err(errors, name, f"invalid JSON: {e}")
        return

    if not isinstance(data, dict):
        err(errors, name, "top level must be an object")
        return

    if "version" not in data:
        err(errors, name, "missing required key 'version'")

    plugins = data.get("plugins")
    if plugins is None:
        err(errors, name, "missing required key 'plugins'")
        return
    if not isinstance(plugins, dict):
        err(errors, name, "'plugins' must be an object")
        return

    required_record_fields = ["scope", "installPath", "version", "installedAt", "lastUpdated"]
    for plugin_key, records in plugins.items():
        prefix = f"plugin '{plugin_key}'"
        if not isinstance(records, list):
            err(errors, name, f"{prefix}: value must be an array of install records")
            continue
        for i, record in enumerate(records):
            if not isinstance(record, dict):
                err(errors, name, f"{prefix}[{i}]: must be an object")
                continue
            for field in required_record_fields:
                val = record.get(field)
                if not isinstance(val, str):
                    err(errors, name, f"{prefix}[{i}]: missing or invalid '{field}' (must be string)")


FILES = [
    ("settings.json", validate_settings),
    ("plugins/known_marketplaces.json", validate_known_marketplaces),
    ("plugins/installed_plugins.json", validate_installed_plugins),
]


def main():
    errors = []

    for relpath, validator in FILES:
        path = pathlib.Path(relpath)
        if not path.exists():
            print(f"  {relpath}: skipped (not in repo, likely gitignored)")
            continue
        validator(path, errors)

    if errors:
        print("JSON schema validation FAILED:")
        for e in errors:
            print(f"  {e}")
        return 1

    print("JSON schema validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
