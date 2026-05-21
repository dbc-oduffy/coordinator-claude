# Lessons — fixture sample

Synthetic lessons file used by `plugins/coordinator/skills/learn-lessons/tests/fixtures/lesson-triage/run-fixture-test.sh`.
Contains 4 entries spanning ≥3 destination kinds (doctrine-edit, wiki-new, project-structural, strip-local).
DO NOT process this file with the real /lesson-triage skill — it's fixture input.

## **Subagent dispatch billing inheritance** [universal]

Parent on 1M-context tier propagates the billing flag to every Agent dispatch
regardless of model override. Use Haiku 4.5 to bypass the gate for mechanical
work; otherwise drop parent context via /clear or /handoff.

## **Skeletal mesh socket attachment ordering** [ue]

UE: AttachActorToComponent must run after the SkeletalMeshComponent has
finished its initialization tick — calling it from BeginPlay races the
component init and silently fails on first spawn.

## **Build script auto-discovery sweeps stale backups**

Auto-discovery globs in build.sh sweep `*backup*` and `*.bak*` files unless
explicitly excluded. Land an exclude pattern in build.sh to prevent stale
artifacts from corrupting the build.

## **TEXT-ONLY hallucination — disk-first verification** [universal]

A subset of dispatched agents hallucinate a "TEXT ONLY" constraint and dump
deliverables inline as analysis blocks. Already covered in coord/CLAUDE.md
"TEXT ONLY Hallucination" section.
