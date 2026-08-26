"""coordinator-validate-local-config — author-time argv-only gate for a
repo's coordinator.local.md.

Invoke as `python3 coordinator/bin/coordinator-validate-local-config` — no
shebang / exec bit on this file (new-file zero-budget ratchet:
env_shebang + extensionless_exec; see `nudge-new-file-zero-budget-ratchets.py`).
Windows-first-class doctrine also means no bash trampoline is wanted here;
an explicit `python3` invocation is the portable call shape.

Purpose: `coordinator_core.ceremony_config.argv_only.check_argv_only` is the
single canonical definition of the argv-only contract that
`coordinator-ceremony-hook.py` enforces at fire time. Fire-time enforcement
is non-fatal, on stderr, in the middle of a ceremony — precisely how
Example-cockpit-repo's `workday_complete_post_command` sat broken without a
signal until an unrelated commit went digging
(`cross-repo/inbox/2026-08-06-example-cockpit-repo-em-argv-only-landed-cockpit-
config-fixed.md`). This CLI is the author-time twin: it reads a repo's
coordinator.local.md frontmatter, runs every `*_command` / `*_cmd` key
through the same predicate, and exits non-zero on the first repo-wide
violation — cheap enough to run in CI, before any ceremony ever fires.

NEGATIVE-SPEC: this tool does not execute, resolve on PATH, or otherwise
touch any configured command — it is a pure read + parse + report. See
`coordinator_core.ceremony_config.argv_only`'s own module docstring for why
PATH-resolution is deliberately out of scope for the predicate it calls.

Exemption marker: a key can opt out of this check by listing its OWN key
name (not the value) under a flat top-level `argv_only_exempt:` frontmatter
key, written as a YAML flow sequence, e.g.:

    argv_only_exempt: [legacy_migration_command]

This shape was PICKED, not confirmed against cockpit's own TypeScript
checker (`tests/portability/ceremony-command-word-form.test.ts`) — their
inbound memo describes their W1/W2 rules but not the exemption marker's
concrete spelling. Needs confirming with example-cockpit-repo-em before either
side treats the spelling as load-bearing across repos.

Routing: entirely self-contained, no separate coordinator_core.ops.* module
backs it — mirrors coordinator/bin/spawn-census's own DR-276 rationale (a
read-only operator CLI with no other caller for a fresh ops module),
routed through `cli_entry.recording_declared_writes()` even though this
tool declares no writes, for the same reason spawn-census does: parity with
every other bin/ CLI's DR-276 write-declaration wrapper costs nothing when
there is nothing to declare.

Usage:
  coordinator-validate-local-config [--repo <path>] [--json]

Exit codes:
  0 — every *_command / *_cmd key is argv-only-conformant (or exempt, or the
      file/keys are simply absent).
  1 — one or more keys are non-conformant.
  2 — CLI usage error.
  3 — engine-root resolution or coordinator_core import failure (transport
      failure, distinct from both business codes above).

Spec backlink: pln-shell-spawn-regrowth-gate-cens-097e21 § C12
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_LIB_DIR = str(Path(__file__).resolve().parent / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_colocated_engine_on_path  # noqa: E402

_COMMAND_KEY_RE = re.compile(r"^([A-Za-z0-9_]+):\s?(.*)$")
_EXEMPT_KEY = "argv_only_exempt"


def _import_deps():
    """Resolve the engine root and import the pinned ceremony_config + cli_entry
    API. Raises RuntimeError (root resolution) or ImportError (module
    missing) — both caught by `main()` and turned into exit code 3.
    """
    require_colocated_engine_on_path(__file__)

    from coordinator_core.ceremony_config.argv_only import check_argv_only
    from coordinator_core.cli_entry import recording_declared_writes

    return {
        "check_argv_only": check_argv_only,
        "recording_declared_writes": recording_declared_writes,
    }


def _extract_frontmatter(path: Path) -> str:
    """Lines strictly between the first and second `---` marker lines.
    Mirrors coordinator_core.resolve_validation_cmd._extract_frontmatter."""
    text = path.read_text(encoding="utf-8", errors="replace")
    out = []
    n = 0
    for line in text.splitlines():
        if line == "---":
            n += 1
            if n == 2:
                break
            continue
        if n == 1:
            out.append(line)
    return "\n".join(out)


def _strip_wrapping_quotes(val: str) -> str:
    """Unquote ONE wrapping YAML scalar pair, preserving interior quotes.
    Mirrors coordinator_core.resolve_validation_cmd._strip_wrapping_quotes
    (double-quote escape resolution omitted here — this CLI only needs
    argv-only conformance, not the fast_test_cmd resolver's exit-126 escape
    contract, and inheriting that contract here without its callers would
    be scope creep)."""
    if len(val) >= 2 and val.startswith('"') and val.endswith('"'):
        return val[1:-1]
    if len(val) >= 2 and val.startswith("'") and val.endswith("'"):
        return val[1:-1].replace("''", "'")
    return val


def _parse_flat_keys(frontmatter: str) -> dict[str, str]:
    """Every flat top-level `key: value` line in `frontmatter`, quote-stripped.
    Last occurrence of a repeated key wins (matches simple flat-frontmatter
    convention elsewhere in this repo)."""
    out: dict[str, str] = {}
    for line in frontmatter.split("\n"):
        m = _COMMAND_KEY_RE.match(line)
        if not m:
            continue
        key, raw_val = m.group(1), m.group(2)
        out[key] = _strip_wrapping_quotes(raw_val.strip())
    return out


def _parse_exempt_list(raw: str) -> set[str]:
    """Parse a flow-sequence-shaped `argv_only_exempt:` value, e.g.
    `[a, b]` or `a, b` (bracket-optional, comma-separated, whitespace-
    tolerant). Empty/absent value -> empty set."""
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return {tok.strip() for tok in raw.split(",") if tok.strip()}


def _is_command_key(key: str) -> bool:
    return key.endswith("_command") or key.endswith("_cmd")


def _collect_rows(deps: dict, local_md: Path) -> list[dict]:
    check_argv_only = deps["check_argv_only"]
    if not local_md.is_file():
        return []
    frontmatter = _extract_frontmatter(local_md)
    flat = _parse_flat_keys(frontmatter)
    exempt = _parse_exempt_list(flat.get(_EXEMPT_KEY, ""))

    rows = []
    for key, value in flat.items():
        if not _is_command_key(key):
            continue
        if key in exempt:
            rows.append(
                {
                    "key": key,
                    "value": value,
                    "conformant": True,
                    "rule": None,
                    "detail": "exempt (argv_only_exempt)",
                }
            )
            continue
        verdict = check_argv_only(value)
        rows.append(
            {
                "key": key,
                "value": value,
                "conformant": verdict.conformant,
                "rule": verdict.rule,
                "detail": verdict.detail,
            }
        )
    rows.sort(key=lambda r: r["key"])
    return rows


def _render_human(rows: list[dict], local_md: Path) -> str:
    if not rows:
        return f"coordinator-validate-local-config: no *_command/*_cmd keys found in {local_md}"
    lines = [f"coordinator-validate-local-config: {local_md}"]
    for row in rows:
        status = "OK  " if row["conformant"] else "FAIL"
        lines.append(f"  [{status}] {row['key']}: {row['value']!r}")
        if not row["conformant"]:
            lines.append(f"           rule={row['rule']} — {row['detail']}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="coordinator-validate-local-config")
    parser.add_argument("--repo", default=".", help="repo root (default: cwd)")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a human table")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    try:
        deps = _import_deps()
    except Exception as exc:  # noqa: BLE001 - transport failure, mapped to exit 3
        print(f"coordinator-validate-local-config: engine-root/import resolution failed: {exc}", file=sys.stderr)
        return 3

    root = Path(args.repo).resolve()
    local_md = root / "coordinator.local.md"

    with deps["recording_declared_writes"]():
        rows = _collect_rows(deps, local_md)

    unconformant = [r for r in rows if not r["conformant"]]

    if args.json:
        print(
            json.dumps(
                {
                    "repo": str(root),
                    "local_md": str(local_md),
                    "rows": rows,
                    "unconformant_count": len(unconformant),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(_render_human(rows, local_md))

    return 1 if unconformant else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
