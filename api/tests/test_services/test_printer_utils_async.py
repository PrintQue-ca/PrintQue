"""Tests for async helpers on real OS threads."""

import asyncio
import threading

async def _return_value():
    await asyncio.sleep(0)
    return 'ok'


def test_run_async_in_thread_runs_coroutine():
    from services.printer_utils import run_async_in_thread

    assert run_async_in_thread(_return_value()) == 'ok'


def test_spawn_os_thread_uses_real_thread():
    from services.printer_utils import spawn_os_thread

    main_ident = threading.get_ident()
    seen = {}

    def worker():
        seen['ident'] = threading.get_ident()

    spawn_os_thread(worker, daemon=True, name='test-os-thread').join(timeout=5)
    assert seen.get('ident') is not None
    assert seen['ident'] != main_ident


def test_run_async_in_thread_from_os_worker_with_lock():
    from services.printer_utils import run_async_in_thread, spawn_os_thread
    from services.state import SafeLock, orders_lock

    result = {}

    def worker():
        with SafeLock(orders_lock):
            result['value'] = run_async_in_thread(_return_value())

    spawn_os_thread(worker, daemon=True, name='async-worker').join(timeout=5)
    assert result.get('value') == 'ok'
