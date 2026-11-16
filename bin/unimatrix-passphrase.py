#!/usr/bin/env python3
"""Unimatrix key passphrases: the 1Password source, the no-argv/no-disk feed, the encrypted mint and the agent load.

The passphrase lives in a 1Password item `unimatrix-<alias>` (field `password`) in the vault named by the
machine-local key `unimatrix.passphrase_vault`. It is read with `op read` and reaches a consumer only through
a pipe or memory: never argv, never a file, never the environment of any process but the askpass child (which
receives the item reference, not the value).

Feed, chosen by the Windows OpenSSH spike (docs/research/unimatrix-key-passphrase/2026-11-09-feed-spike/synthesis.md):
  mint        in-process `cryptography` OpenSSH encrypted key write, every OS. Windows ssh-keygen cannot run a
              `.py` askpass (CreateProcess error 193) and falls back to an EMPTY passphrase, so it is not used.
  agent load  POSIX: `ssh-add` with SSH_ASKPASS aimed at this file's `askpass` entry.
              Windows: the agent wire protocol over the OpenSSH pipe, key decrypted in-process.

Usage as the askpass program: `unimatrix-passphrase.py askpass [<ref>]` prints the passphrase to stdout.
"""
import base64
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

VAULT_KEY = "unimatrix.passphrase_vault"
ITEM_PREFIX = "unimatrix-"
REF_ENV = "UNIMATRIX_PASSPHRASE_REF"
WINDOWS_AGENT_PIPE = r"\\.\pipe\openssh-ssh-agent"
OP_TIMEOUT = 30

_LOCKED_MARKERS = ("not currently signed in", "not signed in", "session expired", "authorization prompt",
                   "authorization timeout", "desktop app", "is locked", "sign in", "authenticat")
_ABSENT_MARKERS = ("isn't an item", "is not an item", "could not be found", "not found", "no item")


class PassphraseSourceMissing(RuntimeError):
    """The passphrase source cannot be reached: the op CLI is absent or the vault key is unset."""


class OnePasswordLocked(RuntimeError):
    """1Password is installed but locked or signed out; the caller waits and names the wait."""


def settings_home():
    env = os.environ.get("COORDINATOR_SETTINGS_HOME")
    return Path(env) if env else Path.home() / ".coordinator-claude-settings"


def _no_window():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def _tail(r):
    return (getattr(r, "stderr", "") or getattr(r, "stdout", "") or "").strip()[:300]


def _op(args, run):
    """Run `op <args>`; the CLI absent is PassphraseSourceMissing, a locked vault is OnePasswordLocked."""
    try:
        r = run(["op", *args], capture_output=True, text=True, timeout=OP_TIMEOUT, stdin=subprocess.DEVNULL,
                creationflags=_no_window())
    except (FileNotFoundError, NotADirectoryError):
        raise PassphraseSourceMissing("passphrase_source_missing: op CLI not found on PATH; install the "
                                      "1Password CLI or mint with --unencrypted-key") from None
    except subprocess.TimeoutExpired:
        raise OnePasswordLocked("1password_locked: op did not answer within "
                                f"{OP_TIMEOUT}s (waiting on the 1Password unlock prompt)") from None
    return r


def _locked(r):
    return any(m in _tail(r).lower() for m in _LOCKED_MARKERS)


def _console_python():
    """A real console CPython for a child argv; OSError when none resolves."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("unimatrix_passphrase_python_interp",
                                                  Path(__file__).resolve().parent / "lib" / "python_interp.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    found = mod.resolve_console_python()
    if not found:
        raise FileNotFoundError("no console Python interpreter resolvable")
    return found


def _machine_local_spawn():
    """`coordinator_core.machine_local_spawn` with the engine on sys.path, or None when no engine resolves."""
    try:
        from coordinator_core import machine_local_spawn
        return machine_local_spawn
    except ImportError:
        pass
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
        from cc_invoke import ensure_engine_on_path

        ensure_engine_on_path(__file__)
        from coordinator_core import machine_local_spawn
        return machine_local_spawn
    except Exception:
        return None


def _machine_local_run(run, argv):
    """Run a machine-local reader argv: the injected `run` when a caller supplied one, else the bounded helper.

    A helper that is absent, fails to start or outlives its ceiling reads as exit 2."""
    if run is not subprocess.run:
        return run(argv, capture_output=True, text=True, timeout=OP_TIMEOUT, creationflags=_no_window())
    helper = _machine_local_spawn()
    done = helper.run_bounded(argv) if helper else None
    return done or subprocess.CompletedProcess(argv, 2, "", "machine-local spawn unavailable, failed or timed out")


def _vault(run):
    reader = settings_home() / "bin" / "_machine_local.py"
    missing = PassphraseSourceMissing(f"passphrase_source_missing: op CLI vault unset; set machine-local key "
                                      f"{VAULT_KEY} to the 1Password vault holding the key passphrases")
    if not reader.is_file():
        raise missing
    try:
        r = _machine_local_run(run, [_console_python(), str(reader), "get", VAULT_KEY])
    except (OSError, subprocess.SubprocessError):
        raise missing from None
    val = (r.stdout or "").strip() if not r.returncode else ""
    if not val:
        raise missing
    return val


def item_name(alias):
    return f"{ITEM_PREFIX}{alias}"


def op_ref(alias, run=subprocess.run):
    """`op://<vault>/unimatrix-<alias>/password`; PassphraseSourceMissing naming the key when the vault is unset."""
    return f"op://{_vault(run)}/{item_name(alias)}/password"


def state(run=subprocess.run):
    """'ready' (op present and signed in), 'locked' (present, not signed in) or 'missing' (no op CLI)."""
    if run is subprocess.run and not shutil.which("op"):
        return "missing"
    try:
        r = _op(["whoami"], run)
    except PassphraseSourceMissing:
        return "missing"
    except OnePasswordLocked:
        return "locked"
    return "ready" if r.returncode == 0 else "locked"


def read_passphrase(ref, run=subprocess.run):
    """The passphrase `op read` returns for `ref`; held in memory only. OnePasswordLocked when signed out."""
    r = _op(["read", "--no-newline", ref], run)
    if r.returncode:
        if _locked(r):
            raise OnePasswordLocked(f"1password_locked: unlock 1Password to read {ref}")
        raise RuntimeError(f"op read {ref} failed: {_tail(r)}")
    out = r.stdout or ""
    if not out:
        raise RuntimeError(f"op read {ref} returned an empty passphrase")
    return out


def ensure_item(alias, run=subprocess.run):
    """The ref of the alias's passphrase item, created with a generated password when absent."""
    ref = op_ref(alias, run)
    r = _op(["read", "--no-newline", ref], run)
    if r.returncode == 0:
        return ref
    if _locked(r):
        raise OnePasswordLocked(f"1password_locked: unlock 1Password to create {ref}")
    if not any(m in _tail(r).lower() for m in _ABSENT_MARKERS):
        raise RuntimeError(f"op read {ref} failed: {_tail(r)}")
    c = _op(["item", "create", "--category=password", f"--title={item_name(alias)}",
             f"--vault={_vault(run)}", "--generate-password=40,letters,digits"], run)
    if c.returncode:
        if _locked(c):
            raise OnePasswordLocked(f"1password_locked: unlock 1Password to create {ref}")
        raise RuntimeError(f"op item create {item_name(alias)} failed: {_tail(c)}")
    return ref


def delete_item(alias, run=subprocess.run):
    """Remove the alias's passphrase item; an item already absent is success."""
    r = _op(["item", "delete", item_name(alias), f"--vault={_vault(run)}"], run)
    if r.returncode == 0:
        return
    if _locked(r):
        raise OnePasswordLocked(f"1password_locked: unlock 1Password to delete {item_name(alias)}")
    if not any(m in _tail(r).lower() for m in _ABSENT_MARKERS):
        raise RuntimeError(f"op item delete {item_name(alias)} failed: {_tail(r)}")


def askpass_supported(platform=None):
    """False on Windows, where OpenSSH cannot spawn a script askpass without a shim."""
    return (platform or sys.platform) != "win32"


def askpass_env(ref, platform=None):
    """Environment for an ssh child that prompts through this file's `askpass` entry; the ref, never the value."""
    if not askpass_supported(platform):
        raise RuntimeError("askpass_unsupported: Windows OpenSSH cannot run a script askpass; use mint_key/agent_add")
    me = Path(__file__).resolve()
    try:
        os.chmod(me, os.stat(me).st_mode | 0o111)
    except OSError:
        pass
    return {"SSH_ASKPASS": str(me), "SSH_ASKPASS_REQUIRE": "force", REF_ENV: ref}


def askpass_main(argv, run=subprocess.run, out=None):
    """The askpass entry: print the passphrase for argv[0] or $UNIMATRIX_PASSPHRASE_REF to `out` (stdout)."""
    ref = argv[0] if argv and argv[0].startswith("op://") else os.environ.get(REF_ENV, "")
    if not ref:
        print("askpass: no passphrase ref given", file=sys.stderr)
        return 2
    try:
        value = read_passphrase(ref, run)
    except (RuntimeError, PassphraseSourceMissing) as exc:
        print(f"askpass: {exc}", file=sys.stderr)
        return 1
    (out or sys.stdout).write(value + "\n")
    return 0


# --- key files -------------------------------------------------------------------------------------------

_MAGIC = b"openssh-key-v1\x00"


def _ssh_string(b):
    return struct.pack(">I", len(b)) + b


def is_encrypted(key_path):
    """True when the OpenSSH private key at `key_path` carries a cipher (reads the header; no subprocess)."""
    try:
        text = Path(key_path).read_text(encoding="ascii", errors="replace")
    except OSError:
        return False
    m = re.search(r"-----BEGIN OPENSSH PRIVATE KEY-----(.*?)-----END OPENSSH PRIVATE KEY-----", text, re.S)
    if not m:
        return False
    try:
        raw = base64.b64decode("".join(m.group(1).split()))
    except ValueError:
        return False
    if not raw.startswith(_MAGIC):
        return False
    n = struct.unpack(">I", raw[len(_MAGIC):len(_MAGIC) + 4])[0]
    return raw[len(_MAGIC) + 4:len(_MAGIC) + 4 + n] != b"none"


def mint_key(priv, comment, passphrase):
    """Write a passphrase-encrypted ed25519 key at `priv` and its `.pub`; refuses to overwrite either.
    The passphrase is used in-process only. Returns the public key line. RuntimeError when the file on
    disk does not read back encrypted."""
    from cryptography.hazmat.primitives import serialization as ser
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    if not passphrase:
        raise RuntimeError("mint_key: refusing an empty passphrase")
    priv = Path(priv)
    pub = Path(str(priv) + ".pub")
    if priv.exists() or pub.exists():
        raise RuntimeError(f"mint_key: {priv} already exists; never overwritten")
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(ser.Encoding.PEM, ser.PrivateFormat.OpenSSH,
                            ser.BestAvailableEncryption(passphrase.encode("utf-8")))
    line = key.public_key().public_bytes(ser.Encoding.OpenSSH, ser.PublicFormat.OpenSSH).decode("ascii")
    priv.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(priv, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(pem)
    if sys.platform == "win32":
        subprocess.run(["icacls", str(priv), "/inheritance:r", "/grant:r", f"{os.environ.get('USERNAME', '')}:F"],
                       capture_output=True, timeout=OP_TIMEOUT, creationflags=_no_window())
    if not is_encrypted(priv):
        priv.unlink()
        raise RuntimeError(f"mint_key: {priv} did not read back encrypted")
    line = f"{line} {comment}"
    pub.write_text(line + "\n", encoding="ascii")
    return line


def public_fingerprint(pub_path):
    """`SHA256:<b64>` fingerprint of the first public key line in `pub_path`."""
    body = Path(pub_path).read_text(encoding="ascii").split()[1]
    digest = hashlib.sha256(base64.b64decode(body)).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def agent_add(key_path, passphrase, pipe_open=None):
    """Windows agent load: decrypt in-process and send SSH_AGENTC_ADD_IDENTITY over the OpenSSH agent pipe.
    RuntimeError when the agent refuses (the 1Password agent owning the pipe serves only its own keys)."""
    try:
        from cryptography.hazmat.primitives import serialization as ser
    except ImportError as exc:
        raise RuntimeError(f"loading an encrypted key needs the `cryptography` package ({exc}); run "
                           f"`{sys.executable} -m pip install cryptography`") from exc
    key = ser.load_ssh_private_key(Path(key_path).read_bytes(), passphrase.encode("utf-8"))
    seed = key.private_bytes(ser.Encoding.Raw, ser.PrivateFormat.Raw, ser.NoEncryption())
    pubraw = key.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw)
    pub = Path(str(key_path) + ".pub")
    fields = pub.read_text(encoding="ascii").split(None, 2) if pub.is_file() else []
    comment = fields[2].strip() if len(fields) > 2 else Path(key_path).name
    msg = (b"\x11" + _ssh_string(b"ssh-ed25519") + _ssh_string(pubraw) + _ssh_string(seed + pubraw)
           + _ssh_string(comment.encode("utf-8")))
    opener = pipe_open or (lambda: open(os.environ.get("SSH_AUTH_SOCK") or WINDOWS_AGENT_PIPE, "r+b", buffering=0))
    with opener() as fh:
        fh.write(struct.pack(">I", len(msg)) + msg)
        head = fh.read(4)
        reply = fh.read(struct.unpack(">I", head)[0]) if len(head) == 4 else b""
    if reply[:1] != b"\x06":
        raise RuntimeError("agent refused the identity (a 1Password-owned agent serves only 1Password keys)")


def _in_agent(pub_path, run):
    r = run(["ssh-add", "-l"], capture_output=True, text=True, timeout=OP_TIMEOUT, stdin=subprocess.DEVNULL,
            creationflags=_no_window())
    return r.returncode == 0 and public_fingerprint(pub_path) in (r.stdout or "")


def ensure_agent(key, run=subprocess.run):
    """Make a minted key usable by a BatchMode dial: 'unencrypted' (nothing to load), 'loaded', 'locked'
    (1Password locked; wait) or 'missing' (no op CLI or vault key). The alias is the key file name less `unimatrix-`."""
    key = Path(key)
    if not is_encrypted(key):
        return "unencrypted"
    pub = Path(str(key) + ".pub")
    try:
        if pub.is_file() and _in_agent(pub, run):
            return "loaded"
    except (OSError, subprocess.SubprocessError):
        pass
    alias = key.name[len(ITEM_PREFIX):] if key.name.startswith(ITEM_PREFIX) else key.name
    try:
        ref = op_ref(alias, run)
        passphrase = read_passphrase(ref, run)
    except OnePasswordLocked:
        return "locked"
    except PassphraseSourceMissing:
        return "missing"
    if not askpass_supported():
        agent_add(key, passphrase)
        return "loaded"
    r = run(["ssh-add", str(key)], capture_output=True, text=True, timeout=OP_TIMEOUT, stdin=subprocess.DEVNULL,
            env={**os.environ, **askpass_env(ref)}, creationflags=_no_window())
    if r.returncode:
        raise RuntimeError(f"ssh-add {key} failed: {_tail(r)}")
    return "loaded"


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] == "askpass":
        return askpass_main(argv[1:])
    if os.environ.get(REF_ENV):  # ssh-add runs SSH_ASKPASS as `<file> "<prompt>"`, with no subcommand word
        return askpass_main([])
    print(__doc__)
    return 2


if __name__ == "__main__":
    if any(_a in ("-h", "--help") for _a in sys.argv[1:]):
        print(__doc__)
        raise SystemExit(0)
    sys.exit(main(sys.argv[1:]))
