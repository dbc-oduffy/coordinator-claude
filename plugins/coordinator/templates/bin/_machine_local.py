#!/usr/bin/env python3
"""
_machine_local.py — implementation of the machine-local registry reader.

Spec backlink: docs/plans/2026-05-19-machine-local-registry.md §4.3
Purpose: Read per-machine key/value config from ~/.claude/machine-local/ TOML
files, following a strict resolution order so operator-set machine-specific
values always outrank shared baselines and env-var escape hatches.

Underscore prefix is intentional — discourages direct invocation.
Users should call `machine-local` (the shell wrapper), not this file.

Resolution order (most-specific first):
  1. <concern>.local.toml  — per-machine concern override
  2. <concern>.toml        — tracked concern baseline
  3. registry.local.toml   — per-machine top-level overrides
  4. registry.toml         — tracked top-level baseline
  5. MACHINE_LOCAL_<KEY>   — env escape hatch (dots → underscores, uppercased)
  6. --default             — caller-supplied fallback
  7. exit 1                — not found

Negative-spec: env does NOT outrank registry layers (the Director of Engineering F1 inversion).
Negative-spec: missing .local files are not errors — treated as empty.
Negative-spec: no regex fallback, no PyYAML, no tomli — stdlib tomllib only.
Negative-spec: reader is read-only for GET path; SET path writes only registry.local.toml
              (or registry.toml with --global). SET never touches concern files.

All consumers — including the ergonomic wrapper ``claude_machine_local.py`` —
shell out to the ``machine-local`` CLI. Direct in-process import is the
dual-identity anti-pattern (docs/wiki/dual-identity-module-hazard.md and
docs/wiki/machine-local-registry.md §8(a)); shell-out is the only contract.
"""

import sys
import os
import argparse

# Hard requirement: fail loud on Python < 3.11 rather than silently degrade.
# coordinator requires Python 3.11+ for TOML parsing via stdlib tomllib.
if sys.version_info < (3, 11):
    print(
        "coordinator requires Python 3.11+ for TOML parsing; "
        "upgrade Python or pin tomli backport in coordinator's dev deps.",
        file=sys.stderr,
    )
    sys.exit(1)

import tomllib  # stdlib, 3.11+

SCHEMA_EXPECTED = 1


def _registry_dir() -> str:
    """Return the path to the machine-local registry directory.

    Honours MACHINE_LOCAL_REGISTRY_DIR for test isolation.
    Falls back to ~/.claude/machine-local/.
    """
    override = os.environ.get("MACHINE_LOCAL_REGISTRY_DIR")
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".claude", "machine-local")


def _load_toml(path: str) -> dict:
    """Load a TOML file and return its contents as a dict.

    Errors loudly on malformed TOML — no silent degradation.
    Returns empty dict when file is absent (missing .local files are fine).
    """
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        print(
            f"machine-local: malformed TOML in {path}: {exc}\n"
            "Remediation: fix the TOML syntax in the file above.",
            file=sys.stderr,
        )
        sys.exit(1)


def _warn_schema(data: dict, path: str) -> None:
    """Emit a warning if schema version doesn't match expected."""
    schema_val = data.get("schema")
    if schema_val is not None and schema_val != SCHEMA_EXPECTED:
        print(
            f"machine-local: warning: {path} declares schema={schema_val}, "
            f"reader expects schema={SCHEMA_EXPECTED}. "
            "Some keys may not be read correctly.",
            file=sys.stderr,
        )


def _flatten_nested(data: dict, _prefix: str = "") -> dict:
    """Recursively flatten nested dicts in a registry file into dotted keys.

    Companion to _flatten_concern, but for registry.toml / registry.local.toml
    where there is no concern-name prefix (the file is the root namespace).
    This makes natural TOML table syntax (``[unreal]\\ninstall_root = "..."``)
    or dotted-key syntax (``unreal.install_root = "..."``) visible to
    ``machine-local get`` for keys whose namespace is NOT promoted to a
    concern file. Belt-and-suspenders: keeps the registry reader robust to
    hand-edits and to namespaces not yet (or no longer) promoted to concerns.
    """
    result = {}
    for k, v in data.items():
        if k in ("schema", "concerns"):
            continue
        full_key = f"{_prefix}{k}"
        if isinstance(v, dict):
            result.update(_flatten_nested(v, _prefix=f"{full_key}."))
        else:
            result[full_key] = v
    return result


def _flatten_concern(concern_name: str, data: dict, _prefix: str = "") -> dict:
    """Prefix all keys in a concern file with '<concern_name>.<prefix>'.

    Recursively flattens nested dicts into dotted subkeys so every nested
    table (not just 'versions') is reachable.  Native types are stored as-is
    so _resolve_key's isinstance(val, list) branch handles list→newline
    uniformly at resolve time rather than at flatten time.

    Self-named top-level table elision: when the concern file uses
    ``[<concern_name>]`` as the top-level table (e.g. ``[unreal]`` inside
    ``unreal.local.toml``), the matching prefix is NOT doubled. The contents
    of that table are merged into the concern's flat namespace. This lets
    operators write the natural TOML form (``[unreal]\\ninstall_root = "..."``)
    and have it resolve as ``unreal.install_root`` instead of
    ``unreal.unreal.install_root``. Top-level keys placed directly (without
    the self-named table) still work — they are auto-prefixed by concern_name.

    Recursive flatten ensures arbitrary nesting is reachable. Native types (not
    str()) preserved so list→newline join at resolve time handles arrays uniformly.
    """
    result = {}
    # Strip sentinel prefix ("\x00") before using in key construction.
    # The sentinel is used only to disable self-named-table elision on
    # recursive calls — it must not appear in the output key strings.
    effective_prefix = _prefix if _prefix != "\x00" else ""
    base = f"{concern_name}.{effective_prefix}" if effective_prefix else f"{concern_name}."
    for k, v in data.items():
        if k == "schema":
            continue  # meta-key, not a user key
        # Self-named top-level table elision: at the root of the concern file
        # (_prefix=""), a sub-table named after the concern itself collapses
        # so that [unreal] inside unreal.local.toml produces unreal.<key>, not
        # unreal.unreal.<key>. Below the root, table names are kept as-is —
        # nested [unreal.versions] etc. still produce the natural dotted path.
        # Sentinel prefix ("\x00") on the recursive call ensures the elision
        # condition (not _prefix) is False for all nested levels — prevents
        # double-elision if a hand-crafted file has [unreal]\nunreal = {...}.
        if not _prefix and isinstance(v, dict) and k == concern_name:
            result.update(_flatten_concern(concern_name, v, _prefix="\x00"))
            continue
        full_key = f"{base}{k}"
        if isinstance(v, dict):
            # Recurse: flatten nested table with dotted subkeys.
            result.update(_flatten_concern(concern_name, v, _prefix=f"{effective_prefix}{k}." if effective_prefix else f"{k}."))
        else:
            # Store native type; _resolve_key handles list→newline join.
            result[full_key] = v
    return result


def _build_resolution_layers(reg_dir: str) -> list[dict]:
    """Build the ordered list of dicts representing the resolution stack.

    Spec: resolution order is concern.local → concern → registry.local → registry.
    Returns layers in priority order (index 0 = highest priority).
    """
    reg_path = os.path.join(reg_dir, "registry.toml")
    reg_local_path = os.path.join(reg_dir, "registry.local.toml")

    registry = _load_toml(reg_path)
    registry_local = _load_toml(reg_local_path)

    if registry:
        _warn_schema(registry, reg_path)
    if registry_local:
        _warn_schema(registry_local, reg_local_path)

    # Concern-namespace exclusivity (the Director of Engineering F5): when a concern is listed in
    # `concerns`, keys in registry.toml whose first segment matches the concern
    # prefix emit a warning and are dropped from the registry layer.
    concerns_list = registry.get("concerns", [])
    if not isinstance(concerns_list, list):
        concerns_list = []

    # Build set of concern prefixes for namespace exclusivity check.
    concern_prefixes = {c.lower() for c in concerns_list}

    # Clean registry dict: flatten nested dicts to dotted keys, drop meta-keys,
    # then enforce namespace exclusivity on the flattened key set. Flattening
    # first lets natural TOML table syntax (`[unreal]\ninstall_root = "..."`)
    # and dotted-key syntax (`unreal.install_root = "..."`) both produce the
    # canonical dotted key the resolver looks up. Belt-and-suspenders: concern
    # files own promoted namespaces, but registry hand-edits or future
    # namespaces should still resolve cleanly.
    def _clean_registry(data: dict, source_label: str) -> dict:
        flat = _flatten_nested(data)
        cleaned = {}
        for k, v in flat.items():
            first_seg = k.split(".")[0].lower()
            if first_seg in concern_prefixes:
                print(
                    f"machine-local: warning: key '{k}' in {source_label} "
                    f"belongs to concern namespace '{first_seg}' — "
                    "the concern file wins; this entry is ignored.",
                    file=sys.stderr,
                )
                continue
            cleaned[k] = v
        return cleaned

    # Load concern layers (highest priority first within each concern).
    concern_local_layers = []
    concern_base_layers = []

    for concern in concerns_list:
        concern = str(concern)
        c_path = os.path.join(reg_dir, f"{concern}.toml")
        c_local_path = os.path.join(reg_dir, f"{concern}.local.toml")

        c_data = _load_toml(c_path)
        c_local_data = _load_toml(c_local_path)

        if c_data:
            _warn_schema(c_data, c_path)
        if c_local_data:
            _warn_schema(c_local_data, c_local_path)

        if c_local_data:
            concern_local_layers.append(_flatten_concern(concern, c_local_data))
        if c_data:
            concern_base_layers.append(_flatten_concern(concern, c_data))

    # Registry layers: flatten + enforce namespace exclusivity via the same helper.
    reg_local_clean = _clean_registry(registry_local, "registry.local.toml")
    reg_clean = _clean_registry(registry, "registry.toml")

    # Priority order: concern.local > concern > registry.local > registry
    layers = concern_local_layers + concern_base_layers + [reg_local_clean, reg_clean]
    return layers


def _resolve_key(key: str, layers: list[dict]) -> str | None:
    """Walk resolution layers and return first match, or None."""
    for layer in layers:
        if key in layer:
            val = layer[key]
            # TOML arrays are stored as Python lists; join with newlines.
            if isinstance(val, list):
                return "\n".join(str(i) for i in val)
            return str(val)
    return None


def _env_key(key: str) -> str:
    """Convert a dotted key to its env-var override name."""
    return "MACHINE_LOCAL_" + key.upper().replace(".", "_")


def _all_keys(layers: list[dict]) -> list[str]:
    """Return deduplicated, ordered list of all keys visible across layers."""
    seen = {}
    for layer in layers:
        for k in layer:
            if k not in seen:
                seen[k] = True
    return list(seen.keys())


def cmd_get(args: argparse.Namespace) -> int:
    """Implement: machine-local get <key> [--default <v>]"""
    reg_dir = _registry_dir()
    layers = _build_resolution_layers(reg_dir)
    key = args.key

    # Walk resolution order: concern.local → concern → registry.local → registry
    val = _resolve_key(key, layers)

    # Env override is BELOW all .toml layers (the Director of Engineering F1 / plan §4.3).
    if val is None:
        env_val = os.environ.get(_env_key(key))
        if env_val is not None:
            val = env_val

    if val is not None:
        print(val)
        return 0

    if args.default is not None:
        print(args.default)
        return 0

    print(f"machine-local: key '{key}' not found in registry", file=sys.stderr)
    return 1


def cmd_has(args: argparse.Namespace) -> int:
    """Implement: machine-local has <key> — exit 0 if set, 1 if not (no output)."""
    reg_dir = _registry_dir()
    layers = _build_resolution_layers(reg_dir)
    key = args.key

    val = _resolve_key(key, layers)
    if val is None:
        val = os.environ.get(_env_key(key))

    return 0 if val is not None else 1


def cmd_keys(args: argparse.Namespace) -> int:
    """Implement: machine-local keys — list all known keys, one per line."""
    reg_dir = _registry_dir()
    layers = _build_resolution_layers(reg_dir)
    for k in _all_keys(layers):
        print(k)
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    """Implement: machine-local path — print absolute path to active registry.toml."""
    reg_dir = _registry_dir()
    abs_path = os.path.abspath(os.path.join(reg_dir, "registry.toml"))
    print(abs_path)
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    """Implement: machine-local set <key> <value> [--global] [--dry-run]

    Writes a string key=value pair to registry.local.toml (default) or
    registry.toml (--global).  Atomic, idempotent, concern-aware.

    Use this instead of editing registry files by hand — direct edits are
    fragile: they do not reproduce on reinstall or transfer to a new machine,
    and may be clobbered by a concurrent session.
    """
    import re
    import datetime

    reg_dir = _registry_dir()
    target_file = "registry.toml" if args.write_global else "registry.local.toml"
    target_path = os.path.join(reg_dir, target_file)

    key = args.key
    value = args.value
    dry_run = args.dry_run

    # Refuse to write keys that belong to a loaded concern namespace.
    # Union concerns from both registry.toml and registry.local.toml so that
    # an operator with concerns declared only in registry.local.toml gets the
    # same guard as one using registry.toml — mirrors _build_resolution_layers.
    reg_path = os.path.join(reg_dir, "registry.toml")
    reg_local_path = os.path.join(reg_dir, "registry.local.toml")
    concerns_set = set()
    for p in (reg_path, reg_local_path):
        if os.path.exists(p):
            d = _load_toml(p)
            for c in d.get("concerns", []):
                concerns_set.add(str(c).lower())
    if concerns_set:
        first_seg = key.split(".")[0].lower()
        if first_seg in concerns_set:
            c_match = first_seg
            print(
                f"machine-local: key '{key}' belongs to concern namespace '{c_match}'. "
                f"Write to {c_match}.local.toml instead (that concern file owns this namespace).",
                file=sys.stderr,
            )
            return 1

    # Read existing content or seed a new file.
    if os.path.exists(target_path):
        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()
        is_new = False
    else:
        is_new = True
        content = (
            f"# {target_file}  (created by `machine-local set`)\n"
            "#\n"
            "# WARNING: Use `machine-local set <key> <value>` to add or change values.\n"
            "# Direct hand-edits are fragile: they do not reproduce on reinstall and\n"
            "# will not transfer automatically to a new machine.\n"
            "schema = 1\n"
        )

    date_tag = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Find and replace an existing quoted key assignment (either basic-string or
    # literal-string form), or append if absent. The pattern matches either form
    # so that operators upgrading from the old basic-string writer shape get an
    # in-place replacement (not a duplicate second line) on the first post-upgrade set.
    # Matches:  "key.name"   =   "old-value"  OR  'old-value'  # optional trailing comment
    #   groups: (prefix up to opening quote of value)(trailing whitespace+comment)
    pattern = re.compile(
        r'^(\s*"' + re.escape(key) + r'"\s*=\s*)(?:"[^"]*"|\'[^\']*\')([ \t]*(?:#[^\n]*)?)',
        re.MULTILINE,
    )

    # Refuse to write values containing a single quote — TOML literal strings
    # (single-quoted) have no escape mechanism. This matches the holodeck
    # write_unreal_concern.py policy: refuse rather than guess.
    if "'" in value:
        print(
            f"machine-local: refusing to write value containing single quote: {value!r}. "
            "Literal-string TOML has no escape for single quote.",
            file=sys.stderr,
        )
        return 1

    value_literal = f"'{value}'"  # TOML literal string (no escape processing)

    if pattern.search(content):
        # Lambda avoids Python 3.12+ re.PatternError on bare \d, \U, \e etc. in
        # f-string template replacements that re.sub would otherwise interpret
        # as bad backreferences.
        new_content = pattern.sub(
            lambda m: f"{m.group(1)}{value_literal}{m.group(2)}",
            content,
        )
        action = "updated"
    else:
        section_pat = re.compile(r"^\[", re.MULTILINE)
        m = section_pat.search(content)
        new_line = f'"{key}" = {value_literal}  # set {date_tag}\n'
        if m:
            insert_at = m.start()
            new_content = content[:insert_at].rstrip("\n") + "\n" + new_line + "\n" + content[insert_at:]
        else:
            new_content = content.rstrip("\n") + "\n" + new_line
        action = "added"

    if dry_run:
        print(f"[dry-run] would {action} {key!r} = {value!r} in {target_path}")
        return 0

    # Atomic write via tmp + rename.
    tmp_path = target_path + f".tmp.{os.getpid()}"
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        if not is_new:
            try:
                os.chmod(tmp_path, os.stat(target_path).st_mode)
            except OSError:
                pass
        os.replace(tmp_path, target_path)
    except Exception as exc:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        print(f"machine-local: write failed: {exc}", file=sys.stderr)
        return 1

    print(f"machine-local: {action} {key!r} = {value!r} in {target_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="machine-local",
        description="Read per-machine config from ~/.claude/machine-local/",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # get
    get_p = subparsers.add_parser("get", help="Print value for a key")
    get_p.add_argument("key", help="Dotted key name (e.g. repos.claude_unreal_holodeck)")
    get_p.add_argument("--default", metavar="VALUE", default=None,
                       help="Value to print if key is missing (always exits 0)")

    # has
    has_p = subparsers.add_parser("has", help="Exit 0 if key is set, 1 if not")
    has_p.add_argument("key", help="Dotted key name")

    # keys
    subparsers.add_parser("keys", help="List all known keys, one per line")

    # path
    subparsers.add_parser("path", help="Print absolute path to active registry.toml")

    # set
    set_p = subparsers.add_parser(
        "set",
        help="Write a key=value pair to the registry (prefer over hand-editing)",
    )
    set_p.add_argument("key", help="Dotted key (e.g. repos.project_rag)")
    set_p.add_argument("value", help="String value to set")
    set_p.add_argument(
        "--global",
        dest="write_global",
        action="store_true",
        help="Write to registry.toml (tracked/shared) instead of registry.local.toml (gitignored/per-machine)",
    )
    set_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without making changes",
    )

    parsed = parser.parse_args()

    dispatch = {
        "get": cmd_get,
        "has": cmd_has,
        "keys": cmd_keys,
        "path": cmd_path,
        "set": cmd_set,
    }
    return dispatch[parsed.command](parsed)


if __name__ == "__main__":
    sys.exit(main())
