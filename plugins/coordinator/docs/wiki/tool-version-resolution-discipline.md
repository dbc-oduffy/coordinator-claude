# Tool Version Resolution Discipline

> When a CLI invocation could plausibly resolve to two or more installed versions, resolution must be explicit and fail-loud when ambiguous. Silent fall-back to whichever-comes-first-on-PATH is a recipe for the multi-hour "works on my machine but the script picked a different binary" bug.

*Lesson surface: 2026-05-06, claude-unreal-holodeck — a tool invocation resolved to a different installed version than the operator expected, costing diagnostic time downstream.*

## Failure shape

The same tool name (`python`, `pip`, `node`, `git`, a project CLI, an MCP server, the editor's headless driver) is installed in multiple places — system package, user package, venv shim, Homebrew, scoop, Windows Store, MSI. PATH ordering decides which one fires. The script that "should be running the project venv's python" instead runs the system python, succeeds on the import (because both have the dep), and silently produces wrong results because the version is older.

Common amplifiers:
- Windows Store python shims that exist as `python.exe` stubs even when no real python is installed there.
- `uv`-managed venvs whose `python` is a hard-link or shim that disagrees with `which python`.
- `nvm` / `pyenv` shims whose version pin changes mid-session via a config file in a parent directory.
- Tool installers that prepend to PATH at install time, silently inverting prior resolution order.

## Rule

When the resolved version matters (project tooling, test runners, CI parity, MCP server boot), one of the following must hold:

1. **Absolute path pin.** The invocation uses a full path: `& "C:\Users\<user>\.venvs\<project>\Scripts\python.exe"` rather than `python`. The path may be computed once and cached, but must not collapse to a bare name on the wire.
2. **Version assertion at boot.** First action of the script/tool is `python --version` (or equivalent) compared against an expected pin. Mismatch → exit non-zero with a remediation message naming both the resolved version and the expected version.
3. **Indirection through a venv-aware launcher.** `uv run`, `npm exec`, `cargo run` — anything that resolves the version through the project's own manifest, not PATH.

Bare `python <script>` in a script that will be run on someone else's machine is a bug unless one of the above is in place.

## Anti-patterns

- "PATH is correct on the dev machine, so the script will work everywhere." PATH is a per-user-per-shell variable; it is not contract.
- "We check `which python` at the start." `which python` reports what PATH resolves to *now*; it does not pin the resolution for the rest of the script. Subprocess calls that re-exec the parent's command can still drift if a venv is activated/deactivated mid-run.
- "The CI runs `python --version` so we're covered." CI tests one resolution path; the failure happens on the operator's machine where resolution differs.

## Cross-references

- [`substrate-pin-doctrine.md`](./substrate-pin-doctrine.md) — substrate pins must lock BOTH index and version; the same logic at the tool layer.
- [`test-environment-discipline.md`](./test-environment-discipline.md) — pinned-venv-python resolution for test harnesses.
- [`bash-on-windows-gotchas.md`](./bash-on-windows-gotchas.md) — shebang locality is the bash-side cousin of this rule.
