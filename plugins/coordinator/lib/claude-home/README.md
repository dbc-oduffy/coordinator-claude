# `claude-home` — canonical resolver for the Claude Central install

> **Source of truth.** This directory is the load-bearing module that resolves where `~/.claude.json` and `~/.claude/` live, with `CLAUDE_HOME` as the deliberate audited override. `/coordinator:setup` Phase 3 Step 3 copies these artifacts into `~/.claude/bin/`; peer install scripts consume from the installed location.
>
> **Doctrine.** [`docs/wiki/machine-local-registry.md § 4a`](../../docs/wiki/machine-local-registry.md) — env-var precedence, filesystem layout invariants, cross-repo alignment policy.

## Artifacts in this directory

| File | Role |
|---|---|
| `_claude_home.py` | The implementation. Stdlib-only Python module. Exposes both a Python API (`from _claude_home import claude_config_path, read_config, write_config`) and a CLI (`python _claude_home.py {home\|path\|dir\|machine-local\|plugins}`). |
| `claude-home` | Bash shim. Resolves a Python interpreter and execs `_claude_home.py` with the caller's args. Installed `chmod +x` at `~/.claude/bin/claude-home`. |
| `claude-home.cmd` | Windows shim. Routes `claude-home <args>` through Git-for-Windows bash so the extensionless script is callable from native cmd.exe / PowerShell without triggering the "Select an app" picker. |
| `tests/test_claude_home.py` | Stdlib `unittest` suite (no pytest dep). 16 tests covering path resolution precedence, sub-location helpers, sibling-not-nested layout invariant, JSON read/write/BOM/atomicity, CLI surface. |
| `README.md` | This file. |

## Public API

### Shell-out (preferred for cross-language portability)

```bash
home=$(claude-home home)              # $HOME analog (CLAUDE_HOME if set, else $HOME)
config=$(claude-home path)            # ~/.claude.json
claude_dir=$(claude-home dir)         # ~/.claude
ml=$(claude-home machine-local)       # ~/.claude/machine-local
plugins=$(claude-home plugins)        # ~/.claude/plugins
```

Unknown subcommand or zero args → exit 2 + usage to stderr.

### Python import (when avoiding subprocess startup matters)

```python
import os
import sys
from pathlib import Path

# Resolve the bin/ location using the same precedence as the module itself.
# Do NOT use Path.home() unconditionally — it ignores CLAUDE_HOME and risks
# importing the wrong copy under test sandboxes.
_base = Path(os.environ.get("CLAUDE_HOME") or os.environ.get("HOME") or Path.home())
sys.path.insert(0, str(_base / ".claude" / "bin"))

from _claude_home import (
    home_dir, claude_home_dir, claude_config_path,
    machine_local_dir, plugins_dir,
    read_config, write_config,
)
```

**Dual-identity caveat.** If anything else in the same process also imports `_claude_home` via a different `sys.path` insertion, two module copies will live in `sys.modules` with separate state. Prefer shelling out to `claude-home` if that is a possibility.

Path resolvers return `pathlib.Path`. `read_config()` returns `{}` for an absent file (no exception); raises `json.JSONDecodeError` with the file path enriched into the message for malformed JSON; tolerates UTF-8 BOM. `write_config(dict)` writes atomically via tempfile + `os.replace`, creates parent dirs, cleans up tmp on failure.

## Why this isn't in `templates/`

Templates are scaffolding the installer copies out — operator-owned post-install, customizable, expected to drift. `claude-home` is the opposite: a load-bearing API that peer repos (project-rag, holodeck, deep-research, future Python/TS/Rust consumers) shell out to or import. Its contract MUST stay stable across plugin versions; operator-customization is anti-doctrine. The `lib/<module>/` shape signals "shared library — do not customize, do consume."

## Env-var precedence (canonical)

```
1. CLAUDE_HOME   $HOME substitute — test sandboxes, CI, alt installs
2. HOME          POSIX-canonical (Linux/macOS/git-bash/MSYS/WSL)
3. USERPROFILE   Windows-canonical fallback (native cmd.exe / PowerShell)
4. Path.home()   language-stdlib last resort
5. exit 1        refuse to guess
```

`.claude.json` lives at `$HOME/.claude.json`; the Claude Central directory lives at `$HOME/.claude/`. They are SIBLINGS under `$HOME`, never nested. CLAUDE_HOME redirects the `$HOME` layer, which moves both atoms together.

## Tests

```bash
python plugins/coordinator/lib/claude-home/tests/test_claude_home.py
```

Stdlib-only; runs anywhere Python 3.9+ runs. 16 tests covering the full surface. CI gate (when one exists) should fail if any test fails — this is load-bearing infrastructure.

## Install location

`/coordinator:setup` Phase 3 Step 3 copies `_claude_home.py`, `claude-home`, and `claude-home.cmd` from this directory into `~/.claude/bin/`. The installed copies are what peer scripts shell out to / import; this directory is the canonical source.

If an operator hand-customizes a file in `~/.claude/bin/`, setup preserves it and emits a notice rather than overwriting — same idempotency contract as the rest of Phase 3. Operator customization of `claude-home` is strongly discouraged (breaks the cross-repo contract); doctrine is to fix the upstream module here and re-run setup.

## Adopting from a peer repo

When a peer repo (project-rag, holodeck, deep-research, future Python/TS/Rust consumers) migrates its own `$HOME` resolver to consume this module, **the bootstrap-lookup and the contents-resolution use different env-var precedence chains**. Conflating them breaks test sandboxes.

- **Bootstrap lookup** = where the module file LIVES on disk. Resolve via real `$HOME` only — `HOME` → `USERPROFILE` → `Path.home()`. Do **NOT** honor `CLAUDE_HOME` for this purpose. `_claude_home.py` is installed at `$HOME/.claude/bin/_claude_home.py` by `/coordinator:setup` against the operator's real `$HOME`; it is NOT replicated into every `CLAUDE_HOME=/tmp/sandbox` test root.
- **Contents resolution** = what the module's API returns (paths to `~/.claude.json`, `~/.claude/`, sub-locations). Resolve via the full precedence chain — `CLAUDE_HOME` → `HOME` → `USERPROFILE` → `Path.home()` (§ Env-var precedence above). This is what the module exists to do.

The two surfaces look identical (both involve `$HOME` resolution) but compose differently under test sandboxing. A test that sets `CLAUDE_HOME=tmp_path` to redirect content resolution will never find `_claude_home.py` at `tmp_path/.claude/bin/` — the bootstrap import fails, the peer's fallback fires, and the central path is never exercised under CI.

**Reference shape for the bootstrap-lookup half** (e.g., in a peer repo's `_claude_config.py` shim):

```python
import os, sys
from pathlib import Path

# BOOTSTRAP lookup — find where the central module is installed.
# Use REAL $HOME only; ignore CLAUDE_HOME deliberately.
_real_home = Path(os.environ.get("HOME") or os.environ.get("USERPROFILE") or Path.home())
_central_bin = _real_home / ".claude" / "bin"

if not (_central_bin / "_claude_home.py").exists():
    # Fall back to the peer's own copy of the resolution chain — central not installed.
    ...
else:
    sys.path.insert(0, str(_central_bin))
    from _claude_home import claude_config_path, read_config, write_config
    # NOW the central module handles CONTENTS resolution with full CLAUDE_HOME precedence.
```

Doctrine: [`docs/wiki/machine-local-registry.md § 4a`](../../docs/wiki/machine-local-registry.md) — bootstrap-vs-contents distinction formalized in the same section that owns the env-var precedence chain.
