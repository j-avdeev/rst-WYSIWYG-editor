"""Background sphinx-build manager: one build at a time per project root.

Runs `python -m sphinx -b html <srcdir> <srcdir>/build/html` — the project's
conventional output location (PRADIS already serves this dir manually), and
the same `build/` name every tree walker in this app already skips. Uses the
backend's own venv (sphinx pinned to the corpus's 8.2.3), so the project's
conf.py and its in-repo `_ext/` extensions load exactly as in production.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

_LOG_TAIL = 60


class BuildManager:
    def __init__(self, srcdir: Path):
        self.srcdir = Path(srcdir)
        self.outdir = self.srcdir / "build" / "html"
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._state = "idle"          # idle | running | succeeded | failed
        self._log: deque[str] = deque(maxlen=_LOG_TAIL)
        self._started_at: float | None = None
        self._finished_at: float | None = None

    def start(self) -> dict:
        with self._lock:
            if self._state == "running":
                return self.status()
            if not (self.srcdir / "conf.py").is_file():
                self._state = "failed"
                self._log.clear()
                self._log.append(f"no conf.py in {self.srcdir} — not a Sphinx source dir")
                return self.status()
            self._state = "running"
            self._log.clear()
            self._started_at = time.time()
            self._finished_at = None
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            return self.status()

    def _run(self) -> None:
        try:
            proc = subprocess.Popen(
                [
                    sys.executable, "-m", "sphinx",
                    "-b", "html",
                    str(self.srcdir), str(self.outdir),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(self.srcdir),
            )
            assert proc.stdout is not None
            for raw_line in proc.stdout:
                self._log.append(raw_line.decode("utf-8", "replace").rstrip())
            returncode = proc.wait()
            with self._lock:
                self._state = "succeeded" if returncode == 0 else "failed"
                self._finished_at = time.time()
        except Exception as exc:  # noqa: BLE001 — must never leave state stuck on running
            with self._lock:
                self._log.append(f"build runner crashed: {exc!r}")
                self._state = "failed"
                self._finished_at = time.time()

    def status(self) -> dict:
        elapsed = None
        if self._started_at is not None:
            elapsed = round((self._finished_at or time.time()) - self._started_at, 1)
        warnings = sum(1 for line in self._log if "WARNING" in line)
        return {
            "state": self._state,
            "elapsed_sec": elapsed,
            "warnings": warnings,
            "log_tail": list(self._log)[-20:],
        }


_managers: dict[str, BuildManager] = {}
_managers_lock = threading.Lock()


def manager_for(srcdir: Path) -> BuildManager:
    key = str(Path(srcdir).resolve())
    with _managers_lock:
        if key not in _managers:
            _managers[key] = BuildManager(Path(key))
        return _managers[key]
