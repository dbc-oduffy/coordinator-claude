"""lessons-outbox-drain.py — mechanical backbone of the DoE Phase 2.6 outbox drain.

`skills/learn-lessons/SKILL.md` § Phase 2.6 (Lessons-Outbox Drain, Central Mode Only)
describes a DoE-owned central-mode state drain: read the outbox's own
`state/lessons-outbox/*.yaml` entries, dedupe across `from_repo` origins, route the
survivors through the (agent-mediated) central-mode apply pipeline, then mark drained —
`git mv` the drained entries to `state/lessons-outbox/drained/` and commit locally. Before
this script existed, Steps 2/3/4/6 were prose with `<peer-path>`/`<N>`/`${DRAIN_DATE}`
placeholders the EM hand-substituted at runtime — never executed as written, so never
verified end-to-end (PM finding, 2026-07-22: "not being able to resolve learn-lessons is
not good"). This script makes the mechanical steps (everything EXCEPT the judgment call of
routing an entry's body to the right wiki, which stays agent-mediated per Step 5) real,
argumented, and testable in isolation from any real peer repo.

`coordinator-lesson-promote` always writes to THIS repo's own outbox — there is no peer
repo to sync from or write back to (see `queue_promote.py`'s central `_outbox_root()`
resolution). An earlier revision of this script carried a peer-fetch/writeback/manifest
model (`sync`, `write-manifest`, `writeback`, `record-outcome` subcommands) sized for a
cross-repo gather that the central-write architecture never needed; that machinery was
retired once the central-write model made it dead weight (SKILL.md Step 5: "This is a
plain local move within this repo — there is no peer repo to write back to and no
manifest to build").

Two subcommands remain, one per mechanical step:

  read        Step 3+4 — glob + parse peer outbox YAMLs, dedupe by (title, change_kind,
                          target_wiki) across however many peer paths are passed.
  assert-empty    Detector, not drainer — verifies the one-root invariant a drain silently
                          depends on: that no OTHER registered peer plane has stranded
                          `state/lessons-outbox/*.yaml` entries this drain never sees. Added
                          2026-07-23 after `state/lessons-outbox/` was silently split across
                          two repos for six weeks — DoE's drain reads a single repo root, so
                          103 entries stranded in claude-klabauter's plane were structurally invisible
                          and every drain reported clean. See `assert_empty()` below for the
                          fail-loud exit-code divergence from its `learn-lessons-roots.py`
                          neighbour — that divergence is deliberate, not a bug to harmonize.

Step 5 (route each deduped entry through the central-mode classifier -> verify-gate ->
apply pipeline) is deliberately NOT mechanized here — which wiki a lesson's body belongs in
is a judgment call the EM/router makes per `docs/wiki/lessons-outbox-schema.md` § Change-kind
enum, not a deterministic parse. `read`'s output is the input to that judgment step; marking
an entry drained (`git mv` to `drained/` + commit, within this repo only) happens directly
once routing succeeds — no manifest, no peer writeback.

Schema reference: docs/wiki/lessons-outbox-schema.md
Spec backlink: archive/specs/2026-06/2026-06-15-universal-lesson-routing-mechanical-capture.md § C4
Co-located test: test_lessons_outbox_drain.py (fixture git repos — never a real peer repo).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml  # PyYAML — available in coordinator venv

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from cc_invoke import require_colocated_engine_on_path  # noqa: E402
from target_wiki_canon import canonical_target_wiki_for_kind  # noqa: E402

# `assert-empty` reuses the SAME peer-root enumeration `learn-lessons-roots.py` uses,
# imported directly rather than re-derived — hand-rolling a second registry-walk here
# would be exactly the kind of drift (two enumerations quietly diverging) this detector
# exists to catch. Resolved via the colocated-checkout ladder (this script lives inside
# the claude-klabauter tree itself), same pattern as the distill-*.py CLIs.
try:
    _REPO_ROOT = Path(require_colocated_engine_on_path(__file__))
except RuntimeError as _exc:
    print(f"{Path(__file__).name}: CLAUDE_KLABAUTER_ROOT resolution failed: {_exc}", file=sys.stderr)
    sys.exit(1)

from coordinator_core.ops.learn_lessons_roots import resolve_roots  # noqa: E402

REQUIRED_FIELDS = ("id", "created", "from_repo", "title", "body", "change_kind", "target_wiki")


# ---------------------------------------------------------------------------
# Step 3 — read one peer's outbox entries
# ---------------------------------------------------------------------------

def read_peer_outbox(peer_path: Path) -> tuple[list[dict], list[str]]:
    """Glob `<peer_path>/state/lessons-outbox/*.yaml` (excluding `drained/`), parse each
    per the schema, and return (entries, warnings). Entries missing a required field are
    reported as warnings and excluded, not silently dropped."""
    outbox_dir = peer_path / "state" / "lessons-outbox"
    entries: list[dict] = []
    warnings: list[str] = []
    if not outbox_dir.is_dir():
        return entries, warnings

    for f in sorted(outbox_dir.glob("*.yaml")):
        try:
            # Real on-disk entries commonly carry a leading `---` document-start marker
            # AND a trailing `---` (an artifact of an earlier writer that mirrored the
            # wiki-frontmatter convention). `yaml.safe_load` treats the trailing marker as
            # the start of a SECOND (empty) document and raises "expected a single document
            # in the stream" — which silently zeroed out every real entry this script ever
            # read (verified: 100% of the 108 + 107-file on-disk corpus failed to parse
            # under plain `safe_load` before this fix). `safe_load_all` tolerates the extra
            # document; taking the first non-empty one recovers the real fixture-style
            # single-document files (no `---` at all) exactly as before.
            docs = [d for d in yaml.safe_load_all(f.read_text(encoding="utf-8")) if d]
            fm = docs[0] if docs else {}
        except Exception as e:
            warnings.append(f"skipping malformed YAML {f}: {e}")
            continue
        missing = [k for k in REQUIRED_FIELDS if k not in fm]
        if missing:
            warnings.append(f"skipping {f}: missing required field(s) {missing}")
            continue
        entries.append({
            **fm,
            "_peer_path": str(peer_path),
            "_filename": f.name,
        })
    return entries, warnings


# ---------------------------------------------------------------------------
# Step 4 — dedupe across peers
# ---------------------------------------------------------------------------

def _canonical_target_wiki(target_wiki: str, change_kind: str) -> str:
    """Normalize `target_wiki` for DEDUPE-KEY COMPARISON ONLY — never mutates the entry's
    stored value (the merged-entry dict below always carries the original spelling).

    Delegates to `target_wiki_canon.canonical_target_wiki_for_kind` (shared with
    `coordinator-lesson-promote`'s write-time normalization) — see that module for the
    full rationale. Was previously a suffix-only (`.md`-append) collapse applied
    unconditionally to every change_kind: that fixed the originally-verified A9 defect
    (`"concurrent-em-hazards"` vs `"concurrent-em-hazards.md"` failing to dedupe) but did
    NOT collapse directory-prefix variance (`"test-design-discipline.md"` vs
    `"docs/wiki/test-design-discipline.md"`), because a basename-only collapse is unsafe
    for non-wiki change_kinds — every skill file shares the basename `SKILL.md`, so
    collapsing on basename alone would silently merge unrelated skills' entries into one
    dedupe group. Gating the FULL collapse on `change_kind` (wiki-new/wiki-append only,
    via `WIKI_TARGETING_CHANGE_KINDS`) resolves that objection: non-wiki kinds keep their
    raw value as the dedupe key (no false-merge risk — SKILL.md paths never collapse),
    while wiki-targeting kinds now compose with the promote CLI's own canonical form
    instead of disagreeing with it."""
    return canonical_target_wiki_for_kind(target_wiki, change_kind)


def dedup_entries(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    """Dedupe on the (title, change_kind, target_wiki) triple, with `target_wiki`
    canonicalized via `_canonical_target_wiki` for the comparison only (see that
    function's docstring for the A9 defect this closes). Multiple entries sharing a
    (canonicalized) triple from different repos are a convergence signal, not a
    collision — merge them, recording every contributing (peer_path, filename, id,
    from_repo) so Step 5's `git mv` can be applied to every contributing source file
    once routing succeeds.

    Returns (unique_or_merged, unknown_target) — `target_wiki: unknown` entries are
    excluded from the apply-eligible list per SKILL.md Step 3/5 and returned separately
    for PM manual-triage surfacing."""
    unknown: list[dict] = []
    by_triple: dict[tuple, dict] = {}
    order: list[tuple] = []

    for e in entries:
        if e.get("target_wiki") == "unknown":
            unknown.append(e)
            continue
        triple = (e["title"], e["change_kind"], _canonical_target_wiki(e["target_wiki"], e["change_kind"]))
        source = {
            "peer_path": e["_peer_path"],
            "filename": e["_filename"],
            "id": e["id"],
            "from_repo": e["from_repo"],
        }
        if triple not in by_triple:
            order.append(triple)
            by_triple[triple] = {
                "title": e["title"],
                "change_kind": e["change_kind"],
                "target_wiki": e["target_wiki"],
                "body": e["body"],
                "scope_tags": e.get("scope_tags", []),
                "evidence": e.get("evidence"),
                "sources": [source],
            }
        else:
            by_triple[triple]["sources"].append(source)

    merged = [by_triple[t] for t in order]
    return merged, unknown


# ---------------------------------------------------------------------------
# assert-empty — verify the one-root invariant (detector, not drainer)
# ---------------------------------------------------------------------------

def assert_empty(this_repo_root: Path) -> dict:
    """Detector for the incident this subcommand exists to close: `state/lessons-outbox/`
    was silently split across two repos for six weeks because DoE's drain reads a single
    repo root and had no way to notice a SECOND plane accumulating entries unseen. Every
    drain reported clean while 103 entries sat stranded in claude-klabauter's plane, structurally
    invisible to a drain that only ever looked at one root.

    Enumerates registered peer roots via `coordinator_core.ops.learn_lessons_roots.resolve_roots`
    — the SAME enumeration `learn-lessons-roots.py` uses — then subtracts `this_repo_root`
    (path-normalized on BOTH sides via `.resolve()`, so a trailing slash or a symlinked path
    can't defeat the subtraction). For each remaining peer, globs
    `<peer>/state/lessons-outbox/*.yaml` non-recursively — `drained/` is a subdirectory and is
    never matched by a non-recursive `*.yaml` glob, mirroring `read_peer_outbox`'s own
    exclusion above (no separate drained/-filter needed; the glob shape already excludes it).

    Three peer outcomes, reported distinctly — NEVER conflated:
      - `checked`:   outbox dir exists, glob is empty — VERIFIED empty.
      - `non_empty`: glob has entries — this is what makes the assertion FAIL.
      - `skipped`:   peer root not on disk, or has no `state/lessons-outbox/` dir at all — a
                     normal "peer not cloned on this machine" condition, NOT a failure, and
                     NOT counted as verified-empty (a peer we couldn't check is not a peer we
                     verified — conflating the two would silently rebuild the exact blind
                     spot this subcommand exists to close).

    Read-only: never mutates, moves, or deletes anything it finds — marking an entry
    drained (Step 5's local `git mv`) is a separate, later step, not this one's."""
    self_resolved = this_repo_root.resolve()

    checked: list[str] = []
    skipped: list[dict] = []
    non_empty: list[dict] = []
    seen_resolved: set = set()

    for raw_root in resolve_roots():
        peer_path = Path(raw_root)
        try:
            peer_resolved = peer_path.resolve()
        except OSError:
            peer_resolved = peer_path
        if peer_resolved == self_resolved or peer_resolved in seen_resolved:
            continue
        seen_resolved.add(peer_resolved)

        if not peer_path.is_dir():
            skipped.append({"peer_root": str(peer_path), "reason": "peer root not on disk"})
            continue

        outbox_dir = peer_path / "state" / "lessons-outbox"
        if not outbox_dir.is_dir():
            skipped.append({"peer_root": str(peer_path),
                             "reason": "no state/lessons-outbox/ directory"})
            continue

        stranded = sorted(f.name for f in outbox_dir.glob("*.yaml"))
        if stranded:
            non_empty.append({"peer_root": str(peer_path), "count": len(stranded),
                               "files": stranded})
        else:
            checked.append(str(peer_path))

    return {
        "status": "FAIL" if non_empty else "PASS",
        "self_root": str(self_resolved),
        "checked": checked,
        "skipped": skipped,
        "non_empty": non_empty,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("read", help="Step 3+4 — read + dedupe outbox entries across peer repos")
    pr.add_argument("peer_path", type=Path, nargs="*",
                     help="repo root(s) to read state/lessons-outbox/ under; defaults to the "
                          "current working directory (central-write means the drain's own repo "
                          "is the only root SKILL.md has ever passed — 'nargs=+' was sized for a "
                          "multi-peer gather the central-write model never needed)")

    pe = sub.add_parser("assert-empty",
                         help="Detector, not drainer — verify no OTHER registered peer "
                              "plane has stranded lessons-outbox entries this drain "
                              "never sees")
    pe.add_argument("this_repo_root", type=Path)

    args = ap.parse_args(argv)

    if args.cmd == "read":
        peer_paths = args.peer_path or [Path.cwd()]
        all_entries: list[dict] = []
        warnings: list[str] = []
        for peer_path in peer_paths:
            entries, peer_warnings = read_peer_outbox(peer_path)
            all_entries.extend(entries)
            warnings.extend(peer_warnings)
        merged, unknown = dedup_entries(all_entries)
        print(json.dumps({
            "entries": merged,
            "unknown_target": unknown,
            "warnings": warnings,
            "stats": {
                "total_read": len(all_entries),
                "unique_after_dedup": len(merged),
                "convergence_merged": sum(1 for e in merged if len(e["sources"]) > 1),
                "unknown_target_count": len(unknown),
            },
        }, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "assert-empty":
        result = assert_empty(args.this_repo_root)
        print(json.dumps(result, indent=2))
        # DELIBERATE DIVERGENCE from `learn-lessons-roots.py`'s exit-0-always convention,
        # despite sitting one directory over and enumerating the same peer roots: that
        # script is a never-block DISCOVERY helper (a failed lookup must not wedge a
        # learn-lessons run); this is a fail-loud DETECTOR whose entire purpose is to make
        # a stranded-plane blind spot loud instead of silent (see assert_empty()'s
        # docstring for the six-week incident this exists to close). Harmonizing this to
        # exit 0 on FAIL would silently rebuild that exact blindness — do NOT "fix" this
        # to match its neighbour.
        return 0 if result["status"] == "PASS" else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
