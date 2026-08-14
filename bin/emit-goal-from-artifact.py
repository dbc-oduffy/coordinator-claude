# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""emit-goal-from-artifact.py — emit authored goal artifacts -> cockpit via DR-210 facade.

Purpose: reads per-repo state/goals/*.yaml YAML frontmatter, maps each goal to
append-goal-event.py params, and invokes append-goal-event.py as a subprocess
(the DR-210 single-writer facade) for each goal. Subprocess-invoke is the DEFAULT
writer — not a fallback. A parallel direct-append would reintroduce dual-writer
divergence that DR-210 consolidated.

Identity chain (executor pin, plan C7):
    artifact frontmatter `id` == wire `goal_id` == cockpit (kind, id) composite node key.
    The artifact id is passed verbatim as goal_id; no new id generated at emit time.

Provenance: source_kind="coordinator_artifact", path="state/goals/<file>.yaml".

Spec backlink: DoE-claude:pln-per-repo-okr-goal-setting-syst-80bced § C7
Spec backlink: docs/plans/2026-06-22-cockpit-tc-3-coordinator-emission.md § DR-210
Spec backlink: DoE-claude:pln-close-the-weekly-goal-loop-yam-d31316 § C11 (thin passthrough
    of weekly_perceptible / parent_goal_id / key_results_status / goal_id to
    append-goal-event.py; claude-klabauter's artifact.emit carries the wire projection + engine)

Usage:
    emit-goal-from-artifact.py [--root <repo-root>] [--repo <owner/repo>] [--dry-run]

Options:
    --root <path>    Repo root to scan for state/goals/*.yaml (default: cwd git root)
    --repo <slug>    Override repo slug passed to append-goal-event.py (default: derived)
    --dry-run        Print append-goal-event.py invocations without executing them

Exit codes:
    0  -- all goals emitted successfully (or --dry-run completed)
    1  -- fatal precondition (root unresolvable, append-goal-event.py missing, etc.)
    2  -- one or more goals failed to emit (partial success; errors logged to stderr)

Port of: emit-goal-from-artifact.sh (3d785330, 2026-07-21) — Windows de-bash
campaign (Plan C, Wave E3-d, per-op port). The bash emitter required `jq` on
PATH for every JSON build (key_results_status[] projection) and
subprocess-invoked read-frontmatter-field.py
per field per goal. Fix-in-port (DR-059): drops the jq dependency entirely — JSON
projection uses the stdlib `json` module — and imports
coordinator_core.ops.read_frontmatter_field.read_frontmatter_field directly
in-process (via cc_invoke.resolve_engine_root() for CLAUDE_KLABAUTER_ROOT resolution,
matching every other Windows-campaign per-op port) instead of subprocess-spawning
read-frontmatter-field.py once per field per goal artifact. append-goal-event.py
itself stays a subprocess invocation — that IS the DR-210 single-writer facade
boundary, not an incidental transport choice.

Negative-spec: as of 2026-07-25 this module DOES forward the artifact->wire
status mapping (see _map_status()/_STATUS_MAP below) via append-goal-event.py's
--status flag. It still does NOT expose --provenance (that half of the
original bash oracle's dead computation remains deferred). The identity-chain
adapter (embedding the artifact id as a --text prefix so append-goal-event.py's
deterministic content-hash goal_id stays stable across re-runs) is preserved
byte-for-byte from the bash oracle.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_BIN_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import cc_invoke  # noqa: E402


def _no_console_kw() -> dict:
    """Lazily resolve claude_klabauter_root onto sys.path, then splat the canonical
    no-console-window kwarg (mirrors ``_resolve_read_frontmatter_field``'s
    own lazy-import posture).

    Unguarded here by design: this function has no local try/except, so a
    resolution failure propagates as `resolve_engine_root`'s own RuntimeError
    (carrying its remediation text) to the caller — both call sites
    (`_resolve_repo_root`, `_derive_repo_slug`) already catch `RuntimeError`
    as part of a broader except tuple. `ensure_engine_on_path` would swallow
    that RuntimeError into a silent None here, losing the remediation text
    before either caller's except clause ever saw it.
    """
    cc_invoke.require_engine_on_path(__file__)
    from coordinator_core.win_portability import no_console_creationflags

    return no_console_creationflags()


_STATUS_MAP = {
    "active": "active",
    "achieved": "done",
    "abandoned": "dropped",
}


def _map_status(artifact_status: str) -> str:
    # Pass through unknown values; append-goal-event.py will validate or route.
    return _STATUS_MAP.get(artifact_status, artifact_status)


def _resolve_read_frontmatter_field():
    """Import coordinator_core.ops.read_frontmatter_field.read_frontmatter_field.

    Raises RuntimeError on CLAUDE_KLABAUTER_ROOT/import failure — mapped to a fatal
    precondition (exit 1) by main(), matching the bash oracle's jq-absent /
    helper-not-found fatal-precondition class.
    """
    cc_invoke.require_engine_on_path(__file__)
    from coordinator_core.ops.read_frontmatter_field import read_frontmatter_field

    return read_frontmatter_field


def _resolve_repo_root(root_override: str) -> str | None:
    if root_override:
        if os.path.isdir(root_override):
            return os.path.abspath(root_override)
        return None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            **_no_console_kw(),
        )
    except (OSError, RuntimeError, ImportError):
        return None
    root = result.stdout.strip()
    if result.returncode != 0 or not root:
        return None
    return root


def _derive_repo_slug(git_root: str, repo_override: str) -> str:
    if repo_override:
        return repo_override
    try:
        result = subprocess.run(
            ["git", "-C", git_root, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            **_no_console_kw(),
        )
    except (OSError, RuntimeError, ImportError):
        return "local"
    if result.returncode != 0:
        return "local"
    url = result.stdout.strip()
    if not url:
        return "local"
    # Mirrors the bash oracle's `sed -E 's#.*github.com[/:]##; s#\.git$##'`.
    slug = re.sub(r"^.*github\.com[/:]", "", url)
    slug = re.sub(r"\.git$", "", slug)
    return slug or "local"


def _extract_key_results_block(text: str) -> str:
    """Extract the key_results[] YAML block from a whole-document goal artifact.

    Mirrors the bash oracle's awk block-scan: everything from a `key_results:`
    top-level key up to (but not including) the next top-level (non-indented)
    key.
    """
    lines = text.splitlines()
    out: list[str] = []
    in_kr = False
    for line in lines:
        if line.startswith("key_results:"):
            in_kr = True
            continue
        if in_kr and re.match(r"^[a-zA-Z_]", line) and not re.match(r"^[ \t]", line):
            break
        if in_kr:
            out.append(line)
    return "\n".join(out)


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
        return value[1:-1]
    return value


def _strip_inline_comment(raw: str) -> str:
    """Strip a trailing YAML inline comment, quote-aware.

    Mirrors the YAML spec's comment-indicator rule: `#` starts a comment only
    outside quotes and only when preceded by whitespace or line-start — so
    `kind: output  # output | outcome` loses the comment but
    `text: "a # b"` keeps its quoted hash verbatim. A naive `value.split('#')[0]`
    would corrupt the latter.
    """
    in_single = in_double = False
    prev_ws = True
    for i, ch in enumerate(raw):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double and prev_ws:
            return raw[:i].rstrip()
        prev_ws = ch in (" ", "\t")
    return raw.rstrip()


def _project_key_results_status(file_path: str, basename: str) -> str:
    """Project the artifact's key_results[] block into wire key_results_status[] shape.

    {id,text,kind,status} — DROPPING evidence_source and per-KR weekly_perceptible
    (C11 field map). Returns a compact JSON array string, or "" when the artifact
    has no key_results[] entries.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
    kr_block = _extract_key_results_block(text)
    if not kr_block.strip():
        return ""

    objects: list[dict] = []
    kr_id = kr_text = kr_kind = kr_status = ""
    in_entry = False

    def _flush():
        nonlocal kr_id, kr_text, kr_kind, kr_status
        if in_entry:
            if not (kr_id or kr_text or kr_kind or kr_status):
                print(
                    f"[emit-goal] WARN {basename}: a key_results[] entry parsed with no "
                    "recognized fields (id/text/kind/status) — check for typo'd or "
                    "malformed keys",
                    file=sys.stderr,
                )
            objects.append({"id": kr_id, "text": kr_text, "kind": kr_kind, "status": kr_status})

    for line in kr_block.splitlines():
        m = re.match(r"^[ \t]*-[ \t]+(.*)$", line)
        if m:
            _flush()
            in_entry = True
            kr_id = kr_text = kr_kind = kr_status = ""
            rest = m.group(1)
            id_m = re.match(r"^id:[ \t]*(.*)$", rest)
            text_m = re.match(r"^text:[ \t]*(.*)$", rest)
            if id_m:
                kr_id = _unquote(_strip_inline_comment(id_m.group(1)))
            elif text_m:
                kr_text = _unquote(_strip_inline_comment(text_m.group(1)))
            continue
        fm = re.match(r"^[ \t]+([a-z_]+):[ \t]*(.*)$", line)
        if in_entry and fm:
            field_name = fm.group(1)
            field_val = _unquote(_strip_inline_comment(fm.group(2)))
            if field_name == "id":
                kr_id = field_val
            elif field_name == "text":
                kr_text = field_val
            elif field_name == "kind":
                kr_kind = field_val
            elif field_name == "status":
                kr_status = field_val
            # evidence_source, weekly_perceptible: intentionally dropped (C11 field map)

    _flush()

    if not objects:
        return ""
    return json.dumps(objects, separators=(",", ":"))


def main(argv: list[str]) -> int:
    args = argv[1:]
    root_override = ""
    repo_override = ""
    dry_run = False

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--root":
            root_override = args[i + 1] if i + 1 < len(args) else ""
            i += 2
        elif a == "--repo":
            repo_override = args[i + 1] if i + 1 < len(args) else ""
            i += 2
        elif a == "--dry-run":
            dry_run = True
            i += 1
        else:
            print(f"ERROR: Unknown argument: {a}", file=sys.stderr)
            return 1

    append_helper = os.environ.get(
        "COORDINATOR_APPEND_GOAL_HELPER", os.path.join(_BIN_DIR, "append-goal-event.py")
    )
    if not os.path.isfile(append_helper):
        print(f"ERROR: append-goal-event.py not found at {append_helper}", file=sys.stderr)
        return 1

    try:
        read_frontmatter_field = _resolve_read_frontmatter_field()
    except RuntimeError as exc:
        print(f"ERROR: could not resolve CLAUDE_KLABAUTER_ROOT: {exc}", file=sys.stderr)
        return 1

    git_root = _resolve_repo_root(root_override)
    if git_root is None:
        print(
            "ERROR: could not determine git root. Run from within a git repository or "
            "pass --root.",
            file=sys.stderr,
        )
        return 1

    goals_dir = os.path.join(git_root, "state", "goals")
    repo_slug = _derive_repo_slug(git_root, repo_override)

    if not os.path.isdir(goals_dir):
        print(f"[emit-goal] no state/goals/ directory at {git_root} — nothing to emit", file=sys.stderr)
        return 0

    goal_files = sorted(
        os.path.join(goals_dir, f) for f in os.listdir(goals_dir) if f.endswith(".yaml")
    )
    if not goal_files:
        print(f"[emit-goal] no *.yaml files found in {goals_dir} — nothing to emit", file=sys.stderr)
        return 0

    print(f"[emit-goal] found {len(goal_files)} goal artifact(s) in {goals_dir}", file=sys.stderr)

    emit_fail = False

    for goal_file in goal_files:
        basename = os.path.basename(goal_file)

        artifact_id = read_frontmatter_field(goal_file, "id")
        period = read_frontmatter_field(goal_file, "period")
        period_value = read_frontmatter_field(goal_file, "period_value")
        objective = read_frontmatter_field(goal_file, "objective")
        artifact_status = read_frontmatter_field(goal_file, "status")

        weekly_perceptible_raw = read_frontmatter_field(goal_file, "weekly_perceptible")
        parent_goal_id = read_frontmatter_field(goal_file, "parent_goal_id")
        goal_id_field = read_frontmatter_field(goal_file, "goal_id")
        key_results_status_json = _project_key_results_status(goal_file, basename)

        if not artifact_id:
            print(f"[emit-goal] SKIP {basename}: missing required frontmatter field 'id'", file=sys.stderr)
            emit_fail = True
            continue
        if not period:
            print(f"[emit-goal] SKIP {basename}: missing required frontmatter field 'period'", file=sys.stderr)
            emit_fail = True
            continue
        if not period_value:
            print(f"[emit-goal] SKIP {basename}: missing required frontmatter field 'period_value'", file=sys.stderr)
            emit_fail = True
            continue

        text = objective if objective else artifact_id
        # 2026-07-25: the artifact->wire status mapping is now live.
        # append-goal-event.py exposes --status (added alongside this fix);
        # _map_status() is called here and its result forwarded below. The
        # bash oracle's other dead computation, _PROV_PATH
        # ("state/goals/<file>.yaml" for --provenance), remains deferred —
        # append-goal-event.py still does not expose --provenance (see
        # module docstring negative-spec, unchanged for that half).
        wire_status = _map_status(artifact_status) if artifact_status else None

        wire_text = f"{artifact_id}: {text}"

        print(
            f"[emit-goal] emitting {basename} (id={artifact_id}, period={period}/{period_value})",
            file=sys.stderr,
        )

        new_field_args: list[str] = ["--parent-goal-id", parent_goal_id]
        if weekly_perceptible_raw:
            new_field_args += ["--weekly-perceptible", weekly_perceptible_raw]
        if key_results_status_json:
            new_field_args += ["--key-results-status", key_results_status_json]
        if goal_id_field:
            new_field_args += ["--goal-id", goal_id_field]
        if wire_status:
            new_field_args += ["--status", wire_status]

        if dry_run:
            print(f"[emit-goal] DRY-RUN: python {append_helper} \\", file=sys.stderr)
            print(f"  --period {period} \\", file=sys.stderr)
            print(f"  --period-value {period_value} \\", file=sys.stderr)
            print(f"  --text {wire_text!r} \\", file=sys.stderr)
            print(f"  --repo {repo_slug} \\", file=sys.stderr)
            print(f"  --root {git_root} \\", file=sys.stderr)
            print(f"  {' '.join(new_field_args)}", file=sys.stderr)
            continue

        cmd = [
            sys.executable,
            append_helper,
            "--period", period,
            "--period-value", period_value,
            "--text", wire_text,
            "--repo", repo_slug,
            "--root", ".",
            *new_field_args,
        ]
        try:
            result = subprocess.run(
                cmd, cwd=git_root, **_no_console_kw(),
                capture_output=True, text=True,
            )
        except (OSError, RuntimeError, ImportError) as exc:
            print(f"[emit-goal] FAIL {basename}: append-goal-event.py invocation error: {exc}", file=sys.stderr)
            emit_fail = True
            continue

        if result.returncode == 0:
            # Success-path stdout (append-goal-event.py's json.dumps(result) line)
            # is intentionally not relayed here — no caller/downstream process
            # consumes it (confirmed: no test or wiki contract asserts on it);
            # only failure output is surfaced for diagnosability. (Review:
            # code-reviewer — Finding 6, 2026-07-22.)
            print(f"[emit-goal] OK {basename}", file=sys.stderr)
        else:
            print(f"[emit-goal] FAIL {basename}: append-goal-event.py exited non-zero", file=sys.stderr)
            if result.stdout:
                print(result.stdout, file=sys.stderr, end="" if result.stdout.endswith("\n") else "\n")
            if result.stderr:
                print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")
            emit_fail = True

    if emit_fail:
        print("[emit-goal] one or more goals failed to emit — check stderr above", file=sys.stderr)
        return 2

    print("[emit-goal] all goals emitted successfully", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
