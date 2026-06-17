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
import re
import datetime

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


def _build_header_pats(prefix_parts):
    """Build (header_pat, aot_pat) for a given table prefix.

    # Review: code-reviewer (F1) — hoisted from inner closures in both
    # _locate_existing_definition and _locate_existing_array_span to eliminate
    # verbatim duplication. Both locators call this module-level function.
    """
    table_path = ".".join(prefix_parts)
    # Review: code-reviewer (F1) — OR bare-key and quoted-segment forms.
    quoted_segs = r'\s*\.\s*'.join(f'"{re.escape(p)}"' for p in prefix_parts)
    h_pat = re.compile(
        r"^\[\s*(?:" + re.escape(table_path) + r"|" + quoted_segs + r")\s*\][ \t]*(?:#[^\n]*)?$",
        re.MULTILINE,
    )
    # Review: code-reviewer (F7) — detect [[table.path]] array-of-tables.
    aot_pat = re.compile(
        r"^\[\[\s*(?:" + re.escape(table_path) + r"|" + quoted_segs + r")\s*\]\][ \t]*(?:#[^\n]*)?$",
        re.MULTILINE,
    )
    return h_pat, aot_pat


def _locate_existing_definition(content: str, key: str) -> dict | None:
    """Find an existing definition of `key` in TOML content.

    Returns a dict describing how the key is currently defined, or None if no
    matching structure exists. Three shapes:

      - {"kind": "flat", "match": <re.Match>}
          Found as `"key.with.dots" = "value"` anywhere in the file (the form
          machine-local set has historically written).
      - {"kind": "table-leaf", "leaf_match": <re.Match>, "abs_start": int,
         "abs_end": int}
          Found as a bare-leaf assignment inside an existing `[table.path]`
          header (the form natural TOML uses for grouped config — and the form
          that triggered the 2026-05-23 duplicate-write bug when set only knew
          about the flat shape).
      - {"kind": "table-header-only", "section_start": int, "section_end": int,
         "leaf_path": str}
          The `[table.path]` header exists but the leaf is absent inside it.
          cmd_set inserts the new leaf into the existing section body — a flat
          append below subsequent `[other.section]` headers would be a TOML
          parse error.
      - {"kind": "array-of-tables-detected", "table_path": str}
          The key's table path is defined as an array-of-tables ([[table.path]]).
          cmd_set cannot modify this shape — surface an actionable error.

    The search tries the longest table-path prefix first so that, for a key
    like `a.b.c.d`, it prefers an existing `[a.b.c]\nd = …` over `[a.b]\nc.d = …`
    if both exist (the registry only uses one form per key in practice).
    """
    # Review: code-reviewer (F11) — re and datetime moved to module-level imports.

    flat_pat = re.compile(
        r'^(\s*"' + re.escape(key) + r'"\s*=\s*)(?:"[^"]*"|\'[^\']*\')([ \t]*(?:#[^\n]*)?)',
        re.MULTILINE,
    )
    fm = flat_pat.search(content)
    if fm:
        return {"kind": "flat", "match": fm}

    parts = key.split(".")
    next_section_pat = re.compile(r"^\[", re.MULTILINE)

    # Review: code-reviewer (F2) — two-pass approach: first pass finds table-leaf
    # matches (longest prefix first); second pass finds table-header-only matches.
    # This prevents returning table-header-only for [a.b.c] when [a.b] already
    # has c.d = "..." as a dotted-leaf assignment inside it.

    # Pass 1: look for table-leaf matches only (longest prefix first).
    for i in range(len(parts) - 1, 0, -1):
        prefix_parts = parts[:i]
        leaf_path = ".".join(parts[i:])
        h_pat, aot_pat = _build_header_pats(prefix_parts)
        # Array-of-tables check is done in pass 1 so it still exits early.
        if aot_pat.search(content):
            return {"kind": "array-of-tables-detected", "table_path": ".".join(prefix_parts)}
        hm = h_pat.search(content)
        if not hm:
            continue
        section_start = hm.end()
        nm = next_section_pat.search(content, section_start)
        section_end = nm.start() if nm else len(content)
        section_body = content[section_start:section_end]
        leaf_pat = re.compile(
            r"^(\s*" + re.escape(leaf_path) + r"\s*=\s*)(?:\"[^\"]*\"|'[^']*')([ \t]*(?:#[^\n]*)?)",
            re.MULTILINE,
        )
        leaf_m = leaf_pat.search(section_body)
        if leaf_m:
            return {
                "kind": "table-leaf",
                "leaf_match": leaf_m,
                "abs_start": section_start + leaf_m.start(),
                "abs_end": section_start + leaf_m.end(),
            }

    # Pass 2: look for table-header-only matches (longest prefix first).
    for i in range(len(parts) - 1, 0, -1):
        prefix_parts = parts[:i]
        leaf_path = ".".join(parts[i:])
        h_pat, _aot = _build_header_pats(prefix_parts)
        hm = h_pat.search(content)
        if not hm:
            continue
        section_start = hm.end()
        nm = next_section_pat.search(content, section_start)
        section_end = nm.start() if nm else len(content)
        return {
            "kind": "table-header-only",
            "section_start": section_start,
            "section_end": section_end,
            "leaf_path": leaf_path,
        }

    return None


def _locate_existing_array_span(content: str, key: str) -> dict | None:
    """Find an existing flat-array definition of `key` in TOML content.

    Spec backlink: docs/plans/2026-06-17-publish-targets-machine-local-migration.md § C1
    Purpose: Locate the byte span of an existing multi-line flat array assignment so
    array-append / array-set can replace the whole span atomically.

    The array-write commands (array-append / array-set) only write and read
    quoted-dotted-key multi-line flat arrays:
        "publish.targets" = [
          'row1',
          'row2',
        ]
    This function detects that shape plus the degenerate single-line / empty forms.

    Returns a dict on match:
        {"kind": "flat-array", "span_start": int, "span_end": int,
         "comment_start": int | None}
    where span_start..span_end covers the `"key" = [\n...\n]` block (plus the
    trailing newline, if any), and comment_start, if not None, points to the start
    of a provenance-comment line immediately above the array assignment (preserved
    on replace per F5).

    Returns None if no array assignment is found for this key (caller then creates
    one fresh).

    Uses module-level _build_header_pats (shared with _locate_existing_definition):
    if the key's table path appears as [[array-of-tables]], this function returns
    {"kind": "array-of-tables-detected", "table_path": str} so the caller can emit
    a specific error.

    Negative-spec: does NOT handle inline-table form (`key = {...}`) — the caller
    detects that via the round-trip pre-check (same as cmd_set's inline-table path).
    """
    # Review: code-reviewer (F4) — removed dead next_section_pat local (unused in this
    # function) and removed the inner _build_header_pats closure (now module-level per F1).
    parts = key.split(".")

    # Check for array-of-tables collision on the full key and any prefix.
    # [[publish.targets]] means the key itself is an array-of-tables table path.
    # [[publish]] with targets as a leaf would also be a collision (a prefix match).
    for i in range(len(parts), 0, -1):
        prefix_parts = parts[:i]
        _, aot_pat = _build_header_pats(prefix_parts)
        if aot_pat.search(content):
            return {"kind": "array-of-tables-detected", "table_path": ".".join(prefix_parts)}

    # Match the flat quoted-dotted-key array form:
    #   "key.with.dots" = [
    #     'row1',
    #     ...
    #   ]
    # The opening bracket may be on the same line or the closing may be on the same
    # line (degenerate []). We match from the `"key"` assignment to the closing `]`.
    array_open_pat = re.compile(
        r'^(\s*"' + re.escape(key) + r'"\s*=\s*\[)',
        re.MULTILINE,
    )
    m = array_open_pat.search(content)
    if not m:
        return None

    # Find the closing `]` that matches the opening `[`.
    open_pos = m.start() + m.group(0).index("[")
    depth = 0
    close_pos = None
    for i, ch in enumerate(content[open_pos:], start=open_pos):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                close_pos = i
                break
    if close_pos is None:
        # Malformed (unclosed bracket) — let the round-trip check catch it.
        return None

    # span_end: include the trailing newline after `]` if present.
    span_start = m.start()
    span_end = close_pos + 1
    if span_end < len(content) and content[span_end] == "\n":
        span_end += 1

    # Detect a provenance comment immediately above the assignment (F5).
    comment_start = None
    line_before_start = content.rfind("\n", 0, m.start())
    if line_before_start != -1:
        prev_line_start = content.rfind("\n", 0, line_before_start)
        if prev_line_start == -1:
            prev_line_start = 0
        else:
            prev_line_start += 1
        prev_line = content[prev_line_start:line_before_start]
        if prev_line.strip().startswith("#"):
            comment_start = prev_line_start

    return {
        "kind": "flat-array",
        "span_start": span_start,
        "span_end": span_end,
        "comment_start": comment_start,
    }


def _reject_single_quote_element(element: str) -> bool:
    """Return True (reject) if element contains a single quote.

    TOML literal strings (single-quoted) have no escape mechanism.
    Negative-spec: no fallback encoding — refuse rather than guess.
    """
    return "'" in element


def _build_array_content(key: str, elements: list[str], date_tag: str,
                         provenance_comment: str | None = None) -> str:
    """Render a quoted-dotted-key multi-line flat TOML array block.

    Write shape per spec:
        # array-append <date>
        "publish.targets" = [
          'row1',
          'row2',
        ]

    If provenance_comment is provided (non-None), it replaces the fresh
    `# array-append <date>` comment (F5: preserve leading comment on replace).
    If elements is empty, renders an empty array.
    """
    comment = provenance_comment if provenance_comment is not None else f"# array-append {date_tag}"
    rows = "".join(f"  '{e}',\n" for e in elements)
    return f'{comment}\n"{key}" = [\n{rows}]\n'


def _write_registry_file(target_path: str, new_content: str, is_new: bool) -> int:
    """Atomic tmp+rename write of registry content.

    Returns 0 on success, 1 on failure (prints error to stderr).
    Preserves file mode when replacing an existing file.
    """
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
    return 0


def _load_registry_target(reg_dir: str, write_global: bool) -> tuple[str, str, str, bool]:
    """Return (target_file, target_path, content, is_new) for set/array commands."""
    target_file = "registry.toml" if write_global else "registry.local.toml"
    target_path = os.path.join(reg_dir, target_file)
    if os.path.exists(target_path):
        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()
        is_new = False
    else:
        is_new = True
        # Review: code-reviewer (F5) — header says "machine-local" not "machine-local set"
        # because array commands also create new files via this helper.
        content = (
            f"# {target_file}  (created by `machine-local`)\n"
            "#\n"
            "# WARNING: Use `machine-local set <key> <value>` to add or change values.\n"
            "# Direct hand-edits are fragile: they do not reproduce on reinstall and\n"
            "# will not transfer automatically to a new machine.\n"
            "schema = 1\n"
        )
    return target_file, target_path, content, is_new


def _check_concern_namespace(reg_dir: str, key: str) -> int:
    """Return 1 (with error) if key belongs to a loaded concern namespace, else 0."""
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
    return 0


def cmd_array_append(args: argparse.Namespace) -> int:
    """Implement: machine-local array-append <key> <element> [--global] [--dry-run]

    Append element to the TOML array at key.  Idempotent: skip if element is
    already present (exact-string dedup).  Create the array if key is absent.

    Spec backlink: docs/plans/2026-06-17-publish-targets-machine-local-migration.md § C1
    Note: the current sole consumer is publish.targets, but the API is keyed on the
    dotted key, not hardcoded to that name.

    Fail loud if key already exists as a scalar (not an array), as an
    array-of-tables, or as an inline table.  Reject elements containing a
    single quote (TOML literal strings have no escape).
    """
    reg_dir = _registry_dir()

    rc = _check_concern_namespace(reg_dir, args.key)
    if rc != 0:
        return rc

    key = args.key
    element = args.element
    dry_run = args.dry_run

    if _reject_single_quote_element(element):
        print(
            f"machine-local: refusing to write element containing single quote: {element!r}. "
            "Literal-string TOML has no escape for single quote.",
            file=sys.stderr,
        )
        return 1

    _target_file, target_path, content, is_new = _load_registry_target(reg_dir, args.write_global)
    date_tag = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Review: code-reviewer (F2) — removed dead pre_parsed/pre_flat/pre_val block; pre_val
    # was never used. The real collision check is the segment-walking parse below.

    # Detect scalar collision — key exists but resolves to a string (not a list).
    # Note: _flatten_nested stores the native Python type; lists come through as list.
    # For the pre-check we read the raw parsed value, not _flatten_nested, because
    # _flatten_nested joins lists with \n (losing the list type we need here).
    try:
        pre_raw = tomllib.loads(content)
        # Walk dotted key segments into the parsed dict.
        _cursor = pre_raw
        for seg in key.split("."):
            if isinstance(_cursor, dict) and seg in _cursor:
                _cursor = _cursor[seg]
            else:
                # Also check quoted-dotted flat key form.
                if isinstance(_cursor, dict) and key in _cursor:
                    _cursor = _cursor[key]
                    break
                _cursor = None
                break
        raw_existing = _cursor
        # Also try quoted-dotted flat key form at top level.
        if raw_existing is None and key in pre_raw:
            raw_existing = pre_raw[key]
    except tomllib.TOMLDecodeError:
        raw_existing = None

    if isinstance(raw_existing, str):
        print(
            f"machine-local: '{key}' is a scalar; refusing to append — "
            "hand-edit or use `array-set`.",
            file=sys.stderr,
        )
        return 1

    if isinstance(raw_existing, dict):
        print(
            f"machine-local: '{key}' is defined as an inline table; "
            "cannot use array-append. Hand-edit the file to update it.",
            file=sys.stderr,
        )
        return 1

    # Detect array-of-tables shape via locator.
    array_span = _locate_existing_array_span(content, key)
    if array_span is not None and array_span["kind"] == "array-of-tables-detected":
        print(
            f"machine-local: '{key}' is defined as an array-of-tables ([[{array_span['table_path']}]]); "
            "cannot use array-append. Hand-edit the file to update it.",
            file=sys.stderr,
        )
        return 1

    # Read current elements from the existing flat-array span (if any).
    current_elements: list[str] = []
    provenance_comment: str | None = None

    if array_span is not None and array_span["kind"] == "flat-array":
        # Parse existing array via tomllib to get the current elements.
        try:
            parsed_existing = tomllib.loads(content)
            # Navigate to the key value — may be a flat quoted-dotted key or
            # nested table, so use _flatten_nested's list-preserving sibling.
            # _flatten_nested joins lists with \n, so read from the raw parsed dict.
            flat_raw = _get_raw_list(parsed_existing, key)
            if isinstance(flat_raw, list):
                current_elements = [str(e) for e in flat_raw]
        except tomllib.TOMLDecodeError:
            pass

        # Retrieve provenance comment (F5).
        if array_span["comment_start"] is not None:
            # Find end of comment line.
            cstart = array_span["comment_start"]
            cend = content.find("\n", cstart)
            if cend == -1:
                cend = len(content)
            provenance_comment = content[cstart:cend]

    # Idempotent dedup: skip if element already present.
    if element in current_elements:
        if dry_run:
            print(f"[dry-run] '{key}': element already present (no-op): {element!r}")
        else:
            print(f"machine-local: '{key}': element already present (no-op): {element!r}")
        return 0

    new_elements = current_elements + [element]
    array_block = _build_array_content(key, new_elements, date_tag, provenance_comment)

    if array_span is not None and array_span["kind"] == "flat-array":
        # Replace the existing span (including provenance comment if we captured it).
        replace_start = array_span["comment_start"] if array_span["comment_start"] is not None else array_span["span_start"]
        replace_end = array_span["span_end"]
        new_content = content[:replace_start] + array_block + content[replace_end:]
        action = "updated"
    else:
        # Insert before first [section] header, or at EOF.
        section_pat = re.compile(r"^\[", re.MULTILINE)
        m = section_pat.search(content)
        if m:
            insert_at = m.start()
            new_content = content[:insert_at].rstrip("\n") + "\n" + array_block + "\n" + content[insert_at:]
        else:
            new_content = content.rstrip("\n") + "\n" + array_block
        action = "added"

    # Post-build round-trip sanity: parse new_content and verify the array
    # contains the expected elements.  Also verifies correct top-level scope
    # (a key appended after a [table] header would scope INTO that table).
    try:
        parsed_new = tomllib.loads(new_content)
    except tomllib.TOMLDecodeError as exc:
        print(
            f"machine-local: refusing to write — post-build TOML is malformed: {exc}. "
            "This is a bug in machine-local array-append. File a report and edit by hand.",
            file=sys.stderr,
        )
        return 1

    roundtrip_list = _get_raw_list(parsed_new, key)
    if not isinstance(roundtrip_list, list) or element not in roundtrip_list:
        print(
            f"machine-local: refusing to write — post-build round-trip of '{key}' "
            f"did not contain the appended element {element!r}. "
            "Likely cause: key scoped into a table rather than at top level. "
            "File a report and edit the registry by hand.",
            file=sys.stderr,
        )
        return 1

    if dry_run:
        print(f"[dry-run] would {action} array '{key}' (append {element!r}) in {target_path}")
        return 0

    rc = _write_registry_file(target_path, new_content, is_new)
    if rc != 0:
        return rc

    print(f"machine-local: {action} array '{key}' (appended {element!r}) in {target_path}")
    return 0


def cmd_array_set(args: argparse.Namespace) -> int:
    """Implement: machine-local array-set <key> <element>... [--global] [--dry-run]

    Replace the entire array at key with the given elements (order-preserving
    dedup).  Same scalar-collision fail-loud and single-quote rejection as
    array-append.

    Spec backlink: docs/plans/2026-06-17-publish-targets-machine-local-migration.md § C1
    Note: the current sole consumer is publish.targets, but the API is keyed on the
    dotted key, not hardcoded to that name.
    """
    reg_dir = _registry_dir()

    rc = _check_concern_namespace(reg_dir, args.key)
    if rc != 0:
        return rc

    key = args.key
    elements = args.elements
    dry_run = args.dry_run

    for element in elements:
        if _reject_single_quote_element(element):
            print(
                f"machine-local: refusing to write element containing single quote: {element!r}. "
                "Literal-string TOML has no escape for single quote.",
                file=sys.stderr,
            )
            return 1

    _target_file, target_path, content, is_new = _load_registry_target(reg_dir, args.write_global)
    date_tag = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Same pre-check as array-append: fail loud on scalar / inline-table.
    try:
        pre_raw = tomllib.loads(content)
        _cursor = pre_raw
        for seg in key.split("."):
            if isinstance(_cursor, dict) and seg in _cursor:
                _cursor = _cursor[seg]
            else:
                if isinstance(_cursor, dict) and key in _cursor:
                    _cursor = _cursor[key]
                    break
                _cursor = None
                break
        raw_existing = _cursor
        if raw_existing is None and key in pre_raw:
            raw_existing = pre_raw[key]
    except tomllib.TOMLDecodeError:
        raw_existing = None

    if isinstance(raw_existing, str):
        print(
            f"machine-local: '{key}' is a scalar; refusing to set array — "
            "hand-edit or use `set`.",
            file=sys.stderr,
        )
        return 1

    if isinstance(raw_existing, dict):
        print(
            f"machine-local: '{key}' is defined as an inline table; "
            "cannot use array-set. Hand-edit the file to update it.",
            file=sys.stderr,
        )
        return 1

    array_span = _locate_existing_array_span(content, key)
    if array_span is not None and array_span["kind"] == "array-of-tables-detected":
        print(
            f"machine-local: '{key}' is defined as an array-of-tables ([[{array_span['table_path']}]]); "
            "cannot use array-set. Hand-edit the file to update it.",
            file=sys.stderr,
        )
        return 1

    # Order-preserving dedup of supplied elements.
    seen: set[str] = set()
    deduped: list[str] = []
    for e in elements:
        if e not in seen:
            seen.add(e)
            deduped.append(e)

    # Retrieve provenance comment from existing span (F5).
    provenance_comment: str | None = None
    if array_span is not None and array_span["kind"] == "flat-array":
        if array_span["comment_start"] is not None:
            cstart = array_span["comment_start"]
            cend = content.find("\n", cstart)
            if cend == -1:
                cend = len(content)
            provenance_comment = content[cstart:cend]

    array_block = _build_array_content(key, deduped, date_tag, provenance_comment)

    if array_span is not None and array_span["kind"] == "flat-array":
        replace_start = array_span["comment_start"] if array_span["comment_start"] is not None else array_span["span_start"]
        replace_end = array_span["span_end"]
        new_content = content[:replace_start] + array_block + content[replace_end:]
        action = "replaced"
    else:
        section_pat = re.compile(r"^\[", re.MULTILINE)
        m = section_pat.search(content)
        if m:
            insert_at = m.start()
            new_content = content[:insert_at].rstrip("\n") + "\n" + array_block + "\n" + content[insert_at:]
        else:
            new_content = content.rstrip("\n") + "\n" + array_block
        action = "created"

    # Post-build round-trip sanity.
    try:
        parsed_new = tomllib.loads(new_content)
    except tomllib.TOMLDecodeError as exc:
        print(
            f"machine-local: refusing to write — post-build TOML is malformed: {exc}. "
            "This is a bug in machine-local array-set. File a report and edit by hand.",
            file=sys.stderr,
        )
        return 1

    roundtrip_list = _get_raw_list(parsed_new, key)
    if not isinstance(roundtrip_list, list) or list(roundtrip_list) != deduped:
        print(
            f"machine-local: refusing to write — post-build round-trip of '{key}' "
            f"returned {roundtrip_list!r}, expected {deduped!r}. "
            "Likely cause: key scoped into a table rather than at top level. "
            "File a report and edit the registry by hand.",
            file=sys.stderr,
        )
        return 1

    if dry_run:
        print(f"[dry-run] would {action} array '{key}' = {deduped!r} in {target_path}")
        return 0

    rc = _write_registry_file(target_path, new_content, is_new)
    if rc != 0:
        return rc

    print(f"machine-local: {action} array '{key}' = {deduped!r} in {target_path}")
    return 0


def _get_raw_list(parsed: dict, key: str) -> object:
    """Navigate parsed TOML dict to retrieve the native value for a dotted key.

    Handles both quoted-dotted-key flat form (where the literal dot is in the
    top-level dict key) and nested-table form.  Returns the raw Python object
    (list, str, dict, etc.) so callers can isinstance-check the type.
    Returns None if the key is not found.
    """
    # Try quoted-dotted flat key first (the form array-write uses).
    if key in parsed:
        return parsed[key]
    # Try walking nested dicts via split(".").
    cursor: object = parsed
    for seg in key.split("."):
        if isinstance(cursor, dict) and seg in cursor:
            cursor = cursor[seg]
        else:
            return None
    return cursor


def cmd_set(args: argparse.Namespace) -> int:
    """Implement: machine-local set <key> <value> [--global] [--dry-run]

    Writes a string key=value pair to registry.local.toml (default) or
    registry.toml (--global).  Atomic, idempotent, concern-aware.

    Use this instead of editing registry files by hand — direct edits are
    fragile: they do not reproduce on reinstall or transfer to a new machine,
    and may be clobbered by a concurrent session.
    """
    # Review: code-reviewer (F11) — re and datetime moved to module-level imports.

    reg_dir = _registry_dir()
    target_file = "registry.toml" if args.write_global else "registry.local.toml"
    target_path = os.path.join(reg_dir, target_file)

    key = args.key
    value = args.value
    dry_run = args.dry_run

    # Review: code-reviewer (F7) — replaced inline concern-namespace check with
    # _check_concern_namespace helper (same behavior, matches array commands).
    rc = _check_concern_namespace(reg_dir, key)
    if rc != 0:
        return rc

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

    # Existing-definition detection has four shapes:
    #   1. Flat:  "key.with.dots" = "old"   anywhere in file
    #   2. Table-form leaf:  [table.path]\nleaf = "old"  — leaf inside an existing table
    #   3. Table-form header without leaf:  [table.path] exists but no matching leaf
    #   4. Array-of-tables / inline table — detected but not modifiable by this writer
    # We try (1) → (2) → (3) → inline-table pre-check → append-as-flat, in order.
    # The dispatch covers the 2026-05-23 bug where set saw only (1) and appended a
    # duplicate when the existing definition was (2), creating a TOML where the
    # table-form silently won on read.
    update_result = _locate_existing_definition(content, key)

    # Guard F1: if the key resolves (via _flatten_nested on the parsed file) to a
    # list, it is an array — fail loud before touching it.  This fires BEFORE the
    # array-of-tables branch and inline-table check so the operator gets the
    # actionable array-command message rather than a generic shape error.
    try:
        _pre_parsed_for_guard = tomllib.loads(content)
        _pre_flat_for_guard = _flatten_nested(_pre_parsed_for_guard)
        _pre_val_for_guard = _pre_flat_for_guard.get(key)
    except tomllib.TOMLDecodeError:
        _pre_val_for_guard = None

    if isinstance(_pre_val_for_guard, list):
        # _flatten_nested joins lists with \n, so the value is a str when the
        # key is a list — but raw pre-parse check is more reliable.  Re-check
        # via _get_raw_list to confirm it is genuinely a list.
        _raw_for_guard = _get_raw_list(_pre_parsed_for_guard, key)
        if isinstance(_raw_for_guard, list):
            print(
                f"machine-local: '{key}' is an array; use `array-append`/`array-set`, not `set`.",
                file=sys.stderr,
            )
            return 1

    if update_result is not None and update_result["kind"] == "array-of-tables-detected":
        # Review: code-reviewer (F7) — array-of-tables detected; route to actionable error.
        print(
            f"machine-local: key '{key}' resolves in '{target_path}' but its "
            "definition shape (inline table, array-of-tables, or other) is not "
            "modifiable by this writer. Hand-edit the file to update it.",
            file=sys.stderr,
        )
        return 1

    if update_result is None:
        # Review: code-reviewer (F3) — inline-table pre-check before falling through to
        # flat-append. If the key resolves via tomllib but no regex shape matched it,
        # the definition is an inline table, array-of-tables, or other unmodifiable form.
        # The round-trip check below would also catch this, but surfacing the specific
        # diagnosis here is far more actionable.
        try:
            pre_parsed = tomllib.loads(content)
            pre_resolved = _flatten_nested(pre_parsed).get(key)
        except tomllib.TOMLDecodeError:
            pre_resolved = None  # malformed — let write proceed, round-trip check will catch it

        if pre_resolved is not None:
            print(
                f"machine-local: key '{key}' resolves in '{target_path}' but its "
                "definition shape (inline table, array-of-tables, or other) is not "
                "modifiable by this writer. Hand-edit the file to update it.",
                file=sys.stderr,
            )
            return 1

        # No existing definition anywhere — append a flat quoted-dotted-key line
        # before the first [<section>] header (or at EOF if none).
        section_pat = re.compile(r"^\[", re.MULTILINE)
        m = section_pat.search(content)
        new_line = f'"{key}" = {value_literal}  # set {date_tag}\n'
        if m:
            insert_at = m.start()
            new_content = content[:insert_at].rstrip("\n") + "\n" + new_line + "\n" + content[insert_at:]
        else:
            new_content = content.rstrip("\n") + "\n" + new_line
        action = "added"
    else:
        kind = update_result["kind"]
        if kind == "flat":
            m = update_result["match"]
            new_content = (
                content[:m.start()]
                + m.group(1) + value_literal + m.group(2)
                + content[m.end():]
            )
            action = "updated"
        elif kind == "table-leaf":
            abs_start = update_result["abs_start"]
            abs_end = update_result["abs_end"]
            leaf_m = update_result["leaf_match"]
            new_content = (
                content[:abs_start]
                + leaf_m.group(1) + value_literal + leaf_m.group(2)
                + content[abs_end:]
            )
            action = "updated"
        elif kind == "table-header-only":
            # Table header exists but the leaf is absent inside it. Inject the
            # leaf at the end of the table's body (before the next section header
            # or EOF). Flat-append would be a TOML error if subsequent
            # [<other.section>] headers follow this one — TOML forbids reopening
            # a closed table from outside any table.
            section_start = update_result["section_start"]
            section_end = update_result["section_end"]
            leaf_path = update_result["leaf_path"]
            section_body = content[section_start:section_end]
            # Review: code-reviewer (F6) — match sibling key indentation rather than
            # always injecting unindented. Standard registry TOML has no indentation,
            # so this falls back to no-indent for the common case.
            indent_match = re.search(r"^([ \t]+)\S", section_body, re.MULTILINE)
            indent = indent_match.group(1) if indent_match else ""
            trimmed = section_body.rstrip("\n")
            suffix = section_body[len(trimmed):]
            new_section = (
                trimmed
                + f"\n{indent}{leaf_path} = {value_literal}  # set {date_tag}\n"
                + suffix
            )
            new_content = content[:section_start] + new_section + content[section_end:]
            action = "added"
        else:  # pragma: no cover — defensive
            print(f"machine-local: internal error: unknown match kind {kind!r}", file=sys.stderr)
            return 1

    # Post-build round-trip sanity check: the new content must parse and the
    # requested key must resolve to the requested value via _flatten_nested.
    # Review: code-reviewer (F4) — this check verifies parse+flatten correctness
    # for the file being written. It does NOT verify the full resolution stack:
    # concern-namespace exclusivity is already handled by the guard above; env-var
    # resolution is below all TOML layers and irrelevant for write verification.
    try:
        parsed = tomllib.loads(new_content)
    except tomllib.TOMLDecodeError as exc:
        print(
            f"machine-local: refusing to write — post-build TOML is malformed: {exc}. "
            "This is a bug in machine-local set, not in your input. "
            "File a report and edit the registry by hand for now.",
            file=sys.stderr,
        )
        return 1

    # Resolve via the same flatten logic the reader uses so a quoted-dotted-key
    # (`"repos.holodeck" = ...` parses as a single flat key) and a nested table
    # (`[repos]\nholodeck = ...` parses as `{"repos": {"holodeck": ...}}`) both
    # resolve to the dotted key the operator typed. Walking parsed with split(".")
    # mishandles the quoted-key shape because TOML keeps the literal dot in the key.
    resolved = _flatten_nested(parsed).get(key)
    if resolved != value:
        print(
            f"machine-local: refusing to write — post-build round-trip read of "
            f"{key!r} returned {resolved!r}, expected {value!r}. "
            "Likely cause: the registry contains a definition shape this writer "
            "does not yet handle, leaving a stale value still in scope. "
            "File a report and edit the registry by hand for now.",
            file=sys.stderr,
        )
        return 1

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

    # array-append
    aa_p = subparsers.add_parser(
        "array-append",
        help="Append an element to a TOML array key (idempotent; current sole consumer: publish.targets)",
    )
    aa_p.add_argument("key", help="Dotted key for the array (e.g. publish.targets)")
    aa_p.add_argument("element", help="String element to append")
    aa_p.add_argument(
        "--global",
        dest="write_global",
        action="store_true",
        help="Write to registry.toml (tracked/shared) instead of registry.local.toml",
    )
    aa_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without making changes",
    )

    # array-set
    as_p = subparsers.add_parser(
        "array-set",
        help="Replace a TOML array key with the given elements (order-preserving dedup; current sole consumer: publish.targets)",
    )
    as_p.add_argument("key", help="Dotted key for the array (e.g. publish.targets)")
    as_p.add_argument("elements", nargs="+", help="String elements to set (replaces current array)")
    as_p.add_argument(
        "--global",
        dest="write_global",
        action="store_true",
        help="Write to registry.toml (tracked/shared) instead of registry.local.toml",
    )
    as_p.add_argument(
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
        "array-append": cmd_array_append,
        "array-set": cmd_array_set,
    }
    return dispatch[parsed.command](parsed)


if __name__ == "__main__":
    sys.exit(main())
