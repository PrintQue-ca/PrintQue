"""Safe Socket.IO emits from background OS threads."""


def safe_emit(socketio, app, event, payload, **kwargs):
    """Emit a Socket.IO event with Flask app context (safe from any thread)."""
    with app.app_context():
        socketio.emit(event, payload, **kwargs)


def emit_status_update(socketio, app, payload):
    """Broadcast printer/order status to connected clients."""
    safe_emit(socketio, app, 'status_update', payload)
