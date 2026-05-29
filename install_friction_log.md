# Daemon / Holodeck Triad — Clean Install Friction Log

> **Run date:** 2026-05-27
> **Operator:** Claude (autonomous, "press ahead where you can")
> **Goal:** Clean install of the triad (project-rag runtime + project-rag-ue-addon + claude-unreal-holodeck consumer) following the *new* (post-split) install instructions, logging every frictious or unclear moment.
> **Machine:** Windows 11, PowerShell. Repos under `C:\Delphi\` (project-rag, project-rag-ue-addon, claude-unreal-holodeck, coordinator-claude — siblings).
>
> Severity legend: **[BLOCKER]** stops progress · **[FRICTION]** worked but cost time/confusion · **[UNCLEAR]** docs ambiguous · **[MISMATCH]** docs vs reality · **[NOTE]** observation.

---

## Executive Report

> **Report date:** 2026-05-29 · **Window covered:** 2026-05-27 → 2026-05-29 (4 working sessions) · **Status: SUBSTANTIALLY COMPLETE** — the triad is installed, the project-rag MCP daemon is live, and the UE 5.7 engine corpus is downloaded, merged, wired, and loaded (`engine_queryable: true`). One residual gap (E24, blended-query band registration) remains before engine knowledge is reachable through a normal query, plus consumer-project priming.

### Mission

Perform a **clean install of the "triad"** — the three-repo, post-split code-RAG stack for Unreal Engine — on a fresh Windows 11 machine, following the *new* (post-split) install instructions, and **log every point of friction** so the upstream maintainer (`dbc-oduffy`) can harden the install experience. The triad:

| Repo | Role |
|------|------|
| `project-rag` | **Host runtime** — generic, content-agnostic code-RAG engine + MCP daemon (HTTP, port 8767). |
| `project-rag-ue-addon` | **Engine-knowledge addon** — produces/publishes the UE engine corpus; registers UE-specific MCP tools + `required_env`. |
| `claude-unreal-holodeck` | **Consumer project** — the UE project that gets indexed; also hosts the live-editor MCP servers. |

### Outcome at a glance

| Milestone | Status |
|-----------|--------|
| Prerequisites (Python, uv, gh, GPU, PS7) | ✅ Resolved (several were blockers — see below) |
| Gate A (`coordinator_whoami` importable) | ✅ Cleared (in ambient python **and** the install venv) |
| Gate B (machine-local registry) | ✅ Cleared (substrate laid down + live `registry.toml`) |
| project-rag host install + MCP registration | ✅ Live — daemon on 8767, 18/18 tools smoke-pass, HTTP transport |
| torch-CUDA (RTX 5070 Ti) | ✅ `torch 2.12.0+cu130`, GPU active |
| project-rag-ue-addon install | ✅ Editable-installed into host venv (`project-rag-ue-addon==0.4.0`) |
| Engine corpus download (13 archives, ~2.9 GB) | ✅ Downloaded |
| Engine corpus **merge → single store** | ✅ `chroma_unreal_5.7` = **542,331 records** |
| Engine corpus **wired + daemon-loaded** | ✅ `engine_queryable: true` |
| Engine corpus reachable via `blended_query` | ⛔ **OPEN (E24)** — band leg not registered |
| Consumer project (`claude-unreal-holodeck`) indexed | ⛔ Not started (graph.db empty → `project_health` BROKEN) |

### What was accomplished (chronological summary)

- **Session 1 (2026-05-27):** Prerequisite scan + first install attempt. Hit the headline blocker immediately — Gate A's `coordinator_whoami` package was nowhere on the machine, the documented remediation path was wrong, and the providing repo (`dbc-oduffy/coordinator-claude`) had never been cloned. `gh` was absent. Stopped before any mutations (E0–E7).
- **Session 2 (2026-05-27):** Cleared Gate A (cloned the dbc coordinator repo, `pip install -e` the whoami package at its *real* path) and Gate B (laid down the machine-local substrate, seeded `registry.toml`). Installed `gh`, a portable PS7 7.6.2 (winget MSI needed elevation it didn't have). Got the project-rag installer to its final step; one blocker left — a cp1252 Unicode crash writing `~/.claude.json`. (E8–E19)
- **Session 3 (2026-05-29):** Cleared the cp1252 blocker (`PYTHONUTF8=1`) → **project-rag MCP fully installed and verified live.** Installed the ue-addon. Downloaded all 13 corpus archives. Hit a new blocker: the merge produced an empty store — corpus content appeared "stranded." (E20–E21, plus a mis-diagnosed E22)
- **Session 4 (2026-05-29):** **Corrected the session-3 root-cause hypothesis** (it was NOT a Windows rename bug) and resolved the corpus blocker: the host venv simply lacked `zstandard`. Installed it, extracted the cached archives in place (no re-download), merged 12 bands into the canonical store (542,331 records), wired the `[env]`, restarted the daemon, and verified `engine_queryable: true`. Found two residual issues (E23, E24). (E22 corrected, E23–E24 new)

### The difficulties — by theme

The install was blocked or slowed **eleven** distinct times. They cluster into five themes:

1. **Missing/mis-located prerequisites the runbook assumed present.**
   - `coordinator_whoami` (Gate A) was not installed, its providing repo (`dbc-oduffy/coordinator-claude`) was never cloned, and the documented `pip install` path was wrong by two path segments (E2, E4). This was the single biggest time-sink and a hard stop in session 1.
   - `gh` CLI absent; `gh auth login` is interactive (E0, E6) — a structural problem for autonomous install.
   - PowerShell 7 is a hard requirement (the 180 KB installer can't be parsed by PS 5.1), but `winget install` recorded success while the MSI silently failed to land without elevation (E13).

2. **Windows-specific defects (the dominant failure class).**
   - **cp1252 Unicode crash** writing `~/.claude.json` (a `█` U+2588 char in the user's existing file) — fixed by `PYTHONUTF8=1` (E19). This single fix was the gate between "installed" and "not."
   - **Missing `zstandard` dependency** → the engine corpus merge silently produced an empty store. The archives are `.tar.zst`; with no zstd module the schema-read decompress raised `ModuleNotFoundError` and (because the call site is unprotected) propagated out *before* extraction, stranding 2.9 GB of `.tmp` files with no diagnostic (E22). This was mis-diagnosed in session 3 as a Windows `_atomic_replace` rename bug; session 4 verified the real cause on disk.
   - `project-rag-cli --help` itself crashes on cp1252 without `PYTHONUTF8=1` (E23-adjacent).
   - `ensure-project-rag-server.ps1` exits 1 on a `$lines.Count` null-property access *after* successfully spawning the daemon (E23).

3. **Documentation vs. reality mismatches.**
   - Installer scripts live in `project_rag_scripts/`, not the `scripts/` the runbook references — and the runbook is internally inconsistent about this (E1).
   - Gate A remediation didn't mention the whoami package must be installed into the *install venv*, not just any importable interpreter (E18).
   - Final MCP registration shape (top-level HTTP `mcpServers`) differs from what the installer log claims (per-project stdio) due to an HTTP migration step (E20).

4. **Silent / swallowed errors that made diagnosis expensive.**
   - The installer swallowed the real Python traceback behind a generic "Failed to read/merge" message; the cp1252 cause had to be extracted by running the embedded heredoc directly (E19).
   - `setup.ps1` swallows the corpus child-download error as a bare exit 1 (E20-era); the download script had to be run directly to see output.
   - `download_corpus.py` swallows the decompress failure into a stranded-file state with no error surfaced (E22).

5. **Cross-repo identity confusion.**
   - Three different "coordinator-claude" things coexist (installed plugin, local template, dbc dependency clone) — the runbook's assumed layout never matches (E5, E11).
   - The engine-corpus repo had to be set explicitly via `PROJECT_RAG_UE_ADDON_REPO` because `gh repo view` resolved against the *current* directory's git remote, picking the wrong repo (E21).

### Engineering decision that paid off (session 4)

When the merge produced an empty store, the prior session's handoff asserted a Windows `_atomic_replace` rename bug. Rather than act on the hypothesis, the actual on-disk state was inspected first: the 13 `tmp*.tmp` entries were **files** (the downloaded archives), not stranded extracted directories — which immediately falsified the rename theory and pointed at a pre-extraction failure. A one-line introspection (`_read_manifest_from_archive` on a cached archive) surfaced the real `ModuleNotFoundError: zstandard`. This let us **reuse the 2.9 GB already on disk** (extract-in-place, no re-download) instead of re-fetching.

### Outstanding work

1. **E24 (top priority):** `project_rag_blended_query` can't reach engine hits — the "engine" band leg isn't registered in the addon band catalog against the merged single-store collection. Last gap before engine RAG is usable from a normal query.
2. **Consumer priming:** index `claude-unreal-holodeck` (graph.db empty → `project_health` BROKEN) and complete consumer wiring.
3. **E23 (minor):** guard `ensure-project-rag-server.ps1:301` `$lines.Count`; make `wire` auto-restart the daemon.

### Upstream fixes to send back to `dbc-oduffy/project-rag` (PM call on PR-ing)

- **Declare `zstandard` as a runtime dependency** — it is mandatory for every `.tar.zst` corpus, yet undeclared (the `-ConsumerOnly` path shipped without it). *(E22)*
- **Wrap `download_corpus.py:233`** (`_read_schema_version_from_archive`) in try/except so a decompress/import failure returns a clean `DownloadResult(exit_code=10)` and deletes the temp artifact, instead of propagating and stranding gigabytes silently. *(E22)*
- **Set `PYTHONUTF8=1` / reconfigure stdout to UTF-8** for the `~/.claude.json` merge subprocess (or `ensure_ascii=True`). *(E19)*
- **Fix the corrupt committed `pyproject.toml` line 7** in `dbc-oduffy/project-rag` HEAD. *(E16)*
- **Update the runbook**: correct `scripts/` → `project_rag_scripts/`; document the venv-targeted whoami install; clarify which "coordinator-claude" is canonical. *(E1, E5, E18)*

> The full chronological evidence for every item above is in the **Friction entries** section below (E0–E24).

---

## Friction entries (chronological)

### E0 — Environment baseline (prerequisite scan)

- **[NOTE] Python:** `py -3` → Python 3.12.10 at `...\Programs\Python\Python312\python.exe` (python.org build — good, not MS Store).
- **[FRICTION] `python3` resolves to the MS Store / WindowsApps shim**, while `python` and `py -3` resolve to the real python.org 3.12. The project-rag AGENT.md prerequisites tell the agent to run `python3 --version` on "macOS/Linux" and `py -3` on Windows — fine — but any doc step that literally calls `python3 ...` (e.g. Step 2 `python <repo>/scripts/...`, Step 4/5 `python -c ...`) is ambiguous on Windows about which interpreter runs. On this box `python` = good, `python3` = UWP shim. Must consistently use `py -3` / the installer's own selector to avoid the UWP refusal class.
- **[NOTE] uv:** present (`...\WinGet\...\uv.exe`). The installer's W2 auto-install path won't be needed.
- **[BLOCKER] `gh` (GitHub CLI) is NOT installed.** The ue-addon engine-corpus download (`download-engine-corpus.{sh,ps1}`) and F-9 doctor remediation shell out to `gh release download`. Even if `gh` is installed via winget, `gh auth login` is an interactive browser/device flow that cannot be completed autonomously → engine corpus fetch is expected to be a hard stop.
- **[NOTE] GPU:** RTX 5070 Ti, driver 591.86 present → torch-CUDA fixup step (project-rag Step 3.5) is in scope.
- **[BLOCKER→fixable] machine-local registry absent:** `~/.claude/machine-local/` does not exist at all. project-rag installer **Gate B (Phase 0.7)** hard-exits without `~/.claude/machine-local/registry.toml`. Doc remediation: run `/coordinator:setup` Phase 3. The `coordinator:setup` skill IS available in this session, so this is satisfiable autonomously.
- **[NOTE] Plugins installed:** `~/.claude/plugins/` has `claude-unreal-holodeck` and `coordinator-claude`. coordinator-claude present satisfies the *plugin* half of Gate A; whether its `coordinator_whoami` Python package is importable is checked next.

### E1 — [MISMATCH] Installer scripts live in `project_rag_scripts/`, not `scripts/`

The project-rag agent runbook (`docs/install/AGENT.md`) references the installer at `<repo>/scripts/install-project-rag-plugin.ps1` in **Step 1, Step 3, Step 3.5, and the Reference section**. On disk, `<repo>/scripts/` does **not** contain it — the real path is `<repo>/project_rag_scripts/install-project-rag-plugin.ps1` (confirmed: `scripts\install-project-rag-plugin.ps1` → False; `project_rag_scripts\install-project-rag-plugin.ps1` → True). Same for `install_project_rag_plugin.py` and `fix-torch-cuda.ps1`. A literal follow of the runbook fails at "verify the file exists." The dir was renamed (`scripts/` → `project_rag_scripts/`) but AGENT.md wasn't updated. Note the runbook is *internally* inconsistent too: its "Reference" + "Dependency chain" sections correctly say `project_rag_scripts/...` while the numbered steps say `scripts/...`.

### E2 — [BLOCKER] Gate A unsatisfiable: `coordinator_whoami` absent, documented fix path wrong, provider repo not cloned

project-rag installer **Gate A (Phase 0.6)** requires the `coordinator_whoami` Python package to be importable by the pinned interpreter. Findings:

1. `py -3 -c "import coordinator_whoami"` → **`ModuleNotFoundError: No module named 'coordinator_whoami'`**. Gate A would hard-exit the installer.
2. AGENT.md's one-step fix is `pip install -e ~/.claude/plugins/coordinator-claude/coordinator/whoami/`. **That path does not exist** (`Test-Path` → False). There is no `coordinator/whoami/` under the installed plugin.
3. Searched BOTH the installed plugin (`~/.claude/plugins/coordinator-claude`) and the local repo (`C:\Delphi\coordinator-claude`) for any `*whoami*` file or any `pyproject`/`setup` declaring `coordinator_whoami` — **zero hits in both**. The package is not present anywhere on this machine.
4. AGENT.md "If something goes wrong" says to install coordinator-claude from **`https://github.com/dbc-oduffy/coordinator-claude`** — i.e. a *fourth* `dbc-oduffy` repo that was never mentioned or cloned. The local `C:\Delphi\coordinator-claude` is the coordinator plugin *template* (its CLAUDE.md says so) and does **not** ship `coordinator_whoami`. So the dependency provider repo is simply not on this machine.
5. The documented autonomous escape hatch (non-interactive implied consent → dep-chain walker auto-installs coordinator-claude) cannot work here either: fetching `dbc-oduffy/coordinator-claude` would require `gh`/authenticated git, and **`gh` is absent** (see E0). 

**Net:** the clean install cannot proceed past project-rag Gate A autonomously. The blocker is a missing prerequisite repo (`dbc-oduffy/coordinator-claude` providing `coordinator_whoami`) plus a stale/incorrect remediation path in the runbook, compounded by the absent `gh` CLI.

### E3 — [BLOCKER, downstream] Gate B (machine-local registry) also unmet, but moot for now

`~/.claude/machine-local/registry.toml` is absent (the whole `machine-local/` dir is missing). project-rag Gate B (Phase 0.7) would also hard-exit. This one is *fixable autonomously* — the `coordinator:setup` skill is available and its Phase 3 seeds the registry — but it is moot while Gate A (E2) blocks, so it was not run to avoid invasive setup under no benefit.

---

### E4 — [MISMATCH] `coordinator_whoami` real path differs from runbook by TWO segments

After cloning `dbc-oduffy/coordinator-claude` (see E5), the package was found at `…/coordinator-claude/plugins/coordinator/whoami/`. The runbook (and Gate A error text) says `~/.claude/plugins/coordinator-claude/coordinator/whoami/` — missing the `plugins/` segment under the repo root. `pip install -e "C:/Delphi/coordinator-claude-dbc/plugins/coordinator/whoami"` succeeded; `import coordinator_whoami` now OK; `python -m coordinator_whoami.project_rag` returns a well-formed envelope (contract_version 1, GPU detected, ms_store_shim=false). **Gate A CLEARED.**

### E5 — [FRICTION] Name collision: dependency repo vs. local template dir

The dependency repo is `dbc-oduffy/coordinator-claude`, but `C:\Delphi\coordinator-claude` already exists (the coordinator *template* / current working dir). Could not clone to the canonical sibling name; cloned to `C:\Delphi\coordinator-claude-dbc` instead. This means the runbook's assumed `~/.claude/plugins/coordinator-claude/...` layout never matches here — there are effectively two different "coordinator-claude" things on this machine (the installed plugin, the template repo) and now a third (the dbc dependency clone). Worth the project clarifying which is canonical.

### E6 — [NOTE] `gh` installed via winget (exit 0)

`winget install GitHub.cli` completed. `gh` will be on PATH for new shells. **`gh auth login` is still required and is interactive** — remains the pause point for the engine-corpus download.

### E7 — [UNCLEAR] Project root for project-rag is unspecified

project-rag registers per-project (indexes a *specific* codebase). The task said "install Daemon/Holodeck" without naming which project to index. The whoami probe auto-detected the cwd (`C:\Delphi\coordinator-claude`, no `.uproject`) as a candidate root — almost certainly not the intent. Needs a PM decision (likely the Lyra UE project, or one of the Delphi repos). Blocks running the project-rag installer meaningfully.

---

### E8 — [MISMATCH] "/coordinator:setup Phase 3" does not exist in the installed template coordinator

The resume checklist (and project-rag AGENT.md) say to seed Gate B by running `/coordinator:setup` Phase 3. The coordinator plugin **installed at `~/.claude/plugins/coordinator-claude`** (and the working-dir template `C:\Delphi\coordinator-claude`) has a `setup.md` with only Sections 1–4 (env prereqs, project config, persona, status) — **no Phase 3, no machine-local substrate, no `install-substrate.sh`**. Blindly invoking it would have configured the coordinator env and never created `registry.toml`.

The real Phase 3 lives in the **dbc clone**: `C:\Delphi\coordinator-claude-dbc\plugins\coordinator\commands\setup.md` (Phase 3 — Machine-local registry substrate), implemented by `…/plugins/coordinator/lib/install-substrate.sh`. This confirms the dbc-oduffy coordinator is the canonical product for the triad; the local template is a stripped-down OSS template.

### E9 — [FRICTION] `install-substrate.sh` expects `CLAUDE_PLUGIN_ROOT` to be the `plugins/` parent, not the plugin dir

`install-substrate.sh` resolves templates as `${CLAUDE_PLUGIN_ROOT}/coordinator/templates/...`. First run with `CLAUDE_PLUGIN_ROOT=…/plugins/coordinator` → FATAL (looked for `…/coordinator/coordinator/templates`). Correct value is `CLAUDE_PLUGIN_ROOT=C:/Delphi/coordinator-claude-dbc/plugins` (the dir that *contains* `coordinator/`). Ran with `COORDINATOR_NON_INTERACTIVE=1` → exit 0.

### E10 — [NOTE] Non-interactive substrate install lays down `.example` files but NOT a live `registry.toml`

Step 3 (seed prompt) is interactive-only, so a non-interactive run leaves only `registry.toml.example` / `registry.local.toml.example` — Gate B would still fail. Remediation done by hand per the Phase 3 doctrine: `cp registry.toml.example registry.toml` (tracked baseline: key declarations + `schema=1` + `concerns=["project_rag","unreal"]`), then `machine-local set` the four `repos.*` paths into `registry.local.toml`. **Gate B now CLEARED.**

### E11 — [DECISION/UNCLEAR] `repos.coordinator_claude` set to the dbc clone

Three "coordinator-claude" things exist (E5): installed plugin, template working dir `C:\Delphi\coordinator-claude`, and the dbc dependency clone. Set `repos.coordinator_claude = C:/Delphi/coordinator-claude-dbc` because the dbc clone is the dbc-oduffy product providing `coordinator_whoami` and the canonical triad coordinator. **PM: confirm this is the intended canonical coordinator for registry consumers.**

### E12 — [NOTE] `~/.claude/bin` added to Windows user PATH

The substrate installer prepended `C:\Users\pkauf\.claude\bin` to the user PATH (so `machine-local`/`claude-home`/`python3` resolvers are found). **Takes effect only in new shells / a Claude restart** — current tool shells still don't have it; invoked the reader by full path this session.

---

### E13 — [BLOCKER] project-rag installer requires PowerShell 7; PS 5.1 cannot parse it

`install-project-rag-plugin.ps1` (180 KB) contains single-quoted here-strings of embedded Python (f-strings like `print(f"...{'OK' if ok else 'FAIL'}")`). Under **Windows PowerShell 5.1** the parser mis-reads these as PowerShell and dies with a cascade of `Unexpected token 'if'` / missing-brace errors. AGENT.md confirms intent: **every** Windows install/doctor/update command uses `pwsh` (PS7), never `powershell`. PS7 is a hard prerequisite.

`winget install Microsoft.PowerShell` reported "Successfully installed (7.6.2.0)" and `winget list` shows it — **but `pwsh.exe` is absent** (`C:\Program Files\PowerShell\` does not exist; no Uninstall-registry entry). Cause: the machine-scoped PowerShell MSI needs elevation; the non-elevated Claude tool shell could not write to `Program Files`, yet winget still recorded the package. **Needs an elevated `winget install Microsoft.PowerShell` (PM) OR a portable per-user PS7 extract (autonomous, if authorized).**

### E14 — [BLOCKER/DECISION] Pre-existing 375 MB UE-docs corpus in holodeck `vector_store/` — handoff assumed absent

`C:\Delphi\claude-unreal-holodeck\vector_store\` is NOT empty (the resume checklist guessed "likely absent"). It contains a full OLD-install corpus:
- `chroma.sqlite3` 375 MB (Apr 24) · `bm25_cache_ue_docs.pkl` 166 MB · `doc_texts.sqlite3` 247 MB · `chunk_index_state.json` 9 MB · a `f405c4ea-…` chroma collection dir · `ue-mcp-server.pid` (PID 65820 — **verified stale/not running**).

In the NEW host/addon split, the engine (UE-docs) corpus is supplied by the **ue-addon** via `gh release download` and bound to project-rag with `--engine-vector-store`. AGENT.md F-9 is literally "corpus schema version below host minimum," so the OLD store may be schema-incompatible with the rewritten host. **Decision needed:** reuse this OLD store as the engine corpus (save the multi-GB re-download / re-index) vs. download a fresh engine corpus from the ue-addon release and treat this dir as stale leftover. Until decided, NOT passing `-EngineVectorStore`; NOT touching the existing files.

### E15 — [NOTE] Installer dry-run is gated behind E13

Attempted `install-project-rag-plugin.ps1 -DryRun -FromClaudeCode -NonInteractive -ProjectRoot C:/Delphi/claude-unreal-holodeck` under PS 5.1 → parse-fail (E13). No dry-run preview obtained yet; will retry under pwsh once PS7 lands.

---

### E16 — [BLOCKER, upstream bug] `project-rag/pyproject.toml` line 7 is committed garbage

The cloned `dbc-oduffy/project-rag` (v0.8.0) ships a **corrupt `pyproject.toml`**: line 7 is the stray text `0.7.0 line found` (line 8 has the real `version = "0.8.0"`). It is committed in HEAD (clean working tree, present in `git show HEAD:pyproject.toml`) — not a local edit. Looks like command stdout (`... line found`) was accidentally written into the manifest during a version bump. `uv`/pip fail-loud: `TOML parse error … key with no value, expected '='`, so **every `pip install -e .` of project-rag dies**, blocking the installer at dependency bootstrap. Grep confirms the corruption is isolated to this one line. **Fixed locally** by deleting line 7 (unblocks install); **upstream dbc-oduffy/project-rag needs the same one-line fix at source.**

### E17 — [NOTE] `-DryRun` is not fully dry

The installer's `-DryRun` still bootstraps the `.venv` (via `uv venv`) and runs `uv pip install -e` before reaching the dry-run-guarded mutations — that's how E16 surfaced. It did NOT touch `~/.claude.json` or the holodeck `vector_store/`. Treat `-DryRun` as "no config/registration writes," not "no filesystem effects."

### PM DECISIONS (2026-05-27, session 2)
- **PS7:** portable per-user extract → installed PS7 **7.6.2** at `C:\Users\pkauf\pwsh7\pwsh.exe` (no elevation). Invoke installer via this full path.
- **Engine corpus:** download FRESH from the ue-addon (`gh release download`); ignore the OLD 375 MB `vector_store/`. Base project-rag install runs WITHOUT `-EngineVectorStore`; engine store bound later from the fresh download.
- **gh auth:** PM running `gh auth login` interactively this session.

### E18 — [BLOCKER] Gate A clearance into ambient python is INSUFFICIENT — installer's isolated venv needs `coordinator_whoami` too

The installer (venv-primary doctrine) bootstraps its own isolated venv at `C:\Delphi\project-rag\.venv` and runs the Phase 0.6 `coordinator_whoami` preflight against **that venv's** interpreter — not the ambient python.org 3.12 where Gate A was originally cleared (E4). The venv could not `import coordinator_whoami` → Phase 0.6 hard-failed and the installer `exit`ed (with NO error text captured in the log — the failure is silent; the last log line is just "[Phase 0.6] Checking coordinator_whoami preflight..."). First full install run also wasted time because `-DryRun`'s earlier half-built empty venv had to be deleted (E17) before a clean dep install.

**Fix:** install whoami editable into the venv: `uv pip install --python C:/Delphi/project-rag/.venv/Scripts/python.exe -e C:/Delphi/coordinator-claude-dbc/plugins/coordinator/whoami`. Verified `import coordinator_whoami` OK in-venv; envelope returns contract_version 1, GPU present (11.9 GB free, cuda 591.86). Dep install itself succeeded and pulled a CUDA torch build (`torch==2.12.0+cu130`, `torchvision==0.27.0+cu130`) — the Section K GPU probe selected CUDA wheels directly. **Doc gap:** the runbook's Gate A remediation doesn't say the whoami install must target the project-rag venv, not just any importable interpreter.

### E19 — [BLOCKER, upstream bug] installer crashes writing `~/.claude.json` — cp1252 UnicodeEncodeError (Windows)

The installer's Section F read/merge step (line 2054, "Failed to read/merge $ClaudeJson (exit 1)") **swallows the real Python traceback** (it routes ErrorRecords into `$mergeStderr`, which is NOT included in the surfaced Write-Error). Extracted the embedded merge heredoc (installer lines 1781–1979) to a temp `.py` and ran it directly against the venv python. Real cause:
```
print(json.dumps(data, indent=2, ensure_ascii=False))   # installer ~line 1978
UnicodeEncodeError: 'charmap' codec can't encode character '█' (█) in position 5483
```
The operator's existing `~/.claude.json` contains a `█` (U+2588) somewhere in history; the merge prints with `ensure_ascii=False` to a Windows stdout pinned to **cp1252**, which can't encode it. **VERIFIED FIX:** re-run the same script (and the whole installer) with `PYTHONUTF8=1` → exit 0, valid JSON, no stderr. Upstream should set `PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8` for the merge subprocess, or `sys.stdout.reconfigure(encoding='utf-8')`, or `ensure_ascii=True`. Two latent installer defects compounded it: (a) the swallowed traceback made it look like a silent death; (b) the `[gpu]` extra install earlier used `uv pip install ... 'project-rag[gpu]'` WITHOUT a `--python`/venv context → "No virtual environment found" (exit 2, non-fatal, fell back to CPU + ambient nvidia-ml-py).

---

### E20 — [RESOLVED] Installer completes with `PYTHONUTF8=1`; registration lands at top-level (HTTP migration); minor `setup-state.json` write failure

Re-ran the full installer (session 3, 2026-05-29) with `PYTHONUTF8=1` + `PYTHONIOENCODING=utf-8` set in the environment → **exit 0.** The E19 fix holds at full-installer scope, not just the extracted merge script. Confirmed live:
- `~/.claude.json` merge succeeded (no cp1252 crash); the `█` U+2588 char is still in the file but no longer fatal.
- MCP server registered and reachable: daemon up on `127.0.0.1:8767`; `project_whoami` + `project_health` both return `verdict: ok`; all 18 tools pass boot `tool_smoke`.
- GPU path live: `torch=2.12.0+cu130`, 11.9 GB VRAM free, CUDA driver 591.86. The earlier `[gpu]`/nvidia-ml-py concern (E19b) is moot — `pynvml` imports fine in the venv.
- **[MISMATCH/NOTE] Registration shape:** installer log claims per-project (`projects[...holodeck].mcpServers.project-rag`, stdio), but the final `~/.claude.json` has the entry at **top-level `mcpServers`** as `{"type":"http","url":"http://127.0.0.1:8767/mcp"}`. An HTTP migration (backup `~/.claude.json.pre-project-rag-http-migration`) moved it. The per-project `mcpServers` ends up `{}` — this is by design post-migration, NOT a clobber. Transient gotcha: reading `~/.claude.json` during Claude Code's resume-flush briefly showed the project key absent; it stabilized after the flush.
- **[FRICTION, minor] `setup-state.json write failed`** at the end of the run — `~/.claude/project-rag/install-profile.json` was written but `setup-state.json` is absent. Non-fatal; state file may be incomplete/stale on next run. Worth an upstream note (same Windows-file-write fragility class).
- **[NOTE] Index is empty (expected):** `project_health` verdict `BROKEN — assets table empty`; graph.db has 0 rows, Chroma 0 chunks. The project is *registered* but never *primed*. Next stage = ue-addon + fresh engine corpus + `/project-rag:index` on the consumer project.

**Restart note confirmed:** the `mcp__project-rag__*` tools only appeared after a full Claude Code restart (they were live on this session's resume), matching the installer's "RESTART REQUIRED" banner.

---

### E22 — [BLOCKER, RESOLVED — root cause was NOT atomic-replace] Engine corpus merge produced empty store because host venv lacked `zstandard`

Session 3 hypothesized the stranded-corpus blocker was a Windows `_atomic_replace` rename no-op in `download_corpus.py`. **That hypothesis was wrong.** Verified on disk (session 4, 2026-05-29): the 13 `tmp*.tmp` entries in the addon data dir were **files** (the downloaded `.tar.zst` archives, magic `28b52ffd`), not stranded extracted dirs. `_atomic_replace` (which extracts AND unlinks the artifact in its `finally`) was **never reached**.

**True root cause:** the host venv (`C:\Delphi\project-rag\.venv`) had **no `zstandard` module installed**, and it is **not declared as a dependency** anywhere in project-rag (grep of all `*.toml`/`*.txt`/`*.cfg` → zero hits), despite `download_corpus.py:468` asserting it is "already a host runtime dep." In `download_corpus()`, line 233 calls `_read_schema_version_from_archive(artifact_path)` **outside any try/except**; that calls `_maybe_decompress_zst` (line 523, also outside the function's inner try) which does `import zstandard` → `ModuleNotFoundError` → wrapped as RuntimeError → **propagates out of `download_corpus` entirely**, so the artifact is never extracted, never unlinked, and the band dir is never created. Identical failure for all 13 bands → 13 stranded `.tmp` files → merge found no band dirs → empty 167 KB canonical chroma.

**Two upstream defects (project-rag):**
1. **Missing dependency declaration.** `zstandard` must be a declared runtime dep (it is mandatory for every `.tar.zst` corpus). A `-ConsumerOnly` install path silently shipped without it.
2. **Unprotected schema-read strands the artifact.** `download_corpus.py:233` should wrap `_read_schema_version_from_archive` in try/except and return a clean `DownloadResult(exit_code=10, ...)` (deleting the temp artifact) instead of letting a decompress/import error propagate and strand 2.9 GB of `.tmp` files with no diagnostic.

**RESOLUTION (no re-download):** `uv pip install --python C:/Delphi/project-rag/.venv/Scripts/python.exe zstandard` → `zstandard==0.25.0`. Then extracted the 13 cached archives in place via the same `_atomic_replace` (reused the 2.9 GB on disk; auto-deleted the stranded `.tmp`s). Ran `merge_per_band_chroma_into_canonical.py` over the 12 vector-store band dirs → **canonical `chroma_unreal_5.7` = 542,331 records, post-merge assertion OK (source=542331, skipped=0).** `project-rag-cli wire` wrote `[env]` (`PROJECT_RAG_ENGINE_VECTOR_STORE` + `PROJECT_RAG_STRUCTURAL_INDEX`). Daemon restarted via `ensure-project-rag-server.ps1` → `engine_domain_status` reports `engine_queryable: true`, `collection_loaded: true`, `semantic_search_verdict: ok`, `cpp_symbol_verdict: ok`.

### E23 — [FOLLOW-ON, OPEN] `ensure-project-rag-server.ps1` crashes post-spawn on `$lines.Count`; `wire` kills daemon without auto-restart

- **[FRICTION]** `project-rag-cli wire` hard-kills the running daemon (to reload `[env]`) but does **not** restart it; nothing listens on 8767 afterward until `ensure-project-rag-server.ps1` is run manually. Wire should re-run the ensure-script (or `process-wire-requests`) itself.
- **[BUG, non-fatal]** `ensure-project-rag-server.ps1:301` does `if ($lines.Count -gt 500)` where `$lines` can be `$null`/scalar → `ParentContainsErrorRecordException: The property 'Count' cannot be found`. The daemon **does** spawn and bind the port before this (log: "process spawned (port bound)"); the script just exits 1 on its own post-spawn log-tail summary. Guard with `@($lines).Count`.

### E24 — [FOLLOW-ON, OPEN] Blended-query "engine" band leg not registered in addon band catalog → engine hits unreachable via `project_rag_blended_query`

Despite `engine_domain_status: engine_queryable=true` (the daemon can query the engine collection directly), `project_rag_blended_query(secondary_weights={"engine":1})` returns `verdict: degraded_runtime`, `hits: []`, hint: *"Requested band(s) ['engine'] carry non-zero weight but are not registered in the addon band catalog … Install or re-register the addon that supplies these bands."* The single-store merge collapsed all 12 source bands into one collection `chroma_unreal_5.7`, but the blended-query band router still expects per-band catalog registration (the generic deprecated `engine_weight`/`"engine"` leg name does not map to the registered band names like `unreal_5.7_runtime`). `engine_domain_status.bands[]` shows only 4 band-name aliases resolving to the canonical collection (each reporting the full 542,331 count → top-level `chunk_count: 2169324` is a 4× double-count artifact), the other 8 report `corpus_missing`. **Next:** re-register/seed the addon band catalog against the merged single-store collection, or determine the correct band-name(s) to pass to blended_query so engine hits are reachable end-to-end. This is the last gap before the engine corpus is usable from a normal query.

---

## RUN STATUS: ENGINE CORPUS MERGED + WIRED + DAEMON-LOADED (engine_queryable=true); residual = blended-query band registration (E24)

Session 4 (2026-05-29): Cleared the session-3 corpus blocker — **real cause was missing `zstandard` dep (E22), not the atomic-replace rename bug hypothesized in the handoff.** Installed `zstandard==0.25.0`, extracted the 13 cached archives in place (no re-download), merged 12 bands → canonical `chroma_unreal_5.7` (542,331 records), wired `[env]`, restarted daemon. `engine_domain_status` = engine_queryable:true. **Residual/open:** (E24) blended-query "engine" band leg not in the addon band catalog → engine hits not yet reachable via `project_rag_blended_query`; (E23) `wire` doesn't auto-restart daemon + ensure-script `$lines.Count` bug; (E22) two upstream project-rag fixes to send back (declare `zstandard`; wrap `download_corpus.py:233`). Still pending from before: prime the consumer project (`claude-unreal-holodeck`) index (graph.db empty → project_health BROKEN until primed); holodeck consumer wiring.

---

## RUN STATUS: INSTALLED — project-rag MCP live (daemon 8767); next = ue-addon + fresh corpus + index

Session 3 (2026-05-29): E19 fix (`PYTHONUTF8=1`) cleared the last blocker. Full installer exit 0; MCP server registered (top-level HTTP → daemon 8767) and verified via live `project_whoami`/`project_health` (both ok, 18/18 tools smoke-pass). gh auth done by PM (`peter-kaufman`, scopes incl. repo+workflow). torch-CUDA confirmed no-op (already cu130). **Remaining:** (1) ue-addon install (`uv pip install -e .` + `-e ../project-rag` into the venv) + register; (2) `gh release download` the FRESH engine corpus, re-run installer with `-EngineVectorStore <corpus>` to bind; (3) index the consumer project (graph.db currently empty → health BROKEN until primed); (4) holodeck consumer wiring. Minor: `setup-state.json` write failed (non-fatal).

---

## RUN STATUS: (superseded) PAUSED — installer at FINAL step; ONE fix left (`PYTHONUTF8=1`), then continue to ue-addon

Gate A + Gate B cleared; PS7 7.6.2 portable installed; project-rag deps installed (CUDA torch 2.12.0+cu130); registry + cli-path + install-profile written. The ONLY remaining blocker is E19 (cp1252 unicode crash on the `~/.claude.json` merge) — **fix verified: set `PYTHONUTF8=1` and re-run the installer.** `~/.claude.json` project-rag entry is still ABSENT (registration never completed). See handoff `tasks/handoffs/2026-05-27_2010_triad-install.md` for the exact resume command. Corpus decision = download fresh (ignore OLD `vector_store/`); `gh auth login` being done by PM.

---

## RUN STATUS: (superseded) PAUSED for PM — Gate A + Gate B cleared; blocked on PS7 install + corpus decision + gh auth

Gate B substrate laid down via dbc `install-substrate.sh`; live `registry.toml` + `registry.local.toml` (4 repo paths) created and verified through the `machine-local` reader. Gate A still satisfied. PowerShell 7 installed via winget (7.6.2) but did not land on disk (elevation, E13). Three items need PM input before the heavy install proceeds: (1) PS7 — elevated winget vs. authorize portable extract; (2) pre-existing 375 MB corpus — reuse vs. re-download (E14); (3) `gh auth login` (interactive) for the later corpus step.

---

## RUN STATUS: (superseded) PROGRESSING — Gate A cleared, gh installed; paused for project-root decision + context checkpoint

Cleared the headline blocker (Gate A) and installed gh. Remaining before project-rag installer can run: (1) **Gate B** — seed `~/.claude/machine-local/registry.toml` via `/coordinator:setup` Phase 3 (autonomous but a heavier skill); (2) **project-root decision** (E7); then the installer itself runs a heavy pip dependency install + torch-CUDA fixup. `gh auth login` (interactive) gates the later corpus step.

**Install actions taken so far:** `pip install -e` of `coordinator_whoami` into python.org 3.12; `winget install GitHub.cli`. No `~/.claude.json` edits, no project-rag/holodeck registration, no corpus download yet.

**PM decisions (2026-05-27):** (1) project-rag project root = **`C:\Delphi\claude-unreal-holodeck`** (index the holodeck repo itself). (2) Save a `/handoff` before the heavy install phase so it runs in fresh context.

### NEXT-SESSION RESUME CHECKLIST (pick up here)
1. Confirm `gh` on PATH in fresh shell (`gh --version`); run `gh auth login` (interactive — needs PM) to unblock corpus later.
2. Seed Gate B: run `/coordinator:setup` (Phase 3) to create `~/.claude/machine-local/registry.toml`.
3. Run project-rag installer (note REAL path — `project_rag_scripts/`, not `scripts/`):
   `pwsh C:/Delphi/project-rag/project_rag_scripts/install-project-rag-plugin.ps1 -FromClaudeCode -ProjectRoot "C:/Delphi/claude-unreal-holodeck"` (+ `-EngineVectorStore` if a holodeck `vector_store/chroma.sqlite3` exists — likely absent per OLD audit).
4. Run torch-CUDA fixup: `pwsh C:/Delphi/project-rag/project_rag_scripts/fix-torch-cuda.ps1` (RTX 5070 Ti present).
5. Verify registration in `~/.claude.json`; then ue-addon (`pip install -e .` + `pip install -e ../project-rag` + register + `gh release download` corpus); then holodeck consumer setup.
6. Gate A already satisfied: `coordinator_whoami` editable-installed from `C:/Delphi/coordinator-claude-dbc/plugins/coordinator/whoami`.

---

## (superseded) earlier halt note — kept for history

## RUN STATUS: HALTED at project-rag prerequisites (Gate A)

Reached the very first installable step and stopped at an unsatisfiable hard prerequisite. **No install actions were taken** — no pip installs, no `~/.claude.json` edits, no plugin registration, no corpus download. Only read-only probes ran. Nothing to roll back.

**To unblock (PM decisions needed):**
1. Clone/obtain `dbc-oduffy/coordinator-claude` (the repo providing `coordinator_whoami`) — the install hard-depends on it and it's not on this machine.
2. Install + authenticate `gh` (`winget install GitHub.cli` then `gh auth login` — auth is interactive) to unblock both the coordinator fetch path and the engine-corpus download.
3. Then re-run: satisfy Gate A (`pip install -e` the whoami package at its *actual* path), seed machine-local registry via `/coordinator:setup` Phase 3 (Gate B), then project-rag installer → ue-addon → holodeck.
