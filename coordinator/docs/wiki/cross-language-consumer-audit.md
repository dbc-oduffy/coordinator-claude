---
system: cross-language-consumer-audit
last_updated: 2026-05-18
status: living
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

## Cross-References

- `docs/wiki/implementation-standards-by-domain.md` — domain-level standards including subprocess and shell integration patterns
- `docs/wiki/pre-dispatch-verification.md` — substrate verification discipline (grep seams before planning)
