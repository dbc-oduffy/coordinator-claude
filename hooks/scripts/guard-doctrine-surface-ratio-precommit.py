# guard-not-a-hook-entrypoint
# Native git pre-commit hook installed by a sibling repo's installer, not a hooks.json entrypoint.
"""Native git pre-commit hook: Layer 1 leg 1b of the doctrinal surface
weight ratchet -- the ONLY enforcing leg (leg 1a,
`guard-doctrine-surface-ratio.py`, is advisory-only, D7).

Spec: docs/plans/2026-08-13-doctrinal-surface-weight-ratchet.md, chunk C9b
(§ D2, D3, D7). Installer registration is chunk C9c, a sibling repo's
own installer -- this script ships complete and tested but is NOT
installed into `.git/hooks/` by anything in this repo; the sibling
installer names this exact path (`coordinator/hooks/scripts/guard-
doctrine-surface-ratio.py` per its own gate registry -- see this repo's
plan body for the cross-repo contract note; do not rename either this
file or the leg-1a guard without a coordinated update on that side).

Why a git hook, not a second `PreToolUse` guard
--------------------------------------------------
`PreToolUse` fires before any commit exists and sees one tool call -- it
cannot net across a commit's edits (D7). At commit time the staged diff
exists, so per-commit netting is directly computable. Precedent:
`coordinator/hooks/hooks.json`'s foreign-platform-path guard makes the
identical two-leg argument (a `PreToolUse` guard "cannot see what is not
a tool call", its independent second leg is a native git pre-commit
hook that "survives a session where every Claude Code hook is dead").

THIS SCRIPT IS THE THIN, UNTESTED WRAPPER. It is a git hook, never
exercised by `pytest` collection (D7's "Consequence for the test plane")
-- its only job is: run the two real git subcommands, parse their output
into `(old_bytes, new_bytes, path)` rows, and hand them to the PURE,
directly-unit-tested functions in `_doctrine_surface_netting.py`
(`net_bytes_by_surface`, `net_bytes_by_file`) plus this module's own
carve-out logic (floor/accumulator, reasoned-growth marker, new-file
admission). Do not "simplify" this split by moving the netting logic
in here and running `git diff` internally from the tested module -- that
removes this plan's only test surface for leg 1b (see the netting
module's own docstring).

UNIT: BYTES, never a line-oriented diff
-------------------------------------------
`git diff --cached --numstat` emits LINE counts; leg 1a prices bytes
(`_sentinel_write_guard.reconstruct_after`'s byte-length delta). Billing
leg 1b off numstat would price one currency and bill another, silently
turn the 512 B floor into ~512 lines (~20 KB), mishandle numstat's
`-\t-` binary rows and its `old => new` / `{a => b}/c` rename path
forms, and be uncorrelated with byte deltas for exactly the
rewrite-to-tighten reflow motion this plan rewards. Instead:
`git diff --cached --raw -z -M` (`-M` collapses a rename into one row
with old+new paths, rather than delete-plus-add) enumerates staged paths
and old/new blob OIDs; `git cat-file -s <oid>` sizes each OID (the null
OID for an added/deleted side sizes as 0). A binary file's raw-diff row
still carries real OIDs (unlike `--numstat`'s `-\t-`), so `cat-file -s`
sizes it exactly like text -- no special-casing needed. A rename row's
path is the NEW path (the one `surface_of` buckets against).

Exit-code discipline
-----------------------
Exits 0 (allow) or 1 (block) ONLY -- never a raw propagated subprocess
code, mirroring the sibling repo's own installer wrapper's exit-code-
clamping discipline (see C9c). That installer wrapper additionally
clamps whatever this script exits, so an internal failure here is free
to fall through to the fail-open path below without bricking the
harness -- but this script clamps anyway, defensively, rather than
depending on that clamp alone.

Fail-open, not fail-closed, on any internal error (subprocess failure,
unreadable baseline, unparseable diff row) -- a defect in this
enforcing leg must not become a universal commit block; it degrades to
"leg 1b did not run this commit," same posture as leg 1a's own
fail-open guards.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

_LIB_DIR = str(Path(__file__).resolve().parents[2] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from _doctrine_changelog_prose import surface_of  # noqa: E402
from _doctrine_surface_netting import (  # noqa: E402
    CREDIT_SCOPE_FILE,
    CREDIT_SCOPE_SURFACE,
    is_sanctioned_reason,
    net_bytes_by_file,
    net_bytes_by_surface,
)
from doctrine_surface_tiers import admission_cap_for, tier_boundaries_for  # noqa: E402


def _load_split_recognizer():
    """`is_sanctioned_split` (C10) lives in a hyphenated-basename module,
    same reason the sibling test suite loads the guard itself via
    `importlib.util.spec_from_file_location` rather than `import_module`.
    Leg 1b, unlike leg 1a, has both a before and an after snapshot at
    commit time, so it CAN recognize a split -- a recognized split must
    be a no-op on this guard (A15)."""
    module_path = REPO_ROOT / "coordinator" / "lib" / "generate-doctrine-surface-split.py"
    spec = importlib.util.spec_from_file_location("generate_doctrine_surface_split", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.is_sanctioned_split


_NULL_OID = "0" * 40

#: A single surface/file's net addition under this floor is deferred, not
#: forgiven -- see `_apply_sub_floor_floor` and D3 carve-out 2.
_SUB_FLOOR_BYTES = 512

_RATIO_PRICED_SURFACES = frozenset({"wiki", "commands", "snippets"})
_ADMISSION_PRICED_SURFACES = frozenset({"wiki", "commands", "snippets", "agents", "skills"})

REPO_ROOT = Path(__file__).resolve().parents[3]

#: Leg 1b's OWN mutable operational state (the sub-floor accumulator) --
#: deliberately NOT `coordinator/tests/baselines/doctrine-surface-weight.
#: json`. That file's sole owner is `doctrine_surface_tiers` (declarative
#: Layer-2 ceiling data, per leg 1a's own module docstring: "Never reads
#: ... directly and never imports anything from coordinator/tests/" --
#: an undeclared hooks-plane -> test-plane coupling D6 forbids). A git
#: hook mutating a test-plane artifact on every commit is the same
#: coupling in the other direction; this leg's accumulator lives entirely
#: in the hooks plane instead, in a state file `.gitignore`d as per-
#: machine runtime state, never doctrine content.
_ACCUMULATOR_STATE_PATH = (
    REPO_ROOT / "coordinator" / "hooks" / "state" / "doctrine-surface-ratio-accumulator.json"
)

#: Per-(surface, credit-scope) accumulator storage keys. The storage key
#: stays PER-SURFACE (D3 carve-out 1's accumulator note), but the two
#: credit-scope pools (`net_bytes_by_surface`'s 2:1 pool vs `net_bytes_
#: by_file`'s 5:1/10:1 pool) are logically distinct and must never share
#: one slot -- see `_doctrine_surface_netting.py`'s own module docstring
#: on why pool separation is load-bearing. Two keys within the same
#: per-surface entry satisfy both facts at once.
_ACCUMULATOR_KEY_BY_SCOPE = {
    CREDIT_SCOPE_SURFACE: "sub_floor_accumulator_surface",
    CREDIT_SCOPE_FILE: "sub_floor_accumulator_file",
}


#: git.exe is a console-subsystem child on Windows and is not exempt from
#: the pop-window discipline even under redirected capture_output.
_NO_CONSOLE_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run_git(args: "list[str]") -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        check=True,
        creationflags=_NO_CONSOLE_WINDOW,
    )
    return result.stdout.decode("utf-8", errors="replace")


def _blob_size(oid: str) -> int:
    if oid in (_NULL_OID, "") or set(oid) == {"0"}:
        return 0
    result = subprocess.run(
        ["git", "cat-file", "-s", oid],
        cwd=str(REPO_ROOT),
        capture_output=True,
        creationflags=_NO_CONSOLE_WINDOW,
    )
    if result.returncode != 0:
        return 0
    try:
        return int(result.stdout.decode("utf-8", errors="replace").strip())
    except ValueError:
        return 0


def _blob_sizes_batch(oids: "set[str]") -> "dict[str, int]":
    """One `git cat-file --batch-check` spawn for every OID in `oids`,
    instead of a `_blob_size` spawn per record -- this is a pre-commit
    hook on a heavily contended shared machine, so batching per-commit
    reads beats a per-item subprocess loop."""
    sizes: "dict[str, int]" = {}
    real_oids = []
    for oid in oids:
        if oid in (_NULL_OID, "") or set(oid) == {"0"}:
            sizes[oid] = 0
        else:
            real_oids.append(oid)
    if not real_oids:
        return sizes
    result = subprocess.run(
        ["git", "cat-file", "--batch-check"],
        cwd=str(REPO_ROOT),
        input="\n".join(real_oids) + "\n",
        capture_output=True,
        text=True,
        creationflags=_NO_CONSOLE_WINDOW,
    )
    for line in result.stdout.splitlines():
        parts = line.split(" ")
        if len(parts) >= 2 and parts[-1] == "missing":
            sizes[parts[0]] = 0
        elif len(parts) >= 3:
            try:
                sizes[parts[0]] = int(parts[2])
            except ValueError:
                sizes[parts[0]] = 0
    return sizes


def _parse_raw_diff_records(raw_output: str) -> "list[tuple[str, str, str, str]]":
    """Parse `git diff --cached --raw -z -M` NUL-delimited output into
    `(old_oid, new_oid, status, path)` records. Each record is
    `:old_mode new_mode old_oid new_oid status\\0path\\0` (a rename/copy
    record carries a SECOND NUL-terminated path -- the new path, which is
    the one both `surface_of` and the split recognizer bucket against)."""
    fields = [f for f in raw_output.split("\x00") if f != ""]
    records: "list[tuple[str, str, str, str]]" = []
    i = 0
    while i < len(fields):
        header = fields[i]
        if not header.startswith(":"):
            i += 1
            continue
        parts = header[1:].split(" ")
        # :old_mode new_mode old_oid new_oid status
        if len(parts) < 5:
            i += 1
            continue
        old_oid, new_oid, status = parts[2], parts[3], parts[4]
        i += 1
        if i >= len(fields):
            break
        path = fields[i]
        i += 1
        if status[0] in ("R", "C"):
            # Rename/copy: a second path field follows -- the NEW path.
            if i < len(fields):
                path = fields[i]
                i += 1
        records.append((old_oid, new_oid, status, path))
    return records


def _parse_raw_diff(raw_output: str) -> "list[tuple[int, int, str]]":
    """`(old_bytes, new_bytes, path)` rows, sized from `_parse_raw_diff_
    records`'s OIDs via `_blob_size` (the null OID sizes as 0). This is
    the row shape the pure netting functions and the admission-cap check
    consume."""
    records = _parse_raw_diff_records(raw_output)
    all_oids: "set[str]" = set()
    for old_oid, new_oid, _status, _path in records:
        all_oids.add(old_oid)
        all_oids.add(new_oid)
    sizes = _blob_sizes_batch(all_oids)
    rows: "list[tuple[int, int, str]]" = []
    for old_oid, new_oid, _status, path in records:
        rows.append((sizes.get(old_oid, 0), sizes.get(new_oid, 0), path))
    return rows


def _cat_file_content(oid: str) -> bytes:
    if oid in (_NULL_OID, "") or set(oid) == {"0"}:
        return b""
    result = subprocess.run(
        ["git", "cat-file", "-p", oid],
        cwd=str(REPO_ROOT),
        capture_output=True,
        creationflags=_NO_CONSOLE_WINDOW,
    )
    if result.returncode != 0:
        return b""
    return result.stdout


def _cat_file_contents_batch(oids: "set[str]") -> "dict[str, bytes]":
    """One `git cat-file --batch` spawn for every OID in `oids`, instead
    of a `_cat_file_content` spawn per path -- same batching rationale as
    `_blob_sizes_batch`."""
    contents: "dict[str, bytes]" = {}
    real_oids = []
    for oid in oids:
        if oid in (_NULL_OID, "") or set(oid) == {"0"}:
            contents[oid] = b""
        else:
            real_oids.append(oid)
    if not real_oids:
        return contents
    result = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=str(REPO_ROOT),
        input=("\n".join(real_oids) + "\n").encode("utf-8"),
        capture_output=True,
        creationflags=_NO_CONSOLE_WINDOW,
    )
    data = result.stdout
    pos = 0
    for oid in real_oids:
        nl = data.index(b"\n", pos)
        header = data[pos:nl].decode("utf-8", errors="replace")
        parts = header.split(" ")
        if len(parts) < 2 or parts[-1] == "missing" or len(parts) < 3:
            contents[oid] = b""
            pos = nl + 1
            continue
        try:
            size = int(parts[2])
        except ValueError:
            contents[oid] = b""
            pos = nl + 1
            continue
        start = nl + 1
        contents[oid] = data[start:start + size]
        pos = start + size + 1
    return contents


def _sanctioned_split_paths(raw_output: str) -> "set[str]":
    """Every path this commit's diff touches that C10's `is_sanctioned_
    split` recognizes as part of a sanctioned split -- the vanished stem
    `.md` entry plus every new file under `stem/`. Leg 1b, unlike leg 1a,
    has both a before and after snapshot at commit time (both sides are
    real staged blobs), so it CAN build the two snapshots
    `is_sanctioned_split` needs -- restricted to exactly the paths this
    diff touches, which is sufficient since the recognizer only reads the
    vanished stem path and the new `stem/*` paths, never anything else.
    A5/A15: a recognized split is a NO-OP on this guard -- neither the
    admission-cap nor the netting/floor carve-outs price these paths."""
    is_sanctioned_split = _load_split_recognizer()
    records = _parse_raw_diff_records(raw_output)

    old_oid_by_path = {}
    new_oid_by_path = {}
    for old_oid, new_oid, _status, path in records:
        old_oid_by_path[path] = old_oid
        new_oid_by_path[path] = new_oid

    deleted_md_stems = [
        path[: -len(".md")]
        for old_oid, new_oid, status, path in records
        if path.endswith(".md") and (set(new_oid) == {"0"} or new_oid == _NULL_OID)
    ]

    stem_new_paths: "dict[str, list[str]]" = {}
    needed_oids: "set[str]" = set()
    for stem in deleted_md_stems:
        prefix = f"{stem}/"
        new_under_stem = [p for p in new_oid_by_path if p.startswith(prefix)]
        if not new_under_stem:
            continue
        stem_new_paths[stem] = new_under_stem
        md_path = f"{stem}.md"
        needed_oids.add(old_oid_by_path.get(md_path, _NULL_OID))
        for p in new_under_stem:
            needed_oids.add(new_oid_by_path[p])
    contents_by_oid = _cat_file_contents_batch(needed_oids)

    sanctioned: "set[str]" = set()
    for stem, new_under_stem in stem_new_paths.items():
        md_path = f"{stem}.md"
        prior_snapshot = {
            md_path: contents_by_oid.get(old_oid_by_path.get(md_path, _NULL_OID), b"")
        }
        current_snapshot = {
            p: contents_by_oid.get(new_oid_by_path[p], b"") for p in new_under_stem
        }
        if is_sanctioned_split(prior_snapshot, current_snapshot, stem):
            sanctioned.add(md_path)
            sanctioned.update(new_under_stem)
    return sanctioned


def _load_baseline() -> dict:
    """Loads leg 1b's own accumulator state -- `{"surfaces": {}}` if the
    state file has never been written (first commit this leg has ever
    priced, or a fresh checkout)."""
    import json

    try:
        return json.loads(_ACCUMULATOR_STATE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"surfaces": {}}


def _save_baseline(baseline: dict) -> None:
    """Write-temp-then-rename: `os.replace` is atomic on both POSIX and
    Windows (same-volume), so a process death mid-write leaves either the
    OLD state file intact or the NEW one fully written -- never a
    truncated/corrupt file. Either outcome keeps the failure mode "debt
    retained, never silently lost"."""
    import json
    import os
    import tempfile

    _ACCUMULATOR_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(baseline, indent=2, sort_keys=False) + "\n"
    fd, tmp_path = tempfile.mkstemp(
        dir=str(_ACCUMULATOR_STATE_PATH.parent), prefix=".doctrine-surface-ratio-accumulator-"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp_path, str(_ACCUMULATOR_STATE_PATH))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _persist_baseline_fail_open(baseline: dict) -> None:
    """Best-effort persistence for a commit that IS allowed to land.
    Swallows a write failure rather than turning a disk error into a
    commit block -- same fail-open posture as every other internal
    failure mode this leg has (module docstring). Debt over-billing
    (a write that half-lands, or a process death mid-write) is
    human-recoverable; a silently-forgiven accumulator is not, so this
    never runs on the deny path (see `main`)."""
    try:
        _save_baseline(baseline)
    except Exception:
        pass


def _build_tier_of(rows: "list[tuple[int, int, str]]"):
    """Closes over each row's pre-edit `old_bytes` (already parsed) to
    build the `Callable[[str], str]` the pure netting functions require --
    resolves a path to its CREDIT-SCOPE POOL (`"surface"` or `"file"`) via
    `tier_boundaries_for(surface_of(path))`, band-selected on the path's
    pre-edit size, exactly mirroring leg 1a's `_select_tier`."""
    pre_edit_size_by_path = {path: old_bytes for old_bytes, _new, path in rows}

    def tier_of(path: str) -> str:
        surface = surface_of(Path(path))
        if surface is None or surface not in _RATIO_PRICED_SURFACES:
            # Off-surface or a ratio-unpriced surface (agents/skills) --
            # neither pool claims it; both netting functions already skip
            # any row whose tier_of() doesn't match their own scope, so
            # returning a sentinel that matches neither is correct.
            return "unpriced"
        pre_edit_size = pre_edit_size_by_path.get(path, 0)
        boundaries = tier_boundaries_for(surface)
        for band in boundaries["tiers"]:
            if band["max"] is None or pre_edit_size < band["max"]:
                return band["credit_scope"]
        return boundaries["tiers"][-1]["credit_scope"]

    return tier_of


def _new_file_admission_denials(rows: "list[tuple[int, int, str]]") -> "list[str]":
    """Carve-out 4: a brand-new file (`old_bytes == 0`) is priced by
    admission, not ratio -- refused only for arriving above its surface's
    top-decile threshold (`admission_cap_for`, C9a's export)."""
    denials = []
    for old_bytes, new_bytes, path in rows:
        if old_bytes != 0:
            continue
        surface = surface_of(Path(path))
        if surface is None or surface not in _ADMISSION_PRICED_SURFACES:
            continue
        threshold = admission_cap_for(surface)
        if new_bytes > threshold:
            denials.append(
                f"{path} arrives at {new_bytes} B, over {surface}'s "
                f"{threshold} B new-file admission cap (D3)."
            )
    return denials


def _apply_sub_floor_and_bill(
    baseline: dict, surface_net: "dict[str, int]", file_net: "dict[str, int]", tier_of
) -> "list[str]":
    """Carve-out 2: bills the STORED accumulator, not the raw in-commit
    net, once it crosses 512 B -- selecting the pool by the tier of the
    file whose growth accumulated (not whichever file is cut in the
    crossing commit). Mutates `baseline["surfaces"][surface][
    "sub_floor_accumulator"]` in place; caller persists it."""
    denials: "list[str]" = []
    surfaces = baseline["surfaces"]
    surface_key = _ACCUMULATOR_KEY_BY_SCOPE[CREDIT_SCOPE_SURFACE]
    file_key = _ACCUMULATOR_KEY_BY_SCOPE[CREDIT_SCOPE_FILE]

    # Surface-wide (2:1) pool -- own accumulator slot, never shared with
    # the file pool below (Finding 2: the two credit-scope pools must not
    # collapse back into one shared slot).
    for surface, net in surface_net.items():
        entry = surfaces.setdefault(surface, {})
        prior = int(entry.get(surface_key, 0))
        addition = max(net, 0)
        accumulated = prior + addition
        if accumulated >= _SUB_FLOOR_BYTES:
            owed = accumulated * 2
            denials.append(
                f"`{surface}` crosses the 512 B sub-floor accumulator "
                f"(accumulated {accumulated} B) -- {owed} B of cuts owed "
                "on the surface this commit (D3 carve-out 2)."
            )
            entry[surface_key] = 0
        else:
            entry[surface_key] = accumulated

    # Same-file (5:1/10:1) pool -- accumulator STORAGE stays PER-SURFACE
    # (D3 carve-out 1's accumulator note), but in its OWN key, distinct
    # from the surface pool's key above, so a same-surface 2:1 crossing
    # can never erase or contaminate this pool's carried-over debt.
    for path, net in file_net.items():
        surface = surface_of(Path(path))
        if surface is None:
            continue
        entry = surfaces.setdefault(surface, {})
        prior = int(entry.get(file_key, 0))
        addition = max(net, 0)
        accumulated = prior + addition
        if accumulated >= _SUB_FLOOR_BYTES:
            boundaries = tier_boundaries_for(surface)
            ratio = 5
            for band in boundaries["tiers"]:
                if band["credit_scope"] == CREDIT_SCOPE_FILE:
                    ratio = band["ratio"]
                    break
            owed = accumulated * ratio
            denials.append(
                f"{path} crosses the 512 B sub-floor accumulator "
                f"(accumulated {accumulated} B) -- {owed} B of cuts owed "
                "on THIS FILE this commit (D3 carve-out 2)."
            )
            entry[file_key] = 0
        else:
            entry[file_key] = accumulated

    return denials


#: Commit-trailer key a reasoned-growth marker is named under (carve-out
#: 3) -- `git commit -m '... \n\nDoctrine-Growth-Reason: <value>'` or a
#: `.git/COMMIT_EDITMSG` line of the same shape, read best-effort below.
_REASON_TRAILER_KEY = "Doctrine-Growth-Reason:"


def _read_reasoned_growth_marker() -> "str | None":
    """Best-effort read of `_REASON_TRAILER_KEY`'s value from `.git/
    COMMIT_EDITMSG` (populated by `git commit -m`/`-F` before the
    pre-commit hook runs) or `COORDINATOR_DOCTRINE_GROWTH_REASON` in the
    environment, for a caller that cannot pre-stage a commit message
    (carve-out 3). Returns `None` on any read failure -- silence is not
    an exception either way, `is_sanctioned_reason(None)` already fails
    closed."""
    import os

    env_value = os.environ.get("COORDINATOR_DOCTRINE_GROWTH_REASON")
    if env_value:
        return env_value
    try:
        msg_path = REPO_ROOT / ".git" / "COMMIT_EDITMSG"
        if not msg_path.is_file():
            return None
        lines = msg_path.read_text(encoding="utf-8", errors="replace").splitlines()
        # Restrict the scan to the TRAILER BLOCK -- the run of non-blank
        # lines after the LAST blank line in the message -- so mid-paragraph
        # prose that merely mentions the trailer key (e.g. pasting this
        # guard's own stderr text into a follow-up commit message) can
        # never be mistaken for a real trailer (Finding 4).
        last_blank = -1
        for i, line in enumerate(lines):
            if line.strip() == "":
                last_blank = i
        trailer_block = lines[last_blank + 1 :]
        if last_blank == -1 and len(lines) > 1:
            # No blank line at all in a multi-line message means there is
            # no distinct trailer paragraph -- fail closed (no marker).
            return None
        for line in trailer_block:
            stripped = line.strip()
            if stripped.startswith(_REASON_TRAILER_KEY):
                return stripped[len(_REASON_TRAILER_KEY) :].strip()
    except Exception:
        return None
    return None


def main() -> int:
    try:
        raw = _run_git(["diff", "--cached", "--raw", "-z", "-M"])
    except Exception:
        return 0

    try:
        rows = _parse_raw_diff(raw)
    except Exception:
        return 0
    if not rows:
        return 0

    try:
        # A5/A15: a recognized sanctioned split is a no-op on this guard
        # -- exclude its touched paths from every carve-out below before
        # pricing anything (C10's `is_sanctioned_split`).
        sanctioned_paths = _sanctioned_split_paths(raw)
        if sanctioned_paths:
            rows = [row for row in rows if row[2] not in sanctioned_paths]
        if not rows:
            return 0
    except Exception:
        # Fail-open on the split recognizer itself -- an internal defect
        # here must not become a universal commit block either.
        pass

    try:
        admission_denials = _new_file_admission_denials(rows)
        tier_of = _build_tier_of(rows)
        surface_net = net_bytes_by_surface(rows, tier_of)
        file_net = net_bytes_by_file(rows, tier_of)

        # `_apply_sub_floor_and_bill` mutates its `baseline` argument in
        # place, but that mutation must NEVER reach disk for a commit that
        # ends up denied (Finding 1) -- persisting it unconditionally here
        # let a denied commit pay off its own accumulator debt, so a bare
        # retry of the identical commit would sail through. Compute the
        # mutation now; the two callers below decide, AFTER the deny/allow
        # verdict is known, whether it is safe to persist.
        baseline = _load_baseline()
        floor_denials = _apply_sub_floor_and_bill(baseline, surface_net, file_net, tier_of)
    except Exception:
        # Fail-open: an internal defect in this enforcing leg must not
        # become a universal commit block.
        return 0

    denials = admission_denials + floor_denials
    if not denials:
        # Nothing owed -- this commit's growth is allowed to land, so its
        # accumulator mutation is real and gets persisted.
        _persist_baseline_fail_open(baseline)
        return 0

    # Carve-out 3: a marker naming a SANCTIONED reason (closed enum, not
    # free text -- silence is not an exception, an out-of-enum value
    # fails the same way `missing_reason` already does on the shipped
    # ratchets) exempts this commit's growth entirely.
    marker = _read_reasoned_growth_marker()
    if is_sanctioned_reason(marker):
        # The commit is still allowed to land -- its growth happened, so
        # the accumulator mutation is real here too.
        _persist_baseline_fail_open(baseline)
        return 0

    # DENIED: this commit does not land. Leave the stored accumulator
    # state exactly as `_load_baseline` found it -- no save call on this
    # path, by design (Finding 1). A bare retry of the identical commit
    # must see the same accumulator state it saw the first time, not a
    # zeroed/incremented one from the rejected attempt.
    for reason in denials:
        print(f"[guard-doctrine-surface-ratio-precommit] {reason}", file=sys.stderr)
    print(
        "Reasoned-growth escape: add a commit trailer "
        f"`{_REASON_TRAILER_KEY} <reason>` naming a sanctioned reason "
        "(see _doctrine_surface_netting.REASONED_GROWTH_MARKERS) to "
        "exempt this growth -- silence is not an exception, and an "
        "out-of-enum value fails the same way.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
