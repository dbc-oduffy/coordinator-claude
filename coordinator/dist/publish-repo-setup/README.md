# dist/publish-repo-setup — Source-of-Truth for Publish-Repo Setup Scripts

This directory is the **source-of-truth** for the three setup scripts that live at
`setup/` in the coordinator-claude publish repo (`X:/coordinator-claude/`).

Edits to these files belong here — in Claude Central, where the plan/review/lessons
feedback loop applies. To mirror changes outward to the publish repo, run:

```bash
bash setup/publish.sh coordinator-claude-publish-repo-setup
```

The percolate target `coordinator-claude-publish-repo-setup` is registered in
`setup/publish-targets.sh` and uses the `sync_flat_mirror` mode, which rsyncs
this directory's contents verbatim into the publish repo's `setup/` directory
(then runs a post-rsync depersonalize hook before committing).

## Files

| File | Publish-repo destination |
|------|--------------------------|
| `install.sh` | `setup/install.sh` |
| `dev-sync.sh` | `setup/dev-sync.sh` |
| `name-personas.sh` | `setup/name-personas.sh` |

## Doctrine

Direct edits to `X:/coordinator-claude/setup/install.sh` (or the other two files)
bypass the coordinator review pipeline and create orphaned content. If a hotfix
was made directly in the publish repo, back-percolate it here immediately, then
re-run `publish.sh coordinator-claude-publish-repo-setup` to bring the repos back
into sync.

For the full flat-mirror authoring doctrine and recovery procedure, see:
`plugins/coordinator/docs/wiki/plugin-extraction-and-distribution.md`
— specifically the **Auxiliary Sync** and **Publish-Repo Content Authoring** sections.
