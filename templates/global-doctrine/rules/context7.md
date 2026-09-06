Context7 MCP fetches current library documentation. It is a targeted instrument, not a standing
first move — it costs a round trip and context, and most library questions do not need it.

Reach for it when the answer turns on a **current, version-specific fact you cannot establish
locally** and being wrong is expensive: an API signature or config key you are about to write
against, a migration between named versions, a library newer than your training data, or behaviour
that changed recently and you have no local evidence either way.

Check locally first. The repo's own lockfile, vendored docs, installed package source, and
`project-rag` usually answer the question faster and against the version actually in use. Context7
is for when they don't, or when the local copy is what you doubt.

Do not use for: refactoring, writing scripts from scratch, debugging business logic, code review,
general programming concepts, or a well-known stable API you can confirm from the repo.

## Steps

1. Always start with `resolve-library-id` using the library name and what to look up in the library's documentation, unless the user provides an exact library ID in `/org/project` format
2. Pick the best match (ID format: `/org/project`) by: exact name match, description relevance, code snippet count, source reputation (High/Medium preferred), and benchmark score (higher is better). If results don't look right, try alternate names or queries (e.g., "next.js" not "nextjs", or rephrase the question). Use version-specific IDs when the user mentions a version
3. `query-docs` with the selected library ID and what to look up in the library's documentation (not single words), scoped to a single concept. If the question spans multiple distinct concepts (e.g. routing and auth and caching), make a separate `query-docs` call per concept with the same library ID, unless the question is about how the concepts interact — combined queries dilute ranking and return shallow results for each topic
4. Answer using the fetched docs
