import logging
import json
import traceback
import threading
import os
from datetime import datetime, timedelta

# Create logs directory if it doesn't exist
LOG_DIR = os.path.join(os.path.expanduser("~"), "PrintQueData", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Configure logging
logger = logging.getLogger('PrintQue')
logger.setLevel(logging.DEBUG)

# Create formatters
detailed_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# File handler for all logs with UTF-8 encoding
file_handler = logging.FileHandler(os.path.join(LOG_DIR, 'printque.log'), encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(detailed_formatter)

# File handler for state changes only with UTF-8 encoding
state_handler = logging.FileHandler(os.path.join(LOG_DIR, 'state_changes.log'), encoding='utf-8')
state_handler.setLevel(logging.INFO)
state_handler.setFormatter(detailed_formatter)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(detailed_formatter)

logger.addHandler(file_handler)
logger.addHandler(state_handler)
logger.addHandler(console_handler)

# =============================================================================
# Dynamic Logging Control
# =============================================================================

# Settings file for persistence
LOGGING_SETTINGS_FILE = os.path.join(os.path.expanduser("~"), "PrintQueData", "logging_settings.json")

# Log level mapping
LOG_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}

# Feature-specific debug flags - these enable verbose logging for specific features
# Can be toggled via API without changing the overall log level
DEBUG_FLAGS = {
    'cooldown': False,      # Cooldown/temperature waiting before ejection
    'ejection': False,      # Ejection process debugging
    'distribution': False,  # Job distribution debugging
    'mqtt': False,          # MQTT/Bambu communication
    'state': False,         # Printer state transitions
    'api': False,           # API request/response debugging
}

# Lock for thread-safe access to debug flags
_debug_flags_lock = threading.Lock()

def _load_logging_settings():
    """Load logging settings from file"""
    try:
        if os.path.exists(LOGGING_SETTINGS_FILE):
            with open(LOGGING_SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                return settings
    except Exception as e:
        print(f"Could not load logging settings: {e}")
    return None

def _save_logging_settings():
    """Save current logging settings to file"""
    try:
        settings = {
            'console_level': get_console_log_level(),
            'debug_flags': get_debug_flags()
        }
        os.makedirs(os.path.dirname(LOGGING_SETTINGS_FILE), exist_ok=True)
        with open(LOGGING_SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        print(f"Could not save logging settings: {e}")

def _apply_saved_settings():
    """Apply saved logging settings on startup"""
    settings = _load_logging_settings()
    if settings:
        # Apply console level
        level = settings.get('console_level', 'INFO')
        if level in LOG_LEVELS:
            console_handler.setLevel(LOG_LEVELS[level])
        
        # Apply debug flags
        saved_flags = settings.get('debug_flags', {})
        with _debug_flags_lock:
            for flag, enabled in saved_flags.items():
                if flag in DEBUG_FLAGS:
                    DEBUG_FLAGS[flag] = enabled

# Apply saved settings on module load
_apply_saved_settings()

def get_console_log_level() -> str:
    """Get current console log level as string"""
    level = console_handler.level
    for name, value in LOG_LEVELS.items():
        if value == level:
            return name
    return 'INFO'

def set_console_log_level(level: str, save: bool = True) -> bool:
    """Set console log level. Returns True if successful."""
    level = level.upper()
    if level not in LOG_LEVELS:
        return False
    
    new_level = LOG_LEVELS[level]
    
    # Update the PrintQue logger's console handler
    console_handler.setLevel(new_level)
    
    # Also update the root logger's StreamHandlers to ensure all console output respects the level
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.setLevel(new_level)
    
    logger.info(f"Console log level changed to {level}")
    if save:
        _save_logging_settings()
    return True

def get_debug_flags() -> dict:
    """Get current debug flags"""
    with _debug_flags_lock:
        return DEBUG_FLAGS.copy()

def set_debug_flag(flag: str, enabled: bool, save: bool = True) -> bool:
    """Set a specific debug flag. Returns True if flag exists."""
    with _debug_flags_lock:
        if flag not in DEBUG_FLAGS:
            return False
        DEBUG_FLAGS[flag] = enabled
        logger.info(f"Debug flag '{flag}' set to {enabled}")
    if save:
        _save_logging_settings()
    return True

def is_debug_enabled(flag: str) -> bool:
    """Check if a specific debug flag is enabled"""
    with _debug_flags_lock:
        return DEBUG_FLAGS.get(flag, False)

def debug_log(flag: str, message: str, level: str = 'debug'):
    """
    Log a message only if the specified debug flag is enabled.
    This allows feature-specific verbose logging without flooding the console.
    
    Args:
        flag: Debug flag name (e.g., 'cooldown', 'ejection')
        message: The message to log
        level: Log level ('debug', 'info', 'warning', 'error')
    """
    if not is_debug_enabled(flag):
        return
    
    prefixed_message = f"[{flag.upper()}] {message}"
    
    if level == 'error':
        logger.error(prefixed_message)
    elif level == 'warning':
        logger.warning(prefixed_message)
    elif level == 'info':
        logger.info(prefixed_message)
    else:
        logger.debug(prefixed_message)

def get_logging_config() -> dict:
    """Get full logging configuration"""
    return {
        'console_level': get_console_log_level(),
        'file_level': 'DEBUG',  # File always captures everything
        'debug_flags': get_debug_flags(),
        'available_levels': list(LOG_LEVELS.keys()),
        'available_flags': list(DEBUG_FLAGS.keys())
    }

def log_state_change(printer_name, old_state, new_state, reason=""):
    """Log printer state changes"""
    # Changed from â†’ to -> for ASCII compatibility
    message = f"PRINTER STATE CHANGE: {printer_name} - {old_state} -> {new_state}"
    if reason:
        message += f" - Reason: {reason}"
    logger.info(message)
    
def log_job_assignment(printer_name, job_name, order_id):
    """Log when jobs are assigned to printers"""
    # Changed from â†’ to -> for ASCII compatibility
    message = f"JOB ASSIGNED: {job_name} -> {printer_name} (Order ID: {order_id})"
    logger.info(message)

def log_error(error_message, printer_name=None):
    """Log errors"""
    if printer_name:
        message = f"ERROR [{printer_name}]: {error_message}"
    else:
        message = f"ERROR: {error_message}"
    logger.error(message)

def log_state_transition(printer_name, old_state, new_state, trigger, details=None):
    """Log detailed printer state transitions with context"""
    transition = {
        "timestamp": datetime.now().isoformat(),
        "printer_name": printer_name,
        "old_state": old_state,
        "new_state": new_state,
        "trigger": trigger,
        "thread": threading.current_thread().name,
        "thread_id": threading.get_ident(),
        "stack_trace": [str(frame) for frame in traceback.extract_stack()[-10:-1]],  # Last 10 frames excluding this one
        "details": details or {}
    }
    
    # Write to JSON file for easy parsing
    transitions_file = os.path.join(LOG_DIR, 'state_transitions.json')
    with open(transitions_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(transition) + '\n')
    
    # Also log to regular log - Changed from â†’ to -> for ASCII compatibility
    message = f"STATE TRANSITION: {printer_name} [{old_state} -> {new_state}] Trigger: {trigger}"
    if details:
        message += f" Details: {details}"
    logger.info(message)

def log_distribution_event(event_type, details):
    """Log distribution-related events"""
    event = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        "thread": threading.current_thread().name,
        "details": details
    }
    
    dist_file = os.path.join(LOG_DIR, 'distribution_events.json')
    with open(dist_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(event) + '\n')
    
    logger.info(f"DISTRIBUTION EVENT: {event_type} - {details}")

def log_job_lifecycle(job_id, printer_name, event, details=None):
    """Log complete job lifecycle events"""
    lifecycle = {
        "timestamp": datetime.now().isoformat(),
        "job_id": job_id,
        "printer_name": printer_name,
        "event": event,
        "details": details or {}
    }
    
    lifecycle_file = os.path.join(LOG_DIR, 'job_lifecycle.json')
    with open(lifecycle_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(lifecycle) + '\n')
    
    logger.info(f"JOB LIFECYCLE: Job {job_id} on {printer_name} - {event}")

def log_manual_action(action, printer_name, user_info=None, details=None):
    """Log manual user actions"""
    manual_action = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "printer_name": printer_name,
        "user_info": user_info or "Unknown",
        "details": details or {}
    }
    
    manual_file = os.path.join(LOG_DIR, 'manual_actions.json')
    with open(manual_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(manual_action) + '\n')
    
    logger.info(f"MANUAL ACTION: {action} on {printer_name} by {user_info or 'Unknown'}")

def log_api_poll_event(printer_name, api_state, stored_state, action, details=None):
    """Log API polling discrepancies and actions"""
    event = {
        "timestamp": datetime.now().isoformat(),
        "printer_name": printer_name,
        "api_state": api_state,
        "stored_state": stored_state,
        "action": action,
        "details": details or {}
    }
    
    api_file = os.path.join(LOG_DIR, 'api_poll_events.json')
    with open(api_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(event) + '\n')
    
    if action != "no_change":
        logger.debug(f"API POLL: {printer_name} - API: {api_state}, Stored: {stored_state}, Action: {action}")

def analyze_printer_history(printer_name, hours=24):
    """Analyze recent history for a specific printer"""
    history = []
    cutoff_time = datetime.now() - timedelta(hours=hours)
    
    # Check all log files
    log_files = ['state_transitions.json', 'distribution_events.json', 
                 'job_lifecycle.json', 'manual_actions.json', 'api_poll_events.json']
    
    for log_file in log_files:
        file_path = os.path.join(LOG_DIR, log_file)
        if not os.path.exists(file_path):
            continue
            
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    event = json.loads(line)
                    event['log_source'] = log_file.replace('.json', '')
                    
                    # Check if this event is related to our printer
                    if ('printer_name' in event and event['printer_name'] == printer_name) or \
                       ('details' in event and isinstance(event.get('details'), dict) and 
                        event['details'].get('printer_name') == printer_name):
                        timestamp = datetime.fromisoformat(event['timestamp'])
                        if timestamp > cutoff_time:
                            history.append(event)
                except Exception as e:
                    logger.debug(f"Error parsing log line from {log_file}: {e}")
                    continue
    
    # Sort by timestamp
    history.sort(key=lambda x: x['timestamp'])
    return history

def get_problem_patterns(hours=24):
    """Identify problematic patterns in the logs"""
    patterns = {
        'unexpected_ready_transitions': [],
        'midnight_distributions': [],
        'manual_flag_cleared': [],
        'rapid_state_changes': []
    }
    
    transitions_file = os.path.join(LOG_DIR, 'state_transitions.json')
    dist_file = os.path.join(LOG_DIR, 'distribution_events.json')
    
    cutoff_time = datetime.now() - timedelta(hours=hours)
    
    # Check state transitions
    if os.path.exists(transitions_file):
        with open(transitions_file, 'r', encoding='utf-8') as f:
            last_transition = {}
            
            for line in f:
                try:
                    event = json.loads(line)
                    timestamp = datetime.fromisoformat(event['timestamp'])
                    
                    if timestamp > cutoff_time:
                        printer_name = event['printer_name']
                        
                        # Check for unexpected READY transitions
                        if event['new_state'] == 'READY' and \
                           event['trigger'] not in ['MANUAL_MARK_READY', 'GROUP_MARK_READY', 'USER_ACTION']:
                            patterns['unexpected_ready_transitions'].append(event)
                        
                        # Check for rapid state changes
                        if printer_name in last_transition:
                            last_time = datetime.fromisoformat(last_transition[printer_name]['timestamp'])
                            if (timestamp - last_time).total_seconds() < 10:
                                patterns['rapid_state_changes'].append({
                                    'printer': printer_name,
                                    'first': last_transition[printer_name],
                                    'second': event,
                                    'interval_seconds': (timestamp - last_time).total_seconds()
                                })
                        
                        last_transition[printer_name] = event
                        
                except Exception as e:
                    logger.debug(f"Error parsing transition: {e}")
                    continue
    
    # Check distribution events
    if os.path.exists(dist_file):
        with open(dist_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    event = json.loads(line)
                    timestamp = datetime.fromisoformat(event['timestamp'])
                    
                    if timestamp > cutoff_time:
                        # Check for midnight distributions
                        if timestamp.hour >= 23 or timestamp.hour <= 1:
                            patterns['midnight_distributions'].append(event)
                            
                except Exception as e:
                    logger.debug(f"Error parsing distribution event: {e}")
                    continue
    
    return patterns

def get_recent_logs(minutes=5):
    """Get console output and logs from the last N minutes"""
    import sys
    
    logs_content = []
    current_time = datetime.now()
    cutoff_time = current_time - timedelta(minutes=minutes)
    
    # Add header
    logs_content.append(f"=== PrintQue Console Output and Logs ===\n")
    logs_content.append(f"Generated: {current_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    logs_content.append(f"Time Range: Last {minutes} minutes\n")
    logs_content.append(f"From: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    logs_content.append(f"To: {current_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    logs_content.append("=" * 70 + "\n\n")
    
    # Get console output
    try:
        from utils.console_capture import console_capture
        
        logs_content.append("=== CONSOLE OUTPUT (Command Prompt) ===\n")
        logs_content.append("=" * 70 + "\n")
        
        console_lines = console_capture.get_recent_output(minutes=minutes)
        
        if console_lines:
            logs_content.append(f"Found {len(console_lines)} console output lines:\n\n")
            for line in console_lines:
                logs_content.append(line)
                if not line.endswith('\n'):
                    logs_content.append('\n')
        else:
            logs_content.append("No console output in the specified time range.\n")
            
            # Show last 100 lines regardless of time
            all_lines = console_capture.get_all_output()
            if all_lines:
                logs_content.append(f"\nShowing last 100 console output lines:\n")
                logs_content.append("-" * 50 + "\n")
                for line in all_lines[-100:]:
                    logs_content.append(line)
                    if not line.endswith('\n'):
                        logs_content.append('\n')
            else:
                logs_content.append("No console output captured yet.\n")
                logs_content.append("\nNote: Console capture might not be started. Make sure console_capture.start() is called.\n")
                
    except ImportError:
        logs_content.append("Console capture module not available.\n")
        logs_content.append("Make sure console_capture.py is in your project directory.\n")
    except Exception as e:
        logs_content.append(f"Error getting console output: {str(e)}\n")
        logs_content.append(f"Error type: {type(e).__name__}\n")
        import traceback
        logs_content.append(f"Traceback: {traceback.format_exc()}\n")
    
    # Also include file logs
    logs_content.append("\n\n=== FILE LOGS ===\n")
    logs_content.append("=" * 70 + "\n\n")
    
    # Read from the main log file
    log_file_path = os.path.join(LOG_DIR, 'printque.log')
    
    if os.path.exists(log_file_path):
        logs_content.append("--- Main Log File ---\n")
        try:
            with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            # Get lines from time range
            recent_lines = []
            for line in lines:
                try:
                    if len(line) >= 19 and line[4] == '-' and line[7] == '-':
                        timestamp_str = line[:19]
                        log_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                        if log_time >= cutoff_time:
                            recent_lines.append(line)
                except:
                    # Include continuation lines of multi-line log entries
                    if recent_lines and not line.startswith('20'):
                        recent_lines.append(line)
            
            if recent_lines:
                logs_content.append(f"Found {len(recent_lines)} log entries:\n")
                logs_content.extend(recent_lines)
            else:
                logs_content.append("No recent entries in main log file.\n")
                # Show last 20 lines anyway
                if lines:
                    logs_content.append("\nShowing last 20 lines from log file:\n")
                    logs_content.extend(lines[-20:])
                
        except Exception as e:
            logs_content.append(f"Error reading log file: {str(e)}\n")
    else:
        logs_content.append("Main log file not found.\n")
    
    # State changes log
    state_log_path = os.path.join(LOG_DIR, 'state_changes.log')
    if os.path.exists(state_log_path):
        logs_content.append("\n--- State Changes Log ---\n")
        try:
            with open(state_log_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            recent_lines = []
            for line in lines:
                try:
                    if len(line) >= 19 and line[4] == '-' and line[7] == '-':
                        timestamp_str = line[:19]
                        log_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                        if log_time >= cutoff_time:
                            recent_lines.append(line)
                except:
                    if recent_lines and not line.startswith('20'):
                        recent_lines.append(line)
            
            if recent_lines:
                logs_content.extend(recent_lines)
            else:
                logs_content.append("No recent state changes.\n")
                
        except Exception as e:
            logs_content.append(f"Error reading state changes log: {str(e)}\n")
    
    # Summary information
    logs_content.append("\n\n=== SYSTEM INFORMATION ===\n")
    logs_content.append("=" * 70 + "\n")
    logs_content.append(f"Log Directory: {LOG_DIR}\n")
    logs_content.append(f"Working Directory: {os.getcwd()}\n")
    logs_content.append(f"Python Version: {sys.version}\n")
    
    # List all log files
    if os.path.exists(LOG_DIR):
        log_files = os.listdir(LOG_DIR)
        logs_content.append(f"\nLog Files in {LOG_DIR}:\n")
        for file in sorted(log_files):
            file_path = os.path.join(LOG_DIR, file)
            if os.path.isfile(file_path):
                size = os.path.getsize(file_path)
                mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                logs_content.append(f"  - {file}: {size:,} bytes (modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')})\n")
    
    return ''.join(logs_content)