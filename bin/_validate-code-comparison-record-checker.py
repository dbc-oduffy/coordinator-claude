#!/usr/bin/env python3
"""Schema-conformance + objectivity-spine checks for one code-comparison-record YAML file.

Invoked in-process by `validate-code-comparison-record.py` (same directory, by-path import — the
underscore prefix means this file gets no `coordinator/bin/*.cmd` launcher and is not registered
in `warm_entrypoint_allowlist.json`; it is an implementation detail of its sibling, not a standalone
entry point) — designed to be discovered by a future run-all-checks / make-test sweep, invoke
directly for now — this module does the actual YAML-shaped assertions since bash has no native
YAML parser. Not intended to be run standalone outside that wrapper, though it works stand-alone:
`python3 _validate-code-comparison-record-checker.py <path>`.

Spec backlink: coordinator/pipelines/deep-research/code-comparison-record-schema.md (DoE-claude).

Arrived from DoE-claude coordinator/pipelines/deep-research/fixtures/.validate-code-comparison-record-checker.py
(docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W3-C7). Pure stdlib + PyYAML, no
DoE-relative path derived from `__file__` — nothing to fix under § Path resolution.
"""
# Review: code-reviewer (C-F7) — softened "the discoverable entry point for a
# run-all-checks / make-test sweep" (present-tense fact) to "designed to be
# discovered... invoke directly for now" (intended/future) — no such sweep
# exists in-tree as of this review.

import re
import sys


SOURCEREF_KEYS = frozenset({"url", "fetch_date", "platform", "comment_id"})
VALID_TIERS = frozenset({"source_read", "artifact_forensic"})

# A fully-qualified permalink: scheme + host + /blob/<sha>/path#Lx-Ly. The schema
# requires this form whenever the target is a git repo with a resolvable SHA.
PERMALINK_RE = re.compile(r"^https?://[^/\s]+/.*/blob/[0-9a-f]{7,40}/.+#L\d+-L\d+$")
# The documented degradation for a target that is not a git repo or has no
# resolvable SHA: a bare local path#Lx-Ly fragment, no scheme, no host, no blob-sha.
LOCAL_FRAGMENT_RE = re.compile(r"^[^:\s]+#L\d+-L\d+$")
# The defect shape: a blob-sha citation that dropped its scheme and host.
BARE_BLOB_RE = re.compile(r"/?blob/[0-9a-f]{7,40}/")


def check_record(record, label: str = "") -> list[str]:
    """Every schema + objectivity-spine violation in one record body.

    `label` prefixes each message so a caller validating an emit file can say
    which entry failed; empty for a single-record file, where there is only one.
    """
    violations = []
    prefix = f"{label}: " if label else ""

    def require(condition, message):
        if not condition:
            violations.append(prefix + message)

    # Review: code-reviewer (C-F1) — a non-mapping record node (empty file -> None,
    # or a scalar) must fail as a clean VIOLATION, not an uncaught TypeError from
    # `field in record` on a non-mapping.
    if not isinstance(record, dict):
        violations.append(
            f"{prefix}record must be a mapping, got {type(record).__name__}"
        )
        return violations

    # (1) All required fields present.
    required_top = [
        "repo", "signal_id", "axis", "peer_ref", "observation",
        "confidence", "analysis", "observed_at", "provenance",
    ]
    for field in required_top:
        require(field in record, f"missing required top-level field: {field}")

    observation = record.get("observation", {}) or {}
    for side in ("peer", "subject"):
        side_obj = observation.get(side, {}) or {}
        require("state" in side_obj, f"observation.{side}.state missing")
        require("evidence" in side_obj, f"observation.{side}.evidence missing")
        evidence = side_obj.get("evidence", []) or []
        # Review: code-reviewer (C-F6) — evidence must be a list before len()/iteration;
        # a scalar string (len()>=1 true) would otherwise iterate over characters and
        # crash with AttributeError on ref.get(...) below.
        require(isinstance(evidence, list), f"observation.{side}.evidence must be a list")
        if isinstance(evidence, list):
            # `evidence: []` is legal — the explicit-absence exception (schema doc
            # § observation.peer / observation.subject). A side documenting a
            # searched-but-absent finding carries the absence in `state`, not in a
            # fabricated citation, so an empty list is not a violation here.
            for i, ref in enumerate(evidence):
                if not isinstance(ref, dict):
                    require(False, f"observation.{side}.evidence[{i}] must be a SourceRef mapping")
                    continue
                for ref_field in SOURCEREF_KEYS:
                    require(
                        ref_field in ref,
                        f"observation.{side}.evidence[{i}].{ref_field} missing"
                        + (" (must be present, null if not comment-scoped)" if ref_field == "comment_id" else ""),
                    )
                # SourceRef is a closed shape — market-intel's counterpart is
                # extra="forbid", so an invented key is rejected at ingest. Catch it
                # here instead, where the emitting side can still fix it.
                for extra_key in sorted(set(ref) - SOURCEREF_KEYS):
                    require(
                        False,
                        f"observation.{side}.evidence[{i}] carries unknown key {extra_key!r} — "
                        "SourceRef is exactly {url, fetch_date, platform, comment_id}",
                    )

            # evidence_tier: required iff the side carries evidence, absent when it
            # does not — there is nothing to qualify. No default-fill: an untiered
            # record serializes identically to a properly-tiered one.
            tier = side_obj.get("evidence_tier")
            if evidence:
                require(
                    tier in VALID_TIERS,
                    f"observation.{side}.evidence_tier '{tier}' not in {sorted(VALID_TIERS)} "
                    "(required whenever that side's evidence is non-empty)",
                )
            else:
                require(
                    "evidence_tier" not in side_obj,
                    f"observation.{side}.evidence_tier must be absent when evidence is empty",
                )

    require("verdict" in observation, "observation.verdict missing")
    require(
        "verdict" not in record,
        "verdict MUST NOT appear at the record top level — it is observation.verdict, nested",
    )

    provenance = record.get("provenance", {}) or {}
    require(provenance.get("source_kind") == "code_comparison", "provenance.source_kind must equal 'code_comparison'")
    derivation = provenance.get("derivation", "")
    require(
        isinstance(derivation, str) and derivation.startswith("doe-deep-research/code-compare@"),
        "provenance.derivation must match 'doe-deep-research/code-compare@<run-id>'",
    )

    # (2) verdict in {MEETS, LAGS, BEATS, INDETERMINATE}; confidence in {HIGH, MEDIUM, LOW}.
    valid_verdicts = {"MEETS", "LAGS", "BEATS", "INDETERMINATE"}
    valid_confidence = {"HIGH", "MEDIUM", "LOW"}

    verdict = observation.get("verdict")
    require(verdict in valid_verdicts, f"observation.verdict '{verdict}' not in {sorted(valid_verdicts)}")

    confidence = record.get("confidence")
    require(confidence in valid_confidence, f"confidence '{confidence}' not in {sorted(valid_confidence)}")

    # (3) Evidence url is a fully-qualified permalink, or the documented bare-path
    # degradation — never a scheme-less blob-sha fragment, which is the shape a
    # hand-transcribed record drifts into and which no downstream consumer validates.
    for side in ("peer", "subject"):
        side_obj = observation.get(side, {}) or {}
        side_evidence = side_obj.get("evidence", []) or []
        # Review: code-reviewer (C-F6, mirrored) — guard evidence shape here too,
        # since this loop re-derives `evidence` independently of the presence-check
        # loop above.
        if not isinstance(side_evidence, list):
            continue
        for i, ref in enumerate(side_evidence):
            if not isinstance(ref, dict):
                continue
            url = ref.get("url", "")
            # Review: code-reviewer (C-F3) — url must be a string before regex
            # search; a schema-shaped-but-wrong-typed value (int/list) would
            # otherwise raise TypeError instead of a clean VIOLATION.
            require(isinstance(url, str), f"observation.{side}.evidence[{i}].url must be a string")
            if not isinstance(url, str):
                continue
            # Review: code-reviewer (C-F5) — strip trailing whitespace before
            # matching so a copy-paste artifact reports as a distinguishable
            # violation rather than a generic shape mismatch.
            stripped_url = url.strip()
            whitespace_note = (
                " (has leading/trailing whitespace; judged after stripping)"
                if stripped_url != url
                else ""
            )
            if PERMALINK_RE.match(stripped_url):
                continue
            if BARE_BLOB_RE.search(stripped_url):
                require(
                    False,
                    f"observation.{side}.evidence[{i}].url is a scheme-less blob-sha fragment"
                    f"{whitespace_note}: {url!r} — a git target with a resolvable SHA takes a "
                    "fully-qualified https://<host>/<owner>/<repo>/blob/<sha>/path#Lx-Ly permalink",
                )
                continue
            require(
                bool(LOCAL_FRAGMENT_RE.match(stripped_url)),
                f"observation.{side}.evidence[{i}].url{whitespace_note} is neither a "
                f"fully-qualified permalink nor a bare path#Lx-Ly fragment: {url!r}",
            )

    # (4) peer_ref present (non-empty).
    peer_ref = record.get("peer_ref")
    require(isinstance(peer_ref, str) and peer_ref.strip() != "", "peer_ref must be present and non-empty")

    # (5) competitor_uid ABSENT (negative-spec 1 — DoE never emits this field).
    require("competitor_uid" not in record, "competitor_uid MUST be absent from a DoE-emitted record (negative-spec 1)")

    # (6) AC6 objectivity: analysis contains no recommendation/imperative tokens.
    recommendation_token_patterns = [
        r"\badopt\b", r"\badapt\b", r"\bdefer\b", r"\bshould\b",
        r"\brecommend\b", r"\brecommends\b", r"\brecommended\b",
        r"\bwe should\b", r"\bmust adopt\b", r"\bought to\b",
        r"\bneeds? to\b",
    ]
    analysis_text = record.get("analysis", "") or ""
    # Review: code-reviewer (C-F2) — analysis must be a string before the
    # token-search loop, mirroring the `derivation` isinstance guard above;
    # a non-string truthy value (YAML list/dict) would otherwise raise
    # TypeError from re.search instead of a clean VIOLATION.
    require(isinstance(analysis_text, str), "analysis must be a string")
    if isinstance(analysis_text, str):
        for token_pattern in recommendation_token_patterns:
            if re.search(token_pattern, analysis_text, flags=re.IGNORECASE):
                violations.append(
                    f"{prefix}analysis contains recommendation/imperative language "
                    f"matching /{token_pattern}/ — analysis must be an annotation, "
                    "never a recommendation (negative-spec)"
                )

    return violations


def main(argv: "list[str] | None" = None) -> int:
    import yaml

    argv = sys.argv if argv is None else argv
    if len(argv) != 2:
        print("usage: _validate-code-comparison-record-checker.py <record.yaml>", file=sys.stderr)
        return 1

    path = argv[1]
    with open(path, "r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f)

    # Both shapes the schema defines are accepted, because the schema tells
    # emitters to run this against the file they are about to emit, and that
    # file is a sequence: § "One record, and a file of records are different
    # shapes" (one record body = a mapping) and § Downstream emit (an emit file
    # = a top-level sequence of those bodies). Rejecting the sequence made the
    # documented last step of every run fail with a violation that reads as
    # "your records are malformed" when the records are fine.
    if isinstance(loaded, list):
        if not loaded:
            print("  VIOLATION: emit file holds an empty sequence — no records to validate",
                  file=sys.stderr)
            return 1
        violations = []
        for i, record in enumerate(loaded):
            violations.extend(check_record(record, label=f"record[{i}]"))
        scope = f"{len(loaded)} record(s)"
    else:
        violations = check_record(loaded)
        scope = "1 record"

    if violations:
        for v in violations:
            print(f"  VIOLATION: {v}", file=sys.stderr)
        return len(violations)

    print(f"  OK — all checks passed ({scope}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
