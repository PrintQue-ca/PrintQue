"""Native threading primitives safe across eventlet greenlets and real OS threads."""
import threading

_native = None


def native_threading():
    """Return the real ``threading`` module (not eventlet's greenlet-based patch)."""
    global _native
    if _native is not None:
        return _native
    try:
        import eventlet
        _native = eventlet.patcher.original('threading')
    except (ImportError, AttributeError):
        _native = threading
    return _native


def spawn_os_daemon(target, *, name=None):
    """Start a daemon thread on a real OS thread (safe under eventlet)."""
    kwargs = {'target': target, 'daemon': True}
    if name is not None:
        kwargs['name'] = name
    thread = native_threading().Thread(**kwargs)
    thread.start()
    return thread


def os_timer(delay, callback):
    """Schedule *callback* on a real OS thread after *delay* seconds."""
    timer = native_threading().Timer(delay, callback)
    timer.daemon = True
    timer.start()
    return timer


def patch_logging_for_os_threads():
    """Use a native lock for the stdlib logging module.

    Eventlet monkey-patches ``threading``; the logging module's internal lock
  then becomes a greenlet lock. Real OS threads (memory monitor, status poll,
    etc.) call ``logging.info()`` and can crash the hub with
    ``greenlet.error: Cannot switch to a different thread``.
    """
    import logging

    native = native_threading()
    logging._lock = native.RLock()  # noqa: SLF001
    for handler in logging.root.handlers:
        lock = getattr(handler, 'lock', None)
        if lock is not None:
            handler.lock = native.RLock()
