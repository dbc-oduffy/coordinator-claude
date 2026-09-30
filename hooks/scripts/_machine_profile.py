"""Zero-spawn machine-profile reader for hooks: ``consumer`` or ``author``.

Same resolution rule as the engine's ``coordinator_core.machine_profile.machine_profile()``:
an explicit ``coordinator.machine_profile`` registry value wins; absent, the box is
``author`` when any registered ``repos.*`` path carries a ``.coordinator-dev-repo``
sentinel at its root, else ``consumer``. Stdlib only, no engine import, no subprocess.
An unreadable registry resolves to ``consumer``.

``feature_enabled(name)`` reads ``coordinator.feature.<name>`` (``on``/``off``);
``doctrine_edit_gate`` is off unless set ``on``, and an unreadable key is off.
"""

from __future__ import annotations

import os
from pathlib import Path

from _engine_root import (
    _flatten_registry,
    _registry_value,
    _settings_home_registry_dir,
)

PROFILE_KEY = "coordinator.machine_profile"
ENV_OVERRIDE = "MACHINE_LOCAL_COORDINATOR_MACHINE_PROFILE"
DEV_REPO_SENTINEL = ".coordinator-dev-repo"
_PROFILES = ("consumer", "author")


def _explicit(reg_dir: Path) -> str | None:
    raw = os.environ.get(ENV_OVERRIDE) or _registry_value(reg_dir, PROFILE_KEY)
    value = (raw or "").strip().lower()
    return value if value in _PROFILES else None


def _registered_repo_has_sentinel(reg_dir: Path) -> bool:
    try:
        import tomllib
    except ImportError:
        return False
    seen: set[str] = set()
    for name in ("registry.local.toml", "registry.toml"):
        try:
            with (reg_dir / name).open("rb") as fh:
                data = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError):
            continue
        for key, value in _flatten_registry(data).items():
            if key.startswith("repos.") and isinstance(value, str) and value:
                seen.add(value)
    for path in seen:
        try:
            if (Path(path) / DEV_REPO_SENTINEL).exists():
                return True
        except OSError:
            continue
    return False


def machine_profile() -> str:
    """``consumer`` or ``author`` for this box."""
    try:
        reg_dir = _settings_home_registry_dir()
        return _explicit(reg_dir) or (
            "author" if _registered_repo_has_sentinel(reg_dir) else "consumer"
        )
    except Exception:  # noqa: BLE001 -- hooks fail open
        return "consumer"


def is_author() -> bool:
    return machine_profile() == "author"


FEATURE_KEY = "coordinator.feature."
#: Unset default per feature, mirroring the engine's ``_FEATURE_DEFAULT``:
#: ``"profile"`` follows the machine profile, ``"off"`` is off everywhere.
_FEATURE_DEFAULT = {
    "cross_repo_memos": "profile",
    "publishing": "profile",
    "doctrine_edit_gate": "off",
}


def feature_enabled(name: str) -> bool:
    """Whether ``coordinator.feature.<name>`` is on; an unreadable key or
    registry resolves to the feature's unset default."""
    default = _FEATURE_DEFAULT.get(name, "off")
    try:
        reg_dir = _settings_home_registry_dir()
        env = os.environ.get("MACHINE_LOCAL_COORDINATOR_FEATURE_" + name.upper())
        raw = env or _registry_value(reg_dir, FEATURE_KEY + name)
        value = (raw or "").strip().lower()
        if value in ("on", "off"):
            return value == "on"
        if default == "profile":
            return machine_profile() == "author"
    except Exception:  # noqa: BLE001 -- hooks fail open
        return False
    return default == "on"
