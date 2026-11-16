#!/usr/bin/env python3
"""Deterministic /learn-lessons driver: `prepare` closes what a script can and packs the residue; `finalize` applies synth verdicts.

Usage:
  lessons_mechanical.py prepare  --repo R [--out P] [--age-before YYYY-MM-DD]
  lessons_mechanical.py finalize --repo R --results J [--out P]
Contract: coordinator/pipelines/learn-lessons/PIPELINE.md; closing rules:
coordinator/docs/wiki/lesson-triage/learn-lessons-mechanical-dispositions.md. The script never
guesses: a row where no rule fires, or a rule is ambiguous, is residue.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

SCHEMA = "lessons-prepared/1"
SYNTH_PAYLOAD_TOKENS = 25000  # fixed per-call cap, mirrors distill's SYNTH_BATCH_BYTES (100000 bytes at 4 per token)
MAX_SYNTH_CALLS = 3
REQUIRED_FIELDS = ("created", "title", "body", "status", "scope", "from_repo")
DOMAIN_TAGS = ("ue", "game-dev", "web-dev", "data-science")
WIKI_DIR = "coordinator/docs/wiki/lesson-triage"
ARCHIVE_DIR = "archive/lessons-archived"
PROVENANCE = "# Discarded by /learn-lessons on"
CODE_VERDICTS = ("agent-prompt-edit", "hook-edit", "script-edit", "snippet-sync-update", "project-structural")
FORBIDDEN_VERDICTS = ("doctrine-edit", "memory-pointer")
NEEDS_JUDGMENT_VERDICTS = ("doe-escalation", "direction-call", "malformed")
_PIPE = Path(__file__).resolve().parent
_COORD = _PIPE.parents[1]
_WIKI_PATH_RE = re.compile(r"coordinator/docs/wiki/[\w./-]+?\.md")
_LINK_RE = re.compile(r"\]\(([^)\s]+)\)")


def estimate_tokens(payload: object) -> int:
    """Tokens of a JSON payload at 4 bytes each, rounded up."""
    return -(-len(json.dumps(payload, sort_keys=True)) // 4)


def norm(text: str) -> str:
    """Whitespace-collapsed, lowercased text; the one normal form every body comparison uses."""
    return " ".join(str(text).split()).lower()


def body_hash(body: str) -> str:
    return hashlib.sha256(norm(body).encode("utf-8")).hexdigest()


def _paragraphs(text: str) -> List[str]:
    return [p for p in (norm(chunk) for chunk in re.split(r"\n\s*\n", text)) if p]


def _contains_run(haystack: List[str], needle: List[str]) -> bool:
    n = len(needle)
    return n > 0 and any(haystack[i:i + n] == needle for i in range(len(haystack) - n + 1))


class Lesson:
    """One open lesson row: its stem, path, raw text, parsed mapping and any schema problem."""

    def __init__(self, path: Path):
        self.path = path
        self.stem = path.stem
        self.raw = path.read_text(encoding="utf-8")
        self.error: Optional[str] = None
        try:
            data = yaml.safe_load(self.raw)
        except yaml.YAMLError:
            data = None
            self.error = "yaml"
        self.data: dict = data if isinstance(data, dict) else {}
        if data is not None and not isinstance(data, dict):
            self.error = "yaml"

    @property
    def created(self) -> str:
        return str(self.data.get("created", ""))

    @property
    def body(self) -> str:
        return str(self.data.get("body", ""))

    def missing_fields(self) -> List[str]:
        if self.error:
            return [self.error]
        return [f for f in REQUIRED_FIELDS
                if self.data.get(f) is None or not str(self.data.get(f)).strip()]

    def tags(self) -> List[str]:
        raw = self.data.get("tags")
        items = raw if isinstance(raw, list) else ([raw] if raw else [])
        return [norm(t) for t in items]

    def explicit_target(self) -> Optional[str]:
        for key in ("proposed_target", "target_wiki"):
            value = self.data.get(key)
            if isinstance(value, str) and value.strip() and value.strip() != "unknown":
                return value.strip()
        return None

    def named_paths(self) -> List[str]:
        found: List[str] = []
        explicit = self.explicit_target()
        if explicit:
            found.append(explicit)
        found.extend(_WIKI_PATH_RE.findall(self.body))
        return sorted(set(found))


class Wiki:
    """Index-bounded wiki reader: only index-linked or lesson-named files are ever read."""

    def __init__(self, repo: Path):
        self.repo = repo
        self._indexed: Dict[str, set] = {}
        self._paras: Dict[str, Optional[List[str]]] = {}

    def _rel(self, path: Path) -> Optional[str]:
        try:
            return path.resolve().relative_to(self.repo.resolve()).as_posix()
        except ValueError:
            return None

    def indexed(self, directory: str) -> set:
        """Repo-relative paths linked from <directory>/_index.md."""
        if directory not in self._indexed:
            reached: set = set()
            index = self.repo / directory / "_index.md"
            if index.is_file():
                for link in _LINK_RE.findall(index.read_text(encoding="utf-8")):
                    target = link.split("#", 1)[0]
                    if not target or "://" in target or not target.endswith(".md"):
                        continue
                    rel = self._rel(index.parent / target)
                    if rel:
                        reached.add(rel)
            self._indexed[directory] = reached
        return self._indexed[directory]

    def is_indexed(self, rel: str) -> bool:
        return rel in self.indexed(rel.rpartition("/")[0])

    def paragraphs(self, rel: str) -> Optional[List[str]]:
        if rel not in self._paras:
            path = self.repo / rel
            self._paras[rel] = _paragraphs(path.read_text(encoding="utf-8")) if path.is_file() else None
        return self._paras[rel]

    def clean(self, named: str) -> Optional[str]:
        """Repo-relative form of a lesson-named path when it stays inside the repo, else None."""
        return self._rel(self.repo / named)

    def covering_file(self, lesson: Lesson) -> Optional[str]:
        needle = _paragraphs(lesson.body)
        candidates = set(self.indexed(WIKI_DIR))
        for named in lesson.named_paths():
            rel = self.clean(named)
            if rel and rel.startswith("coordinator/docs/wiki/") and rel.endswith(".md"):
                candidates.add(rel)
        for rel in sorted(candidates):
            paras = self.paragraphs(rel)
            if paras and _contains_run(paras, needle):
                return rel
        return None

    def append_target(self, lesson: Lesson) -> Optional[str]:
        named = lesson.explicit_target()
        rel = self.clean(named) if named else None
        if rel and rel.startswith("coordinator/docs/wiki/") and rel.endswith(".md") \
                and (self.repo / rel).is_file() and self.is_indexed(rel):
            return rel
        return None


class Archive:
    """The append-only discard archive: dedupe reads it, closure appends to it before a row is removed."""

    def __init__(self, repo: Path):
        self.repo = repo
        self.root = repo / ARCHIVE_DIR

    def body_hashes(self) -> Dict[str, str]:
        hashes: Dict[str, str] = {}
        if not self.root.is_dir():
            return hashes
        for page in sorted(self.root.glob("*.md")):
            text = page.read_text(encoding="utf-8")
            for chunk in re.split(r"(?m)^(?=" + re.escape(PROVENANCE) + ")", text):
                if not chunk.startswith(PROVENANCE):
                    continue
                try:
                    data = yaml.safe_load(chunk.partition("\n")[2])
                except yaml.YAMLError:
                    continue
                if isinstance(data, dict) and isinstance(data.get("body"), str) and data["body"].strip():
                    hashes.setdefault(body_hash(data["body"]), f"{ARCHIVE_DIR}/{page.name}")
        return hashes

    def close(self, lesson: Lesson) -> None:
        """Archive first, then remove the row."""
        now = datetime.now()
        page = self.root / f"{now:%Y-%m}.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        entry = f"{PROVENANCE} {now:%Y-%m-%d %H:%M} from state/lessons/{lesson.path.name}\n{lesson.raw}"
        if not entry.endswith("\n"):
            entry += "\n"
        with page.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(entry + "\n")
        lesson.path.unlink()


def load_lessons(repo: Path) -> List[Lesson]:
    """Open rows under <repo>/state/lessons in filename order; rows whose status is not open are not the queue."""
    root = repo / "state" / "lessons"
    rows = []
    for path in sorted(root.glob("*.yaml")) if root.is_dir() else []:
        lesson = Lesson(path)
        status = lesson.data.get("status")
        if lesson.error or status is None or str(status).strip().lower() == "open" or not str(status).strip():
            rows.append(lesson)
    return rows


def _append_to_page(page: Path, text: str) -> None:
    current = page.read_text(encoding="utf-8")
    if not current.endswith("\n"):
        current += "\n"
    page.write_text(current + "\n" + text.strip("\n") + "\n", encoding="utf-8", newline="\n")


def _retag_local(lesson: Lesson) -> bool:
    """Rewrite only the scope line; False when the line is not a plain `scope: universal`."""
    new, n = re.subn(r"(?m)^scope:[ \t]*universal[ \t]*$", "scope: project", lesson.raw, count=1)
    if n != 1:
        return False
    lesson.path.write_text(new, encoding="utf-8", newline="\n")
    return True


def load_budget() -> int:
    contract = _COORD / "contract" / "ceremony-budget.json"
    return int(json.loads(contract.read_text(encoding="utf-8"))["whole_backlog_token_bar"])


def load_verdicts() -> List[str]:
    profile = _COORD / "queue-profiles" / "lessons.yaml"
    return list(yaml.safe_load(profile.read_text(encoding="utf-8"))["verdicts"])


def synth_record(lesson: Lesson) -> dict:
    record = {"id": lesson.stem}
    for key in ("title", "created", "scope", "tags", "from_repo", "proposed_target", "target_wiki", "body"):
        value = lesson.data.get(key)
        if value is not None and value != "":
            record[key] = str(value) if key == "created" else value
    return record


def _fit_alone(record: dict) -> dict:
    """An oversize row rides alone with its body cut to fit the payload cap."""
    marker = "\n[body truncated to fit the payload cap]"
    while estimate_tokens([record]) > SYNTH_PAYLOAD_TOKENS and len(record["body"]) > len(marker):
        excess_chars = (estimate_tokens([record]) - SYNTH_PAYLOAD_TOKENS) * 4
        keep = max(len(record["body"]) - len(marker) - excess_chars - 16, 0)
        record = {**record, "body": record["body"][:keep] + marker}
    return record


def pack_payloads(records: List[dict]) -> Tuple[List[dict], List[str]]:
    """Greedy payloads in (created, id) order, each within SYNTH_PAYLOAD_TOKENS; residue past the third is deferred."""
    ordered = sorted(records, key=lambda r: (str(r.get("created", "")), r["id"]))
    payloads: List[List[dict]] = []
    deferred: List[str] = []
    for record in ordered:
        if payloads and estimate_tokens(payloads[-1] + [record]) <= SYNTH_PAYLOAD_TOKENS:
            payloads[-1].append(record)
            continue
        if len(payloads) >= MAX_SYNTH_CALLS:
            deferred.append(record["id"])
            continue
        payloads.append([record if estimate_tokens([record]) <= SYNTH_PAYLOAD_TOKENS else _fit_alone(record)])
    return ([{"lessons": p, "est_tokens": estimate_tokens(p)} for p in payloads], deferred)


def synth_schema(ids: List[str], verdicts: List[str]) -> dict:
    allowed = [v for v in verdicts if v not in FORBIDDEN_VERDICTS]
    record = {
        "type": "object",
        "required": ["id", "verdict", "target", "markdown", "cites"],
        "additionalProperties": False,
        "properties": {
            "id": {"enum": ids},
            "verdict": {"enum": allowed},
            "target": {"type": "string"},
            "markdown": {"type": "string"},
            "cites": {"type": "array", "items": {"type": "string"}},
        },
    }
    return {"type": "object", "required": ["verdicts"], "additionalProperties": False,
            "properties": {"verdicts": {"type": "array", "items": record}}}


def prepare(repo: Path, age_before: Optional[str] = None) -> dict:
    """Close every row a deterministic rule closes, then pack the residue; returns the prepared mapping."""
    rows = load_lessons(repo)
    wiki, archive = Wiki(repo), Archive(repo)
    closed: List[dict] = []
    live: List[Lesson] = []

    for lesson in rows:  # age-sweep, then malformed
        if age_before and not lesson.missing_fields() and norm(lesson.data["scope"]) == "universal" \
                and lesson.created < age_before:
            archive.close(lesson)
            closed.append({"id": lesson.stem, "disposition": "age-sweep",
                           "evidence": f"universal row created {lesson.created} before cutoff {age_before}"})
            continue
        missing = lesson.missing_fields()
        if missing:
            closed.append({"id": lesson.stem, "disposition": "malformed",
                           "evidence": "missing or empty field: " + ", ".join(missing)})
            continue
        live.append(lesson)

    groups: Dict[str, List[Lesson]] = {}
    for lesson in live:
        groups.setdefault(body_hash(lesson.body), []).append(lesson)
    archived = archive.body_hashes()
    survivors: List[Lesson] = []
    for digest, members in groups.items():
        members.sort(key=lambda r: (r.created, r.path.name))
        if digest in archived:
            kept, young = None, members
            where = archived[digest]
        else:
            kept, young = members[0], members[1:]
            where = kept.stem
            survivors.append(kept)
        for lesson in young:
            archive.close(lesson)
            closed.append({"id": lesson.stem, "disposition": "dedupe", "evidence": where})

    residue: List[Lesson] = []
    for lesson in sorted(survivors, key=lambda r: r.path.name):
        covered = wiki.covering_file(lesson)
        if covered:
            archive.close(lesson)
            closed.append({"id": lesson.stem, "disposition": "discard", "evidence": covered})
            continue
        if norm(lesson.data["scope"]) == "universal" and set(lesson.tags()) & set(DOMAIN_TAGS):
            if _retag_local(lesson):
                closed.append({"id": lesson.stem, "disposition": "retag-local",
                               "evidence": "scope: universal -> project; tag " + ", ".join(
                                   sorted(set(lesson.tags()) & set(DOMAIN_TAGS)))})
                continue
        target = wiki.append_target(lesson)
        if target:
            _append_to_page(repo / target, lesson.body)
            archive.close(lesson)
            closed.append({"id": lesson.stem, "disposition": "wiki-append", "evidence": target})
            continue
        residue.append(lesson)

    verdicts = load_verdicts()
    payloads, deferred = pack_payloads([synth_record(r) for r in residue])
    return {
        "schema": SCHEMA,
        "closed": sorted(closed, key=lambda c: c["id"]),
        "residue_ids": sorted(r.stem for r in residue),
        "deferred_ids": sorted(deferred),
        "age_sweep": f"before {age_before}" if age_before else "skipped: no central-run cutoff given",
        "synth": {
            "payloads": payloads,
            "schemas": [synth_schema([le["id"] for le in p["lessons"]], verdicts) for p in payloads],
            "budget_tokens": load_budget(),
        },
    }


def _records_of(raw: object) -> List[dict]:
    if isinstance(raw, dict):
        for key in ("verdicts", "records", "results"):
            if isinstance(raw.get(key), list):
                return [r for r in raw[key] if isinstance(r, dict)]
        return []
    return [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []


def _queue_append_cmd() -> Optional[str]:
    home = Path(os.environ.get("COORDINATOR_SETTINGS_HOME") or Path.home() / ".coordinator-claude-settings")
    for suffix in ("", ".exe", ".cmd"):
        candidate = home / "bin" / f"coordinator-queue-append{suffix}"
        if candidate.is_file():
            return str(candidate)
    return shutil.which("coordinator-queue-append")


def _queue_row(repo: Path, lesson: Lesson, record: dict) -> Optional[str]:
    """Append one improvement-queue row (queue_scope project) for a code-kind verdict; an error string on failure."""
    cmd = _queue_append_cmd()
    if not cmd:
        return "coordinator-queue-append not found"
    scratch = repo / "scratch" / "lessons-finalize"
    scratch.mkdir(parents=True, exist_ok=True)
    body_file = scratch / f"{lesson.stem}.body.md"
    cites = [str(c) for c in record.get("cites", [])]
    body_file.write_text(
        f"{lesson.body}\n\nLesson: state/lessons/{lesson.path.name}\nTarget: {record.get('target', '')}\n"
        f"Cites: {', '.join(cites)}\n", encoding="utf-8", newline="\n")
    try:
        proc = subprocess.run(
            [cmd, "--schema", "improvement-queue", "--title", str(lesson.data.get("title") or lesson.stem),
             "--body-file", str(body_file), "--status", "open", "--surface", str(record.get("target") or lesson.stem),
             "--proposed-action", str(record.get("markdown") or record.get("target") or lesson.stem),
             "--change-kind", record["verdict"], "--queue-scope", "project", "--evidence", "; ".join(cites),
             "--source", f"learn-lessons {lesson.stem}"],
            cwd=str(repo), capture_output=True, text=True, timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (subprocess.TimeoutExpired, OSError) as exc:
        return f"{type(exc).__name__}: {exc}"[:300]
    finally:
        body_file.unlink(missing_ok=True)
    return None if proc.returncode == 0 else (proc.stderr or proc.stdout).strip()[:300]


def _inside_wiki(repo: Path, target: str) -> Optional[Path]:
    path = (repo / target).resolve()
    root = (repo / "coordinator" / "docs" / "wiki").resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    return path if path.suffix == ".md" else None


def finalize(repo: Path, raw_results: object) -> dict:
    """Apply synth verdicts: wiki ops by splice, code-kind verdicts into one improvement-queue row each."""
    lessons = {r.stem: r for r in load_lessons(repo)}
    allowed = set(load_verdicts()) - set(FORBIDDEN_VERDICTS)
    archive = Archive(repo)
    out: Dict[str, list] = {k: [] for k in
                            ("applied", "queued", "needs_judgment", "route_to_central", "refused")}

    def refuse(stem: str, reason: str) -> None:
        out["refused"].append({"id": stem, "reason": reason})

    seen = set()
    for record in _records_of(raw_results):
        stem = str(record.get("id", ""))
        verdict = record.get("verdict")
        lesson = lessons.get(stem)
        if lesson is None or stem in seen:
            refuse(stem, "no open lesson row with this id" if lesson is None else "duplicate record")
            continue
        seen.add(stem)
        cites = record.get("cites")
        if verdict not in allowed:
            refuse(stem, f"verdict not allowed: {verdict}")
        elif not isinstance(cites, list) or not [c for c in cites if str(c).strip()]:
            refuse(stem, "cites required")
        elif verdict == "universal":
            out["route_to_central"].append(stem)
        elif verdict in NEEDS_JUDGMENT_VERDICTS:
            out["needs_judgment"].append(stem)
        elif verdict in ("discard", "dedupe"):
            archive.close(lesson)
            out["applied"].append({"id": stem, "verdict": verdict, "target": record.get("target", "")})
        elif verdict in ("wiki-append", "wiki-new"):
            page = _inside_wiki(repo, str(record.get("target") or ""))
            text = str(record.get("markdown") or "")
            if page is None:
                refuse(stem, "target must be a .md file under coordinator/docs/wiki")
            elif not text.strip():
                refuse(stem, "markdown required")
            elif verdict == "wiki-append" and not page.is_file():
                refuse(stem, "wiki-append target does not exist")
            elif verdict == "wiki-new" and page.exists():
                refuse(stem, "wiki-new target already exists")
            else:
                if verdict == "wiki-append":
                    _append_to_page(page, text)
                else:
                    page.parent.mkdir(parents=True, exist_ok=True)
                    page.write_text(text.strip("\n") + "\n", encoding="utf-8", newline="\n")
                archive.close(lesson)
                out["applied"].append({"id": stem, "verdict": verdict, "target": page.relative_to(repo).as_posix()})
        elif verdict in CODE_VERDICTS:
            error = _queue_row(repo, lesson, record)
            if error:
                refuse(stem, f"queue append failed: {error}")
            else:
                archive.close(lesson)
                out["queued"].append({"id": stem, "verdict": verdict, "target": record.get("target", "")})
        else:
            refuse(stem, f"unhandled verdict: {verdict}")
    return out


def _write_json(path: Path, payload: dict, compact: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, separators=(",", ":"), sort_keys=True) if compact \
        else json.dumps(payload, indent=2, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="lessons_mechanical.py", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    prep = sub.add_parser("prepare", help="close deterministic rows, pack residue, write prepared.json")
    fin = sub.add_parser("finalize", help="apply the synth verdicts")
    for p in (prep, fin):
        p.add_argument("--repo", required=True, help="repo root; lessons are read from <repo>/state/lessons")
        p.add_argument("--out", help="output JSON path (default: <repo>/scratch/learn-lessons/<cmd>.json)")
    prep.add_argument("--age-before", help="age-sweep cutoff YYYY-MM-DD; omitted means the sweep is skipped")
    fin.add_argument("--results", required=True, help="the lessons-synth workflow result JSON")
    args = ap.parse_args(argv)
    repo = Path(args.repo)
    if not repo.is_dir():
        ap.error(f"--repo is not a directory: {repo}")
    out = Path(args.out) if args.out else repo / "scratch" / "learn-lessons" / f"{args.cmd}.json"
    if args.cmd == "prepare":
        prepared = prepare(repo, args.age_before)
        _write_json(out, prepared, compact=True)
        print(json.dumps({"closed": len(prepared["closed"]), "residue": len(prepared["residue_ids"]),
                          "deferred": len(prepared["deferred_ids"]),
                          "payloads": len(prepared["synth"]["payloads"]), "out": str(out)}))
    else:
        result = finalize(repo, json.loads(Path(args.results).read_text(encoding="utf-8")))
        _write_json(out, result, compact=False)
        print(json.dumps({k: len(v) for k, v in result.items()} | {"out": str(out)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
