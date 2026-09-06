---
title: Step Zero NDJSON Emitter Contract
status: active
kind: doctrine-wiki
created: 2026-06-22
spec-backlink: docs/plans/2026-06-22-step-zero-emitter-contract-lib.md
---

# Step Zero NDJSON Emitter Contract

> Canonical spec for the NDJSON shape emitted by install Step Zero probes. Coordinator, example-game-repo, and example-cockpit-repo each keep their own emitter implementation; this spec and the conformance fixture (`tests/fixtures/step-zero-conformance.json`) are the shared artifact every implementation is measured against.

## Purpose

The Step Zero probe surface emits one compact JSON line per probe — a single-emitter, single-consumer NDJSON stream. The contract below is **ratified and stable**. Each sibling repo that ships probes emits against this same shape; drift from it is caught by running the conformance fixture against the repo's own emitter before shipping.

The contract was ratified via `cross-repo/inbox/2026-06-22-env-stepzero-convergence-reply.md`. The reference implementation (ported from the original bash) lives at claude-klabauter `coordinator_core/install/step_zero_emit.py`. The **fixture bytes** (`tests/fixtures/step-zero-conformance.json`) are the single normative authority — non-bash consumers conform against the fixture, not against bash `printf` formatting quirks.

---

## Wire Format

- One JSON object per probe, one line per probe.
- Lines are newline-terminated (`\n` LF, not CRLF).
- No commas or wrapper object between lines — plain NDJSON, not a JSON array.
- String values are escaped per the Escape Contract below. No `jq` dependency — the emitter is handrolled to be safe at Step Zero before any toolchain is confirmed present.

### Example output (two probes)

```
{"name":"probe_python","status":"pass","severity":"hard","detail":"python 3.11.8 found at /usr/bin/python3","remediation":""}
{"name":"probe_git","status":"fail","severity":"hard","detail":"git not found on PATH","remediation":"Install git and ensure it is on PATH."}
```

---

## The Five Keys

Every probe line contains exactly these five string-valued keys, in this order:

| Key | Type | Meaning |
|---|---|---|
| `name` | string | Stable probe identifier. Consumers key on this to locate a probe's result. No spaces; snake_case convention. |
| `status` | string | Verdict for this probe. One of the four values in the `status` enum below. |
| `severity` | string | Gate weight for this probe. One of the three values in the `severity` enum below. |
| `detail` | string | Human-readable description of what was found or why the probe concluded what it did. May be empty. May contain multiline content from external tools (e.g. git stderr) — it is escaped per the Escape Contract. |
| `remediation` | string | Human-readable instruction for how to clear the condition. Empty for `pass`. Non-empty for `fail` and `warn`. For `inconclusive`, MAY be empty or MAY carry a recovery action (e.g. "ensure network connectivity and retry", "install git, then configure auth") — the probe decides based on whether a concrete next step exists. (The bash reference's `clone_auth` inconclusive branches ship non-empty remediation; the fixture's inconclusive cases reflect this.) |

No additional keys appear in the base contract. Future additive optional keys bump the minor contract version.

---

## `status` Enum

The `status` field carries the probe's verdict — what it observed.

| Value | Meaning |
|---|---|
| `pass` | The probe ran successfully and the checked condition is satisfied. |
| `fail` | The probe ran successfully and the checked condition is NOT satisfied. Expect a non-empty `remediation`. |
| `warn` | The probe ran successfully; the condition is marginal or advisory. The `severity` field (not this field) determines whether the gate holds on `warn`. |
| `inconclusive` | The probe genuinely could not determine the answer — the checked tool was absent, the network was offline, the substrate was unreachable. **Never a false pass or false fail.** |

**Vocabulary rule:** use exactly `inconclusive`. Never `skipped`, `unknown`, `n/a`, or any synonym. Synonym drift in consumer parsers silently breaks the `inconclusive` case. See `docs/wiki/doctor-probe-design.md` § `inconclusive` Is a First-Class Probe Status for the rationale.

---

## `severity` Enum

<!-- ENV-PREREQ-PROBE-taxonomy: hard | semi-hard | advisory (this enum) -->
<!-- DISTINCT from manifest-dep taxonomy: hard | soft | optional (agent-install-contract.md §Severity semantics) -->
<!-- Do not conflate the two taxonomies — they are orthogonal contracts for different surfaces. -->

The `severity` field carries the probe's gate weight — how a non-`pass` verdict affects the install gate decision.

| Value | Meaning |
|---|---|
| `hard` | A `fail` or `warn` on a hard probe is a gate-stop. The install or step cannot safely proceed. No operator escape path. |
| `semi-hard` | A `fail` or `warn` blocks the preflight exit like `hard`, but is escapable via a probe-specific override flag (operator consciously proceeds). Use only for prerequisites near-universal but with a legitimate alternative the probe can't always detect. Example: `clone_auth` — git auth is nearly always required, but an operator with a local mirror may bypass it knowingly. |
| `advisory` | A `fail` or `warn` on an advisory probe is surfaced to the operator but does not stop the gate. |

**Verdict-field orthogonality:** `status` (the verdict — what did we observe?) and `severity` (the gate weight — how much does it matter?) are **independent, non-multiplexed axes**. A `warn` can be `hard`, `semi-hard`, or `advisory`. A `fail` can be `advisory`. Do not collapse them into one field; a field that means "WARN-but-hard" or "FAIL-but-advisory" is uninterpretable downstream (same antipattern as `docs/wiki/doctor-probe-design.md` § Verdict Fields Must Not Multiplex Soft Pressure With Real Degradation).

---

## Escape Contract

String values are escaped by the emitter before embedding in the JSON line. The escapes are applied **in order** — order is normative. A consumer implementing its own emitter MUST apply the escapes in this sequence; out-of-order application double-escapes.

| Step | Input character | Output sequence | Rationale |
|---|---|---|---|
| 1 | `\` backslash | `\\` | **Must be first.** Escaping backslash last would double-escape all `\n`, `\r`, `\t` sequences already emitted in steps 3–5. |
| 2 | `"` double-quote | `\"` | Closes the JSON string value prematurely without escaping. |
| 3 | CR (`\r`, U+000D) | `\r` (literal two chars) | Bare carriage returns produce invalid JSON; common in Windows git stderr captured as multiline `detail`. |
| 4 | LF (`\n`, U+000A) | `\n` (literal two chars) | Bare linefeeds end the NDJSON line prematurely. |
| 5 | TAB (`\t`, U+0009) | `\t` (literal two chars) | Bare tabs produce technically-invalid compact JSON string values. |

**What is NOT escaped:** All other C0 control characters (U+0000–U+001F except the five above), NUL, and non-ASCII bytes (including multi-byte UTF-8) pass through raw. This boundary is intentional — the five-escape set covers the characters that break NDJSON line framing and JSON string validity in practice. Consumers must not assume additional escaping.

The bash reference (claude-klabauter `coordinator_core/install/step_zero_emit.py`, function `_co_pp_json_escape`) implements exactly this five-step sequence. Read the source to confirm — the source is authoritative on what the bash emitter does; the fixture is authoritative on what every conformant emitter must produce.

---

## Conformance Fixture and Protocol

### Fixture as normative authority

`tests/fixtures/step-zero-conformance.json` is the **single normative authority** for the contract. The bash reference (claude-klabauter `coordinator_core/install/step_zero_emit.py`) is the worked example for bash consumers — illustrative, not normative. Non-bash consumers (node, Python, PowerShell) conform against the fixture bytes, not against bash `printf` formatting.

The fixture root carries `"contract_version": "1.1"` (v1.1 adds `semi-hard` to the `severity` enum; v1.0 was the first release with the full five-escape set). Versioning policy:

- **Minor bump** — additive escape cases, new optional fields in probe lines, or new enum values added to `status` or `severity`.
- **Major bump** — any key or enum removal, or a change to escape semantics.

Re-implementer consumers should pin the contract version they were validated against. Verbatim-vendors pin the source SHA instead (see § Consumer conformance protocol → Verbatim-vendor below).

### Consumer conformance protocol

**First, pick your vendor-mode — the conformance story differs by how you obtain the emitter.** Both modes prove the same property (your emitter produces contract-conformant bytes); they differ in which artifact is the oracle.

| Vendor-mode | What you ship | Conformance oracle |
|---|---|---|
| **Re-implementer** | Your own emitter in your own language (PowerShell, Python, node) — no bash SSOT in your tree | The **fixture bytes**. You have no SSOT blob to match, so the fixture is your independent oracle. |
| **Verbatim-vendor** | A byte-for-byte copy of the bash SSOT (claude-klabauter `coordinator_core/install/step_zero_emit.py`) vendored into your tree | The **SSOT blob at a pinned SHA**. Conformance is transitive (see below). Do **not** re-vendor the fixture. |

#### Re-implementer — conform against the fixture

To prove your own-language emitter conforms:

1. **Vendor the fixture.** Copy `tests/fixtures/step-zero-conformance.json` into your repo under a path you control. _(Vendoring is correct for this stable, ratified contract — but wrong for a HEAD-tracking drift-check, where it induces blindness to DoE-HEAD drift; see `emission-conformance-contract.md` § Dedicated-Ref Freshness Protocol and § EM-Response-2a.)_
2. **Pin `eol=lf` on your vendored copy.** Add the following line to a `.gitattributes` file **inside your vendored copy's directory** (not inherited from a parent):
   ```
   step-zero-conformance.json text eol=lf
   ```
   The shipped fixture carries **no inheritable `eol` attribute**. The meta-repo `.gitattributes` that enforces LF in coordinator's own checkout does NOT ship to OSS consumers or get copied to sibling repos when they vendor the file. Without this explicit pin, git may silently rewrite fixture bytes to CRLF on Windows — invalidating the byte-equality check. The pin must live inside the vendored directory so it travels with the file.
3. **Wire a `bin/check-fixture-sync.sh`** that fetches the canonical fixture from this repo and asserts it is byte-identical to your vendored copy. See `docs/wiki/cross-repo-contract-test-discipline.md` for the skip-if-prerequisite-absent pattern.
4. **Run your emitter against every case.** For each entry in `cases`:
   - Feed `input.name`, `input.status`, `input.severity`, `input.detail`, `input.remediation` to your emitter.
   - Base64-decode `expected_output_bytes` to recover the expected line bytes.
   - Assert **byte equality** between your emitter's output and the decoded bytes (including the trailing `\n`).
5. **Fail non-zero on any mismatch.** A conformance runner that exits 0 with mismatched bytes is a false-pass — the same antipattern as `inconclusive` collapsed into `pass`.

The escaping cases in the fixture (backslash, double-quote, CR, LF, TAB, CRLF in `detail`, and empty `remediation`) are the load-bearing cases — they pin the five-escape-in-order behavior that is most likely to drift across language emitters.

#### Verbatim-vendor — pin the SHA, skip the fixture

If you vendor the bash SSOT (claude-klabauter `coordinator_core/install/step_zero_emit.py`) **verbatim**, running the fixture is redundant *and* strictly weaker than a byte-identity pin. Prove conformance this way instead:

1. **Pin the source SHA.** Record the coordinator commit your vendored copy was taken from.
2. **Byte-identity hard gate.** Assert your vendored emitter body is byte-identical to the coordinator blob *at the pinned SHA*. This byte-identity test **is** your conformance test.
3. **Freshness advisory leg.** Assert the pinned SHA == coordinator HEAD as an advisory (xfail / warn, not red) re-vendor-due nudge. Coordinator is `source_is_live`, so HEAD is the conformance-validated SSOT.
4. **Do NOT vendor the fixture, the `.gitattributes` `eol=lf` pin, or a `contract_version` pin.** They add no safety over the SHA-pin and re-import the unpinned-`eol=lf` drift hazard that the re-implementer recipe has to guard against.

**Why this is sound (transitive conformance):** copy == SSOT (your byte-identity gate) ∧ SSOT ⊨ fixture (claude-klabauter's own `coordinator_core/tests/test_step_zero_emit.py`) ⇒ copy ⊨ fixture. The verbatim vendor never needs to run the fixture itself.

**Why byte-identity is *stronger* than fixture conformance:** it catches drift the fixture cannot — whitespace, comment text, and crucially **escape-order** (the five-escape ordering is normative; a re-ordered-but-still-conformant emitter would pass the fixture yet differ from the SSOT). A verbatim vendor that ran only the fixture would hold a *weaker* guarantee than one that pins the SHA.

Reference implementation of this mode: `project-rag-ue-addon` vendors the 3-file unit (`prereq_probe.sh` + `manifest_reader.sh` + `step_zero_emit.sh`) into `project_rag_ue_addon_scripts/lib/coordinator_prereq/`, with `tests/test_prereq_probe_parity.py` carrying a hard byte-identity gate plus an advisory pin-==-HEAD freshness leg — no fixture, no `.gitattributes`, no `contract_version`.

---

## Polyglot Emitters — Consumer Responsibility

Coordinator ships the bash reference (claude-klabauter `coordinator_core/install/step_zero_emit.py`) and the conformance fixture. It does **not** ship PowerShell, node, or Python reference emitters. Each consumer repo owns its emitter in its own language; the fixture is the polyglot surface that makes all of them comparable. YAGNI on multi-language emitters until a consumer asks.

**bash-reference sourcing caveat.** `step_zero_emit.sh` calls `exit 78` (not `return`) when sourced under bash < 4 — intentional for coordinator's own call sites (a bash<4 environment can't run the consumers either). A sibling that sources the bash reference inside a function, subshell, or test harness must be aware it will **exit the containing process** (code 78) on a bash-version mismatch rather than returning an error. If you need return-not-exit semantics, wrap the source in a subshell you can branch on, or port the contract to your own language against the fixture rather than sourcing the bash reference directly.

---

## Related

- claude-klabauter `coordinator_core/install/step_zero_emit.py` — bash reference implementation (illustrative, not normative).
- `tests/fixtures/step-zero-conformance.json` — normative fixture (v1.1).
- claude-klabauter `coordinator_core/tests/test_step_zero_emit.py` — conformance runner for the reference implementation (ships in the coordinator source tree; sibling consumers wire their own runner against the vendored fixture).
- `docs/wiki/doctor-probe-design.md` § `inconclusive` Is a First-Class Probe Status — the rationale for the `inconclusive` vocabulary rule and the broader fidelity doctrine for probes.
- `docs/wiki/cross-repo-contract-test-discipline.md` — skip-if-prerequisite-absent gates and cross-repo fixture sync patterns.
- `docs/wiki/cross-repo-contract-parity.md` — producer/consumer contract-field parity across repos.
