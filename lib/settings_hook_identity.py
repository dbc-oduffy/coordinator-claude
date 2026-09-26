
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
    return CMD_PATH_DEF


def group_is_generated_def() -> str:
    return GROUP_IS_GENERATED_DEF


def jq_program() -> str:
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
