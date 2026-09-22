"""percolate-gate.py — naked-Python engine for the `/percolate` skill's
residual imperative gate logic (DoE-claude coordinator/skills/percolate/SKILL.md).

Ports the four genuine imperative-logic fences the skill still carries as
bash after the b644d5a9 bin/lib migration: the Branch-0 first-run setup gate
(target resolution + `.percolate-ignore` existence check — the per-target
hook-dir existence loop was removed 2026-07-24 as vestigial once the
percolate engine went declarative, see docs/plans/2026-07-24-extirpate-
orphaned-claude-central-publish-shell.md), the Step 2c three-tier
content-leakage scan (HIGH/MEDIUM/LOW regex tiers over the about-to-publish
file set, plus the peer-repo-name extension), and the Step 2d inverse-drift
anchor resolution (lastsync marker vs 30-day fallback) and its scoped
`git log` commit listing. The pre-ci guard (formerly Step 5a's
shell-hook-script execution loop) now runs declaratively inside the engine
— `publish.py`'s `dispatch_percolate_pre_ci` — with no separate hook-script
execution step; this module carries no pre-ci subcommand. Everything the
skill still names a "thin single-CLI-invocation fence" (the
`_cc_trusted`/`_cc_root` guard preamble, the `resolve-claude-klabauter-bin` resolver,
`publish.py`/`load_targets` invocations themselves) is deliberately NOT
ported here — those are D1/D2's concern, not this chunk's.

Subcommands:
  branch0-gate <target> --percolate-root <path> --claude-klabauter-root <path>
      Resolve the target row via percolate.targets.load_targets and confirm
      `<source_dir>/.percolate-ignore` exists. Prints `CONFIGURED:<source_dir>`
      and exits 0 when every check passes; on any failure prints one reason
      line per failure (`MISSING_TARGETS` / `MISSING_TARGET_ENTRY` /
      `MISSING_IGNORE`) and exits 1. Does NOT check for per-target hook
      subdirectories under `percolate-hooks/<target>/` — those are vestigial
      now that the percolate engine consumes the declarative
      `percolate-store.yaml` instead, and the pre-ci guard runs declaratively
      inside `publish.py` rather than via a shell hook-script loop.

  scan-secrets --files <file-list-path> [--identity-file <path>]
               [--peer-repos-file <repo-registry.md path>] [--target <name>]
               [--percolate-root <path>]
      Run the three severity-tier grep-style scan (HIGH credential shapes,
      MEDIUM identity/internal-path/peer-repo shapes, LOW informational)
      over the newline-delimited absolute file paths in <file-list-path>.
      Renders the Step 2c panel to stdout. Exits 2 if any HIGH hit fired
      (publish-blocking contract — mirrors the skill's "HIGH >=1: abort"
      rule), else 0. A MEDIUM path-shape match whose rooted segment is a
      placeholder (single letter, `<...>`, `$...`, `foo`, or any of those
      under a file extension — `/x/y.md`), whose slash-rooted
      match sits MID-path on a placeholder segment (`refs/x/old`), or whose
      line carries `abs-path-ok: <reason>` / `foreign-path-ok: <reason>` is
      discharged and never reaches the gating panel (`_medium_line_gates`);
      email-shape matches are never discharged that way, the one exception
      being a public-forge SSH service address (`git@github.com`), which
      names a service and not a person. With --percolate-root, the
      peer-repo-name leg's hits are resolved against <target>'s
      `percolate-store.yaml` guards: a target declaring a `no-residual-pattern` / `registry_codenames` guard gets
      those hits rendered in a SEPARATE covered group (read pre-transform;
      Phase-4's post-rsync audit is the post-transform oracle), never mixed
      into the plain MEDIUM group the pre-transform read would otherwise
      misrepresent as an unaddressed leak. Without --percolate-root (or on a
      target with no such guard), the panel is unchanged.

  inverse-drift <target> --percolate-root <path> --dest <dest-path>
                --files <file-list-path>
      Resolve the lastsync-marker-vs-30-day-fallback anchor, then run a
      `git log` in <dest> scoped to the (dest-relative) paths in
      <file-list-path> since that anchor. Renders the Step 2d panel.
      Prints `anchor_mode: marker|30day-fallback|marker-stale` on its own
      line first. Lists only hand-authored commits whose changes are still
      live in HEAD. The publisher's own source-head-stamped commits, and hand
      commits a later publish already rewrote, are counted on a `not drift:`
      line and never listed.

  resolve-root [--explain]
      Fronts `coordinator_core.percolate.runtime_root.
      coordinator_percolate_runtime_root_explained()`, which walks the four-
      rung PERCOLATE_ROOT ladder once and returns `(path, rung)`. Bare form
      prints the resolved absolute path on stdout, one line, exit 0.
      `--explain` prints `<path>\t<rung>` (tab-separated), where rung is one
      of the stable labels `env` / `repo-local-git` / `doe-root-pointer` /
      `shared-install`. On a ladder RuntimeError, its own remediation message
      reaches stderr verbatim (not reworded) and the subcommand exits 1 with
      no stdout. Unlike the other subcommands, this one takes NO
      `--percolate-root` flag -- resolving that root is its entire job.

  list-targets --percolate-root <path> [--target <name>]
      Step 1 / Step 5. Resolves the registered target set via
      percolate.targets.load_targets (the same library publish.py itself
      calls). With no --target: prints every resolved target's name, one per
      line, in load_targets' own resolution order (PRIMARY, then SUPPLEMENT,
      then LEGACY fallback -- load_targets already dedupes by name, an
      earlier tier's row always winning, so no re-dedup is needed here).
      With --target <name>: resolves that one target's row and prints ONLY
      its absolute dest path (match-and-exit pattern -- exits 1 with no
      stdout if the target isn't found among the resolved rows). On a
      TargetsError (malformed row, unresolvable required target, no targets
      found anywhere), prints the error's message to stderr and exits 1.

  coverage-drift <source_dir> [--limit N]
      Step 2a. Portable Python replacement for the skill's `find
      "<source_dir>" -type f -newer "<source_dir>/.percolate-ignore" | head
      -20` pipe (GNU/BSD `find -newer` is directionally portable but head
      count and quoting are still shell narration). Lists files under
      <source_dir> whose mtime is strictly newer than
      `<source_dir>/.percolate-ignore`'s mtime, one absolute path per line,
      capped at --limit (default 20, matching the skill's `head -20`). If
      `.percolate-ignore` is missing, prints nothing and exits 0 (coverage-
      drift is silent until the file exists, per the skill's own note).

  ignore-mtime <source_dir>
      Step 2a "last reviewed" date. Portable Python replacement for `date -r
      "<source_dir>/.percolate-ignore" '+%Y-%m-%d'`. Prints the ignore
      file's mtime as `YYYY-MM-DD` and exits 0. Exits 1 with no stdout if
      `.percolate-ignore` doesn't exist (nothing to date).

  crlf-diff <dest_file> <source_file>
      Step 2d CRLF-only false-positive dismissal. Portable Python
      replacement for `diff --strip-trailing-cr <dest-file>
      <source-file>` — compares the two files line-by-line with trailing
      `\\r` stripped from each line before comparison (so a CRLF-vs-LF-only
      difference reads as identical, matching GNU diff's
      `--strip-trailing-cr` semantics). Exits 0 with no stdout when the
      stripped content is identical (the skill's "empty = no content
      change" signal — dismiss as CRLF-only, not real drift). Exits 1 and
      prints a unified diff of the stripped content when it differs (real
      drift signal). Exits 1 with a one-line stderr message if either path
      is missing or unreadable.

Negative-spec: this module does NOT invoke publish.py, does NOT resolve
$_cc_claude_klabauter/$_cc_trusted itself (both are caller/D2 concerns), and does NOT
mutate .percolate-ignore, publish-targets.portable, or any percolated
source/dest content — read-only gate logic only. It also does NOT execute
pre-ci shell hooks (the former `run-pre-ci-hooks` subcommand, removed
2026-07-24 once the declarative engine-side pre-ci guard reached parity —
see docs/plans/2026-07-24-extirpate-orphaned-claude-central-publish-shell.md).
It also does NOT resolve a python3/python interpreter for the skill's Step
2c/Step 5a CI-smoke invocations — that hand-rolled interpreter-discovery
prose routes through the existing resolve-python seam, not this module
(C4's L151/L274 concern, out of scope for this port).

Spec backlink: coordinator/skills/percolate/SKILL.md (DoE-claude) — Branch 0,
Step 2a, Step 2c, Step 2d. Port chunk: M3 C-PERCOLATE, W1.7/C4.
"""
from __future__ import annotations

import argparse
import difflib
import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, NamedTuple, Optional, Tuple

_BIN_DIR = Path(__file__).resolve().parent
_LIB_DIR = _BIN_DIR.parent / "lib"
# Both rungs are load-bearing and neither substitutes for the other. `_LIB_DIR`
# resolves this module's own short-form imports (`from percolate.targets import
# ...`). `_REPO_ROOT` resolves the ABSOLUTE form those same modules use between
# themselves -- `coordinator/lib/percolate/targets.py` does `from
# coordinator.lib.percolate.resolve_target import ...`, which needs the repo
# root on the path, not the lib dir. With only the lib rung present, the short
# import resolved and then died one frame deeper on `No module named
# 'coordinator'`, so EVERY subcommand raised ModuleNotFoundError at its first
# engine call -- including `scan-secrets`, whose HIGH tier is the publish-
# blocking credential gate. Failure was invisible to `--help`, which argparse
# serves without ever entering a subcommand body.
_REPO_ROOT = _BIN_DIR.parent.parent

_BOOTSTRAP_DONE = False


def _bootstrap_engine() -> None:
    """Put lib/ (short-form `percolate.*` imports) and the repo root (the
    absolute-form imports those modules use between themselves) on sys.path.

    Moved out of module scope: this used to mutate sys.path on every import
    of this file, a process global ~50 warm-server sessions share. Only the
    trigger moved; both rungs remain load-bearing (see the comment this
    replaced, preserved above the original assignment).
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    for _rung in (_LIB_DIR, _REPO_ROOT):
        if str(_rung) not in sys.path:
            sys.path.insert(0, str(_rung))
    _BOOTSTRAP_DONE = True


_PUBLISH_PY = _BIN_DIR / "publish.py"


def _import_publish_module():
    """Import `coordinator/bin/publish.py` in-process via `importlib.util`
    (same idiom `percolate-sweep-scope-probe.py::_import_publish_module`
    uses) so this gate consults `resolve_percolate_identity_path`'s two-rung
    ladder rather than carrying a second, drifting copy of it."""
    spec = importlib.util.spec_from_file_location("_percolate_gate_publish", _PUBLISH_PY)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not build a module spec for {_PUBLISH_PY}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Branch 0 — first-run setup gate
# ---------------------------------------------------------------------------

def _shares_one_destination(dests: List[str]) -> bool:
    """True iff some dest in `dests` contains every other — i.e. the rows
    publish into a single mirror rather than several. Compared as normalized
    POSIX strings because `load_targets` already emits forward-slash dest
    paths regardless of host.

    Lowercased before comparing, so `X:/Foo` and `x:/foo` read as the same
    destination — correct on this Windows-first repo, where the filesystem is
    case-insensitive and identical rows can differ only by casing accident.
    That is wrong in principle on a case-sensitive filesystem, where two
    distinct directories differing only in case would be merged into one. The
    cost is bounded: this function only feeds the `route:` diagnostic hint
    below, and the branch of `_cmd_branch0_gate` that can reach it has already
    decided to exit 1, so a false merge at worst suggests `coordinator-publish`
    on a row that already targets the same mirror — a redundant same-mirror
    publish, never a wrong-mirror one.

    `.lower()`, deliberately, NOT `.casefold()`. Review (code-reviewer on
    d062782b) constructed `X:/aß` against `X:/ass/sub` (abs-path-ok: synthetic
    pair): casefold maps `ß` to `ss`, so those two genuinely-distinct
    directories collapse to the same string and read as nested. That is a
    conflation, not an ordering problem —
    no choice of root fixes it, because the information is gone before the
    comparison starts. `.lower()` leaves `ß` alone.

    Two things that claim is NOT (review: code-reviewer on c532740ad, which
    caught the first draft of this paragraph overstating both):

      * It is not "the case mapping Windows uses". NTFS compares through
        `RtlUpcaseUnicodeChar`, a fixed-width uppercase table pinned to the
        Unicode version the volume was formatted under; it maps 1:1 per UTF-16
        code unit and cannot expand one character into two. Python's Unicode
        lowering is neither fixed-width nor version-pinned. The two agree
        across the ASCII drive-letter mirror paths this repo actually
        produces, which is why this works — not because they are the same
        function.
      * It does not close the conflation class, only this instance of it.
        `'\u0130'.lower()` (LATIN CAPITAL I WITH DOT ABOVE) expands to `i` plus
        COMBINING DOT ABOVE, so `X:/İfoo` and `X:/i\u0307foo/sub` collide
        exactly the way `ß` did. Left unguarded deliberately: real dest paths
        here are ASCII, and the containment scan below cannot help once two
        strings are genuinely equal. If dest paths ever stop being ASCII, this
        is the assumption that breaks.

    `str.lower()` is locale-independent — it applies only Unicode's
    unconditional case mappings, never the `tr`/`az` conditional dotted-I
    rule — so this does not vary with the host's locale.

    Root selection still asks which candidate contains the rest rather than
    picking the shortest STRING, so nothing depends on a length ordering that
    a case mapping could perturb. The list is one entry per matched row, so
    the quadratic scan is free."""
    if not dests:
        return False
    normalized = {d.replace("\\", "/").rstrip("/").lower() for d in dests}
    return any(
        all(d == root or d.startswith(root + "/") for d in normalized)
        for root in normalized
    )


def _missing_target_entry_guidance(target: str, all_rows: List[List[str]]) -> List[str]:
    """Lines to print after `MISSING_TARGET_ENTRY`, resolving the operator's
    actual next move rather than leaving them to infer it.

    The case this exists for: claude-klabauter registers NINE `claude-klabauter*` rows
    against one mirror, and no row is named for the mirror itself, so
    `/percolate klabauter` — the obvious thing to type — misses every row.
    `percolate-round` is single-target by construction, so the correct move is
    `coordinator-publish`, and the previous behaviour (a bare
    `MISSING_TARGET_ENTRY`, with `percolate-round` then offering the first-run
    setup walk) steered an operator into re-registering nine rows that already
    exist. That routing rule was real, load-bearing, and enforced only by a
    paragraph of skill prose; this is the artifact that discharges it.

    A row matches `target` when every dash-delimited token of `target` appears
    among the row's own tokens — a token-set-subset test (`wanted <= set(...)`),
    not a prefix or a sequential-infix test: order and adjacency are ignored,
    so target `a-b` also matches a row tokenizing to `a-x-b`. It is still not a
    PREFIX test — `klabauter` matches `claude-klabauter` because the single
    token is present anywhere, so a prefix test would not have fired for the
    exact input this exists to answer. A genuine typo (`claude-klabautr`)
    tokenizes to nothing that matches and correctly falls through to the
    registered-names line, which is what tells an operator "mistyped" apart
    from "never registered". A looser-than-intended match is low-risk: the
    only branch of `_cmd_branch0_gate` that calls this one has already
    appended `MISSING_TARGET_ENTRY` and exits 1 whatever comes back (the
    clean path exits 0 with `CONFIGURED:` and never reaches here), and a
    spurious match only reaches the `route:` line below when the matched rows
    also share one destination (`_shares_one_destination`) — capping the
    damage at a redundant same-mirror publish, never a wrong-mirror one.

    Emits a `route:` line only when routing is actually the answer (two or more
    matched rows sharing one destination). `percolate-round.py::_branch0_gate`
    keys on that literal prefix to suppress its own first-run-setup offer,
    which would otherwise contradict this line; every other caller ignores it,
    branching on the exit code and a `CONFIGURED:` prefix alone."""
    known = sorted({row[0] for row in all_rows})
    if not known:
        return []

    wanted = {tok for tok in target.split("-") if tok}
    matched = [row for row in all_rows if wanted <= set(row[0].split("-"))]

    if len(matched) == 1:
        return ["did you mean: " + matched[0][0]]

    if len(matched) > 1 and _shares_one_destination([row[3] for row in matched]):
        names = sorted(row[0] for row in matched)
        # All of them: echo the operator's own word — `publish.py`'s
        # `_mirror_sigil_for_alias` resolves it to the same mirror — so the
        # printed line is runnable verbatim.
        argument = " " + (target if len(names) == len(known) else ",".join(names))
        return [
            f"route: {len(names)} rows match '{target}' and share one destination; "
            f"percolate-round is single-target. Use: coordinator-publish{argument}"
        ]

    return ["registered: " + ", ".join(known)]


def _cmd_branch0_gate(args: argparse.Namespace) -> int:
    _bootstrap_engine()
    from percolate.targets import TargetsError, load_targets  # noqa: E402

    setup_dir = Path(args.percolate_root) / "setup"
    target = args.target
    reasons: List[str] = []
    source_dir: Optional[Path] = None

    try:
        rows = load_targets(setup_dir, target_filter=target)
    except TargetsError:
        reasons.append("MISSING_TARGETS")
    else:
        match = next(
            (row.split("|") for row in rows if row.split("|", 1)[0] == target), None
        )
        if match is None:
            reasons.append("MISSING_TARGET_ENTRY")
            try:
                all_rows = [row.split("|") for row in load_targets(setup_dir)]
            except TargetsError:
                all_rows = []
            reasons.extend(_missing_target_entry_guidance(target, all_rows))
        else:
            source_dir = Path(match[2])
            if not (source_dir / ".percolate-ignore").is_file():
                reasons.append("MISSING_IGNORE")

    if reasons:
        for reason in reasons:
            print(reason)
        return 1

    print(f"CONFIGURED:{source_dir}")
    return 0


# ---------------------------------------------------------------------------
# Step 2c — content-leakage scan
# ---------------------------------------------------------------------------

# Tier HIGH — credential / secret shapes. Any hit blocks the publish.
_TIER_HIGH = re.compile(
    r"(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|"
    r"AKIA[A-Z0-9]{16}|xox[bpars]-[A-Za-z0-9-]{10,}|ya29\.[A-Za-z0-9_-]{20,}|"
    r"-----BEGIN [A-Z ]+PRIVATE KEY-----)"
)

# Tier MEDIUM — generic identity/internal-path shapes (no operator-specific
# literals — see the skill's Step 2c note on why macOS/BSD grep -E's lack of
# \b support keeps this tier separate from publish.py's PERSONAL_REVIEW_PATTERNS
# audit; Python's `re` supports \b natively so that constraint does not carry
# over to this port, but the pattern SET is kept identical for parity).
#
# The email-shape alternative requires a non-empty local part directly
# abutting `@` — a Python decorator (`@pytest.mark.parametrize(`) has no
# such local part, only leading whitespace, so it no longer collides. The
# lookahead after `@` excludes RFC 2606 reserved test domains
# (example.com/.net/.org, and test/invalid/localhost as the domain's
# complete FINAL label) — never real identity, always fixture data. Both
# branches require the reserved form to be the whole domain or its trailing
# label — `(?![A-Za-z0-9.-])` after each alternative rejects a same-label
# continuation (`test-domain.com`, `invalid-corp.io`) and a further-label
# continuation (`localhost.internal.example`), so only a genuine reserved
# suffix (`foo.test`, `sub.example.test`) or the bare `example.com`/`.net`/
# `.org` domain is exempt — never a bare-word prefix match. `example` is in
# the final-label set because RFC 2606 reserves the `.example` TLD as well as
# the three second-level `example.*` domains (`t@t.example` is fixture data).
_TIER_MEDIUM = re.compile(
    r"(~/\.claude/(tasks|projects|memory|plans)/|/x/[a-z-]+|[XxCc]:/[a-z-]+|"
    r"[A-Za-z0-9._%+-]+@"
    r"(?!(?:example\.(?:com|net|org)|"
    r"(?:[A-Za-z0-9-]+\.)*(?:test|example|invalid|localhost))(?![A-Za-z0-9.-]))"
    r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b)"
)

# A MEDIUM path-shape match is discharged -- it names no machine -- when the
# segment it roots is a placeholder, or when its line carries the fleet's
# same-line path marker with a reason. Both rules mirror
# `coordinator_core.ops.session.guard_concrete_path_citations`
# (`_is_placeholder_segment`, `_PLACEHOLDER_WORDS`, `_MARKER_RE` and its
# reason-mandatory check), restated here rather than imported: that module's
# import costs ~27 ms on a gate that runs inside every percolate round. The
# restatement is a SUPERSET as of the extension rule below -- that guard reads
# a cited path, which carries no leaf-file fixtures, so it has no equivalent. The
# email alternative is never discharged by either rule -- the path marker
# adjudicates a path, not an identity; its one discharge is the public-forge
# service address (`_is_forge_service_address`), which is not an identity at
# all.
#
# Negative-spec: this is NOT an allowlist of files or literals. A drive or
# `/x/` root followed by a real repo name, or a Claude projects dir followed
# by a real slug, still gates, as does a bare path marker with no reason, and
# a line whose placeholder match sits beside a concrete one gates on the
# concrete one.
_PLACEHOLDER_SEGMENT_WORDS = frozenset(
    {
        "alice", "bob", "username", "you", "me",
        "foo", "bar", "baz", "test", "example", "someone",
        "operator", "yourname",
        "host", "hostname", "server", "share", "fileserver", "machine",
    }
)
_PATH_MARKER_RE = re.compile(r"(?:^|[^A-Za-z0-9_])(?:abs-path-ok|foreign-path-ok):")
_PATH_SEGMENT_RE = re.compile(r"[^/\\\s`'\"()\[\],;]*")
_PATH_ROOT_LEN = 3

# A placeholder segment may carry a file extension: an extension is a TYPE, not
# a name, so the stem is what the placeholder rule reads. `/x/y.md` is a
# synthetic fixture path in both segments and names nothing on any machine.
#
# Negative-spec: only the stem's own placeholder shape discharges it. A real
# stem under any extension still gates (`/x/notes.md`, `/x/claude-klabauter`),
# and a deeper path is still read at its rooted segment, so
# `/x/cross-repo/archive/a.md` gates on `cross-repo` -- the leaf `a.md` is
# never what the rule looks at.
_PATH_EXTENSION_RE = re.compile(r"\.[A-Za-z0-9]{1,8}$")

# A slash-rooted MEDIUM match preceded by a path character roots nothing: it
# is an interior slice of a longer path, and the segment it names is read by
# the same placeholder rule the rooted case uses.
_INTERIOR_ROOT_PREFIX_RE = re.compile(r"[A-Za-z0-9._-]")
_SLASH_ROOT_RE = re.compile(r"^/([^/]+)/")

# An email-shape match whose local part is the forge's own service account at
# a PUBLIC forge host is a service address every clone of a public repo
# carries -- generic by construction, naming no person and no machine of ours.
_FORGE_SERVICE_LOCAL_PART = "git"
_PUBLIC_FORGE_HOSTS = frozenset(
    {"github.com", "gitlab.com", "bitbucket.org", "codeberg.org", "git.sr.ht"}
)


def _line_has_path_marker(line: str) -> bool:
    return any(line[m.end():].strip() for m in _PATH_MARKER_RE.finditer(line))


def _is_placeholder_segment(segment: str) -> bool:
    if not segment:
        return False
    if segment == "..." or segment[0] in "<${*":
        return True
    if len(segment) == 1 and segment.isalpha():
        return True
    if segment.lower() in _PLACEHOLDER_SEGMENT_WORDS:
        return True
    stem = _PATH_EXTENSION_RE.sub("", segment)
    return stem != segment and _is_placeholder_segment(stem)


def _is_interior_placeholder_root(line: str, match: "re.Match[str]") -> bool:
    """Does this slash-rooted MEDIUM match sit MID-path on a placeholder segment?

    `refs/x/old` is a git ref namespace, not the `x` drive: the match `/x/old`
    is preceded by a path character, so its leading `/` roots nothing and `x`
    is an interior single-letter segment -- a placeholder under exactly the
    reading `_is_placeholder_segment` already applies one segment further
    along.

    Negative-spec: this discharges nothing that names a machine. A path-rooted
    `/x/claude-klabauter` (nothing path-like before the `/`) and every `X:/...`
    drive form are untouched and still gate, as does any interior segment the
    placeholder rule does not already accept.
    """
    root = _SLASH_ROOT_RE.match(match.group(0))
    if root is None:
        return False
    start = match.start()
    if start == 0 or not _INTERIOR_ROOT_PREFIX_RE.match(line[start - 1]):
        return False
    return _is_placeholder_segment(root.group(1))


def _is_forge_service_address(token: str) -> bool:
    """Is ``token`` a public code-forge's SSH service address (`git@github.com`)?

    The local part is the forge's fixed service account, not a person, and the
    host is a public service every clone URL of that forge repeats verbatim.

    Negative-spec: not an allowlist of files, lines or literals, and it is the
    ONLY discharge an email-shape match ever gets. Any other local part at
    these hosts still gates (`someone@github.com`), and `git@` at any other
    host -- a self-hosted forge, a company domain -- still gates.
    """
    local, _, host = token.partition("@")
    return local.lower() == _FORGE_SERVICE_LOCAL_PART and host.lower() in _PUBLIC_FORGE_HOSTS


def _medium_line_gates(line: str) -> bool:
    """Does ``line`` carry at least one MEDIUM match that is not discharged?"""
    marked = None
    for match in _TIER_MEDIUM.finditer(line):
        token = match.group(0)
        if "@" in token:
            if _is_forge_service_address(token):
                continue
            return True
        if _is_interior_placeholder_root(line, match):
            continue
        if marked is None:
            marked = _line_has_path_marker(line)
        if marked:
            continue
        seg_start = match.end() if token.startswith("~") else match.start() + _PATH_ROOT_LEN
        segment = _PATH_SEGMENT_RE.match(line, seg_start).group(0)
        if not _is_placeholder_segment(segment):
            return True
    return False

# Tier LOW — informational only (40-char hex commit SHAs, doctrine language).
_TIER_LOW = re.compile(r"(\b[0-9a-f]{40}\b|First Officer Doctrine)")

# Stable, non-prose panel markers for the MEDIUM tier's two-panel render
# (see `_cmd_scan_secrets`). `percolate-round.py::_count_medium_hits`
# reads these to find the Panel A/B boundary without pattern-matching on
# the human-facing header text, which is free to reword. Panel A
# (informational, pre-transform peer-repo-name reads) is never gate
# input; Panel B (gating) is what Step 3's medium-hit count consumes.
_MEDIUM_PANEL_INFORMATIONAL_MARKER = "##SCAN-PANEL:INFORMATIONAL##"
_MEDIUM_PANEL_GATING_MARKER = "##SCAN-PANEL:GATING##"


def _scan_file(
    path: Path,
    pattern: re.Pattern,
    line_gates: Optional[Callable[[str], bool]] = None,
) -> List[Tuple[Path, int, str]]:
    hits: List[Tuple[Path, int, str]] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            for lineno, line in enumerate(fh, start=1):
                if pattern.search(line) and (line_gates is None or line_gates(line)):
                    hits.append((path, lineno, line.rstrip("\n")))
    except OSError:
        pass
    return hits


def _redact_high(line: str) -> str:
    """Redact any HIGH-tier secret token to its first 4 chars + ellipsis,
    per the skill's panel-rendering contract."""

    def _sub(match: "re.Match[str]") -> str:
        token = match.group(0)
        return token[:4] + "..."

    return _TIER_HIGH.sub(_sub, line)


def _load_file_list(files_path: Path) -> List[Path]:
    if not files_path.is_file():
        return []
    lines = files_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return [Path(line) for line in lines if line.strip()]


def _peer_repo_pattern(peer_repos_file: Optional[Path], target: str) -> Optional[re.Pattern]:
    if peer_repos_file is None or not peer_repos_file.is_file():
        return None
    text = peer_repos_file.read_text(encoding="utf-8", errors="ignore")
    names = re.findall(r"^- shortname:\s*(\S+)", text, re.M)
    names = [n for n in names if n != target]
    if not names:
        return None
    alternation = "|".join(re.escape(n) for n in names)
    return re.compile(rf"\b({alternation})\b")


def _target_declares_registry_codename_guard(percolate_root: Optional[Path], target: str) -> bool:
    """Does ``target``'s resolved `percolate-store.yaml` section declare a
    `no-residual-pattern` guard whose `pattern_source` is a `registry_codenames`
    descriptor (§ `coordinator_core.ops.percolate_run._registry_pattern_resolver`)?

    This is the same declaration Step 0.6 names as engine-native, and is the
    ONLY signal this module treats as "the peer-repo scan leg's hits are about
    to be rewritten by depersonalize before publish, not shipped verbatim as
    read here". No percolate_root, no target, or a target the store does not
    declare all resolve to False -- the same outcome as no transform being
    declared, never a guess. A store that fails to PARSE is left to raise:
    this function does not swallow a parse failure into a silent False, since
    that would misreport an unrelated store defect as "no transform covers
    this target". Deliberately bypasses `store.load_store`'s full
    `validate_store_dict` pass (stale-baseline reporting and all) -- this is
    a read-only guard-declaration lookup, not a store-authoring lint, and
    `load_store`'s validation side effects print to the same stdout this
    scan renders its panel on.
    """
    if percolate_root is None or not target:
        return False
    store_path = percolate_root / "setup" / "percolate-hooks" / "percolate-store.yaml"
    if not store_path.is_file():
        return False

    _bootstrap_engine()
    import yaml

    from coordinator_core.percolate.store import resolve_target  # noqa: E402

    with store_path.open("r", encoding="utf-8") as fh:
        store = yaml.safe_load(fh)
    if not isinstance(store, dict):
        return False

    try:
        section = resolve_target(store, target)
    except KeyError:
        return False

    for guard in section.get("guards") or []:
        if guard.get("kind") != "no-residual-pattern":
            continue
        pattern_source = (guard.get("params") or {}).get("pattern_source")
        if isinstance(pattern_source, dict) and pattern_source.get("registry_codenames") is True:
            return True
    return False


def _cmd_scan_secrets(args: argparse.Namespace) -> int:
    _bootstrap_engine()
    files = _load_file_list(Path(args.files))

    high_hits: List[Tuple[Path, int, str]] = []
    medium_hits: List[Tuple[Path, int, str]] = []
    medium_covered_hits: List[Tuple[Path, int, str]] = []
    low_hits: List[Tuple[Path, int, str]] = []

    medium_pattern = _TIER_MEDIUM
    peer_pattern = _peer_repo_pattern(
        Path(args.peer_repos_file) if args.peer_repos_file else None, args.target or ""
    )
    transform_covers_peer = _target_declares_registry_codename_guard(
        Path(args.percolate_root) if getattr(args, "percolate_root", None) else None,
        args.target or "",
    )
    if args.target and not getattr(args, "percolate_root", None):
        # --target without --percolate-root silently
        # skips the transform-coverage split with no signal; state it once.
        print(
            "  NOTE: --percolate-root not passed — transform-coverage split "
            "(§ AC1/AC2) skipped; peer-repo-name hits render in the plain "
            "unsplit group."
        )

    for path in files:
        high_hits.extend(_scan_file(path, _TIER_HIGH))
        medium_hits.extend(_scan_file(path, medium_pattern, _medium_line_gates))
        if peer_pattern is not None:
            peer_hits = _scan_file(path, peer_pattern)
            if transform_covers_peer:
                medium_covered_hits.extend(peer_hits)
            else:
                medium_hits.extend(peer_hits)
        low_hits.extend(_scan_file(path, _TIER_LOW))

    identity_file = Path(args.identity_file) if args.identity_file else None
    resolved_identity_file: Optional[Path] = None
    if identity_file is not None:
        setup_dir = identity_file.parent
        try:
            publish_module = _import_publish_module()
            resolved_identity_file = publish_module.resolve_percolate_identity_path(setup_dir)
        except Exception:
            # Ladder resolution itself failed (e.g. publish.py import broke) --
            # fall back to the single per-repo stat this gate used before the
            # ladder existed, rather than mis-firing UNCONFIGURED on a resolver
            # bug that has nothing to do with identity-file presence.
            resolved_identity_file = identity_file if identity_file.is_file() else None

    if identity_file is not None and resolved_identity_file is None:
        print(
            "  NOTE: setup/.percolate-identity not found — machine-slug detection"
        )
        print(
            "        (PERSONAL_REVIEW_PATTERNS in publish.py Phase-4) is UNCONFIGURED."
        )
        print(
            "        Copy setup/.percolate-identity.example -> .percolate-identity and"
        )
        print("        populate PERSONAL_REVIEW_PATTERNS with your machine codenames.")
        print(
            "        This Step 2c scan covers generic shapes only; operator-specific"
        )
        print("        tokens are NOT scanned until .percolate-identity is in place.")
    elif resolved_identity_file is not None:
        if resolved_identity_file != identity_file:
            print(
                f"  NOTE: machine-slug detection configured via {resolved_identity_file} "
                "(machine-local rung; no per-repo setup/.percolate-identity)."
            )
        try:
            from percolate.phase4_audit import parse_percolate_identity  # noqa: E402

            identity = parse_percolate_identity(resolved_identity_file)
            if not identity.review:
                print(
                    "  NOTE: .percolate-identity exists but PERSONAL_REVIEW_PATTERNS is"
                )
                print(
                    "        empty — machine-slug detection is effectively unconfigured."
                )
                print("        Populate PERSONAL_REVIEW_PATTERNS with your machine codenames.")
        except Exception:
            pass

    print("Content-leakage scan:")
    print("  HIGH (credential/secret shapes -- BLOCKS publish):")
    if high_hits:
        for path, lineno, line in high_hits:
            print(f"    {path}:{lineno}: {_redact_high(line)}")
    else:
        print("    (none)")

    if transform_covers_peer:
        print(f"  {_MEDIUM_PANEL_INFORMATIONAL_MARKER}")
        print(
            "  MEDIUM -- peer-repo names, read pre-transform (depersonalize runs before "
            "publish; Phase-4 is the post-transform oracle):"
        )
        if medium_covered_hits:
            for path, lineno, line in medium_covered_hits:
                print(f"    {path}:{lineno}: {line}")
        else:
            print("    (none)")

    print(f"  {_MEDIUM_PANEL_GATING_MARKER}")
    print("  MEDIUM (identity / internal paths / peer-repo names -- surfaces to gate):")
    if medium_hits:
        for path, lineno, line in medium_hits:
            print(f"    {path}:{lineno}: {line}")
    else:
        print("    (none)")

    print("  LOW (informational -- commit SHAs, doctrine language):")
    if low_hits:
        files_touched = len({p for p, _, _ in low_hits})
        print(f"    {len(low_hits)} hits across {files_touched} files")
    else:
        print("    (none)")

    return 2 if high_hits else 0


# ---------------------------------------------------------------------------
# Step 2d — inverse-drift detection
# ---------------------------------------------------------------------------

_PATHSPEC_BATCH_BUDGET = 6000

# The two `git` calls below run through `coordinator_core.git.run.run_git` and
# are bounded by its LOCAL lane ceiling of 2.0s. They pass no `timeout=` of
# their own because there is no number they could pass that would matter:
# `run.py :: _resolve_budget` folds a caller's figure through `min()` against
# that ceiling, so the 60s hang detector this site used to carry resolved to
# 2.0s the moment it moved onto the seam. Carrying the constant anyway, with a
# comment claiming the ceiling was "headroom on top of" it, stated the
# relationship exactly backwards.
#
# 2.0s is the right bound, not merely the one we are given: both calls run
# `-C <dest>` against a LOCAL working tree (never a remote, so `remote=True`
# would be a lie to buy 30s), and a `git log` over a few hundred pathspecs is
# sub-second. A leg of this class exceeding 2.0s is a defect by this repo's
# own load norm, not a leg that needs a bigger number. If one ever does time
# out here, the honest fix is a grandfather entry in
# `test_shared_git_runner.py` with the argument written down -- NOT a wider
# timeout, which the seam will refuse to honour anyway.


def _resolve_target_source_dir(percolate_root: Path, target: str) -> Optional[Path]:
    """Resolve a target's source dir the same way ``branch0-gate`` does.

    Lets ``inverse-drift`` map a source-built file list onto the destination
    tree without every caller having to pass ``--source-dir`` — the skill's
    documented Step 2d invocation predates that flag, and a guard that only
    works when the caller remembers an argument is the failure mode this
    resolution exists to remove.
    """
    _bootstrap_engine()
    try:
        from percolate.targets import TargetsError, load_targets  # noqa: E402
    except ImportError:
        return None

    try:
        rows = load_targets(percolate_root / "setup", target_filter=target)
    except TargetsError:
        return None

    match = next((row.split("|") for row in rows if row.split("|", 1)[0] == target), None)
    if match is None or len(match) < 3:
        return None
    return Path(match[2])


_LEGACY_SOURCE_STAMP = r" \[source [0-9a-f]{12}\]"


class _DriftLog(NamedTuple):
    """What ``_git_log_batched`` found in the anchor window, already sorted
    into the three classes Step 2d reports."""

    drift_lines: List[str]
    publisher_commits: int
    superseded_commits: int


def _drift_log_cmd_base(dest: Path) -> List[str]:
    """The one ``git log`` shape ``_git_log_batched`` parses.

    ``%x1e`` opens each record so ``--name-only``'s path lines stay attached
    to their commit; ``%ct`` orders the union across batches; ``--topo-order``
    puts every descendant ahead of its ancestors, which the supersession walk
    relies on; ``--no-renames`` keeps both sides of a rename visible as paths.
    """
    return [
        "-C", str(dest), "log", "--no-merges", "--no-renames", "--topo-order",
        "--name-only", "--date=short", "--format=%x1e%ct %h %ad %s",
    ]


def _publisher_stamp_re() -> "re.Pattern[str]":
    """Matches a commit subject the publisher itself wrote into dest.

    Every percolate leg that commits into a mirror (``publish.py``,
    ``percolate-round.py``, ``percolate-mirror.py``) ends its subject with the
    stamp ``coordinator_core.git.git_state.format_source_sha_suffix`` spells,
    so the current spelling is derived from that function rather than copied
    here. ``[source <sha12>]`` is the stamp's own earlier spelling (renamed
    2026-09-04), still present in mirror history.

    Negative-spec: NOT a match on the prose prefixes (``percolate publish:``,
    ``percolate: sync``, ``engine sync from ...``). Those drift, and a hand
    commit can reuse one. The stamp is machine-written and anchored at the
    end of the subject.
    """
    _bootstrap_engine()
    from coordinator_core.git.git_state import format_source_sha_suffix  # noqa: E402

    probe = "0" * 12
    current = re.escape(format_source_sha_suffix(probe)).replace(probe, "[0-9a-f]{12}")
    return re.compile(rf"(?:{current}|{_LEGACY_SOURCE_STAMP})$")


def _git_log_batched(
    log_cmd_base: List[str],
    revision_args: List[str],
    rel_paths: List[str],
) -> _DriftLog:
    """Run ``git log`` over ``rel_paths`` in command-line-safe batches, and
    separate hand-authored drift from the publisher's own history.

    ``log_cmd_base`` carries no leading ``"git"`` (it goes straight to
    ``run_git``) and must be ``_drift_log_cmd_base``'s shape.

    Windows caps a process command line at 32767 characters, and a mirror row
    can carry hundreds of pathspecs. Passing them in one invocation raises
    ``FileNotFoundError: [WinError 206] The filename or extension is too long``
    and takes the whole inverse-drift check down with it. ``git log`` has no
    ``--pathspec-from-file`` (verified against git 2.55: *unrecognized
    argument*; the flag exists on add/commit/checkout/reset only), so batching
    is the portable route rather than stdin.

    Classification, per commit in the window:

    * publisher: its subject carries the source-head stamp
      (``_publisher_stamp_re``). Its bytes ARE the source's, so a sync
      cannot overwrite anything of a human's in it.
    * superseded: hand-authored, but a later publisher commit rewrote every
      path of it the window covers, so what it changed is already gone from
      HEAD. There is nothing left for this sync to overwrite.
    * drift: hand-authored, with at least one path no later publisher commit
      touched. That path's dest bytes are a human's, and this sync
      overwrites them.

    Supersession is judged per batch. A path lives in exactly one batch, so
    every commit touching it is listed there in git's topological order.

    Negative-spec: batches are a command-line-length concession, NOT a scope
    narrowing. Every pathspec is still queried, and a commit spanning two
    batches is reported once, as drift if any batch finds it live. A
    hand-authored commit with no listed path counts as drift, not as
    superseded.
    """
    if not rel_paths:
        return _DriftLog([], 0, 0)

    batches: List[List[str]] = []
    current: List[str] = []
    current_len = 0
    for rel in rel_paths:
        entry_len = len(rel) + 1
        if current and current_len + entry_len > _PATHSPEC_BATCH_BUDGET:
            batches.append(current)
            current = []
            current_len = 0
        current.append(rel)
        current_len += entry_len
    if current:
        batches.append(current)

    from coordinator_core.git.run import run_git  # noqa: E402

    stamp_re = _publisher_stamp_re()
    display: dict[str, tuple[int, str]] = {}
    publisher: set[str] = set()
    hand_authored: set[str] = set()
    drifting: set[str] = set()
    for batch in batches:
        cmd = log_cmd_base + revision_args + ["--"] + batch
        result = run_git(cmd)
        if result.returncode != 0:
            # A destination with no commits yet is a legitimate "no history,
            # so no drift" — not the swallowed-error class this raise exists
            # to expose (WinError 206, bad pathspec, unreadable repo).
            if "does not have any commits yet" in result.stderr:
                return _DriftLog([], 0, 0)
            raise RuntimeError(
                f"git log failed (exit {result.returncode}) on a {len(batch)}-pathspec "
                f"batch: {result.stderr.strip()}"
            )
        overwritten: set[str] = set()
        for record in result.stdout.split("\x1e"):
            header, _, body = record.partition("\n")
            fields = header.split(" ", 3)
            if len(fields) < 3:
                continue
            committed_at, sha, date = fields[:3]
            subject = fields[3] if len(fields) > 3 else ""
            paths = [p for p in body.splitlines() if p.strip()]
            if stamp_re.search(subject):
                publisher.add(sha)
                overwritten.update(paths)
                continue
            hand_authored.add(sha)
            display.setdefault(sha, (int(committed_at), f"{sha} {date} {subject}"))
            if not paths or any(p not in overwritten for p in paths):
                drifting.add(sha)

    ordered = sorted((display[sha] for sha in drifting), reverse=True)
    return _DriftLog(
        [line for _committed_at, line in ordered],
        len(publisher),
        len(hand_authored - drifting),
    )


def _emit_inverse_drift_verdict(
    anchor_mode: str,
    since_ref: Optional[str],
    drift_log: _DriftLog,
    rel_paths: List[str],
    dest: Path,
    source_dir: Optional[Path],
) -> int:
    """Machine-readable inverse-drift verdict, so a caller consumes a FIELD
    instead of a human reading prose.

    Three things it states rather than guesses:

    `anchor_reliable` — only `anchor_mode == "marker"` bounds the log at the
    last real sync. Under `30day-fallback`/`marker-stale` the window reaches
    further back than the last reviewed round.

    `publisher_commits_excluded` / `superseded_commits_excluded` — the
    publisher's own commits, and hand commits a later publish already
    rewrote (§ `_git_log_batched`). Neither is in `commit_lines`. Measured on
    claude-klabauter 2026-09-11: 231 listed commits, every one a stamped
    publish. Prose-prefix matching was rejected here earlier as a guess
    (three prefixes observed); the stamp is not a prefix. One formatter
    spells it and every publishing leg emits it.

    `crlf_only` — the sanctioned per-file dismissal (residue wiki §
    "Inverse-drift false-positive dismissal, in full"): source CRLF against an
    LF-normalized dest is not a content change. Applied by exact line compare,
    never a raw `diff`, because dest content has passed the depersonalize
    transform and so always differs from source verbatim.

    Deliberately NOT claimed: that a non-CRLF delta is real drift. The
    transform guarantees a byte difference, so the surviving set is a
    candidate list a human still adjudicates when the anchor is unreliable.
    """
    crlf_only: List[str] = []
    differing: List[str] = []
    for rel in rel_paths:
        dest_file = dest / rel
        source_file = (source_dir / rel) if source_dir else None
        if not dest_file.is_file() or source_file is None or not source_file.is_file():
            continue
        try:
            if _strip_cr_lines(dest_file) == _strip_cr_lines(source_file):
                crlf_only.append(rel)
            else:
                differing.append(rel)
        except OSError:
            differing.append(rel)

    verdict = {
        "anchor_mode": anchor_mode,
        "anchor_reliable": anchor_mode == "marker",
        "anchor_ref": since_ref,
        "commits": len(drift_log.drift_lines),
        "commit_lines": drift_log.drift_lines,
        "publisher_commits_excluded": drift_log.publisher_commits,
        "superseded_commits_excluded": drift_log.superseded_commits,
        "dismissed_crlf_only": crlf_only,
        "content_differs": differing,
        "real_drift": (
            bool(drift_log.drift_lines) and anchor_mode == "marker" and bool(differing)
        ),
    }
    print(json.dumps(verdict, indent=2))
    return 0


def _cmd_inverse_drift(args: argparse.Namespace) -> int:
    target = args.target
    percolate_root = Path(args.percolate_root)
    dest = Path(args.dest)
    files = _load_file_list(Path(args.files))

    marker = percolate_root / "setup" / "percolate-state" / f"{target}.lastsync"
    since_ref: Optional[str] = None
    anchor_mode = "30day-fallback"
    if marker.is_file():
        since_ref = marker.read_text(encoding="utf-8").strip()
        anchor_mode = "marker"

    # The Step 2c file list this shares is built from SOURCE paths, so a bare
    # relative_to(dest) misses on every entry. The old fallback appended the
    # absolute source path verbatim; git then matched nothing and the check
    # reported "no drift" unconditionally — a guard that cannot fire is worse
    # than one that crashes, so an unresolvable path is now fatal.
    source_dir = Path(args.source_dir) if getattr(args, "source_dir", None) else None
    if source_dir is None:
        source_dir = _resolve_target_source_dir(percolate_root, target)
    rel_paths: List[str] = []
    unresolved: List[str] = []
    for path in files:
        for root in (dest, source_dir):
            if root is None:
                continue
            try:
                rel_paths.append(str(path.relative_to(root)))
                break
            except ValueError:
                continue
        else:
            unresolved.append(str(path))

    if unresolved:
        print(
            f"percolate-gate: inverse-drift: {len(unresolved)} path(s) are under neither "
            f"--dest ({dest}) nor --source-dir ({source_dir}); pass --source-dir so the "
            f"file list can be mapped onto the destination tree. First: {unresolved[0]}",
            file=sys.stderr,
        )
        return 1

    log_cmd_base = _drift_log_cmd_base(dest)

    if anchor_mode == "marker":
        from coordinator_core.git.run import run_git  # noqa: E402

        verify = run_git(
            ["-C", str(dest), "rev-parse", "--verify", since_ref],
        )
        if verify.returncode != 0:
            anchor_mode = "marker-stale"

    if anchor_mode == "marker":
        revision_args = [f"{since_ref}..HEAD"]
    else:
        revision_args = ["--since=30 days ago"]

    drift_log = _git_log_batched(log_cmd_base, revision_args, rel_paths)
    log_lines = drift_log.drift_lines

    if getattr(args, "json", False):
        return _emit_inverse_drift_verdict(
            anchor_mode, since_ref, drift_log, rel_paths, dest, source_dir
        )

    print(f"anchor_mode: {anchor_mode}")
    if drift_log.publisher_commits or drift_log.superseded_commits:
        print(
            f"not drift: {drift_log.publisher_commits} publisher commit(s), "
            f"{drift_log.superseded_commits} hand commit(s) a later publish already rewrote"
        )

    if not log_lines:
        return 0

    anchor_desc = {
        "marker": since_ref or "",
        "30day-fallback": "30-day fallback (no marker)",
        "marker-stale": "marker-stale (SHA not in dest history)",
    }[anchor_mode]

    print("Inverse drift -- dest commits touching files about to be overwritten:")
    print(f"  anchor: {anchor_desc}")
    for line in log_lines:
        print(f"  {line}")
    print(
        "  -> Read each commit's diff before proceeding. If it's a real fix, "
        "back-port to source FIRST,"
    )
    print("    then re-run /percolate. Confirming below will OVERWRITE these changes.")
    return 0


# ---------------------------------------------------------------------------
# Step 2a — coverage-drift detection + last-reviewed date
# ---------------------------------------------------------------------------

def _cmd_coverage_drift(args: argparse.Namespace) -> int:
    source_dir = Path(args.source_dir)
    ignore_file = source_dir / ".percolate-ignore"
    if not ignore_file.is_file():
        return 0

    anchor_mtime = ignore_file.stat().st_mtime
    hits: List[Path] = []
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime > anchor_mtime:
                hits.append(path)
        except OSError:
            continue
        if len(hits) >= args.limit:
            break

    for path in hits:
        print(path)
    return 0


def _cmd_ignore_mtime(args: argparse.Namespace) -> int:
    ignore_file = Path(args.source_dir) / ".percolate-ignore"
    if not ignore_file.is_file():
        return 1

    mtime = datetime.fromtimestamp(ignore_file.stat().st_mtime, tz=timezone.utc)
    print(mtime.strftime("%Y-%m-%d"))
    return 0


# ---------------------------------------------------------------------------
# Step 2d — CRLF-only false-positive dismissal
# ---------------------------------------------------------------------------

def _strip_cr_lines(path: Path) -> List[str]:
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as fh:
        return [line.rstrip("\r\n") for line in fh]


def _cmd_crlf_diff(args: argparse.Namespace) -> int:
    dest_file = Path(args.dest_file)
    source_file = Path(args.source_file)

    for label, path in (("dest", dest_file), ("source", source_file)):
        if not path.is_file():
            print(f"crlf-diff: {label} file not found: {path}", file=sys.stderr)
            return 1

    try:
        dest_lines = _strip_cr_lines(dest_file)
        source_lines = _strip_cr_lines(source_file)
    except OSError as exc:
        print(f"crlf-diff: {exc}", file=sys.stderr)
        return 1

    if dest_lines == source_lines:
        return 0

    diff = difflib.unified_diff(
        dest_lines,
        source_lines,
        fromfile=str(dest_file),
        tofile=str(source_file),
        lineterm="",
    )
    for line in diff:
        print(line)
    return 1


# ---------------------------------------------------------------------------
# Step 0.5 — resolve-root
# ---------------------------------------------------------------------------

def _cmd_resolve_root(args: argparse.Namespace) -> int:
    _bootstrap_engine()
    from coordinator_core.percolate.runtime_root import (  # noqa: E402
        coordinator_percolate_runtime_root_explained,
    )

    try:
        path, rung = coordinator_percolate_runtime_root_explained()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.explain:
        print(f"{path}\t{rung}")
    else:
        print(path)
    return 0


# ---------------------------------------------------------------------------
# Step 1 / Step 5 — list-targets
# ---------------------------------------------------------------------------

def _cmd_list_targets(args: argparse.Namespace) -> int:
    _bootstrap_engine()
    from percolate.targets import TargetsError, load_targets  # noqa: E402

    setup_dir = Path(args.percolate_root) / "setup"
    try:
        rows = load_targets(setup_dir, target_filter=args.target)
    except TargetsError as exc:
        print(exc.message, file=sys.stderr)
        return 1

    if args.target:
        match = next(
            (row.split("|") for row in rows if row.split("|", 1)[0] == args.target),
            None,
        )
        if match is None:
            return 1
        print(match[3])
        return 0

    for row in rows:
        print(row.split("|", 1)[0])
    return 0



# ---------------------------------------------------------------------------
# publish-readiness — the one preflight that reports EVERY blocker at once
# ---------------------------------------------------------------------------

#: Bound for this subcommand's non-git remote probes (the GitHub REST/`gh`
#: calls below) -- the git spawns themselves are bounded by
#: `coordinator_core.git.run.run_git`'s own local/remote ceilings, never a
#: module-private number.
_READINESS_REMOTE_TIMEOUT_S = 120

_PASS, _WARN, _FAIL = "PASS", "WARN", "FAIL"


def _readiness_git(repo: str, args: "List[str]", *, remote: bool = False):
    _bootstrap_engine()
    from coordinator_core.git.run import run_git

    return run_git(["-C", repo, "--no-optional-locks", *args], remote=remote)


def _check_engine_root(findings: "List[tuple]") -> Optional[str]:
    """Rung 1 of the report: which engine tree will percolate bind, and does it
    carry the percolate package at all.

    First because it is the one failure that makes every later check a lie: a
    run bound to a published mirror cannot import `coordinator_core.percolate`,
    so it dies before resolving a single target and the operator learns nothing
    about the four problems waiting behind it.
    """
    root = str(_REPO_ROOT)
    dispatch = os.environ.get("COORDINATOR_ENGINE_ROOT", "")
    if (Path(root) / "coordinator_core" / "percolate").is_dir():
        detail = "percolate engine source: {0}".format(root)
        if dispatch and os.path.realpath(dispatch) != os.path.realpath(root):
            detail += " (dispatch root is {0}; a publish tool is on the LOCATOR axis, so this is expected)".format(dispatch)
        findings.append((_PASS, "engine-root", detail))
        return root
    findings.append((
        _FAIL,
        "engine-root",
        "'{0}' has no coordinator_core/percolate -- that is a published engine "
        "mirror, not the source checkout percolate publishes from.\n"
        "    Fix: run this from the engine SOURCE checkout, or set "
        "COORDINATOR_ENGINE_SOURCE_ROOT to it.".format(root),
    ))
    return None


def _check_targets(
    findings: "List[tuple]", percolate_root: str, mirror: Optional[str]
) -> "List[tuple]":
    """Resolve every registered row, reporting the resolver's OWN remediation.

    Returns the resolved `(name, source, dest)` tuples for the selected mirror,
    or `[]`. A resolution abort is one finding carrying the resolver's message
    verbatim -- it already names the exact registry key and the exact
    `machine-local set` command, and rewording it here would be a second copy to
    drift.
    """
    _bootstrap_engine()
    from percolate.targets import TargetsError, load_targets  # noqa: E402

    try:
        rows = load_targets(Path(percolate_root) / "setup", target_filter=None)
    except TargetsError as exc:
        findings.append((_FAIL, "registry", exc.message))
        return []

    parsed = []
    for row in rows:
        fields = row.split("|")
        if len(fields) >= 4:
            parsed.append((fields[0], fields[2], fields[3]))
    if not parsed:
        findings.append((_FAIL, "registry", "no publish targets resolved from any tier."))
        return []

    if mirror is None:
        findings.append((_PASS, "registry", "{0} row(s) resolved".format(len(parsed))))
        return parsed

    normalized = mirror.replace("-", "_").lower()
    selected = [
        r for r in parsed
        if r[0] == mirror
        or normalized in os.path.realpath(r[2]).replace("-", "_").lower()
    ]
    if not selected:
        findings.append((
            _FAIL,
            "registry",
            "no resolved row lands in a mirror matching '{0}'. Known rows: {1}".format(
                mirror, ", ".join(name for name, _, _ in parsed)
            ),
        ))
        return []
    findings.append((
        _PASS, "registry", "{0} row(s) resolved for '{1}'".format(len(selected), mirror)
    ))
    return selected


def _check_worktree(findings: "List[tuple]", dests: "List[str]") -> Optional[str]:
    """One git worktree root for every selected row's dest, and it is a
    worktree rather than this box's deployed engine."""
    roots = set()
    for dest in dests:
        proc = _readiness_git(dest if os.path.isdir(dest) else os.path.dirname(dest),
                              ["rev-parse", "--show-toplevel"])
        if proc is None or proc.returncode != 0:
            findings.append((
                _FAIL, "mirror-worktree",
                "'{0}' is not inside a git worktree.\n"
                "    Fix: clone the publish repo and point the registry key at "
                "the clone.".format(dest),
            ))
            return None
        roots.add(os.path.realpath(proc.stdout.strip()))
    if len(roots) != 1:
        findings.append((
            _FAIL, "mirror-worktree",
            "the selected rows land in {0} different worktrees: {1} -- one "
            "publish round writes one mirror.".format(len(roots), sorted(roots)),
        ))
        return None
    root = sorted(roots)[0]

    try:
        from coordinator_core.engine_root import is_published_engine_mirror

        if is_published_engine_mirror(root):
            findings.append((
                _FAIL, "mirror-worktree",
                "'{0}' IS this box's deployed engine mirror, not a publish "
                "worktree. Publishing there pushes onto the mirror's own "
                "checked-out branch.\n"
                "    Fix: machine-local set publish.mirrors.<key>.path "
                "<a SEPARATE clone>".format(root),
            ))
            return None
    except Exception:  # noqa: BLE001 -- fail-open, same contract as the predicate
        pass

    status = _readiness_git(root, ["status", "--porcelain"])
    dirty = len([ln for ln in (status.stdout or "").splitlines() if ln.strip()]) if status else 0
    findings.append((
        _PASS if not dirty else _WARN,
        "mirror-worktree",
        "{0}{1}".format(root, "" if not dirty else " ({0} uncommitted path(s) -- a "
                        "previous round may have stopped mid-run)".format(dirty)),
    ))
    return root


def _check_upstream(findings: "List[tuple]", root: str, *, fetch: bool) -> Optional[str]:
    """Branch, tracking state, and how far the clone is from the tip it will be
    measured against. Returns the checked-out branch name."""
    _bootstrap_engine()
    from percolate.dest_refresh import default_remote_branch  # noqa: E402

    head = _readiness_git(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    branch = head.stdout.strip() if head and head.returncode == 0 else ""
    if not branch or branch == "HEAD":
        findings.append((
            _FAIL, "upstream",
            "'{0}' is in detached HEAD -- a round cannot tell which branch it "
            "would land on.\n    Fix: git -C {0} checkout <branch>".format(root),
        ))
        return None

    if fetch:
        _readiness_git(root, ["fetch", "--no-tags", "--prune", "origin"], remote=True)

    up = _readiness_git(root, ["rev-parse", "--abbrev-ref", "@{u}"])
    base = up.stdout.strip() if up and up.returncode == 0 else ""
    if not base:
        base = default_remote_branch(Path(root)) or ""
        if not base:
            findings.append((
                _FAIL, "upstream",
                "'{0}' branch '{1}' has no upstream and the clone can name no "
                "remote default branch.\n"
                "    Fix: git -C {0} remote set-head origin --auto".format(root, branch),
            ))
            return branch
        note = " (no upstream; measured against the remote default branch)"
    else:
        note = ""

    counts = _readiness_git(root, ["rev-list", "--left-right", "--count", "HEAD..." + base])
    if counts is None or counts.returncode != 0:
        findings.append((
            _WARN, "upstream",
            "could not measure '{0}' against {1}{2}".format(branch, base, note),
        ))
        return branch
    parts = counts.stdout.split()
    ahead, behind = (int(parts[0]), int(parts[1])) if len(parts) == 2 else (0, 0)
    if ahead and behind:
        findings.append((
            _FAIL, "upstream",
            "'{0}' has diverged from {1} ({2} ahead, {3} behind){4} -- publishing "
            "over it would discard one side.\n"
            "    Fix: git -C {5} merge {1}".format(branch, base, ahead, behind, note, root),
        ))
        return branch
    findings.append((
        _PASS, "upstream",
        "{0} vs {1}: {2} ahead, {3} behind{4}".format(branch, base, ahead, behind, note),
    ))
    return branch


def _branch_rules_over_http(slug: str, branch: str) -> Optional[str]:
    """GitHub's branch-rules endpoint, read directly. `None` on any failure.

    Fail-open to `None` so the caller reports UNKNOWN rather than inventing
    either verdict; a proxy, an offline box, or a private repo with no token all
    land here and all mean "not answered", never "allowed".
    """
    import urllib.error
    import urllib.request

    url = "https://api.github.com/repos/{0}/rules/branches/{1}".format(slug, branch)
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(request, timeout=_READINESS_REMOTE_TIMEOUT_S) as response:
            return response.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 -- see docstring
        return None


def _check_ref_creation(findings: "List[tuple]", root: str, branch: str) -> None:
    """Would this push CREATE a ref on the remote, and is creation allowed.

    THE TRAP THIS CLOSES. `git push --dry-run` does NOT evaluate a GitHub
    repository ruleset: it reports success and the real push is then refused
    with `GH013 ... Cannot create ref due to creations being restricted`, after
    a full round has already run, committed, and left the mirror dirty. A
    dry-run that passes where the real action is refused is a false
    confirmation, so this asks the two questions the dry-run cannot:

      1. does `refs/heads/<branch>` already exist on the remote? If it does, the
         push UPDATES a ref and no creation rule applies.
      2. if it does not, does the remote restrict creation? Answered by `gh api
         repos/<owner>/<repo>/rules/branches/<branch>`, which reports the rules
         that WOULD apply. Without `gh`, or without credentials, this cannot be
         determined locally and the finding is a WARN naming what is unknown --
         never a PASS, because "we could not check" and "it is allowed" are the
         two answers this whole check exists to stop conflating.
    """
    import subprocess

    ls = _readiness_git(root, ["ls-remote", "--exit-code", "--heads", "origin", branch], remote=True)
    if ls is not None and ls.returncode == 0 and ls.stdout.strip():
        findings.append((
            _PASS, "ref-creation",
            "origin already has refs/heads/{0}; this push updates it".format(branch),
        ))
        return

    url = _readiness_git(root, ["remote", "get-url", "origin"])
    slug = ""
    if url is not None and url.returncode == 0:
        raw = url.stdout.strip()
        for prefix in ("https://github.com/", "git@github.com:", "ssh://git@github.com/"):
            if raw.startswith(prefix):
                slug = raw[len(prefix):]
                break
        if slug.endswith(".git"):
            slug = slug[: -len(".git")]

    if not slug:
        findings.append((
            _WARN, "ref-creation",
            "this push would CREATE refs/heads/{0} on origin, and origin is not a "
            "GitHub URL this check can query -- ref-creation permission UNKNOWN. "
            "`git push --dry-run` does NOT evaluate a remote's creation rules, so "
            "a passing dry-run is not evidence here.\n"
            "    Fix: confirm the branch is allowed, or land on a branch that "
            "already exists on origin.".format(branch),
        ))
        return

    payload = None
    try:
        proc = subprocess.run(
            ["gh", "api", "repos/{0}/rules/branches/{1}".format(slug, branch)],
            capture_output=True, text=True, timeout=_READINESS_REMOTE_TIMEOUT_S,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode == 0:
            payload = proc.stdout
    except Exception:  # noqa: BLE001 -- gh absent or unrunnable
        pass

    if payload is None:
        # `gh` is a convenience, not the capability. A cloud container commonly
        # has no `gh` on PATH while the REST endpoint is plainly reachable, and
        # leaving the answer UNKNOWN there would make the one environment this
        # whole check exists for the one it cannot serve. Token if present, no
        # token otherwise -- the endpoint answers unauthenticated for a public
        # repo, which every publish mirror is.
        payload = _branch_rules_over_http(slug, branch)

    if payload is None:
        findings.append((
            _WARN, "ref-creation",
            "this push would CREATE refs/heads/{0} on {1}. A repository ruleset "
            "can refuse that, and `git push --dry-run` does NOT evaluate rulesets "
            "-- it reports success and the real push fails with GH013 after the "
            "round has already run. `gh` could not answer here, so the permission "
            "is UNKNOWN.\n"
            "    Fix: confirm the branch is allowed, or land on a branch that "
            "already exists on origin.".format(branch, slug),
        ))
        return

    try:
        rules = json.loads(payload or "[]")
    except ValueError:
        rules = []
    restricted = [r for r in rules if isinstance(r, dict) and r.get("type") == "creation"]
    if restricted:
        existing = _readiness_git(root, ["ls-remote", "--heads", "origin"], remote=True)
        names = []
        if existing is not None and existing.returncode == 0:
            names = [
                ln.split("refs/heads/", 1)[1]
                for ln in existing.stdout.splitlines()
                if "refs/heads/" in ln
            ]
        findings.append((
            _FAIL, "ref-creation",
            "{0} FORBIDS ref creation, and this push would create "
            "refs/heads/{1}. The real push fails with GH013; a --dry-run does "
            "not evaluate this rule and reports success.\n"
            "    Fix: land on one of the branches that already exist on origin: "
            "{2}".format(slug, branch, ", ".join(sorted(names)) or "(none readable)"),
        ))
        return
    findings.append((
        _PASS, "ref-creation",
        "{0} permits creating refs/heads/{1}".format(slug, branch),
    ))


def _cmd_publish_readiness(args: argparse.Namespace) -> int:
    """Every blocker on the publish path, in one invocation.

    WHY ONE COMMAND AND NOT FIVE. Each of these failures only becomes visible
    once the one before it is fixed, so discovering them costs one full run
    each -- and a publish run is minutes and writes to a shared clone. Serial
    rediscovery IS the defect; this reports all of them together and never stops
    at the first, which is why every check below degrades to a finding instead
    of returning early.

    Exit 0 when nothing FAILED (WARNs do not gate -- an unanswerable question is
    not a refusal), 1 when anything did.
    """
    findings: "List[tuple]" = []

    root = _check_engine_root(findings)
    percolate_root = args.percolate_root or (root or str(_REPO_ROOT))

    rows = _check_targets(findings, percolate_root, args.mirror) if root else []
    worktree = _check_worktree(findings, [dest for _, _, dest in rows]) if rows else None
    branch = _check_upstream(findings, worktree, fetch=not args.no_fetch) if worktree else None
    if worktree and branch:
        _check_ref_creation(findings, worktree, branch)

    width = max((len(name) for _, name, _ in findings), default=0)
    print("=== percolate publish-readiness{0} ===".format(
        ": " + args.mirror if args.mirror else ""))
    for verdict, name, detail in findings:
        print("  [{0}] {1}  {2}".format(verdict.ljust(4), name.ljust(width), detail))
    failed = [f for f in findings if f[0] == _FAIL]
    print("--- {0} check(s): {1} pass, {2} warn, {3} fail ---".format(
        len(findings),
        sum(1 for f in findings if f[0] == _PASS),
        sum(1 for f in findings if f[0] == _WARN),
        len(failed),
    ))
    if failed:
        print("NOT READY: fix the FAIL line(s) above, then re-run this command.")
        return 1
    print("READY: every check that can be answered locally passes.")
    return 0


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="percolate-gate")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_branch0 = sub.add_parser("branch0-gate")
    p_branch0.add_argument("target")
    p_branch0.add_argument("--percolate-root", required=True)
    p_branch0.add_argument("--claude-klabauter-root", required=False)
    p_branch0.set_defaults(func=_cmd_branch0_gate)

    p_scan = sub.add_parser("scan-secrets")
    p_scan.add_argument("--files", required=True)
    p_scan.add_argument("--identity-file", required=False)
    p_scan.add_argument("--peer-repos-file", required=False)
    p_scan.add_argument("--target", required=False)
    p_scan.add_argument(
        "--percolate-root",
        required=False,
        help=(
            "Resolves <root>/setup/percolate-hooks/percolate-store.yaml so the peer-repo "
            "MEDIUM leg can be split by declared transform coverage (§ AC1/AC2). Omitted: "
            "the panel renders exactly as before this coverage split existed."
        ),
    )
    p_scan.set_defaults(func=_cmd_scan_secrets)

    p_drift = sub.add_parser("inverse-drift")
    p_drift.add_argument("target")
    p_drift.add_argument("--percolate-root", required=True)
    p_drift.add_argument("--dest", required=True)
    p_drift.add_argument("--files", required=True)
    p_drift.add_argument("--source-dir", required=False)
    p_drift.add_argument(
        "--json",
        action="store_true",
        help=(
            "Emit a machine-readable verdict (anchor_mode/anchor_reliable, "
            "CRLF-only dismissals, surviving candidates) instead of prose."
        ),
    )
    p_drift.set_defaults(func=_cmd_inverse_drift)

    p_resolve_root = sub.add_parser("resolve-root")
    p_resolve_root.add_argument("--explain", action="store_true")
    p_resolve_root.set_defaults(func=_cmd_resolve_root)

    p_list = sub.add_parser("list-targets")
    p_list.add_argument("--percolate-root", required=True)
    p_list.add_argument("--target", required=False)
    p_list.set_defaults(func=_cmd_list_targets)

    p_coverage = sub.add_parser("coverage-drift")
    p_coverage.add_argument("source_dir")
    p_coverage.add_argument("--limit", type=int, default=20)
    p_coverage.set_defaults(func=_cmd_coverage_drift)

    p_mtime = sub.add_parser("ignore-mtime")
    p_mtime.add_argument("source_dir")
    p_mtime.set_defaults(func=_cmd_ignore_mtime)

    p_ready = sub.add_parser("publish-readiness")
    p_ready.add_argument("mirror", nargs="?", default=None)
    p_ready.add_argument("--percolate-root", default=None)
    p_ready.add_argument(
        "--no-fetch",
        action="store_true",
        help="Skip the origin fetch; report ahead/behind against refs already local.",
    )
    p_ready.set_defaults(func=_cmd_publish_readiness)

    p_crlf = sub.add_parser("crlf-diff")
    p_crlf.add_argument("dest_file")
    p_crlf.add_argument("source_file")
    p_crlf.set_defaults(func=_cmd_crlf_diff)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
