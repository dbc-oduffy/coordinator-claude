## Optional Tripwire Installs

After Phase 3 scaffolding completes, offer to install coordinator-standard tripwire tests into the consuming repo's test suite. Each tripwire is a copyable template — copy, customize the allowlist, and wire into CI.

### Windows console-subprocess tripwire (offer always on Windows-operator repos)

Offer this tripwire when the consuming repo includes shell scripts that may run on
Windows operator machines (any `*.sh` in the repo root or a `scripts/` / `bin/` subtree
is a reliable signal).

**What it catches:** bare `python -c`, `python3 -c`, `python.exe -c`, `powershell.exe`,
and PowerShell `& python` invocations in `*.sh` files — shapes that pop a
focus-stealing console window on Windows when spawned from the headless Bash-tool
parent process.

**Canonical suppression markers (two forms, honored identically by all layers):**
- `# popup-intentional-last-resort` — the popup occurs and is accepted (pythonw fallback or genuine console need).
- `# popup-safe-env-suppressed` — the popup is suppressed at this site by env-var means and is therefore safe.

Place the applicable marker on the same line as the bare call (shell/Python comment form). When inside an embedded interpreter string (`python -c "..."`) place the marker on the surrounding SHELL line, outside the string — the marker inside a Python string argument is parsed by Python at runtime, not by the tripwire regex. The retired form `# noqa: bare-subprocess-windows` is NOT honoured; do not use it.

**Install steps:**

1. Copy `<coordinator-plugin-root>/tests/templates/test_no_bare_console_subprocess.py` into the consuming repo at `tests/test_no_bare_console_subprocess.py` (resolve `<coordinator-plugin-root>` the same way the rest of this skill does — `CLAUDE_PLUGIN_ROOT` / the `.doe-root` pointer — and fail loud if unresolved).
2. Customize the allowlist at the top of the copied file: `PREFIXES` — subtree paths that are known-safe (e.g. `vendor/`, `tests/fixtures/`); `EXACT_FILES` — individual files allowed to use bare calls (e.g. the safe-path wrapper itself).
3. Verify it runs and reports nothing unexpected: `python tests/test_no_bare_console_subprocess.py` (or `pytest tests/test_no_bare_console_subprocess.py`) — `python3` has no alias on Windows; use the bare `python` interpreter name.
4. Add the appropriate suppression marker to any remaining bare calls in files NOT covered by the allowlist — `# popup-intentional-last-resort` if the popup is accepted (last-resort / pythonw fallback); `# popup-safe-env-suppressed` if the popup is already suppressed by env-var means.

**Template path:** `~/.claude/plugins/coordinator/tests/templates/test_no_bare_console_subprocess.py`

Offer the install when the PM has not already done so (check for the file in the
consuming repo's test tree). If the PM declines, note it in the Phase 4 REPORT under
`### Needs Attention` with a one-line pointer to the template path.

### Widened spawn tripwire — `.py`/`.ps1`, non-optional (Phase 3m-adjacent, ALWAYS installed)

Unlike the `.sh` console-subprocess tripwire above, this gate is **not offered** — it installs
unconditionally, the same non-offered posture as Phase 3m's guard-regression tests. The `.sh`-only
tripwire's own docstring used to delegate `.py`/`.ps1` coverage to a `~/.claude` install-plane
authoring hook that a repo without `coordinator_core` never has — leaving such a repo with no
Python-spawn gate at all. This section closes that gap by shipping the widened gate at onboarding
time rather than as a follow-up a repo may never adopt.

**What it catches.** A bare `subprocess.run`/`Popen`/`call`/`check_output`/`check_call` (via
`import subprocess`, `import subprocess as sp`, or `from subprocess import run`) with no
`creationflags=`, no `**` splat, and no suppression tag — AST-resolved for `.py`, so it does not
false-positive on `asyncio.run(...)`, an unrelated `.run()` method, or a `run(` substring inside
a comment/docstring, all of which a regex leg cannot avoid. `.ps1` has no stdlib AST available, so
that leg is regex, like the `.sh` leg above: a bare `Start-Process` missing `-WindowStyle Hidden`,
and a bare `powershell.exe`/`pwsh`/`pwsh.exe` invocation.

**Files to copy** (read on disk this session, named exactly):

1. `coordinator/tests/templates/test_no_bare_python_spawn.py` — the template. Both legs (`.py` AST,
   `.ps1` regex) live in this one file; its own module docstring carries the full onboarding
   procedure (`HOW TO ONBOARD IN A CONSUMING REPO`) — follow it rather than re-deriving the steps.
2. `coordinator/lib/spawn_detect.py` — the vendored AST detector. This is a **verbatim** copy of
   an upstream `coordinator_core` module (stdlib-only: `ast, dataclasses, enum, hashlib, pathlib,
   re` — zero `coordinator_core` imports of its own), copied byte-for-byte on purpose so it
   carries no live dependency on `coordinator_core`, which a fleet repo without that package
   cannot resolve. Copy it alongside the template; do not edit it.
3. `coordinator/hooks/scripts/_win_portability.py` (for hook-shaped consumers, `sys.path.insert`
   convention) and/or `coordinator/lib/win_portability.py` (for lib/bin/CLI consumers) — the
   `no_console_creationflags()` helper the remediation text points a fixer at. Ship whichever
   placement matches the consuming repo's own import convention; both are dependency-free.

**Onboarding steps**, matching the template's own docstring:

1. Copy the template + `spawn_detect.py` into the `guards/` subdirectory the consuming repo's own
   `fast_test_cmd` collects (same `<scope>/guards/` derivation as Phase 3m above — never bare
   `tests/`).
2. Adjust the repo-root hop count. The template resolves `_REPO_ROOT` as `Path(__file__)
   .resolve().parent.parent.parent` (3 hops off its own location) when `TRIPWIRE_REPO_ROOT` is
   unset — the scope constant lives right below it, `SCOPE_SUBDIR: tuple`, a **single named
   constant** so a later widening from `hooks/scripts/`-only to repo-wide is a one-line edit (this
   is the same one-line-widening shape that let this repo's own hooks-scripts-only gate widen
   toward `lib/`, bin/CLI, and CI scope without touching the walk logic).
3. Extend `EXCLUDE_DIRS` from `spawn_detect.DEFAULT_EXCLUDE + ("tasks",)` — see the exclude-set
   starting point below.
4. Set `RATCHET_MAX` and populate `spawn_exemption_register.yaml` only if the repo is choosing to
   tier a bulk-legacy tree (see exemption mechanisms below) — leave both at the template's
   onboarding default (`RATCHET_MAX = 0`, no register file) for a fresh, small repo with nothing to
   tier.
5. Run `pytest <scope>/guards/test_no_bare_python_spawn.py` and burn down what it flags, or tag
   genuinely intentional sites (see below).

**The exclude-set starting point.** Extend `spawn_detect.DEFAULT_EXCLUDE` — `scratch, scratchpad,
.venv, venv, node_modules, build, .git, __pycache__` — with this repo's own ephemera dirname
(`"tasks"` here; a consuming repo names its own equivalent, e.g. a scratch/flight-recorder
convention it already has). **Do not add `dist` (or any generated-output dirname) as a bare-name
exclude.** The vendored detector's own `DEFAULT_EXCLUDE` docstring names the exact failure this
avoids: an earlier upstream commit added a bare `"dist"` entry that matched dirname only, and
silently hid real, committed subprocess call sites under this repo's own `coordinator/dist/` —
which holds real git-tracked publish-mirror output, not a vendored third-party tree, and happens
to share that conventional dirname. If a genuinely vendored tree needs excluding, name it
explicitly by path, never by a bare name a real source directory could collide with. (This repo's
own gate keeps `coordinator/dist/` out of scope structurally — it is simply not one of the walked
`SCOPE_SUBDIR` roots — rather than via an exclude-dirs entry; see
`state/audits/2026-08-07-dist-mirror-upstream-audit.md` for the full disposition, including the
honest finding that this exclusion is not fully "generated from a covered upstream" for 11 files
under `coordinator/dist/` that have no in-repo source at all — a real coverage gap for OSS-only
dist content, carried forward rather than papered over.)

**Exemption mechanisms — two, coexisting by design, neither keyed `file:line`:**

- **Inline `# guard-allow: <rule-id> <rationale>` sentinel** — for a hot-path or lib site where a
  human is already editing the line. Scanned across the flagged call's full source span
  (`call.lineno..call.end_lineno`), so it works on a multi-line call. The legacy
  `# popup-intentional-last-resort` tag is honoured identically for last-resort cases.
- **Central register (`spawn_exemption_register.yaml`) + monotonic ratchet** — for tiering a bulk
  legacy tree (a large existing test tree, typically) without rewriting every site at once. Keyed
  on `<repo-relative-path>::<enclosing-qualname>::<argv0>` — never `file:line`. A
  `frozen_relpaths` closed set makes exemption structurally impossible for any file not present at
  population time — a newly-authored file can never acquire a working entry even if one is
  hand-added to `entries`. `RATCHET_MAX` bounds the register to a committed integer; any growth
  fails the gate. See this repo's own `coordinator/tests/guards/spawn_exemption_register.yaml` for
  a worked instance.

Both mechanisms key on a stable marker rather than a `file:line` pair — a `(relpath, lineno)` key
drifts silently the moment two sessions touch the same file on a shared branch, which is this
repo's normal operating condition, not an edge case.

**This repo's measured burn-down cost** (`state/audits/2026-08-07-python-spawn-site-census.md`,
AST-authoritative, supersedes the regex heuristic in the sizing object): 389 sites repo-wide, 165
unsuppressed at HEAD before burn-down. The hot path that actually pays the Windows spawn tax —
`coordinator/hooks/scripts/` — was 8 files, 23 unsuppressed sites, burned to green with an empty
exemption register. `coordinator/lib/` carried zero sites; the real CLI surface
(`coordinator/scripts/`) carried 1, already suppressed; `.github/scripts/` carried 2, fixed. The
test tree (~230 of the ~324 original heuristic-sized sites, 82 unsuppressed of 236 total AST
sites across 39 files) was **tiered, not burned down** — register + ratchet, 65 entries, new test
files structurally ineligible for an exemption. This is the only measured predictor available for
what another fleet repo's onboarding costs: expect the hot-path burn-down to be small (single-digit
files) and the test-tree tiering to dominate the diff if the repo carries a large legacy test tree.

### Cross-platform CI reference (offer when `cross_platform` is declared or inferred-and-confirmed)

Offer this CI reference when `_CROSS_PLATFORM_DECLARED=true` (from Phase 1 `coordinator.local.md` capture) OR when `_CROSS_PLATFORM_INFERRED=true` and the PM confirms the inference prompt.

**Inference prompt (when `_CROSS_PLATFORM_INFERRED=true` and `_CROSS_PLATFORM_DECLARED` is unset):**

> This repo looks cross-platform (detected: {_CROSS_PLATFORM_SIGNAL}). Declare `cross_platform: true` in `coordinator.local.md` and install the CI reference? [yes / no / not now]

On "yes": write `cross_platform: true` as a flat top-level entry into `coordinator.local.md` (same shape as `fast_test_cmd`) and set `_CROSS_PLATFORM_DECLARED=true`, then proceed to the offer below. On "no" or "not now": skip the CI reference offer and note the decline in `### Needs Attention`. **Never auto-write without asking — detect-then-ask, not detect-then-silently-pick.**

**Why this uses an explicit declared field rather than pure signal-detect:** repo-setup's existing tripwire offers key on detected code signals (e.g. `*.sh` presence), but `cross_platform: true` is a deliberate departure from that pattern. Cross-platform-ness is a cross-cutting property that applies equally to TS, Python, C++, and Rust repos; it is most honestly declared by an operator who has thought it through. Silent inference risks a false positive — e.g. inferring cross-platform from `*.sh` in `bin/` and auto-installing a pytest CI snippet into a TypeScript repo. The explicit optional field preserves operator judgment while keeping the detect-then-ask path for convenience.

**Offer text (once cross-platform is declared or inferred-and-confirmed):**

> This repo declares cross-platform support. Install the cross-platform CI reference (3-OS matrix + honest-measurement markers)?
>
> Reference snippet: `~/.claude/plugins/coordinator/templates/ci/cross-platform-matrix.snippet.yml`

**Language-aware install — IMPORTANT: do not hand a pytest snippet to a non-Python repo.**

- **Python repos** (`detected_type == data-science` OR `pyproject.toml` / `requirements.txt` / `pytest.ini` detected in Phase 1): auto-copy `templates/ci/cross-platform-matrix.snippet.yml` into the consuming repo, then link the principle wiki and add a `### Needs Attention` reminder to adapt the marker names and deselect logic for the project's hardware-gated tests:

  1. Copy `<coordinator-plugin-root>/templates/ci/cross-platform-matrix.snippet.yml` into the consuming repo at `templates/ci/cross-platform-matrix.snippet.yml` (create `templates/ci/` if absent; resolve `<coordinator-plugin-root>` the same way the rest of this skill does).
  2. Review inline comments — adapt marker names (`cross_repo_fix_locus` is coordinator-standard; hardware-gate markers like `real_spawn` are project-rag-specific examples, replace with your own).
  3. Wire the matrix block into your CI workflow (GitHub Actions, GitLab CI, etc.).

- **Non-Python repos (TS, Rust, UE-C++, general):** do NOT copy the pytest snippet. Instead, surface the wiki + snippet as a worked example:

  > The cross-platform CI reference (`cross-platform-matrix.snippet`) is a worked **pytest** example of the language-agnostic principle. Adapt the matrix and honest-measurement marker conventions to your CI system and test runner.

**Template path:** `~/.claude/plugins/coordinator/templates/ci/cross-platform-matrix.snippet.yml`

Offer the install when the PM has not already done so (check for the snippet in the consuming repo's tree). If the PM declines, note it in the Phase 4 REPORT under `### Needs Attention` with a one-line pointer to the template path and wiki.
