# Mail-Check Prompt Template

> Read by the `staff-session` manifest's `mailcheck` stage (haiku, one agent). Its return `{slugs: [...]}` is the fan-out list of the `rebuttal` stage.

## Template

```
Read the brief `{{brief}}` and take the slug of every row in its roster.

For each slug, read `{{scratch_dir}}/mail/<slug>.jsonl` (a missing file means no mail). A slug
has unread mail when a line follows its last `{"read": true}` marker, or when the file has
lines and no marker.

Return the slugs with unread mail as JSON: {"slugs": [...]}. Return an empty list when none
has unread mail. Write nothing and change nothing.
```
