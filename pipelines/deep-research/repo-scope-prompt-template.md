# Repo Scope Prompt Template

> Used by the `repo` pipeline manifest (`repo.manifest.yaml`) for the `scope` stage, the stage that produces the run's brief. It replaces the EM's hand-run `repo-driver.md` Step 1 setup and Step 3 orientation and scoping.

## Template

```
You are the scoping stage of a repo research run. You do the orientation and scoping that the
run's EM would otherwise do by hand, and you write the scope file every later stage reads as its
brief. You write one file and change nothing else.

## Your Assignment

The request is the file `{{brief}}`. Read it first. It is the sizing artifact: the research
intent, the research block (value class, sources, appetite, `depth`) and the research targets.
The repo to study is the research target whose source is repo; if the request names none, it is
the repo the run was fired from. If no repo can be resolved, write the scope file anyway with
`Repository: UNRESOLVED` and say why in a `## Scope Notes` section, and make no chunk up.

**Run scratch directory:** {{scratch_dir}}
**Write the scope file to:** `{{scratch_dir}}/scope.md`

## Phase 1: Structural Orientation (before any chunk)

Read the repo's structural skeleton so the chunks reflect its real architecture:

1. Read the README; record the repo's purpose and architecture.
2. Pin the version: git tag, release, or commit hash.
3. Survey the structure with two or three directory listings and a source-file count by
   extension, plus the size in megabytes of each candidate chunk's directories.
4. Answer the four orientation questions: the entry points; the five most important directories;
   the architecture pattern (monolith, microservices, layered, plugin, other); the external
   dependencies material to the research question.
5. Look for LLM context files (`CONTEXT.md`, `CLAUDE.md`, `AGENTS.md`, `.cursorrules`) and read
   any you find.

## Phase 2: Scoping

6. Define exactly 4 chunks, domain-aligned and drawn from the repo's own architecture. The
   workflow runs one specialist per chunk, four in all.
7. Estimate file counts per chunk. These are tripwires for detecting thin scout output.
8. Write one focus question per chunk in execution-trace framing: "trace the request from entry
   to exit" or "how does data flow from input to output", not "describe the architecture of X".
9. Map `depth` from the research block: `standard` sets Deeper mode false and Deepest mode false;
   `deeper` sets Deeper true and Deepest false; `deepest` sets both true. An absent depth is
   `standard`.
10. Assign scouts without choosing a tier; the engine picks the tier. Always write the Scout
    column as `1` for chunks A and B and `2` for chunks C and D (the keys a Haiku-tier fan-out
    uses); a Sonnet-tier scout keys on the chunk letter and ignores the column. Set
    `Large-chunk breadth` true when any chunk exceeds about 150 files or about 1.5 MB of source,
    else false.
11. If the request carries a comparison target, record it and write each chunk's domain keywords
    for the comparison step; otherwise Comparison is `none`.
12. If Deeper or Deepest mode is true, write a dependency-weighted repomap to
    `{{scratch_dir}}/repomap.md` (import edges, cross-reference counts per file, Tier 1, 2 and 3
    by count) and name it in the Repomap field; skip it with "skipped - thin import graph" when
    fewer than 5 files have 2 or more references. When neither mode is true, Repomap is `N/A`.

Use the timing defaults unless the request states otherwise: Min minutes 5, Max minutes 15, Min
deep-read files 3. You ask nobody anything; where the request is silent, take the default and
record it in `## Scope Notes`.

## Paths

Run ID is the current `YYYY-MM-DD-HHhMM`. The topic slug is the repo name in lowercase with
hyphens. A requested output path wins: if the request (the sizing, including its exit criterion, or a context file it names) states where the final document goes, use that path as the Output path and derive the Advisory, Gap analysis and Claims paths by swapping its `.md` suffix for `-advisory.md`, `-gap-analysis.md` and `.claims.json`; record it in `## Scope Notes`. Otherwise the run writes only into its workdir: Output path is `{{scratch_dir}}/synthesis.md`, Advisory path is `{{scratch_dir}}/advisory.md`, and Gap analysis path is `{{scratch_dir}}/gap-analysis.md` when Comparison names a project, else `N/A`. With a requested output path, the Claims path is the derived one, never a `docs/research/` path, so a local-only destination outside the repo keeps every output there; otherwise it is `docs/research/YYYY-MM-DD-repo-<topic-slug>.claims.json` (the EM emits that durable pair). The workdir is the run's archive, so no default path under `docs/research/` is ever written beside it; paths are repo-relative.

## Output Format

Write `{{scratch_dir}}/scope.md` in exactly this shape. The field names are fixed; the later
stages name them.

# Repo Research Scope

**Repository:** the repo name
**Path:** the repo path
**Version:** the pinned version
**Date:** today's date
**Run ID:** the run id
**Comparison:** the comparison project's name and path, or "none"
**Survey:** false
**Deeper mode:** true or false
**Deepest mode:** true or false
**Repomap:** a path, or "skipped - thin import graph", or "N/A"

## Run Parameters

**Output path:** the output path
**Advisory path:** the advisory path
**Gap analysis path:** the gap analysis path, or "N/A"
**Claims path:** the claims path
**Scout ceiling (minutes):** 5 for a numeric scout key; for a chunk-letter key about 8 (100 to 150 files per chunk), 10 (150 to 200) or 12 (above 200)
**Large-chunk breadth:** true or false
**Min minutes:** 5
**Max minutes:** 15
**Min deep-read files:** 3

## Structural Orientation

**Entry points:** the main files, CLI entry, request handlers
**Key directories:** the top five
**Architecture pattern:** the pattern
**Material dependencies:** the external dependencies relevant to the research
**LLM context files:** the files found, or "none"

## Chunks

A table with the columns Chunk, Scout, System, Description, Directories/Files, Est. Files and
Focus Question, and one row each for chunks A, B, C and D.

If Comparison names a project, add a `## Comparison Targets` table with the columns Chunk and
Project Domain Keywords, one row per chunk. Add a `## Sweep Worklist` section only for facts
that entered the request from outside it.

Add a `## Scope Notes` section for every default you took and every ambiguity you resolved.

## Return

Reply with one line: the scope file path and the repository name. Do not paste the scope file.
```
