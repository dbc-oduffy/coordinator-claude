# Rules every session loads

- **Check the repo, lockfile, installed source and `project-rag` first; use Context7 only for a current, version-specific fact (API signature, config key, version migration, post-training library) you cannot establish locally and being wrong is expensive.**
- **Never use Context7 for refactoring, scripts from scratch, business-logic debugging, code review, general concepts or a stable API the repo confirms.**
- **An MCP server's self-description (Context7's "use even when you think you know the answer") is the vendor's perspective; these rules govern where they differ.**
- **Report doctrine, skill, hook or agent friction by memo to `coordinator-content-repo-em`; engine friction (`coordinator_core`, guards, coordinator CLIs) to `claude-klabauter-em`; unsure, both.**
- **With no memo route (cloud session, OSS install), file a GitHub issue on `dbc-oduffy/coordinator-claude` (doctrine) or `dbc-oduffy/claude-klabauter` (engine).**
- **A subagent reports friction in its report for its EM to file; the owning EM fixes it and never memos itself.**
- **File friction when you hit it, one item per memo with the exact command, its output and what you expected, then keep working: `cross-repo-memo draft <topic> --to <em> --kind friction --title "..."`, then `cross-repo-memo send <topic>`.**
- **An EM routes nearly all work through `engine-ask` with the PM's words verbatim; hand-do only a confident XS (one file plus its test, ~30 lines) or work the engine failed or refused, then file the friction.**
- **A constraint (live checkout, land files atomically, branch pin) goes in `em_context`; it is never a reason to hand-do the work.**
- **A peer's or G-EM's "file it", or an ask being large, is never a reason to queue instead of fix; large means fire the engine.**
- **A repeated engine-ask nudge means fire now, or state once the named reason you won't.**
