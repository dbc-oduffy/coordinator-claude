# coordinator-initiative — mint, attach, and list unattached initiatives.
#
# Spec backlink: docs/plans/2026-07-04-initiative-govern-sweep-prioritize-doe-d.md § C2 (AC3)
#
# Purpose: authoring-side CLI for the initiative governing discipline.
#   create          Mint state/initiatives/<id>.yaml. Fail-loud on existing id; atomic write.
#   attach          Write initiative: <id> FK to an artifact's YAML frontmatter. Also
#                   accepts `attach --pairs-file <path>`: N (artifact-path,
#                   initiative-id) pairs in ONE process invocation instead of N —
#                   the batch form callers like coordinator_core.ops.backfill_initiative_fk
#                   use to collapse a per-pair subprocess spawn loop into one spawn.
#                   Pairs-file is TSV (`artifact_path<TAB>initiative_id` per line,
#                   blank/`#`-comment lines skipped); output is one JSON line per
#                   pair on stdout for per-pair attribution, in pairs-file line order.
#   list-unattached Narrow CLI (--format/--limit only) over the native
#                   records_query.query_records(unattached=True) union lens
#                   (in-process call, no node/query-records.js spawn).
#
# VERBATIM — central-seam resolution: state/initiatives/ is resolved via
# coordinator_state_root --central by invoking lib/coordinator-state-root.py
# as a subprocess (de-bash campaign). NOT coordinator-session.sh.
# Spec backlink: docs/plans/2026-07-04-initiative-govern-sweep-prioritize-doe-d.md § C2
#
# Port: de-bash campaign, extensionless entrypoint keeps its exact
# name (callers depend on it) and becomes a python3-shebang script. No bash
# version guard is needed any more (CPython, not bash 3.2/4 discrimination).
#
# Test override: COORDINATOR_INITIATIVE_ROOT bypasses coordinator_state_root
# resolution (for unit tests that do not have a configured claude-klabauter/central
# state root).
#
# Negative-spec: does NOT auto-create initiatives from detector output (surface-and-confirm only).
# Negative-spec: does NOT build the interactive attach UI.
# Negative-spec: does NOT use coordinator-session.sh for state root resolution.
# Negative-spec: does NOT write any file outside state/initiatives/<id>.yaml or the named artifact.

from __future__ import annotations

import json
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# lib/ is one level up from bin/ (coordinator/bin/ → coordinator/lib/).
LIB_DIR = os.path.join(SCRIPT_DIR, "..", "lib")
_COORDINATOR_STATE_ROOT_PY = os.path.join(LIB_DIR, "coordinator-state-root.py")

# records_query.py lives under bin/lib/ (coordinator/bin/lib/), a SIBLING of
# LIB_DIR above (coordinator/lib/) — NOT the same directory. Mirrors the
# import preamble in coordinator/bin/detect-initiative-candidates, the other
# native consumer of this trampoline. Do NOT conflate with LIB_DIR/
# _COORDINATOR_STATE_ROOT_PY above, which resolve a different lib/ tree.
_BIN_LIB_DIR = os.path.join(SCRIPT_DIR, "lib")

# Engine-root bootstrap: `_resolve_initiatives_dir` below (reached from
# `create`/`attach`, function-scoped, not module scope) imports
# `coordinator_core.win_portability`. Without this, the import dies with
# ModuleNotFoundError on the mirror (coordinator_core not pip-installed).
if _BIN_LIB_DIR not in sys.path:
    sys.path.insert(0, _BIN_LIB_DIR)
import cc_invoke  # noqa: E402

cc_invoke.ensure_engine_on_path(__file__)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


# ── Central-seam resolution ────────────────────────────────────────────────────
# Resolves state/initiatives/ via coordinator_state_root --central.
# Respects COORDINATOR_INITIATIVE_ROOT env override for test isolation.
# Negative-spec: does NOT fall back silently if the seam fails — returns None (fail-loud).
def _resolve_initiatives_dir() -> str | None:
    # Test-isolation override: bypasses central-seam resolution entirely.
    override = os.environ.get("COORDINATOR_INITIATIVE_ROOT", "")
    if override:
        return override

    if not os.path.isfile(_COORDINATOR_STATE_ROOT_PY):
        print(
            f"coordinator-initiative: lib/coordinator-state-root.py not found at "
            f"{_COORDINATOR_STATE_ROOT_PY}",
            file=sys.stderr,
        )
        print("  Remediation: ensure the coordinator plugin is fully installed.", file=sys.stderr)
        return None

    # De-bash campaign: the bash sourced-lib oracle was ported to a Python CLI
    # trampoline (coordinator-state-root.py) — invoke it directly rather than
    # sourcing bash. Mirrors the subprocess pattern used by coordinator-doc-new
    # (Python) for the same seam.
    # ENGINE (claude-klabauter): sole consumer emit-cockpit-snapshot.py reads
    # state/initiatives — §Residency-Is-Not-Ownership; doctrine reclassification
    # pending lockstep cockpit-read flip (improvement-queue entry)
    import subprocess

    from coordinator_core.win_portability import no_console_creationflags

    try:
        proc = subprocess.run(
            [sys.executable, _COORDINATOR_STATE_ROOT_PY, "--central"],
            capture_output=True,
            text=True,
            **no_console_creationflags(),
        )
    except OSError as exc:
        print(
            f"coordinator-initiative: failed to resolve central state root via "
            f"coordinator-state-root.py.\n  {exc}",
            file=sys.stderr,
        )
        print(
            "  Ensure CLAUDE_KLABAUTER_ROOT is configured (machine-local registry) and the lib is reachable.",
            file=sys.stderr,
        )
        return None

    if proc.returncode != 0:
        print(
            "coordinator-initiative: failed to resolve central state root via "
            "coordinator-state-root.py.",
            file=sys.stderr,
        )
        print(
            "  Ensure CLAUDE_KLABAUTER_ROOT is configured (machine-local registry) and the lib is reachable.",
            file=sys.stderr,
        )
        return None

    state_root = proc.stdout.strip()
    if not state_root:
        print(
            "coordinator-initiative: coordinator_state_root --central returned empty path.",
            file=sys.stderr,
        )
        return None

    return f"{state_root}/initiatives"


# ── YAML quoting ───────────────────────────────────────────────────────────────
# Wrap a value in YAML double-quoted string, escaping embedded \ and ".
# Used for id, label, owner, target_date to produce spec-compliant YAML.
def _yaml_dquote(val: str) -> str:
    val = val.replace("\\", "\\\\")  # escape backslashes
    val = val.replace('"', '\\"')  # escape double-quotes
    # Review: code-reviewer — F11 (nit): escape control characters so a newline or carriage
    # return in --label/--id (e.g. from a value containing a literal newline) produces valid
    # YAML \n/\r, not a literal newline inside the double-quoted string (which is invalid YAML).
    val = val.replace("\n", "\\n")  # escape newlines
    val = val.replace("\r", "\\r")  # escape carriage returns
    return f'"{val}"'


# ── Usage ──────────────────────────────────────────────────────────────────────
def _usage() -> None:
    print("Usage:", file=sys.stderr)
    print(
        "  coordinator-initiative create --id <id> --label <label> [--owner <owner>] "
        "[--target-date <YYYY-MM-DD>] [--force]",
        file=sys.stderr,
    )
    print("  coordinator-initiative attach <artifact-path> <initiative-id>", file=sys.stderr)
    print("  coordinator-initiative attach --pairs-file <path>", file=sys.stderr)
    print(
        "  coordinator-initiative list-unattached [--format paths|json|markdown-list] "
        "[--limit N]",
        file=sys.stderr,
    )
    print("", file=sys.stderr)
    print("Subcommands:", file=sys.stderr)
    print(
        "  create          Mint state/initiatives/<id>.yaml. Fails on existing id "
        "(use --force to overwrite).",
        file=sys.stderr,
    )
    print(
        "  attach          Set initiative: <id> in the artifact YAML frontmatter (FK write).",
        file=sys.stderr,
    )
    print(
        "  list-unattached List all artifacts with initiative == null "
        "(native records.query unattached union lens; --format/--limit only).",
        file=sys.stderr,
    )


# ── create ─────────────────────────────────────────────────────────────────────
# Mint state/initiatives/<id>.yaml.
# Fail-loud (non-zero exit + remediation message) when the id already exists and --force is absent.
# Write is atomic via temp-file + rename to prevent partial writes on crash.
def _cmd_create(args: list[str]) -> int:
    id_ = ""
    label = ""
    owner = ""
    target_date = ""
    force = False

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--id":
            id_ = args[i + 1] if i + 1 < len(args) else ""
            i += 2
        elif arg.startswith("--id="):
            id_ = arg[len("--id="):]
            i += 1
        elif arg == "--label":
            label = args[i + 1] if i + 1 < len(args) else ""
            i += 2
        elif arg.startswith("--label="):
            label = arg[len("--label="):]
            i += 1
        elif arg == "--owner":
            owner = args[i + 1] if i + 1 < len(args) else ""
            i += 2
        elif arg.startswith("--owner="):
            owner = arg[len("--owner="):]
            i += 1
        elif arg == "--target-date":
            target_date = args[i + 1] if i + 1 < len(args) else ""
            i += 2
        elif arg.startswith("--target-date="):
            target_date = arg[len("--target-date="):]
            i += 1
        elif arg == "--force":
            force = True
            i += 1
        else:
            print(f"coordinator-initiative create: unknown flag: {arg}", file=sys.stderr)
            print("  Run coordinator-initiative --help for usage.", file=sys.stderr)
            return 1

    if not id_:
        print("coordinator-initiative create: --id is required.", file=sys.stderr)
        return 1

    # Review: code-reviewer — F2 (P1): parse-time slug validation to prevent path-traversal writes.
    # Accept only ^[a-z0-9][a-z0-9-]*$ — reject any id containing /, \, .., or a leading dot.
    if not _ID_RE.match(id_):
        print(f"coordinator-initiative create: invalid --id '{id_}'", file=sys.stderr)
        print(
            "  Initiative ids must match ^[a-z0-9][a-z0-9-]*$ (lowercase alphanumeric + hyphens, "
            "no leading hyphen).",
            file=sys.stderr,
        )
        print("  Rejected characters: /, \\, .., or a leading dot.", file=sys.stderr)
        print("  Example valid id: my-initiative-2026", file=sys.stderr)
        return 1

    if not label:
        print("coordinator-initiative create: --label is required.", file=sys.stderr)
        return 1

    initiatives_dir = _resolve_initiatives_dir()
    if initiatives_dir is None:
        return 1
    os.makedirs(initiatives_dir, exist_ok=True)

    target = os.path.join(initiatives_dir, f"{id_}.yaml")

    # FAIL-LOUD on existing id (without --force).
    if os.path.isfile(target) and not force:
        print(
            f"coordinator-initiative create: initiative '{id_}' already exists at {target}",
            file=sys.stderr,
        )
        print(
            f"  To attach work to this initiative: coordinator-initiative attach "
            f"<artifact-path> {id_}",
            file=sys.stderr,
        )
        print("  To overwrite the initiative definition: re-run create with --force", file=sys.stderr)
        return 1

    # Atomic write: temp-file + rename prevents partial content on crash.
    tmp = f"{target}.tmp.{os.getpid()}"
    lines = [
        f"id: {_yaml_dquote(id_)}\n",
        f"label: {_yaml_dquote(label)}\n",
        "status: active\n",
    ]
    if owner:
        lines.append(f"owner: {_yaml_dquote(owner)}\n")
    else:
        lines.append("owner: null\n")
    if target_date:
        lines.append(f"target_date: {_yaml_dquote(target_date)}\n")
    else:
        lines.append("target_date: null\n")

    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(lines)
    os.replace(tmp, target)
    print(target)
    return 0


# ── attach ─────────────────────────────────────────────────────────────────────
# Write initiative: <id> to the artifact's YAML frontmatter (plain FK write).
# If the artifact already has an initiative: key it is replaced; otherwise inserted
# before the closing --- of the frontmatter block.
# Verifies the initiative YAML exists before writing (fail-loud if not).
# Write is atomic via temp-file + rename.
#
# `_attach_one` holds the rewrite core (initiative-yaml existence check + frontmatter
# rewrite), shared by the single-pair CLI path (`_cmd_attach`) and the
# `--pairs-file` batch path (`_cmd_attach_batch`) below — both call it once
# `initiatives_dir` is resolved and `artifact_path` is known to exist, so N pairs in
# one invocation run the identical rewrite logic as N separate invocations.
def _attach_one(artifact_path: str, initiative_id: str, initiatives_dir: str) -> tuple[bool, list[str], list[str]]:
    """Attach a single pair given an already-resolved `initiatives_dir` and a
    caller-verified-to-exist `artifact_path`. Returns `(ok, stdout_lines,
    stderr_lines)` — the exact message lines the single-pair CLI path prints
    verbatim on success/failure, and the batch path folds into its own per-pair
    JSON attribution."""
    initiative_yaml = os.path.join(initiatives_dir, f"{initiative_id}.yaml")
    if not os.path.isfile(initiative_yaml):
        return False, [], [
            f"coordinator-initiative attach: initiative '{initiative_id}' not found at "
            f"{initiatives_dir}/{initiative_id}.yaml",
            f"  Create it first: coordinator-initiative create --id {initiative_id} "
            f"--label '<label>'",
        ]

    with open(artifact_path, "r", encoding="utf-8") as f:
        content = f.read()
    original_lines = content.splitlines(keepends=True)

    # Review: code-reviewer — F3 (P1): fail-loud if artifact has no YAML frontmatter block.
    # The awk strategy silently no-ops (copies file unchanged, exits 0) when no opening --- exists,
    # producing a false-success signal. Guard at the boundary before the rewrite runs.
    first_line = original_lines[0].rstrip("\r\n") if original_lines else ""
    if first_line != "---":
        return False, [], [
            f"coordinator-initiative attach: artifact has no YAML frontmatter block: {artifact_path}",
            "  The file must begin with a --- frontmatter opening line.",
            "  Ensure the artifact has a valid YAML frontmatter block before attaching.",
        ]

    # Rewrite the frontmatter — scan inside the frontmatter block (between opening
    # and closing ---).
    #   - Update an existing initiative: line to the new id.
    #   - If no initiative: line exists, inject one before the closing ---.
    in_front = False
    found = False
    out_lines: list[str] = []
    for idx, line in enumerate(original_lines):
        stripped = line.rstrip("\r\n")
        if idx == 0 and re.match(r"^---\s*$", stripped):
            in_front = True
            out_lines.append(line)
            continue
        if in_front and re.match(r"^---\s*$", stripped):
            if not found:
                out_lines.append(f"initiative: {initiative_id}\n")
            in_front = False
            out_lines.append(line)
            continue
        if in_front and re.match(r"^initiative:", stripped):
            out_lines.append(f"initiative: {initiative_id}\n")
            found = True
            continue
        out_lines.append(line)

    new_content = "".join(out_lines)

    # Review: code-reviewer — F3 (P1): detect unterminated-frontmatter / not-found case to
    # prevent false success. Verify the FK line was actually written to the new content.
    if not re.search(rf"^initiative: {re.escape(initiative_id)}", new_content, re.MULTILINE):
        return False, [], [
            f"coordinator-initiative attach: failed to inject initiative FK into {artifact_path}",
            "  The artifact frontmatter may be unterminated (no closing ---).",
        ]

    tmp = f"{artifact_path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_content)
    os.replace(tmp, artifact_path)
    return True, [f"attached: {artifact_path} -> initiative: {initiative_id}"], []


def _cmd_attach(args: list[str]) -> int:
    if args and args[0] == "--pairs-file":
        if len(args) < 2:
            print(
                "coordinator-initiative attach --pairs-file: requires a path argument",
                file=sys.stderr,
            )
            return 1
        return _cmd_attach_batch(args[1])

    if len(args) < 2:
        print(
            "coordinator-initiative attach: requires <artifact-path> <initiative-id>",
            file=sys.stderr,
        )
        print("  Usage: coordinator-initiative attach <artifact-path> <initiative-id>", file=sys.stderr)
        return 1
    artifact_path = args[0]
    initiative_id = args[1]

    if not os.path.isfile(artifact_path):
        print(f"coordinator-initiative attach: artifact not found: {artifact_path}", file=sys.stderr)
        return 1

    # Verify the target initiative exists (fail-loud).
    initiatives_dir = _resolve_initiatives_dir()
    if initiatives_dir is None:
        return 1

    ok, out_lines, err_lines = _attach_one(artifact_path, initiative_id, initiatives_dir)
    for line in out_lines:
        print(line)
    for line in err_lines:
        print(line, file=sys.stderr)
    return 0 if ok else 1


# ── attach --pairs-file ──────────────────────────────────────────────────────────
# Batch form of attach: N (artifact-path, initiative-id) pairs processed in ONE
# process invocation instead of N. Exists to let a caller looping over a mapping
# (coordinator_core.ops.backfill_initiative_fk) collapse a per-pair subprocess
# spawn into a single spawn — the amplification-gate fix this flag was added for.
#
# Pairs-file format mirrors backfill_initiative_fk's own TSV mapping file:
# `artifact_path<TAB>initiative_id` per line; blank lines and `#`-prefixed comment
# lines are skipped (never counted, never emitted as a result line) — the caller is
# expected to have already applied its own comment/blank/malformed-row filtering,
# same as it would for the single-pair path.
#
# initiatives_dir is resolved ONCE for the whole batch (collapsing the single-pair
# path's per-call coordinator_state_root subprocess spawn too), then each pair is
# attached via the shared `_attach_one` core, in pairs-file line order.
#
# Emits exactly one JSON line per non-blank/non-comment pairs-file line, in that
# same order, to stdout — {"artifact_path", "initiative_id", "ok": true, "message"}
# on success, {"artifact_path", "initiative_id", "ok": false, "error"} on failure.
# A caller needing per-pair attribution matches its own pair list against these
# JSON lines POSITIONALLY (one result per input line, same order) rather than by
# re-parsing message text.
#
# Exit code: 0 only if every pair succeeded (matches the single-pair path's
# fail-loud contract); 1 if any pair failed. The exit code alone does not say WHICH
# pair failed — that is what the JSON lines are for.
def _cmd_attach_batch(pairs_file: str) -> int:
    if not os.path.isfile(pairs_file):
        print(
            f"coordinator-initiative attach --pairs-file: file not found: {pairs_file}",
            file=sys.stderr,
        )
        return 1

    initiatives_dir = _resolve_initiatives_dir()
    if initiatives_dir is None:
        return 1

    any_failed = False
    with open(pairs_file, "r", encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            line = raw_line.rstrip("\n").rstrip("\r")
            if not line or line.startswith("#"):
                continue

            if "\t" in line:
                artifact_path, initiative_id = line.split("\t", 1)
            else:
                artifact_path, initiative_id = line, ""
            artifact_path = artifact_path.strip()
            initiative_id = initiative_id.strip()

            if not artifact_path or not initiative_id:
                any_failed = True
                print(json.dumps({
                    "artifact_path": artifact_path,
                    "initiative_id": initiative_id,
                    "ok": False,
                    "error": "malformed pairs-file line (missing artifact_path or initiative_id)",
                }))
                continue

            if not os.path.isfile(artifact_path):
                any_failed = True
                print(json.dumps({
                    "artifact_path": artifact_path,
                    "initiative_id": initiative_id,
                    "ok": False,
                    "error": f"artifact not found: {artifact_path}",
                }))
                continue

            ok, out_lines, err_lines = _attach_one(artifact_path, initiative_id, initiatives_dir)
            record = {"artifact_path": artifact_path, "initiative_id": initiative_id, "ok": ok}
            if ok:
                record["message"] = " ".join(out_lines)
            else:
                any_failed = True
                record["error"] = " ".join(err_lines)
            print(json.dumps(record))

    return 1 if any_failed else 0


# ── list-unattached ────────────────────────────────────────────────────────────
# In-process call into the native `unattached` union lens (coordinator/bin/lib/
# records_query.py -> coordinator_core records.query op, claude-klabauter commit 5709969b).
# De-bash/de-node campaign: this was the last live `node` spawn on the initiative
# surface (execvp into the now-retired query-records.js CLI); repointed to call
# records_query.query_records() directly instead of shelling out.
#
# Flag surface is intentionally NARROW, not a passthrough: the retired wrapper
# forwarded arbitrary query-records.js flags via `*args` to `exec`, but an
# in-process function call cannot honor an open-ended flag list. Caller-set
# verification (grepped every commands/skills/docs/test caller of
# `list-unattached` in this repo, 2026-07-22) found NO production caller passes
# ANY flag to this subcommand — only --format and --limit are supported here,
# matching the retired CLI's own two most load-bearing options and the two
# params query_records() exposes without ambiguity. Any other flag (--root,
# --type, --where, --sort, --since, --older-than, or an unrecognized flag)
# FAILS LOUD rather than being silently dropped or silently mis-mapped — a
# silently-dropped --format would hand a caller `markdown-list` while it
# parses the output as JSON; a silently-dropped filter is worse. See
# records_query.py's own "SILENT-DROP TRAP" docstring section for the exact
# failure mode this guards against.
#
# Defaults (--format markdown-list, --limit 50) are chosen to byte-match the
# retired `node query-records.js --unattached` CLI's own defaults (EM-verified
# 2026-07-22: stdout identical across default/--limit N/--format json/--format
# paths --limit 0 invocations, back-to-back against the same corpus).
#
# Negative-spec: does NOT filter, transform, or re-implement the lens logic —
# the engine (claude-klabauter's records.query op, reached via records_query.py) still
# owns the union/lens computation; this function only shapes the CLI surface
# around a single in-process call.
_LIST_UNATTACHED_FORMATS = ("paths", "json", "markdown-list")


def _cmd_list_unattached(args: list[str]) -> int:
    format_ = "markdown-list"
    limit: int | None = 50

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--format":
            if i + 1 >= len(args):
                print(
                    "coordinator-initiative list-unattached: --format requires a value",
                    file=sys.stderr,
                )
                return 1
            format_ = args[i + 1]
            i += 2
        elif arg.startswith("--format="):
            format_ = arg[len("--format="):]
            i += 1
        elif arg == "--limit":
            if i + 1 >= len(args):
                print(
                    "coordinator-initiative list-unattached: --limit requires a value",
                    file=sys.stderr,
                )
                return 1
            try:
                limit = int(args[i + 1])
            except ValueError:
                print(
                    f"coordinator-initiative list-unattached: --limit expects an integer, "
                    f"got '{args[i + 1]}'",
                    file=sys.stderr,
                )
                return 1
            i += 2
        elif arg.startswith("--limit="):
            raw = arg[len("--limit="):]
            try:
                limit = int(raw)
            except ValueError:
                print(
                    f"coordinator-initiative list-unattached: --limit expects an integer, "
                    f"got '{raw}'",
                    file=sys.stderr,
                )
                return 1
            i += 1
        else:
            print(
                f"coordinator-initiative list-unattached: unsupported flag: {arg}",
                file=sys.stderr,
            )
            print(
                "  Supported flags: --format <paths|json|markdown-list>, --limit <N>",
                file=sys.stderr,
            )
            print(
                "  Flags forwarded by the retired query-records.js exec wrapper (e.g. "
                "--root, --type, --where, --sort, --since, --older-than) are NOT honored "
                "by this native call and are refused rather than silently dropped or "
                "mis-mapped. Use lib/records_query.py's query_records() directly if you "
                "need one of them.",
                file=sys.stderr,
            )
            return 1

    if format_ not in _LIST_UNATTACHED_FORMATS:
        print(
            f"coordinator-initiative list-unattached: unsupported --format '{format_}'",
            file=sys.stderr,
        )
        print(f"  Supported: {', '.join(_LIST_UNATTACHED_FORMATS)}", file=sys.stderr)
        return 1

    if _BIN_LIB_DIR not in sys.path:
        sys.path.insert(0, _BIN_LIB_DIR)
    try:
        from records_query import query_records
    except ImportError as exc:
        print(
            f"coordinator-initiative list-unattached: records_query.py not importable "
            f"from {_BIN_LIB_DIR}",
            file=sys.stderr,
        )
        print(f"  {exc}", file=sys.stderr)
        print("  Ensure the coordinator plugin is fully installed.", file=sys.stderr)
        return 1

    try:
        out = query_records("", "", format_=format_, limit=limit, unattached=True)
    except Exception as exc:  # noqa: BLE001 - CLI boundary: any failure -> diagnostic + exit 1
        print(
            f"coordinator-initiative list-unattached: query_records failed: {exc}",
            file=sys.stderr,
        )
        print(
            "  Native engine broken or unreachable. No legacy query-records.js fallback "
            "exists (de-node cutover, native-primary integrity).",
            file=sys.stderr,
        )
        return 1

    sys.stdout.write(out)
    return 0


# ── Main dispatch ──────────────────────────────────────────────────────────────
def main(argv: list[str]) -> int:
    if not argv:
        _usage()
        return 1

    subcmd = argv[0]
    rest = argv[1:]

    if subcmd == "create":
        return _cmd_create(rest)
    if subcmd == "attach":
        return _cmd_attach(rest)
    if subcmd == "list-unattached":
        return _cmd_list_unattached(rest)
    if subcmd in ("-h", "--help", "help"):
        _usage()
        return 0

    print(f"coordinator-initiative: unknown subcommand '{subcmd}'", file=sys.stderr)
    print("  Valid subcommands: create, attach, list-unattached", file=sys.stderr)
    print("  Run coordinator-initiative --help for usage.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
