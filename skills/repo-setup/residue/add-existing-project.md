---
segment_id: add-existing-project
class: protected
order: 2
situation: add-existing-project
---
<!-- Purpose: `add-existing-project` lane judgment note. Values: `lanes/add-existing-project.yaml`. -->

# repo-setup — add-existing-project lane

`p15.ratification-ask` resolves `ratify`: Phase 1.5's name, type and workstreams are trusted and
win over `detected_type`. `p3f.untrack-scratch-offer` never auto-runs `git rm --cached`; it declines
and reports `Needs Attention`. `p3f5.custom-hook-skip` DEFERS (skip + `Needs Attention`) when a
custom auto-push hook exists. The UNATTENDED-HALT SET applies unchanged (`lanes/CONTRACT.md`).
