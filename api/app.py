# Monkey-patch for eventlet - MUST be at the very top before other imports
import eventlet
eventlet.monkey_patch()

import os
import uuid
from flask import Flask, send_from_directory
from flask_socketio import SocketIO
from flask_cors import CORS
from routes import register_routes
from services.state import initialize_state
from services.printer_manager import start_background_tasks, close_connection_pool, get_minutes_since_finished
from utils.config import Config
import asyncio
import logging
from utils.license_validator import verify_license_startup
import webbrowser
import threading
import time
import atexit
from utils.console_capture import console_capture

# Set up logging to a user-writable directory
LOG_DIR = os.path.join(os.getenv('DATA_DIR', os.path.expanduser("~")), "PrintQueData")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "app.log")

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

# Function to open web browser
def open_browser():
    """Open browser after a short delay"""
    time.sleep(3)  # Wait for Flask to start
    try:
        webbrowser.open(f'http://localhost:{Config.PORT}')
        logging.info(f"Opened web browser to http://localhost:{Config.PORT}")
    except Exception as e:
        logging.error(f"Failed to open web browser: {e}")

# Verify license and get license information
def verify_license():
    # Create an empty license.key file if it doesn't exist
    license_path = os.path.join(os.getcwd(), "license.key")
    if not os.path.exists(license_path):
        try:
            with open(license_path, 'w') as f:
                f.write("FREE-0000-0000-0000")
            logging.info("Created default license.key file")
        except Exception as e:
            logging.error(f"Error creating license file: {str(e)}")

    license_info = verify_license_startup()
    logging.info(f"License tier: {license_info['tier']}")
    logging.info(f"Max printers: {license_info['max_printers']}")
    return license_info

# Initialize the app with static and templates folders
static_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
template_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
os.makedirs(static_folder, exist_ok=True)

app = Flask(__name__, static_folder=static_folder, static_url_path='/static', template_folder=template_folder)
app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['APP_VERSION'] = Config.APP_VERSION
app.config['UPLOAD_FOLDER'] = os.path.join(LOG_DIR, "uploads")  # Writable upload folder
app.config['LOG_DIR'] = LOG_DIR

# Enable CORS for React frontend development
CORS(app, resources={
    r"/api/*": {"origins": ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://127.0.0.1:5173"]},
    r"/socket.io/*": {"origins": ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://127.0.0.1:5173"]}
})

socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://127.0.0.1:5173"])

# Initialize state
initialize_state()

# Verify license
license_info = verify_license()
app.config['LICENSE_TIER'] = license_info['tier']
app.config['MAX_PRINTERS'] = license_info['max_printers']
app.config['LICENSE_FEATURES'] = license_info['features']
app.config['LICENSE_VALID'] = license_info['valid']
if 'days_remaining' in license_info:
    app.config['LICENSE_DAYS_REMAINING'] = license_info['days_remaining']

# Register all routes
register_routes(app, socketio)

# Enhanced favicon route with fallback
@app.route('/favicon.ico')
def favicon():
    """Serve favicon with proper caching and fallback"""
    try:
        static_folder_path = app.static_folder or 'static'

        # Try to serve actual favicon.ico first
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

if __name__ == '__main__':
    # Start console capture
    console_capture.start()

    # Start the application without password check
    start_background_tasks(socketio, app)

    # Start browser in a new thread
    threading.Thread(target=open_browser, daemon=True).start()

    # Run the Flask app
    # Added app.config['DEBUG'] for the debug flag
    socketio.run(app, host='0.0.0.0', port=Config.PORT, debug=app.config.get('DEBUG', False))
