# Gitignore Policy

## Principle

The default failure mode must be **"tracked too much"**, never **"silently lost work."** A file that shouldn't be tracked is a minor cleanup; a file that was silently ignored and never committed is lost work.

## Rules

### No deny-all patterns

The following patterns are forbidden in any `.gitignore` file:

| Pattern | What it does | Why it's forbidden |
|---------|-------------|-------------------|
| `*` | Ignores everything | Forces allowlist maintenance; one missed entry = lost work |
| `*.*` | Ignores all files with extensions | Same problem — silently drops new file types |
| `/*` | Ignores everything at root | Root-scoped deny-all with the same failure mode |

### No deny-then-allowlist within directories

A pattern like `somedir/*` followed by `!somedir/keep-this` is a deny-all-then-allowlist within that directory. This is forbidden because:

1. New files added to `somedir/` are silently ignored
2. Contributors must remember to update the allowlist for every new file
3. Forgotten entries are invisible — `git status` won't show what you can't see

### What to do instead

Use **allow-all-then-exclude** — the standard `.gitignore` approach:

```gitignore
# Good: exclude specific things you don't want
node_modules/
*.pyc
__pycache__/
.env

# Bad: deny everything then allow specific things back
*
!*.py
!*.md
```

## Enforcement

The CI script `.github/scripts/validate-gitignore.py` checks for:

1. **Global deny-all** (`*`, `*.*`, `/*`) — any occurrence fails the check
2. **Directory deny-then-allowlist** — a `dir/*` pattern followed by 3+ `!dir/...` exceptions where >50% of subsequent lines are exceptions triggers a warning

## Rationale

This policy exists because of a specific failure mode in AI-assisted development: when agents create or modify `.gitignore` files, they sometimes reach for deny-all patterns (a common pattern in build output directories). In a workflow where commits happen frequently and automatically, a bad `.gitignore` pattern can silently exclude work for an entire session before anyone notices.
