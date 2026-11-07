<!-- canonical source for project-rag-preamble — edit here, then run bin/verify-snippet-sync project-rag-preamble --fix -->
<!-- consumers: discovered at runtime by bin/verify-snippet-sync project-rag-preamble via grep for BEGIN sentinel across $PLUGIN_ROOT -->

**Code lookup: project-rag first.** Engine facts and symbol questions (definitions, callers, members, UE types) go to the project-rag tools before Grep/Glob; Grep is for literal text.

First action, when `mcp__project-rag__*` tools are present (they arrive deferred): `ToolSearch("select:mcp__project-rag__project_staleness_check,mcp__project-rag__project_symbol,mcp__project-rag__project_symbol_callers,mcp__project-rag__project_symbol_references,mcp__project-rag__project_symbol_brief,mcp__project-rag__project_referencers,mcp__project-rag__project_semantic_search,mcp__project-rag__project_rag_instructions")`
Then `project_staleness_check`; callers `project_symbol_callers`/`_references`; impact `project_referencers`; else `project_rag_instructions`.
Bodies, members, UE engine types: load `project_symbol_source`, `project_engine_*` by name; a `project_symbol` stub is not "corpus can't answer".
**Enumeration is not a lookup.** "What exists?" (target list, file set, coverage count, "is X covered?") is answered by walking the filesystem, never by an index; use project-rag to understand what the walk found.
If a project-rag call errors, retry it once; retry a substring timeout by exact name. MetaHuman lookups need `source=unreal_5.8_plugin`: a `source=engine` miss is a wrong-source error, so retry with the right source. A UE or MetaHuman fact you assert whose retry fails ABORTS per the global rules (exact call and output; pinned-sha engine source is the only fallback, never memory), and unaudited code is reported "unaudited". An executor working from a plan's cited facts needs no fresh lookup; a new fact it needs and cannot get stops that row only. Non-UE facts, or no project-rag installed: use Grep/Read and carry on.
**Every grep is scoped**: `git grep` or the Grep tool on named paths in your own repo; never search recursively from a repo root, `..`, a sibling checkout or a drive (`A-RECURSIVE-GREP-FROM-A-REPO-ROOT-STALLS-THE-BOX`). A search constraint in your brief or `em_context` binds you, even when project-rag is down.
Friction: memo `project-rag-em` / `gh issue create -R dbc-oduffy/project-rag`.
