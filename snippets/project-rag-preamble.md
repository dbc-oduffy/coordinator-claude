<!-- canonical source for project-rag-preamble — edit here, then run bin/verify-snippet-sync project-rag-preamble --fix -->
<!-- consumers: discovered at runtime by bin/verify-snippet-sync project-rag-preamble via grep for BEGIN sentinel across $PLUGIN_ROOT -->

**Code lookup: project-rag first.** Whenever project-rag's CLI, MCP tools or registry entry is present it is the primary path: engine facts and symbol questions (definitions, callers, members) go to its tools before Grep/Glob; Grep is for literal text. Grep/Read stays available (never a prohibition); a project-rag shortfall is reported to project-rag as a gap, not silently routed around.

First action, when `mcp__project-rag__*` tools are present (they arrive deferred): `ToolSearch("select:mcp__project-rag__project_staleness_check,mcp__project-rag__project_symbol_brief,mcp__project-rag__project_lsp_definition,mcp__project-rag__project_lsp_hover,mcp__project-rag__project_code_outline,mcp__project-rag__project_symbol,mcp__project-rag__project_rag_instructions")`
Then `project_staleness_check(repo=<repos.* key>)`.
Pass `repo=<repos.* key>` on every project-rag call; its key is a `repos.` row of `machine-local keys`. An answer from the wrong repo is a miss.
Shape -> tool: symbol `project_symbol_brief(symbol_name=X, lsp=true)` first; type/location `project_lsp_definition`/`project_lsp_hover(file=, line=, name=)`; a file's symbols `project_code_outline(file=)`; exact-name identity `project_symbol(symbol_name=X)`; else `project_rag_instructions`.
Bodies and members: load `project_symbol_source` by name; a `project_symbol` stub is not "corpus can't answer".
**Enumeration is not a lookup.** "What exists?" (target list, file set, coverage count, "is X covered?") is answered by walking the filesystem, never by an index; use project-rag to understand what the walk found.
If a project-rag call errors, retry it once; retry a substring timeout by exact name.
Non-UE block: a non-UE miss after the retry is not an ABORT; use Grep/Read scoped to named paths, carry on, and report the fallback to project-rag as a gap. No project-rag CLI, MCP or registry entry at all: Grep/Read.
Executors only: an executor working from a plan's cited facts needs no fresh lookup; a new fact it needs and cannot get stops that row only.
**Every grep is scoped**: `git grep` or the Grep tool on named paths in your own repo; never search recursively from a repo root, `..`, a sibling checkout or a drive (`A-RECURSIVE-GREP-FROM-A-REPO-ROOT-STALLS-THE-BOX`). A search constraint in your brief or `em_context` binds you, even when project-rag is down.
Friction: memo `project-rag-em` / `gh issue create -R dbc-oduffy/project-rag`.
