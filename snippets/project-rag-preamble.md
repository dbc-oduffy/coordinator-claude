<!-- canonical source for project-rag-preamble — edit here, then run bin/verify-snippet-sync project-rag-preamble --fix -->
<!-- consumers: discovered at runtime by bin/verify-snippet-sync project-rag-preamble via grep for BEGIN sentinel across $PLUGIN_ROOT -->

**Code lookups: project-rag before grep** once `project_staleness_check` answers for your repo. SCIP may lag; it still beats grep.
`ToolSearch("select:mcp__project-rag__project_staleness_check,mcp__project-rag__project_file,mcp__project-rag__project_symbol,mcp__project-rag__project_symbol_callers,mcp__project-rag__project_symbol_references,mcp__project-rag__project_symbol_brief,mcp__project-rag__project_referencers,mcp__project-rag__project_semantic_search,mcp__project-rag__project_rag_instructions")`
Definition `project_symbol`; callers/usages/summary `project_symbol_callers`/`_references`/`_brief`; blast radius `project_referencers`; docs `project_semantic_search`; else `project_rag_instructions`.
