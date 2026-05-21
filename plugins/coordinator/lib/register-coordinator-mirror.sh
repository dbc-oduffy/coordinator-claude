#!/usr/bin/env bash
# Register the coordinator plugin in registry.local.toml's plugin.mirrors section.
#
# The coordinator plugin's live install IS the canonical source (~/.claude/) — no
# inward propagation step is needed. Edits flow outward via publish.sh. Registering
# this structural fact lets bin/check-plugin-drift.sh surface it as `n/a-by-design`
# rather than treating it as an unchecked entry.
#
# Idempotent + atomic: uses Python with os.replace to avoid heredoc-append races
# under concurrent /coordinator:setup invocations. Both create-if-absent and
# section-append are handled in one atomic operation.
#
# Spec: docs/plans/2026-05-21-plugin-source-live-mirror-doctrine.md § Chunk 5 / AC-7
# Review trail: code-reviewer chain-end findings #7, #14, #18 — replaced non-atomic
# heredoc append with this script; fall-through after the early-exit handles two cases:
#   (a) file absent — create + append
#   (b) file exists, section absent — append only

set -euo pipefail

_check_only="${1:-}"
_reg="$(claude-home machine-local)/registry.local.toml"
_coordinator_live="$(claude-home plugins)/coordinator-claude/coordinator"

python3 - "$_reg" "$_coordinator_live" "$_check_only" <<'PYEOF'
import os, sys
from pathlib import Path

reg_path = Path(sys.argv[1])
live_path = sys.argv[2]
check_only = sys.argv[3] == "--check-only" if len(sys.argv) > 3 else False

def _toml_escape(s: str) -> str:
    # Escape per TOML spec for basic strings (double-quoted).
    # Order matters: backslash must be first to avoid double-escaping.
    s = s.replace("\\", "\\\\")
    s = s.replace('"', '\\"')
    s = s.replace("\n", "\\n")
    s = s.replace("\t", "\\t")
    s = s.replace("\r", "\\r")
    return s

section_header = "[plugin.mirrors.coordinator-claude]"
section_body = (
    "\n"
    f"{section_header}\n"
    "# Live install IS canonical source — registered automatically by /coordinator:setup\n"
    "# Drift probe and refresh script treat this as n/a-by-design; no git/venv legs to check.\n"
    'propagation_mode = "source_is_live"\n'
    f'live_path = "{_toml_escape(live_path)}"\n'
)

existing = reg_path.read_text(encoding="utf-8") if reg_path.exists() else ""
if check_only:
    if section_header in existing:
        print("coordinator_plugin_mirrors: ready")
    else:
        print("coordinator_plugin_mirrors: would write")
    sys.exit(0)

if section_header in existing:
    print("plugin.mirrors.coordinator-claude already registered — skipping.")
    sys.exit(0)

reg_path.parent.mkdir(parents=True, exist_ok=True)
if not existing:
    existing = "schema = 1\n"

new_text = existing.rstrip("\n") + "\n" + section_body
# Use string concatenation rather than .with_suffix() — multi-dot suffixes
# raise ValueError on Python <3.12 (CPython relaxed this in 3.12).
tmp = reg_path.parent / (reg_path.name + f".tmp.{os.getpid()}")
tmp.write_text(new_text, encoding="utf-8")
if reg_path.exists():
    try:
        tmp.chmod(os.stat(reg_path).st_mode)
    except OSError:
        pass
os.replace(tmp, reg_path)
print("Coordinator plugin registered (source_is_live mode). Drift probe will skip it as n/a-by-design.")
PYEOF
