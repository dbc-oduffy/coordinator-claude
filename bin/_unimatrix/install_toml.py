"""Minimal TOML status-line editor for Codex config.toml.

Stdlib-only (uses tomllib), inert on import.
"""
import json
import os
import shutil
import tempfile
import tomllib
from pathlib import Path

_STATUS_DEFAULT = ["thread-name"]
_STATUS_PATHS = {"current-dir", "project-root", "project", "project-name"}


def _status_profile(current) -> list[str]:
    if current is None or current == []:
        return list(_STATUS_DEFAULT)
    if not isinstance(current, list) or not all(isinstance(item, str) for item in current):
        raise ValueError("tui.status_line must be a string array")
    result = []
    for item in current:
        item = "thread-name" if item in _STATUS_PATHS else item
        if item != "thread-name" or item not in result:
            result.append(item)
    if "thread-name" not in result:
        result.insert(0, "thread-name")
    return result


def _toml_chunks(text):
    """Complete TOML statements, so fake headers inside multiline strings are data."""
    pending = ""
    offset = 0
    for line in text.splitlines(keepends=True):
        pending += line
        try:
            parsed = tomllib.loads(pending)
        except tomllib.TOMLDecodeError:
            continue
        yield offset, offset + len(pending), pending, parsed
        offset += len(pending)
        pending = ""
    if pending:
        raise ValueError("unsupported or incomplete TOML statement")


def _toml_inline(value):
    if isinstance(value, dict):
        return "{ " + ", ".join(json.dumps(key) + " = " + _toml_inline(item) for key, item in value.items()) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(_toml_inline(item) for item in value) + "]"
    if isinstance(value, (str, bool, int, float)):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    raise ValueError("unsupported inline TUI value; configuration unchanged")


def _status_edit(text, value):
    scope = ()
    tui_header = None
    for start, end, chunk, parsed in _toml_chunks(text):
        stripped = chunk.lstrip()
        if stripped.startswith("["):
            scope = ()
            branch = parsed
            while isinstance(branch, dict) and len(branch) == 1:
                key, branch = next(iter(branch.items()))
                scope += (key,)
            if scope == ("tui",):
                tui_header = end
            continue
        if scope == ("tui",) and "status_line" in parsed:
            replacement = "" if value is None else "status_line = " + _toml_inline(value) + "\n"
            return text[:start] + replacement + text[end:]
        if not scope and isinstance(parsed.get("tui"), dict):
            fields = dict(parsed["tui"])
            inline = chunk.split("=", 1)[0].strip() in ("tui", '"tui"', "'tui'")
            if "status_line" in fields or inline:
                if value is None:
                    fields.pop("status_line", None)
                else:
                    fields["status_line"] = value
                prefix = "tui = " if inline else "tui.status_line = "
                replacement = (prefix + _toml_inline(fields if prefix == "tui = " else value) + "\n") if fields else ""
                return text[:start] + replacement + text[end:]
    if value is None:
        return text
    assignment = "status_line = " + _toml_inline(value) + "\n"
    return text[:tui_header] + assignment + text[tui_header:] if tui_header is not None else "tui." + assignment + text


def _footer_write(path, text):
    """Atomic replacement keeps existing config permissions and unrelated bytes."""
    descriptor, temporary = tempfile.mkstemp(prefix=".coordinator-footer-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
        if path.exists():
            shutil.copymode(path, temporary)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _footer_state(path):
    state = json.loads(path.read_text(encoding="utf-8"))
    valid_array = lambda value: isinstance(value, list) and all(isinstance(item, str) for item in value)
    if (not isinstance(state, dict) or state.get("version") != 1
            or type(state.get("present")) is not bool or not valid_array(state.get("managed"))
            or (state["present"] and not valid_array(state.get("original")))):
        raise ValueError("invalid footer ownership record")
    return state


def seed_codex_status_line(config_path, *, uninstall=False) -> str:
    """Own only the footer value; restore only while it remains our exact value."""
    path = Path(config_path)
    state_path = path.with_name(".coordinator-status-line.json")
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    parsed = tomllib.loads(text)
    tui = parsed.get("tui", {})
    if not isinstance(tui, dict):
        raise ValueError("tui must be a table")
    present = "status_line" in tui
    current = tui.get("status_line")
    if uninstall:
        if not state_path.exists():
            return "absent"
        state = _footer_state(state_path)
        if current != state["managed"]:
            return "retained-customized"
        replacement = _status_edit(text, state["original"] if state["present"] else None)
        tomllib.loads(replacement)
        _footer_write(path, replacement)
        state_path.unlink()
        return "restored"
    prior = None
    if state_path.exists():
        try:
            prior = _footer_state(state_path)
        except ValueError:
            prior = None
    base = prior["original"] if prior is not None and current == prior["managed"] else current
    if prior is not None and current != prior["managed"] and isinstance(current, list):
        seeded = set(prior["managed"]) - set(prior["original"] or []) - set(_STATUS_DEFAULT)
        base = [item for item in current if item not in seeded]
    wanted = _status_profile(base)
    if wanted == current:
        return "present"
    replacement = _status_edit(text, wanted)
    check = tomllib.loads(replacement)
    if check.get("tui", {}).get("status_line") != wanted:
        raise ValueError("footer edit did not address global tui.status_line")
    state = _footer_state(state_path) if state_path.exists() else None
    if not isinstance(state, dict) or state.get("version") != 1 or current != state.get("managed"):
        state = {"version": 1, "present": present, "original": base}
    state["managed"] = wanted
    path.parent.mkdir(parents=True, exist_ok=True)
    _footer_write(state_path, json.dumps(state, ensure_ascii=False) + "\n")
    _footer_write(path, replacement)
    return "updated"
