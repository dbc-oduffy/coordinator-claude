"""Deterministic coordinator-plugin to host-plugin tree translator, driven by unimatrix-host-map.json.

`generate(plugin_root, out_dir, host)` reads a Claude plugin source tree and writes the host's
plugin tree: same inputs give the same bytes on every OS (pathlib only, sorted traversal, LF text,
no symlinks). Anything the host table cannot translate is listed in UNMAPPED.json at the tree root.
Stdlib only; no subprocess, no LLM step.

agy hooks.json is a top-level object keyed by hook name, each value {"<Event>": [...]} (shape from
the agy 1.4.12 strict-validate relay; no agy doc on the build box). `agy plugin validate` proves the
file loads, not that a hook fires: ${PLUGIN_DIR} expansion and a guard running need a live agy
session, which nothing here covers.
"""
import json
import re
import shutil
from pathlib import Path

TABLE_NAME = "unimatrix-host-map.json"
UNMAPPED_NAME = "UNMAPPED.json"
TOKEN_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}|\$CLAUDE_PLUGIN_ROOT\b")
TOOL_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
SKIP_NAMES = frozenset({"__pycache__", ".DS_Store", ".git"})
DOCTRINE_SOURCES = ("global-doctrine/CLAUDE.md", "global-doctrine/rules/rules.md")
NO_MAP = "host has no mapping table entry"


def load_table():
    """The per-host mapping table, read from beside this file."""
    return json.loads((Path(__file__).resolve().with_name(TABLE_NAME)).read_text(encoding="utf-8"))


def _is_text(data):
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _lf(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text if not text or text.endswith("\n") else text + "\n"


def _json_bytes(obj):
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _walk(root):
    """Files under root as (posix rel path, Path), sorted by rel path; symlinks and junk are skipped."""
    found = []
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if SKIP_NAMES & set(rel.parts) or p.suffix == ".pyc" or p.is_symlink() or not p.is_file():
            continue
        found.append((rel.as_posix(), p))
    return sorted(found, key=lambda t: t[0])


def _split_frontmatter(text):
    """(frontmatter lines, body) for a leading `---` block, else (None, text)."""
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return lines[1:i], "\n".join(lines[i + 1:])
    return None, text


def _join_frontmatter(head, body):
    return "---\n" + "\n".join(head) + "\n---\n" + body.lstrip("\n") if head else body


def _field(head, key):
    for i, line in enumerate(head):
        if re.match(rf"{re.escape(key)}\s*:", line):
            return i, line.split(":", 1)[1].strip().strip("\"'")
    return None, None


class _Plan:
    """Collects translated files and the unmapped report; writes nothing until finished."""

    def __init__(self, cfg, token_suffixes):
        self.cfg = cfg
        self.files = {}
        self.unmapped = set()
        self.suffixes = tuple(token_suffixes)

    def miss(self, kind, source, reason):
        self.unmapped.add((kind, source, reason))

    def put(self, rel, data, kind, source):
        if rel in self.files:
            self.miss(kind, source, f"output path {rel} already produced by another source")
            return False
        self.files[rel] = data
        return True

    def rewrite(self, text):
        return TOKEN_RE.sub(lambda _m: self.cfg["plugin_root_token"], text)

    def put_file(self, rel, src_path, kind, source):
        """Copy one source file; text is LF-normalised and gets the plugin-root token rewritten."""
        data = src_path.read_bytes()
        if _is_text(data):
            text = _lf(data.decode("utf-8"))
            if rel.endswith(self.suffixes):
                text = self.rewrite(text)
            data = text.encode("utf-8")
        return self.put(rel, data, kind, source)


def _doctrine_text(plugin_root):
    base = plugin_root
    for root in (base.parent, base, base.parent / "templates", base / "templates"):
        if (root / DOCTRINE_SOURCES[0]).is_file():
            parts = [_lf((root / s).read_text(encoding="utf-8")) for s in DOCTRINE_SOURCES if (root / s).is_file()]
            return "\n".join(parts)
    return None


def _inventory(plugin_root):
    """(kind, rel source) of every translatable item, for a host whose table is empty."""
    items = []
    for kind, sub in (("agent", "agents"), ("command", "commands")):
        d = plugin_root / sub
        if d.is_dir():
            items += [(kind, f"{sub}/{rel}") for rel, _ in _walk(d) if rel.endswith(".md")]
    skills = plugin_root / "skills"
    if skills.is_dir():
        items += [("skill", f"skills/{c.name}") for c in sorted(skills.iterdir(), key=lambda c: c.name)
                  if not c.is_symlink()]
    if (plugin_root / "hooks" / "hooks.json").is_file():
        items.append(("hooks", "hooks/hooks.json"))
    if _doctrine_text(plugin_root) is not None:
        items.append(("rules", DOCTRINE_SOURCES[0]))
    return items


def _map_model(value, cfg):
    """(agy tier, None) or (None, reason)."""
    tiers = cfg["tiers"]
    if value in tiers:
        if tiers[value] is None:
            return None, f"tier {value!r} has no agy value"
        return tiers[value], None
    if value in cfg["valid_tiers"]:
        return value, None
    return None, f"model {value!r} is not a known tier"


def _agents(plan, plugin_root):
    d = plugin_root / "agents"
    if not d.is_dir():
        return
    for rel, p in _walk(d):
        src = f"agents/{rel}"
        if not rel.endswith(".md"):
            plan.miss("agent", src, "not a markdown agent file")
            continue
        text = plan.rewrite(_lf(p.read_text(encoding="utf-8")))
        head, body = _split_frontmatter(text)
        if head is not None:
            i, val = _field(head, "model")
            if i is not None:
                new, reason = _map_model(val, plan.cfg)
                if new is None:
                    del head[i]
                    plan.miss("agent-model", src, reason)
                else:
                    head[i] = f"model: {new}"
                text = _join_frontmatter(head, body)
        plan.put(src, text.encode("utf-8"), "agent", src)


def _command_skills(plan, plugin_root):
    d = plugin_root / "commands"
    if not d.is_dir():
        return
    for rel, p in _walk(d):
        src = f"commands/{rel}"
        if not rel.endswith(".md"):
            plan.miss("command", src, "not a markdown command file")
            continue
        if not plan.cfg["commands_to_skills"]:
            plan.miss("command", src, "host has no command surface")
            continue
        name = "-".join(Path(rel[:-3]).parts)
        out = f"skills/{name}/SKILL.md"
        head, body = _split_frontmatter(plan.rewrite(_lf(p.read_text(encoding="utf-8"))))
        head = list(head or [])
        i, _ = _field(head, "name")
        if i is None:
            head.insert(0, f"name: {name}")
        else:
            head[i] = f"name: {name}"
        _put_skill_md(plan, out, _join_frontmatter(head, body), src)


def _put_skill_md(plan, out, text, src):
    data = text.encode("utf-8")
    cap = plan.cfg["max_text_bytes"]
    if len(data) > cap:
        plan.miss("oversize", src, f"{len(data)} bytes exceeds the {cap}-byte cap")
        return
    plan.put(out, data, "skill", src)


def _skills(plan, plugin_root):
    d = plugin_root / "skills"
    if not d.is_dir():
        return
    for child in sorted(d.iterdir(), key=lambda c: c.name):
        src = f"skills/{child.name}"
        if child.is_symlink() or SKIP_NAMES & {child.name}:
            continue
        if not child.is_dir() or not (child / "SKILL.md").is_file():
            plan.miss("skill", src, "not a directory holding SKILL.md")
            continue
        text = plan.rewrite(_lf((child / "SKILL.md").read_text(encoding="utf-8")))
        head, body = _split_frontmatter(text)
        head = list(head or [])
        i, name = _field(head, "name")
        name = name or child.name
        if i is None:
            head.insert(0, f"name: {name}")
        out_dir = f"skills/{name}"
        _put_skill_md(plan, f"{out_dir}/SKILL.md", _join_frontmatter(head, body), f"{src}/SKILL.md")
        for rel, p in _walk(child):
            if rel != "SKILL.md":
                plan.put_file(f"{out_dir}/{rel}", p, "skill-file", f"{src}/{rel}")


def _hook_matcher(matcher, event, plan):
    mapped = []
    for tok in matcher.split("|"):
        t = tok.strip()
        if t in plan.cfg["tools"]:
            mapped.append(plan.cfg["tools"][t])
            continue
        if TOOL_NAME_RE.fullmatch(t):
            plan.miss("matcher", "hooks/hooks.json", f"{event}: tool {t!r} has no agy name")
        mapped.append(t)
    return "|".join(mapped)


def _flatten_groups(groups, event, plan):
    """agy takes bare command handlers for a non-tool event; a matcher/hooks group is rejected whole."""
    flat = []
    for group in groups:
        if isinstance(group, dict) and isinstance(group.get("hooks"), list):
            if "matcher" in group:
                plan.miss("matcher", "hooks/hooks.json", f"{event}: matcher {group['matcher']!r} dropped; agy {event} takes none")
            flat += group["hooks"]
        else:
            flat.append(group)
    return flat


def _hook_name(event):
    """agy hook name for one event's handlers: the event in kebab case (PreToolUse -> pre-tool-use)."""
    return re.sub(r"(?<!^)(?=[A-Z])", "-", event).lower()


def _hooks(plan, plugin_root):
    src = plugin_root / "hooks" / "hooks.json"
    if not src.is_file():
        return
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except ValueError as exc:
        plan.miss("hooks", "hooks/hooks.json", f"unparseable JSON: {exc}")
        return
    drop = set(plan.cfg["hook_drop_fields"])

    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items() if k not in drop}
        if isinstance(o, list):
            return [clean(v) for v in o]
        return plan.rewrite(o) if isinstance(o, str) else o

    data = clean(data)
    events = data.get("hooks") if isinstance(data, dict) else None
    if isinstance(events, dict):
        for event in sorted(events):
            if event not in plan.cfg["hook_events"]:
                plan.miss("hook-event", "hooks/hooks.json", f"event {event!r} has no agy equivalent")
                del events[event]
                continue
            groups = events[event] if isinstance(events[event], list) else []
            if event not in plan.cfg["tool_hook_events"]:
                events[event] = _flatten_groups(groups, event, plan)
                continue
            for group in groups:
                if isinstance(group, dict) and isinstance(group.get("matcher"), str):
                    group["matcher"] = _hook_matcher(group["matcher"], event, plan)
    named = {_hook_name(event): {event: events[event]} for event in sorted(events)} if isinstance(events, dict) else {}
    plan.put(plan.cfg["hooks_path"], _json_bytes(named), "hooks", "hooks/hooks.json")


def _rules(plan, plugin_root):
    text = _doctrine_text(plugin_root)
    if text is None:
        plan.miss("rules", DOCTRINE_SOURCES[0], "no global-doctrine/CLAUDE.md beside the plugin root")
        return
    head, body = _split_frontmatter(plan.rewrite(text))
    head = list(head or [])
    i, _ = _field(head, "trigger")
    line = f"trigger: {plan.cfg['rules_trigger']}"
    if i is None:
        head.insert(0, line)
    else:
        head[i] = line
    data = _join_frontmatter(head, body).encode("utf-8")
    cap = plan.cfg["max_text_bytes"]
    if len(data) > cap:
        plan.miss("oversize", DOCTRINE_SOURCES[0], f"{len(data)} bytes exceeds the {cap}-byte cap")
        return
    plan.put(plan.cfg["rules_path"], data, "rules", DOCTRINE_SOURCES[0])


def _manifest(plan, plugin_root):
    """plugin.json at the output root: name, version, description, logo from the source manifest."""
    src = plugin_root / plan.cfg["source_manifest_path"]
    source = {}
    if src.is_file():
        try:
            loaded = json.loads(src.read_text(encoding="utf-8"))
            source = loaded if isinstance(loaded, dict) else {}
        except ValueError as exc:
            plan.miss("manifest", plan.cfg["source_manifest_path"], f"unparseable JSON: {exc}")
    else:
        plan.miss("manifest", plan.cfg["source_manifest_path"], "no source plugin manifest; name taken from the directory")
    manifest = {"name": source.get("name") or plugin_root.resolve().name}
    for key in ("version", "description"):
        if isinstance(source.get(key), str):
            manifest[key] = source[key]
    logo = source.get("logo")
    if isinstance(logo, str) and logo:
        manifest["logo"] = logo
        logo_path = plugin_root / logo
        if not Path(logo).is_absolute() and ".." not in Path(logo).parts and logo_path.is_file():
            plan.put_file(Path(logo).as_posix(), logo_path, "file", logo)
    plan.put(plan.cfg["manifest_path"], _json_bytes(manifest), "manifest", plan.cfg["source_manifest_path"])


def _copied_dirs(plan, plugin_root):
    for name in plan.cfg["copy_dirs"]:
        d = plugin_root / name
        if not d.is_dir():
            continue
        for rel, p in _walk(d):
            if name == "hooks" and rel == "hooks.json":
                continue
            plan.put_file(f"{name}/{rel}", p, "file", f"{name}/{rel}")


def _unhandled_top_level(plan, plugin_root):
    handled = {"agents", "commands", "skills", "hooks", *plan.cfg["copy_dirs"], *plan.cfg["ignore_top_level"]}
    for child in sorted(plugin_root.iterdir(), key=lambda c: c.name):
        if child.name not in handled and child.name not in SKIP_NAMES:
            plan.miss("surface", child.name, "no mapping for this plugin surface")


def _prepare_out(out_dir, plugin_root):
    out, src = out_dir.resolve(), plugin_root.resolve()
    if out == src or src.is_relative_to(out) or out.is_relative_to(src):
        raise ValueError(f"out dir {out_dir} overlaps the plugin source {plugin_root}")
    if out.exists():
        if not out.is_dir():
            raise ValueError(f"out path {out_dir} is not a directory")
        entries = sorted(out.iterdir(), key=lambda c: c.name)
        if entries and not (out / UNMAPPED_NAME).is_file():
            raise ValueError(f"out dir {out_dir} is not empty and holds no prior {UNMAPPED_NAME}; refusing to clear it")
        for e in entries:
            if e.is_dir() and not e.is_symlink():
                shutil.rmtree(e)
            else:
                e.unlink()
    out.mkdir(parents=True, exist_ok=True)
    return out


def generate(plugin_root, out_dir, host="agy"):
    """Write `host`'s plugin tree for `plugin_root` into `out_dir`.

    Returns {"written": [sorted posix rel paths, UNMAPPED.json included],
    "unmapped": [{"kind", "source", "reason"}, ...] sorted}. ValueError for an unknown host or an
    out_dir that is non-empty without a prior UNMAPPED.json (or overlaps the source); the tree is
    built in memory first, so a failed run clears nothing.
    """
    plugin_root, out_dir = Path(plugin_root), Path(out_dir)
    table = load_table()
    if host not in table:
        raise ValueError(f"unknown host {host!r}; table has {', '.join(sorted(table))}")
    cfg = table[host]
    if not plugin_root.is_dir():
        raise ValueError(f"plugin root {plugin_root} is not a directory")
    plan = _Plan(cfg, cfg.get("token_suffixes", ()))
    if not cfg:
        for kind, source in _inventory(plugin_root):
            plan.miss(kind, source, NO_MAP)
    else:
        _manifest(plan, plugin_root)
        _agents(plan, plugin_root)
        _command_skills(plan, plugin_root)
        _skills(plan, plugin_root)
        _hooks(plan, plugin_root)
        _rules(plan, plugin_root)
        _copied_dirs(plan, plugin_root)
        _unhandled_top_level(plan, plugin_root)
    unmapped = [{"kind": k, "source": s, "reason": r} for k, s, r in sorted(plan.unmapped)]
    plan.files[UNMAPPED_NAME] = _json_bytes({"host": host, "unmapped": unmapped})
    out = _prepare_out(out_dir, plugin_root)
    written = sorted(plan.files)
    for rel in written:
        target = out.joinpath(*rel.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(plan.files[rel])
    return {"written": written, "unmapped": unmapped}
