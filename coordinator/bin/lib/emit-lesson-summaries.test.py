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
import textwrap
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
      A: "Clean lesson in lessons.md only"              (captured, universal)
      B: "Lesson in lessons.md and outbox"              (pending — outbox wins)
      C: "Lesson in lessons.md and drained"             (drained — drained wins)
      D: "Drained-only lesson not in lessons.md"        (drained — AC6 load-bearing)
      E: "Outbox-only lesson with empty body"            (pending, partial — outbox-only, no body — AC7)
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

    # Write lessons.md — does NOT include title_D or title_E
    lessons_md = state / "lessons.md"
    lessons_md.write_text(textwrap.dedent(f"""\
        - **{title_A}** [universal] 2026-01-01
        This is the body of lesson A. It covers a clean capture.

        - **{title_B}** 2026-01-02
        Body of lesson B. This one also has a pending outbox entry.

        - **{title_C}** [universal] 2026-01-03
        Body of lesson C. This one also has a drained outbox entry.
        """), encoding="utf-8")

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
            if rec_B.get("created") is not None:
                ok("AC8b: created field populated from outbox")
            else:
                fail("AC8b: created should be non-null for pending lesson")
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

        # ---------- AC8d: captured-only nullable fields ----------
        if titles["key_A"] in by_key:
            rec_A = by_key[titles["key_A"]]
            null_fields = ["change_kind", "target_wiki", "from_repo", "created"]
            for field in null_fields:
                if field in rec_A and rec_A[field] is None:
                    ok(f"AC8d: captured-only has {field}=null")
                elif field not in rec_A:
                    fail(f"AC8d: captured-only is missing field '{field}' (must be present-as-null per D9)")
                else:
                    fail(f"AC8d: captured-only {field} should be null but is '{rec_A[field]}'")
            # scope should still be set from [universal] tag
            if rec_A.get("scope") == "universal":
                ok("AC8d: captured-only scope='universal' from [universal] tag")
            else:
                fail(f"AC8d: expected scope='universal' from [universal] tag, got '{rec_A.get('scope')}'")

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
            print(f"warn: validator not found at {_VALIDATOR}, skipping schema validation")

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

    print()
    if FAIL_COUNT == 0:
        print("ALL TESTS PASSED")
        sys.exit(0)
    else:
        print(f"{FAIL_COUNT} TEST(S) FAILED", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
