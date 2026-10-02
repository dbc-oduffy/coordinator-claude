"""Auto-compaction default and threshold derivation, shared by the status line and the
imminent-compaction hook.

The harness compacts at `min(window - 13000, window * pct / 100)`, where `window` is
`CLAUDE_CODE_AUTO_COMPACT_WINDOW` clamped to the model window and `pct` is
`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`. The override can only lower the threshold. The statusline payload
carries no threshold field, so consumers derive it here from the configured inputs.

Installer helper: `python3 compaction_defaults.py --apply <settings.json>` writes
`env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE = DEFAULT_AUTOCOMPACT_PCT` when the key is absent and never
overwrites an operator value.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DEFAULT_AUTOCOMPACT_PCT = 40
PCT_ENV = "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"
WINDOW_ENV = "CLAUDE_CODE_AUTO_COMPACT_WINDOW"
BUFFER_TOKENS = 13000


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    return None


def settings_path() -> Path:
    raw = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(raw) if raw else Path.home() / ".claude") / "settings.json"


def _settings_env() -> dict:
    try:
        block = json.loads(settings_path().read_text(encoding="utf-8")).get("env")
    except (OSError, ValueError, AttributeError):
        return {}
    return block if isinstance(block, dict) else {}


def configured(name: str, settings_env: dict | None = None) -> float | None:
    """The process env value for `name`, else the `env` block of the user settings.

    Callers resolving several names pass one parsed `settings_env` so the file is read once.
    """
    if _number(os.environ.get(name)) is not None:
        return _number(os.environ.get(name))
    return _number((_settings_env() if settings_env is None else settings_env).get(name))


def threshold_tokens(window_size: object, settings_env: dict | None = None) -> tuple[float | None, str]:
    """(tokens at which auto-compaction fires, provenance) or (None, why-unknown)."""
    model_window = _number(window_size)
    if model_window is None:
        return None, "window size unknown"
    if settings_env is None:
        settings_env = _settings_env()
    window = min(configured(WINDOW_ENV, settings_env) or model_window, model_window)
    pct = configured(PCT_ENV, settings_env)
    budget = window - BUFFER_TOKENS
    if pct is not None:
        budget = min(budget, window * pct / 100.0)
        return budget, f"{PCT_ENV}={pct:g} of {window:g}"
    return budget, f"window {window:g} minus {BUFFER_TOKENS}"


def apply_default(settings: dict) -> bool:
    """Set the default override in `settings["env"]` when absent. True when changed."""
    env = settings.setdefault("env", {})
    if not isinstance(env, dict) or PCT_ENV in env:
        return False
    env[PCT_ENV] = str(DEFAULT_AUTOCOMPACT_PCT)
    return True


def apply_default_to_file(path: Path) -> bool:
    try:
        settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        return False
    if not isinstance(settings, dict) or not apply_default(settings):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return True


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--apply":
        print("applied" if apply_default_to_file(Path(sys.argv[2])) else "unchanged")
    else:
        print(f"usage: {sys.argv[0]} --apply <settings.json>", file=sys.stderr)
        sys.exit(2)
