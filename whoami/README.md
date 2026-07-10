# coordinator-whoami

Cross-plugin MCP whoami package. Owns the canonical contract schema, the
plugin-agnostic envelope validator + builder, and per-plugin subpackages
(project-rag ships first; example-game-repo-control slots in without refactor).

Spec backlink: `archive/specs/2026-05/2026-05-19-whoami-substrate-migration.md`
Contract spec: `docs/wiki/cross-plugin-whoami-contract.md`

## Install

Development (editable, from this directory):

```bash
pip install -e .
```

OSS distribution ships through `X:/coordinator-claude` via `setup/publish.sh`.
Do not install from PyPI — this package is not published there.

## CLI invocation (project-rag subpackage)

```bash
python -m coordinator_whoami.project_rag
python -m coordinator_whoami.project_rag --human
python -m coordinator_whoami.project_rag --refresh
python -m coordinator_whoami.project_rag --no-persist
```

Note: there is no `--contract` flag. The CLI always emits envelope-shaped
JSON (R2 single-canonical-shape decision). The `--human` flag pretty-prints
the envelope for human reading; the default is compact JSON.

## Package layout

```
coordinator_whoami/          # Generic, plugin-agnostic surfaces
  contract.py                #   validate_envelope() — Draft 2020-12 validator
  envelope_base.py           #   build_envelope() — plugin-agnostic primitive
  schemas/
    whoami-envelope.v1.json  #   Vendored contract schema (package-data)
  project_rag/               # project-rag-specific subpackage
    __main__.py              #   CLI entry point; invokes compose_envelope() + optional persist()
    cli.py                   #   compose(), WHOAMI_SCHEMA_VERSION — host introspection probe
    envelope.py              #   compose_envelope(), persist() — contract projection + persistence
    addons.py                #   Addon contributor discovery + dispatch
    _paths.py                #   resolve_user_marker_dir (inlined from project-rag)
    schemas/
      cli_output.v1.json     #   Inner per-plugin CLI-output schema
```
<!-- Review: Reviewer C C-F5 — added __main__.py row; corrected cli.py comment; moved persist() to envelope.py row -->

## Public API

Generic (plugin-agnostic, `coordinator_whoami` root):
- `validate_envelope(envelope: dict) -> None` — raises `jsonschema.ValidationError` on non-conformance
- `build_envelope(*, plugin_name, extras_key, plugin_version, binding, status, plugin_extras, addon_extras=None) -> dict`  <!-- Review: Reviewer C C-F1 — added missing extras_key param and keyword-only * marker -->

project-rag subpackage (`coordinator_whoami.project_rag`):
- `compose() -> dict` — host introspection; returns CLI-output-shaped dict (from `cli.py`)
- `compose_envelope() -> dict` — projects compose() output into contract envelope (from `envelope.py`)
- `persist(envelope: dict) -> Path` — writes envelope under `whoami_profile` in `~/.claude/project-rag/install-profile.json` (from `envelope.py`; atomic write via tmp+os.replace)
<!-- Review: Reviewer C C-F5 — persist() correctly attributed to envelope.py, not cli.py -->
