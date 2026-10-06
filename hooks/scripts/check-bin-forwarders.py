"""Drift probe: every engine-owned `coordinator/bin/` script must stay a forwarder.

Asserts each name in `FORWARDER_NAMES` is a thin stub that references
`_engine_forward` and carries no logic beyond the canonical forwarder body.
Exits 1 listing offenders (a regrown fork, a missing file); 0 when clean.
"""

from __future__ import annotations

import sys
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parents[2] / "bin"

FORWARDER_NAMES = (
    "_hook_cost_probe.py",
    "approvability-calibration.py",
    "atlas-citation-check.py",
    "baton-chain-closure.py",
    "check-anchor-freshness.py",
    "check-citation-integrity.py",
    "check-decision-citations.py",
    "check-doctrine-status.py",
    "check-gitignore-template-drift.py",
    "check-launch-shape.py",
    "check-mcp-namespace-registration.py",
    "check-prior-art-enumeration-drift.py",
    "check-projectragignore-fleet-drift.py",
    "check-settings-env.py",
    "check-survey-attestation.py",
    "check-watch-state-gitignore-fleet.py",
    "compose-review-wave.py",
    "copy-currency-refresh.py",
    "corpus-currency-probe.py",
    "emit-dispatch-workflow.py",
    "expired-plan-gates.py",
    "export-catering-resolution.py",
    "goal-assessment-staleness.py",
    "goal-kr-evidence.py",
    "group-em-enter.py",
    "group-em-nomination.py",
    "group-em-watch-cli.py",
    "host-gpu-probe.py",
    "instrument-can-report-red.py",
    "measure-hook-class-cost.py",
    "measure-listener-availability.py",
    "measure-loopback-round-trip.py",
    "memo-outbox-tracking-guard.py",
    "mise-census-revalidate.py",
    "mise-prep-gate.py",
    "mise-prep-run.py",
    "navi-singleton.py",
    "needs-restart.py",
    "plan-reversibility-eligibility.py",
    "plan-spine-check.py",
    "pre_commit_corpus_artifact_guard.py",
    "red-set-report.py",
    "resolve-peer-address.py",
    "stable-suite-run.py",
    "statusline.py",
    "structural-index-refresh.py",
    "subagent-statusline.py",
    "survey-consume-gate.py",
    "tier-last-run.py",
    "triage-plan-candidates.py",
    "uhura-mode.py",
    "waste-signal.py",
    "writes-ignored-check.py",
)

CANONICAL_CODE = (
    "import sys",
    "from pathlib import Path",
    'sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))',
    "from _engine_forward import forward",
    "sys.exit(forward(__file__))",
)


def _code_lines(text: str) -> tuple[str, ...]:
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return tuple(out)


def offenders(bin_dir: Path = BIN_DIR, names=FORWARDER_NAMES) -> list[str]:
    bad = []
    for name in names:
        path = bin_dir / name
        if not path.is_file():
            bad.append(f"{name}: missing")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "_engine_forward" not in text:
            bad.append(f"{name}: does not reference _engine_forward")
        elif _code_lines(text) != CANONICAL_CODE:
            bad.append(f"{name}: carries logic beyond the forwarder body")
    return bad


def main() -> int:
    bad = offenders()
    if bad:
        print("bin forwarder drift:", file=sys.stderr)
        for line in bad:
            print(f"  {line}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
