"""The files a publish round derives and regenerates, never merges.

Trap: publish.py duplicates the stamp filename and the manifest rel on purpose (it cannot import
this package at module load); `coordinator/bin/tests/test_publish_round_derived_pinned.py` keeps
the copies equal. No git spawn in this module.
"""

from __future__ import annotations

import hashlib
import json
from typing import Mapping, Optional

EXPECTED_MANIFEST_REL = ".coordinator/expected-manifest.json"
REGENERATED_BASENAMES = frozenset({"_engine_stamp", "_engine_published_at"})


def is_peer_merge_derived(rel: str) -> bool:
    """True for the manifest rel or any path whose basename is a regenerated stamp file."""
    if rel == EXPECTED_MANIFEST_REL:
        return True
    return rel.replace("\\", "/").rsplit("/", 1)[-1] in REGENERATED_BASENAMES


def blob_sha(data: bytes) -> str:
    """Git blob sha1 of `data`."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def manifest_bytes(paths: Mapping[str, str], source_head: str) -> bytes:
    """Exact bytes of the expected manifest; the manifest never lists itself."""
    body_paths = {k: v for k, v in paths.items() if k != EXPECTED_MANIFEST_REL}
    body = json.dumps(
        {"schema": 1, "source_head": source_head, "paths": body_paths}, sort_keys=True, indent=2
    ) + "\n"
    return body.encode("utf-8")


def source_head_of(raw: bytes) -> Optional[str]:
    """`source_head` of a manifest's bytes; None when unparseable or absent."""
    try:
        value = json.loads(raw.decode("utf-8")).get("source_head")
    except (ValueError, AttributeError):
        return None
    return value if isinstance(value, str) else None
