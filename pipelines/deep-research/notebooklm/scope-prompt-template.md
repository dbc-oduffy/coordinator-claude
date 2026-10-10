# Scope Prompt Template

> The scope stage's prompt in `notebooklm.manifest.yaml`. It turns the sizing into `strategy.md`, which every later stage reads as `{{brief}}`. The only placeholders are the closed double-brace set.

## Template

```
You are the NotebookLM Research Scope stage. Turn the sizing into the run's strategy file.

## Inputs

- **Sizing:** {{brief}} — carries the research topic, the intent, the `research` block, and `research.targets`.
- **PM-supplied URLs:** the `research.targets` entries whose `source` is `notebooklm`. Treat each as a pre-selected source for a notebook (YouTube, podcast, article, Drive document).
- **Best practices:** read `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/notebooklm/notebooklm-best-practices.md` first.
- **Protocol:** read `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/notebooklm/team-protocol.md` § Data Contract, § Rate Limit Budgeting and § Timing for the strategy.md shape, worker counts per tier, and ceilings.

## Output

**Write to:** {{scratch_dir}}/strategy.md

Design the notebook topology, questions, source strategy and worker count directly. NLM tier (free, plus, ultra) defaults to `free` unless the brief or sizing names one; never stop to ask. A field the brief sets (`tier_assumption`, source guidance, notebook count) is kept as written. Where your table disagrees, keep the brief's value and add one advisory line under `## Scope notes`, e.g. `brief says tier ultra; table says plus; kept ultra`. Copy the brief's source guidance (paste-as-text sources, prior-run `sources.md` seeds) verbatim into each affected notebook's source strategy. Time-box scoping to 2-3 minutes: pick the simpler topology if still deliberating.

The frontmatter carries the team-protocol Data Contract fields (`worker_count`, `total_expected_queries`, `tier_assumption`) plus:

- `research_topic`, `topic_slug`
- `output_path`: `docs/research/YYYY-MM-DD-{topic_slug}-nlm.md`; `output_path_base`: it without `.md`; `advisory_path`: `output_path` with `.md` replaced by `-advisory.md`
- `cleanup_notebooks`: `true` or `false` (default `false`)
- `scout_ceiling_minutes`: default 5

The body carries one `## Notebook {letter}` section per notebook, letters A, B, C as many as `worker_count`, each with Focus, Custom instructions, Questions, Source strategy (`scout-provided` or `research_start`), Search guidance for scout, and Estimated ceiling. Notebooks fed by PM-supplied URLs list those URLs in the section and use `scout-provided`.

## Return

Reply with one line: the strategy path, `worker_count`, and the notebook letters as a comma-separated list.
```
