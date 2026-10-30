---
segment_id: tripwire-installs
class: protected
order: 5
situation: tripwire-offer
---
## Optional tripwire installs — mechanical half

**Windows console-subprocess tripwire** (`.sh`-only). Copy
`tests/templates/test_no_bare_console_subprocess.py` to `tests/test_no_bare_console_subprocess.py`,
customize `PREFIXES`/`EXACT_FILES`, verify with `python tests/test_no_bare_console_subprocess.py`
(bare `python` on Windows). Suppression markers: `# popup-intentional-last-resort`,
`# popup-safe-env-suppressed`; retired `# noqa: bare-subprocess-windows` is NOT honoured. Whether to offer it is lane/PM judgment.
