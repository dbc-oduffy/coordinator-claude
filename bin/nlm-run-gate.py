#!/usr/bin/env python3
"""nlm-run-gate: settings-home forwarder to DoE's notebooklm run-gate script.

Runs deep-research/notebooklm/nlm-run-gate.py from the resolved DoE pipelines
root in-process, so the target's exit code and stdout are the caller's.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from doe_pipeline_forward import forward  # noqa: E402

if __name__ == "__main__":
    forward("deep-research/notebooklm/nlm-run-gate.py", "nlm-run-gate")
