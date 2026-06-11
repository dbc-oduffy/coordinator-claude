# Parity Audit Doctrine

**Purpose:** When porting or migrating a plugin or module from one host to another, parity audits must include a dedicated sweep for host→plugin direct imports — code in the host repo that still references the plugin's old in-host location. Symbol-level diff alone misses this class of breakage: the symbols moved, but stale import paths in the host stay broken and only surface at runtime.

→ See also: `docs/wiki/plugin-extraction-and-distribution.md`, `docs/wiki/dual-identity-module-hazard.md`

---

## The Plugin-Migration Parity Gap

The standard parity checklist compares symbol sets and test coverage between old and new locations. That catches what moved and what was dropped. It does not catch what was left behind.

When a module is carved out of a host repo — extracted as a plugin, published as a standalone package, or split into a peer repo — the host codebase may still contain `import` or `from` statements pointing at the old in-host path. Those statements passed CI before the move because the module existed there. After the move they are broken, but no symbol-level diff flags them: the symbols are present in the new location; the broken call sites are in the host, not the plugin.

The failure mode is silent until runtime: the plugin installs cleanly, all plugin-side tests pass, symbol parity is green — and then the host crashes on first use because an unswept import still points at the carved-out path.

---

## The Audit Checklist

Run all four checks. Symbol parity alone is not sufficient.

1. **Symbol parity** — set diff of exported names between old and new location. Confirms nothing was accidentally dropped during the move.

2. **Test parity** — per-file mapping of test coverage. Each test that exercised the old location should have a counterpart exercising the new one.

3. **Host→plugin direct-import sweep** — grep the host repo for every import form that references the old module path. This is the check that symbol parity misses. See § Grep Recipe below.

4. **Configuration/registration parity** — entry points, plugin manifests, `setup.cfg` / `pyproject.toml` console scripts, hook registrations, MCP tool declarations. A symbol that moved but lost its registration is invisible to the host even if the import path was updated.

---

## When the Host→Plugin Sweep Applies

Run this sweep any time code moves out of the host's module tree:

- Carved-out plugin (in-repo module → standalone package)
- Extracted shared library (monorepo module → published package)
- Split repo (single repo → two repos with a dependency edge)
- Namespace reorganisation that changes the import root (e.g. `host.utils.foo` → `shared.foo`)

If import paths changed — even within the same repo — the sweep applies.

---

## Grep Recipe

Run both forms against the host repo root. Replace `old.module.path` with the Python dotted path (or JS/TS module specifier) of the old location.

```bash
# Python / CommonJS require-style
grep -rn "from old.module.path" <host-repo-root>
grep -rn "import old.module.path" <host-repo-root>

# Also catch aliased forms and partial-path matches
grep -rn "old/module/path" <host-repo-root>
```

Each match is a stale import that will fail at runtime after the move. Fix by updating the import to the new location, or deleting it if the call site was also removed.

For TypeScript/JavaScript, adapt the pattern to the module specifier form:

```bash
grep -rn "from ['\"]old-package/module['\"]" <host-repo-root>
grep -rn "require(['\"]old-package/module['\"]" <host-repo-root>
```

---

## Notes

- Run the sweep on the **host repo**, not the plugin repo. The plugin's own imports are covered by symbol parity; it is the host's stale references that this sweep targets.
- Paginated grep truncates results silently. Use `grep` directly or pass `head_limit: 0` in tool calls — a partial result gives false confidence.
- If the old path was a namespace package (multiple directories contributing to one dotted name), grep each contributing path separately.
