# Plugin Identity and Health Sentinels

> Decay-discipline doctrine for plugin-local data dirs (`~/.claude/plugins/<plugin>/data/`), live MCP introspection, and the writer-boundary that keeps their decay models separate.

## The underlying principle: decay discipline

Each plugin-orientation artifact has a decay model. The decay model determines what staleness *means* for that artifact, and crossing decay models inverts that meaning destructively. The three-way split below isn't a tool-boundary convention — it's the operational shape of two decay regimes plus a no-side-effects bridge:

- **Persistent artifacts get receipt semantics: stale = signal.** A receipt is durable evidence that *something happened at a point in time*. A 30-hour-old receipt is information ("no one has checked since yesterday — surface that"), not data. Receipts on disk, written by the actor whose action they witness.
- **Live artifacts get truth semantics: current = answer.** Identity ("what is this bound to right now") has no useful stale form. The answer is queried from the running process that authoritatively holds it. Never cached, never persisted, never written.
- **The scanner is the no-side-effects bridge between them.** Scanners read receipts and surface verdicts; they do not write, do not query MCP, do not synthesize state. The whole point of a scanner is that it carries no decay model of its own.

Crossing any of these boundaries inverts the decay model in the failure-mode sense:

- Persisting live state turns "stale = stale data" into "stale = active lie" (a `whoami.json` written before a consumer-switch is now wrong, not just old).
- Querying live for receipts turns "no one has checked" into "looks fine right now" (a fresh MCP response overwrites the receipt-staleness signal that was the whole point).
- Letting a scanner write turns the bridge into a third writer with its own implicit decay, dissolving the discipline that justified separating the surfaces in the first place.

## How the principle lands as tool layout

| Surface              | Path / Tool                                     | Writer                | Trigger                  | Decay regime                | Contract                              |
| -------------------- | ----------------------------------------------- | --------------------- | ------------------------ | --------------------------- | ------------------------------------- |
| **Health receipt**   | `~/.claude/plugins/<plugin>/data/doctor-last-run.json` | Doctor skill only     | Doctor invocation        | Stale = signal (nudge)      | Durable evidence of a transient check |
| **Health scanner**   | `scan-addon-health.sh` (and future siblings)    | n/a (reader)          | `/session-start`, `/workday-start` | None — no-side-effects | Reduces verdicts to RED/AMBER/GREEN   |
| **Identity (live)**  | `project_whoami` MCP tool (and per-plugin equivalents) | n/a (live response) | Caller invocation        | None — current = answer     | Status panel for the running process  |

The receipt surface and the identity surface are deliberately **not** merged into a single file. They don't share a decay model, so they can't share a contract.

## Scope of this doctrine: runtime-queryable state only

<!-- Narrowing amendment — 2026-05-19. Source: docs/plans/2026-05-19-coordinator-installer-redesign.md (Zolí review Conflict #1, direction: both). Framing: narrowing, not overturning — the three-EM consensus on runtime-identity is preserved. -->

The decay-discipline described in this wiki applies to **runtime-queryable plugin state** — MCP binding, daemon PID, consumer-project path, current binding state. These are the artifacts whose live source makes on-disk persistence an active lie after a state change.

**Operator-set configuration is NOT in scope.** Operator display name, preferred persona names, machine label, and similar stable-configuration fields are categorically different from runtime-queryable identity:

- They have no live source that would make a persisted copy stale mid-session.
- They are set once by the operator's explicit intent, not inferred from runtime state.
- They are conceptually closer to a dotfile setting (e.g. `~/.gitconfig`) than to a plugin-runtime identity artifact.
- The "stale = active lie" failure mode does not apply — there is no process that can silently overwrite a correct operator name with a wrong one on restart.

Persisting operator-set configuration (e.g. to `~/.claude/coordinator-identity.yaml`) is appropriate and does not violate this doctrine. The wiki's decay-discipline governs what *plugins produce at runtime*, not what *operators configure at setup time*.

For machine-local operator-set values (sibling-repo roots, Unreal install root, CUDA toolkit, vendor SDKs) — values stable across sessions, set by operator intent, consumed by any tool or language — see `machine-local-registry.md`. The Scope amendment above and the machine-local registry are companion doctrines: this wiki defines what operator-set configuration is and why it sits outside decay-discipline; machine-local-registry defines where it lives and how it is queried.

---

## Why no `whoami.json`

The shape "second on-disk sentinel for **plugin runtime identity**" was proposed 2026-05-19 and deferred by mutual consent of the holodeck EM, project-rag host EM, and project-rag-ue-addon EM. Memos at `~/.claude/cross-repo/archive/2026-05-19-project-rag-*-whoami-sentinel*.md` (grandfathered pre-cutoff memos). The principle:

**Identity is runtime state with a live source. Don't persist what you can query.**

(This principle applies to runtime-queryable state. Operator-set configuration is handled separately — see scope note above.)

Three problems a `whoami.json` would introduce:

1. **Ephemeral data goes stale fast.** `consumer_project`, daemon PID, editor PID, current binding all change mid-session. A 20-minute-old `whoami.json` actively lies after a consumer-switch, and a cross-plugin scanner reading two stale sentinels flags false mismatches.
2. **The writer-set has no good answer.** Either the MCP server writes on startup (disk-as-fan-out for what's already queryable) or the slash-command side probes and caches (guaranteed staleness). The writer-set fuzziness isn't an implementation detail to resolve — it's the proposal telling us identity doesn't belong on disk.
3. **The compelling use case wants live cross-MCP query, not stale-disk reconciliation.** The cross-plugin mismatch detector ("project-rag's `consumer_project` vs holodeck-control's `consumer_project` should agree") only works correctly if both sides are read live. The right primitive when that incident surfaces is a `scan-addon-identity` action that calls each plugin's introspection MCP tool live and diffs — no on-disk sentinel.

## The writer-boundary rule

**MCP servers do not write plugin-local data dirs.** A plugin's `~/.claude/plugins/<plugin>/data/` reflects last-skill-action, not last-MCP-tick. Crossing that boundary would invert the decay model — a freshly-restarted MCP would silently overwrite a doctor RED with a green-on-paper "I just started up", exactly the false-confidence failure mode the receipt model was designed to prevent.

Concretely:

- **Doctor skill** writes `doctor-last-run.json` (and any future receipt-shaped sentinels).
- **MCP server** writes its own data dir (e.g., project-rag's `<ProjectRoot>/Saved/ProjectRag/`, the embed sidecar log) and answers introspection tools at runtime. It does **not** touch `~/.claude/plugins/<plugin>/data/`.
- **Scanner scripts** are readers, never writers.

<!-- Amended 2026-05-19 by 2026-05-19-cross-plugin-whoami-contract.md: project_whoami reframed from canonical to specific implementation. Decay-discipline content preserved. -->

## Identity surfacing via MCP — `project_whoami` as project-rag's implementation of the [cross-plugin whoami contract](cross-plugin-whoami-contract.md)

`project_whoami` is project-rag's MCP introspection tool and its conformant implementation of the coordinator-owned cross-plugin whoami contract. For the envelope schema, see [cross-plugin-whoami-contract.md](cross-plugin-whoami-contract.md). The current `project_whoami` response will be re-shaped to conform; existing fields (`source`, `project_kind`, etc.) map into the contract's `binding.target`, top-level common fields, and `extras["project_rag"]` slot per the host EM's v9 envelope work.

Resolution is ContextVar (`current_project_context()`) → `SourceRegistry.resolve_by_path(project_root)`. **Always live, no caching, no staleness window.**

Other plugins exposing identity implement their own coordinator-conformant whoami tool — live tool, no disk cache, response synthesized from authoritative runtime state, conforming to the shared envelope schema.

### Scanner-design wrinkle: `source: null` is "unbound", not "mismatch"

`project_whoami` returns `source: None` when the caller's `project_root` doesn't match any registered SourceEntry — engine-only mode, or a project that finished setup but isn't indexed. By-design contract per the synthesis-host research ("be-configured-because-setup-and-doctor-said-so-then-whoami-works", not "fail-loud-when-unconfigured").

**Any future cross-plugin scanner reading whoami-shaped outputs must treat `null` as "consumer not yet bound to a host source", not as a mismatch signal.** Mismatch comparisons are only valid when both compared values are non-null.

## Extending the surface — preferred shapes

If a future incident motivates surfacing additional state, the path-of-least-resistance ranks:

1. **Extend the live introspection tool.** For identity-shaped data with no decay model (daemon PID, sidecar revision): if the new field is relevant to ≥2 MCP plugins, propose it as a common field in the coordinator-defined whoami envelope ([cross-plugin-whoami-contract.md](cross-plugin-whoami-contract.md)); if it's a single-plugin concern, add it to that plugin's `extras` slot in the contract's envelope. Single writer (MCP), live response, no new infra.
2. **Contribute via `project_rag_register_health_field` hookimpl.** For state-shaped data with natural decay ("last index timestamp for band X"), addons extend the health envelope through the existing chain. Single source of truth, same decay model as the rest of the envelope.
3. **Add a doctor probe.** For yes/no health questions with a remediation step (corpus schema currentness, plugin Binaries freshness), extend the doctor skill so the verdict flows through the existing receipt sentinel.
4. **New disk sentinel.** Only when none of (1)–(3) fit — e.g., the writer must be a skill, the decay model is distinct, the verdict-reduction has structural value. The doctor sentinel is the existence proof; the bar for a second one is high.

   The **setup-state receipt** (`~/.claude/coordinator-setup-state.yaml`) is the justified second disk sentinel: its writer must be a skill (`/setup` + the EM-facilitated orientation, no MCP/doctor owns it), its decay model is distinct (a milestone set once and never re-checked for currency — unlike the doctor receipt's "stale = re-run" nudge), and its yes/no verdict (`setup_concluded_at` present?) is a cross-repo chaining gate sibling repos consume. → [`coordinator-setup-state-receipt.md`](coordinator-setup-state-receipt.md).

## Known follow-up items (not blocking, not yet scoped)

Surfaced during the 2026-05-19 consult and parked for the next consumer-driven trigger:

1. **`corpus_schema_current` doctor probe** (host-owned). Runs `MIN_SUPPORTED_SCHEMA <= graph.schema_version <= SCHEMA_VERSION`. Today no consumer plugin has a clean way to ask "is the corpus I'm about to query schema-current?" — they'd have to shell out to `/project-rag:show-index`, read `graph.db` schema_meta directly, or read `corpus-manifest.json`, all of which couple them to internal layout. A doctor probe gives them a stable contract.
2. **`addon_sources_available[].corpus_version` field** (addon-owned). Addons already know their corpus version (it's in their manifest); surfacing it through the existing `project_rag_register_health_field` hookimpl is structurally clean and lets consumers compare across plugins.

Both are receipt/health-shaped, not identity-shaped. Both unblock when a concrete consumer surfaces the need.

## Cross-references

- `~/.claude/cross-repo/archive/2026-05-19-project-rag-host-em-whoami-sentinel.md` — original consult to host EM (grandfathered pre-cutoff memo)
- `~/.claude/cross-repo/archive/2026-05-19-project-rag-host-em-whoami-sentinel.reply.md` — host EM reply (canonical statement of the writer-boundary rule)
- `~/.claude/cross-repo/archive/2026-05-19-project-rag-addon-em-whoami-sentinel.cover.md` — addon EM consult after host reply
- `~/.claude/cross-repo/archive/2026-05-19-project-rag-em-whoami-sentinel.md` — initial addon EM consult

## Decision shape (for the next person to find this)

**Receipt-on-disk, identity-via-MCP, deliberate non-merger.** Revisit when a concrete incident surfaces that the receipt-only sentinel + live MCP introspection genuinely could not have caught.

## Provenance

The doctrine emerged from a three-EM consult (holodeck EM, project-rag host EM, project-rag-ue-addon EM) on 2026-05-19. Authorship credit, for future readers tracing the framing:

- **Holodeck EM** identified the separable-shape question (receipt vs status panel) and the "stale = signal" property of the receipt sentinel that would dilute under overload.
- **Project-rag host EM** found the sharp articulation of the writer-boundary ("doctor writes, scanner reads, MCP answers live") and the inversion failure mode that makes it load-bearing — a fresh MCP restart silently overwriting a doctor RED with a green-on-paper "I just started up". This argument is what moved the decision from "defer until incident" to "defer on principle".
- **Coordinator DoE** framed the underlying decay-discipline principle that ties the three legs together (persistent = receipt semantics, live = truth semantics, scanner = no-side-effects bridge) and reframed the deferral rationale around live-source-availability rather than incident-absence.

Treating this as decided. Don't re-litigate without naming an incident the existing three-surface layout would have failed to catch.
