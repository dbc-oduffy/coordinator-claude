---
name: dispatch
description: Manually dispatch a UE editor operation to a domain agent
argument-hint: "<domain> <task description>"
allowed-tools: ["Agent"]
---

Dispatch a UE editor control task to the appropriate domain agent. The user provides either:
1. An explicit domain + task: `/dispatch world build a desert landscape`
2. Just a task (auto-route): `/dispatch set up combat with 3 enemy types`

## Domain Keywords

| Keyword | Agent | Domain |
|---------|-------|--------|
| `world` | ue-world-builder | Landscape, lighting, geometry, levels, volumes, splines, navigation |
| `asset` | ue-asset-author | Blueprints, materials, textures, skeletons, sequences, widgets |
| `gameplay` | ue-gameplay-engineer | Actors, characters, combat, AI, inventory, interactions, GAS, input |
| `infra` | ue-infra-engineer | Performance, tests, validation, networking, game framework, audio |

## Routing Rules

1. If the user specifies a domain keyword, dispatch to that agent directly.
2. If no keyword: infer the correct agent from the task description.
   - **If the task is precise and single-domain**, route to the matching domain agent.
   - **If the task crosses 2+ domains** or is underspecified, advise the EM to decompose and dispatch domain agents sequentially with verification between steps.

## Examples

- `/dispatch world dramatic sunset lighting setup` → ue-world-builder
- `/dispatch asset create a door blueprint with open/close` → ue-asset-author
- `/dispatch gameplay spawn enemies with patrol AI` → ue-gameplay-engineer
- `/dispatch infra run all automation tests` → ue-infra-engineer
- `/dispatch spawn 3 PointLights at (0,0,300), (500,0,300), (1000,0,300)` → ue-world-builder (precise)
- `/dispatch build arena with enemies and lighting` → Multi-domain: decompose into world-builder (arena + lighting) then gameplay-engineer (enemies)
