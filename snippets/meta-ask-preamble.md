<!-- canonical source for meta-ask-preamble — edit here, then run bin/verify-snippet-sync meta-ask-preamble --fix -->
<!-- consumers: discovered at runtime by bin/verify-snippet-sync meta-ask-preamble via grep for BEGIN sentinel across $PLUGIN_ROOT -->

**What 'working' means on this stack.** This code lives on multiple machines and multiple operating systems — Windows, macOS, Linux. "Working" means working on all of them. Not "compiles on this machine." Not "passes the test the EM ran." Not "the immediate symptom is gone." Working means: a future agent picking this up on a different OS, with a different home directory, with the repos cloned to different paths, can run this code without batch-fixing backslashes or rewriting hardcoded paths.

**The substrate is here to help, not to nag.** The registry-correct way to reference a sibling-repo path is shorter than the wrong way:

- Python: `from claude_machine_local import repos`, then `repos.project_rag / "subdir/file.py"` (pathlib `/` operator joins path segments)
- Shell: `source "${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/bin/claude-machine-local.sh"`, then `echo "$REPO_PROJECT_RAG/subdir/file.py"` (never hardcode `~/.claude/bin/...` — that path moved to settings-home)

If you find yourself about to type a hardcoded Windows drive path or a hardcoded macOS/Linux home-directory path in code (not in a docstring example or test fixture), reach for the helpers above instead. Same character count after the import; works on every machine the code will run on.
