# CI/CD Pipeline

Automated validation for coordinator-claude. All checks are Python scripts with no external dependencies beyond PyYAML, runnable both locally and in GitHub Actions.

## Design Principles

- **Every check runs locally with the same command as CI.** No "works in CI" surprises. Run `python .github/scripts/run-all-checks.py` and get the same result as CI.
- **Fail loud, fail early.** Each check is a separate named step — failures are isolated and obvious.
- **Convention over configuration.** The local runner discovers scripts by naming pattern (`validate-*.py`, `check-*.py`), not a hardcoded list. Add a script, it runs automatically.
- **Advisory vs. blocking.** PR validation is blocking (must pass to merge). Health checks are advisory (create issues, don't block).
- **Standalone scripts, no frameworks.** Each script is self-contained Python. Dependencies: stdlib + PyYAML only.

## Running Locally

```bash
python .github/scripts/run-all-checks.py
```

This runs all validation scripts and reports a pass/fail summary. Run it before committing.

## Validation Checks (Blocking)

These run on every PR to `main` and on push to `work/**`/`feature/**` branches.

| Check | Script | What It Catches |
|-------|--------|-----------------|
| Secrets | `check-secrets.py` | Accidental API keys, AWS credentials, GitHub tokens, hardcoded passwords |
| File sizes | `check-file-sizes.py` | Files over 1 MB in the PR diff (prevents permanent repo bloat) |
| Gitignore policy | `validate-gitignore.py` | Deny-all patterns that violate the gitignore policy |
| Frontmatter | `validate-frontmatter.py` | Missing or malformed YAML frontmatter in plugin components |
| References | `validate-references.py` | Broken links in routing files, dead agent references, broken relative links |
| JSON schemas | `validate-json-schemas.py` | Structural errors in settings.json, known_marketplaces.json, installed_plugins.json |
| Agent tools | `validate-agent-tools.py` | Consistency between tool lists in YAML frontmatter and behavioral instructions |
| Spec line counts | `check-spec-line-counts.py` | Spec files (SKILL.md, PIPELINE.md) that have grown beyond a reasonable ceiling |
| README inventory | `check-readme-inventory.py` | Coordinator README component counts that don't match actual file counts |
| Hook paths | `validate-hook-paths.py` | Hook script paths in hooks.json that don't resolve to actual files |

## Secrets Scanning

The secrets scanner supports two suppression mechanisms for false positives:

**Inline suppression** — add `# noqa: secrets` to a line:
```python
EXAMPLE_KEY = "sk-test-not-a-real-key"  # noqa: secrets
```

**File-based allowlist** — for files that don't support comments (e.g., JSON), add entries to `.github/.secrets-allowlist`:
```
path/to/file.json:42
```
Format: `filepath:line_number`, one per line.

## Health Checks (Advisory)

A weekly cron workflow (`health-check.yml`) runs Monday mornings and creates a GitHub issue with the `health-check` label if it finds anything.

Health checks never fail the build — they create issues for humans to triage:
- Stale `work/*` branches with no commits in 7+ days
- Git-tracked files over 1 MB
- Repo-specific drift detection

## Workflow Architecture

**`validate-plugins.yml` — PR Validation**
- Trigger: PR to `main` + push to `work/**`/`feature/**`
- Job name: `validate` (stable contract — keep this name if you add branch protection)

**`health-check.yml` — Weekly Health**
- Trigger: cron (Monday 9am UTC) + manual `workflow_dispatch`
- Output: GitHub issue with `health-check` label

## Adding a New Check

1. Create `.github/scripts/validate-<name>.py` or `.github/scripts/check-<name>.py`
2. Script must exit 0 on success, non-zero on failure
3. Print human-readable output (errors, then summary line)
4. Add a step to `validate-plugins.yml` if it should be blocking
5. The local runner (`run-all-checks.py`) picks it up automatically by convention

No configuration files to update. No imports to register. Just name the file correctly and it runs.

## Branch Protection

The repo uses a GitHub repository ruleset for `main`:
- Require PR (0 approvals) — no direct push
- Block deletion
- Force push: allowed
- Required status checks: none by default (CI is advisory, not a merge gate)

To make CI a required merge gate, add the `validate` status check to your ruleset:
```bash
gh api repos/{owner}/{repo}/rulesets \
  --method POST \
  --input - <<'EOF'
{
  "name": "Main branch protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["refs/heads/main"],
      "exclude": []
    }
  },
  "rules": [
    {"type": "pull_request", "parameters": {"required_approving_review_count": 0, "dismiss_stale_reviews_on_push": false, "require_code_owner_review": false, "require_last_push_approval": false, "required_review_thread_resolution": false}},
    {"type": "deletion"},
    {"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": true, "required_status_checks": [{"context": "validate"}]}}
  ]
}
EOF
```
