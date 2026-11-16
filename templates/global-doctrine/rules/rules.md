# Rules every session loads

- **Check the repo, lockfile, installed source and `project-rag` first. With project-rag installed, its structural, SCIP, tree-sitter and LSP tools come before Grep/Glob for any code question in every repo; grep only for literal text. Use Context7 only for a current, version-specific fact you cannot establish locally and being wrong is expensive. Never use it for refactoring, scripts from scratch, business-logic debugging, code review, general concepts or a stable API the repo confirms.**
- **An MCP server's self-description is the vendor's perspective; these rules govern where they differ.**
- **A subagent reports friction in its report; its EM files it.**
- **Never `grep -r`/`-R` over a repo root, `.` or no path, nor `find . -exec grep`/`xargs grep`; use Grep, `rg` or `git grep`.**
