"""
snippet-registry — CLI trampoline over claude-klabauter coordinator_core.snippet_sync.registry.

Folded from the retired bash CLI (477 LoC, itself shelling to a python3
heredoc to parse snippets/registry.toml) per T3a-g3f Q14 — the nested
bash-wraps-python shape was exactly the antipattern this migration targets.

Usage:
  snippet-registry list-snippets
      Print one snippet name per line (all enrolled names), alphabetically.

  snippet-registry list-consumers <snippet-name>
      Print one resolved consumer path per line.
      Exit 0 on success, 2 on unknown snippet name, 3 on schema_version mismatch.
      Conditional consumers with unset machine-local keys emit a NOTE to stderr
      and are skipped (no exit-nonzero — absent sibling repos are routine).

  snippet-registry list-for <consumer-path>
      Reverse lookup: print snippet names whose resolved consumer set includes
      <consumer-path>. Empty output + exit 0 = no match.

Exit codes:
  0  success
  1  usage / internal error
  2  unknown snippet name (list-consumers only)
  3  schema_version mismatch or absent

Spec backlink: DoE scratch/subagent-sandbox/bash-to-python-engine-migration/recipe-t3a-g3.md § 6
DR backlink:   docs/decisions/2026-06-15-snippet-registry-shape.md
Port of: coordinator/bin/snippet-registry (bash CLI, retired on cutover; see git log)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_BIN_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
# machine_local_resolve.py imports from the coordinator_core package
# (win_portability) at module level -- that package is resolvable only from
# the repo root, not from _LIB_DIR, so it must be on sys.path too or the
# import below raises ModuleNotFoundError every time this CLI runs as a
# subprocess (which is how every real caller invokes it).
_REPO_ROOT = os.path.dirname(os.path.dirname(_BIN_DIR))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from cc_invoke import require_dispatch_engine_on_path  # noqa: E402
from coordinator_data_root import data_root  # noqa: E402
from machine_local_resolve import resolve_machine_local_bin  # noqa: E402


def _resolve_plugin_root() -> Path:
    """Resolve the coordinator root consumer relative paths (e.g. "agents/...")
    resolve against — CLAUDE_PLUGIN_ROOT override always wins; otherwise the
    parent of the resolved snippets/ data dir (co-located or DoE-resident per
    `coordinator_data_root.data_root()`), since that parent IS the coordinator
    root under either layout.
    """
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env)
    return data_root("snippets").parent


def main() -> None:
    args = sys.argv[1:]
    subcommand = args[0] if args else ""

    if subcommand in ("--help", "-h"):
        print("Usage: snippet-registry <subcommand> [args]")
        print("  list-snippets")
        print("  list-consumers <snippet-name>")
        print("  list-for <consumer-path>")
        sys.exit(0)

    claude_klabauter_root = require_dispatch_engine_on_path()
    try:
        from coordinator_core.snippet_sync import registry as reg
    except ImportError as exc:
        print(
            f"snippet-registry: coordinator_core.snippet_sync.registry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    plugin_root = _resolve_plugin_root()
    registry_toml = plugin_root / "snippets" / "registry.toml"
    machine_local_bin = resolve_machine_local_bin(script_dir)

    try:
        data = reg.load_registry(registry_toml)
    except reg.RegistryError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(exc.exit_code)

    if subcommand == "list-snippets":
        for name in reg.list_snippets(data):
            print(name)
        sys.exit(0)

    if subcommand == "list-consumers":
        if len(args) < 2:
            print("Usage: snippet-registry list-consumers <snippet-name>", file=sys.stderr)
            sys.exit(1)
        try:
            consumers = reg.resolve_consumers(
                data, args[1], plugin_root, machine_local_bin=machine_local_bin
            )
        except reg.RegistryError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(exc.exit_code)
        # `resolve_consumers()` intentionally returns native-separator paths
        # (internal Path/os.path reopen-and-compare surface, confirmed by the
        # 2026-08-07 separator-cluster pass which reverted a same-shape fix
        # inside registry.py after it broke 9 green tests) -- normalize only
        # here, at the CLI presentation boundary, mirroring
        # verify-snippet-sync's `--list` fix.
        for path in consumers:
            print(str(path).replace(os.sep, "/"))
        sys.exit(0)

    if subcommand == "list-for":
        if len(args) < 2:
            print("Usage: snippet-registry list-for <consumer-path>", file=sys.stderr)
            sys.exit(1)
        for name in reg.list_for(data, args[1], plugin_root, machine_local_bin=machine_local_bin):
            print(name)
        sys.exit(0)

    if subcommand == "":
        print("Usage: snippet-registry <subcommand> [args]", file=sys.stderr)
        print("  list-snippets", file=sys.stderr)
        print("  list-consumers <snippet-name>", file=sys.stderr)
        print("  list-for <consumer-path>", file=sys.stderr)
        sys.exit(1)

    print(f"ERROR: snippet-registry: unknown subcommand '{subcommand}'", file=sys.stderr)
    print("  Known subcommands: list-snippets, list-consumers, list-for", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
