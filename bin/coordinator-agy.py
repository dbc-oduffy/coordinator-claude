#!/usr/bin/env python3
"""Launch agy with coordinator EM defaults. See agy-coordinator.py."""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).with_name("agy-coordinator.py")), run_name="__main__")
