"""SessionStart guard — keep `<settings-home>/bin/` from silently lagging its source.

`bin/` is written at INSTALL time, so between installs it is a snapshot: a template
that gains a feature reaches nobody until an operator re-runs the installer on that
machine. Consumers cannot see that lag and cannot fix it from their side.

This guard closes it by refreshing already-installed files whose source is this
plugin's `templates/bin/`, at most once a day per machine. The mechanics, the
refresh-only negative-spec, and the baked-`__PYTHON_BIN__` exemption live in
`_bin_impl_drift.py`; this file is the SessionStart entrypoint and nothing else.

Fails open, always: a session must never fail to start because a freshness sweep
could not run. Every failure path returns 0 with no output.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> int:
    try:
        from _bin_impl_drift import check_and_refresh
        from _engine_root import _settings_home

        banner = check_and_refresh(_settings_home() / "bin")
    except Exception:
        return 0

    if banner:
        print(banner)
    return 0


if __name__ == "__main__":
    sys.exit(main())
