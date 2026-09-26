#!/usr/bin/env python3

import re
import sys


SOURCEREF_KEYS = frozenset({"url", "fetch_date", "platform", "comment_id"})
VALID_TIERS = frozenset({"source_read", "artifact_forensic"})

PERMALINK_RE = re.compile(r"^https?://[^/\s]+/.*/blob/[0-9a-f]{7,40}/.+#L\d+-L\d+$")
LOCAL_FRAGMENT_RE = re.compile(r"^[^:\s]+#L\d+-L\d+$")
BARE_BLOB_RE = re.compile(r"/?blob/[0-9a-f]{7,40}/")


def check_record(record, label: str = "") -> list[str]:
    violations = []
    prefix = f"{label}: " if label else ""

    def require(condition, message):
        if not condition:
            violations.append(prefix + message)

    # or a scalar) must fail as a clean VIOLATION, not an uncaught TypeError from
    if not isinstance(record, dict):
        violations.append(
            f"{prefix}record must be a mapping, got {type(record).__name__}"
        )
        return violations

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
        require(isinstance(evidence, list), f"observation.{side}.evidence must be a list")
        if isinstance(evidence, list):
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
                for extra_key in sorted(set(ref) - SOURCEREF_KEYS):
                    require(
                        False,
                        f"observation.{side}.evidence[{i}] carries unknown key {extra_key!r} — "
                        "SourceRef is exactly {url, fetch_date, platform, comment_id}",
                    )

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

    for side in ("peer", "subject"):
        side_obj = observation.get(side, {}) or {}
        side_evidence = side_obj.get("evidence", []) or []
        if not isinstance(side_evidence, list):
            continue
        for i, ref in enumerate(side_evidence):
            if not isinstance(ref, dict):
                continue
            url = ref.get("url", "")
            # otherwise raise TypeError instead of a clean VIOLATION.
            require(isinstance(url, str), f"observation.{side}.evidence[{i}].url must be a string")
            if not isinstance(url, str):
                continue
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

    peer_ref = record.get("peer_ref")
    require(isinstance(peer_ref, str) and peer_ref.strip() != "", "peer_ref must be present and non-empty")

    require("competitor_uid" not in record, "competitor_uid MUST be absent from a DoE-emitted record (negative-spec 1)")

    recommendation_token_patterns = [
        r"\badopt\b", r"\badapt\b", r"\bdefer\b", r"\bshould\b",
        r"\brecommend\b", r"\brecommends\b", r"\brecommended\b",
        r"\bwe should\b", r"\bmust adopt\b", r"\bought to\b",
        r"\bneeds? to\b",
    ]
    analysis_text = record.get("analysis", "") or ""
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
