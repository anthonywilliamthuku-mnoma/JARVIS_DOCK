"""One place that knows how to reach the Windows Runtime.

Two things live here, both learned the hard way on this PC:

* The monolithic ``winsdk`` package is deprecated in favour of per-namespace
  ``winrt-*`` wheels, and this PC has the new ones. Both expose the same class
  names, so the rest of LEON asks :func:`klass` and never imports either.
* WinRT and ``comtypes`` (which the volume control uses) cannot share an
  apartment tidily. Mixing them on one thread makes a WinRT call hang instead of
  failing, so every WinRT call is run on one dedicated thread that owns its
  apartment, and the answer is handed back.
"""

from __future__ import annotations

import asyncio
import contextlib
import ctypes
import importlib
import queue
import threading
from collections.abc import Callable
from typing import Any

# COINIT_APARTMENTTHREADED is what comtypes uses for pycaw; the WinRT worker
# wants the free-threaded mode, because its async completions are delivered
# without a window message pump.

_JOB: queue.Queue[tuple[Callable[[], Any], dict[str, Any], threading.Event]] = queue.Queue()
_WORKER: threading.Thread | None = None
_WORKER_LOCK = threading.Lock()


def klass(module: str, name: str) -> Any | None:
    """A WinRT class, given its namespace and name, or ``None``."""
    for prefix in ("winrt", "winsdk"):
        try:
            loaded = importlib.import_module(f"{prefix}.{module}")
        except ImportError:
            continue
        found = getattr(loaded, name, None)
        if found is not None:
            return found
    return None


def available() -> bool:
    """Whether Windows media, and therefore the media tile, can work."""
    return (
        klass("windows.media.control", "GlobalSystemMediaTransportControlsSessionManager")
        is not None
    )


def apartment(multithreaded: bool = False) -> None:
    """Give this thread a COM apartment, once. Safe to call repeatedly."""
    ole32 = getattr(getattr(ctypes, "windll", None), "ole32", None)
    if ole32 is None:
        return
    with contextlib.suppress(OSError):  # already initialised in another mode
        ole32.CoInitializeEx(None, 0x0 if multithreaded else 0x2)


def _serve() -> None:
    apartment(multithreaded=True)
    while True:
        work, box, done = _JOB.get()
        try:
            box["value"] = work()
        except BaseException as exc:  # noqa: BLE001 - handed back to the caller
            box["error"] = exc
        finally:
            done.set()


def _ensure_worker() -> None:
    global _WORKER
    with _WORKER_LOCK:
        if _WORKER is not None and _WORKER.is_alive():
            return
        _WORKER = threading.Thread(target=_serve, name="leon-winrt", daemon=True)
        _WORKER.start()


def call(work: Callable[[], Any], timeout: float = 6.0) -> Any:
    """Run one API call on the WinRT thread and return its result."""
    _ensure_worker()
    box: dict[str, Any] = {}
    done = threading.Event()
    _JOB.put((work, box, done))
    if not done.wait(timeout):
        raise TimeoutError("a Windows call did not answer in time")
    if "error" in box:
        raise box["error"]
    return box["value"]


def run_async(make: Callable[[], Any], timeout: float) -> Any:
    """Await one WinRT coroutine on the WinRT thread."""

    async def guarded() -> Any:
        return await asyncio.wait_for(make(), timeout)

    return call(lambda: asyncio.run(guarded()), timeout + 2.0)
