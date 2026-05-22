"""Safe Socket.IO emits from background OS threads."""


def _enrich_status_payload(payload):
    """Add `queue` for clients; keep legacy `orders` when queue data is included."""
    if not isinstance(payload, dict):
        return payload
    out = dict(payload)
    if 'queue' in out:
        if 'orders' not in out:
            out['orders'] = out['queue']
        return out
    if 'orders' in out:
        out['queue'] = out['orders']
    return out


def safe_emit(socketio, app, event, payload, **kwargs):
    """Emit a Socket.IO event with Flask app context (safe from any thread)."""
    with app.app_context():
        socketio.emit(event, payload, **kwargs)


def emit_status_update(socketio, app, payload):
    """Broadcast printer/queue status to connected clients."""
    safe_emit(socketio, app, 'status_update', _enrich_status_payload(payload))
