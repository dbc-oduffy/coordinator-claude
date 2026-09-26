
from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    args = argv[1:]
    show_findings = "--findings" in args

    engine_root = Path(__file__).resolve().parents[2]
    if str(engine_root) not in sys.path:
        sys.path.insert(0, str(engine_root))

    from coordinator_core.warm import serve_classifier

    names = serve_classifier.load_allowlist_names()
    verdicts = serve_classifier.classify_population(names)
    report = serve_classifier.partition_report(verdicts)

    output: dict = {"population": "warm_entrypoint_allowlist.json:entrypoints", "partition": report}
    if show_findings:
        output["findings"] = [
            {"path": f.path, "line": f.line, "reason": f.reason, "text": f.text}
            for f in serve_classifier.findings_for(verdicts)
        ]

    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
