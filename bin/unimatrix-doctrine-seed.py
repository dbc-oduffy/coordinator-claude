"""Seed DoE doctrine and skills into the Codex and agy host surfaces.

One managed-block implementation serves every marker pair (`split_block`, `seed_block`,
`unseed_block`); the installer's peer-doctrine helpers rebind onto it. Text outside a block's markers
is never touched.

Surfaces: a managed coordinator-doctrine block in a host rules file under a byte cap (Codex
`project_doc_max_bytes` 32768, agy 24000); agy `skills.json` `entries[]` path entries; Codex user
skills at SKILL.md under each skill's folder in the home directory's .agents/skills (not moved by CODEX_HOME), one symlink per skill
(a copy where the symlink is refused) with a sibling `<skill>.coordinator-managed` marker that
uninstall requires before removing anything.
"""
import json
import os
import shutil
import sys
from pathlib import Path

DOCTRINE_BEGIN = "<!-- BEGIN coordinator-doctrine (managed by unimatrix-install; edits inside are overwritten) -->"
DOCTRINE_END = "<!-- END coordinator-doctrine -->"
CODEX_CAP_BYTES = 32768
AGY_CAP_BYTES = 24000
MANAGED_SUFFIX = ".coordinator-managed"
DOCTRINE_SOURCES = ("global-doctrine/CLAUDE.md", "global-doctrine/rules/rules.md")


def main(argv):
    """Library module with no run work: report that and exit 2 (unimatrix-install.py imports it)."""
    print("unimatrix-doctrine-seed: library module imported by unimatrix-install.py; nothing to run", file=sys.stderr)
    return 2


def split_block(text, begin, end):
    """Return (before, after) around the managed block delimited by begin/end, or None when absent."""
    start = text.find(begin)
    if start < 0:
        return None
    stop = text.find(end, start)
    if stop < 0:
        return None
    stop += len(end)
    if text[stop:stop + 1] == "\n":
        stop += 1
    return text[:start], text[stop:]


def seed_block(path, block, begin, end):
    """Write the managed block into a rules file; return "created", "added", "updated" or "present"."""
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(block, encoding="utf-8")
        return "created"
    text = path.read_text(encoding="utf-8")
    parts = split_block(text, begin, end)
    if parts is None:
        sep = "" if not text or text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        path.write_text(text + sep + block, encoding="utf-8")
        return "added"
    new = parts[0] + block + parts[1]
    if new == text:
        return "present"
    path.write_text(new, encoding="utf-8")
    return "updated"


def unseed_block(path, begin, end):
    """Remove only the managed block (deleting a file left empty); return "removed" or "absent"."""
    path = Path(path)
    if not path.exists():
        return "absent"
    text = path.read_text(encoding="utf-8")
    parts = split_block(text, begin, end)
    if parts is None:
        return "absent"
    before, after = parts
    if before.endswith("\n\n") and not after:
        before = before[:-1]
    rest = before + after
    if rest.strip():
        path.write_text(rest, encoding="utf-8")
    else:
        path.unlink()
    return "removed"


def render_coordinator_doctrine(plugin_root, cap_bytes):
    """Return the managed block of global-doctrine CLAUDE.md then rules.md; ValueError above cap_bytes UTF-8 bytes."""
    root = Path(plugin_root)
    body = "\n\n".join((root / rel).read_text(encoding="utf-8").strip("\n") for rel in DOCTRINE_SOURCES)
    block = f"{DOCTRINE_BEGIN}\n{body}\n{DOCTRINE_END}\n"
    size = len(block.encode("utf-8"))
    if size > cap_bytes:
        raise ValueError(f"coordinator doctrine block is {size} bytes, over the {cap_bytes}-byte host cap")
    return block


def _load_entries(skills_json):
    path = Path(skills_json)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8") or "{}")
    return data if isinstance(data, dict) else {}


def seed_agy_skills(skills_json, skills_root):
    """Add one {"path": skills_root} entry to agy skills.json; return "created", "added" or "present"."""
    path = Path(skills_json)
    existed = path.exists()
    data = _load_entries(path)
    entries = data.get("entries")
    if not isinstance(entries, list):
        entries = []
    wanted = str(skills_root)
    if any(isinstance(e, dict) and e.get("path") == wanted for e in entries):
        return "present"
    data["entries"] = entries + [{"path": wanted}]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return "added" if existed else "created"


def unseed_agy_skills(skills_json, skills_root):
    """Remove only our path entry (deleting a file left with no entries and no other keys); return "removed" or "absent"."""
    path = Path(skills_json)
    if not path.exists():
        return "absent"
    data = _load_entries(path)
    entries = data.get("entries")
    wanted = str(skills_root)
    if not isinstance(entries, list) or not any(isinstance(e, dict) and e.get("path") == wanted for e in entries):
        return "absent"
    kept = [e for e in entries if not (isinstance(e, dict) and e.get("path") == wanted)]
    data["entries"] = kept
    if not kept and set(data) == {"entries"}:
        path.unlink()
    else:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return "removed"


def _skill_dirs(skills_root):
    root = Path(skills_root)
    if not root.is_dir():
        return []
    return sorted(d for d in root.iterdir() if d.is_dir() and (d / "SKILL.md").is_file())


def _marker(dest):
    return dest.with_name(dest.name + MANAGED_SUFFIX)


def _remove_entry(dest):
    if dest.is_symlink() or dest.is_file():
        dest.unlink()
    elif dest.is_dir():
        shutil.rmtree(dest)


def seed_codex_skills(agents_skills_dir, skills_root):
    """Expose each depth-2 SKILL.md dir of skills_root under agents_skills_dir; return the names seeded.

    An entry without our marker is foreign and left alone. A marker-carrying entry whose
    source skill is gone is pruned.
    """
    dest_root = Path(agents_skills_dir)
    seeded = []
    live = {src.name for src in _skill_dirs(skills_root)}
    if dest_root.is_dir():
        for marker in sorted(dest_root.glob("*" + MANAGED_SUFFIX)):
            name = marker.name[: -len(MANAGED_SUFFIX)]
            if name not in live:
                _remove_entry(dest_root / name)
                marker.unlink()
    for src in _skill_dirs(skills_root):
        dest = dest_root / src.name
        marker = _marker(dest)
        if (dest.exists() or dest.is_symlink()) and not marker.exists():
            continue
        dest_root.mkdir(parents=True, exist_ok=True)
        if dest.exists() or dest.is_symlink():
            _remove_entry(dest)
        try:
            os.symlink(src, dest, target_is_directory=True)
        except OSError:
            shutil.copytree(src, dest)
        marker.write_text("managed by unimatrix-install\n", encoding="utf-8")
        seeded.append(src.name)
    return seeded


def unseed_codex_skills(agents_skills_dir):
    """Remove only marker-carrying skill entries (and their markers); return the names removed."""
    dest_root = Path(agents_skills_dir)
    if not dest_root.is_dir():
        return []
    removed = []
    for marker in sorted(dest_root.glob("*" + MANAGED_SUFFIX)):
        dest = dest_root / marker.name[: -len(MANAGED_SUFFIX)]
        _remove_entry(dest)
        marker.unlink()
        removed.append(dest.name)
    return removed


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
