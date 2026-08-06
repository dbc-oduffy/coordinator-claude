"""oss-repo-constants.py — importable constants for the coordinator OSS publish repo.

Single source of truth for the coordinator-claude canonical publish URL and owner/repo
identifiers, imported (via file-path spec_from_file_location, not a normal `import`,
because the hyphenated filename isn't a valid module identifier) by any script that
needs the coordinator publish URL — prevents inline duplication and per-script drift.
Constants-only: must not produce stdout/stderr output or side effects when loaded.
"""
# lib/oss-repo-constants.py — importable constants for coordinator OSS publish repos.
#
# Purpose: single source of truth for the coordinator-claude canonical publish URL
# and owner/repo identifiers. Imported by any script that needs the coordinator
# publish URL — prevents inline duplication and per-script drift.
#
# Spec backlink: docs/plans/2026-06-01-boot-currency-notification-hook.md § C2
# Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
#
# Usage (in any script):
#   import importlib.util
#   spec = importlib.util.spec_from_file_location(
#       "oss_repo_constants",
#       "/path/to/coordinator/lib/oss-repo-constants.py",
#   )
#   module = importlib.util.module_from_spec(spec)
#   spec.loader.exec_module(module)
#   module.COORDINATOR_PUBLISH_URL
#
#   (file-path import is required, not `import oss_repo_constants`, because
#   the hyphenated filename is not a valid Python module identifier for a
#   normal `import` statement — same reason bash callers used `source` with
#   a path rather than a package name.)
#
# Negative-spec:
#   - deep-research-claude URL is NOT defined here — it belongs to the spinoff
#     (state/handoffs/2026-06-01_122922_deep-research-currency-notification.md).
#   - This file is IMPORTED/EXECUTED ONLY for its module-level constants — it
#     must not produce any stdout/stderr output or side-effects when loaded.

# Coordinator-claude publish repo constants.
COORDINATOR_PUBLISH_OWNER = "dbc-oduffy"
COORDINATOR_PUBLISH_REPO = "coordinator-claude"
COORDINATOR_PUBLISH_URL = f"https://github.com/{COORDINATOR_PUBLISH_OWNER}/{COORDINATOR_PUBLISH_REPO}.git"
