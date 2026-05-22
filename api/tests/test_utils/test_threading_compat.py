"""Tests for native threading helpers."""

import logging

from utils.threading_compat import patch_logging_for_os_threads
from utils.threading_compat import native_threading
from services.printer_utils import spawn_os_thread


def test_patch_logging_for_os_threads():
    patch_logging_for_os_threads()
    assert type(logging._lock).__name__ in ('RLock', '_RLock')


def test_native_semaphore_across_os_threads():
    sem = native_threading().Semaphore(1)
    seen = {}

    def worker():
        sem.acquire(blocking=True, timeout=1)
        seen['ok'] = True
        sem.release()

    spawn_os_thread(worker, daemon=True, name='sem-worker').join(timeout=5)
    assert seen.get('ok') is True
