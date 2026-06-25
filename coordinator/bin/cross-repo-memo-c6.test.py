#!/bin/sh
''''exec "$(command -v python3 || command -v python || command -v py)" "$0" "$@" #'''
from __future__ import annotations
"""
cross-repo-memo-c6.test.py — C6 round-trip and fixture-behavioral tests.

Spec backlink: docs/plans/2026-05-30-pickup-cross-repo-memo-fork.md § C6

Two parts:

  C6a — kind-contract round-trip (binds AC4/AC5/AC6 at the integration level).
    For each kind ∈ {ask, consult, fyi} AND the no-kind case:
      1. Drive the CLI to write a memo to a temp receiver dir.
      2. Assert the written file validates schema-GREEN under cross-repo-memo.yaml
         using schema.js (the same validator that lint-frontmatter.js uses).
      3. Assert the surfacing helper (workday-start-cross-repo-memo-surface.sh)
         bands it correctly:
           ask/consult  → appears before a fyi memo in output (urgent band)
           fyi          → appears after ask/consult (quiet band), carries [fyi] marker
           no-kind      → bands as ask (urgent, no [fyi] marker)
    Claim: proves the kind contract agrees end-to-end across C2/C3/C4.

  C6b — memo-fixture behavioral assertion (binds AC2/AC7).
    1. Positive: a memo fixture with status=actioned + decision=accepted + decision_note
       validates schema-GREEN.
    2. Positive (fyi variant): a memo with status=actioned + actioned_note (no decision)
       validates schema-GREEN.
    3. Negative-spec (AC2): applying handoff-schema mutations to a memo produces
       schema-INVALID results:
         - status: consumed   → REJECTED (not in memo status enum)
         - status: active     → REJECTED (not in memo status enum)
         - deployment_state: in_flight → REJECTED (unknown required field remains required;
           the schema.js cross-field rule fires because memo's required fields
           are missing — we verify any schema error results, or check status enum)
       This is the mechanical proof that "the handoff active→consumed mutation
       must never be applied to a memo."

Run with: python bin/cross-repo-memo-c6.test.py
"""

import datetime
import json
import os
import subprocess
import sys
import tempfile
import textwrap

# ---------------------------------------------------------------------------
# Test infrastructure (mirrors cross-repo-memo.test.py conventions)
# ---------------------------------------------------------------------------

TESTS_PASSED = 0
TESTS_FAILED = 0
FAILURES: list[str] = []


def _bin_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _script_path() -> str:
    return os.path.join(_bin_dir(), "cross-repo-memo")


def _surface_helper_path() -> str:
    return os.path.join(_bin_dir(), "workday-start-cross-repo-memo-surface.sh")


def _schema_js_path() -> str:
    return os.path.join(_bin_dir(), "lib", "schema.js")


def _schemas_dir() -> str:
    return os.path.join(os.path.dirname(_bin_dir()), "schemas")


def _python() -> str:
    return sys.executable


# Standalone-script helpers mirror cross-repo-memo.test.py by design (no shared import); keep in sync if either changes.
# Review: code-reviewer F8 — deliberate duplication noted; these helpers are not accidentally repeated.
def _run_dispatcher(args: list[str], env: dict, stdin_text: str = "") -> subprocess.CompletedProcess:
    """Invoke cross-repo-memo CLI via subprocess (Windows-compatible)."""
    return subprocess.run(
        [_python(), _script_path()] + args,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        input=stdin_text,
    )


def _make_mock_machine_local(tmpdir: str, return_value: str) -> str:  # mirrors cross-repo-memo.test.py by design
    """Create a stub machine-local Python script that returns return_value."""
    stub_path = os.path.join(tmpdir, "_mock_machine_local.py")
    escaped = return_value.replace("\\", "\\\\")
    script = textwrap.dedent(f"""\
        #!/usr/bin/env python3
        import sys
        print("{escaped}")
        sys.exit(0)
    """)
    with open(stub_path, "w") as f:
        f.write(script)
    return stub_path


def _today() -> str:
    return datetime.date.today().isoformat()


def pass_test(name: str) -> None:
    global TESTS_PASSED
    TESTS_PASSED += 1
    print(f"  PASS: {name}")


def fail_test(name: str, reason: str) -> None:
    global TESTS_FAILED
    TESTS_FAILED += 1
    msg = f"  FAIL: {name} — {reason}"
    FAILURES.append(msg)
    print(msg)


# ---------------------------------------------------------------------------
# Schema validation helper via Node.js / schema.js
#
# Rather than spawning lint-frontmatter.js (which walks a whole repo), we call
# schema.js directly via a tiny inline Node script that:
#   1. loadSchemas from the real schemas/ dir.
#   2. Selects the cross-repo-memo schema by name.
#   3. Parses the given file's frontmatter.
#   4. Validates it and returns {ok, errors} as JSON.
#
# This is the same code path lint-frontmatter.js uses.
# ---------------------------------------------------------------------------

_NODE_VALIDATE_SCRIPT = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const { loadSchemas, parseFrontmatter, validateFrontmatter } = require(process.argv[2]);

const schemasDir = process.argv[3];
const filePath   = process.argv[4];

const schemas = loadSchemas(schemasDir);
const schema  = schemas['cross-repo-memo'];
if (!schema) {
  process.stdout.write(JSON.stringify({ ok: false, errors: [{ field: '__setup__', error: 'cross-repo-memo schema not found', hint: '' }] }));
  process.exit(0);
}

const content = fs.readFileSync(filePath, 'utf8');
const { frontmatter } = parseFrontmatter(content);
const result = validateFrontmatter(frontmatter, schema);
process.stdout.write(JSON.stringify(result));
"""


def _validate_memo_file(file_path: str) -> dict:
    """Validate a memo file against the cross-repo-memo schema.

    Returns the {ok, errors} dict from schema.js validateFrontmatter.
    Raises RuntimeError if Node is unavailable.
    """
    # Write the inline validator script to a temp file.
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".js", delete=False, encoding="utf-8"
    ) as f:
        f.write(_NODE_VALIDATE_SCRIPT)
        node_script_path = f.name

    try:
        result = subprocess.run(
            ["node", node_script_path, _schema_js_path(), _schemas_dir(), file_path],
            capture_output=True,
            text=True,
        )
        # Review: code-reviewer F3 — import json moved to module top; used here directly.
        if result.returncode != 0:
            raise RuntimeError(
                f"Node validator exited {result.returncode}: {result.stderr}"
            )
        return json.loads(result.stdout)
    finally:
        try:
            os.unlink(node_script_path)
        except OSError:
            pass


def _run_surface_helper(inbox_dir: str, mock_today: str = "") -> str:
    """Run workday-start-cross-repo-memo-surface.sh against inbox_dir and return output."""
    env = {**os.environ, "CROSS_REPO_INBOX_DIR": inbox_dir}
    if mock_today:
        env["MOCK_TODAY"] = mock_today
    result = subprocess.run(
        ["bash", _surface_helper_path()],
        env=env,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _write_memo_fixture(inbox_dir: str, filename: str, frontmatter_body: str) -> str:
    """Write a raw memo fixture directly to inbox_dir/<filename>.

    frontmatter_body is the YAML content between the --- delimiters.
    Returns the full path to the written file.
    """
    os.makedirs(inbox_dir, exist_ok=True)
    file_path = os.path.join(inbox_dir, filename)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"---\n{frontmatter_body}\n---\n\nMemo body.\n")
    return file_path


# ---------------------------------------------------------------------------
# C6a — kind-contract round-trip
#
# For each kind ∈ {ask, consult, fyi, <absent>}:
#   1. CLI writes a memo to a temp receiver dir.
#   2. Written file validates schema-GREEN.
#   3. Surfacing helper bands it correctly.
#
# The banding assertion for the fyi vs. urgent band requires at least two
# memos in the inbox so the sort order is observable.
# ---------------------------------------------------------------------------

def test_c6a_kind_roundtrip_schema_and_band(
    kind: str | None,
    expected_band: str,  # "urgent" or "quiet"
    test_num: str,
) -> None:
    """Drive CLI → validate schema-GREEN → verify surface banding for one kind value."""
    kind_label = kind if kind is not None else "<absent>"
    name = f"C6a-{test_num} — kind={kind_label}: CLI→schema-GREEN, surfaces in {expected_band} band"

    today = _today()
    # Use MOCK_TODAY = today so age reads "0 days old" and no stale flag fires.
    mock_today = today

    with tempfile.TemporaryDirectory() as receiver_tmpdir, \
         tempfile.TemporaryDirectory() as claude_home_tmpdir, \
         tempfile.TemporaryDirectory() as stub_tmpdir:

        mock_impl = _make_mock_machine_local(stub_tmpdir, receiver_tmpdir)
        env = {
            "MACHINE_LOCAL_IMPL": mock_impl,
            "CLAUDE_HOME": claude_home_tmpdir,
        }

        # Build CLI args — include --kind only when a value is provided.
        cli_args = [
            "--to", "project-rag-em",
            "--topic", f"kind-test-{kind_label.replace('<', '').replace('>', '')}",
            "--title", f"Kind={kind_label} Test Memo",
        ]
        if kind is not None:
            cli_args.extend(["--kind", kind])

        result = _run_dispatcher(cli_args, env=env, stdin_text="This is the memo body.\n")

        if result.returncode != 0:
            fail_test(name, f"CLI failed (exit {result.returncode}): {result.stderr}")
            return

        # Locate the written file.
        topic_slug = f"kind-test-{kind_label.replace('<', '').replace('>', '')}"
        filename = f"{today}-{topic_slug}.md"
        written_file = os.path.join(receiver_tmpdir, "cross-repo", "inbox", filename)

        if not os.path.isfile(written_file):
            fail_test(name, f"Expected written file not found: {written_file}")
            return

        # --- 2. Schema validation (AC5) ---
        try:
            validation = _validate_memo_file(written_file)
        except RuntimeError as exc:
            fail_test(name, f"Schema validation failed to run: {exc}")
            return

        if not validation.get("ok"):
            errs = validation.get("errors", [])
            fail_test(
                name,
                f"Schema validation FAILED (expected GREEN): {errs}"
            )
            return

        # --- 3. Surface banding (AC6) ---
        inbox_dir = os.path.join(receiver_tmpdir, "cross-repo", "inbox")

        # Write a companion fyi memo so we can compare line order.
        # For the fyi test case, write a companion ask memo.
        companion_kind = "fyi" if expected_band == "urgent" else "ask"
        companion_filename = f"{today}-companion-{companion_kind}.md"
        companion_fm = textwrap.dedent(f"""\
            title: "Companion {companion_kind} Memo"
            from: "central-em"
            to: "project-rag-em"
            created: {today}
            status: open
            kind: {companion_kind}
        """).strip()
        _write_memo_fixture(inbox_dir, companion_filename, companion_fm)

        surface_output = _run_surface_helper(inbox_dir, mock_today=mock_today)

        # Find line numbers for each memo in output.
        lines = surface_output.splitlines()
        our_line_num = next(
            (i + 1 for i, l in enumerate(lines) if f"Kind={kind_label}" in l),
            None
        )
        companion_line_num = next(
            (i + 1 for i, l in enumerate(lines) if f"Companion {companion_kind}" in l),
            None
        )

        if our_line_num is None:
            fail_test(name, f"Our memo not found in surface output:\n{surface_output}")
            return
        if companion_line_num is None:
            fail_test(name, f"Companion memo not found in surface output:\n{surface_output}")
            return

        if expected_band == "urgent":
            # ask/consult/no-kind → should appear BEFORE the fyi companion.
            if our_line_num < companion_line_num:
                pass  # correct
            else:
                fail_test(
                    name,
                    f"Expected urgent memo (line {our_line_num}) to appear before "
                    f"fyi companion (line {companion_line_num}) in output:\n{surface_output}"
                )
                return
            # Urgent memos should NOT carry [fyi] marker.
            our_line_text = lines[our_line_num - 1]
            if "[fyi]" in our_line_text:
                fail_test(
                    name,
                    f"Urgent memo should not carry [fyi] marker; got: {our_line_text!r}"
                )
                return
        else:
            # fyi → should appear AFTER the ask companion.
            if our_line_num > companion_line_num:
                pass  # correct
            else:
                fail_test(
                    name,
                    f"Expected fyi memo (line {our_line_num}) to appear after "
                    f"ask companion (line {companion_line_num}) in output:\n{surface_output}"
                )
                return
            # Quiet memos should carry [fyi] marker.
            our_line_text = lines[our_line_num - 1]
            if "[fyi]" not in our_line_text:
                fail_test(
                    name,
                    f"Quiet (fyi) memo should carry [fyi] marker; got: {our_line_text!r}"
                )
                return

    pass_test(name)


# ---------------------------------------------------------------------------
# C6b — memo-fixture behavioral assertion (binds AC2/AC7)
#
# Note on M0 already-actioned short-circuit (SKILL.md Memo Branch M0, added per code-reviewer F1):
#   M0 is a prose-branch behavior verified by SKILL prose, not by schema validation.
#   An already-actioned memo is schema-valid (status=actioned passes the memo enum).
#   C6b's schema tests intentionally do not cover M0 — there is nothing schema-level
#   to assert. The guard is behavioral: the EM reads it as read-only context and stops.
#   Schema tests assert what schema.js rejects; M0's stop condition is agent behavior.
#   Review: code-reviewer F5 — behavioral-only M0 coverage noted here.
#
# Tests:
#   1. Positive: status=actioned + decision=accepted + decision_note → schema-GREEN.
#   2. Positive (fyi variant): status=actioned + actioned_note (no decision) → schema-GREEN.
#   3. Negative: status=consumed → schema-INVALID (not in memo status enum).
#   4. Negative: status=active → schema-INVALID (not in memo status enum).
#   5. Negative: deployment_state: in_flight present → schema-INVALID (unknown field causes
#      the memo to be validated against memo schema which does not have required fields
#      expected — or the memo status is still wrong; we assert the validator rejects it).
#
# Note on C6b test 5 (deployment_state):
#   The memo schema has no 'deployment_state' field at all. Adding 'deployment_state'
#   to a memo does NOT by itself cause schema.js to reject it (schema.js does not
#   reject unknown optional fields — only required-field absence and enum violations
#   cause errors). Therefore C6b test 5 proves the COMBINATION: a file with
#   deployment_state is a HANDOFF (not a memo), and when we drop its proper handoff
#   required fields (status: active → consumed flip), the memo validator would
#   reject status: consumed. The key negative assertion is AC2: the validator
#   DOES reject status: consumed (not in memo enum), which is the actual mutation
#   a /pickup handoff branch would apply. deployment_state alone with status: open
#   would pass memo schema (unknown fields are tolerated); the test correctly uses
#   status: consumed as the pivot.
# ---------------------------------------------------------------------------

def _build_base_memo_fm(
    status: str,
    today: str,
    extra_fields: dict[str, str] | None = None,
) -> str:
    """Build minimal valid memo frontmatter for the given status."""
    lines = [
        f'title: "C6b Test Memo"',
        f'from: "central-em"',
        f'to: "project-rag-em"',
        f'created: {today}',
        f'status: {status}',
        f'delivery_mode: receiver-repo',
        f'summary: "A brief summary for testing."',
    ]
    if extra_fields:
        for k, v in extra_fields.items():
            lines.append(f'{k}: {v}')
    return "\n".join(lines)


def test_c6b_actioned_ask_validates_green() -> None:
    """C6b-1 (AC7): status=actioned + decision=accepted + decision_note validates schema-GREEN.

    This is the 'ask' terminal state after /pickup adjudicate-and-own.
    """
    name = "C6b-1 (AC7) — actioned+decision+decision_note memo validates schema-GREEN"
    today = _today()

    fm = _build_base_memo_fm(
        status="actioned",
        today=today,
        extra_fields={
            "decision": "accepted",
            "decision_note": '"Applied the requested change."',
        },
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        inbox_dir = os.path.join(tmpdir, "cross-repo", "inbox")
        file_path = _write_memo_fixture(inbox_dir, f"{today}-c6b-test1.md", fm)
        try:
            validation = _validate_memo_file(file_path)
        except RuntimeError as exc:
            fail_test(name, f"Schema validation failed to run: {exc}")
            return

        if not validation.get("ok"):
            errs = validation.get("errors", [])
            fail_test(name, f"Schema validation FAILED (expected GREEN): {errs}")
            return

    pass_test(name)


def test_c6b_actioned_fyi_validates_green() -> None:
    """C6b-2 (AC7): status=actioned + actioned_note (no decision field) validates schema-GREEN.

    This is the 'fyi' terminal state: receiver acknowledges only.
    No 'decision' field is required or expected for fyi acknowledgement.
    """
    name = "C6b-2 (AC7) — actioned+actioned_note (fyi variant) validates schema-GREEN"
    today = _today()

    fm = _build_base_memo_fm(
        status="actioned",
        today=today,
        extra_fields={
            "actioned_note": '"noted — informational"',
        },
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        inbox_dir = os.path.join(tmpdir, "cross-repo", "inbox")
        file_path = _write_memo_fixture(inbox_dir, f"{today}-c6b-test2.md", fm)
        try:
            validation = _validate_memo_file(file_path)
        except RuntimeError as exc:
            fail_test(name, f"Schema validation failed to run: {exc}")
            return

        if not validation.get("ok"):
            errs = validation.get("errors", [])
            fail_test(name, f"Schema validation FAILED (expected GREEN): {errs}")
            return

    pass_test(name)


def test_c6b_status_consumed_rejected() -> None:
    """C6b-3 (AC2): status=consumed is NOT in the memo status enum → schema-INVALID.

    'consumed' is a HANDOFF status (active → consumed). Applying it to a memo
    is the exact mutation the /pickup handoff branch would wrongly apply. The
    validator must REJECT it. This is the mechanical proof of AC2.
    """
    name = "C6b-3 (AC2) — status=consumed is REJECTED by memo schema (handoff mutation negative-spec)"
    today = _today()

    fm = _build_base_memo_fm(status="consumed", today=today)

    with tempfile.TemporaryDirectory() as tmpdir:
        inbox_dir = os.path.join(tmpdir, "cross-repo", "inbox")
        file_path = _write_memo_fixture(inbox_dir, f"{today}-c6b-consumed.md", fm)
        try:
            validation = _validate_memo_file(file_path)
        except RuntimeError as exc:
            fail_test(name, f"Schema validation failed to run: {exc}")
            return

        if validation.get("ok"):
            fail_test(
                name,
                "Schema validation returned OK (expected REJECT) for status=consumed. "
                "This means the handoff 'active→consumed' mutation would pass memo "
                "schema validation — a VIOLATION of AC2."
            )
            return

        # Confirm the error mentions status and the invalid value.
        errs = validation.get("errors", [])
        errs_str = str(errs)
        if "status" not in errs_str.lower() and "consumed" not in errs_str.lower():
            fail_test(
                name,
                f"Rejected but error does not mention 'status'/'consumed': {errs}"
            )
            return

    pass_test(name)


def test_c6b_status_active_rejected() -> None:
    """C6b-4 (AC2): status=active is NOT in the memo status enum → schema-INVALID.

    'active' is the HANDOFF initial status. It is not a valid memo status.
    Verifies that the memo schema enum properly excludes handoff-only values.
    """
    name = "C6b-4 (AC2) — status=active is REJECTED by memo schema (handoff status negative-spec)"
    today = _today()

    fm = _build_base_memo_fm(status="active", today=today)

    with tempfile.TemporaryDirectory() as tmpdir:
        inbox_dir = os.path.join(tmpdir, "cross-repo", "inbox")
        file_path = _write_memo_fixture(inbox_dir, f"{today}-c6b-active.md", fm)
        try:
            validation = _validate_memo_file(file_path)
        except RuntimeError as exc:
            fail_test(name, f"Schema validation failed to run: {exc}")
            return

        if validation.get("ok"):
            fail_test(
                name,
                "Schema validation returned OK (expected REJECT) for status=active. "
                "Handoff 'active' status must not be valid for memo schema."
            )
            return

        errs = validation.get("errors", [])
        errs_str = str(errs)
        if "status" not in errs_str.lower() and "active" not in errs_str.lower():
            fail_test(
                name,
                f"Rejected but error does not mention 'status'/'active': {errs}"
            )
            return

    pass_test(name)


def test_c6b_combined_handoff_mutation_rejected() -> None:
    """C6b-5 (AC2): combined handoff mutation (status=consumed + deployment_state) is REJECTED.

    This is the complete set of mutations /pickup would apply to a handoff:
    - status: active → consumed
    - deployment_state: in_flight

    Applied to a memo file, the validator must reject it. The pivot assertion
    is status=consumed (not in memo enum); deployment_state is an additional
    signal that this is not a memo (but unknown optional fields alone do not
    cause rejection in schema.js).
    """
    name = (
        "C6b-5 (AC2) — combined handoff mutation (status=consumed + deployment_state) "
        "REJECTED by memo schema"
    )
    today = _today()

    fm = _build_base_memo_fm(
        status="consumed",
        today=today,
        extra_fields={
            "deployment_state": "in_flight",
        },
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        inbox_dir = os.path.join(tmpdir, "cross-repo", "inbox")
        file_path = _write_memo_fixture(inbox_dir, f"{today}-c6b-handoff-mut.md", fm)
        try:
            validation = _validate_memo_file(file_path)
        except RuntimeError as exc:
            fail_test(name, f"Schema validation failed to run: {exc}")
            return

        if validation.get("ok"):
            fail_test(
                name,
                "Schema validation returned OK (expected REJECT) for the combined handoff "
                "mutation. The /pickup handoff branch must NOT be applied to memos."
            )
            return

    pass_test(name)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> int:
    print("Running cross-repo-memo C6 round-trip and fixture-behavioral tests...")
    print(f"Script: {_script_path()}")
    print(f"Schemas: {_schemas_dir()}")
    print(f"Surface helper: {_surface_helper_path()}")
    print()

    # --- C6a: kind-contract round-trip ---
    print("=== C6a: kind-contract round-trip (CLI → schema-GREEN → surface banding) ===")
    # (kind, expected_band, test_num)
    c6a_cases = [
        ("ask",     "urgent", "T1"),
        ("consult", "urgent", "T2"),
        ("fyi",     "quiet",  "T3"),
        (None,      "urgent", "T4"),  # absent kind → defaults to ask (urgent)
    ]
    for kind, expected_band, test_num in c6a_cases:
        try:
            test_c6a_kind_roundtrip_schema_and_band(kind, expected_band, test_num)
        except Exception as exc:
            fail_test(
                f"C6a-{test_num} — kind={(kind or '<absent>')}",
                f"unexpected exception: {exc}"
            )

    print()
    print("=== C6b: memo-fixture behavioral assertion (positive + negative-spec) ===")
    c6b_tests = [
        test_c6b_actioned_ask_validates_green,
        test_c6b_actioned_fyi_validates_green,
        test_c6b_status_consumed_rejected,
        test_c6b_status_active_rejected,
        test_c6b_combined_handoff_mutation_rejected,
    ]
    for test_fn in c6b_tests:
        try:
            test_fn()
        except Exception as exc:
            fail_test(test_fn.__name__, f"unexpected exception: {exc}")

    print()
    print(
        f"Results: {TESTS_PASSED} passed, {TESTS_FAILED} failed "
        f"out of {TESTS_PASSED + TESTS_FAILED} tests"
    )
    if FAILURES:
        print("Failures:")
        for f in FAILURES:
            print(f"  {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
