"""POSIX PTY relay for claude-author --control-socket: implements ``protocol.Relay``.

``spawn`` starts the child on a fresh pty; ``PosixRelay.run`` is the single selectors loop that
relays stdin -> master (``Observers.on_input``) and master -> stdout (``Observers.on_output``),
services fds the supervisor adds through ``register`` and deadlines added through
``call_later``, and returns the child's exit code. No callback may block: a sleep in one
freezes relay and human input.
"""
from __future__ import annotations

import errno
import fcntl
import heapq
import itertools
import os
import pty
import selectors
import signal
import struct
import subprocess
import sys
import termios
import time
import tty
from typing import Callable, Optional

_READ_CHUNK = 65536
_FORWARDED = tuple(s for s in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGHUP", None))
                   if s is not None)


def _winsize(fd: int) -> Optional[bytes]:
    try:
        return fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8)
    except OSError:
        return None


def _write_all(fd: int, data: bytes) -> None:
    """Blocking-safe full write; a non-blocking fd that would block is polled until drained."""
    view = memoryview(data)
    while view:
        try:
            n = os.write(fd, view)
        except BlockingIOError:
            time.sleep(0.001)
            continue
        view = view[n:]


class PosixRelay:
    """A child on a pty. ``write``/``resize``/``alive``/``wait`` satisfy ``protocol.Relay``."""

    def __init__(self, proc: subprocess.Popen, master: int, observers, *,
                 stdin_fd: int, stdout_fd: int) -> None:
        self._proc = proc
        self._master = master
        self._obs = observers
        self._stdin = stdin_fd
        self._stdout = stdout_fd
        self._sel: Optional[selectors.BaseSelector] = None
        self._timers: list = []
        self._seq = itertools.count()
        self._pending: list[tuple[int, Callable[[], None]]] = []
        self._returncode: Optional[int] = None
        self._master_open = True

    # ------------------------------------------------------------ Relay protocol

    def write(self, data: bytes) -> None:
        """Write keystrokes to the child's pty; OSError means the child is gone."""
        if not self._master_open:
            raise OSError(errno.EIO, "pty closed")
        _write_all(self._master, data)

    def resize(self, cols: int, rows: int) -> None:
        if not self._master_open:
            return
        fcntl.ioctl(self._master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def alive(self) -> bool:
        return self._proc.poll() is None

    def wait(self) -> int:
        if self._returncode is None:
            self._returncode = self._proc.wait()
        return self._returncode

    @property
    def pid(self) -> int:
        return self._proc.pid

    # ------------------------------------------------------------ supervisor hooks

    def register(self, fileobj, callback: Callable[[], None]) -> None:
        """Service ``fileobj`` (readable) in the relay loop by calling ``callback()``."""
        if self._sel is None:
            self._pending.append((fileobj, callback))  # type: ignore[arg-type]
        else:
            self._sel.register(fileobj, selectors.EVENT_READ, callback)

    def unregister(self, fileobj) -> None:
        if self._sel is None:
            self._pending = [p for p in self._pending if p[0] is not fileobj]
        else:
            try:
                self._sel.unregister(fileobj)
            except (KeyError, ValueError):
                pass

    def call_later(self, delay_s: float, fn: Callable[[], None]) -> None:
        """Run ``fn`` on the loop thread after ``delay_s``; never holds a lock meanwhile."""
        heapq.heappush(self._timers, (time.monotonic() + delay_s, next(self._seq), fn))

    # ------------------------------------------------------------ the loop

    def run(self) -> int:
        """Relay until the child is gone; restore the terminal; return the exit code."""
        is_tty = os.isatty(self._stdin)
        saved = termios.tcgetattr(self._stdin) if is_tty else None
        wake_r, wake_w = os.pipe()
        os.set_blocking(wake_r, False)
        os.set_blocking(wake_w, False)
        sig_flags = {"winch": False, "term": []}
        old_handlers: dict = {}

        def poke() -> None:
            try:
                os.write(wake_w, b"x")
            except OSError:
                pass

        def on_winch(signum, frame):
            sig_flags["winch"] = True
            poke()

        def on_term(signum, frame):
            sig_flags["term"].append(signum)
            poke()

        sel = selectors.DefaultSelector()
        self._sel = sel
        try:
            if saved is not None:
                tty.setraw(self._stdin)
            self._copy_winsize()
            try:
                old_handlers[signal.SIGWINCH] = signal.signal(signal.SIGWINCH, on_winch)
                for s in _FORWARDED:
                    old_handlers[s] = signal.signal(s, on_term)
            except ValueError:
                pass  # not the main thread: no signal relay
            sel.register(self._master, selectors.EVENT_READ, self._on_master)
            sel.register(wake_r, selectors.EVENT_READ, lambda: os.read(wake_r, 4096))
            if self._stdin_usable():
                sel.register(self._stdin, selectors.EVENT_READ, self._on_stdin)
            for fobj, cb in self._pending:
                sel.register(fobj, selectors.EVENT_READ, cb)
            self._pending = []
            while self._master_open:
                timeout = None
                if self._timers:
                    timeout = max(0.0, self._timers[0][0] - time.monotonic())
                for key, _ in sel.select(timeout):
                    key.data()
                    if not self._master_open:
                        break
                if sig_flags["winch"]:
                    sig_flags["winch"] = False
                    self._copy_winsize()
                while sig_flags["term"]:
                    self._signal_child(sig_flags["term"].pop(0))
                now = time.monotonic()
                while self._timers and self._timers[0][0] <= now:
                    heapq.heappop(self._timers)[2]()
            return self.wait()
        finally:
            for s, h in old_handlers.items():
                try:
                    signal.signal(s, h)
                except (ValueError, TypeError):
                    pass
            self._close_master()
            sel.close()
            self._sel = None
            os.close(wake_r)
            os.close(wake_w)
            if saved is not None:
                termios.tcsetattr(self._stdin, termios.TCSAFLUSH, saved)
            if self._proc.poll() is None:
                self._signal_child(signal.SIGHUP)

    # ------------------------------------------------------------ internals

    def _stdin_usable(self) -> bool:
        try:
            os.fstat(self._stdin)
            return True
        except OSError:
            return False

    def _copy_winsize(self) -> None:
        ws = _winsize(self._stdout) or _winsize(self._stdin)
        if ws is not None and self._master_open:
            try:
                fcntl.ioctl(self._master, termios.TIOCSWINSZ, ws)
            except OSError:
                pass

    def _signal_child(self, signum: int) -> None:
        try:
            os.kill(self._proc.pid, signum)
        except (ProcessLookupError, PermissionError):
            pass

    def _close_master(self) -> None:
        if self._master_open:
            self._master_open = False
            try:
                os.close(self._master)
            except OSError:
                pass

    def _on_stdin(self) -> None:
        try:
            data = os.read(self._stdin, _READ_CHUNK)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            data = b""
        if not data:
            self._sel.unregister(self._stdin)  # type: ignore[union-attr]
            return
        self._obs.on_input(data)
        try:
            _write_all(self._master, data)
        except OSError:
            pass

    def _on_master(self) -> None:
        try:
            data = os.read(self._master, _READ_CHUNK)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            data = b""  # EIO: the child side of the pty is gone
        if not data:
            self._close_master()
            return
        self._obs.on_output(data)
        try:
            _write_all(self._stdout, data)
        except OSError:
            pass


def spawn(argv: list[str], env: dict[str, str], observers, *,
          stdin_fd: Optional[int] = None, stdout_fd: Optional[int] = None) -> PosixRelay:
    """Start ``argv`` on a new pty with exactly ``env``; the child leads a new session whose
    controlling terminal is the pty. Call ``.run()`` to relay."""
    master, slave = pty.openpty()
    try:
        ws = _winsize(sys.stdout.fileno() if stdout_fd is None else stdout_fd)
        if ws is not None:
            fcntl.ioctl(slave, termios.TIOCSWINSZ, ws)

        def _ctty() -> None:
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        proc = subprocess.Popen(  # popup-intentional-last-resort: POSIX-only module (fcntl/pty/termios)
            argv, stdin=slave, stdout=slave, stderr=slave, env=env,
            start_new_session=True, preexec_fn=_ctty, close_fds=True)  # popup-intentional-last-resort — POSIX pty child owns the console, no conhost
    except BaseException:
        os.close(master)
        raise
    finally:
        os.close(slave)
    return PosixRelay(proc, master, observers,
                      stdin_fd=sys.stdin.fileno() if stdin_fd is None else stdin_fd,
                      stdout_fd=sys.stdout.fileno() if stdout_fd is None else stdout_fd)
