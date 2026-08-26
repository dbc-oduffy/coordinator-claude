"""settings_hook_identity.py — shared settings.json generated-hook identity key.

Purpose: SINGLE source of truth for "is this hook group coordinator-generated?",
  consumed by both the forward generator (gen-settings-hooks.py) and the uninstall
  inverse-strip leg (uninstall_strip_settings_hooks, coordinator_core.install.uninstall_legs, claude-klabauter).
  Prior to this module the identity key (interpreter-prefix strip + generated-dir
  prefix test) was duplicated inline in the forward generator at two call sites
  (a stray-check and the main jq program); any future uninstall-side re-derivation
  would have been a THIRD copy, guaranteed to drift.

Identity key: a hook group is "generated" iff at least one of its command hooks has
  a resolved command path — after stripping a leading interpreter prefix
  (bash/node/python3/python) — that starts with "<coordinator_root>/hooks/".
  All other groups are preserved verbatim. This mirrors gen-settings-hooks.py's
  `group_is_generated` jq def exactly; do not re-derive divergently.

Spec backlink: DoE-claude:pln-first-class-coordinator-uninst-15db2e § C2
Prior art: docs/wiki/install-surface-completeness.md § Multi-site value parity
  ("one canonical manifest, all call-sites consume it" — this module is that
  canonical manifest for the settings-hook identity key specifically).
Surface source of truth: tasks/coordinator-uninstall/surface-map.md § settings.json
  inverse-strip contract.

Port backlink: docs/plans/2026-07-19-debash-coordinator-windows.md (E3-e, naked-python
  port). No in-repo caller currently invokes this module — gen-settings-hooks.py has
  its own inline jq defs and the uninstall inverse-strip leg lives cross-repo in
  claude-klabauter — kept as the canonical settings-hook identity primitive for any
  future in-repo consumer.
"""

from __future__ import annotations

import shutil
import subprocess

CMD_PATH_DEF = (
    "def cmd_path:\n"
    '  ltrimstr("bash ") | ltrimstr("node ") | ltrimstr("python3 ") | ltrimstr("python ");\n'
)

GROUP_IS_GENERATED_DEF = (
    "def group_is_generated:\n"
    "  .hooks | any(\n"
    '    .type == "command" and\n'
    "    (.command | cmd_path | startswith($generated_hooks_dir + \"/\"))\n"
    "  );\n"
)


def cmd_path_def() -> str:
    """Return the jq `def cmd_path: ...;` snippet (interpreter-prefix strip)."""
    return CMD_PATH_DEF


def group_is_generated_def() -> str:
    """Return the jq `def group_is_generated: ...;` snippet.

    Depends on cmd_path (see cmd_path_def) being defined earlier in the same
    jq program, and on a `$generated_hooks_dir` jq --arg being bound by the
    caller (the caller's invocation must pass
    `--arg generated_hooks_dir "<coordinator_root>/hooks"`).
    """
    return GROUP_IS_GENERATED_DEF


def jq_program() -> str:
    """Return both defs concatenated, ready to prepend to a larger jq program string."""
    return cmd_path_def() + group_is_generated_def()


_INVERSE_STRIP_FILTER = """
# Preserved: groups where NO command hook has a path under coordinator/hooks/.
# All non-hooks top-level keys (e.g. .enabledPlugins) pass through untouched
# via the trailing `. + {hooks: ...}` merge below.
((.hooks // {}) | to_entries | map(
  .key as $event |
  (.value | map(select(group_is_generated | not))) |
  {key: $event, value: .}
) | map(select(.value | length > 0)) | from_entries) as $preserved |

. + {hooks: $preserved}
"""


def inverse_strip(settings_json: str, coordinator_root: str, out_path: str) -> None:
    """Write, to <out_path>, a copy of <settings_json> with every generated hook
    group removed (identity: group_is_generated_def) and every other group —
    including all non-hook top-level keys such as `.enabledPlugins` — preserved
    untouched. Atomic-safe only insofar as the caller treats <out_path> as a
    temp file and renames it into place; this function itself performs a
    single jq invocation and does not do the rename.

    Raises ValueError on missing/invalid arguments, RuntimeError if jq is
    missing, FileNotFoundError if settings_json does not exist, and
    subprocess.CalledProcessError if jq itself fails (invalid JSON input) —
    callers must not swallow these.
    """
    if not settings_json:
        raise ValueError("inverse_strip: missing settings_json_path")
    if not coordinator_root:
        raise ValueError("inverse_strip: missing coordinator_root")
    if not out_path:
        raise ValueError("inverse_strip: missing out_path")

    if shutil.which("jq") is None:
        raise RuntimeError("inverse_strip: jq is required but not installed.")

    import os

    if not os.path.isfile(settings_json):
        raise FileNotFoundError(f"inverse_strip: not found: {settings_json}")

    generated_hooks_dir = coordinator_root.rstrip("/") + "/hooks"
    program = jq_program() + _INVERSE_STRIP_FILTER

    with open(out_path, "w", encoding="utf-8", newline="\n") as out_fh:
        subprocess.run(
            ["jq", "--arg", "generated_hooks_dir", generated_hooks_dir, program, settings_json],
            stdout=out_fh,
            check=True,
        )
