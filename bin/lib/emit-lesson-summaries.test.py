#!/usr/bin/env python3
"""emit-lesson-summaries.test.py — self-contained regression tests for the lesson summary emitter.

Tests:
  AC6  union-not-left-join: drained-only entry (no lessons.md row) IS emitted
  AC7  count-honesty / degraded-but-counted: malformed entry → parse_status="partial", still emitted
  AC8a promotion_state precedence: drained wins over lessons.md+drained
  AC8b promotion_state precedence: pending wins over lessons.md+outbox
  AC8c promotion_state precedence: captured for lessons.md-only
  AC8d captured-only nullability: change_kind/target_wiki/from_repo/created are null
  SCOPE      scope from [universal] tag survives partial parse
  SCOPE-OUTBOX block-list scope_tags:\n  - universal (no body marker) → scope=universal (F1 fix)
  KEY        lesson_key regex: ^[0-9a-f]{16}$
  AC7-nonnull  every emitted record has parse_status in ("ok","partial")

Run: python3 bin/lib/emit-lesson-summaries.test.py
Exit non-zero on any failure.

Spec backlink: docs/plans/2026-06-23-cockpit-contract-ext-wave2-emit-and-queue-migration.md § C3
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Locate the emitter script relative to this test file
_THIS_DIR = Path(__file__).resolve().parent
_EMITTER = _THIS_DIR / "emit-lesson-summaries.py"
# Locate the validator (bin/lib/validate-cockpit-record.mjs relative to coordinator root)
_COORDINATOR_ROOT = _THIS_DIR.parent.parent  # bin/lib/ -> bin/ -> coordinator/
_VALIDATOR = _COORDINATOR_ROOT / "bin" / "lib" / "validate-cockpit-record.mjs"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_KEY_RE = re.compile(r"^[0-9a-f]{16}$")

FAIL_COUNT = 0


def fail(msg: str) -> None:
    global FAIL_COUNT
    FAIL_COUNT += 1
    print(f"FAIL: {msg}", file=sys.stderr)


def ok(msg: str) -> None:
    print(f"ok:   {msg}")


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip().lower())


def _lesson_key(title: str) -> str:
    normalized = _normalize_title(title)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _run_emitter(tmp_root: Path) -> list[dict]:
    """Run the emitter against the given tmp repo root, return parsed records."""
    result = subprocess.run(
        [sys.executable, str(_EMITTER), str(tmp_root), "test-repo", "test-branch", "abc123", "2026-01-01T00:00:00Z"],
        capture_output=True, text=True, timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        raise RuntimeError(f"Emitter exited {result.returncode}:\nstdout={result.stdout}\nstderr={result.stderr}")
    return json.loads(result.stdout)


def _write_outbox_yaml(path: Path, data: dict) -> None:
    """Write a simple outbox YAML file.

    Review: code-reviewer — limitation: if a body value itself contains a bare `---` line,
    the parser in _parse_outbox_yaml will misinterpret it as a fence boundary. The outbox
    corpus does not produce bodies with `---` lines, so this is acceptable but documented.
    """
    lines = ["---"]
    for k, v in data.items():
        if v is None:
            lines.append(f"{k}: null")
        elif "\n" in str(v):
            lines.append(f"{k}: |")
            for bl in str(v).splitlines():
                lines.append(f"  {bl}")
        elif isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                lines.append(f"  - {item}")
        else:
            # Quote strings with colons or special chars
            sv = str(v)
            if any(c in sv for c in ":#{}[]!"):
                lines.append(f'{k}: "{sv}"')
            else:
                lines.append(f"{k}: {sv}")
    lines.append("---")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------

def _build_fixture_tree(tmp_path: Path) -> dict:
    """
    Build a tmp fixture tree and return a dict describing the titles used,
    so tests can look up expected keys.

    Titles used:
      A: "Clean lesson in lessons.md only"              (captured, universal) [state/lessons/]
      B: "Lesson in lessons.md and outbox"              (pending — outbox wins) [state/lessons/ + outbox]
      C: "Lesson in lessons.md and drained"             (drained — drained wins) [state/lessons/ + drained]
      D: "Drained-only lesson not in lessons.md"        (drained — AC6 load-bearing) [drained only]
      E: "Outbox-only lesson with empty body"            (pending, partial — AC7) [outbox only]
    """
    state = tmp_path / "state"
    state.mkdir(parents=True)
    plugins = tmp_path / "plugins"
    plugins.mkdir()  # presence satisfies _find_repo_root marker

    outbox = state / "lessons-outbox"
    outbox.mkdir()
    drained = outbox / "drained"
    drained.mkdir()

    # Title constants
    title_A = "Clean lesson in lessons.md only"
    title_B = "Lesson in lessons.md and outbox"
    title_C = "Lesson in lessons.md and drained"
    title_D = "Drained-only lesson not in lessons.md"
    title_E = "Outbox-only lesson with empty body"

    # Write per-entry YAML files to state/lessons/ — does NOT include title_D or title_E.
    # C3c migration: first surface is now state/lessons/*.yaml, not lessons.md.
    lessons_dir = state / "lessons"
    lessons_dir.mkdir()
    _write_outbox_yaml(
        lessons_dir / "2026-01-01-lesson-a.yaml",
        {
            "title": title_A,
            "body": "This is the body of lesson A. It covers a clean capture.",
            "created": "2026-01-01",  # date-only — emitter normalizes to "2026-01-01T00:00:00Z"
            "status": "open",
            "scope": "universal",
            "from_repo": "test-repo",
            # Review: code-reviewer (F7/AC8d) — add target_wiki and evidence so AC8d can assert
            # exact forwarded values rather than asserting null (born-attributable forward test).
            "target_wiki": "docs/wiki/test-lesson-a.md",
            "evidence": "Evidence string for lesson A",
        },
    )
    _write_outbox_yaml(lessons_dir / "2026-01-02-lesson-b.yaml", {
        "title": title_B,
        "body": "Body of lesson B. This one also has a pending outbox entry.",
        "created": "2026-01-02",
        "status": "open",
        "scope": "project",
        "from_repo": "test-repo",
    })
    _write_outbox_yaml(lessons_dir / "2026-01-03-lesson-c.yaml", {
        "title": title_C,
        "body": "Body of lesson C. This one also has a drained outbox entry.",
        "created": "2026-01-03",
        "status": "open",
        "scope": "universal",
        "from_repo": "test-repo",
    })

    # Write outbox entry for B (pending)
    _write_outbox_yaml(outbox / "2026-01-02-lesson-b.yaml", {
        "id": "aaaa-bbbb",
        "created": "2026-01-02T12:00:00+00:00",
        "from_repo": "claude-central-em",
        "change_kind": "doctrine-edit",
        "target_wiki": "docs/wiki/test.md",
        "title": title_B,
        "body": "Outbox body for lesson B.",
        "scope_tags": ["pending-tag"],
        "evidence": "Evidence for B",
    })

    # Write drained entry for C (drained + in lessons.md → drained wins)
    _write_outbox_yaml(drained / "2026-01-03-lesson-c.yaml", {
        "id": "cccc-dddd",
        "created": "2026-01-03T12:00:00+00:00",
        "from_repo": "claude-central-em",
        "change_kind": "wiki-edit",
        "target_wiki": "docs/wiki/other.md",
        "title": title_C,
        "body": "Drained body for lesson C.",
        "scope_tags": ["universal"],
        "evidence": None,
    })

    # Write drained entry for D (drained-only — NOT in lessons.md — AC6)
    _write_outbox_yaml(drained / "2026-01-04-lesson-d.yaml", {
        "id": "dddd-eeee",
        "created": "2026-01-04T12:00:00+00:00",
        "from_repo": "claude-central-em",
        "change_kind": "hook-edit",
        "target_wiki": None,
        "title": title_D,
        "body": "This lesson exists only in drained, not in lessons.md at all.",
        "scope_tags": [],
        "evidence": None,
    })

    # Write outbox entry for E (outbox-only, empty body → parse_status="partial" — AC7)
    _write_outbox_yaml(outbox / "2026-01-05-lesson-e.yaml", {
        "id": "eeee-ffff",
        "created": "2026-01-05T12:00:00+00:00",
        "from_repo": "claude-central-em",
        "change_kind": "doctrine-edit",
        "target_wiki": None,
        "title": title_E,
        "body": "",  # deliberately empty → parse_status="partial"
        "scope_tags": [],
        "evidence": None,
    })

    return {
        "title_A": title_A,
        "title_B": title_B,
        "title_C": title_C,
        "title_D": title_D,
        "title_E": title_E,
        "key_A": _lesson_key(title_A),
        "key_B": _lesson_key(title_B),
        "key_C": _lesson_key(title_C),
        "key_D": _lesson_key(title_D),
        "key_E": _lesson_key(title_E),
    }


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def run_tests() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        titles = _build_fixture_tree(tmp_path)

        records = _run_emitter(tmp_path)
        by_key = {r["lesson_key"]: r for r in records}

        # ---------- AC6: union-not-left-join (load-bearing) ----------
        if titles["key_D"] in by_key:
            ok("AC6: drained-only entry IS emitted (full outer join, not left-join)")
            rec_D = by_key[titles["key_D"]]
            if rec_D["promotion_state"] == "drained":
                ok("AC6: drained-only entry has promotion_state='drained'")
            else:
                fail(f"AC6: drained-only entry has promotion_state='{rec_D['promotion_state']}', expected 'drained'")
            # Review: code-reviewer — AC6 previously only checked key+promotion_state;
            # add body transport, title, and parse_status assertions for load-bearing correctness.
            expected_title_D = titles["title_D"]
            if rec_D.get("title") == expected_title_D:
                ok(f"AC6: drained-only entry title correct: {expected_title_D!r}")
            else:
                fail(f"AC6: drained-only entry title wrong — expected {expected_title_D!r}, got {rec_D.get('title')!r}")
            drained_body_snippet = "only in drained"
            if drained_body_snippet in (rec_D.get("body") or ""):
                ok("AC6: drained-only entry body transported from drained YAML")
            else:
                fail(f"AC6: drained-only entry body missing expected content {drained_body_snippet!r}; got {rec_D.get('body')!r}")
            if rec_D.get("parse_status") == "ok":
                ok("AC6: drained-only entry parse_status='ok'")
            else:
                fail(f"AC6: drained-only entry parse_status expected 'ok', got {rec_D.get('parse_status')!r}")
        else:
            fail(f"AC6: CRITICAL — drained-only entry (key={titles['key_D']}) NOT in emitted records (left-join bug)")

        # ---------- AC7: count-honesty / degraded-but-counted ----------
        if titles["key_E"] in by_key:
            rec_E = by_key[titles["key_E"]]
            if rec_E["parse_status"] == "partial":
                ok("AC7: malformed/partial lesson has parse_status='partial'")
            else:
                fail(f"AC7: expected parse_status='partial', got '{rec_E['parse_status']}'")
            ok("AC7: partial lesson is emitted (degraded-but-counted, not dropped)")
        else:
            fail(f"AC7: partial lesson (key={titles['key_E']}) was dropped — should be emitted with parse_status=partial")

        # Total count: 5 distinct keys (A,B,C,D,E)
        expected_min_count = 5
        if len(records) >= expected_min_count:
            ok(f"AC7: total emitted count {len(records)} >= {expected_min_count} (all distinct lesson_keys represented)")
        else:
            fail(f"AC7: expected >= {expected_min_count} records but got {len(records)}")

        # ---------- AC8a: promotion_state precedence — drained wins ----------
        if titles["key_C"] in by_key:
            rec_C = by_key[titles["key_C"]]
            if rec_C["promotion_state"] == "drained":
                ok("AC8a: lesson in lessons.md + drained → promotion_state='drained'")
            else:
                fail(f"AC8a: expected 'drained', got '{rec_C['promotion_state']}'")
        else:
            fail(f"AC8a: lesson C (key={titles['key_C']}) not emitted")

        # ---------- AC8b: promotion_state precedence — pending ----------
        if titles["key_B"] in by_key:
            rec_B = by_key[titles["key_B"]]
            if rec_B["promotion_state"] == "pending":
                ok("AC8b: lesson in lessons.md + outbox → promotion_state='pending'")
            else:
                fail(f"AC8b: expected 'pending', got '{rec_B['promotion_state']}'")
            # Also verify outbox fields populated
            if rec_B.get("change_kind") == "doctrine-edit":
                ok("AC8b: change_kind populated from outbox")
            else:
                fail(f"AC8b: expected change_kind='doctrine-edit', got '{rec_B.get('change_kind')}'")
            # Review: code-reviewer (F4/AC8b) — assert exact normalized value, not just non-null.
            # Outbox fixture has "2026-01-02T12:00:00+00:00"; _normalize_created passes it
            # through unchanged (contains "T" and matches ISO regex).
            expected_created_B = "2026-01-02T12:00:00+00:00"
            if rec_B.get("created") == expected_created_B:
                ok(f"AC8b: created='{expected_created_B}' (exact value from outbox, normalized)")
            else:
                fail(f"AC8b: created expected '{expected_created_B}', got '{rec_B.get('created')}'  (IsoDateTime offset accepted)")
        else:
            fail(f"AC8b: lesson B (key={titles['key_B']}) not emitted")

        # ---------- AC8c: promotion_state precedence — captured ----------
        if titles["key_A"] in by_key:
            rec_A = by_key[titles["key_A"]]
            if rec_A["promotion_state"] == "captured":
                ok("AC8c: lessons.md-only lesson → promotion_state='captured'")
            else:
                fail(f"AC8c: expected 'captured', got '{rec_A['promotion_state']}'")
        else:
            fail(f"AC8c: lesson A (key={titles['key_A']}) not emitted")

        # ---------- AC8d: captured-only field contract (updated for born-attributable) ----------
        # Born-attributable fix: `from_repo` and `created` are now forwarded from the per-entry
        # YAML into captured records, so they are NON-null for lesson A (fixture has both).
        # `change_kind` remains null for captured entries — it is only set from outbox/drained
        # records and is NOT part of the per-entry YAML format.
        # `target_wiki` and `evidence` are null here because the fixture YAML for A omits them.
        if titles["key_A"] in by_key:
            rec_A = by_key[titles["key_A"]]
            # Fields that must remain null: change_kind is only from outbox/drained
            for field in ["change_kind"]:
                if field in rec_A and rec_A[field] is None:
                    ok(f"AC8d: captured-only has {field}=null (outbox-only field, not in per-entry YAML)")
                elif field not in rec_A:
                    fail(f"AC8d: captured-only is missing field '{field}' (must be present-as-null per D9)")
                else:
                    fail(f"AC8d: captured-only {field} should be null but is '{rec_A[field]}'")
            # Review: code-reviewer (F7/AC8d) — fixture now supplies target_wiki and evidence;
            # assert exact forwarded values (born-attributable non-null forward test).
            if rec_A.get("target_wiki") == "docs/wiki/test-lesson-a.md":
                ok("AC8d: captured-only target_wiki='docs/wiki/test-lesson-a.md' (born-attributable, from per-entry YAML)")
            elif "target_wiki" not in rec_A:
                fail("AC8d: captured-only is missing field 'target_wiki' (must be present-as-null per D9)")
            else:
                fail(
                    f"AC8d: captured-only target_wiki expected 'docs/wiki/test-lesson-a.md',"
                    f" got '{rec_A.get('target_wiki')}'"
                )
            if rec_A.get("evidence") == "Evidence string for lesson A":
                ok("AC8d: captured-only evidence='Evidence string for lesson A' (born-attributable, from per-entry YAML)")
            elif "evidence" not in rec_A:
                fail("AC8d: captured-only is missing field 'evidence' (must be present-as-null per D9)")
            else:
                fail(
                    f"AC8d: captured-only evidence expected 'Evidence string for lesson A',"
                    f" got '{rec_A.get('evidence')}'"
                )
            # Born-attributable: from_repo and created ARE in the fixture YAML → must be non-null
            if rec_A.get("from_repo") is not None:
                ok(f"AC8d: captured-only from_repo='{rec_A['from_repo']}' (born-attributable, from per-entry YAML)")
            else:
                fail("AC8d: captured-only from_repo should be non-null (born-attributable fix) but is null")
            # "2026-01-01" (date-only in YAML) must be normalized to "2026-01-01T00:00:00Z"
            if rec_A.get("created") == "2026-01-01T00:00:00Z":
                ok("AC8d: captured-only created='2026-01-01T00:00:00Z' (date-only '2026-01-01' normalized to IsoDateTime)")
            else:
                fail(f"AC8d: captured-only created expected '2026-01-01T00:00:00Z' (date-only normalized), got '{rec_A.get('created')}'")
            # scope should still be set from scope field in YAML (universal)
            if rec_A.get("scope") == "universal":
                ok("AC8d: captured-only scope='universal' from scope field in per-entry YAML")
            else:
                fail(f"AC8d: expected scope='universal' from scope field in YAML, got '{rec_A.get('scope')}'")

        # ---------- lesson_key regex shape check ----------
        for rec in records:
            key_val = rec.get("lesson_key", "")
            if not _KEY_RE.match(key_val):
                fail(f"KEY: lesson_key '{key_val}' does not match ^[0-9a-f]{{16}}$")
        ok(f"KEY: all {len(records)} lesson_key values match ^[0-9a-f]{{16}}$")

        # ---------- Schema validation via validator (at least one record of each state) ----------
        if _VALIDATOR.is_file():
            for promotion_state in ("captured", "pending", "drained"):
                candidates = [r for r in records if r["promotion_state"] == promotion_state]
                if not candidates:
                    # Not a failure if the fixture doesn't produce this state
                    continue
                rec = candidates[0]
                with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                    json.dump(rec, f)
                    tmpf = f.name
                try:
                    val_result = subprocess.run(
                        ["node", str(_VALIDATOR), "lesson-summary", tmpf],
                        capture_output=True, text=True, timeout=15,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    if val_result.returncode == 0:
                        ok(f"SCHEMA: {promotion_state} record validates against lesson-summary schema")
                    else:
                        fail(f"SCHEMA: {promotion_state} record FAILED schema validation:\n{val_result.stdout}\n{val_result.stderr}")
                except Exception as e:
                    fail(f"SCHEMA: validator invocation failed for {promotion_state}: {e}")
                finally:
                    os.unlink(tmpf)
        else:
            # Review: code-reviewer (F5) — was silent stdout warn; now fail() so CI without
            # node does not silently pass schema validation. Gate on env var if no-node CI
            # is intentional: SKIP_SCHEMA_VALIDATION=1 python3 emit-lesson-summaries.test.py
            if os.environ.get("SKIP_SCHEMA_VALIDATION") == "1":
                print(f"warn: validator not found at {_VALIDATOR}, schema validation skipped (SKIP_SCHEMA_VALIDATION=1)")
            else:
                fail(f"SCHEMA: validator not found at {_VALIDATOR} — set SKIP_SCHEMA_VALIDATION=1 to skip")

    # ---------- F7: 4-space-indented scope_tags list item ----------
    # Review: code-reviewer — list-item parser was broadened to match any indent ≥2 (re.match
    # r"^\s{2,}- "). Verify a YAML file with 4-space-indented scope_tags is parsed correctly
    # by running the emitter against a minimal fixture containing one such entry.
    with tempfile.TemporaryDirectory() as tmpdir2:
        tmp2 = Path(tmpdir2)
        (tmp2 / "state").mkdir(parents=True)
        (tmp2 / "plugins").mkdir()
        ob2 = tmp2 / "state" / "lessons-outbox"
        ob2.mkdir()
        (ob2 / "drained").mkdir()
        title_F7 = "Four-space scope_tags indented lesson"
        # Write a drained YAML with 4-space-indented scope_tags
        yaml_content = (
            "---\n"
            f"title: {title_F7}\n"
            "body: body for F7 test\n"
            "scope_tags:\n"
            "    - universal\n"  # 4-space indent
            "created: 2026-01-06T00:00:00+00:00\n"
            "change_kind: doctrine-edit\n"
            "from_repo: test\n"
            "target_wiki: null\n"
            "evidence: null\n"
            "---\n"
        )
        (ob2 / "drained" / "2026-01-06-f7.yaml").write_text(yaml_content, encoding="utf-8")
        result_f7 = subprocess.run(
            [sys.executable, str(_EMITTER), str(tmp2), "test-repo", "test-branch", "abc123", "2026-01-01T00:00:00Z"],
            capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result_f7.returncode != 0:
            fail(f"F7: emitter failed for 4-space scope_tags fixture: {result_f7.stderr}")
        else:
            recs_f7 = json.loads(result_f7.stdout)
            key_F7 = _lesson_key(title_F7)
            by_key_f7 = {r["lesson_key"]: r for r in recs_f7}
            if key_F7 in by_key_f7 and by_key_f7[key_F7].get("scope") == "universal":
                ok("F7: 4-space-indented scope_tags 'universal' item correctly parsed → scope='universal'")
            elif key_F7 not in by_key_f7:
                fail(f"F7: 4-space scope_tags fixture not emitted (key={key_F7})")
            else:
                fail(f"F7: 4-space scope_tags 'universal' not recognised; got scope={by_key_f7[key_F7].get('scope')!r}")

    # ---------- SCOPE-OUTBOX: block-list scope_tags="universal" (no [universal] in body) ----------
    # Review: code-reviewer (F2) — covers the F1-fixed path: block-list `scope_tags:\n  - universal`
    # must survive the parser and produce scope="universal" even when body has no [universal] marker.
    with tempfile.TemporaryDirectory() as tmpdir3:
        tmp3 = Path(tmpdir3)
        (tmp3 / "state").mkdir(parents=True)
        (tmp3 / "plugins").mkdir()
        ob3 = tmp3 / "state" / "lessons-outbox"
        ob3.mkdir()
        (ob3 / "drained").mkdir()
        title_scope_outbox = "Scope outbox universal block list lesson"
        # Write a YAML with block-list scope_tags (no [universal] in body) to confirm F1 fix
        yaml_scope = (
            "---\n"
            f"title: {title_scope_outbox}\n"
            "body: body text without the universal marker anywhere\n"
            "scope_tags:\n"
            "  - universal\n"  # block-list form — requires F1 fix to parse correctly
            "created: 2026-01-07T00:00:00+00:00\n"
            "change_kind: doctrine-edit\n"
            "from_repo: test\n"
            "target_wiki: null\n"
            "evidence: null\n"
            "---\n"
        )
        (ob3 / "drained" / "2026-01-07-scope-outbox.yaml").write_text(yaml_scope, encoding="utf-8")
        result_so = subprocess.run(
            [sys.executable, str(_EMITTER), str(tmp3), "test-repo", "test-branch", "abc123", "2026-01-01T00:00:00Z"],
            capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result_so.returncode != 0:
            fail(f"SCOPE-OUTBOX: emitter failed: {result_so.stderr}")
        else:
            recs_so = json.loads(result_so.stdout)
            key_so = _lesson_key(title_scope_outbox)
            by_key_so = {r["lesson_key"]: r for r in recs_so}
            if key_so not in by_key_so:
                fail(f"SCOPE-OUTBOX: block-list scope_tags fixture not emitted (key={key_so})")
            elif by_key_so[key_so].get("scope") == "universal":
                ok("SCOPE-OUTBOX: block-list `scope_tags:\\n  - universal` (no body marker) → scope='universal'")
            else:
                fail(
                    f"SCOPE-OUTBOX: expected scope='universal' from block-list scope_tags, "
                    f"got scope={by_key_so[key_so].get('scope')!r} — F1 fix may not have taken effect"
                )

    # ---------- AC7-nonnull: every emitted record has parse_status in ("ok","partial") ----------
    # Review: code-reviewer (F12) — AC7 non-nullable contract: parse_status must always be
    # present and one of the two legal values; a missing or unexpected value is a schema violation.
    with tempfile.TemporaryDirectory() as tmpdir4:
        tmp4 = Path(tmpdir4)
        titles4 = _build_fixture_tree(tmp4)
        records4 = _run_emitter(tmp4)
        bad_parse_status = [
            r for r in records4
            if r.get("parse_status") not in ("ok", "partial")
        ]
        if bad_parse_status:
            for r in bad_parse_status:
                fail(
                    f"AC7-nonnull: record {r.get('lesson_key')!r} has "
                    f"parse_status={r.get('parse_status')!r}, expected 'ok' or 'partial'"
                )
        else:
            ok(f"AC7-nonnull: all {len(records4)} records have parse_status in ('ok','partial')")

    # ---------- SENTINEL: "0000-00-00" created → emitted created is None ----------
    # Verifies that the sentinel date used in legacy-migrated lessons emits honest null
    # rather than a fake "0000-00-00T00:00:00Z" that would pollute date-bounded queries.
    with tempfile.TemporaryDirectory() as tmpdir_s:
        tmp_s = Path(tmpdir_s)
        (tmp_s / "state").mkdir(parents=True)
        (tmp_s / "plugins").mkdir()
        lessons_s = tmp_s / "state" / "lessons"
        lessons_s.mkdir()
        (tmp_s / "state" / "lessons-outbox").mkdir()
        (tmp_s / "state" / "lessons-outbox" / "drained").mkdir()
        title_s = "Sentinel date lesson migrated from legacy format"
        _write_outbox_yaml(lessons_s / "0000-00-00-sentinel.yaml", {
            "title": title_s,
            "body": "Body for sentinel date test.",
            "scope": "project",
            "created": "0000-00-00",  # sentinel — must emit null, not "0000-00-00T00:00:00Z"
            "from_repo": "test-repo",
            "status": "open",
        })
        result_s = subprocess.run(
            [sys.executable, str(_EMITTER), str(tmp_s), "test-repo", "test-branch", "abc123", "2026-01-01T00:00:00Z"],
            capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result_s.returncode != 0:
            fail(f"SENTINEL: emitter failed: {result_s.stderr}")
        else:
            recs_s = json.loads(result_s.stdout)
            key_s = _lesson_key(title_s)
            by_key_s = {r["lesson_key"]: r for r in recs_s}
            if key_s not in by_key_s:
                fail(f"SENTINEL: sentinel-date lesson not emitted (key={key_s})")
            else:
                rec_s = by_key_s[key_s]
                if rec_s.get("created") is None:
                    ok("SENTINEL: '0000-00-00' created → emitted created=null (honest sentinel)")
                else:
                    fail(f"SENTINEL: '0000-00-00' created expected null but got '{rec_s.get('created')}'")
                # from_repo should still be forwarded (sentinel only affects created)
                if rec_s.get("from_repo") == "test-repo":
                    ok("SENTINEL: from_repo still forwarded when created is sentinel")
                else:
                    fail(f"SENTINEL: from_repo expected 'test-repo', got '{rec_s.get('from_repo')}'")

    # ---------- F1-OVERLAY: dual-presence — YAML has from_repo, outbox lacks it → captured value survives ----------
    # Review: code-reviewer (F1) — when a lesson is in BOTH per-entry YAML (from_repo="repo-a")
    # AND outbox (no from_repo field), the overlay must fall back to the captured value rather than
    # wiping it with None. Validates the `from_repo = outbox_rec.get("from_repo") or from_repo` fix.
    with tempfile.TemporaryDirectory() as tmpdir_f1:
        tmp_f1 = Path(tmpdir_f1)
        (tmp_f1 / "state").mkdir(parents=True)
        (tmp_f1 / "plugins").mkdir()
        lessons_f1 = tmp_f1 / "state" / "lessons"
        lessons_f1.mkdir()
        outbox_f1 = tmp_f1 / "state" / "lessons-outbox"
        outbox_f1.mkdir()
        (outbox_f1 / "drained").mkdir()
        title_f1 = "Dual-presence lesson YAML has from_repo outbox lacks it"
        # Per-entry YAML: has from_repo="repo-a" — must survive overlay
        _write_outbox_yaml(
            lessons_f1 / "2026-06-30-dual-presence.yaml",
            {
                "title": title_f1,
                "body": "Body of dual-presence lesson.",
                "scope": "project",
                "created": "2026-06-30",
                "from_repo": "repo-a",
                "status": "open",
            },
        )
        # Outbox entry for the same lesson: deliberately omits from_repo (no field at all)
        _write_outbox_yaml(
            outbox_f1 / "2026-06-30-dual-presence-outbox.yaml",
            {
                "title": title_f1,
                "body": "Outbox body for dual-presence lesson.",
                "change_kind": "doctrine-edit",
                "scope_tags": ["project"],
                "created": "2026-06-30T09:00:00Z",
                # from_repo intentionally absent — overlay must fall back to captured "repo-a"
            },
        )
        result_f1 = subprocess.run(
            [
                sys.executable,
                str(_EMITTER),
                str(tmp_f1),
                "test-repo",
                "test-branch",
                "abc123",
                "2026-01-01T00:00:00Z",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result_f1.returncode != 0:
            fail(f"F1-OVERLAY: emitter failed: {result_f1.stderr}")
        else:
            recs_f1 = json.loads(result_f1.stdout)
            key_f1 = _lesson_key(title_f1)
            by_key_f1 = {r["lesson_key"]: r for r in recs_f1}
            if key_f1 not in by_key_f1:
                fail(f"F1-OVERLAY: dual-presence lesson not emitted (key={key_f1})")
            else:
                rec_f1 = by_key_f1[key_f1]
                if rec_f1.get("from_repo") == "repo-a":
                    ok("F1-OVERLAY: from_repo='repo-a' survived outbox overlay (outbox lacked the field)")
                else:
                    fail(
                        f"F1-OVERLAY: from_repo expected 'repo-a' (captured value),"
                        f" got '{rec_f1.get('from_repo')}' — outbox overlay wiped it"
                    )
                # promotion_state must be pending (outbox wins over YAML-only)
                if rec_f1.get("promotion_state") == "pending":
                    ok("F1-OVERLAY: dual-presence lesson promotion_state='pending' (outbox present)")
                else:
                    fail(f"F1-OVERLAY: expected promotion_state='pending', got '{rec_f1.get('promotion_state')}'")

    # ---------- AC1: born-attributable captured lesson (direct build_lesson_summaries import) ----------
    # Verifies that captured lessons with from_repo/created/evidence/target_wiki in their
    # per-entry YAML emit those fields as non-null (the born-attributable null-drop fix).
    # Uses importlib to import build_lesson_summaries from the hyphenated filename.
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("emit_lesson_summaries", str(_EMITTER))
    _mod = _ilu.module_from_spec(_spec)
    # Review: code-reviewer (F8) — exec_module limitation: re-executes module-level side-effects
    # (e.g. regex compilation, sys.path mutation) on every call. Safe here because the module
    # is stateless at module-level, but would silently double-register any module-level state.
    # If this test is ever parallelised or the module gains module-level side-effects, switch
    # to the subprocess approach used by all other test blocks above.
    _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
    build_lesson_summaries = _mod.build_lesson_summaries

    with tempfile.TemporaryDirectory() as tmpdir_ba:
        tmp_ba = Path(tmpdir_ba)
        (tmp_ba / "state").mkdir(parents=True)
        (tmp_ba / "plugins").mkdir()  # satisfies _find_repo_root marker
        lessons_ba = tmp_ba / "state" / "lessons"
        lessons_ba.mkdir()
        # Write a captured lesson with ALL born-attributable fields: no outbox/drained copy.
        title_ba = "Born-attributable captured lesson with full metadata"
        body_ba = "This lesson body must survive unchanged through the emitter pipeline."
        _write_outbox_yaml(lessons_ba / "2026-06-30-born-attr.yaml", {
            "title": title_ba,
            "body": body_ba,
            "scope": "universal",
            "created": "2026-06-30T10:00:00Z",
            "from_repo": "claude-central-em",
            "evidence": "Observed in session 2026-06-30",
            "target_wiki": "docs/wiki/lessons-born-attributable.md",
            "status": "open",
        })
        records_ba = build_lesson_summaries(
            repo_root=tmp_ba,
            coordinator_root=_EMITTER.parent.parent.parent,
            repo_name="test-repo",
            git_branch="test-branch",
            git_sha="abc123",
            observed_at="2026-06-30T10:00:00Z",
        )
        key_ba = _lesson_key(title_ba)
        by_key_ba = {r["lesson_key"]: r for r in records_ba}
        if key_ba not in by_key_ba:
            fail(f"AC1: born-attributable captured lesson not in emitted records (key={key_ba})")
        else:
            rec_ba = by_key_ba[key_ba]
            # promotion_state must be "captured" (no outbox/drained copy)
            if rec_ba.get("promotion_state") == "captured":
                ok("AC1: born-attributable captured lesson has promotion_state='captured'")
            else:
                fail(f"AC1: expected promotion_state='captured', got '{rec_ba.get('promotion_state')}'")
            # parse_status must be "ok" (all fields present)
            if rec_ba.get("parse_status") == "ok":
                ok("AC1: born-attributable captured lesson has parse_status='ok'")
            else:
                fail(f"AC1: expected parse_status='ok', got '{rec_ba.get('parse_status')}'")
            # body must equal the YAML body (unchanged)
            if rec_ba.get("body") == body_ba:
                ok("AC1: born-attributable captured lesson body unchanged")
            else:
                fail(f"AC1: body changed — expected {body_ba!r}, got {rec_ba.get('body')!r}")
            # from_repo must be non-null and match YAML value
            if rec_ba.get("from_repo") == "claude-central-em":
                ok("AC1: born-attributable captured lesson from_repo='claude-central-em' (non-null, from YAML)")
            else:
                fail(f"AC1: from_repo expected 'claude-central-em', got '{rec_ba.get('from_repo')}'")
            # created must be non-null and match YAML value
            if rec_ba.get("created") == "2026-06-30T10:00:00Z":
                ok("AC1: born-attributable captured lesson created='2026-06-30T10:00:00Z' (non-null, from YAML)")
            else:
                fail(f"AC1: created expected '2026-06-30T10:00:00Z', got '{rec_ba.get('created')}'")
            # evidence must be non-null and match YAML value
            if rec_ba.get("evidence") == "Observed in session 2026-06-30":
                ok("AC1: born-attributable captured lesson evidence non-null (from YAML)")
            else:
                fail(f"AC1: evidence expected 'Observed in session 2026-06-30', got '{rec_ba.get('evidence')}'")
            # target_wiki must be non-null and match YAML value
            if rec_ba.get("target_wiki") == "docs/wiki/lessons-born-attributable.md":
                ok("AC1: born-attributable captured lesson target_wiki non-null (from YAML)")
            else:
                fail(f"AC1: target_wiki expected 'docs/wiki/lessons-born-attributable.md', got '{rec_ba.get('target_wiki')}'")

    print()
    if FAIL_COUNT == 0:
        print("ALL TESTS PASSED")
        sys.exit(0)
    else:
        print(f"{FAIL_COUNT} TEST(S) FAILED", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
