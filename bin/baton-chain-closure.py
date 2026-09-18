#!/usr/bin/env python3
"""baton-chain-closure -- detect that an entire baton-chain (workstream), not a single baton, has
closed, and emit a PM-facing closure signal conforming to `group-em-output-contract.md`.

Ported from DoE-claude `coordinator/bin/baton-chain-closure.py` (W2-C6,
`docs/plans/2026-09-18-doe-holds-no-scripts.md`) -- mechanical move, no behavioural change.
`_repo_root()` was already "engine" class (§ Path resolution): `Path(__file__).resolve().
parents[2]` names the repo root from this module's own tree. The docstring's citation of
`coordinator/schemas/handoff.schema.json` below is updated to name this engine's own vendored copy
(`coordinator_core/frontmatter/schemas/handoff.schema.json`, byte-identical to DoE's today) -- this
module never actually loads that schema at runtime (declared lineage on the handoff artifact is
read directly, field by field), so the citation is documentation only and needed no code change.

WHY THIS EXISTS. The PM's stated use: *"I would then want to be made aware of a baton-chain
(workstream) having entirely closed such that I can load up a new one."* A single baton shipping
is not that fact; the fact is only true when every component of the chain the baton belongs to has
resolved.

CHAIN IDENTITY -- EMPIRICALLY VERIFIED, NOT ASSUMED (gem-05 spec step 1). Measured 2026-08-29 over
all 783 handoffs in `state/handoffs/` + `archive/handoffs/**`:

  - `deliverable_id` genuinely groups multi-baton chains -- 115 ids span >1 baton, the largest
    spanning 13 (`dlv-warm-route-the-bash-guard-hook-doe-half-72e490`, the bash-guard/rehome
    chain, a linear `predecessor` walk end to end).
  - BUT `deliverable_id` is NOT sufficient alone. Of 248 `predecessor` links where both ends carry
    a populated `deliverable_id`, 174 agree and 74 (30%) cross a deliverable boundary. A material
    subset of those crossings are the SAME deliverable re-minted under a new hash (e.g.
    `dlv-narrow-the-write-confinement-bump-publis-a43510` -> `dlv-narrow-the-write-confinement-
    bump-a-publ-276e8d`), which silently splits one real chain into two re-mints, each of which
    can then read "closed" on its own -- the exact failure this module exists to refuse.

  Therefore: a chain is the TRANSITIVE CLOSURE of the union of two explicit relations -- (a)
  shared `deliverable_id`, and (b) the `predecessor` spine. Both are declared lineage on the
  artifact itself (`coordinator_core/frontmatter/schemas/handoff.schema.json`); no third, INFERRED
  relation (title similarity, slug prefix, date proximity, branch) is ever added.

CLOSURE, PER COMPONENT (gem-02's landed taxonomy, DR-183). A chain is closed only when EVERY
component baton is resolved:
  - `deployment_state` in {shipped, continued, closed} -- `awaiting_gate`/`ready_to_fire`/
    `in_flight` are not terminal, and `landed` is EXPLICITLY not terminal (never encountered as a
    `deployment_state` value; named defensively per gem-05's Anti-scope).
  - A `continued` component's `continued_into` successor MUST resolve to another baton already IN
    the same chain -- a successor outside the chain is a hole, not a closure.
  - Every governing plan's spine row (reached via `origin_plan_id`/`plan_ids`) sits at one of
    DR-183's four resolutions (`coded`, `wont_do`, `backlogged`, `spun_off`) -- `open` is never a
    resolution. A baton naming no plan contributes no spine rows; that is not a failure.
  - STRANDED IS A NON-TERMINAL CONDITION. A NON-terminal component that is `status: claimed`
    reports whether its claimant is live (in progress) or dead (stranded) -- both block closure,
    and the reason text says which, because "someone is working it" and "nobody is" are different
    facts for the PM. Liveness joins against the harness session registry; the idiom is copied
    from `group-em-nomination.py` -- that module's filename is hyphenated and so not import-safe,
    hence a copy, not an import.
    A TERMINAL component's claim state is IRRELEVANT and is never reported. A baton that shipped
    or was continued and was left `status: claimed` by a session that has since ended is finished,
    not stranded -- that is the ordinary resting state of every superseded link in the corpus
    (13 of the 14 members of the bash-guard/rehome chain sit exactly there). Probing claim state
    on terminal components made every chain older than its sessions permanently un-closable.

Zero subprocess, PyYAML for frontmatter and plan-tasks parsing; no shell.

NEGATIVE-SPEC: this module never signals partial closure as closure -- a chain one baton short is
open, full stop. It never infers a chain from adjacency. It never treats a single baton shipping
as a chain closing (`signal` skips single-baton components). It carries no memory of what it has
signalled before -- every verdict is re-derived from disk on every call. `signal` takes ONE baton
and emits at most ONE decision; corpus-wide enumeration lives on `chains`, which is diagnostic and
never reaches the PM's window.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import sys
from pathlib import Path
from typing import NamedTuple, Optional

_TERMINAL_DEPLOYMENT = {"shipped", "continued", "closed"}
_RESOLVED_DISPOSITIONS = {"coded", "wont_do", "backlogged", "spun_off"}
_COMMENT_PREFIX = re.compile(r"\A\s*<!--.*?-->", re.DOTALL)
_SPINE_FENCE = re.compile(r"```ya?ml\s+plan-tasks\s*\n(.*?)\n```", re.DOTALL)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


class Baton(NamedTuple):
    path: Path
    handoff_id: Optional[str]
    deliverable_id: Optional[str]
    predecessor: Optional[str]
    predecessor_id: Optional[str]
    deployment_state: Optional[str]
    status: Optional[str]
    claimed_by: Optional[str]
    continued_into: Optional[str]
    plan_ids: list
    blocks: list
    stub_id: Optional[str]
    summary: Optional[str]
    title: str
    roadmap_id: Optional[str] = None


def _split_frontmatter(text: str):
    """(frontmatter dict, body) or (None, text) when no valid `---`-delimited YAML block leads.

    A leading HTML comment is skipped before the fence is sought: the seeded install-leg handoff
    templates carry a provenance comment above their frontmatter, and treating those as unreadable
    made every chain in the corpus unverifiable at once.
    """
    import yaml

    text = _COMMENT_PREFIX.sub("", text, count=1).lstrip()
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    try:
        data = yaml.load(parts[1], Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
    except yaml.YAMLError:
        return None, text
    if not isinstance(data, dict):
        return None, text
    return data, parts[2]


def _load_baton(path: Path) -> Optional[Baton]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    fm, _body = _split_frontmatter(text)
    if fm is None:
        return None
    predecessor = fm.get("predecessor")
    predecessor = None if predecessor in (None, "none") else str(predecessor)
    plan_ids = fm.get("plan_ids") or []
    if not plan_ids and fm.get("origin_plan_id"):
        plan_ids = [fm["origin_plan_id"]]
    return Baton(
        path=path,
        handoff_id=fm.get("handoff_id"),
        deliverable_id=fm.get("deliverable_id"),
        predecessor=predecessor,
        predecessor_id=fm.get("predecessor_id"),
        deployment_state=fm.get("deployment_state"),
        status=fm.get("status"),
        claimed_by=fm.get("claimed_by"),
        continued_into=fm.get("continued_into"),
        plan_ids=list(plan_ids),
        blocks=list(fm.get("blocks") or []),
        roadmap_id=fm.get("roadmap_id"),
        stub_id=fm.get("stub_id"),
        summary=fm.get("summary"),
        title=str(fm.get("title") or path.stem),
    )


def _iter_handoff_paths(repo_root: Path) -> list:
    live = repo_root / "state" / "handoffs"
    archived = repo_root / "archive" / "handoffs"
    paths = []
    if live.is_dir():
        paths.extend(sorted(live.glob("*.md")))
    if archived.is_dir():
        paths.extend(sorted(archived.glob("**/*.md")))
    return paths


def load_all_batons(repo_root: Path, unreadable: Optional[list] = None) -> list:
    """Every parseable baton on disk; unparseable paths append to `unreadable` when supplied.

    NEGATIVE-SPEC: a handoff that fails to parse is never silently dropped. A dropped file may be
    a chain member, and its absence removes the edge that would have held its chain open -- so the
    rest would read CLOSED without it. Callers that decide closure MUST pass `unreadable` and
    refuse to declare closed while it is non-empty.
    """
    out = []
    for p in _iter_handoff_paths(repo_root):
        b = _load_baton(p)
        if b is not None:
            out.append(b)
        elif unreadable is not None:
            unreadable.append(p)
    return out


def _index_batons(batons: list):
    """(handoff_id -> baton, basename -> baton). A basename claimed by more than one path maps to
    None: an archived file and a later live file can share a name, and resolving to whichever
    loaded first would merge two unrelated chains or attach the wrong predecessor."""
    by_id = {b.handoff_id: b for b in batons if b.handoff_id}
    by_name = {}
    for b in batons:
        name = b.path.name
        by_name[name] = None if name in by_name else b
    return by_id, by_name


def _resolve_predecessor(b: Baton, by_id: dict, by_name: dict) -> Optional[Baton]:
    if b.predecessor_id and b.predecessor_id in by_id:
        return by_id[b.predecessor_id]
    if b.predecessor:
        name = Path(b.predecessor.replace("\\", "/")).name
        return by_name.get(name)
    return None


class _UnionFind:
    def __init__(self, items):
        self.parent = {i: i for i in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def build_chains(batons: list) -> dict:
    """Connected components over the union of two DECLARED relations only -- shared
    `deliverable_id` and the resolved `predecessor` spine. See module docstring § CHAIN IDENTITY.
    """
    by_id, by_name = _index_batons(batons)
    by_key = {str(b.path): b for b in batons}
    keys = list(by_key.keys())
    uf = _UnionFind(keys)

    dlv_groups: dict = {}
    for b in batons:
        if b.deliverable_id:
            dlv_groups.setdefault(b.deliverable_id, []).append(str(b.path))
    for group in dlv_groups.values():
        for k in group[1:]:
            uf.union(group[0], k)

    for b in batons:
        pred = _resolve_predecessor(b, by_id, by_name)
        if pred is not None:
            uf.union(str(b.path), str(pred.path))

    chains: dict = {}
    for k in keys:
        root = uf.find(k)
        chains.setdefault(root, []).append(by_key[k])
    return chains


# --- Liveness: copied idiom, not imported (group-em-nomination.py's filename is not
# import-safe -- hyphenated -- per that module's own header comment). ---


def _session_registry_dir() -> Path:
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    root = Path(override) if override else Path.home() / ".claude"
    return root / "sessions"


def _pid_alive_windows(pid: int) -> bool:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return code.value == STILL_ACTIVE
        return True
    finally:
        kernel32.CloseHandle(handle)


def _pid_alive_posix(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    arm = _pid_alive_windows if os.name == "nt" else _pid_alive_posix
    return arm(pid)


def _session_is_live(session_id: str, registry_dir: Optional[Path] = None) -> bool:
    directory = registry_dir or _session_registry_dir()
    try:
        entries = sorted(directory.glob("*.json"))
    except OSError:
        return False
    for p in entries:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        sid = data.get("sessionId") or data.get("session_id")
        if sid != session_id:
            continue
        try:
            pid = int(data.get("pid") or 0)
        except (TypeError, ValueError):
            pid = 0
        return _pid_alive(pid)
    return False


# --- Governing-plan spine resolution ---


def build_plan_index(repo_root: Path) -> dict:
    """`plan_id` -> plan file path, over every `docs/plans/*.md`."""
    index: dict = {}
    plans_dir = repo_root / "docs" / "plans"
    if not plans_dir.is_dir():
        return index
    for p in sorted(plans_dir.glob("*.md")):
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm, _body = _split_frontmatter(text)
        if fm and fm.get("plan_id"):
            index[str(fm["plan_id"])] = p
    return index


def _plan_spine_dispositions(path: Path) -> list:
    import yaml

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    out = []
    for match in _SPINE_FENCE.finditer(text):
        try:
            rows = yaml.load(match.group(1), Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
        except yaml.YAMLError:
            out.append(("?", "unparseable-fence"))
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                out.append((str(row.get("id", "?")), str(row.get("disposition", "open"))))
    return out


class ClosureResult(NamedTuple):
    closed: bool
    reasons: list


def evaluate_closure(
    chain: list,
    plan_index: dict,
    registry_dir: Optional[Path] = None,
) -> ClosureResult:
    reasons: list = []
    chain_by_id = {b.handoff_id: b for b in chain if b.handoff_id}

    for b in chain:
        if b.deployment_state not in _TERMINAL_DEPLOYMENT:
            reasons.append(
                f"{b.path.name}: deployment_state={b.deployment_state!r} not terminal"
            )
            if b.status == "claimed" and b.claimed_by:
                if _session_is_live(b.claimed_by, registry_dir):
                    reasons.append(
                        f"{b.path.name}: claimed by {b.claimed_by} — session live (in progress)"
                    )
                else:
                    reasons.append(
                        f"{b.path.name}: claimed by {b.claimed_by} — session not live (stranded)"
                    )
        elif b.deployment_state == "continued":
            target = b.continued_into
            resolved = chain_by_id.get(target) if target else None
            if resolved is None and target:
                target_name = Path(str(target).replace("\\", "/")).name
                resolved = next(
                    (c for c in chain if c.path.name == target_name), None
                )
            if resolved is None:
                reasons.append(
                    f"{b.path.name}: continued_into successor {target!r} not in chain (hole)"
                )

    plan_ids = sorted({pid for b in chain for pid in b.plan_ids if pid})
    for pid in plan_ids:
        plan_path = plan_index.get(pid)
        if plan_path is None:
            reasons.append(f"plan {pid}: not found on disk")
            continue
        for row_id, disposition in _plan_spine_dispositions(plan_path):
            if disposition not in _RESOLVED_DISPOSITIONS:
                reasons.append(
                    f"plan {plan_path.name} row {row_id}: disposition={disposition!r} "
                    "is not a DR-183 resolution"
                )

    return ClosureResult(closed=not reasons, reasons=reasons)


def chain_name(chain: list) -> str:
    dlv_ids = sorted({b.deliverable_id for b in chain if b.deliverable_id})
    if dlv_ids:
        return dlv_ids[0]
    return sorted(chain, key=lambda b: b.path.name)[0].path.name


def _chain_tip(chain: list) -> Optional[Baton]:
    """The chain's head: the one member no other member names as its predecessor.

    None when the spine forks or the chain is a bare `deliverable_id` group with no spine at all --
    callers fall back rather than pick arbitrarily.
    """
    by_id, by_name = _index_batons(chain)
    referenced = set()
    for b in chain:
        pred = _resolve_predecessor(b, by_id, by_name)
        if pred is not None:
            referenced.add(str(pred.path))
    tips = {str(b.path): b for b in chain if str(b.path) not in referenced}
    return next(iter(tips.values())) if len(tips) == 1 else None


def _one_sentence(text) -> str:
    """The first sentence only, terminator stripped.

    NEGATIVE-SPEC: never returns a multi-sentence body. A baton `summary` routinely carries
    forward-looking prose after its first sentence, and the gem-04 contract excludes that from a
    PM-facing emission -- filtered here at source, not trimmed by the reader.
    """
    s = str(text).strip()
    cut = len(s)
    for sep in (". ", "; ", "! ", "? "):
        i = s.find(sep)
        if i != -1:
            cut = min(cut, i + 1)
    return s[:cut].strip().rstrip(".;!?").strip()


def emit_signal(chain: list) -> str:
    """The gem-04 group-em-output-contract signal: three fields only, filtered at source.

    NEGATIVE-SPEC: never includes rationale, working status, commit hashes, metrics, or an FYI —
    those are the contract's excluded classes (`coordinator/snippets/group-em-output-contract.md`).
    The outcome is stated ONCE — the tip's, or at most two summaries when the spine forks — never
    every member's `summary` glued end to end, which reads as the wall the contract forbids.
    """
    name = chain_name(chain)
    roadmap_ids = sorted({b.roadmap_id for b in chain if b.roadmap_id})
    own = {(b.roadmap_id, b.stub_id) for b in chain if b.stub_id}
    unblocks = sorted(
        {
            (b.roadmap_id, s)
            for b in chain
            for s in b.blocks
        }
        - own
    )

    tip = _chain_tip(chain)
    if tip is not None and tip.summary:
        outcome = _one_sentence(tip.summary)
    else:
        summaries = [_one_sentence(s) for s in sorted({b.summary for b in chain if b.summary})]
        outcome = "; ".join(summaries[:2])

    content = f"{name} delivered: {outcome}." if outcome else f"{name} delivered; see its batons."
    if unblocks:
        qualified = ", ".join(
            f"{rid}/{s}" if rid else s for rid, s in unblocks
        )
        content += f" Unblocks: {qualified}."

    scope = f" (roadmap {', '.join(roadmap_ids)})" if roadmap_ids else ""

    return "\n".join(
        [
            f"Decision point: chain {name}{scope} has entirely closed; which workstream "
            "loads next is unresolved without them.",
            "Action required: choose.",
            f"Content: {content}",
        ]
    )


def _stranded_reasons(result: ClosureResult) -> list:
    """The subset of a chain's closure reasons that report a dead (stranded) claimant.

    A live-claimant reason ("session live (in progress)") is deliberately excluded: the PM's
    ask is who to reassign, not who is already working it. Terminal-status chains never reach
    `evaluate_closure`'s claim-state branch at all (module docstring § CLOSURE, PER COMPONENT),
    so they contribute no reasons here and are silently absent from the projection — that is
    correct, not an omission.
    """
    return [r for r in result.reasons if r.endswith("(stranded)")]


def _cmd_chains(repo_root: Path, stranded_only: bool = False) -> int:
    """Enumerate every chain with its closure verdict, or — with `stranded_only` — a bounded
    STRANDED-only projection over the same walk.

    NEGATIVE-SPEC: `stranded_only` adds no detection logic and re-runs no per-baton `check` — it
    reuses `load_all_batons`/`build_chains`/`evaluate_closure` verbatim and filters their output
    at presentation time only.
    """
    unreadable = []
    batons = load_all_batons(repo_root, unreadable)
    chains = build_chains(batons)
    plan_index = build_plan_index(repo_root)
    ordered = sorted(chains.values(), key=chain_name)

    if stranded_only:
        for members in ordered:
            result = evaluate_closure(members, plan_index)
            for reason in _stranded_reasons(result):
                print(f"{chain_name(members)}: {reason}")
        for u in unreadable:
            print(f"! {u}: unreadable handoff — the projection above is unverifiable")
        return 1 if unreadable else 0

    for members in ordered:
        result = evaluate_closure(members, plan_index)
        verdict = "CLOSED" if result.closed else "OPEN"
        print(f"{chain_name(members)} ({len(members)} baton(s)): {verdict}")
        for m in sorted(members, key=lambda b: b.path.name):
            print(f"  - {m.path}")
        for reason in result.reasons:
            print(f"  ! {reason}")
    for u in unreadable:
        print(f"! {u}: unreadable handoff — every verdict above is unverifiable")
    return 1 if unreadable else 0


def _chain_containing(repo_root: Path, handoff_path: str):
    """(chain members or None, unreadable paths). The second element is why closure may not be
    declared: an unparseable handoff is a chain member this walk could not see."""
    target = Path(handoff_path).resolve()
    unreadable = []
    for members in build_chains(load_all_batons(repo_root, unreadable)).values():
        if any(m.path.resolve() == target for m in members):
            return members, unreadable
    return None, unreadable


def _cmd_check(repo_root: Path, handoff_path: str) -> int:
    members, unreadable = _chain_containing(repo_root, handoff_path)
    if members is None:
        print(f"no chain found containing {handoff_path}", file=sys.stderr)
        return 2
    result = evaluate_closure(members, build_plan_index(repo_root))
    name = chain_name(members)
    if result.closed and not unreadable:
        print(f"{name}: CLOSED")
        return 0
    print(f"{name}: OPEN")
    for reason in result.reasons:
        print(f"  ! {reason}")
    for p in unreadable:
        print(f"  ! {p}: unreadable handoff — closure unverifiable")
    return 1


def _cmd_signal(repo_root: Path, handoff_path: str) -> int:
    """One baton in, at most one decision out.

    NEGATIVE-SPEC: never enumerates the corpus. Emitting every historically-closed chain at once
    is the alarm-fatigue failure `group-em-output-contract.md` § Filter at source exists to
    refuse — its falsifier is a PM reading ONE screen. Corpus-wide enumeration stays on `chains`,
    which is diagnostic and never reaches the PM's window. Silence is the common case and is not
    an error. No ledger of already-signalled chains is kept: closure is re-derived from disk on
    every call, so a successor session reaches the same verdict without a message.
    """
    members, unreadable = _chain_containing(repo_root, handoff_path)
    if members is None:
        print(f"no chain found containing {handoff_path}", file=sys.stderr)
        return 2
    if len(members) < 2:
        return 0  # a single baton shipping is never "a chain closing" (Anti-scope).
    if unreadable:
        for p in unreadable:
            print(f"{p}: unreadable handoff — closure unverifiable", file=sys.stderr)
        return 0
    if evaluate_closure(members, build_plan_index(repo_root)).closed:
        print(emit_signal(members))
    return 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="baton-chain-closure",
        description="Detect that an entire baton-chain has closed, and emit the PM signal.",
    )
    parser.add_argument("--repo", help="repo root; default self-resolved from this file")
    sub = parser.add_subparsers(dest="verb", required=True)
    p_chains = sub.add_parser("chains", help="enumerate every chain with its closure verdict")
    p_chains.add_argument(
        "--stranded-only",
        action="store_true",
        help="bounded projection: only STRANDED (dead-claimant) reasons, one per line",
    )
    p_check = sub.add_parser("check", help="the chain containing one handoff: closed or not")
    p_check.add_argument("handoff_path")
    p_signal = sub.add_parser(
        "signal", help="emit the PM-facing signal if THIS baton's chain has entirely closed"
    )
    p_signal.add_argument("handoff_path")

    args = parser.parse_args(argv)
    repo_root = Path(args.repo).resolve() if args.repo else _repo_root()

    if args.verb == "chains":
        return _cmd_chains(repo_root, stranded_only=args.stranded_only)
    if args.verb == "check":
        return _cmd_check(repo_root, args.handoff_path)
    if args.verb == "signal":
        return _cmd_signal(repo_root, args.handoff_path)
    raise AssertionError(f"unhandled verb {args.verb!r}")  # argparse guarantees one of the above


if __name__ == "__main__":
    sys.exit(main())
