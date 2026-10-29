<!-- canonical source for project-rag-preamble — edit here, then run bin/verify-snippet-sync project-rag-preamble --fix -->
<!-- consumers: discovered at runtime by bin/verify-snippet-sync project-rag-preamble via grep for BEGIN sentinel across $PLUGIN_ROOT -->

**Code lookup: project-rag first.**

1. First action, when `mcp__project-rag__*` tools are present (they arrive deferred): `ToolSearch("select:mcp__project-rag__project_staleness_check,mcp__project-rag__project_symbol,mcp__project-rag__project_symbol_callers,mcp__project-rag__project_symbol_references,mcp__project-rag__project_symbol_brief,mcp__project-rag__project_referencers,mcp__project-rag__project_semantic_search,mcp__project-rag__project_rag_instructions")`
2. Then `project_staleness_check`; callers `project_symbol_callers`/`_references`; impact `project_referencers`; else `project_rag_instructions`.
Bodies, members, UE engine types: load `project_symbol_source`, `project_engine_*` by name; a `project_symbol` stub is not "corpus can't answer".
**Enumeration is not a lookup.** "What exists?" means a target list, a file set, a coverage count, or "is X covered?". Answer it by walking the filesystem (Glob, a disk enumerator), never with project-rag or any other index, because an index reports only what it already holds. Use project-rag to understand what the walk found, never to decide what exists.
If a project-rag call errors or its tools are absent (daemon down), fall back to Grep/Read and carry on.
Friction: memo `project-rag-em` / `gh issue create -R dbc-oduffy/project-rag`.
