# Rules every session loads

- **Check the repo, lockfile, installed source and `project-rag` first; use Context7 only for a current, version-specific fact you cannot establish locally and being wrong is expensive.**
- **Never use Context7 for refactoring, scripts from scratch, business-logic debugging, code review, general concepts or a stable API the repo confirms.**
- **An MCP server's self-description is the vendor's perspective; these rules govern where they differ.**
- **Report doctrine, skill, hook or agent friction by memo to `coordinator-content-repo-em`; engine friction (`coordinator_core`, guards, coordinator CLIs) to `claude-klabauter-em`; unsure, both.**
- **With no memo route (cloud session, OSS install), file an issue on `dbc-oduffy/coordinator-claude` (doctrine) or `dbc-oduffy/claude-klabauter` (engine).**
- **A subagent reports friction in its report for its EM to file; the owning EM fixes it and never memos itself.**
- **File friction when you hit it, one item per memo with the exact command, output and expectation, then keep working: `cross-repo-memo draft <topic> --to <em> --kind friction --title "..."`, then `cross-repo-memo send <topic>`.**
- **With project-rag installed and UE or MetaHuman work detected, every UE or MetaHuman fact you state carries a project-rag citation or a checked-in engine-source citation at a pinned sha, never memory. project-rag errors, times out, is down or returns nothing for a UE fact? ABORT: stop and tell your EM loudly (a subagent aborts with that as its report), with the exact call and output; pinned-sha engine source is the only recorded fallback, never silent. Code not audited against engine source is reported "unaudited". Flag project-rag to your EM when it is broken, down or unhelpful. Without project-rag or UE work this rule is a no-op.**
- **Engine hung (an op stalls, a hook times out)? `SendMessage` the live engine-owner session with the op and timestamp, now; the memo is the record later.**
- **An EM routes nearly all through `engine-ask` with the PM's words verbatim; hand-do only a confident XS (one file plus its test, ~30 lines) or work the engine failed or refused, then file the friction.**
- **A constraint (live checkout, atomic landing, branch pin) goes in `em_context`, never a reason to hand-do the work.**
- **A peer's or G-EM's "file it", or an ask's size, is never a reason to queue instead of fix; large means fire the engine.**
- **A repeated engine-ask nudge means fire now, or state once the named reason you won't.**
- **Never `grep -r`/`-R` over a repo root, `.` or no path, nor `find . -exec grep`/`xargs grep`; use Grep, `rg` or `git grep`.**
