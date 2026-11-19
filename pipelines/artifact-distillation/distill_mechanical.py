"""Deterministic driver for the mechanical /distill phases; no agent is ever spawned.

  prepare  --repo-root R --input-file F [--nuggets N.json] [--verdicts V.json]
           [--run-id ID] [--out-dir D] [--store PATH] [--pointer-index INDEX.jsonl]
      Loads the distill.scope manifest and its batch / slug shards, validates the declared
      counts, lifts Work Completed / Architectural Decisions / Systems Affected bullets of every
      batch file into tagged nuggets, runs the Phase 2.5 judgment precheck (prepared.judgmentPrecheck:
      sidecars_seen, distinct_eligible_plans, existing_judgment_entries, dispatch), groups nuggets into clusters by topic key, hashes each cluster's sources, and
      runs the candidates batch. Writes <out-dir>/prepared.json (the Workflow's inline input).
      Without --nuggets the load half still runs and clusters stay empty. Also writes
      <out-dir>/synth-batch-NN.json (per topic: curated nuggets, page heading outline and gotcha
      one-liners, packed up to SYNTH_BATCH_BYTES, at most MAX_SYNTH_CALLS of them) and <out-dir>/topics/<slug>.json
      (one topic's context) for single-turn schema synth calls (SYNTH_SCHEMA). prepared.synth.payloads holds
      the batches inline; topics past the last batch are prepared.synth.deferred_topics.

  finalize --repo-root R --manifest M.json [--manifest M2.json ...] [--run-id ID] [--out-dir D] [--store PATH]
           [--dry-run] [--no-archive] [--no-scratch] [--invoke-bin PATH] [--doc-new-bin PATH]
      manifest: {"run_id", "files": [{"staged", "target", "topic_key", "homed"?}],
      "hashes": {topic_key: sha256}, "deletions": [{"artifact_path", "citation_target"}],
      "archive": [{"src", "dst"}], "synth_results"?: [synth JSON objects or paths], "prepared"?: path}.
      A sharded prepare takes one --manifest per shard (each carries its `shard` marker); they merge into
      <out-dir>/merged-manifest.json against <out-dir>/shards.json and splice against the shard files.
      Runs, in order: synth splice into staged pages (cite-checked) and decision_records minted through
      coordinator-doc-new (not with --dry-run; a record whose title or slug matches prepared.drIndex is
      reported under dr_exists, never minted), promote collision check, promote, the leg-2 inputs
      (<out-dir>/promoted.json and splice-report.json, named under report.leg2),
      verify-citations, archive moves, the fleet.scratch_hygiene scratch drop, and
      DIRECTORY_GUIDE index regen. Writes <out-dir>/finalize-report.json.

Promote and verify-citations run the claude-klabauter-authored coordinator/bin scripts by subprocess.
Exit 0 ok, 1 a phase halted (report names it), 2 unusable input. Every report carries
agent_spawns: 0 and per-phase wall seconds.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import types
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

BIN_DIR = Path(__file__).resolve().parents[2] / "bin"
PROMOTE_SCRIPT = "distill-promote-staged.py"
CANDIDATES_SCRIPT = "distill-candidates-batch.py"
DEFAULT_STORE = "state/distillation-source-hashes.json"
SCRATCH_ROOT = "state/scratch/artifact-distillation"
INVOKE_NAME = "coordinator-invoke"
# The Workflow runner's launch cap; the same figure as dispatch_emit/emit.py _WORKFLOW_SCRIPT_BYTE_CAP.
# Kept local: this pipeline never imports the engine.
LAUNCH_CAP_BYTES = 524288
LAUNCH_MARGIN_BYTES = 32768  # headroom a launch keeps under the cap for launch_args and growth
HARVEST_SCRIPT = Path(__file__).resolve().with_name("distill-harvest.workflow.js")
_RUN_ID_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]*$")
_GUIDE_ROW = re.compile(r"^\|\s*\[([^\]\n]*)\]\(([^)\n]+\.md)\)\s*\|")
_GUIDE_SEP = re.compile(r"^\|\s*:?-{3,}:?\s*\|")
_H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


class DriverError(Exception):
    """A phase cannot proceed; `code` is the halt name carried into the report."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def slugify(text: str) -> str:
    """Same canonical slug as the Workflow's slugifyTopic."""
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d-%Hh%M")


def check_run_id(run_id: str) -> str:
    if not _RUN_ID_RE.match(run_id or ""):
        raise DriverError("bad-run-id", f"run id {run_id!r} must be a plain token")
    return run_id


def inside(repo: Path, rel: str) -> Path:
    """Resolve a repo-relative path, refusing absolute paths and parent escapes."""
    norm = str(rel).replace("\\", "/")
    parts = norm.split("/")
    if not norm or norm.startswith("/") or re.match(r"^[A-Za-z]:", norm) or ".." in parts:
        raise DriverError("path-escapes-repo", f"{rel!r} is not a repo-relative path")
    return repo / norm


def read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DriverError("unusable-input", f"{path}: {exc}") from exc


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_cmd(argv: List[str], cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


# --------------------------------------------------------------------------- load

def load_input(manifest_path: Path) -> dict:
    """Merge a distill.scope manifest with its shards, enforcing the declared counts."""
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("batchFiles"), list) \
            or not isinstance(manifest.get("slugShardFiles"), list):
        raise DriverError("not-a-manifest", f"{manifest_path} needs batchFiles and slugShardFiles")
    base = manifest_path.parent
    batches: List[dict] = []
    for rel in manifest["batchFiles"]:
        b = read_json(inside(base, rel))
        files = b.get("files") if isinstance(b, dict) else None
        if not isinstance(files, list) or b.get("file_count") != len(files):
            raise DriverError("input-count-mismatch", f"batch file {rel!r} file_count differs from its files")
        batches.append({k: v for k, v in b.items() if k != "file_count"})
    wiki_slugs: Dict[str, str] = {}
    for rel in manifest["slugShardFiles"]:
        s = read_json(inside(base, rel))
        entries = s.get("entries") if isinstance(s, dict) else None
        if not isinstance(entries, dict) or s.get("slug_count") != len(entries):
            raise DriverError("wiki-slugs-dropped", f"slug shard {rel!r} slug_count differs from its entries")
        wiki_slugs.update(entries)
    if not batches:
        raise DriverError("empty-input-batches", "input has empty or missing batches")
    total = sum(len(b["files"]) for b in batches)
    if manifest.get("batch_count") is not None and manifest["batch_count"] != len(batches):
        raise DriverError("input-count-mismatch", f"batch_count {manifest['batch_count']} != {len(batches)} loaded")
    if manifest.get("total_file_count") is not None and manifest["total_file_count"] != total:
        raise DriverError("input-count-mismatch", f"total_file_count {manifest['total_file_count']} != {total} loaded")
    if manifest.get("wikiSlugCount") is not None and manifest["wikiSlugCount"] != len(wiki_slugs):
        raise DriverError("wiki-slugs-dropped", f"wikiSlugCount {manifest['wikiSlugCount']} != {len(wiki_slugs)} loaded")
    rest = {k: v for k, v in manifest.items() if k not in ("batchFiles", "slugShardFiles")}
    return {**rest, "batches": batches, "wikiSlugs": wiki_slugs,
            "batch_count": len(batches), "total_file_count": total, "wikiSlugCount": len(wiki_slugs)}


# --------------------------------------------------------------------------- clustering

def _verdict_map(verdicts: object) -> Optional[Dict[str, dict]]:
    """Accept the curate op's {verdicts: [...]}, a bare list, or a {tag: verdict} map."""
    if verdicts is None:
        return None
    if isinstance(verdicts, dict) and isinstance(verdicts.get("verdicts"), list):
        verdicts = verdicts["verdicts"]
    if isinstance(verdicts, list):
        out = {}
        for v in verdicts:
            if isinstance(v, dict) and v.get("tag") is not None:
                out[str(v["tag"])] = v
        return out
    if isinstance(verdicts, dict):
        return {str(k): (v if isinstance(v, dict) else {"verdict": v}) for k, v in verdicts.items()}
    raise DriverError("bad-verdicts", "verdicts must be a list or a tag map")


def _resolve_tag(tag: str, vmap: Optional[Dict[str, dict]]) -> Optional[str]:
    """Destination key for a tag, or None when curation dropped it. Unknown shapes stop the run."""
    if vmap is None:
        return tag
    v = vmap.get(tag)
    if v is None:
        raise DriverError("curated-tag-missing", f"tag {tag!r} has no curation verdict")
    kind = v.get("verdict")
    if kind == "keep":
        return v.get("canonical_slug") or tag
    if kind == "normalize":
        if not v.get("canonical_slug"):
            raise DriverError("curated-normalize-no-slug", f"tag {tag!r} normalizes without canonical_slug")
        return v["canonical_slug"]
    if kind == "merge":
        if not v.get("merge_target"):
            raise DriverError("curated-merge-no-target", f"tag {tag!r} merges without merge_target")
        return v["merge_target"]
    if kind == "drop":
        return None
    raise DriverError("curated-unknown-verdict", f"tag {tag!r} has verdict {kind!r}")


MERGE_JACCARD = 0.5
MERGE_MIN_SHARED = 2


def _variant_score(a: List[str], b: List[str]) -> float:
    """Similarity of two slug token lists; 0 means distinct topics.

    A token-prefix of at least MERGE_MIN_SHARED tokens (the shorter slug heads the longer)
    scores above 1; otherwise two slugs
    must share MERGE_MIN_SHARED tokens at Jaccard >= MERGE_JACCARD.
    """
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    jac = len(set(a) & set(b)) / len(set(a) | set(b))
    if len(short) >= MERGE_MIN_SHARED and long_[:len(short)] == short:
        return 1 + jac
    if len(set(a) & set(b)) >= MERGE_MIN_SHARED and jac >= MERGE_JACCARD:
        return jac
    return 0.0


def _merge_topic_variants(groups: Dict[str, dict], wiki_slugs: Dict[str, str]) -> Dict[str, List[str]]:
    """Anchor slug -> slugs it owns (itself included), so each topic has one owning wiki page.

    Homed slugs that resolve to one path collapse onto the lowest slug; distinct homed paths
    never join. Anchors are visited homed first, then by nugget count, shortest slug, slug; each
    remaining slug joins its best-scoring anchor or becomes one. Sorted input makes it order-free.
    """
    by_path: Dict[str, List[str]] = {}
    for slug in groups:
        if slug in wiki_slugs:
            by_path.setdefault(wiki_slugs[slug], []).append(slug)
    owned: Dict[str, List[str]] = {}
    absorbed = set()
    for slugs in by_path.values():
        head = min(slugs)
        owned[head] = sorted(slugs)
        absorbed.update(s for s in slugs if s != head)

    def weight(s: str) -> int:
        return sum(len(groups[m]["nuggets"]) for m in owned.get(s, [s]))

    rest = sorted((s for s in groups if s not in absorbed and s not in owned),
                  key=lambda s: (-weight(s), len(s), s))
    anchors = sorted(owned)
    for slug in rest:
        toks = slug.split("-")
        best, best_score = None, 0.0
        for a in anchors:
            score = _variant_score(toks, a.split("-"))
            if score > best_score:
                best, best_score = a, score
        if best is None:
            owned[slug] = [slug]
            anchors.append(slug)
        else:
            owned[best].append(slug)
    return {s: sorted(owned[s]) for s in sorted(owned)}


def _home_variants(groups: Dict[str, dict], wiki_slugs: Dict[str, str]) -> Dict[str, List[str]]:
    """Fold each unhomed slug that is a variant of an existing wiki page's slug into that page's group.

    A page's slug need not itself be a nugget tag: variants of it still belong to that page, not
    to a new one. Same _variant_score thresholds as the topic merge; ties go to the lowest page
    slug. Mutates groups; returns page slug -> the tag slugs folded into it.
    """
    index: Dict[str, List[str]] = {}
    for w in sorted(wiki_slugs):
        for tok in set(w.split("-")):
            index.setdefault(tok, []).append(w)
    folded: Dict[str, List[str]] = {}
    for slug in sorted(s for s in groups if s not in wiki_slugs):
        toks = slug.split("-")
        best, best_score = None, 0.0
        for w in sorted({w for t in set(toks) for w in index.get(t, ())}):
            score = _variant_score(toks, w.split("-"))
            if score > best_score:
                best, best_score = w, score
        if best is None:
            continue
        src = groups.pop(slug)
        groups.setdefault(best, {"topicKey": best, "nuggets": []})["nuggets"].extend(src["nuggets"])
        folded.setdefault(best, []).append(slug)
    return folded


NON_CONTENT_TAG_SOURCES = frozenset({"path", "leading", "file-stem", "fallback"})
UNCATEGORIZED = "uncategorized"


def _non_content_tag(nugget: dict, slug: str) -> bool:
    """True when the nugget's tag came from a path, leading words, a file stem or the fallback, not its content.

    A nugget with no tag_source carries a scan agent's own tag and counts as content-derived.
    """
    return slug == UNCATEGORIZED or nugget.get("tag_source") in NON_CONTENT_TAG_SOURCES


def _per_nugget_cluster(nugget: dict, primary: str, taken: set) -> dict:
    """A one-nugget topic keyed by the nugget's id; its page is minted only from synth's page_title.

    A DECISION nugget's key is `decision-<id>`, not `nugget-<id>`: a `nugget-` key is judge-only and
    cannot mint the decision record the nugget owes.
    """
    slug = base = slugify(f"{'decision' if nugget.get('type') == 'DECISION' else 'nugget'}-{nugget.get('id')}")
    k = 1
    while slug in taken:
        k += 1
        slug = f"{base}-{k}"
    taken.add(slug)
    return {"topicKey": slug, "slug": slug, "homed": False, "per_nugget": True,
            "wikiPath": f"{primary}/{slug}.md", "nuggets": [nugget]}


def _resolve_content_homes(groups: Dict[str, dict], wiki_slugs: Dict[str, str]) -> None:
    """Move each unhomed group whose nuggets mostly name one existing wiki page into that page's group.

    A nugget names a page when _wiki_tag finds its slug in the content; a strict majority of the
    group's nuggets must name the same page path (the lowest slug of that path receives the group).
    Homes come only from wiki_slugs. Mutates groups.
    """
    for slug in sorted(s for s in groups if s not in wiki_slugs):
        ns = groups[slug]["nuggets"]
        votes: Dict[str, List[str]] = {}
        for n in ns:
            named = _wiki_tag(str(n.get("content") or ""), wiki_slugs)
            if named:
                votes.setdefault(wiki_slugs[named], []).append(named)
        if not votes:
            continue
        _, named = max(sorted(votes.items()), key=lambda kv: len(kv[1]))
        if len(named) * 2 <= len(ns):
            continue
        groups.pop(slug)
        home = min(named)
        groups.setdefault(home, {"topicKey": home, "nuggets": []})["nuggets"].extend(ns)


def _detach_singletons(groups: Dict[str, dict], wiki_slugs: Dict[str, str], owned: Dict[str, List[str]]) -> List[dict]:
    """Remove each unhomed topic left with one nugget after the variant merge; returns those nuggets.

    `owned` is _merge_topic_variants' anchor -> members map. A one-nugget topic is a guess, not a
    topic, so it becomes a per-nugget topic rather than a page named after its tag. Mutates groups and owned.
    """
    loose: List[dict] = []
    for anchor in sorted(owned):
        if len(owned[anchor]) != 1 or anchor in wiki_slugs or len(groups[anchor]["nuggets"]) != 1:
            continue
        loose.extend(groups.pop(anchor)["nuggets"])
        owned.pop(anchor)
    return loose


def cluster_nuggets(nuggets: List[dict], wiki_slugs: Dict[str, str], wiki_dirs: List[str],
                    verdicts: object = None) -> Tuple[List[dict], List[dict]]:
    """Group nuggets by topic key into clusters; returns (clusters, dropped nuggets).

    Pure and order-independent: nuggets sort by (source, id), clusters by slug. Tags that
    curation normalizes to one slug share a group. A nugget whose tag is not content-derived
    (tag_source path, leading, file-stem or fallback, or the literal "uncategorized") homes first
    by the wiki page its own content names (_wiki_tag), else on its tag only when that tag is
    exactly a wiki slug; otherwise it is loose. A group of content-tagged nuggets that mostly
    name one wiki page joins that page (_resolve_content_homes). Tag variants across files merge
    into one cluster (_merge_topic_variants); a merged cluster lists its absorbed slugs under
    "variants". Variants of a wiki page's slug fold into that page even when no nugget carries
    the page slug itself (_home_variants). A cluster whose slug resolves in wiki_slugs is homed
    (merges into that guide); every other tag-slug cluster is new at wiki_dirs[0]. Loose nuggets
    and every unhomed topic still holding one nugget after the variant merge become per-nugget
    clusters (per_nugget true, one nugget each, slug nugget-<id>), never a cluster named for a
    path, branch, DR id or source file. No two clusters share a wikiPath.
    Count conservation (in == clustered + dropped) is asserted.
    """
    vmap = _verdict_map(verdicts)
    groups: Dict[str, dict] = {}
    dropped: List[dict] = []
    loose: List[dict] = []
    for n in nuggets:
        raw = n.get("topicKey") or n.get("topic_key") or n.get("tag") or n.get("system_tag")
        if not raw:
            raise DriverError("nugget-no-topic", f"nugget {n.get('id')!r} carries no topicKey or tag")
        key = _resolve_tag(str(raw), vmap)
        if key is None:
            dropped.append(n)
            continue
        slug = slugify(key)
        if not slug:
            raise DriverError("nugget-bad-topic", f"topic {key!r} slugifies to nothing")
        if _non_content_tag(n, slug):
            named = _wiki_tag(str(n.get("content") or ""), wiki_slugs)
            if named:
                slug = key = named
            elif slug == UNCATEGORIZED or slug not in wiki_slugs:
                loose.append(n)
                continue
        g = groups.setdefault(slug, {"topicKey": key, "nuggets": []})
        g["topicKey"] = min(g["topicKey"], key)
        g["nuggets"].append(n)
    _resolve_content_homes(groups, wiki_slugs)
    folded = _home_variants(groups, wiki_slugs)
    owned = _merge_topic_variants(groups, wiki_slugs)
    loose += _detach_singletons(groups, wiki_slugs, owned)
    primary = wiki_dirs[0] if wiki_dirs else "docs/wiki"
    clusters = []
    for slug, members in owned.items():
        g = groups[slug]
        homed_path = wiki_slugs.get(slug)
        merged = [n for m in members for n in groups[m]["nuggets"]]
        members = members + [f for m in members for f in folded.get(m, [])]
        cluster = {
            "topicKey": g["topicKey"],
            "slug": slug,
            "homed": homed_path is not None,
            "wikiPath": homed_path or f"{primary}/{slug}.md",
            "nuggets": sorted(merged, key=lambda x: (str(x.get("source", "")), str(x.get("id", "")))),
        }
        if len(members) > 1:
            cluster["variants"] = sorted(m for m in members if m != slug)
        clusters.append(cluster)
    taken = {c["slug"] for c in clusters}
    clusters += [_per_nugget_cluster(n, primary, taken)
                 for n in sorted(loose, key=lambda x: (str(x.get("source", "")), str(x.get("id", ""))))]
    clusters.sort(key=lambda c: c["slug"])
    if sum(len(c["nuggets"]) for c in clusters) + len(dropped) != len(nuggets):
        raise DriverError("count-conservation", "clustered plus dropped nuggets differ from nuggets in")
    return clusters, dropped


# --------------------------------------------------------------------------- script phases

def script_json(script: str, argv_tail: List[str], repo: Path) -> Tuple[int, object, str]:
    proc = run_cmd([sys.executable, str(BIN_DIR / script), *argv_tail], repo)
    try:
        payload = json.loads(proc.stdout) if proc.stdout.strip() else None
    except ValueError:
        payload = None
    return proc.returncode, payload, proc.stderr.strip()[:300]


def source_hashes(clusters: List[dict], repo: Path, out_dir: Path, store: str) -> Dict[str, dict]:
    spec = [{"topic_key": c["topicKey"],
             "sources": sorted({n["source"] for n in c["nuggets"] if n.get("source")})} for c in clusters]
    if not spec:
        return {}
    spec_file = out_dir / "source-hash-spec.json"
    write_json(spec_file, spec)
    rc, payload, err = script_json(PROMOTE_SCRIPT, ["check", str(spec_file), "--store", store], repo)
    if rc != 0 or not isinstance(payload, dict):
        raise DriverError("source-hash-failed", f"exit {rc}: {err}")
    return payload


def candidates(clusters: List[dict], repo: Path, out_dir: Path) -> Tuple[List[dict], str]:
    """Candidate restatements per cluster; a missing engine CLI degrades to [] with a status."""
    entries = []
    for c in clusters:
        text_file = out_dir / f"candidates-{c['slug']}.txt"
        text_file.write_text("\n\n".join(n.get("content", "") for n in c["nuggets"] if n.get("content")),
                             encoding="utf-8")
        entries.append({"topic_key": c["topicKey"], "wiki_path": c["wikiPath"],
                        "text_file": text_file.relative_to(repo).as_posix()})
    if not entries:
        return [], "no-clusters"
    spec_file = out_dir / "candidates-spec.json"
    write_json(spec_file, entries)
    rc, payload, err = script_json(CANDIDATES_SCRIPT, [str(spec_file)], repo)
    if rc == 2 or not isinstance(payload, dict):
        return [], f"unavailable: {err or 'no output'}"
    out = []
    for key in sorted(payload):
        rec = payload[key]
        if isinstance(rec, dict) and rec.get("status") == "ok":
            out.append({"topic_key": key, "wiki_path": rec.get("wiki_path"),
                        "candidate_restatements": rec.get("candidate_restatements", [])})
    return out, "ok" if rc == 0 else "partial"


# --------------------------------------------------------------------------- section lift

LIFT_SECTIONS = (("work completed", "KNOWLEDGE"), ("architectural decisions", "DECISION"),
                 ("systems affected", "KNOWLEDGE"), ("design", "KNOWLEDGE"), ("decision", "DECISION"),
                 ("what i learned", "KNOWLEDGE"), ("lessons learned", "KNOWLEDGE"))
_SUBBULLET_SECTIONS = {"design", "decision", "what i learned", "lessons learned"}  # an indented bullet is its own nugget
_SPINE_TITLES = {"tasks", "task spine"}
_SPINE_FENCE = re.compile(r"\s*```+\s*ya?ml\s+plan-tasks\b")
_HISTORICAL_TITLES = ("problem", "background")
LIFT_CONTENT_BYTES = 16000  # a lifted nugget rides whole; only a body past this is cut, at a sentence end
LIFT_TAG_BYTES = 48
_EPHEMERAL_DIRS = {"scratch", "handoffs", "stand-downs", "inbox", "dispatch-reports", "run-reports"}
_TRIAGE_ONLY_DIRS = {"daily-summaries", "week-changelogs", "week-changelog"}
_RETIRED_STATUS = {"superseded", "retired", "abandoned", "rejected", "obsolete"}
_GENERIC_DIRS = {"coordinator", "pipelines", "docs", "doc", "state", "archive", "src", "scratch"}
_NOT_A_SYSTEM = {"and", "or", "vs", "the", "an"}
_DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})-?")
_PATH_REF = re.compile(r"(?<![\w/.:\-])\.?[A-Za-z_][\w.\-]*(?:/[\w.\-]+)+")
_PATH_LIKE = re.compile(r"(?<![\w/.:\-])\.?[A-Za-z_][\w.\-]*(?:/[\w.\-]*)+")  # _PATH_REF plus a bare `dir/`
_FRONTMATTER = re.compile(r"---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.S)


def _cap(text: str, limit: int) -> str:
    """Cut text until its JSON-escaped length fits limit bytes."""
    while text and len(json.dumps(text)) - 2 > limit:
        text = text[:max(0, len(text) - max(1, (len(json.dumps(text)) - 2 - limit) // 6))]
    return text


_SENTENCE_END = re.compile(r"[.!?:;](?=\s|$)|\n")


def _cap_sentence(text: str, limit: int) -> str:
    """Text cut to fit limit JSON bytes, ending at the last sentence end in its back half, else the last word."""
    cut = _cap(text, limit)
    if cut == text:
        return text
    ends = [m.end() for m in _SENTENCE_END.finditer(cut)]
    if ends and ends[-1] >= len(cut) // 2:
        return cut[:ends[-1]].rstrip()
    space = cut.rfind(" ")
    return (cut[:space] if space > 0 else cut).rstrip()


def _split_frontmatter(text: str) -> Tuple[Dict[str, str], str]:
    fm: Dict[str, str] = {}
    m = _FRONTMATTER.match(text) if text.startswith("---") else None
    if not m:
        return fm, text
    for line in m.group(1).splitlines():
        kv = re.match(r"([A-Za-z_][\w-]*):\s*(.*)$", line)
        if kv:
            val = re.sub(r"\s+#.*$", "", kv.group(2)).strip().strip("\"'")
            if val not in ("null", "~"):
                fm[kv.group(1).lower()] = val
    return fm, text[m.end():]


def lift_section_bullets(body: str) -> List[dict]:
    """Bullets and table rows under the LIFT_SECTIONS headings, outside code fences.

    Each item is {"section", "type", "text", "kind"}: kind "b" (text a string, continuation lines
    joined) or "r" (text a list of cells; the header row is dropped by its separator line). Under a
    Design, Decision or What-I-Learned heading an indented bullet is its own item. A Tasks / Task
    spine heading and its subsections lift nothing.
    """
    out: List[dict] = []
    sec: Optional[Tuple[str, str]] = None
    level = 0
    spine_level = 0
    cur: Optional[dict] = None
    fence = False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        head = re.match(r"(#{1,6})\s+(.*)", line)
        if head:
            n = len(head.group(1))
            if spine_level and n <= spine_level:
                spine_level = 0
            if not spine_level and _is_spine_title(head.group(2)):
                spine_level = n
            if sec is not None and n <= level:
                sec = None
            if sec is None and not spine_level:
                title = re.sub(r"[^a-z ]", "", head.group(2).lower()).strip()
                for key, kind in LIFT_SECTIONS:
                    if title.startswith(key):
                        sec, level = (key, kind), n
                        break
            cur = None
            continue
        if sec is None or spine_level:
            continue
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if re.fullmatch(r"[\s|:\-]+", line) and "-" in line:
                if out and out[-1]["kind"] == "r":
                    out.pop()
            elif any(cells):
                out.append({"section": sec[0], "type": sec[1], "text": cells, "kind": "r"})
            cur = None
            continue
        bullet = re.match(r"(?:[-*]|\d+\.)\s+(.*)", line.lstrip() if sec[0] in _SUBBULLET_SECTIONS else line)
        if bullet:
            cur = {"section": sec[0], "type": sec[1], "text": bullet.group(1), "kind": "b"}
            out.append(cur)
        elif cur is not None and line[:1] in (" ", "\t") and line.strip():
            cur["text"] += " " + re.sub(r"^[-*]\s+", "", line.strip())
        elif line.strip():
            cur = None
    return out


def _clean(text: str) -> str:
    """Drop the trailing commit list and markup, collapse whitespace."""
    text = re.split(r"\s+\|\s+commits:", text)[0]
    return re.sub(r"\s+", " ", re.sub(r"[*`]", "", text)).strip()


def _path_tag(text: str) -> str:
    """Slug from the first repo-style path in text: its first two non-generic directories."""
    for m in _PATH_REF.finditer(text):
        parts = [p for p in m.group(0).rstrip(".,;:").split("/") if p]
        if len(parts) < 2 or len(parts[0]) < 2 or parts[0].lower() in _NOT_A_SYSTEM:
            continue
        dirs = parts[:-1] if "." in parts[-1] else parts
        keep = [slugify(p) for p in dirs if slugify(p) and slugify(p) not in _GENERIC_DIRS
                and not re.search(r"\d{4}", p)] or [slugify(p) for p in dirs if slugify(p)]
        if keep:
            return "-".join(keep[:2])
    return ""


def _wiki_tag(text: str, wiki_slugs: Dict[str, str]) -> str:
    """A wiki slug named in text: longest 2-6 word run first, then a backticked file stem.

    The word-run pass skips repo paths, so a cited path's tokens never name a page; only prose does.
    """
    if not wiki_slugs:
        return ""
    tokens = re.findall(r"[a-z0-9]+", _PATH_LIKE.sub(" ", text).lower())
    for n in range(6, 1, -1):
        for k in range(len(tokens) - n + 1):
            gram = "-".join(tokens[k:k + n])
            if gram in wiki_slugs:
                return gram
    for m in re.findall(r"`([^`]+)`", text):
        gram = slugify(re.sub(r"\.md$", "", m.split("/")[-1]))
        if gram in wiki_slugs:
            return gram
    return ""


def _leading_tag(text: str) -> str:
    return "-".join(re.findall(r"[a-z0-9]+", text.lower())[:4])


def _file_tag(fm: Dict[str, str], core: str, title: str, headings: List[str],
              wiki_slugs: Dict[str, str]) -> Tuple[str, str]:
    """(tag, tag_source) of a whole file: frontmatter, wiki (title/headings name a page), file-stem or fallback."""
    for key in ("topic", "system", "area"):
        val = fm.get(key, "")
        if val and not re.search(r"[,;|]", val) and slugify(val):
            return slugify(val), "frontmatter"
    prose = set(re.findall(r"[a-z0-9]+", (title + " " + " ".join(headings[:6])).lower()))
    words = prose | set(core.split("-"))
    fits = [s for s in wiki_slugs if all(w in words for w in s.split("-"))
            and (len(s.split("-")) > 1 or s in core.split("-"))]
    if fits:
        best = min(fits, key=lambda s: (-len(s.split("-")), s))
        return best, "wiki" if all(w in prose for w in best.split("-")) else "file-stem"
    stem = "-".join(core.split("-")[:5])
    return (stem, "file-stem") if stem else (UNCATEGORIZED, "fallback")


def _file_fate(rel: str, fate: str, why: str) -> dict:
    """The one recorded outcome of a file that yields no nugget (the workflow's file_fates shape)."""
    base = rel.rsplit("/", 1)[-1]
    return {"path": rel, "fate": fate,
            "fate_prose": f"{base} was classified by script in prepare as {fate}: {why}; no scan agent read it."}


def _is_spine_title(title: str) -> bool:
    """True for a plan's work-list heading (Tasks, Task spine): a section the lifter never takes."""
    return re.sub(r"[^a-z ]", "", title.lower()).strip() in _SPINE_TITLES


def _is_historical_title(title: str) -> bool:
    """True for a Problem / Background heading: the state before a shipped plan landed."""
    return re.sub(r"[^a-z ]", "", title.lower()).strip().startswith(_HISTORICAL_TITLES)


def _h2_sections(body: str) -> List[Tuple[str, str]]:
    """(title, text) of each H2 section outside code fences (the whole body when it has no H2).

    A Tasks / Task spine section and every ```yaml plan-tasks fenced block are dropped.
    """
    sections: List[Tuple[str, List[str]]] = [("", [])]
    fence = False
    spine_fence = False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            if spine_fence:
                spine_fence = False
                continue
            if not fence and _SPINE_FENCE.match(line):
                spine_fence = True
                continue
            fence = not fence
        elif spine_fence:
            continue
        head = None if fence else re.match(r"##\s+(.*)", line)
        if head and not line.startswith("###"):
            sections.append((head.group(1).strip(), []))
        else:
            sections[-1][1].append(re.sub(r"^#{1,6}\s+", "", line))
    if len(sections) > 1:
        sections = sections[1:]
    return [(title, " ".join(lines)) for title, lines in sections
            if any(ln.strip() for ln in lines) and not _is_spine_title(title)]


def is_triage_only(rel: str) -> bool:
    """True for a daily-summary or week-changelog file: read-only intake that is admitted, never harvested."""
    return bool(_TRIAGE_ONLY_DIRS & set(rel.replace("\\", "/").split("/")[:-1]))


def lift_file(rel: str, text: str, wiki_slugs: Dict[str, str], batch_id: str, index: int,
              fates: Optional[List[dict]] = None) -> List[dict]:
    """Nuggets lifted from one file; every file yields nuggets or exactly one entry appended to `fates`.

    A triage-only file (`is_triage_only`) is the exception: it lifts nothing and records no fate.

    Section bullets lift first. A file with none lifts whole: one nugget per H2 section (the whole
    body when it has none) under the file's tag. Empty, retired, ephemeral-path and already-captured
    files, and files whose content cleans to nothing, lift nothing and record a fate. Tag order for
    bullets: wiki slug in the content, else path tag, else (a Systems Affected row or a box-named
    rollup) leading words, else the file's own tag. Each nugget's tag_source (frontmatter, wiki, path,
    leading, file-stem, fallback) says where its tag came from; cluster_nuggets homes the last four
    by content or per nugget. A whole-file nugget from a Problem or Background H2 of a `status:
    implemented` file carries historical true. A Tasks section lifts nothing; a file whose only
    content is one records an EPHEMERAL fate.
    """
    def fate(kind: str, why: str) -> List[dict]:
        if fates is not None:
            fates.append(_file_fate(rel, kind, why))
        return []

    if is_triage_only(rel):
        return []
    fm, body = _split_frontmatter(text)
    parts = rel.split("/")
    stem = os.path.basename(rel)
    stem = stem[:-3] if stem.endswith(".md") else stem
    core = slugify(_DATE_PREFIX.sub("", stem))
    if not body.strip():
        return fate("EPHEMERAL", "the file has no body")
    if fm.get("superseded_by") or fm.get("status", "").lower() in _RETIRED_STATUS:
        return fate("EPHEMERAL", "the file is retired or superseded")
    if _EPHEMERAL_DIRS & set(parts[:-1]):
        return fate("EPHEMERAL", "the file sits in a working-state directory")
    headings = [re.sub(r"^#+\s*", "", ln).strip() for ln in body.splitlines() if re.match(r"#{1,3}\s", ln)]
    title = fm.get("title") or (headings[0] if headings else "") or core.replace("-", " ")
    ftype = "DECISION" if (fm.get("kind") or fm.get("type") or fm.get("category") or "").lower() == "decision" \
        or "decisions" in parts or core.startswith("dr-") else "KNOWLEDGE"
    if ftype == "KNOWLEDGE" and core in wiki_slugs and wiki_slugs[core] != rel:
        return fate("ALREADY_CAPTURED", "a wiki page with the same slug already holds it")
    items = lift_section_bullets(body)
    ftag, ftag_src = _file_tag(fm, core, title, headings, wiki_slugs)
    ftag = _cap(ftag, LIFT_TAG_BYTES)
    dm_ = _DATE_PREFIX.match(stem)
    date = (fm.get("date") or (dm_.group(1) if dm_ else ""))[:10]
    if not items:
        whole: List[dict] = []
        shipped = fm.get("status", "").lower() == "implemented"
        for sec_title, section in _h2_sections(body):
            content = _clean((f"{sec_title}: " if sec_title else "") + section)
            if not content:
                continue
            nugget = {"id": f"{batch_id}-{index + 1:03d}-{len(whole) + 1:02d}", "type": ftype, "source": rel,
                      "content": _cap_sentence(content, LIFT_CONTENT_BYTES) or core or "file",
                      "system_tag": ftag or UNCATEGORIZED, "tag_source": ftag_src if ftag else "fallback"}
            if date:
                nugget["date"] = date
            if shipped and _is_historical_title(sec_title):
                nugget["historical"] = True
            whole.append(nugget)
        return whole or fate("EPHEMERAL", "the file has no content to lift")
    box = slugify(fm.get("machine") or fm.get("box") or fm.get("host") or "")
    rollup = "rollup_schema" in fm or "grain" in fm or (box != "" and core == box)
    rollup_untagged = rollup and ftag == "-".join(core.split("-")[:5])

    def systems_text(it: dict) -> str:
        return it["text"][0] if it["kind"] == "r" else it["text"]

    def item_tag(text: str, clean: str) -> Tuple[str, str]:
        found = _wiki_tag(text, wiki_slugs)
        if found:
            return found, "wiki"
        found = _path_tag(text)
        return (found, "path") if found else (_leading_tag(clean), "leading")

    system_tags = [item_tag(systems_text(it), _clean(systems_text(it)))
                   for it in items if it["section"] == "systems affected"]
    nuggets: List[dict] = []
    for it in items:
        is_sys = it["section"] == "systems affected"
        if it["kind"] == "r":
            cells = it["text"]
            raw = cells[0] if is_sys else " ".join(cells)
            content = _clean(cells[0] + (" - " + cells[-1] if len(cells) > 1 else "")) if is_sys \
                else _clean(" | ".join(cells))
        else:
            raw = content = it["text"]
            content = _clean(raw)
        if not content:
            continue
        words = set(re.findall(r"[a-z0-9]+", raw.lower()))
        tag, src = _wiki_tag(raw, wiki_slugs), "wiki"
        if not tag:
            tag, src = _path_tag(raw), "path"
        if not tag and not is_sys:
            tag, src = next(((s, o) for s, o in system_tags if s and any(len(w) > 3 and w in words for w in s.split("-"))),
                            ("", ""))
        if not tag:
            tag, src = (_leading_tag(content), "leading") if is_sys or rollup_untagged else (ftag, ftag_src)
        nugget = {"id": f"{batch_id}-{index + 1:03d}-{len(nuggets) + 1:02d}",
                  "type": "DECISION" if it["type"] == "DECISION" or ftype == "DECISION" else "KNOWLEDGE",
                  "source": rel, "content": _cap_sentence(content, LIFT_CONTENT_BYTES) or core or "file",
                  "system_tag": _cap(tag, LIFT_TAG_BYTES) or UNCATEGORIZED,
                  "tag_source": src if _cap(tag, LIFT_TAG_BYTES) else "fallback"}
        if date:
            nugget["date"] = date
        nuggets.append(nugget)
    return nuggets or fate("EPHEMERAL", "the file has no content to lift")


def lift_batches(repo: Path, batches: List[dict], wiki_slugs: Dict[str, str],
                 read: Optional[List[str]] = None, fates: Optional[List[dict]] = None) -> List[dict]:
    """Lifted nuggets for every readable batch file, in batch then file order.

    `read`, when given, collects each readable file's path (the files prepare classified); `fates`
    collects the file fate of each readable file that lifted no nugget. A triage-only file is skipped
    unread: it joins neither `read` nor `fates`.
    """
    out: List[dict] = []
    for batch in batches:
        for index, rel in enumerate(batch["files"]):
            if is_triage_only(str(rel)):
                continue
            try:
                text = inside(repo, rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if read is not None:
                read.append(str(rel).replace("\\", "/"))
            out.extend(lift_file(str(rel).replace("\\", "/"), text, wiki_slugs, str(batch.get("batchId", "")), index,
                                 fates))
    return out


# --------------------------------------------------------------------------- synth leg

SYNTH_AGENT_TYPE = "coordinator:distill-synth"
DISTILL_WRITER_TYPE = "coordinator:distill-writer"
SYNTH_BATCH_BYTES = 200000  # ~50K tokens at estimate_tokens' 4 bytes per token
MAX_SYNTH_CALLS = 3
SYNTH_OUTLINE_CHARS = 2000
SYNTH_TOPIC_TOKENS = 10000
MINTED_DR_DECIDER = "EM"  # the decision was taken in the cited source work; the scaffold's placeholder is replaced. Unverified attribution: a distill-minted record is accepted on the source's authority, not a fresh decision
_DR_TEXT_FIELDS = ("problem", "decision", "alternatives", "implementation")
NO_OPS_REASONS = ("nothing-new-vs-page", "all-nuggets-duplicate", "insufficient-substance", "stale-code-state")
NO_OPS_DROPPED = "dropped"  # a sent topic the synth never named
NO_OPS_UNREASONED = "unreasoned"  # a named topic with nothing landing and no valid no_ops_reason
DISPOSITION_UNCITED = "uncited"  # no landed op or record cites the nugget and no reason covers it
DISPOSITION_JUDGED = "JUDGED:"  # prefix; the synth gave the nugget a NO_OPS_REASONS reason instead of a cite
_NO_ITEMS = {"maxItems": 0}
HOME_KINDS = ("durable-contract", "root-cause")
DISPOSITION_HOME_SUGGESTED = "home-suggested"  # the JUDGED: reason of a nugget carrying a valid home_suggestion
_NUGGET_ID_BATCH = re.compile(r"^(.+)-\d{3}-\d{2}$")


def judge_topic_key(nugget_id: object) -> str:
    """The judge-only topic key of a per-nugget nugget: nugget-<scan batch id>, the id minus its file and nugget segments.

    An id not shaped `<batch>-<file:03d>-<nugget:02d>` keeps its own key, nugget-<full id>.
    """
    text = str(nugget_id)
    m = _NUGGET_ID_BATCH.match(text)
    return slugify(f"nugget-{m.group(1) if m else text}")


def record_nuggets(cluster: dict) -> List[dict]:
    """A per_nugget cluster's nuggets that ride a record-capable topic under the cluster's own key.

    The harvest workflow forces any `nugget-` key judge-only, so only other keys carry decision records;
    every other nugget of a per_nugget cluster is judged under its batch key.
    """
    if cluster["topicKey"].startswith("nugget-"):
        return []
    return [n for n in cluster["nuggets"] if n.get("type") == "DECISION"]


def _valid_home_suggestion(hs: object) -> bool:
    """A home_suggestion is {wiki_path: repo-relative path, kind: one of HOME_KINDS}."""
    if not (isinstance(hs, dict) and hs.get("kind") in HOME_KINDS and isinstance(hs.get("wiki_path"), str)):
        return False
    norm = hs["wiki_path"].strip().replace("\\", "/")
    return bool(norm) and not norm.startswith("/") and not re.match(r"^[A-Za-z]:", norm) and ".." not in norm.split("/")


def _is_cited(disposition: str) -> bool:
    """True for ADD_SECTION, CREATE_DR and DR-EXISTS; false for an uncited or JUDGED nugget."""
    return disposition != DISPOSITION_UNCITED and not disposition.startswith(DISPOSITION_JUDGED)


def _synth_topic_schema(key: Optional[str] = None, ids: Optional[List[str]] = None) -> dict:
    """One topic entry's schema; with key and ids, topic_key is a const and every cite an enum of ids.

    An entry with no ops and no decision_records must carry no_ops_reason (if/then). The optional
    nugget_reasons gives each nugget the entry leaves uncited a reason of its own; page_title names the
    page a per-nugget topic would mint.
    """
    cite = {"enum": list(ids)} if ids else {"type": "string"}
    return {
        "type": "object", "required": ["topic_key", "ops"],
        "properties": {
            "topic_key": {"const": key} if key is not None else {"type": "string"},
            "no_ops_reason": {"enum": list(NO_OPS_REASONS)},
            "page_title": {"type": "string"},
            "nugget_reasons": {"type": "array", "items": {
                "type": "object", "required": ["nugget_id", "reason"],
                "properties": {"nugget_id": cite, "reason": {"enum": list(NO_OPS_REASONS)},
                               "home_suggestion": {"type": "object", "required": ["wiki_path", "kind"],
                                                   "properties": {"wiki_path": {"type": "string"},
                                                                  "kind": {"enum": list(HOME_KINDS)}}}}}},
            "ops": {"type": "array", "items": {
                "type": "object", "required": ["section_heading", "action", "markdown", "cites"],
                "properties": {"section_heading": {"type": "string"},
                               "action": {"enum": ["append", "new_section"]},
                               "markdown": {"type": "string"},
                               "cites": {"type": "array", "minItems": 1, "items": cite}}}},
            "decision_records": {"type": "array", "items": {
                "type": "object", "required": ["nugget_id", "title", "decision", "cites"],
                "properties": {"nugget_id": cite, "title": {"type": "string"},
                               "problem": {"type": "string"}, "decision": {"type": "string"},
                               "alternatives": {"type": "string"}, "implementation": {"type": "string"},
                               "cites": {"type": "array", "minItems": 1, "items": cite}}}}},
        "if": {"properties": {"ops": _NO_ITEMS, "decision_records": _NO_ITEMS}, "required": ["ops"]},
        "then": {"required": ["no_ops_reason"]},
    }


def payload_schema(payload: dict) -> dict:
    """Schema for one synth call: topic_key enum over the payload's keys, each key's cites enum over its cite_ids.

    Parts of one topic split across inputs share a key, so their ids merge under it.
    """
    ids_by_key: Dict[str, List[str]] = {}
    judge_only: set = set()
    for t in payload.get("topics", []):
        have = ids_by_key.setdefault(t["topic_key"], [])
        have += [i for i in t.get("cite_ids", []) if i not in have]
        if t.get("judge_only"):
            judge_only.add(t["topic_key"])
    shared = _synth_topic_schema()
    shared["properties"]["topic_key"] = {"enum": list(ids_by_key)}
    shared["anyOf"] = [_topic_cite_variant(k, v, k in judge_only) for k, v in ids_by_key.items()]
    return {"type": "object", "required": ["topics"],
            "properties": {"topics": {"type": "array", "items": shared}}}


def _topic_cite_variant(key: str, ids: List[str], judge_only: bool = False) -> dict:
    """The per-topic constraint alone: topic_key const and cite enums; the op and record shapes live once in the shared items schema.

    A judge-only topic has no page to splice or mint onto, so its ops and decision_records stay empty.
    """
    cite = {"enum": list(ids)} if ids else {"type": "string"}
    return {"properties": {
        "topic_key": {"const": key},
        "ops": _NO_ITEMS if judge_only else {"items": {"properties": {"cites": {"items": cite}}}},
        "nugget_reasons": {"items": {"properties": {"nugget_id": cite}}},
        "decision_records": _NO_ITEMS if judge_only
        else {"items": {"properties": {"nugget_id": cite, "cites": {"items": cite}}}}}}


SYNTH_SCHEMA = {"type": "object", "required": ["topics"],
                "properties": {"topics": {"type": "array", "items": _synth_topic_schema()}}}
_GOTCHA = re.compile(r"^\s*[-*]\s+\**(gotcha|trap|pitfall)\b", re.I)
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_CODE_PATH = re.compile(r"`([A-Za-z_.][\w.\-]*(?:/[\w.\-]+)+\.[A-Za-z0-9]{1,5})`")


def estimate_tokens(payload: object) -> int:
    """Tokens of a JSON payload at 4 bytes each, rounded up."""
    return -(-len(json.dumps(payload, sort_keys=True)) // 4)


def page_outline(text: str, limit: int = SYNTH_OUTLINE_CHARS) -> dict:
    """Heading outline and gotcha one-liners of a page, frontmatter and code fences skipped, within limit chars."""
    _, body = _split_frontmatter(text)
    headings: List[str] = []
    gotchas: List[str] = []
    used = 0
    fence = False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        m = _HEADING.match(line)
        item = line.strip() if m else (line.strip()[:120] if _GOTCHA.match(line) else "")
        if not item:
            continue
        if used + len(item) > limit:
            break
        used += len(item)
        (headings if m else gotchas).append(item)
    return {"headings": headings, "gotchas": gotchas}


def _cited_code_paths(nugget: dict) -> List[str]:
    return list(dict.fromkeys(_CODE_PATH.findall(nugget.get("content") or "")))


def last_commit_dates(repo: Path, wanted: set, since: str) -> Dict[str, str]:
    """Path -> last commit date (YYYY-MM-DD) for the wanted paths, from ONE `git log` over commits since `since`.

    A wanted path last committed before `since` is absent; a git failure yields an empty map.
    """
    if not wanted:
        return {}
    try:
        proc = run_cmd(["git", "-c", "core.quotepath=off", "log", "--name-only", "--no-renames",
                        "--format=%x01%cs", f"--since={since}"], repo, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return {}
    if proc.returncode != 0:
        return {}
    dates: Dict[str, str] = {}
    day = ""
    for line in proc.stdout.splitlines():
        if line.startswith("\x01"):
            day = line[1:].strip()
        elif line.strip() and line.strip() in wanted and line.strip() not in dates:
            dates[line.strip()] = day
    return dates


def stale_code_stamps(clusters: List[dict], repo: Path) -> Dict[str, bool]:
    """Nugget id -> whether any code path its text cites was committed after the nugget's date.

    One git invocation covers the run. A nugget with no date, no cited path, or no cited path that
    resolves (in git history since the earliest nugget date, or on disk) gets no entry.
    """
    dated = [n for c in clusters for n in c["nuggets"] if n.get("date") and n.get("id") is not None]
    wanted = {p for n in dated for p in _cited_code_paths(n)}
    dates = last_commit_dates(repo, wanted, min(n["date"] for n in dated)) if wanted else {}
    stamps: Dict[str, bool] = {}
    for n in dated:
        paths = [p for p in _cited_code_paths(n) if p in dates or (repo / p).is_file()]
        if paths:
            stamps[n["id"]] = any(dates.get(p, "") > n["date"] for p in paths)
    return stamps


def synth_entry(n: dict) -> dict:
    """The synth payload's view of a cluster nugget; pack_synth_payloads drops whatever this re-derives."""
    return {"id": n.get("id"), "text": n.get("content", ""), "cite": n.get("source", ""),
            **{k: n[k] for k in ("type", "date", "historical") if n.get(k) is not None}}


def synth_inputs(clusters: List[dict], repo: Path) -> List[dict]:
    """Per-topic synth input: curated nuggets plus the target page's outline; no source or page text.

    A topic whose nuggets exceed SYNTH_TOPIC_TOKENS is split into several inputs sharing one topic_key;
    a lone nugget still over the bar is cut at a sentence end to fit. Each nugget with a resolvable
    cited code path carries stale_code_state (see stale_code_stamps).
    """
    stamps = stale_code_stamps(clusters, repo)
    out: List[dict] = []

    def split_into(head: dict, nuggets: List[dict]) -> None:
        part: List[dict] = []

        def shaped(entries: List[dict]) -> dict:
            return {**head, "nuggets": entries, "cite_ids": [n["id"] for n in entries]}

        def flush() -> None:
            if part:
                out.append(shaped(list(part)))
                part.clear()

        for n in nuggets:
            entry = synth_entry(n)
            if n.get("id") in stamps:
                entry["stale_code_state"] = stamps[n["id"]]
            if estimate_tokens(shaped(part + [entry])) > SYNTH_TOPIC_TOKENS:
                flush()
            while estimate_tokens(shaped([entry])) > SYNTH_TOPIC_TOKENS and entry["text"]:
                entry["text"] = _cap_sentence(entry["text"], int((len(json.dumps(entry["text"])) - 2) * 0.8))
            part.append(entry)
        flush()

    batches: Dict[str, List[dict]] = {}
    for c in clusters:
        nuggets = c["nuggets"]
        if c.get("per_nugget"):
            records = record_nuggets(c)
            record_ids = {n.get("id") for n in records}
            for n in nuggets:
                if n.get("id") not in record_ids:
                    batches.setdefault(judge_topic_key(n.get("id")), []).append(n)
            nuggets = records
            if not nuggets:
                continue
        page = inside(repo, c["wikiPath"])
        outline = page_outline(page.read_text(encoding="utf-8", errors="replace")) \
            if c.get("homed") and page.is_file() else {"headings": [], "gotchas": []}
        split_into({"topic_key": c["topicKey"], "wiki_path": c["wikiPath"], "new_page": not page.is_file(),
                    "outline": outline}, nuggets)
    for key in sorted(batches):
        split_into({"topic_key": key, "judge_only": True}, batches[key])
    return out


def pack_synth_batches(inputs: List[dict], cap: Optional[int] = None,
                       weight: Optional[Dict[str, int]] = None) -> List[List[dict]]:
    """Greedy batches of topics in slug order, each within cap (default SYNTH_BATCH_BYTES) JSON bytes; an oversize topic rides alone.

    `weight` adds bytes per topic_key on top of the input's own: the clusters a payload's launch shard
    must carry, which the input bytes do not show and which alone can push one payload past the launch cap."""
    cap = SYNTH_BATCH_BYTES if cap is None else cap
    batches: List[List[dict]] = []
    size = 0
    for item in sorted(inputs, key=lambda i: slugify(i["topic_key"])):
        n = len(json.dumps(item)) + (weight or {}).get(item["topic_key"], 0)
        if not batches or size + n > cap:
            batches.append([])
            size = 0
        batches[-1].append(item)
        size += n
    return batches


def pack_wiki_slugs(slugs: Dict[str, str]) -> Dict[str, List[str]]:
    """The slug->path index grouped by parent directory: `slug` when the file is `<slug>.md`, else
    `slug=<basename>`. prepared.json rides inline in the Workflow launch under its 524,288-byte cap,
    and the flat map's repeated path prefixes were most of it. Inverse: unpack_wiki_slugs; the
    harvest workflow's loader unpacks the same shape."""
    packed: Dict[str, List[str]] = {}
    for slug, path in sorted(slugs.items()):
        parent, _, base = path.rpartition("/")
        packed.setdefault(parent, []).append(slug if base == f"{slug}.md" else f"{slug}={base}")
    return packed


def unpack_wiki_slugs(packed: Dict[str, List[str]]) -> Dict[str, str]:
    slugs: Dict[str, str] = {}
    for parent, entries in packed.items():
        for entry in entries:
            slug, _, base = entry.partition("=")
            base = base or f"{slug}.md"
            slugs[slug] = f"{parent}/{base}" if parent else base
    return slugs


_ABSENT = object()


def _nuggets_by_id(clusters: object) -> Dict[str, dict]:
    by_id: Dict[str, dict] = {}
    for c in clusters if isinstance(clusters, list) else []:
        for n in c.get("nuggets") or []:
            if n.get("id") is not None:
                by_id.setdefault(n["id"], n)
    return by_id


def pack_synth_payloads(payloads: List[dict], clusters: object) -> List[dict]:
    """Payload nuggets without what `synth_entry` re-derives from the same prepared's clusters: a clustered
    nugget's content rode in both, and prepared.json rides inline under the Workflow script cap.
    A packed entry is `{id, <keys that differ from the derivation>}`; a key the derivation holds and the
    entry lacks is packed as null (so an explicit None value does not round-trip). `cite_ids` is dropped
    when it equals the nuggets' ids. Inverse: unpack_synth_payloads; the harvest workflow's loader
    (restorePrepared) mirrors it."""
    by_id = _nuggets_by_id(clusters)

    def entry(e: dict) -> dict:
        n = by_id.get(e.get("id"))
        if n is None:
            return e
        base = synth_entry(n)
        return {"id": e["id"], **{k: v for k, v in e.items() if k != "id" and base.get(k, _ABSENT) != v},
                **{k: None for k in base if k not in e}}

    def topic(t: dict) -> dict:
        nuggets = t.get("nuggets")
        if not isinstance(nuggets, list):
            return t
        packed = {**t, "nuggets": [entry(e) for e in nuggets]}
        if t.get("cite_ids") == [e.get("id") for e in nuggets]:
            del packed["cite_ids"]
        return packed

    return [{**p, "topics": [topic(t) for t in p.get("topics") or []]} for p in payloads]


def unpack_synth_payloads(payloads: List[dict], clusters: object) -> List[dict]:
    by_id = _nuggets_by_id(clusters)

    def entry(e: dict) -> dict:
        n = by_id.get(e.get("id"))
        if n is None:
            return e
        out = synth_entry(n)
        for k, v in e.items():
            if v is None:
                out.pop(k, None)
            else:
                out[k] = v
        return out

    def topic(t: dict) -> dict:
        nuggets = t.get("nuggets")
        if not isinstance(nuggets, list):
            return t
        full = [entry(e) for e in nuggets]
        return {**t, "nuggets": full, **({} if "cite_ids" in t else {"cite_ids": [e.get("id") for e in full]})}

    return [{**p, "topics": [topic(t) for t in p.get("topics") or []]} for p in payloads]


UNREAD_NUGGET_KEYS = ("system_tag", "tag_source")


def _cluster_derivations(cluster: dict, wiki_slugs: Dict[str, str], wiki_dirs: object) -> dict:
    """What cluster_nuggets would write for the keys a slug fixes: topicKey, homed, wikiPath and per_nugget."""
    slug = cluster["slug"]
    path = wiki_slugs.get(slug)
    primary = wiki_dirs[0] if isinstance(wiki_dirs, list) and wiki_dirs else "docs/wiki"
    return {"topicKey": slug, "homed": path is not None, "wikiPath": path or f"{primary}/{slug}.md",
            "per_nugget": slug.startswith("nugget-")}


def pack_clusters(clusters: List[dict], wiki_slugs: Dict[str, str], wiki_dirs: object) -> List[dict]:
    """Clusters without what their slug re-derives (topicKey, homed, wikiPath, per_nugget, each dropped only
    where it equals the derivation) and without the nugget keys nothing reads after prepare (system_tag,
    tag_source: the workflow's scan path reads them, a prepared cluster's nuggets never). prepared.json rides
    inline under the Workflow launch cap. A cluster carrying no str slug is kept whole. Inverse:
    unpack_clusters; the harvest workflow's loader (restoreClusters) mirrors it."""
    def one(c: dict) -> dict:
        if not isinstance(c.get("slug"), str):
            return c
        derived = _cluster_derivations(c, wiki_slugs, wiki_dirs)
        out = {k: v for k, v in c.items() if k not in derived or c[k] != derived[k]}
        if derived["per_nugget"] and "per_nugget" not in c:
            out["per_nugget"] = False
        out["nuggets"] = [{k: v for k, v in n.items() if k not in UNREAD_NUGGET_KEYS} for n in c.get("nuggets") or []]
        return out

    return [one(c) if isinstance(c, dict) else c for c in clusters]


def unpack_clusters(clusters: List[dict], wiki_slugs: Dict[str, str], wiki_dirs: object) -> List[dict]:
    """Restores the keys pack_clusters derived; the nugget keys it dropped stay dropped."""
    def one(c: dict) -> dict:
        if not isinstance(c.get("slug"), str):
            return c
        derived = _cluster_derivations(c, wiki_slugs, wiki_dirs)
        out = {**{k: v for k, v in derived.items() if k != "per_nugget"}, **c}
        if "per_nugget" not in c and derived["per_nugget"]:
            out["per_nugget"] = True
        return out

    return [one(c) if isinstance(c, dict) else c for c in clusters]


def prepared_text(prepared: dict) -> str:
    """The exact text write_prepared lands: the packed compact JSON, one trailing newline."""
    out = dict(prepared)
    wiki_slugs = out.get("wikiSlugs") or {}
    if "wikiSlugs" in out:
        out["wikiSlugsPacked"] = pack_wiki_slugs(out.pop("wikiSlugs") or {})
    synth = out.get("synth")
    if isinstance(synth, dict) and isinstance(synth.get("payloads"), list) and not synth.get("payloadsPacked"):
        out["synth"] = {**synth, "payloads": pack_synth_payloads(synth["payloads"], out.get("clusters")),
                        "payloadsPacked": True}
    synth = out.get("synth")
    if isinstance(synth, dict) and isinstance(synth.get("schemas"), list) and not synth.get("schemasDerived"):
        full = synth["payloads"]
        if synth.get("payloadsPacked"):
            full = unpack_synth_payloads(full, out.get("clusters"))
        if synth["schemas"] == [payload_schema(p) for p in full]:
            out["synth"] = {**{k: v for k, v in synth.items() if k != "schemas"}, "schemasDerived": True}
    clusters = out.get("clusters")
    if (isinstance(clusters, list) and clusters and not out.get("clustersPacked")
            and all(isinstance(c, dict) and isinstance(c.get("slug"), str) and isinstance(c.get("nuggets"), list)
                    and all(k in c for k in ("topicKey", "homed", "wikiPath")) for c in clusters)):
        out["clusters"] = pack_clusters(clusters, wiki_slugs, out.get("wikiDirs"))
        out["clustersPacked"] = True
    # Compact, not write_json's indent=2: whitespace counts against the launch's script cap too.
    return json.dumps(out, separators=(",", ":"), sort_keys=True) + "\n"


def write_prepared(path: Path, prepared: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n": the file's byte count is the launch's byte count on every OS.
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(prepared_text(prepared))


SHARD_KEY = "launchShard"
SHARDS_INDEX = "shards.json"
_SHARD_LOAD_KEYS = ("runId", "repoRoot", "wikiDirs", "wikiSlugs", "wikiSlugCount", "requiredAgentTypes")


def _payload_keys(payload: dict) -> List[str]:
    return [t["topic_key"] for t in payload.get("topics", []) if isinstance(t, dict) and "topic_key" in t]


def _payload_clusters(prepared: dict) -> List[set]:
    """Per payload, the topicKeys of the clusters it draws on: a homed topic by its key, a per_nugget cluster
    (batched under a judge-only key) by its nugget ids."""
    clusters = prepared.get("clusters") or []
    owner = {n.get("id"): c["topicKey"] for c in clusters for n in c.get("nuggets") or []}
    known = {c["topicKey"] for c in clusters}
    out = []
    for payload in prepared["synth"]["payloads"]:
        keys = set()
        for topic in payload.get("topics", []):
            if topic.get("topic_key") in known:
                keys.add(topic["topic_key"])
            keys |= {owner[n.get("id")] for n in topic.get("nuggets") or [] if n.get("id") in owner}
        out.append(keys)
    return out


def _payload_units(owned: List[set]) -> List[List[int]]:
    """Payload indices grouped so no cluster spans two groups; a shard never splits a cluster."""
    units: List[Tuple[List[int], set]] = []
    for i, keys in enumerate(owned):
        idx, held = [i], set(keys)
        for unit in [u for u in units if u[1] & held]:
            units.remove(unit)
            idx, held = unit[0] + idx, held | unit[1]
        units.append((sorted(idx), held))
    return sorted((u[0] for u in units))


def _shard_slice(prepared: dict, idx: List[int], primary: bool, owned: List[set], count: int) -> dict:
    synth = prepared["synth"]
    payloads = [synth["payloads"][i] for i in idx]
    topic_keys = {k for p in payloads for k in _payload_keys(p)}
    all_topic_keys = {k for p in synth["payloads"] for k in _payload_keys(p)}
    mine = set().union(*(owned[i] for i in idx))
    claimed = set().union(*owned)
    deferred = list(synth.get("deferred_topics") or []) if primary else []
    # Shard 0 also holds every entry no payload draws on (unchanged, deferred, pointer-covered topics).
    keep = (lambda k: k in mine or k not in claimed) if primary else (lambda k: k in mine)
    keep_file = (lambda k: k in topic_keys or k not in all_topic_keys) if primary else (lambda k: k in topic_keys)
    block = {**synth, "payloads": payloads, "deferred_topics": deferred,
             "deferred_nugget_ids": list(synth.get("deferred_nugget_ids") or []) if primary else []}
    for name in ("schemas", "batches"):
        if isinstance(synth.get(name), list) and len(synth[name]) == len(synth["payloads"]):
            block[name] = [synth[name][i] for i in idx]
    if isinstance(synth.get("topic_files"), dict):
        block["topic_files"] = {k: v for k, v in synth["topic_files"].items() if keep_file(k)}
    block["topics"] = len(topic_keys | set(deferred))
    base = ({k: v for k, v in prepared.items() if k not in ("clusters", "candidates", "sourceHashes", "synth")}
            if primary else {k: prepared[k] for k in _SHARD_LOAD_KEYS if k in prepared})
    if not primary:
        base.update({k: 0 for k in ("batch_count", "total_file_count") if k in prepared})
    return {**base, "synth": block,
            "clusters": [c for c in prepared.get("clusters") or [] if keep(c["topicKey"])],
            "candidates": [c for c in prepared.get("candidates") or [] if keep(c.get("topic_key"))],
            "sourceHashes": {k: v for k, v in (prepared.get("sourceHashes") or {}).items() if keep(k)},
            SHARD_KEY: {"index": 0, "count": count, "run_id": prepared.get("runId")}}


def shard_prepared(prepared: dict, script_bytes: int, budget: int) -> List[dict]:
    """Split one prepared dict into launches, each `script_bytes` plus its write_prepared file within `budget`.

    The partition unit is the synth payload: a shard holds a set of `synth.payloads` in payload order (at most
    MAX_SYNTH_CALLS; payloads sharing a cluster stay together, so the set can skip an index) plus exactly the `clusters`, `candidates` and `sourceHashes` entries of those payloads'
    topics. Greedy fill; a single payload that alone overflows raises DriverError launch-over-cap naming it.
    One launch fitting returns `[prepared]` unchanged, no SHARD_KEY. Otherwise each returned dict is a prepared
    dict in write_prepared's input form and carries `SHARD_KEY: {"index": i, "count": n, "run_id": runId}`.
    Shard 0 is primary: it alone carries the run context the non-synth phases read (batches, declared counts,
    file_fates, judgmentPrecheck, drIndex, curated, classified residue). Shards 1..n-1 carry the keys the
    workflow load phase asserts (runId, repoRoot, wikiDirs, wikiSlugs, requiredAgentTypes) and run synth only,
    with declared counts recomputed per shard. Each topic rides exactly one shard."""
    def size(shard: dict) -> int:
        return script_bytes + len(prepared_text(shard).encode("utf-8"))

    if size(prepared) <= budget:
        return [prepared]
    payloads = (prepared.get("synth") or {}).get("payloads") or []
    if not payloads:
        raise DriverError("launch-over-cap", f"the harvest launch is {size(prepared)} bytes over the {budget}-byte "
                                             "budget and holds no synth payload to split across launches")
    owned = _payload_clusters(prepared)
    groups: List[List[int]] = []
    current: List[int] = []
    for unit in _payload_units(owned):
        for attempt in (0, 1):
            trial = sorted(current + unit)
            primary = not groups
            # count=99 keeps the marker's width above any real shard count while the partition is unsettled.
            fits = (len(trial) <= MAX_SYNTH_CALLS
                    and size(_shard_slice(prepared, trial, primary, owned, 99)) <= budget)
            if fits:
                current = trial
                break
            if primary and not current and not attempt:
                # Shard 0 alone carries the run context; a payload that cannot share it rides shard 1,
                # leaving the primary payload-free.
                groups.append([])
                continue
            if not current or attempt:
                lone = size(_shard_slice(prepared, unit, primary, owned, 99))
                raise DriverError("launch-over-cap",
                                  f"synth payload {unit[0]} (topics {', '.join(_payload_keys(payloads[unit[0]]))}) alone "
                                  f"makes a {lone}-byte launch, over the {budget}-byte budget; it cannot be split")
            groups.append(current)
            current = []
    groups.append(current)
    shards = []
    for i, idx in enumerate(groups):
        shard = _shard_slice(prepared, idx, i == 0, owned, len(groups))
        shard[SHARD_KEY]["index"] = i
        shards.append(shard)
    return shards


def merge_shard_manifests(manifests: List[dict], shards_index: dict) -> dict:
    """One promote manifest from the per-shard manifests of a sharded run.

    `shards_index` is the SHARDS_INDEX content: `{run_id, budget, script_bytes, shards: [{path, index,
    launch_bytes, payloads, topics}]}`; each manifest carries its shard marker as `shard` (`{index, count,
    run_id}`). Requires every index in `shards_index` exactly once, else DriverError shard-index-missing or
    shard-index-duplicate. Returns `{run_id, files, synth_results, hashes}`: `files` and `synth_results`
    concatenated in shard index order, `hashes` unioned; two shards hashing one topic_key differently raise
    DriverError shard-merge-conflict, as do two shards staging one target. Shard 0's other keys (deletions, archive, wikiDirs) ride through; a
    manifest whose run_id differs from the index's, or whose index the index does not list, raises
    shard-merge-conflict."""
    run_id = shards_index.get("run_id")
    wanted = {s["index"] for s in shards_index.get("shards") or []}
    by_index: Dict[int, dict] = {}
    for m in manifests:
        marker = m.get("shard")
        if not isinstance(marker, dict) or not isinstance(marker.get("index"), int):
            raise DriverError("shard-index-missing", "a shard manifest carries no `shard` marker with an integer index")
        i = marker["index"]
        if i in by_index:
            raise DriverError("shard-index-duplicate", f"shard index {i} appears in more than one manifest")
        if i not in wanted:
            raise DriverError("shard-merge-conflict", f"shard index {i} is not in the shards index {sorted(wanted)}")
        if m.get("run_id", run_id) != run_id:
            raise DriverError("shard-merge-conflict", f"shard {i} manifest run_id {m.get('run_id')!r} is not {run_id!r}")
        by_index[i] = m
    absent = sorted(wanted - set(by_index))
    if absent:
        raise DriverError("shard-index-missing", f"no manifest for shard index {absent} of {sorted(wanted)}")
    merged: dict = {k: v for k, v in by_index[min(wanted)].items()
                    if k not in ("shard", "prepared", "files", "synth_results", "hashes", "run_id")}
    merged.update({"run_id": run_id, "files": [], "synth_results": [], "hashes": {}})
    staged_targets: set = set()
    for i in sorted(by_index):
        m = by_index[i]
        for row in m.get("files") or []:
            target = row.get("target")
            if target is not None and target in staged_targets:
                raise DriverError("shard-merge-conflict", f"shard {i} stages target {target!r} that an earlier shard already stages")
            staged_targets.add(target)
            merged["files"].append(row)
        merged["synth_results"] += list(m.get("synth_results") or [])
        for key, value in (m.get("hashes") or {}).items():
            if key in merged["hashes"] and merged["hashes"][key] != value:
                raise DriverError("shard-merge-conflict", f"topic {key!r} has different hashes across shards")
            merged["hashes"][key] = value
    return merged


def read_sharded_prepared(shards_index: dict, base: Path) -> dict:
    """The shards' prepared files read back (each unpacked against its own clusters) and joined into one
    dict: every shard's clusters and synth payloads, shard 0's run context. Relative shard paths resolve
    against `base`."""
    parts = []
    for entry in sorted(shards_index.get("shards") or [], key=lambda s: s["index"]):
        path = Path(entry["path"])
        parts.append(read_prepared(path if path.is_absolute() else base / path))
    if not parts:
        raise DriverError("unusable-input", "the shards index lists no shard")
    synth = {**(parts[0].get("synth") or {}),
             "payloads": [p for part in parts for p in (part.get("synth") or {}).get("payloads") or []]}
    return {**parts[0], "clusters": [c for part in parts for c in part.get("clusters") or []], "synth": synth}


def launch_bytes(prepared_path: Path, script_path: Path) -> int:
    """Bytes the harvest Workflow launch carries: the inline prepared.json plus the workflow script."""
    return Path(prepared_path).stat().st_size + Path(script_path).stat().st_size


def read_prepared(path: Path) -> dict:
    prepared = read_json(path)
    if "wikiSlugsPacked" in prepared:
        prepared["wikiSlugs"] = unpack_wiki_slugs(prepared.pop("wikiSlugsPacked"))
    if prepared.pop("clustersPacked", False):
        prepared["clusters"] = unpack_clusters(prepared["clusters"], prepared.get("wikiSlugs") or {},
                                               prepared.get("wikiDirs"))
    synth = prepared.get("synth")
    if isinstance(synth, dict) and synth.pop("payloadsPacked", False):
        synth["payloads"] = unpack_synth_payloads(synth["payloads"], prepared.get("clusters"))
    if isinstance(synth, dict) and synth.pop("schemasDerived", False):
        synth["schemas"] = [payload_schema(p) for p in synth.get("payloads") or []]
    return prepared


POINTER_TAG_NAMES = frozenset({"root cause", "decision", "ruling", "reversed prior", "DR citation", "contract",
                               "trap", "finding", "defect", "rule", "rationale", "persistence", "fleet"})
POINTER_TAG_FALLBACK = "durable"
# Lone-only tags: `durable` (pointed, no named kind) and `section` (a span no marker flagged —
# the pointer pass indexes every section). Trap: mechanical_disposition._TAG_CODES must stay a
# subset of POINTER_TAG_NAMES | POINTER_LONE_TAGS, or prepare refuses the index the pass writes.
POINTER_LONE_TAGS = frozenset({POINTER_TAG_FALLBACK, "section"})
POINTER_MAX_TAGS = 3
_POINTER_KEYS = frozenset({"path", "heading", "start_line", "end_line", "tag"})


def _posix_rel(path: object) -> str:
    text = str(path).replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def _pointer_entry_defect(entry: object) -> Optional[str]:
    if not isinstance(entry, dict):
        return "not a JSON object"
    if set(entry) != _POINTER_KEYS:
        missing, extra = sorted(_POINTER_KEYS - set(entry)), sorted(set(entry) - _POINTER_KEYS)
        return f"keys must be exactly {sorted(_POINTER_KEYS)} (missing {missing}, unexpected {extra})"
    for key in ("path", "heading"):
        if not isinstance(entry[key], str) or not entry[key].strip():
            return f"{key} must be a non-empty string"
    start, end = entry["start_line"], entry["end_line"]
    if any(isinstance(v, bool) or not isinstance(v, int) for v in (start, end)):
        return "start_line and end_line must be integers"
    if not 1 <= start <= end:
        return f"line span must satisfy 1 <= start_line <= end_line, got {start}..{end}"
    tag = entry["tag"]
    if not isinstance(tag, str) or not tag:
        return "tag must be a non-empty string"
    names = tag.split("+")
    if len(names) == 1 and names[0] in POINTER_LONE_TAGS:
        return None
    if len(names) > POINTER_MAX_TAGS or any(n not in POINTER_TAG_NAMES for n in names):
        return (f"tag {tag!r} must be one of {sorted(POINTER_LONE_TAGS)} alone or up to {POINTER_MAX_TAGS} names from "
                f"{sorted(POINTER_TAG_NAMES)} joined by '+'")
    return None


def load_pointer_index(path: Path) -> List[dict]:
    """The pointer index's entries: JSONL, one {path, heading, start_line, end_line, tag} object per line.

    Raises DriverError(unusable-input) naming the file and line of the first malformed entry; an index
    with no entries is refused too, since it would silently route every nugget to judgment.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise DriverError("unusable-input", f"pointer index {path}: {exc}") from exc
    entries: List[dict] = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError as exc:
            raise DriverError("unusable-input", f"pointer index {path}:{number}: not JSON: {exc}") from exc
        defect = _pointer_entry_defect(entry)
        if defect:
            raise DriverError("unusable-input", f"pointer index {path}:{number}: {defect}")
        entries.append(entry)
    if not entries:
        raise DriverError("unusable-input", f"pointer index {path}: no entries")
    return entries


POINTER_COVERED_FIELD = "pointer_covered"  # cluster key: ids of the nuggets pointer coverage withheld from synth


def pointer_covered_ids(clusters: List[dict], entries: List[dict]) -> Dict[str, List[object]]:
    """topicKey -> ids of the nuggets the pointer index covers, so synth never sees them.

    Nuggets carry a source file, not a section, so coverage is judged per path: a path is pointer-covered
    only when every entry of it is an unmarked `section` span. The pass indexes every section of every
    file, so any marked entry (durable, decision, ...) means the file holds material synth must read.
    A DECISION nugget is never covered: it owes a decision record or a PIPELINE.md SKIP reason.
    """
    indexed = {_posix_rel(e["path"]) for e in entries}
    marked = {_posix_rel(e["path"]) for e in entries if e["tag"] != "section"}
    covered = indexed - marked
    out: Dict[str, List[object]] = {}
    for c in clusters:
        ids = [n.get("id") for n in c["nuggets"]
               if n.get("type") != "DECISION" and _posix_rel(n.get("source", "")) in covered]
        if ids:
            out[c["topicKey"]] = ids
    return out


def split_by_pointer(clusters: List[dict], entries: List[dict]) -> Tuple[List[dict], int]:
    """Clusters reduced to the nuggets pointer_covered_ids leaves, each made per-nugget, and the covered count."""
    gone = pointer_covered_ids(clusters, entries)
    rest: List[dict] = []
    skipped = 0
    for c in clusters:
        out = set(gone.get(c["topicKey"], ()))
        keep = [n for n in c["nuggets"] if n.get("id") not in out]
        skipped += len(c["nuggets"]) - len(keep)
        if keep:
            rest.append({**c, "per_nugget": True, "nuggets": keep})
    return rest, skipped


def write_synth_batches(clusters: List[dict], repo: Path, out_dir: Path, pointer: Optional[dict] = None) -> dict:
    """Write synth inputs and return the synth block of prepared.json.

    "payloads" are the batch dicts inline (at most MAX_SYNTH_CALLS), the only input a synth call sees;
    "batches" are their files, kept for audit. Topics past the last batch land in "deferred_topics".
    A `pointer` dict rides in every payload and in the block as "pointer_index".
    """
    inputs = synth_inputs(clusters, repo)
    topic_files: Dict[str, str] = {}
    seen: Dict[str, int] = {}
    for item in inputs:
        key = item["topic_key"]
        seen[key] = seen.get(key, 0) + 1
        suffix = "" if seen[key] == 1 else f".part{seen[key]}"
        path = out_dir / "topics" / f"{slugify(key)}{suffix}.json"
        write_json(path, item)
        topic_files.setdefault(key, path.as_posix())
    cluster_bytes = {c["topicKey"]: len(json.dumps(c)) for c in clusters}
    owner = {n.get("id"): c["topicKey"] for c in clusters for n in c.get("nuggets") or []}
    weight: Dict[str, int] = {}
    for item in inputs:
        # A judge-only key (per_nugget batch) names no cluster; it draws on its nuggets' owners.
        owners = {item["topic_key"]} | {owner[n] for n in item.get("cite_ids", []) if n in owner}
        weight[item["topic_key"]] = max(weight.get(item["topic_key"], 0), sum(cluster_bytes.get(k, 0) for k in owners))
    packed = pack_synth_batches(inputs, weight=weight)
    kept, rest = packed[:MAX_SYNTH_CALLS], packed[MAX_SYNTH_CALLS:]
    payloads = [{"topics": batch, **({"pointer_index": pointer} if pointer else {})} for batch in kept]
    files = []
    for i, payload in enumerate(payloads, 1):
        path = out_dir / f"synth-batch-{i:02d}.json"
        write_json(path, payload)
        files.append(path.as_posix())
    sent = {i["topic_key"] for batch in kept for i in batch}
    deferred = sorted({i["topic_key"] for batch in rest for i in batch} - sent)
    # Judge keys (nugget-<batch>) name no cluster, so the coverage gate exempts deferred work by nugget id.
    deferred_ids = sorted({str(n) for batch in rest for i in batch if i["topic_key"] in deferred
                           for n in i.get("cite_ids", [])})
    block = {"batches": files, "payloads": payloads, "deferred_topics": deferred,
             "deferred_nugget_ids": deferred_ids, "topic_files": topic_files,
             "topics": len({i["topic_key"] for i in inputs}), "schema": SYNTH_SCHEMA,
             "schemas": [payload_schema(p) for p in payloads],
             "max_topic_tokens": max((estimate_tokens(i) for i in inputs), default=0)}
    if pointer:
        block["pointer_index"] = pointer
    return block


def _section_span(lines: List[str], heading: str) -> Optional[Tuple[int, int]]:
    """[start, end) of the section whose heading text matches, case-insensitively; end is the next heading of equal or higher level."""
    want = heading.strip().lstrip("#").strip().lower()
    for i, line in enumerate(lines):
        m = _HEADING.match(line)
        if m and m.group(2).strip().lower() == want:
            level = len(m.group(1))
            for j in range(i + 1, len(lines)):
                n = _HEADING.match(lines[j])
                if n and len(n.group(1)) <= level:
                    return i, j
            return i, len(lines)
    return None


def splice_ops(base: str, ops: List[dict], title: str) -> str:
    """Insert ops into a page: append to a named section, or create it; existing text is never removed.

    A missing page (empty base) starts from a scaffold H1 and nav line. Each op's cites land in a
    provenance comment after its markdown.
    """
    if not base.strip():
        base = f"# {title}\n\n[Directory guide](./DIRECTORY_GUIDE.md)\n"
    lines = base.rstrip("\n").split("\n")
    for op in ops:
        block = op["markdown"].strip("\n").split("\n") + [f"<!-- distilled: {', '.join(op['cites'])} -->"]
        span = _section_span(lines, op["section_heading"])
        if span is None:
            lines += ["", f"## {op['section_heading'].strip().lstrip('#').strip()}", ""] + block
            continue
        end = span[1]
        while end > span[0] + 1 and not lines[end - 1].strip():
            end -= 1
        lines[end:end] = [""] + block
        after = end + 1 + len(block)
        if after < len(lines) and lines[after].strip():
            lines.insert(after, "")
    return "\n".join(lines) + "\n"


def _reject_reason(op: object, nugget_ids: set, repo: Path) -> Optional[str]:
    """Mechanical citation check: why an op is refused, or None. Stands in for model reads of HEAD."""
    if not isinstance(op, dict) or not all(isinstance(op.get(k), str) and op[k].strip()
                                           for k in ("section_heading", "markdown")) \
            or op.get("action") not in ("append", "new_section"):
        return "malformed-op"
    cites = op.get("cites")
    if not isinstance(cites, list) or not cites or not all(isinstance(c, str) for c in cites):
        return "no-cite"
    unknown = [c for c in cites if c not in nugget_ids]
    if unknown:
        return f"unknown-cite: {unknown[0]}"
    for ref in _CODE_PATH.findall(op["markdown"]):
        try:
            if not inside(repo, ref).exists():
                return f"stale-path: {ref}"
        except DriverError:
            return f"stale-path: {ref}"
    return None


def _dr_reject_reason(dr: object, nugget_ids: set, repo: Path) -> Optional[str]:
    """Why a decision_record is refused, or None: same cite and stale-path checks as an op."""
    if not isinstance(dr, dict) or not all(isinstance(dr.get(k), str) and dr[k].strip() for k in ("title", "decision")) \
            or any(dr.get(k) is not None and not isinstance(dr[k], str) for k in _DR_TEXT_FIELDS):
        return "malformed-dr"
    cites = dr.get("cites")
    if not isinstance(cites, list) or not cites or not all(isinstance(c, str) for c in cites):
        return "no-cite"
    unknown = [c for c in [*cites, dr.get("nugget_id")] if c not in nugget_ids]
    if unknown:
        return f"unknown-cite: {unknown[0]}"
    return _reject_reason({"section_heading": "x", "action": "append", "cites": cites,
                           "markdown": "\n".join(dr.get(k) or "" for k in _DR_TEXT_FIELDS) or "x"},
                          nugget_ids, repo)


def _stamp_decision_head(head: str) -> str:
    """Frontmatter lines (without fences) of a scaffolded DR with a settled status and the EM as decider."""
    head = re.sub(r"^deciders:[^\n]*(?:\n[ \t]+-[^\n]*)*\n?", "", head, flags=re.M)
    head = re.sub(r"^status:[^\n]*\n?", "", head, flags=re.M)
    return head + f"status: accepted\ndeciders:\n  - {MINTED_DR_DECIDER}\n"


def mint_decision_record(dr: dict, run_id: str, repo: Path, doc_new: Optional[List[str]]) -> dict:
    """Scaffold one docs/decisions record through coordinator-doc-new, fill its sections, stamp provenance.

    The scaffolder allocates the DR number; with no scaffolder the record is refused, never numbered by guess.
    """
    if doc_new is None:
        return {"status": "rejected", "reason": "dr-allocator-unavailable"}
    proc = run_cmd([*doc_new, "--type", "decision", "--title", dr["title"].strip()], repo)
    lines = [l.strip() for l in proc.stdout.splitlines() if l.strip()]
    path = (Path(lines[-1]) if Path(lines[-1]).is_absolute() else repo / lines[-1]) if lines else None
    if proc.returncode != 0 or path is None or not path.is_file():
        return {"status": "rejected", "reason": f"dr-mint-failed: {proc.stderr.strip()[:200] or proc.returncode}"}
    text = path.read_text(encoding="utf-8")
    for head, field in (("Problem", "problem"), ("Decision", "decision"),
                        ("Alternatives Considered", "alternatives"), ("Implementation", "implementation")):
        body = (dr.get(field) or "").strip()
        if body:
            text = re.sub(rf"(^## {head}\n\n)<!--.*?-->", lambda m, b=body: m.group(1) + b, text, count=1,
                          flags=re.S | re.M)
    prov = f"provenance:\n  run_id: {run_id}\n  source_nuggets: {json.dumps(sorted(set(dr['cites'])))}\n"
    text = re.sub(r"\A(---\n.*?\n)(---\n)", lambda m: _stamp_decision_head(m.group(1)) + prov + m.group(2), text,
                  count=1, flags=re.S)
    text = re.sub(r"^(\|\s*Status\s*\|).*$", r"\1 Accepted |", text, count=1, flags=re.M | re.I)
    text = re.sub(r"^(\|\s*Deciders\s*\|).*$", rf"\1 {MINTED_DR_DECIDER} |", text, count=1, flags=re.M | re.I)
    path.write_text(text, encoding="utf-8")
    try:
        rel = path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        rel = path.as_posix()
    return {"status": "minted", "path": rel}


DR_MATCH_MIN_WORDS = 2
DR_MATCH_FRACTION = 0.75
_DR_STEM_PREFIX = re.compile(r"^(?:dr-)?[0-9a-z]*\d[0-9a-z]*-", re.I)


def _index_words(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 3}


def existing_dr_for(title: str, dr_index: object) -> Optional[dict]:
    """The drIndex record a decision_record title already has, or None: same slug, or a word match.

    A word match is DR_MATCH_MIN_WORDS shared words and DR_MATCH_FRACTION of the shorter side's words;
    the best score wins, ties go to the lower path. Title and file-name slug only, never bodies.
    """
    slug, words = slugify(title), _index_words(title)
    best: Optional[Tuple[int, str, dict]] = None
    for rec in dr_index if isinstance(dr_index, list) else []:
        if not isinstance(rec, dict) or not isinstance(rec.get("path"), str):
            continue
        stem = _DR_STEM_PREFIX.sub("", Path(rec["path"]).stem)
        rec_title = str(rec.get("title") or "")
        if slug and slug in (slugify(rec_title), slugify(stem)):
            score = 10 ** 6
        else:
            rec_words = _index_words(f"{rec_title} {stem}")
            shared = len(words & rec_words)
            floor = max(DR_MATCH_MIN_WORDS, DR_MATCH_FRACTION * min(len(words), len(rec_words)))
            score = shared if shared >= floor else 0
        if score and (best is None or (-score, rec["path"]) < (-best[0], best[1])):
            best = (score, rec["path"], rec)
    return best[2] if best else None


_DR_LED_SLUG = re.compile(r"dr-[0-9a-z]+(-|$)")


def _minted_page(title: str, placeholder: str, wiki_slugs: Dict[str, str], repo: Path) -> Optional[dict]:
    """The page a per-nugget topic lands on, named only by synth's page_title; None when no content title names one.

    A title whose slug is an existing wiki page lands there (homed). A title holding a path separator
    or led by a DR id, or one that slugifies to nothing, names no page.
    """
    slug = slugify(title)
    if not slug or re.search(r"[\\/]", title) or _DR_LED_SLUG.match(slug):
        return None
    if slug in wiki_slugs:
        return {"target": wiki_slugs[slug], "slug": slug, "homed": True, "title": title}
    target = f"{placeholder.rsplit('/', 1)[0]}/{slug}.md"
    return {"target": target, "slug": slug, "homed": inside(repo, target).is_file(), "title": title}


def apply_synth(results: List[object], prepared: dict, repo: Path, out_dir: Path, run_id: str = "",
                doc_new: Optional[List[str]] = None, mint: bool = True) -> Tuple[List[dict], dict]:
    """Splice synth output into staged page copies and mint decision_records; returns (manifest rows, report).

    Ops and records with a missing or unknown cite, or a backticked repo path absent at HEAD, are
    rejected and listed; the rest land. A topic with a rejected op mints no decision_record
    (each is listed rejected as topic-has-rejected-op). A record whose title matches a prepared drIndex record
    (existing_dr_for) is not minted: it is listed under "dr_exists" and its cited nuggets read
    DR-EXISTS. A topic with no landed op or record is reported under
    "unsynthesized"; the ones the synth named with nothing landing are also "no_ops_topics". Topic keys
    join by slug. "no_ops_reasons" maps each sent topic with nothing landing to its no_ops_reason, or
    "dropped" (never named) / "unreasoned"; "coverage" counts sent-topic nuggets cited ("covered"), judged and
    assigned. A nugget a minted record cites stays CREATE_DR when an op cites it too. "dispositions" gives each
    nugget ADD_SECTION or CREATE_DR when a landed op or minted record cites it; else JUDGED:<reason> when a
    valid nugget_reasons entry, or its topic's no_ops_reason when nothing landed there, names it; else uncited.
    An invalid nugget_reasons entry is listed under "nugget_reasons_rejected". One carrying a valid
    home_suggestion {wiki_path, kind} reads JUDGED:home-suggested and is listed under "home_suggestions"; no page
    is written for it. A judge-only topic (nugget-<scan batch id>, covering that batch's per_nugget nuggets) splices
    and mints nothing: its ops and records are rejected. A per_nugget topic splices only
    onto the page its page_title names (_minted_page), never its topic key; without a usable title its ops are
    rejected as per-nugget-no-content-title. With mint False records are listed as would-mint.
    """
    topics = {c["topicKey"]: c for c in prepared.get("clusters", [])}
    members: Dict[str, List[str]] = {}
    for k, c in topics.items():
        if c.get("per_nugget"):
            record_ids = {n.get("id") for n in record_nuggets(c)}
            for n in c["nuggets"]:
                if n.get("id") not in record_ids:
                    members.setdefault(judge_topic_key(n.get("id")), []).append(k)
    judge_keys = {k for k in members if k not in topics}
    by_slug = {slugify(k): k for k in reversed(list(topics))}
    for k in sorted(judge_keys):
        by_slug.setdefault(slugify(k), k)
    ops_by_topic: Dict[str, List[dict]] = {}
    drs_by_topic: Dict[str, List[dict]] = {}
    rejected: List[dict] = []
    named: set = set()
    claimed: Dict[str, str] = {}
    judged: Dict[str, str] = {}
    homes: Dict[str, dict] = {}
    titles: Dict[str, str] = {}
    bad_nugget_reasons: List[dict] = []
    for res in results:
        for t in (res.get("topics") if isinstance(res, dict) else None) or []:
            echoed = t.get("topic_key") if isinstance(t, dict) else None
            key = by_slug.get(slugify(echoed)) if isinstance(echoed, str) else None
            if key is None:
                rejected.append({"topic_key": echoed, "reason": "unknown-topic"})
                continue
            judge = key in judge_keys
            scope = list(dict.fromkeys(members[key])) if judge else [key]
            named.update(scope)
            if t.get("no_ops_reason") in NO_OPS_REASONS:
                for k in scope:
                    claimed.setdefault(k, t["no_ops_reason"])
            ids = {n.get("id") for k in scope for n in topics[k]["nuggets"]}
            if judge:
                ids -= {n.get("id") for k in scope for n in record_nuggets(topics[k])}
            if isinstance(t.get("page_title"), str) and not judge:
                titles.setdefault(key, t["page_title"].strip())
            for nr in t.get("nugget_reasons") or []:
                if not (isinstance(nr, dict) and nr.get("nugget_id") in ids and nr.get("reason") in NO_OPS_REASONS
                        and ("home_suggestion" not in nr or _valid_home_suggestion(nr["home_suggestion"]))):
                    bad_nugget_reasons.append({"topic_key": key, "entry": nr})
                elif "home_suggestion" in nr:
                    hs = nr["home_suggestion"]
                    judged[nr["nugget_id"]] = DISPOSITION_HOME_SUGGESTED
                    homes.setdefault(nr["nugget_id"], {"nugget_id": nr["nugget_id"], "wiki_path": hs["wiki_path"].strip(),
                                                       "kind": hs["kind"]})
                else:
                    judged.setdefault(nr["nugget_id"], nr["reason"])
            for op in t.get("ops") or []:
                why = "judge-only-topic-has-ops" if judge else _reject_reason(op, ids, repo)
                if why:
                    rejected.append({"topic_key": key, "reason": why})
                else:
                    ops_by_topic.setdefault(key, []).append(op)
            for dr in t.get("decision_records") or []:
                why = "judge-only-topic-has-ops" if judge else _dr_reject_reason(dr, ids, repo)
                if why:
                    rejected.append({"topic_key": key, "reason": why, "decision_record": True})
                else:
                    drs_by_topic.setdefault(key, []).append(dr)
    minted: List[dict] = []
    dr_exists: List[dict] = []
    existing_by_nugget: Dict[str, dict] = {}
    covered: Dict[str, str] = {}
    minted_ids: set = set()
    op_rejected = {r["topic_key"] for r in rejected if not r.get("decision_record")}
    for key in sorted(drs_by_topic):
        for dr in drs_by_topic[key]:
            if key in op_rejected:
                rejected.append({"topic_key": key, "reason": "topic-has-rejected-op", "decision_record": True})
                continue
            if dr["nugget_id"] in minted_ids:
                rejected.append({"topic_key": key, "reason": f"duplicate-dr: {dr['nugget_id']}", "decision_record": True})
                continue
            existing = existing_dr_for(dr["title"], prepared.get("drIndex"))
            if existing:
                minted_ids.add(dr["nugget_id"])
                dr_exists.append({"topic_key": key, "nugget_id": dr["nugget_id"], "title": dr["title"],
                                  "existing_path": existing["path"], "existing_id": existing.get("id")})
                for c in dr["cites"]:
                    covered[c] = "DR-EXISTS"
                    existing_by_nugget[c] = existing
                continue
            got = {"status": "would-mint"} if not mint else mint_decision_record(dr, run_id, repo, doc_new)
            if got["status"] == "rejected":
                rejected.append({"topic_key": key, "reason": got["reason"], "decision_record": True})
                continue
            minted_ids.add(dr["nugget_id"])
            minted.append({"topic_key": key, "nugget_id": dr["nugget_id"], "title": dr["title"], **got})
            for c in dr["cites"]:
                covered[c] = "CREATE_DR"
    pages: Dict[str, dict] = {}
    for key in sorted(ops_by_topic):
        c = topics[key]
        if c.get("per_nugget"):
            page = _minted_page(titles.get(key, ""), c["wikiPath"], prepared.get("wikiSlugs") or {}, repo)
            if page is None:
                rejected.append({"topic_key": key, "reason": "per-nugget-no-content-title"})
                ops_by_topic.pop(key)
                continue
        else:
            page = {"target": c["wikiPath"], "slug": c["slug"], "homed": bool(c.get("homed")),
                    "title": key.replace("-", " ").title()}
        entry = pages.setdefault(page["target"], {**page, "topic_key": key, "ops": []})
        entry["ops"] += ops_by_topic[key]
    for key in ops_by_topic:
        for op in ops_by_topic[key]:
            for c in op["cites"]:
                covered.setdefault(c, "ADD_SECTION")
    rows = []
    for entry in pages.values():
        target = inside(repo, entry["target"])
        base = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
        staged = out_dir / "staged" / f"{entry['slug']}.md"
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_text(splice_ops(base, entry["ops"], entry["title"]), encoding="utf-8")
        rows.append({"staged": staged.relative_to(repo).as_posix(), "target": entry["target"],
                     "topic_key": entry["topic_key"], "homed": entry["homed"]})
    landed = set(ops_by_topic) | {m["topic_key"] for m in minted} | {m["topic_key"] for m in dr_exists}
    dispositions = []
    for key in sorted(topics):
        for n in topics[key]["nuggets"]:
            nid = n.get("id")
            row = {"topic_key": key, "nugget_id": nid, "disposition": covered.get(nid, DISPOSITION_UNCITED)}
            if row["disposition"] == "DR-EXISTS":
                row["existing"] = existing_by_nugget[nid]["path"]
                row["reason"] = f"DR-EXISTS {row['existing']}"
            elif row["disposition"] == DISPOSITION_UNCITED:
                why = judged.get(nid) or (claimed.get(key) if key in named and key not in landed else None)
                if why:
                    row["disposition"] = f"{DISPOSITION_JUDGED}{why}"
                    row["reason"] = why
            dispositions.append(row)
    payloads = (prepared.get("synth") or {}).get("payloads")
    sent = {m for p in payloads for t in p.get("topics", []) if slugify(t["topic_key"]) in by_slug
            for m in (members[by_slug[slugify(t["topic_key"])]] if by_slug[slugify(t["topic_key"])] in judge_keys
                      else [by_slug[slugify(t["topic_key"])]])} if payloads else set(topics)
    no_ops_reasons = {k: claimed.get(k, NO_OPS_UNREASONED) if k in named else NO_OPS_DROPPED
                      for k in sorted(sent - landed)}
    assigned = [d for d in dispositions if d["topic_key"] in sent]
    return rows, {"spliced": sorted(ops_by_topic), "rejected": rejected, "decision_records": minted,
                  "dr_exists": dr_exists,
                  "unsynthesized": sorted(set(topics) - landed),
                  "no_ops_topics": sorted(named - landed),
                  "no_ops_reasons": no_ops_reasons,
                  "coverage": {"covered": sum(_is_cited(d["disposition"]) for d in assigned),
                               "judged": sum(d["disposition"].startswith(DISPOSITION_JUDGED) for d in assigned),
                               "assigned": len(assigned)},
                  "nugget_reasons_rejected": bad_nugget_reasons,
                  "home_suggestions": [homes[d["nugget_id"]] for d in dispositions
                                       if d["disposition"] == f"{DISPOSITION_JUDGED}{DISPOSITION_HOME_SUGGESTED}"],
                  "dispositions": dispositions}


DR_INDEX_DIR = "docs/decisions"
DR_INDEX_PER_NUGGET = 5
DR_INDEX_MAX = 80
DR_INDEX_TITLE_CHARS = 120
_DR_ID_REF = re.compile(r"\bDR-[0-9A-Za-z][\w\-]*", re.I)


def dr_title_index(clusters: List[dict], repo: Path) -> List[dict]:
    """Existing decision records that may already hold a DECISION nugget of this run: [{"path", "id", "title"}].

    Per DECISION nugget the DR_INDEX_PER_NUGGET records whose title or file name share the most
    words with it (two at least), plus any record the nugget names by id; at most DR_INDEX_MAX in
    all. Titles only, never bodies: the phase-3b agent has no tool to list docs/decisions/.
    """
    decisions = [n for c in clusters for n in c["nuggets"] if n.get("type") == "DECISION"]
    root = repo / DR_INDEX_DIR
    if not decisions or not root.is_dir():
        return []
    records = []
    for path in sorted(root.glob("*.md")):
        with path.open(encoding="utf-8", errors="replace") as fh:
            fm, _ = _split_frontmatter(fh.read(4096))
        title = (fm.get("title") or path.stem).strip().strip("\"'")
        rid = (fm.get("id") or path.stem).strip().strip("\"'")
        records.append({"path": f"{DR_INDEX_DIR}/{path.name}", "id": rid, "title": title[:DR_INDEX_TITLE_CHARS],
                        "words": _index_words(f"{title} {path.stem}")})
    picked: Dict[str, dict] = {}
    for n in decisions:
        text = f"{n.get('content', '')} {n.get('system_tag', '')}"
        words = _index_words(text)
        named = {m.lower() for m in _DR_ID_REF.findall(text)}
        for r in records:
            if r["id"].lower() in named or any(r["path"].rsplit("/", 1)[-1].lower().startswith(x + "-") for x in named):
                picked.setdefault(r["path"], r)
        scored = sorted(((len(words & r["words"]), r["path"], r) for r in records), key=lambda t: (-t[0], t[1]))
        for score, _, r in scored[:DR_INDEX_PER_NUGGET]:
            if score >= 2:
                picked.setdefault(r["path"], r)
    return [{k: v for k, v in r.items() if k != "words"} for r in list(picked.values())[:DR_INDEX_MAX]]


# --------------------------------------------------------------------------- judgment precheck

DEFAULT_MIN_CONVERGENCE = 3
SIDECAR_ROOTS = (".coordinator-local/subagent-share", ".coordinator-local/plan-sidecars", "docs/plans", "archive/specs")
JUDGMENT_DIR = "docs/wiki/codebase-judgment"
INELIGIBLE_STATUSES = {"em-rejected", "suspended"}
_SIDECAR_HEAD_CHARS = 16000
_LEDGER_FENCE = re.compile(r"^##\s+Findings Ledger\s*$.*?^```json[ \t]*\r?\n(.*?)^```", re.S | re.M)


def _plan_stem(ref: str) -> str:
    return Path(str(ref).replace("\\", "/")).stem


def _ledger_has_eligible_row(text: str) -> bool:
    """True unless the sidecar's ledger parses to rows that are all rejected or suspended (or empty).
    An absent or unparseable ledger stays eligible: only the dispatched agent can read past it."""
    m = _LEDGER_FENCE.search(text)
    if not m:
        return True
    try:
        rows = json.loads(m.group(1))
    except ValueError:
        return True
    if not isinstance(rows, list):
        return True
    return any(not (isinstance(r, dict) and r.get("status") in INELIGIBLE_STATUSES) for r in rows)


def judgment_precheck(repo: Path, batches: List[dict], min_convergence: object = None) -> dict:
    """Mechanical Phase 2.5 gate. Counts the distinct batch-named plans that a `findings_ledger:`
    sidecar joins (via `target_plan:`/`plan:` filename stem) with at least one non-rejected,
    non-suspended ledger row, and lists the existing judgment entries. `dispatch` is True when that
    count reaches the threshold, or when an existing entry has at least one eligible plan to
    increment it. The result is an upper bound: claim-topic grouping and mechanical-finding
    exclusion stay with the agents it admits."""
    threshold = min_convergence if isinstance(min_convergence, int) and not isinstance(min_convergence, bool) \
        and min_convergence > 0 else DEFAULT_MIN_CONVERGENCE
    batch_stems = {_plan_stem(f) for b in batches or [] if isinstance(b, dict)
                   for f in b.get("files") or [] if isinstance(f, str)}
    sidecars_seen = 0
    eligible: set = set()
    for root in SIDECAR_ROOTS:
        base = repo / root
        if not base.is_dir():
            continue
        for dirpath, _dirs, names in os.walk(base):
            for name in names:
                if not name.endswith(".md"):
                    continue
                path = Path(dirpath) / name
                try:
                    with path.open("r", encoding="utf-8", errors="replace") as fh:
                        head = fh.read(_SIDECAR_HEAD_CHARS)
                    fm, _ = _split_frontmatter(head)
                    if "findings_ledger" not in fm and not re.search(r"^findings_ledger:", head, re.M):
                        continue
                    sidecars_seen += 1
                    ref = fm.get("target_plan") or fm.get("plan")
                    if not ref or _plan_stem(ref) not in batch_stems:
                        continue
                    if _ledger_has_eligible_row(path.read_text(encoding="utf-8", errors="replace")):
                        eligible.add(_plan_stem(ref))
                except OSError:
                    continue
    jdir = repo / JUDGMENT_DIR
    entries = sorted(p.relative_to(repo).as_posix() for p in jdir.glob("*.md")) if jdir.is_dir() else []
    distinct = len(eligible)
    return {"sidecars_seen": sidecars_seen, "distinct_eligible_plans": distinct,
            "eligible_plans": sorted(eligible), "existing_judgment_entries": entries,
            "min_convergence": threshold,
            "dispatch": distinct >= threshold or (bool(entries) and distinct >= 1)}


# --------------------------------------------------------------------------- prepare

def prepare(repo: Path, input_file: Path, nuggets_file: Optional[Path], verdicts_file: Optional[Path],
            run_id: Optional[str], out_dir: Optional[Path], store: str,
            pointer_index: Optional[Path] = None) -> dict:
    timings: Dict[str, float] = {}
    pointer_entries = load_pointer_index(pointer_index) if pointer_index else None
    t = time.perf_counter()
    loaded = load_input(input_file)
    timings["load"] = time.perf_counter() - t
    run_id = check_run_id(run_id or loaded.get("runId") or new_run_id())
    out_dir = out_dir or repo / SCRATCH_ROOT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    nuggets: List[dict] = []
    if nuggets_file:
        raw = read_json(nuggets_file)
        nuggets = raw.get("nuggets") if isinstance(raw, dict) else raw
        if not isinstance(nuggets, list):
            raise DriverError("unusable-input", "nuggets file must hold a list or {nuggets: [...]}")
    verdicts = read_json(verdicts_file) if verdicts_file else None
    curated = verdicts if (isinstance(verdicts, dict) and isinstance(verdicts.get("verdicts"), list)
                           and isinstance(verdicts.get("counts"), dict)) else None

    t = time.perf_counter()
    read_files: List[str] = []
    file_fates: List[dict] = []
    lifted = lift_batches(repo, loaded["batches"], loaded["wikiSlugs"], read_files, file_fates)
    nuggets = nuggets + lifted
    vmap = _verdict_map(verdicts)
    if vmap is not None:
        for n in lifted:
            vmap.setdefault(n["system_tag"], {"verdict": "keep"})
        verdicts = vmap
    timings["lift"] = time.perf_counter() - t

    t = time.perf_counter()
    clusters, dropped = cluster_nuggets(nuggets, loaded["wikiSlugs"], loaded.get("wikiDirs") or ["docs/wiki"], verdicts)
    timings["cluster"] = time.perf_counter() - t

    t = time.perf_counter()
    hashes = source_hashes(clusters, repo, out_dir, store)
    timings["source-hash"] = time.perf_counter() - t
    unchanged = sorted(k for k, v in hashes.items() if v.get("unchanged") is True)

    t = time.perf_counter()
    cands, cand_status = candidates([c for c in clusters if c["topicKey"] not in unchanged], repo, out_dir)
    timings["candidates"] = time.perf_counter() - t

    t = time.perf_counter()
    synth_clusters = [c for c in clusters if c["topicKey"] not in unchanged]
    pointer = None
    if pointer_entries is not None:
        withheld = pointer_covered_ids(synth_clusters, pointer_entries)
        synth_clusters, skipped = split_by_pointer(synth_clusters, pointer_entries)
        judged = {c["topicKey"] for c in synth_clusters}
        clusters = [{**c, **({"per_nugget": True} if c["topicKey"] in judged else {}),
                     **({POINTER_COVERED_FIELD: withheld[c["topicKey"]]} if c["topicKey"] in withheld else {})}
                    for c in clusters]
        try:
            shown = pointer_index.resolve().relative_to(repo).as_posix()
        except ValueError:
            shown = pointer_index.resolve().as_posix()
        pointer = {"path": shown, "entries": len(pointer_entries), "covered_nuggets": skipped,
                   "instruction": f"The sections of the pointer index at {shown} are covered by pointer and are not in "
                                  "this payload. Write a short synthesis that links to the index; never restate its entries."}
    synth = write_synth_batches(synth_clusters, repo, out_dir, pointer)
    timings["synth-inputs"] = time.perf_counter() - t

    t = time.perf_counter()
    precheck = judgment_precheck(repo, loaded["batches"], loaded.get("minConvergence"))
    timings["judgment-precheck"] = time.perf_counter() - t

    prepared = {
        **loaded,
        "judgmentPrecheck": precheck,
        "synth": synth,
        "runId": run_id,
        "repoRoot": loaded.get("repoRoot") or str(repo),
        "clusters": clusters,
        "dropped_nuggets": [n.get("id") for n in dropped],
        "lifted_nuggets": len(lifted),
        "sourceHashes": hashes,
        "unchangedTopics": unchanged,
        "candidates": cands,
        "candidates_status": cand_status,
        "classifiedFiles": list(dict.fromkeys(read_files)),
        "drIndex": dr_title_index(clusters, repo),
        "file_fates": file_fates,
        "requiredAgentTypes": sorted({DISTILL_WRITER_TYPE, *([SYNTH_AGENT_TYPE] if synth["payloads"] else [])}),
        "agent_spawns": 0,
        "timings": {k: round(v, 4) for k, v in timings.items()},
    }
    if curated is not None:
        # Leg 2 checks each curated list against a count beside it; the op's return carries none.
        curated = {**curated, **{f"{k[:-1]}Count": len(curated[k])
                                 for k in ("judgmentClusters", "contradictionClusters")
                                 if isinstance(curated.get(k), list)}}
        prepared["curated"] = curated
    for stale in [*out_dir.glob("prepared-[0-9][0-9].json"), out_dir / SHARDS_INDEX]:
        stale.unlink(missing_ok=True)
    write_prepared(out_dir / "prepared.json", prepared)
    launch = launch_bytes(out_dir / "prepared.json", HARVEST_SCRIPT)
    budget = LAUNCH_CAP_BYTES - LAUNCH_MARGIN_BYTES
    report = {"status": "ok", "run_id": run_id,
              "clusters": len(clusters), "unchanged": len(unchanged), "agent_spawns": 0,
              "judgmentPrecheck": precheck,
              "timings": prepared["timings"]}
    if launch <= budget:
        return {**report, "prepared": (out_dir / "prepared.json").as_posix()}
    script_bytes = HARVEST_SCRIPT.stat().st_size
    entries = []
    for shard in shard_prepared(prepared, script_bytes, budget):
        path = out_dir / f"prepared-{shard[SHARD_KEY]['index']:02d}.json"
        write_prepared(path, shard)
        entries.append({"path": path.as_posix(), "index": shard[SHARD_KEY]["index"],
                        "launch_bytes": launch_bytes(path, HARVEST_SCRIPT),
                        "payloads": len(shard["synth"]["payloads"]),
                        "topics": sorted({k for p in shard["synth"]["payloads"] for k in _payload_keys(p)})})
    over = [e for e in entries if e["launch_bytes"] > budget]
    if over:
        for e in entries:
            Path(e["path"]).unlink(missing_ok=True)
        raise DriverError("launch-over-cap", f"shard {over[0]['path']} is {over[0]['launch_bytes']} bytes, over the "
                                             f"{budget}-byte budget ({LAUNCH_CAP_BYTES} cap less a "
                                             f"{LAUNCH_MARGIN_BYTES}-byte margin); the Workflow tool refuses the launch")
    (out_dir / "prepared.json").unlink()
    write_json(out_dir / SHARDS_INDEX, {"run_id": run_id, "budget": budget, "script_bytes": script_bytes,
                                        "shards": entries})
    return {**report, "shards": entries, "shards_index": (out_dir / SHARDS_INDEX).as_posix()}


# --------------------------------------------------------------------------- finalize

def _h1(text: str) -> str:
    m = _H1.search(text)
    return m.group(1).strip().lower() if m else ""


def collision_check(rows: List[dict], repo: Path, store_path: Path) -> List[dict]:
    """Targets a promote would clobber: a page that exists but this pipeline never wrote.

    A homed row (merge into an existing guide) may replace it only while the H1 survives; a
    non-homed row never may. Defends A-DISTILL-HARVEST-CAN-OVERWRITE-A-LIVE-CONTRACT-PAGE.
    """
    try:
        store = json.loads(store_path.read_text(encoding="utf-8")) if store_path.is_file() else {}
    except (OSError, ValueError):
        store = {}
    found = []
    for row in rows:
        target = inside(repo, row["target"])
        if not target.is_file():
            continue
        slug = slugify(row.get("topic_key", ""))
        homed = row.get("homed")
        if homed is None:
            homed = slug in store
        if not homed:
            found.append({"target": row["target"], "reason": "exists-and-not-homed"})
            continue
        staged = Path(row["staged"])
        staged = staged if staged.is_absolute() else repo / staged
        old = _h1(target.read_text(encoding="utf-8", errors="replace"))
        new = _h1(staged.read_text(encoding="utf-8", errors="replace")) if staged.is_file() else ""
        if old and old != new:
            found.append({"target": row["target"], "reason": "h1-changed"})
    return found


def archive_moves(rows: List[dict], repo: Path, dry_run: bool) -> List[dict]:
    """Plain renames into archive/; each row reports moved, skipped-missing or skipped-exists."""
    out = []
    for row in rows:
        src, dst = inside(repo, row["src"]), inside(repo, row["dst"])
        if not str(row["dst"]).replace("\\", "/").startswith("archive/"):
            raise DriverError("archive-dst-outside-archive", f"{row['dst']!r} is not under archive/")
        if not src.is_file():
            out.append({**row, "action": "skipped-missing"})
        elif dst.exists():
            out.append({**row, "action": "skipped-exists"})
        elif dry_run:
            out.append({**row, "action": "would-move"})
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.replace(src, dst)
            out.append({**row, "action": "moved"})
    return out


def _resolve_bin(bin_name: str, override: Optional[str]) -> Optional[List[str]]:
    """argv for a settings-home CLI: the override, else PATH, else <settings-home>/bin; None when absent."""
    if override:
        return [sys.executable, override] if override.endswith(".py") else [override]
    found = shutil.which(bin_name)
    if found:
        return [found]
    home = os.environ.get("COORDINATOR_SETTINGS_HOME") or str(Path.home() / ".coordinator-claude-settings")
    for name in (bin_name, bin_name + ".exe", bin_name + ".cmd"):
        cand = Path(home) / "bin" / name
        if cand.is_file():
            return [str(cand)]
    return None


def resolve_invoke(override: Optional[str]) -> Optional[List[str]]:
    return _resolve_bin(INVOKE_NAME, override)


def _jsonl(stdout: str) -> List[dict]:
    """Rows of a coordinator-invoke reply: result.records of a JSON-RPC envelope, else one JSON object per line."""
    try:
        whole = json.loads(stdout)
    except ValueError:
        whole = None
    if isinstance(whole, dict):
        result = whole.get("result")
        records = result.get("records") if isinstance(result, dict) else whole.get("records")
        if isinstance(records, list):
            return [r for r in records if isinstance(r, dict)]
        return [whole]
    rows = []
    for line in stdout.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _envelope_status(stdout: str) -> Tuple[int, str]:
    """(result.exit_code, result.error) of a JSON-RPC envelope reply; (0, "") when the reply is not one."""
    try:
        whole = json.loads(stdout)
    except ValueError:
        return 0, ""
    result = whole.get("result") if isinstance(whole, dict) else None
    if not isinstance(result, dict):
        return 0, ""
    code = result.get("exit_code")
    return (code if isinstance(code, int) and not isinstance(code, bool) else 0), str(result.get("error") or "")


_TRACKED_CHECK_CHUNK = 100


def _planned_deletions(rows: List[dict]) -> List[str]:
    """Paths the dry run plans to delete: every non-summary row naming a path whose action is absent or a delete."""
    return [r["path"] for r in rows
            if not r.get("summary") and isinstance(r.get("path"), str) and r["path"]
            and "delete" in str(r.get("action", "delete"))]


def _tracked_among(repo: Path, paths: List[str]) -> List[str]:
    """Git-tracked files under the given paths (a directory path yields its tracked files); raises on any git failure."""
    tracked: List[str] = []
    for i in range(0, len(paths), _TRACKED_CHECK_CHUNK):
        chunk = paths[i:i + _TRACKED_CHECK_CHUNK]
        proc = run_cmd(["git", "--literal-pathspecs", "ls-files", "-z", "--", *chunk], repo)
        if proc.returncode != 0:
            raise OSError(f"git ls-files exited {proc.returncode}: {proc.stderr.strip()[:200]}")
        tracked.extend(p for p in proc.stdout.split("\0") if p)
    return sorted(set(tracked))


def scratch_drop(repo: Path, invoke: Optional[List[str]], dry_run: bool) -> dict:
    """fleet.scratch_hygiene cadence distill: dry run first, apply only with hold_pending_marker and only when
    no planned deletion is git-tracked; an unanswerable tracked check refuses the apply too."""
    if invoke is None:
        return {"status": "unavailable", "detail": "coordinator-invoke not found"}

    def call(apply: bool) -> Tuple[int, List[dict], str]:
        params = json.dumps({"repo_root": str(repo), "cadence": "distill", "apply": apply})
        try:
            proc = run_cmd([*invoke, "fleet.scratch_hygiene", params], repo)
        except (subprocess.SubprocessError, OSError) as exc:
            return 1, [], f"{type(exc).__name__}: {exc}"[:300]
        # The op fails in-band: process exit 0 with result.exit_code != 0 and result.error set.
        in_band_rc, in_band_err = _envelope_status(proc.stdout)
        return (proc.returncode or in_band_rc, _jsonl(proc.stdout),
                (in_band_err or proc.stderr.strip())[:300])

    rc, rows, err = call(False)
    summary = next((r for r in rows if r.get("summary")), None)
    if summary is None:
        return {"status": "error", "exit": rc, "detail": err or "no summary row"}
    caps = summary.get("capabilities") or []
    if dry_run or "hold_pending_marker" not in caps:
        return {"status": "planned", "applied": False, "summary": summary,
                "reason": "dry-run" if dry_run else "hold_pending_marker absent"}
    planned = _planned_deletions(rows)
    if planned:
        try:
            tracked = _tracked_among(repo, planned)
        except (subprocess.SubprocessError, OSError) as exc:
            return {"status": "refused", "applied": False, "summary": summary, "reason": "tracked-check-failed",
                    "detail": f"{type(exc).__name__}: {exc}"[:300]}
        if tracked:
            return {"status": "refused", "applied": False, "summary": summary, "reason": "tracked-planned-deletion",
                    "tracked": tracked, "detail": f"{len(tracked)} git-tracked file(s) in the planned deletions"}
    rc, rows, err = call(True)
    summary = next((r for r in rows if r.get("summary")), summary)
    if rc != 0:
        return {"status": "error", "applied": False, "exit": rc, "summary": summary,
                "detail": err or "apply exited non-zero"}
    return {"status": "applied", "applied": True, "exit": rc, "summary": summary}


def _summary_line(staged_text: str) -> str:
    # Provenance frontmatter precedes the body on every harvested page; its keys are not a summary.
    lines = staged_text.splitlines()
    if lines and lines[0].strip() == "---":
        end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "---"), None)
        lines = lines[end + 1:] if end is not None else lines
    for line in lines:
        s = line.strip()
        if s and not s.startswith(("#", "---", "<!--", "|", "```")):
            return s[:160].replace("|", "/")
    return "(no summary)"


def index_regen(new_targets: List[Tuple[str, str]], repo: Path, wiki_dirs: List[str], dry_run: bool) -> List[dict]:
    """Add a DIRECTORY_GUIDE row for each newly minted guide; present rows are never rewritten."""
    out = []
    for target_rel, text in new_targets:
        wiki_dir = next((d for d in wiki_dirs if target_rel.startswith(d.rstrip("/") + "/")), None)
        if wiki_dir is None:
            out.append({"target": target_rel, "action": "skipped-not-in-wiki"})
            continue
        guide = repo / wiki_dir / "DIRECTORY_GUIDE.md"
        if not guide.is_file():
            out.append({"target": target_rel, "action": "skipped-no-guide"})
            continue
        rel = target_rel[len(wiki_dir.rstrip("/")) + 1:]
        lines = guide.read_text(encoding="utf-8").splitlines(keepends=True)
        rows = [(i, m) for i, l in enumerate(lines) if (m := _GUIDE_ROW.match(l))]
        stem = Path(rel).stem
        if any(Path(m.group(2).replace("./", "", 1)).as_posix() == rel for _, m in rows):
            out.append({"target": target_rel, "action": "present"})
            continue
        new_row = f"| [{stem}](./{rel}) | {stem} | {_summary_line(text)} |\n"
        before = next((i for i, m in rows if Path(m.group(2)).stem.lower() > stem.lower()), None)
        # A header-only table (fresh guide) has no rows to anchor on; insert under its separator.
        sep = next((i + 1 for i, l in enumerate(lines) if _GUIDE_SEP.match(l)), None)
        at = before if before is not None else (rows[-1][0] + 1 if rows else sep)
        if at is None:
            out.append({"target": target_rel, "action": "skipped-no-table"})
            continue
        if not dry_run:
            lines.insert(at, new_row)
            guide.write_text("".join(lines), encoding="utf-8")
        out.append({"target": target_rel, "action": "would-add" if dry_run else "added"})
    return out


def write_leg2_inputs(repo: Path, out_dir: Path, promoted: object, splice_report: object) -> dict:
    """Write promoted.json and splice-report.json beside the run's other scratch for the leg-2 launch op.

    Returns their paths, repo-relative when out_dir is inside the repo. The launch args file itself is the engine op's.
    """
    paths = {}
    for key, name, payload in (("promoted_path", "promoted.json", promoted),
                               ("splice_report_path", "splice-report.json", splice_report)):
        write_json(out_dir / name, payload)
        try:
            paths[key] = (out_dir / name).resolve().relative_to(repo.resolve()).as_posix()
        except ValueError:
            paths[key] = (out_dir / name).resolve().as_posix()
    return paths


WATERMARK_KIND = "distill"
_ENGINE_ROOT_MODULE = Path(__file__).resolve().parents[2] / "hooks" / "scripts" / "_engine_root.py"


def _load_run_watermark() -> types.ModuleType:
    """The engine's coordinator_core.run_watermark, imported through the resolved engine root.

    Raises DriverError("engine-unresolved") when no engine root answers; never vendors the module.
    """
    import importlib
    import importlib.util
    spec = importlib.util.spec_from_file_location("_distill_engine_root", _ENGINE_ROOT_MODULE)
    seam = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seam)
    root = seam.resolve_claude_klabauter_root()
    if not root:
        raise DriverError("engine-unresolved", "no stamped engine root answers; fetch claude-klabauter")
    seam.place_engine_root_on_path(root)
    return importlib.import_module("coordinator_core.run_watermark")


def promote_watermark(repo: Path, run_id: str) -> dict:
    """Advance the distill run watermark staged under the run dir; the outcome is data, never a raise."""
    try:
        wm = _load_run_watermark()
        promoted = wm.promote(repo, repo / SCRATCH_ROOT / run_id, WATERMARK_KIND)
    except DriverError as exc:
        return {"status": "unresolved", "code": exc.code, "detail": exc.detail}
    except Exception as exc:  # noqa: BLE001 -- any engine import or promote failure is reported, not fatal
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:300]}
    if promoted is None:
        return {"status": "no-pending"}
    return {"status": "promoted", "path": Path(promoted).as_posix()}


def finalize(repo: Path, manifest_file: Union[Path, List[Path]], run_id: Optional[str], out_dir: Optional[Path],
             store: str, dry_run: bool, no_archive: bool, no_scratch: bool, invoke_bin: Optional[str],
             doc_new_bin: Optional[str] = None) -> dict:
    """Promote one run. `manifest_file` is one promote manifest, or one per shard of a sharded prepare: the
    shard manifests merge against <out-dir>/shards.json into <out-dir>/merged-manifest.json, which the run
    then treats as its one manifest. A lone manifest stamped as one shard of several is refused."""
    paths = manifest_file if isinstance(manifest_file, list) else [manifest_file]
    loaded = [read_json(p) for p in paths]
    if not all(isinstance(m, dict) for m in loaded):
        raise DriverError("unusable-input", "manifest must be an object")
    stamp = loaded[0].get("shard")
    stamp_count = stamp.get("count", 1) if isinstance(stamp, dict) else 1
    if isinstance(stamp_count, bool) or not isinstance(stamp_count, int):
        raise DriverError("unusable-input", f"manifest shard count must be an integer, got {stamp_count!r}")
    sharded = len(loaded) > 1 or stamp_count > 1
    manifest = loaded[0]
    run_id = check_run_id(run_id or manifest.get("run_id") or new_run_id())
    out_dir = out_dir or repo / SCRATCH_ROOT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    shards_index: Optional[dict] = None
    if sharded:
        shards_index = read_json(out_dir / SHARDS_INDEX)
        if not isinstance(shards_index, dict):
            raise DriverError("unusable-input", f"{out_dir / SHARDS_INDEX} must be an object")
        manifest = merge_shard_manifests(loaded, shards_index)
        write_json(out_dir / "merged-manifest.json", manifest)
    rows = list(manifest.get("files") or [])
    timings: Dict[str, float] = {}
    report: dict = {"run_id": run_id, "agent_spawns": 0, "dry_run": dry_run, "halted": None, "phases": {}}

    def finish() -> dict:
        report["timings"] = {k: round(v, 4) for k, v in timings.items()}
        write_json(out_dir / "finalize-report.json", report)
        return report

    t = time.perf_counter()
    if manifest.get("synth_results"):
        results = [p if isinstance(p, dict) else read_json(inside(repo, p) if not Path(p).is_absolute() else Path(p))
                   for p in manifest["synth_results"]]
        prepared_path = manifest.get("prepared")
        prepared = (read_sharded_prepared(shards_index, out_dir) if shards_index is not None
                    else read_prepared(Path(prepared_path) if prepared_path else out_dir / "prepared.json"))
        spliced_rows, synth_report = apply_synth(results, prepared, repo, out_dir, run_id,
                                                 _resolve_bin("coordinator-doc-new", doc_new_bin), not dry_run)
        have = {r["target"] for r in rows}
        rows += [r for r in spliced_rows if r["target"] not in have]
        report["phases"]["synth-splice"] = synth_report
    timings["synth-splice"] = time.perf_counter() - t

    t = time.perf_counter()
    collisions = collision_check(rows, repo, repo / store)
    timings["collision-check"] = time.perf_counter() - t
    report["phases"]["collision-check"] = {"collisions": collisions}
    if collisions:
        report["halted"] = "promote-collision"
        return finish()

    pre_existing = {r["target"] for r in rows if inside(repo, r["target"]).is_file()}
    texts = {}
    for r in rows:
        sp = Path(r["staged"])
        sp = sp if sp.is_absolute() else repo / sp
        texts[r["target"]] = sp.read_text(encoding="utf-8", errors="replace") if sp.is_file() else ""

    t = time.perf_counter()
    if rows and not dry_run:
        promote_file = out_dir / "promote-manifest.json"
        write_json(promote_file, {"run_id": run_id,
                                  "files": [{"staged": r["staged"], "target": r["target"]} for r in rows],
                                  "hashes": manifest.get("hashes") or {}})
        rc, payload, err = script_json(PROMOTE_SCRIPT, ["promote", str(promote_file), "--store", store], repo)
        result = payload if isinstance(payload, dict) else {"status": "error", "promoted": [], "error": err}
    else:
        result = {"status": "ok", "promoted": [], "error": "", "planned": [r["target"] for r in rows]}
    timings["promote"] = time.perf_counter() - t
    report["phases"]["promote"] = result
    if result.get("status") != "ok":
        report["halted"] = "promote-failed"
        return finish()
    if not dry_run:
        report["leg2"] = write_leg2_inputs(repo, out_dir, result.get("promoted") or [],
                                           report["phases"].get("synth-splice") or {})
        report["phases"]["watermark"] = promote_watermark(repo, run_id)
        wm_path = report["phases"]["watermark"].get("path")
        report["commit_paths"] = sorted({*(result.get("promoted") or []), *([wm_path] if wm_path else [])})

    t = time.perf_counter()
    dels = list(manifest.get("deletions") or [])
    confirmed: Dict[str, bool] = {}
    if dels:
        cite_file = out_dir / "citation-spec.json"
        write_json(cite_file, [{"artifact_path": d["artifact_path"], "citation_target": d["citation_target"]} for d in dels])
        rc, payload, err = script_json(PROMOTE_SCRIPT, ["verify-citations", str(cite_file)], repo)
        confirmed = payload if isinstance(payload, dict) else {}
    timings["verify-citations"] = time.perf_counter() - t
    unconfirmed = sorted(d["artifact_path"] for d in dels if confirmed.get(d["artifact_path"]) is not True)
    report["phases"]["verify-citations"] = {
        "confirmed": sorted(k for k, v in confirmed.items() if v is True),
        "unconfirmed": unconfirmed}
    if unconfirmed:
        report["send_back"] = unconfirmed  # DELETE rows with no on-disk citation: must not be deleted

    t = time.perf_counter()
    try:
        report["phases"]["archive"] = [] if no_archive else archive_moves(list(manifest.get("archive") or []), repo, dry_run)
    except DriverError as exc:
        report["phases"]["archive"] = {"error": exc.detail}
        report["halted"] = exc.code
    timings["archive"] = time.perf_counter() - t

    t = time.perf_counter()
    report["phases"]["scratch"] = ({"status": "skipped"} if no_scratch
                                   else scratch_drop(repo, resolve_invoke(invoke_bin), dry_run))
    timings["scratch"] = time.perf_counter() - t
    scratch_phase = report["phases"]["scratch"]
    if scratch_phase.get("status") in ("error", "unavailable", "refused"):
        report.setdefault("warnings", []).append(
            {"phase": "scratch", "warning": "scratch-phase-failed", "status": scratch_phase["status"],
             "exit": scratch_phase.get("exit"), "detail": scratch_phase.get("detail")})

    t = time.perf_counter()
    wiki_dirs = list(manifest.get("wikiDirs") or ["docs/wiki"])
    new_targets = [(r["target"], texts[r["target"]]) for r in rows if r["target"] not in pre_existing]
    report["phases"]["index"] = index_regen(new_targets, repo, wiki_dirs, dry_run)
    timings["index"] = time.perf_counter() - t
    if unconfirmed and not report["halted"]:
        report["halted"] = "unconfirmed-citation"
    return finish()


# --------------------------------------------------------------------------- cli

def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(prog="distill_mechanical.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("prepare", "finalize"):
        p = sub.add_parser(name)
        p.add_argument("--repo-root", required=True)
        p.add_argument("--run-id")
        p.add_argument("--out-dir")
        p.add_argument("--store", default=DEFAULT_STORE)
        if name == "prepare":
            p.add_argument("--input-file", required=True)
            p.add_argument("--nuggets")
            p.add_argument("--verdicts")
            p.add_argument("--pointer-index")
        else:
            p.add_argument("--manifest", required=True, action="append")
            p.add_argument("--dry-run", action="store_true")
            p.add_argument("--no-archive", action="store_true")
            p.add_argument("--no-scratch", action="store_true")
            p.add_argument("--invoke-bin")
            p.add_argument("--doc-new-bin")
    ns = ap.parse_args(argv)
    repo = Path(ns.repo_root).resolve()
    out_dir = Path(ns.out_dir).resolve() if ns.out_dir else None
    try:
        if ns.cmd == "prepare":
            result = prepare(repo, Path(ns.input_file).resolve(),
                             Path(ns.nuggets).resolve() if ns.nuggets else None,
                             Path(ns.verdicts).resolve() if ns.verdicts else None,
                             ns.run_id, out_dir, ns.store,
                             Path(ns.pointer_index).resolve() if ns.pointer_index else None)
        else:
            manifests = [Path(m).resolve() for m in ns.manifest]
            result = finalize(repo, manifests if len(manifests) > 1 else manifests[0], ns.run_id, out_dir, ns.store,
                              ns.dry_run, ns.no_archive, ns.no_scratch, ns.invoke_bin, ns.doc_new_bin)
    except DriverError as exc:
        print(json.dumps({"status": "error", "halted": exc.code, "detail": exc.detail}))
        return 2 if exc.code in ("unusable-input", "not-a-manifest", "bad-run-id") else 1
    for w in result.get("warnings") or []:
        print(f"warning: {w['phase']}: {w['warning']}: {w.get('detail')}", file=sys.stderr)
    print(json.dumps(result))
    return 1 if result.get("halted") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
