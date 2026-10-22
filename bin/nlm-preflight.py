#!/usr/bin/env python3
"""nlm-preflight: settings-home forwarder to DoE's notebooklm preflight script.

Runs deep-research/notebooklm/nlm-preflight.py from the resolved DoE pipelines
root in-process, so the target's exit code and stdout are the caller's.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from doe_pipeline_forward import forward  # noqa: E402

if __name__ == "__main__":
    forward("deep-research/notebooklm/nlm-preflight.py", "nlm-preflight")
