"""
Enhanced error handling wrapper for PrintQue application.
Modified to remove tkinter dependency and work with PyInstaller.

When run from scripts/ (e.g. python scripts/run_app.py), adds api/ to path
and uses api/ for templates/static. Run from repo root.
"""
import os
import sys
import traceback
import time
import logging
import shutil
import atexit
import re
from pathlib import Path

def main():
    # When run from scripts/, ensure api is on path and we use api dir for templates/static
    script_dir = Path(__file__).resolve().parent
    root_dir = script_dir.parent
    api_dir = root_dir / "api"
    if script_dir.name == "scripts":
        sys.path.insert(0, str(api_dir))
        os.chdir(api_dir)

    try:
        # Set up error logging
        error_log_path = os.path.join(os.path.expanduser("~"), "PrintQueData", "flask_error.log")
        os.makedirs(os.path.dirname(error_log_path), exist_ok=True)
        
        error_logger = logging.getLogger('run_app')
        error_logger.setLevel(logging.ERROR)
        handler = logging.FileHandler(error_log_path, mode='a')
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        error_logger.addHandler(handler)
        
        # Set exception hook to catch unhandled exceptions
        def handle_exception(exc_type, exc_value, exc_traceback):
            error_logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
        sys.excepthook = handle_exception
        
        print("Starting PrintQue application...")
        
        # Import everything needed WITHOUT tkinter
        from flask import Flask
        from flask_socketio import SocketIO
        from concurrent.futures import ThreadPoolExecutor
        import asyncio
        import webbrowser
        import threading
        
        # Import our application modules
        from routes import register_routes
        from state import initialize_state
        from printer_manager import start_background_tasks, close_connection_pool
        from config import Config
        from console_capture import console_capture
        
        # Start console capture immediately after import
        console_capture.start()
        print("Console capture started...")
        
        # Set up logging
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
        
        # Initialize the app
        executor = ThreadPoolExecutor(max_workers=20)
        
        # Get the base directory and set up templates
        # When frozen (compiled), use the executable's directory
        if getattr(sys, 'frozen', False):
            base_dir = sys._MEIPASS
        else:
            # When run from scripts/, use api dir for templates/static
            base_dir = str(api_dir) if script_dir.name == "scripts" else os.path.dirname(os.path.abspath(__file__))
            
        template_folder = os.path.join(base_dir, "templates")
        static_folder = os.path.join(base_dir, "static")
        
        # Ensure template directory exists
        os.makedirs(template_folder, exist_ok=True)
        os.makedirs(static_folder, exist_ok=True)
        
        logging.debug(f"Base directory: {base_dir}")
        logging.debug(f"Template folder: {template_folder}")
        logging.debug(f"Static folder: {static_folder}")
        
        app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
        app.config['SECRET_KEY'] = Config.SECRET_KEY
        app.config['UPLOAD_FOLDER'] = os.path.join(LOG_DIR, "uploads")
        socketio = SocketIO(app, async_mode='threading', thread_pool=executor)
        
        # Natural sort function for Jinja2
        def natural_sort(items):
            """Natural sort that handles mixed types and alphanumeric strings"""
            def natural_key(item):
                # Convert to string to handle both int and str types
                text = str(item)
                
                # Split into numeric and non-numeric parts
                parts = []
                for part in re.split(r'(\d+)', text):
                    if part.isdigit():
                        parts.append((0, int(part)))  # Numeric parts
                    elif part:
                        parts.append((1, part.lower()))  # Text parts (case-insensitive)
                
                return parts if parts else [(1, text.lower())]
            
            try:
                return sorted(items, key=natural_key)
            except Exception as e:
                # Fallback to simple string sort if anything goes wrong
                return sorted([str(x) for x in items])
        
        # Register the filter
        app.jinja_env.filters['natural_sort'] = natural_sort
        
        # Initialize state
        initialize_state()
        # Import deduplication functions
        from printer_manager import deduplicate_printers, deduplicate_orders
        
        # First deduplication - clean up any duplicates from saved files
        deduplicate_printers()
        deduplicate_orders()
        
        # Wait a moment for initialization to complete
        import time
        time.sleep(1)
        
        # Second deduplication - catch any runtime duplicates
        deduplicate_printers()
        deduplicate_orders()
        
        # Open Source Edition - all features enabled
        logging.info("PrintQue Open Source Edition - All features enabled")
        
        # Register routes
        register_routes(app, socketio)
        
        # Add favicon route to prevent 404 errors
        @app.route('/favicon.ico')
        def favicon():
            """Return a 204 No Content for favicon requests to prevent 404 errors"""
            return '', 204
        
        # Add logging for debugging template issues
        app.logger.setLevel(logging.DEBUG)
        
        # Add teardown function
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
        
        # Start the application
        start_background_tasks(socketio, app)
        
        # Start browser in a new thread
        threading.Thread(target=open_browser, daemon=True).start()
        
        # Run the Flask app
        print(f"Starting Flask server on port {Config.PORT}...")
        socketio.run(app, host='0.0.0.0', port=Config.PORT, debug=False, allow_unsafe_werkzeug=True)
        
        # If we get here, the server was stopped normally
        print("Server stopped.")
        
    except Exception as e:
        # Log the error to a file
        error_log_path = os.path.join(os.path.expanduser("~"), "PrintQueData", "startup_error.log")
        os.makedirs(os.path.dirname(error_log_path), exist_ok=True)
        
        with open(error_log_path, 'a') as f:
            f.write(f"\n{'='*50}\n")
            f.write(f"ERROR at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Exception: {str(e)}\n")
            f.write(f"Traceback:\n")
            traceback.print_exc(file=f)
            f.write(f"{'='*50}\n")
        
        # Display error message to user
        print("\nApplication Error")
        print("="*40)
        print(f"Error: {str(e)}")
        print("\nThis error has been logged to:")
        print(error_log_path)
        print("\nPlease check this log file for details.")
        print("="*40)
        
        # Only wait for input if not running as a frozen exe
        if not getattr(sys, 'frozen', False):
            # Running as a script, can use input()
            input("\nPress Enter to exit...")
        else:
            # Running as compiled exe, just pause briefly so error can be logged
            time.sleep(2)

if __name__ == "__main__":
    main()
