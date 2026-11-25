#!/usr/bin/env python3
"""Launch grok with the agent inbox held by this process. See grok-coordinator.py."""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).with_name("grok-coordinator.py")), run_name="__main__")
