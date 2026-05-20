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
Negative-spec: reader is read-only; no writes, no caching files, no side effects.
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


def _flatten_concern(concern_name: str, data: dict, _prefix: str = "") -> dict:
    """Prefix all keys in a concern file with '<concern_name>.<prefix>'.

    Recursively flattens nested dicts into dotted subkeys so every nested
    table (not just 'versions') is reachable.  Native types are stored as-is
    so _resolve_key's isinstance(val, list) branch handles list→newline
    uniformly at resolve time rather than at flatten time.

    Review: code-reviewer (F2 + F5) — recursive flatten covers arbitrary nested
    tables; storing native types prevents str() at flatten time which drops
    newline-join for arrays.
    """
    result = {}
    base = f"{concern_name}.{_prefix}" if _prefix else f"{concern_name}."
    for k, v in data.items():
        if k == "schema":
            continue  # meta-key, not a user key
        full_key = f"{base}{k}"
        if isinstance(v, dict):
            # Recurse: flatten nested table with dotted subkeys.
            result.update(_flatten_concern(concern_name, v, _prefix=f"{_prefix}{k}." if _prefix else f"{k}."))
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

    # Clean registry dict: remove meta-keys and enforce namespace exclusivity.
    def _clean_registry(data: dict, source_label: str) -> dict:
        cleaned = {}
        for k, v in data.items():
            if k in ("schema", "concerns"):
                continue
            # Check if this key's first segment is a loaded concern's prefix.
            first_seg = k.split(".")[0].lower()
            if first_seg in concern_prefixes:
                print(
                    f"machine-local: warning: key '{k}' in {source_label} "
                    f"belongs to concern namespace '{first_seg}' — "
                    "the concern file wins; this entry is ignored.",
                    file=sys.stderr,
                )
                continue
            # Flatten list values to newline-joined string for keys subcommand,
            # but preserve the raw value type for structured use in layers.
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

    # Registry layers: clean to enforce namespace exclusivity.
    reg_local_clean = {}
    for k, v in registry_local.items():
        if k in ("schema", "concerns"):
            continue
        first_seg = k.split(".")[0].lower()
        if first_seg in concern_prefixes:
            print(
                f"machine-local: warning: key '{k}' in registry.local.toml "
                f"belongs to concern namespace '{first_seg}' — "
                "the concern file wins; this entry is ignored.",
                file=sys.stderr,
            )
            continue
        reg_local_clean[k] = v

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

    parsed = parser.parse_args()

    dispatch = {
        "get": cmd_get,
        "has": cmd_has,
        "keys": cmd_keys,
        "path": cmd_path,
    }
    return dispatch[parsed.command](parsed)


if __name__ == "__main__":
    sys.exit(main())
