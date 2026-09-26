# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""fan-out-dispatch.py — Fan-out wave compiler: overlap pass + scoped executor prompts.

Purpose: Collapse the entire fan-out ceremony into one EM-side call so fanning out is
the path of least resistance. Given a chunk-spec (TSV), runs the file-overlap
intersection pass, then emits N paste-ready scoped dispatch prompts — one per chunk.

Port of: fan-out-dispatch.sh (65e5d199, 2026-07-19) — de-bash-coordinator
campaign, Wave 3 (docs/plans/2026-07-19-debash-coordinator-windows.md). Pure
Python invoked as `python fan-out-dispatch.py`, with a generated Windows
launcher (fan-out-dispatch.cmd) for bare-name invocation. The CLI surface, the
stdout dispatch-block contract, the stderr EM-reminder contract, and every exit code are
byte-for-byte preserved from the bash oracle.

Spec backlink: docs/plans/2026-05-27-fan-out-default-doctrine.md §Chunk 1
Spec backlink (organic-ramp): docs/plans/2026-05-30-organic-ramp-concurrency-doctrine.md §C2
Spec backlink (invariant observers): docs/plans/2026-06-22-invariant-verification-observers.md §C2
Spec backlink (run-report subsume): DoE-claude:pln-universal-subagent-run-report--4250e3 §C5/DEC-6

Input format (TSV, one row per chunk):
  <chunk-id>TAB<brief-one-liner-or-@filepath>TAB<comma-separated-file-paths>

Optional 4th field (pinned-interface existence check — offer-shaped, exit 0 always):
  <chunk-id>TAB<brief>TAB<comma-separated-file-paths>TAB<symbol>@<producer-relative-path>
  If the file exists but the symbol is absent, a NOTE is emitted on stderr advising
  serial predecessor-wave shape. If the file does not exist, a similar file-absent NOTE
  is emitted. In both cases concurrent dispatch proceeds — this is an advisory, not a gate.
  Malformed 4th fields (not matching <symbol>@<path>) emit a NOTE and are skipped.
  A bare `-` in the 4th field is the "no pin" sentinel — use it to reach the 5th field
  below without declaring a pinned interface; it is silently skipped (no NOTE).
  A row supplying a 5th field MUST supply a non-empty 4th field (a real pin or `-`) —
  an empty 4th field with a 5th field present is a hard parse error (exit 1), not a
  silent misparse: see the raw-line pre-collapse check ahead of tab-collapse below.

Optional 5th field (change_kind — gates the candidate-restatement push, see below):
  <chunk-id>TAB<brief>TAB<comma-separated-file-paths>TAB<pin-or-`-`>TAB<change_kind>
  When change_kind is `wiki-append` or `wiki-new`, this compiler calls
  `coordinator_core.learn_lessons_assemble.generate_candidates` against the chunk's
  first in-scope file (the wiki target) and the chunk's resolved brief (the incoming
  text), and injects the result into the executor's dispatch block as
  `candidate_restatements: [{line, excerpt}]` — computed and pushed, never a field the
  executor must run something to obtain. Any other change_kind value (or an absent 5th
  field) emits no such field and makes no call. Generator failure (unresolvable claude-klabauter
  root, import error, or an exception from the call) degrades to an empty list rather
  than blocking the row — see `_generate_candidate_restatements`. The "first file is the
  wiki target" convention is advisory-checked, not silently trusted: a non-`.md` first
  file on a wiki-append/wiki-new row emits a NOTE (does not block the row).

Usage:
  printf 'chunk-A\tFix the auth module\tauth.py,auth_test.py\n' | python fan-out-dispatch.py
  python fan-out-dispatch.py --spec wave.tsv

Exit codes:
  0 — success, N blocks emitted to stdout
  1 — spec/overlap error (with explanatory message on stderr, no partial output)
  2 — usage or environment error

Environment: none required. Resolves snippet paths relative to script location.

Negative-spec (de-bash campaign): this module NEVER re-wraps into a shell. The path
resolution, exit-code translation, and arg-marshalling the bash forwarder carried are
promoted INTO Python. The spawn-time run-report provisioner is called IN-PROCESS
(import coordinator_core.subagent_sandbox.provision_report), never shelled out.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _resolve_plugin_root() -> str:
    """Resolve the coordinator root sibling DATA dirs (snippets/, subagent-sandbox-
    policy.yaml) live under — CLAUDE_PLUGIN_ROOT override always wins; otherwise the
    parent of the resolved snippets/ data dir (co-located or DoE-resident per
    `coordinator_data_root.data_root()`), since that parent IS the coordinator root
    under either layout. Mirrors `snippet-registry`'s `_resolve_plugin_root()`.

    Historical: PLUGIN_ROOT used to be a bare `os.path.dirname(SCRIPT_DIR)` walk, which
    broke once the 2026-07-22 executable-surface migration split snippets/ (DoE-resident)
    away from this script (claude-klabauter-resident) — see coordinator_data_root.py's
    module docstring. Resolved via the shared two-rung resolver instead of reimplementing
    the DOE_ROOT chain here (negative-spec in that module).
    """
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return env
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from coordinator_data_root import data_root

    return str(data_root("snippets").parent)


# Module ATTRIBUTE, restored as a lazy one. `PLUGIN_ROOT` was a module-scope
# constant (`PLUGIN_ROOT = _resolve_plugin_root()`) until c992b99f7 deferred this
# `fan_out_dispatch.PLUGIN_ROOT` were never considered, and
# PLUGIN_ROOT`, taking every review-dispatch sidecar with it.
# CLAUDE_PLUGIN_ROOT, and a cached value would pin the first reader's
def __getattr__(name: str) -> str:
    if name == "PLUGIN_ROOT":
        return _resolve_plugin_root()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _usage() -> "int":
    _err(
        "Usage: fan-out-dispatch.py [--spec <file>] [--plan <path>]\n"
        "       printf 'id\\tbrief\\tfile1,file2\\n' | fan-out-dispatch.py [--plan <path>]\n"
        "\n"
        "Input: TSV on stdin or --spec <file>, one row per chunk:\n"
        "  <chunk-id>TAB<brief-one-liner-or-@filepath>TAB<comma-separated-file-paths>\n"
        "\n"
        "Options:\n"
        "  --plan <path>   Path to the plan document driving this wave. When provided,\n"
        "                  fan-out-dispatch provisions a per-chunk run-report sidecar\n"
        "                  via claude-klabauter's universal subagent-sandbox provisioner\n"
        "                  (deterministic provision_key=<plan-slug>.<chunk-id>, DEC-6)\n"
        "                  and emits sidecar_path: in each executor brief. Fails open\n"
        "                  (no sidecar_path: line) if the provisioner is unresolvable.\n"
        "\n"
        "Output: N paste-ready executor dispatch prompts to stdout.\n"
        "        EM reminders (concurrency cap, commit discipline) to stderr.\n"
        "\n"
        "Errors on: file-overlap between chunks, malformed rows, non-git-repo cwd."
    )
    return 2


def _strip_html_comment_header(template: str) -> str:
    """Strip HTML-comment blocks + leading blank lines, mirroring the bash oracle.

    Any line that STARTS with `<!--` opens a comment block consumed until a line
    containing `-->`; leading blank lines before the first body line are dropped.
    (Faithful port of fan-out-dispatch.sh's PEER_SCOPE_BODY / PLAN_DOC_OOS_BODY loops.)
    """
    body_lines: List[str] = []
    in_html_comment = False
    leading_blank = True
    for tline in template.split("\n"):
        if tline.startswith("<!--") and not in_html_comment:
            in_html_comment = True
            if "-->" in tline:
                in_html_comment = False
            continue
        if in_html_comment:
            if "-->" in tline:
                in_html_comment = False
            continue
        if leading_blank and tline == "":
            continue
        leading_blank = False
        body_lines.append(tline)
    return "\n".join(body_lines)


def _resolve_claude_klabauter_root_silent() -> Optional[str]:
    try:
        sys.path.insert(0, os.path.join(SCRIPT_DIR, "lib"))
        import cc_invoke  # noqa: E402  (path injected above)

        return cc_invoke.ensure_engine_on_path(__file__)
    except Exception:
        return None


def _no_console_kw() -> Dict[str, Any]:
    try:
        claude_klabauter_root = _resolve_claude_klabauter_root_silent()
        if claude_klabauter_root and claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        from coordinator_core.win_portability import no_console_creationflags

        return no_console_creationflags()
    except Exception:
        return {}


_WIKI_CHANGE_KINDS = ("wiki-append", "wiki-new")


def _generate_candidate_restatements(
    target_path: str, incoming_text: str
) -> "List[Dict[str, Any]]":
    try:
        claude_klabauter_root = _resolve_claude_klabauter_root_silent()
        if not claude_klabauter_root or not os.path.isdir(claude_klabauter_root):
            raise RuntimeError(f"claude-klabauter root unresolved (got {claude_klabauter_root!r})")
        if claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        from coordinator_core.learn_lessons_assemble import generate_candidates

        candidates, _meta = generate_candidates(target_path, incoming_text, repo_root=None)
        return [{"line": c["line"], "excerpt": c["excerpt"]} for c in candidates]
    except Exception as exc:
        _err(
            f"NOTE: candidate-restatement generation failed for '{target_path}' — "
            f"emitting an empty candidate_restatements list rather than blocking dispatch "
            f"({exc})."
        )
        return []


def _derive_plan_slug(plan_path: str) -> str:
    """Reduce a plan path to its DEC-6 slug: basename with the leading
    YYYY-MM-DD- date prefix stripped and a trailing .md suffix dropped.

    Returns "" when the result is empty after stripping — callers decide how to
    handle that (this function raises nothing itself). Factored out of
    `_provision_sidecars` so `coordinator/bin/provision-sidecar.py` can derive
    the same `provision_key = f"{plan_slug}.{chunk_id}"` convention from
    `--plan`/`--chunk` without a second copy of this regex (see that script's
    module docstring, hard design call 2).
    """
    plan_basename = os.path.basename(plan_path)
    plan_slug = re.sub(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}-", "", plan_basename)
    if plan_slug.endswith(".md"):
        plan_slug = plan_slug[:-3]
    return plan_slug


def _provision_sidecars(
    plan_path: str,
    chunk_ids: List[str],
    plugin_root: str,
) -> "tuple[str, List[str]]":
    plan_slug = _derive_plan_slug(plan_path)
    if not plan_slug:
        _err(f"fan-out-dispatch.py: ERROR — could not derive plan-slug from: {plan_path}")
        raise SystemExit(2)

    sidecar_paths = ["" for _ in chunk_ids]

    claude_klabauter_root = _resolve_claude_klabauter_root_silent()
    if not claude_klabauter_root or not os.path.isdir(claude_klabauter_root):
        return plan_slug, sidecar_paths
    module_dir = os.path.join(claude_klabauter_root, "coordinator_core", "subagent_sandbox")
    if not os.path.isdir(module_dir):
        return plan_slug, sidecar_paths

    target_git_root = ""
    try:
        if claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        from coordinator_core.git.repo_root import show_toplevel

        target_git_root = show_toplevel() or ""
    except Exception:
        target_git_root = ""
    if not target_git_root:
        return plan_slug, sidecar_paths

    try:
        if claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        from coordinator_core.subagent_sandbox import provision_report
    except Exception:
        return plan_slug, sidecar_paths

    session_id = (
        os.environ.get("COORDINATOR_SESSION_ID")
        or os.environ.get("CLAUDE_SESSION_ID")
        or os.environ.get("CLAUDE_CODE_SESSION_ID")
        or ""
    )
    policy_path = os.path.join(plugin_root, "subagent-sandbox-policy.yaml")

    for i, cid in enumerate(chunk_ids):
        provision_key = f"{plan_slug}.{cid}"
        payload = {
            "agent_type": "coordinator:executor",
            "subagent_type": "coordinator:executor",
            "session_id": session_id,
            "provision_key": provision_key,
        }
        try:
            path = provision_report._provision(payload, policy_path, target_git_root)
        except Exception:
            path = None
        sidecar_paths[i] = path or ""

    return plan_slug, sidecar_paths


def _machine_local_get(key: str) -> str:
    """Best-effort `machine-local get <key>`; empty string on any failure.

    `shutil.which` is bareword ("machine-local", no extension) intentionally —
    it IS PATHEXT-aware on Windows and resolves `machine-local.cmd` on PATH
    unassisted, so this is not the F7 hazard (unlike the extensionless-path
    probes in the other three defects fixed alongside this one). What WAS
    broken here is the bare `except Exception: pass`: it cannot distinguish
    "machine-local not installed" (expected, degrade silently) from "the
    subprocess call itself crashed" (the exact ambiguity that made the
    original F7 bugs invisible for weeks) — narrowed to the exceptions
    `subprocess.run` can actually raise here, with a stderr breadcrumb on the
    crash path. Still degrades to empty string either way — never fatal.

    `SubprocessError` (not just `TimeoutExpired`) future-proofs against other
    subprocess-family exceptions; `UnicodeDecodeError` is caught separately
    because `text=True` decodes child stdout/stderr using the locale
    encoding and can raise on non-UTF-8 output from a third-party binary —
    neither is a subclass of the other. (Review: code-reviewer — Finding 3,
    2026-07-22: the prior `(OSError, subprocess.TimeoutExpired)` tuple did
    not catch `UnicodeDecodeError`, silently reopening the "unexpected
    exception propagates" failure mode this docstring says doesn't exist.)
    """
    import shutil

    exe = shutil.which("machine-local")
    if not exe:
        return ""
    try:
        proc = subprocess.run(
            [exe, "get", key],
            capture_output=True,
            text=True,
            timeout=5,
            **_no_console_kw(),
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError) as exc:
        print(f"fan-out-dispatch: machine-local get {key!r} failed: {exc}", file=sys.stderr)
    return ""


def _memory_probe() -> str:
    probe = os.path.join(SCRIPT_DIR, "probe-memory-headroom.py")
    if not os.path.isfile(probe):
        return ""
    try:
        import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
        from cc_invoke import child_env  # noqa: E402

        proc = subprocess.run(
            [sys.executable, probe],
            capture_output=True,
            text=True,
            timeout=10,
            env=child_env(),
            **_no_console_kw(),
        )
        return proc.stdout
    except Exception:
        return ""


def _probe_field(probe_out: str, key: str) -> str:
    for line in probe_out.split("\n"):
        idx = line.find("=")
        if idx >= 0 and line[:idx] == key:
            return line[idx + 1:]
    return ""


def _fmt_headroom_mb(mb: int) -> str:
    if mb >= 1024:
        return f"≈{mb // 1024} GB"
    return f"≈{mb} MB"


def _is_uint(s: str) -> bool:
    return bool(re.fullmatch(r"[0-9]+", s))


def main(argv: List[str]) -> int:
    plugin_root = _resolve_plugin_root()
    peer_scope_snippet = os.path.join(plugin_root, "snippets", "peer-scope-block.md")
    plan_doc_oos_snippet = os.path.join(plugin_root, "snippets", "plan-doc-oos-block.md")
    text_only_snippet = os.path.join(plugin_root, "snippets", "text-only-recovery-preamble.md")

    spec_file = ""
    plan_path = ""

    args = list(argv)
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--help", "-h"):
            return _usage()
        elif a == "--spec":
            if i + 1 >= len(args) or args[i + 1] == "":
                _err("fan-out-dispatch.py: --spec requires a file argument")
                return 2
            spec_file = args[i + 1]
            i += 2
        elif a == "--plan":
            if i + 1 >= len(args) or args[i + 1] == "":
                _err("fan-out-dispatch.py: --plan requires a file argument")
                return 2
            plan_path = args[i + 1]
            i += 2
        else:
            _err(f"fan-out-dispatch.py: unknown argument: {a}")
            return 2

    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            **_no_console_kw(),
        )
    except Exception:
        inside = None
    if inside is None or inside.returncode != 0:
        _err("fan-out-dispatch.py: ERROR — not inside a git repository.")
        _err("  Remediation: run from within your git working tree (e.g., cd /path/to/repo).")
        return 2

    branch_proc = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True,
        text=True,
        **_no_console_kw(),
    )
    expected_branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else ""
    if not expected_branch:
        _err("fan-out-dispatch.py: ERROR — could not determine current branch (detached HEAD?).")
        _err("  Remediation: checkout a named branch before running fan-out-dispatch.")
        return 2

    if spec_file:
        if not os.path.isfile(spec_file):
            _err(f"fan-out-dispatch.py: spec file not found: {spec_file}")
            return 2
        with open(spec_file, "r", encoding="utf-8") as f:
            spec_content = f.read()
    else:
        spec_content = sys.stdin.read()

    if spec_content == "":
        _err("fan-out-dispatch.py: empty spec — no chunks to process")
        return 2

    for path, label in (
        (peer_scope_snippet, "peer-scope"),
        (plan_doc_oos_snippet, "plan-doc-oos"),
        (text_only_snippet, "text-only-recovery-preamble"),
    ):
        if not os.path.isfile(path):
            _err(f"fan-out-dispatch.py: ERROR — {label} snippet not found: {path}")
            return 2
    with open(peer_scope_snippet, "r", encoding="utf-8") as f:
        peer_scope_template = f.read().rstrip("\n")
    with open(plan_doc_oos_snippet, "r", encoding="utf-8") as f:
        plan_doc_oos_template = f.read().rstrip("\n")
    with open(text_only_snippet, "r", encoding="utf-8") as f:
        text_only_preamble = f.read().rstrip("\n")

    chunk_ids: List[str] = []
    chunk_briefs: List[str] = []
    chunk_files_raw: List[str] = []
    chunk_pins: List[str] = []
    chunk_change_kinds: List[str] = []

    row_num = 0
    for line in spec_content.split("\n"):
        if line == "":
            continue
        if re.match(r"^[ \t]*#", line):
            continue

        row_num += 1

        raw_fields = line.split("\t")
        if len(raw_fields) >= 5 and raw_fields[3] == "":
            _err(
                f"fan-out-dispatch.py: ERROR — malformed row {row_num} "
                f"(chunk '{raw_fields[0] if raw_fields else ''}'): a 5th (change_kind) field "
                "was supplied but the 4th (pin) field is empty. Use the `-` sentinel in the "
                "4th field to reach a 5th field without declaring a pinned interface — an "
                "empty 4th field is NOT equivalent to `-` and will misparse."
            )
            _err(f"  Row content: {line}")
            _err("  No output emitted.")
            return 1

        fields = [f for f in line.split("\t") if f != ""]

        if len(fields) < 3 or len(fields) > 5:
            _err(
                f"fan-out-dispatch.py: ERROR — malformed row {row_num}: "
                f"expected 3, 4, or 5 tab-separated fields, got {len(fields)}."
            )
            _err(f"  Row content: {line}")
            _err("  No output emitted.")
            return 1

        chunk_id = fields[0]
        brief_raw = fields[1]
        files_raw = fields[2]
        pin_raw = fields[3] if len(fields) >= 4 else ""
        change_kind_raw = fields[4] if len(fields) >= 5 else ""

        if chunk_id == "":
            _err(f"fan-out-dispatch.py: ERROR — malformed row {row_num}: chunk-id field is empty.")
            _err("  No output emitted.")
            return 1
        if brief_raw == "":
            _err(
                f"fan-out-dispatch.py: ERROR — malformed row {row_num} "
                f"(chunk '{chunk_id}'): brief field is empty."
            )
            _err("  No output emitted.")
            return 1
        if files_raw == "":
            _err(
                f"fan-out-dispatch.py: ERROR — malformed row {row_num} "
                f"(chunk '{chunk_id}'): file-paths field is empty."
            )
            _err("  No output emitted.")
            return 1

        brief = brief_raw
        if brief_raw.startswith("@"):
            brief_file = brief_raw[1:]
            if not os.path.isfile(brief_file):
                _err(
                    f"fan-out-dispatch.py: ERROR — row {row_num} (chunk '{chunk_id}'): "
                    f"@file brief references non-existent file: {brief_file}"
                )
                _err("  No output emitted.")
                return 1
            with open(brief_file, "r", encoding="utf-8") as bf:
                brief = bf.read().rstrip("\n")
            if brief == "":
                _err(
                    f"fan-out-dispatch.py: ERROR — row {row_num} (chunk '{chunk_id}'): "
                    f"@file brief file is empty: {brief_file}"
                )
                _err("  No output emitted.")
                return 1

        chunk_ids.append(chunk_id)
        chunk_briefs.append(brief)
        chunk_files_raw.append(files_raw)
        chunk_pins.append(pin_raw)
        chunk_change_kinds.append(change_kind_raw)

    chunk_count = len(chunk_ids)
    if chunk_count == 0:
        _err("fan-out-dispatch.py: no valid chunk rows found in spec")
        return 2

    chunk_files_lists: List[List[str]] = []
    for idx, chunk_id in enumerate(chunk_ids):
        raw = chunk_files_raw[idx]
        joined: List[str] = []
        for p in raw.split(","):
            p = p.strip()
            if p == "":
                _err(
                    f"fan-out-dispatch.py: ERROR — chunk '{chunk_id}': "
                    "empty path entry in file list after splitting on commas."
                )
                _err(f"  Raw file field: {raw}")
                _err("  No output emitted.")
                return 1
            joined.append(p)
        chunk_files_lists.append(joined)

    for idx in range(chunk_count):
        pin = chunk_pins[idx]
        if pin == "" or pin == "-":
            continue
        at = pin.find("@")
        pin_symbol = pin[:at] if at >= 0 else pin
        pin_path = pin[at + 1:] if at >= 0 else ""
        if pin_symbol == "" or pin_path == "" or at < 0:
            _err(
                f"NOTE: chunk '{chunk_ids[idx]}' has a malformed 4th-column pin "
                f"(expected <symbol>@<path>, got '{pin}') — skipping interface-existence "
                "check for this chunk."
            )
            continue

        if os.path.isfile(pin_path):
            try:
                with open(pin_path, "r", encoding="utf-8", errors="replace") as pf:
                    contents = pf.read()
            except Exception:
                contents = ""
            if pin_symbol not in contents:
                _err(
                    f"NOTE: chunk '{chunk_ids[idx]}' declares a pinned interface "
                    f"'{pin_symbol}' but that symbol was NOT found in '{pin_path}'. The "
                    "producer may not have written this interface yet. Consider using a "
                    "serial predecessor-wave shape instead: land the producer first (verify "
                    f"'{pin_symbol}' is present in '{pin_path}'), then dispatch this consumer "
                    "chunk. Concurrent dispatch proceeds — this is an advisory, not a gate. "
                    "See docs/wiki/dispatching-parallel-agents.md § Read-Overlap Is NOT "
                    "Write-Overlap (§ Author vs. verify)."
                )
        else:
            _err(
                f"NOTE: chunk '{chunk_ids[idx]}' declares a pinned interface '{pin_symbol}' "
                f"against '{pin_path}' but that file does not exist. The producer may not have "
                "written it yet. Consider using a serial predecessor-wave shape: land the "
                "producer first, then dispatch this consumer chunk. Concurrent dispatch "
                "proceeds — this is an advisory, not a gate. See "
                "docs/wiki/dispatching-parallel-agents.md § Dispatch-Gate Taxonomy."
            )

    overlap_found = False
    overlap_report = ""
    for a in range(chunk_count):
        id_i = chunk_ids[a]
        files_i = chunk_files_lists[a]
        for b in range(chunk_count):
            if b <= a:
                continue
            id_j = chunk_ids[b]
            files_j = chunk_files_lists[b]
            for fi_path in files_i:
                for fj_path in files_j:
                    if fi_path == fj_path:
                        overlap_found = True
                        overlap_report += (
                            f"  File '{fi_path}' claimed by both '{id_i}' and '{id_j}'\n"
                        )

    if overlap_found:
        _err("fan-out-dispatch.py: ERROR — file overlap detected between chunks:")
        sys.stderr.write(overlap_report)
        _err("  Action required: merge the overlapping chunks into one executor OR sequence them")
        _err("  (serial dispatch with EM verification between). Never silently pick.")
        _err("  No output emitted.")
        return 1

    chunk_candidate_restatements: "List[Optional[List[Dict[str, Any]]]]" = [None for _ in chunk_ids]
    for idx in range(chunk_count):
        if chunk_change_kinds[idx] not in _WIKI_CHANGE_KINDS:
            continue
        target_path = chunk_files_lists[idx][0]
        if not target_path.endswith(".md"):
            _err(
                f"NOTE: chunk '{chunk_ids[idx]}' has change_kind '{chunk_change_kinds[idx]}' "
                f"but its first in-scope file ('{target_path}') is not a .md file. This "
                "compiler always computes candidate_restatements against the FIRST file in "
                "the chunk's file list — if that isn't the wiki target, put the wiki file "
                "first in the comma-separated list for this row."
            )
        incoming_text = chunk_briefs[idx]
        chunk_candidate_restatements[idx] = _generate_candidate_restatements(
            target_path, incoming_text
        )

    plan_slug = ""
    chunk_sidecar_paths: List[str] = ["" for _ in chunk_ids]
    if plan_path:
        plan_slug, chunk_sidecar_paths = _provision_sidecars(plan_path, chunk_ids, plugin_root)

    large_wave_threshold_raw = os.environ.get("LARGE_WAVE_THRESHOLD", "")
    if large_wave_threshold_raw == "":
        large_wave_threshold_raw = _machine_local_get("fan_out.large_wave_threshold")
    if large_wave_threshold_raw == "" or not _is_uint(large_wave_threshold_raw):
        large_wave_threshold = 16
    else:
        large_wave_threshold = int(large_wave_threshold_raw)

    probe_out = _memory_probe()
    ram_avail_mb = _probe_field(probe_out, "ram_available_mb")
    vram_free_mb = _probe_field(probe_out, "vram_free_mb")

    ram_floor_raw = os.environ.get("FAN_OUT_MIN_RAM_HEADROOM_MB", "")
    if ram_floor_raw == "":
        ram_floor_raw = _machine_local_get("fan_out.min_ram_headroom_mb")
    ram_floor_mb = int(ram_floor_raw) if _is_uint(ram_floor_raw) else 4096

    vram_floor_raw = os.environ.get("FAN_OUT_MIN_VRAM_HEADROOM_MB", "")
    if vram_floor_raw == "":
        vram_floor_raw = _machine_local_get("fan_out.min_vram_headroom_mb")
    vram_floor_mb = int(vram_floor_raw) if _is_uint(vram_floor_raw) else 2048

    headroom_readout = ""
    if _is_uint(ram_avail_mb):
        headroom_readout = f"RAM free {_fmt_headroom_mb(int(ram_avail_mb))}"
    if _is_uint(vram_free_mb):
        if headroom_readout:
            headroom_readout += ", "
        headroom_readout += f"VRAM free {_fmt_headroom_mb(int(vram_free_mb))}"

    out = sys.stdout

    if chunk_count >= large_wave_threshold:
        cores_note = (
            f"NOTE: {chunk_count} concurrent agents is a large wave (≈3× cores) — a speed "
            "advisory, NOT a cap: past here CPU scheduling contention may start tapering "
            "throughput, but CPU/GPU parallelize fine, so ramp pilot→expand and watch RAM/VRAM "
            "commit more than CPU. If any chunk is an orchestrator, count its fanout. Your "
            "call, not a PM gate. See § Concurrency Budget."
        )
        if headroom_readout:
            cores_note += f" Live headroom now: {headroom_readout}."
        out.write(cores_note + "\n")

    ram_tight = _is_uint(ram_avail_mb) and int(ram_avail_mb) < ram_floor_mb
    vram_tight = _is_uint(vram_free_mb) and int(vram_free_mb) < vram_floor_mb
    if ram_tight or vram_tight:
        out.write(
            f"NOTE: memory headroom is tight ({headroom_readout or 'unknown'}) — memory commit, "
            "not core count, is what actually degrades this machine. Before launching "
            f"{chunk_count} agents, ramp pilot→expand and watch the headroom drop per agent; a "
            "GPU/CUDA-heavy chunk can commit far more than its share. Floor: RAM "
            f"{ram_floor_mb} MB / VRAM {vram_floor_mb} MB (override via "
            "FAN_OUT_MIN_{RAM,VRAM}_HEADROOM_MB). Your call, not a PM gate. See § Concurrency Budget.\n"
        )

    fat_chunk_threshold_raw = os.environ.get("FAT_CHUNK_THRESHOLD", "4")
    fat_chunk_threshold = int(fat_chunk_threshold_raw) if _is_uint(fat_chunk_threshold_raw) else 4
    for idx in range(chunk_count):
        fc_count = len(chunk_files_lists[idx])
        if fc_count >= fat_chunk_threshold:
            out.write(
                f"NOTE: chunk '{chunk_ids[idx]}' owns {fc_count} files — confirm this is ONE "
                "coherent surface. If these are independent deliverables with disjoint write "
                "targets, split into separate chunks (read-overlap and a pinned import interface "
                "are NOT reasons to keep them in one executor). See "
                "docs/wiki/dispatching-parallel-agents.md, Step 0.5 of the fan-out methodology.\n"
            )

    sys.stderr.write(
        "\n"
        "--- fan-out-dispatch.py: EM REMINDERS (not for executor prompts) ---\n"
        "Concurrency: ramp pilot→expand — launch a pilot, observe this session's\n"
        "responsiveness, expand. Maximize hardware utilization; the cores-scaled NOTE\n"
        "(≈3× cores) is a speed-taper advisory, NOT a cap — a CPU time-slices far more\n"
        "than (cores) tasks, so past the threshold you pay scheduling contention, you do\n"
        "not stop. CPU/GPU parallelize, so the dimension to watch is memory commit\n"
        "(RAM/VRAM), not core count — for a live readout run bin/probe-memory-headroom.py\n"
        "(--human), the memory-commit-aware signal behind the headroom NOTEs above.\n"
        "If any chunk is an orchestrator (spawning sub-agents),\n"
        "count its fanout toward your wave size; leaf workers (executors, reviewers, simple\n"
        "file-scoped scouts) spawn nothing. Note: the platform's min(16, cores-2) cap\n"
        "applies ONLY inside Workflow scripts, NOT on this manual fan-out path — organic\n"
        "ramp is the guard here, by design.\n"
        "\n"
        "Commit discipline: YOU (the EM) commit serially after the wave completes using plain\n"
        "scoped git:  git add -- <file1> <file2> ...  &&  git commit -m \"<subject>\"\n"
        "Executors do NOT commit. No commit step appears in the emitted executor prompts.\n"
        "\n"
        f"Branch captured: {expected_branch}\n"
        f"Chunks in this wave: {chunk_count}\n"
        "---\n"
        "\n"
    )

    peer_scope_body = _strip_html_comment_header(peer_scope_template)
    plan_doc_oos_body = _strip_html_comment_header(plan_doc_oos_template)

    for idx in range(chunk_count):
        chunk_id = chunk_ids[idx]
        brief = chunk_briefs[idx]
        own_files = chunk_files_lists[idx]

        peer_lines_parts: List[str] = []
        for j in range(chunk_count):
            if j == idx:
                continue
            peer_id = chunk_ids[j]
            peer_files_display = ", ".join(chunk_files_lists[j])
            peer_lines_parts.append(
                f"- {peer_id} (files: {peer_files_display}) — concurrent executor handles this"
            )
        peer_lines = "\n".join(peer_lines_parts)

        peer_scope_filled = peer_scope_body.replace("{{peer_chunks}}", peer_lines)

        out.write("\n")
        out.write(f"# ===== EXECUTOR DISPATCH BLOCK: {chunk_id} =====\n")
        out.write("```\n")
        out.write(f"## Chunk: {chunk_id}\n")
        out.write("\n")
        out.write("### Brief\n")
        out.write(f"{brief}\n")
        out.write("\n")
        out.write("### In-scope\n")
        out.write("Files this executor owns:\n")
        for f in own_files:
            out.write(f"- {f}\n")
        out.write("\n")
        out.write(f"{peer_scope_filled}\n")
        out.write("\n")
        out.write(f"{plan_doc_oos_body}\n")
        out.write("\n")
        out.write("### Destructive-action prohibition\n")
        out.write("Do NOT delete, force-push, reset --hard, or run any destructive git operation.\n")
        out.write(
            "Do NOT stage, push, or commit any files. The EM commits serially after the wave "
            "with plain scoped git.\n"
        )
        out.write("Do NOT modify any file outside the In-scope list above.\n")
        out.write("\n")
        out.write("### Disk-first verification preamble\n")
        out.write(f"{text_only_preamble}\n")
        out.write("\n")
        if plan_slug and chunk_sidecar_paths[idx]:
            out.write(f"sidecar_path: {chunk_sidecar_paths[idx]}\n")
        candidates = chunk_candidate_restatements[idx]
        if candidates is not None:
            out.write(f"candidate_restatements: {json.dumps(candidates)}\n")
        out.write("```\n")
        out.write(f"# ===== END BLOCK: {chunk_id} =====\n")
        out.write("\n")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
        os._exit(0)
