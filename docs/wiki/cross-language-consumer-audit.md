---
system: cross-language-consumer-audit
last_updated: 2026-05-18
status: active
provenance: authored 2026-05-18 — captures the inline-foreign-language invocation blind spot in polyglot consumer audits
---

# Cross-Language Consumer Audit

> When auditing consumers of a module or symbol in a polyglot codebase, static `import`/`require`/`from` grep misses consumers invoked through inline foreign-language stanzas. This guide covers the full checklist.

## The Trap

A standard audit for consumers of `foo` runs something like:

```
grep -r "import foo\|from foo import\|require('foo')" .
```

This finds direct language-level imports. It misses invocations like:

```bash
python -c "import foo; foo.bar()"
pwsh -Command '$x = [foo]::method()'
node -e "const f = require('foo'); f.run()"
bash -c "python foo_runner.py --flag"
```

These patterns appear in shell scripts, Makefiles, CI YAML, test fixtures, and inline subprocess calls from other languages. When you rename, remove, or change the interface of `foo`, grep-only audits declare zero consumers while three CI jobs silently break at runtime.

## Audit Checklist When Modifying a Module

Run ALL of the following for a complete picture before renaming, deleting, or changing the public interface of any module:

1. **Direct imports** — language-native `import`/`from`/`require`/`use`
2. **Inline `python -c`** — shell stanzas that embed a Python one-liner
3. **Inline `pwsh -Command` / `powershell -Command`** — PowerShell inline blocks
4. **Inline `node -e`** — Node.js one-liner invocations
5. **Inline `bash -c` / `sh -c`** — shell subshell stanzas (may call the module indirectly via a script name)
6. **Here-docs (`<<EOF`, `<<'EOF'`)** — multi-line embedded scripts piped to an interpreter
7. **CI/CD YAML `run:` blocks** — GitHub Actions, GitLab CI, etc. embed shell inline

## Concrete Grep Patterns

```bash
# 1. Direct Python imports
grep -rn "import <module>\|from <module> import" --include="*.py" .

# 2. Inline python -c stanzas
grep -rn "python[3]* -c ['\"].*import <module>" .

# 3. Inline pwsh / powershell
grep -rn -i "pwsh.*-Command.*<module>\|powershell.*-Command.*<module>" .

# 4. Inline node -e
grep -rn "node -e ['\"].*require.*<module>" .

# 5. bash -c / sh -c
grep -rn "bash -c ['\"].*<module>\|sh -c ['\"].*<module>" .

# 6. Here-docs — match interpreter line + module reference within N lines
grep -rn "<<['\"]?EOF" . | xargs -I{} grep -l "<module>" {} 2>/dev/null
# or: grep -rn -A20 "<<['\"]?EOF" . | grep "<module>"

# 7. CI YAML run blocks
grep -rn "run:.*<module>\|  - .*<module>" --include="*.yml" --include="*.yaml" .
```

Replace `<module>` with the actual module name. Run from the repo root. Use `head_limit:0` in Grep tool calls to avoid silent truncation.

## When to Escalate to Full-Repo Grep

- **Targeted grep** (scoped to known consumer directories) is sufficient when the module is clearly internal with a narrow call surface (e.g., a single-purpose utility used by 1-2 subsystems).
- **Full-repo grep** is required when:
  - The module is a shared utility or has a public-facing name
  - The codebase mixes Python, PowerShell, Bash, and JS in the same repo
  - CI/CD configuration lives outside the main source tree
  - Any previous audit found inline-invocation consumers (pattern has recurred once)

When in doubt, full-repo is cheap. A missed consumer costs a broken pipeline run.

## Beyond Grep — Coupling Channels a Reads-Only Census Cannot See

Inline-invocation grep (above) finds *textual* consumers. It does **not** find consumers that couple through a channel with no textual reference to the module at all. A relocation/rename survival oracle that probes only the one obvious channel — the file read — passes green while a second channel silently degrades.

Enumerate **every channel a consumer resolves through** before declaring a relocation safe:

1. **File reads** — the obvious channel; the one grep and a naive survival check both cover.
2. **Interpreter / package borrowing** — a consumer that borrows another component's private venv or interpreter (e.g. a daemon importing through `~/.claude/.coordinator-venv` for `coordinator_whoami`). No `import <module>` line names the moved path; a reads-only census sees nothing, yet the import breaks at runtime when the venv relocates.
3. **Live-service health** — a consumer that reaches the moved component over a running socket/daemon, not a file. Probe the service actually answers post-move, not just that its config file resolves.

A consumer-survival AC must assert one probe **per channel**, not one probe for the whole component. (Empirical source: durable-substrate C7 dogfood — AC9's project-rag survival check verified the concern-file read (passed) while the daemon silently degraded on borrowed-venv import, 2026-07-06.)

**`--check-only` is not a proven no-mutation preview until you prove it.** Before trusting a migration tool's `--check-only`/`--dry-run` as a safe preview of a relocation, confirm it does not run the real mutation — the same C7 dogfood found a `--check-only` that executed the actual migration.

## Format / Schema Changes Are Consumer-Audit Triggers

A mid-plan change to a foundational **artifact shape** — `.yaml`→`.md`, a renamed required field, an id moved from frontmatter into body text — is a consumer-audit event exactly like a module rename. Every consumer that hard-codes the old shape breaks silently: a hook globbing `*.yaml` becomes a dead-letter drop, an emitter that skip-silently on an absent field stops emitting, an id-passthrough that assumed a frontmatter key falls back to a text workaround. None throw.

When a foundational shape changes mid-plan, **re-thread every consumer before shipping** — grep for the glob patterns, the required-field checks, and the id passthroughs, and update each. Do not rely on the shape-change author's mental model of "who reads this"; the silent-failure consumers are precisely the ones not in that model. (Empirical source: a `.yaml`→`.md` change left three silent-failure bugs each caught only by fresh-eyes review.)

## Worked Example — Package Retirement Down to a Subprocess-Invoked Script

`coordinator_whoami` (a Python package, `coordinator/whoami/`) was retired
(archive/specs/2026-08-23-retire-coordinator-whoami-entirely.md). Its cross-repo consumers
(project-rag, example-game-repo) never imported it — every one shelled out
(`[sys.executable, "-m", "coordinator_whoami.machine"]`), because project-rag's own contract
bans importing whoami-shaped capability (`core/host_inventory.py:6-11`, "LOAD-BEARING -- do NOT
replace with Python import"). A consumer census run as an **import grep** would have found zero
matches by construction — the retirement plan's own deferral was first justified on exactly that
measurement, then reopened once the shell-out invocation shape was accounted for. This is the
"Beyond Grep" class above (§ Interpreter / package borrowing), sharpened: a subprocess-invoked
dependency that is never once `import`ed is invisible to every grep pattern in this document's
own checklist unless the audit specifically greps for the invocation string
(`-m coordinator_whoami`, `python_whoami`, etc.) rather than an `import` statement.

Of twelve probe functions in the retired package, direct consumer polling (not a grep, an
explicit ask to each named consumer team) found exactly one still needed: `_probe_gpu`. It
survives as a standalone script, `coordinator/bin/host-gpu-probe.py`, invoked by absolute path —
**never imported, never a package** — emitting `{"gpu": {...}}` on stdout. Consumers that shelled
out to `python -m coordinator_whoami.machine` and read `envelope["gpu"]` now shell out to
`python <repo>/coordinator/bin/host-gpu-probe.py` and read `envelope["gpu"]` from that script's
own JSON — same shape, same twelve keys, different invocation string. Any repo-wide search for
who calls the old package must therefore also search for who calls the new script, using the
same inline-invocation checklist above (item 2, `python -c`/`-m` stanzas) rather than assuming a
deleted package has no remaining textual footprint.

## Cross-References

- `docs/wiki/implementation-standards-by-domain.md` — domain-level standards including subprocess and shell integration patterns
- `docs/wiki/pre-dispatch-verification.md` — substrate verification discipline (grep seams before planning)
