from __future__ import annotations

import shlex


def win_safe_shlex_split(cmd_str: str) -> list[str]:
    lexer = shlex.shlex(cmd_str, posix=True)
    lexer.whitespace_split = True
    lexer.escape = ""
    return list(lexer)
