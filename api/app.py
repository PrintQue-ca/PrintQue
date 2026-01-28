# Monkey-patch for eventlet - MUST be at the very top before other imports
import eventlet
eventlet.monkey_patch()

import os
import sys
import webbrowser
import threading
from flask import Flask, send_from_directory, send_file
from flask_socketio import SocketIO
from flask_cors import CORS
from routes import register_routes
from services.state import initialize_state
from services.printer_manager import start_background_tasks, close_connection_pool
from utils.config import Config
import asyncio
import logging
import time
import atexit
from utils.console_capture import console_capture

# Set up logging to a user-writable directory
LOG_DIR = os.path.join(os.getenv('DATA_DIR', os.path.expanduser("~")), "PrintQueData")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "app.log")

# Import log level configuration from logger module
from utils.logger import get_console_log_level, LOG_LEVELS

# Set up logging with file handler at DEBUG (captures everything) and console at configured level
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Create app's console handler using saved log level
app_console_handler = logging.StreamHandler()
app_console_handler.setLevel(LOG_LEVELS.get(get_console_log_level(), logging.INFO))
app_console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Configure root logger - handlers filter by their own levels
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)  # Allow all through, handlers decide
root_logger.addHandler(file_handler)
root_logger.addHandler(app_console_handler)

# Initialize the app with static and templates folders
# Handle both development and packaged (PyInstaller) environments
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    base_dir = sys._MEIPASS
else:
    # Running as script
    base_dir = os.path.dirname(os.path.abspath(__file__))

static_folder = os.path.join(base_dir, 'static')
template_folder = os.path.join(base_dir, 'templates')
frontend_folder = os.path.join(base_dir, 'frontend_dist')
os.makedirs(static_folder, exist_ok=True)

app = Flask(__name__, static_folder=static_folder, static_url_path='/static', template_folder=template_folder)
app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = os.path.join(LOG_DIR, "uploads")  # Writable upload folder
app.config['LOG_DIR'] = LOG_DIR

# Enable CORS for React frontend development and packaged builds
allowed_origins = [
    "http://localhost:3000", "http://127.0.0.1:3000",
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:5000", "http://127.0.0.1:5000",  # Same-origin for packaged builds
    "*"  # Allow all for packaged single-executable builds
]

CORS(app, resources={
    r"/api/*": {
        "origins": allowed_origins,
        "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"]
    },
    r"/socket.io/*": {
        "origins": allowed_origins
    }
})

socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

# Initialize state
initialize_state()

# Open Source Edition - all features enabled, no limits
logging.info("PrintQue Open Source Edition - All features enabled")

# Register all routes
register_routes(app, socketio)

# ==================== Frontend Serving ====================
# Serve React frontend from frontend_dist folder (for packaged builds)

@app.route('/assets/<path:filename>')
def serve_frontend_assets(filename):
    """Serve frontend asset files (JS, CSS, etc.)"""
    assets_folder = os.path.join(frontend_folder, 'assets')
    if os.path.exists(assets_folder):
        return send_from_directory(assets_folder, filename)
    return '', 404

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    """Serve React frontend - SPA catch-all route"""
    # Skip API routes and socket.io
    if path.startswith('api/') or path.startswith('socket.io'):
        return '', 404

    # Skip static files
    if path.startswith('static/'):
        return send_from_directory(static_folder, path[7:])

    # Check if frontend_dist exists (packaged build)
    if os.path.exists(frontend_folder):
        # Try to serve the exact file first
        file_path = os.path.join(frontend_folder, path)
        if path and os.path.exists(file_path) and os.path.isfile(file_path):
            return send_from_directory(frontend_folder, path)

        # For SPA routing, return the main HTML file
        # TanStack Start uses _shell.html, standard builds use index.html
        for html_file in ['index.html', '_shell.html']:
            html_path = os.path.join(frontend_folder, html_file)
            if os.path.exists(html_path):
                return send_file(html_path)

    # Fallback: Return a simple status page if no frontend is available
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>PrintQue API</title>
        <style>
            body { font-family: system-ui, sans-serif; max-width: 600px; margin: 100px auto; padding: 20px; }
            h1 { color: #2196F3; }
            code { background: #f0f0f0; padding: 2px 6px; border-radius: 4px; }
        </style>
    </head>
    <body>
        <h1>PrintQue API Server</h1>
        <p>The API server is running. Available endpoints:</p>
        <ul>
            <li><code>GET /api/v1/printers</code> - List printers</li>
            <li><code>GET /api/v1/orders</code> - List orders</li>
            <li><code>GET /api/v1/system/stats</code> - System statistics</li>
        </ul>
        <p>For the full web interface, ensure the frontend is built and included.</p>
    </body>
    </html>
    ''', 200

# Enhanced favicon route with fallback
@app.route('/favicon.ico')
def favicon():
    """Serve favicon with proper caching and fallback"""
    try:
        # Try frontend_dist first (built frontend assets)
        frontend_favicon_path = os.path.join(frontend_folder, 'favicon.ico')
        if os.path.exists(frontend_favicon_path):
            response = send_from_directory(
                frontend_folder,
                'favicon.ico',
                mimetype='image/vnd.microsoft.icon'
            )
            response.headers['Cache-Control'] = 'public, max-age=86400'
            return response

        static_folder_path = app.static_folder or 'static'

        # Fallback: Try static folder favicon.ico
        favicon_path = os.path.join(static_folder_path, 'favicon.ico')
        if os.path.exists(favicon_path):
            response = send_from_directory(
                static_folder_path,
                'favicon.ico',
                mimetype='image/vnd.microsoft.icon'
            )
            response.headers['Cache-Control'] = 'public, max-age=86400'
            return response

        # Fallback: Try PNG format
        favicon_png_path = os.path.join(static_folder_path, 'favicon-32x32.png')
        if os.path.exists(favicon_png_path):
            response = send_from_directory(
                static_folder_path,
                'favicon-32x32.png',
                mimetype='image/png'
            )
            response.headers['Cache-Control'] = 'public, max-age=86400'
            return response

        # Final fallback: Generate a PrintQue SVG favicon
        svg_favicon = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="32" height="32" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="grad1" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#2196F3;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#1976D2;stop-opacity:1" />
    </linearGradient>
  </defs>
  <!-- Pin shape background -->
  <path d="M16 2 C22 2 26 6 26 12 C26 16 22 20 16 28 C10 20 6 16 6 12 C6 6 10 2 16 2 Z" fill="url(#grad1)"/>
  <!-- White speech bubble inside -->
  <path d="M12 8 C12 7 13 6 14 6 L20 6 C21 6 22 7 22 8 L22 13 C22 14 21 15 20 15 L17 15 L14 18 L14 15 C13 15 12 14 12 13 Z" fill="white"/>
</svg>'''

        response = app.response_class(
            svg_favicon,
            mimetype='image/svg+xml'
        )
        response.headers['Cache-Control'] = 'public, max-age=3600'
        return response

    except Exception as e:
        logging.error(f"Error serving favicon: {e}")
        return '', 204

@app.teardown_appcontext
def shutdown_session(exception=None):
    """Clean up resources when the app context tears down"""
    # Don't try to close connection pool here - it causes issues
    # Connection pool cleanup should only happen on app shutdown
    pass

def cleanup_on_exit():
    """Clean up resources on application exit"""
    try:
        # Create a new event loop for cleanup
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Run the async cleanup
        loop.run_until_complete(close_connection_pool())
        loop.close()

        logging.info("Cleanup completed successfully")
    except Exception as e:
        logging.error(f"Error during cleanup: {str(e)}")

# Register the cleanup function
atexit.register(cleanup_on_exit)

def find_available_port(start_port: int, max_attempts: int = 10) -> int:
    """Find an available port, starting from start_port and incrementing if taken."""
    import socket

    for attempt in range(max_attempts):
        port = start_port + attempt
        try:
            # Try to bind to the port to check availability
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('0.0.0.0', port))
            sock.close()

            if port != start_port:
                logging.warning(f"Port {start_port} was in use, using port {port} instead")
            return port
        except OSError:
            logging.debug(f"Port {port} is in use, trying next...")
            continue

    raise RuntimeError(f"Could not find available port after {max_attempts} attempts starting from {start_port}")

def open_browser(port: int):
    """Open the default web browser after a short delay"""
    time.sleep(2)  # Wait for server to start
    url = f"http://localhost:{port}"
    try:
        webbrowser.open(url)
        logging.info(f"Opened browser to {url}")
    except Exception as e:
        logging.warning(f"Could not open browser: {e}")

if __name__ == '__main__':
    # Start console capture
    console_capture.start()

    # Find available port (auto-increment if default is taken)
    actual_port = find_available_port(Config.PORT)

    # Start the application without password check
    start_background_tasks(socketio, app)

    # Log server startup message
    logging.info("")
    logging.info("=" * 60)
    logging.info("=" * 60)
    logging.info("")
    logging.info("    ╔═══════════════════════════════════════════════╗")
    logging.info("    ║                                               ║")
    logging.info("    ║      PRINTQUE OPEN SOURCE EDITION             ║")
    logging.info("    ║      All features enabled - No limits         ║")
    logging.info("    ║                                               ║")
    logging.info("    ╚═══════════════════════════════════════════════╝")
    logging.info("")
    logging.info(f"    Server running at: http://localhost:{actual_port}")
    logging.info(f"    Network access:    http://0.0.0.0:{actual_port}")
    logging.info("")
    logging.info("=" * 60)
    logging.info("=" * 60)
    logging.info("")

    # Open browser automatically (only for packaged builds or when explicitly requested)
    if getattr(sys, 'frozen', False) or os.environ.get('OPEN_BROWSER', '').lower() == 'true':
        browser_thread = threading.Thread(target=open_browser, args=(actual_port,), daemon=True)
        browser_thread.start()

    # Run the Flask app
    # Added app.config['DEBUG'] for the debug flag
    socketio.run(app, host='0.0.0.0', port=actual_port, debug=app.config.get('DEBUG', False))
