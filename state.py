from datetime import datetime
import json
import os
import threading
import logging
import time
from cryptography.fernet import Fernet
from config import Config
import copy
import uuid
import paho.mqtt.client as mqtt
import re
from flask import current_app, render_template, jsonify, request

# Set up logging
LOG_DIR = os.path.join(os.path.expanduser("~"), "PrintQueData")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "app.log")

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# File paths (moved to writable directory)
USER_DATA_DIR = LOG_DIR  # Use the same directory for consistency
PRINTERS_FILE = os.path.join(LOG_DIR, "printers.json")
TOTAL_FILAMENT_FILE = os.path.join(LOG_DIR, "total_filament.json")
ORDERS_FILE = os.path.join(LOG_DIR, "orders.json")

# Global state variables
PRINTERS = []
TOTAL_FILAMENT_CONSUMPTION = 0
ORDERS = []
_STATE_INITIALIZED = False  # ← ADDED THIS LINE

# Global ejection control
EJECTION_PAUSED = False
EJECTION_PAUSED_FILE = os.path.join(USER_DATA_DIR, "ejection_paused.json")

# Enhanced ejection state tracking
EJECTION_STATES = {}  # Track ejection state per printer
EJECTION_STATES_LOCK = threading.Lock()

# Ejection locks for each printer
EJECTION_LOCKS = {}
EJECTION_LOCKS_LOCK = threading.Lock()

# Task tracking
TASKS = {}

# Transaction tracking for prints
PRINT_TRANSACTIONS = {}

# MQTT clients for Bambu printers
MQTT_CLIENTS = {}

# Load encryption key
key = Config.ENCRYPTION_KEY.encode() if Config.ENCRYPTION_KEY else Fernet.generate_key()
cipher = Fernet(key)

def validate_group_name(group_name):
    """Validate group name - alphanumeric, spaces, hyphens, underscores only"""
    if not group_name or not isinstance(group_name, str):
        return False
    return bool(re.match(r'^[\w\s-]+$', group_name.strip()))

def sanitize_group_name(group_name):
    """Sanitize group name to ensure it's valid"""
    if not group_name:
        return "Default"
    # Convert to string if not already
    group_name = str(group_name).strip()
    # If empty after stripping, return default
    if not group_name:
        return "Default"
    # Remove any characters that aren't alphanumeric, space, hyphen, or underscore
    sanitized = re.sub(r'[^\w\s-]', '', group_name)
    # If nothing left after sanitization, return default
    return sanitized if sanitized else "Default"

# Add Lock Acquisition Order
LOCK_ACQUISITION_ORDER = {
    "order_locks_lock": 1,
    "orders_lock": 2,
    "filament_lock": 3,
    "tasks_lock": 4,
    "printers_rwlock": 5,
    "lock_stats_lock": 6,
    "lock_owners_lock": 7,
    "print_transactions_lock": 8,
    "ejection_states_lock": 9,
    "ejection_locks_lock": 10
}

class NamedLock:
    def __init__(self, name=None):
        self._lock = threading.RLock()
        self.name = name or str(id(self._lock))
        self._owner = None
        self._acquire_time = None
    
    def acquire(self, timeout=None):
        current_thread = threading.get_ident()
        if self._owner == current_thread:
            logging.warning(f"Thread {current_thread} attempting to re-acquire lock {self.name} it already holds")
            return True
            
        if timeout is None:
            result = self._lock.acquire()
        else:
            result = self._lock.acquire(timeout=timeout)
            
        if result:
            self._owner = current_thread
            self._acquire_time = time.time()
        return result
    
    def release(self):
        self._owner = None
        self._acquire_time = None
        return self._lock.release()
    
    def __enter__(self):
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

class SafeLock:
    def __init__(self, lock, timeout=None, name=None):
        self.lock = lock
        
        # Handle common mistake where name is passed as second parameter
        if isinstance(timeout, str):
            # If timeout is a string, assume it's meant to be the name
            if name is None:
                name = timeout
            timeout = None
            
        self.timeout = timeout or Config.SAFE_LOCK_TIMEOUT  # Use config value
        self.name = name or getattr(lock, 'name', str(id(lock)))
        self.start_time = None
        
    def __enter__(self):
        logging.debug(f"Acquiring lock {self.name}")
        self.start_time = time.time()
        self.thread_id = threading.get_ident()
        self.thread_name = threading.current_thread().name
        
        logging.debug(f"Thread {self.thread_name} (ID: {self.thread_id}) is trying to acquire {self.name}")
        
        acquired = self.lock.acquire(timeout=self.timeout)
        
        if not acquired:
            logging.error(f"Lock acquisition timed out for {self.name} after {self.timeout}s")
            if self._attempt_deadlock_recovery():
                acquired = self.lock.acquire(timeout=self.timeout)
                if not acquired:
                    raise TimeoutError(f"Lock acquisition timed out for {self.name} after recovery attempt")
            else:
                raise TimeoutError(f"Lock acquisition timed out for {self.name}")
        
        with lock_owners_lock:
            thread_id = threading.get_ident()
            lock_owners[self.name] = thread_id
        
        duration = time.time() - self.start_time
        if duration > 1.0:
            logging.warning(f"Slow lock acquisition for {self.name}: {duration:.2f}s")
            
        return self
    
    def _attempt_deadlock_recovery(self):
        logging.warning(f"Attempting deadlock recovery for {self.name}")
        try:
            with lock_owners_lock:
                for lock_name, owner_thread_id in lock_owners.items():
                    if owner_thread_id == self.thread_id:
                        logging.critical(f"Thread {self.thread_id} already owns lock {lock_name} while trying to acquire {self.name}")
                
                ownership_info = ", ".join([f"{name}:{tid}" for name, tid in lock_owners.items()])
                logging.warning(f"Current lock ownerships: {ownership_info}")
                
            return check_deadlock()
        except Exception as e:
            logging.error(f"Error during deadlock recovery attempt: {e}")
            return False
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        end_time = time.time()
        duration = end_time - self.start_time
        
        with lock_stats_lock:
            if self.name in lock_stats:
                lock_stats[self.name]["acquire_count"] += 1
                lock_stats[self.name]["total_time"] += duration
                lock_stats[self.name]["max_time"] = max(lock_stats[self.name]["max_time"], duration)
        
        with lock_owners_lock:
            if self.name in lock_owners:
                del lock_owners[self.name]
        
        self.lock.release()
        logging.debug(f"Released lock {self.name} after {duration:.4f}s")
        
        if exc_type:
            logging.error(f"Exception in lock {self.name} context: {exc_type.__name__}: {exc_val}")

class ReadWriteLock:
    def __init__(self, name=None):
        self._read_ready = threading.Condition(threading.Lock())
        self._readers = 0
        self._writers = 0
        self.name = name or str(id(self))
    
    def acquire_read(self, timeout=None):
        with self._read_ready:
            start_time = time.time()
            remaining_timeout = timeout
            
            while self._writers > 0:
                if timeout is not None:
                    if not self._read_ready.wait(timeout=remaining_timeout):
                        return False
                    elapsed = time.time() - start_time
                    remaining_timeout = max(0.1, timeout - elapsed)
                else:
                    self._read_ready.wait()
            
            self._readers += 1
        return True
    
    def release_read(self):
        with self._read_ready:
            self._readers -= 1
            if not self._readers:
                self._read_ready.notify_all()
    
    def acquire_write(self, timeout=None):
        with self._read_ready:
            start_time = time.time()
            remaining_timeout = timeout
            
            while self._writers > 0 or self._readers > 0:
                if timeout is not None:
                    if not self._read_ready.wait(timeout=remaining_timeout):
                        return False
                    elapsed = time.time() - start_time
                    remaining_timeout = max(0.1, timeout - elapsed)
                else:
                    self._read_ready.wait()
            
            self._writers += 1
        return True
    
    def release_write(self):
        with self._read_ready:
            self._writers -= 1
            self._read_ready.notify_all()

class ReadLock:
    def __init__(self, rwlock, timeout=None):
        self.rwlock = rwlock
        self.timeout = timeout or Config.READ_LOCK_TIMEOUT  # Use config value
        self.name = rwlock.name + "_read"
        
    def __enter__(self):
        logging.debug(f"Acquiring read lock {self.name}")
        start_time = time.time()
        
        if not self.rwlock.acquire_read(timeout=self.timeout):
            logging.error(f"Read lock acquisition timed out for {self.name}")
            raise TimeoutError(f"Read lock acquisition timed out for {self.name}")
        
        duration = time.time() - start_time
        if duration > 1.0:
            logging.warning(f"Slow read lock acquisition for {self.name}: {duration:.2f}s")
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.rwlock.release_read()
        logging.debug(f"Released read lock {self.name}")
        
        if exc_type:
            logging.error(f"Exception in read lock {self.name}: {exc_type.__name__}: {exc_val}")

class WriteLock:
    def __init__(self, rwlock, timeout=None):
        self.rwlock = rwlock
        self.timeout = timeout or Config.WRITE_LOCK_TIMEOUT  # Use config value
        self.name = rwlock.name + "_write"
        
    def __enter__(self):
        logging.debug(f"Acquiring write lock {self.name}")
        start_time = time.time()
        
        if not self.rwlock.acquire_write(timeout=self.timeout):
            logging.error(f"Write lock acquisition timed out for {self.name}")
            raise TimeoutError(f"Write lock acquisition timed out for {self.name}")
        
        duration = time.time() - start_time
        if duration > 1.0:
            logging.warning(f"Slow write lock acquisition for {self.name}: {duration:.2f}s")
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.rwlock.release_write()
        logging.debug(f"Released write lock {self.name}")
        
        if exc_type:
            logging.error(f"Exception in write lock {self.name}: {exc_type.__name__}: {exc_val}")

# Lock objects for thread safety
filament_lock = NamedLock("filament_lock")
orders_lock = NamedLock("orders_lock")
printers_rwlock = ReadWriteLock(name="printers_rwlock")
tasks_lock = NamedLock("tasks_lock")
print_transactions_lock = NamedLock("print_transactions_lock")

# Order-specific locks
order_locks = {}
order_locks_lock = NamedLock("order_locks_lock")

# Lock monitoring
lock_stats = {
    "filament_lock": {"acquire_count": 0, "total_time": 0, "max_time": 0},
    "orders_lock": {"acquire_count": 0, "total_time": 0, "max_time": 0},
    "printers_rwlock": {"acquire_count": 0, "total_time": 0, "max_time": 0},
    "tasks_lock": {"acquire_count": 0, "total_time": 0, "max_time": 0},
    "order_locks_lock": {"acquire_count": 0, "total_time": 0, "max_time": 0},
    "print_transactions_lock": {"acquire_count": 0, "total_time": 0, "max_time": 0},
    "ejection_states_lock": {"acquire_count": 0, "total_time": 0, "max_time": 0},
    "ejection_locks_lock": {"acquire_count": 0, "total_time": 0, "max_time": 0}
}
lock_stats_lock = NamedLock("lock_stats_lock")
lock_owners = {}
lock_owners_lock = NamedLock("lock_owners_lock")

def acquire_locks(*locks, timeout=10):
    sorted_locks = sorted(locks, key=lambda x: LOCK_ACQUISITION_ORDER.get(getattr(x, 'name', str(id(x))), 999))
    
    class MultiLock:
        def __enter__(self):
            self.acquired_locks = []
            start_time = time.time()
            remaining_timeout = timeout
            
            for lock in sorted_locks:
                name = getattr(lock, 'name', str(id(lock)))
                logging.debug(f"Acquiring lock {name} as part of group")
                
                if not lock.acquire(timeout=remaining_timeout):
                    for acquired in self.acquired_locks:
                        acquired.release()
                    raise TimeoutError(f"Lock acquisition timed out for {name} in group lock")
                
                self.acquired_locks.append(lock)
                elapsed = time.time() - start_time
                remaining_timeout = max(0.1, timeout - elapsed)
            
            return self
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            for lock in reversed(self.acquired_locks):
                name = getattr(lock, 'name', str(id(lock)))
                lock.release()
                logging.debug(f"Released lock {name} from group")
            
            if exc_type:
                logging.error(f"Exception in multi-lock context: {exc_type.__name__}: {exc_val}")
    
    return MultiLock()

# Enhanced ejection state management functions
def set_printer_ejection_state(printer_name, state, metadata=None):
    """Set ejection state for a specific printer"""
    with EJECTION_STATES_LOCK:
        EJECTION_STATES[printer_name] = {
            'state': state,  # 'none', 'queued', 'in_progress', 'completed'
            'timestamp': time.time(),
            'metadata': metadata or {}
        }
        logging.info(f"Ejection state for {printer_name}: {state}")

def get_printer_ejection_state(printer_name):
    """Get ejection state for a specific printer"""
    with EJECTION_STATES_LOCK:
        return EJECTION_STATES.get(printer_name, {'state': 'none', 'timestamp': 0, 'metadata': {}})

def clear_printer_ejection_state(printer_name):
    """Clear ejection state for a specific printer"""
    with EJECTION_STATES_LOCK:
        if printer_name in EJECTION_STATES:
            del EJECTION_STATES[printer_name]
            logging.info(f"Cleared ejection state for {printer_name}")

def is_ejection_in_progress_enhanced(printer_name):
    """Enhanced check for ejection in progress"""
    state = get_printer_ejection_state(printer_name)
    if state['state'] in ['queued', 'in_progress']:
        # Check for timeout (safety mechanism)
        if time.time() - state['timestamp'] > 1800:  # 30 minutes
            logging.warning(f"Ejection timeout for {printer_name}, clearing state")
            clear_printer_ejection_state(printer_name)
            return False
        return True
    return False

def get_ejection_lock(printer_name):
    """Get or create an ejection lock for a specific printer"""
    with EJECTION_LOCKS_LOCK:
        if printer_name not in EJECTION_LOCKS:
            EJECTION_LOCKS[printer_name] = NamedLock(f"ejection_lock_{printer_name}")
        return EJECTION_LOCKS[printer_name]

def release_ejection_lock(printer_name):
    """Release ejection lock for a specific printer"""
    with EJECTION_LOCKS_LOCK:
        if printer_name in EJECTION_LOCKS:
            try:
                EJECTION_LOCKS[printer_name].release()
                logging.debug(f"Released ejection lock for {printer_name}")
            except Exception as e:
                logging.warning(f"Error releasing ejection lock for {printer_name}: {e}")

def is_ejection_in_progress(printer_name):
    """Check if ejection is currently in progress for a specific printer"""
    ejection_lock = get_ejection_lock(printer_name)
    # Try to acquire lock without blocking - if we can't, ejection is in progress
    acquired = ejection_lock.acquire(timeout=0)
    if acquired:
        ejection_lock.release()
        return False
    return True

def cleanup_all_ejection_states():
    """Clean up all ejection states (call on startup)"""
    with EJECTION_STATES_LOCK:
        EJECTION_STATES.clear()
        logger.info("Cleared all ejection states on startup")

def reset_all_ejection_states():
    """Reset all ejection states - emergency function"""
    with EJECTION_STATES_LOCK:
        cleared_count = len(EJECTION_STATES)
        EJECTION_STATES.clear()
        logging.warning(f"EMERGENCY: Reset {cleared_count} ejection states")
        
    with EJECTION_LOCKS_LOCK:
        released_count = 0
        for printer_name, lock in EJECTION_LOCKS.items():
            try:
                lock.release()
                released_count += 1
            except:
                pass  # Lock may not be acquired
        logging.warning(f"EMERGENCY: Released {released_count} ejection locks")
        
    return cleared_count + released_count

def debug_ejection_system():
    """Debug function to show current ejection system state"""
    print("\n=== EJECTION SYSTEM DEBUG ===")
    
    with EJECTION_STATES_LOCK:
        print(f"Active ejection states: {len(EJECTION_STATES)}")
        for printer_name, state in EJECTION_STATES.items():
            elapsed = time.time() - state['timestamp']
            print(f"  {printer_name}: {state['state']} ({elapsed:.1f}s ago)")
    
    with EJECTION_LOCKS_LOCK:
        print(f"Ejection locks: {len(EJECTION_LOCKS)}")
        for printer_name in EJECTION_LOCKS.keys():
            in_progress = is_ejection_in_progress(printer_name)
            print(f"  {printer_name}: {'LOCKED' if in_progress else 'FREE'}")
    
    print(f"Global ejection paused: {get_ejection_paused()}")
    print("============================\n")

def cleanup_ejection_locks():
    """Clean up unused ejection locks"""
    with EJECTION_LOCKS_LOCK:
        with ReadLock(printers_rwlock):
            active_printer_names = {p['name'] for p in PRINTERS}
            for printer_name in list(EJECTION_LOCKS.keys()):
                if printer_name not in active_printer_names:
                    del EJECTION_LOCKS[printer_name]
                    logging.debug(f"Cleaned up ejection lock for removed printer: {printer_name}")

def encrypt_api_key(api_key):
    return cipher.encrypt(api_key.encode()).decode()

def decrypt_api_key(encrypted_api_key):
    try:
        if not encrypted_api_key:
            logger.warning("Empty API key provided for decryption")
            return None
        return cipher.decrypt(encrypted_api_key.encode()).decode()
    except Exception as e:
        logger.error(f"Decryption failed for API key: {e}")
        return None

def save_data(filename, data):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logger.debug(f"Saved data to {filename}")
    except Exception as e:
        logger.error(f"Failed to save data to {filename}: {str(e)}")

def load_data(filename, default_value):
    bundle_path = os.path.join(os.path.dirname(__file__), os.path.basename(filename))
    path = filename if os.path.exists(filename) else bundle_path
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.debug(f"Loaded data from {path}")
                return data
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Error reading {path}: {e}")
            return default_value
        except Exception as e:
            logger.error(f"Unexpected error loading {path}: {e}")
            return default_value
    logger.debug(f"No {path} found, returning default")
    return default_value

def get_ejection_paused():
    """Get the current ejection paused state"""
    global EJECTION_PAUSED
    return EJECTION_PAUSED

def set_ejection_paused(paused):
    """Set the ejection paused state and save to file"""
    global EJECTION_PAUSED
    EJECTION_PAUSED = paused
    save_data(EJECTION_PAUSED_FILE, EJECTION_PAUSED)
    logger.info(f"Ejection {'paused' if paused else 'resumed'}")

def validate_gcode_file(file):
    if not file:
        return False, "No file uploaded"
    
    filename = file.filename.lower()
    
    # Accept .gcode, .bgcode, .3mf, and .gcode.3mf files
    valid_extensions = ['.gcode', '.bgcode', '.3mf']
    
    # Special handling for .gcode.3mf files
    if filename.endswith('.gcode.3mf'):
        return True, ""
    
    # Check other extensions
    if any(filename.endswith(ext) for ext in valid_extensions):
        return True, ""
    
    return False, "Invalid file format. Accepted formats: .gcode, .bgcode, .3mf, .gcode.3mf"
    
# NEW FUNCTION: Validation for Ejection G-code files
def validate_ejection_file(file):
    """Validate uploaded ejection G-code files"""
    if not file:
        return False, "No file uploaded"

    filename = file.filename.lower()
    # Accept common G-code and text file extensions
    valid_extensions = ['.gcode', '.txt', '.gc', '.nc', '.bgcode']

    if any(filename.endswith(ext) for ext in valid_extensions):
        return True, ""

    return False, "Invalid file format. Please use .gcode, .txt, .gc, .nc, or .bgcode files"


def get_order_lock(order_id):
    with SafeLock(order_locks_lock):
        if order_id not in order_locks:
            lock = NamedLock(f"order_lock_{order_id}")
            order_locks[order_id] = lock
        return order_locks[order_id]

def clean_order_locks():
    with SafeLock(order_locks_lock):
        with SafeLock(orders_lock):
            active_order_ids = {o['id'] for o in ORDERS}
            for order_id in list(order_locks.keys()):
                if order_id not in active_order_ids:
                    del order_locks[order_id]

def save_order_to_history_direct(order):
    """Direct method to save completed order to history when Flask context is not available"""
    try:
        # Use the global LOG_DIR constant
        history_file = os.path.join(LOG_DIR, 'print_history.json')
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(history_file), exist_ok=True)
        
        # Prepare history entry with extra_data
        history_entry = {
            'id': order.get('id'),
            'filename': order.get('filename', 'Unknown'),
            'quantity': order.get('quantity', 0),
            'groups': order.get('groups', order.get('printer_group', ['Unknown'])),
            'filament_g': order.get('filament_g', 0),
            'ejection_enabled': order.get('ejection_enabled', False),
            'source': order.get('source', 'unknown'),
            'extra_data': order.get('extra_data', {}),
            'created_at': order.get('created_at'),
            'completed_at': order.get('completed_at', datetime.now().isoformat()),
            'duration_seconds': None
        }
        
        # Calculate duration if possible
        if 'created_at' in order and 'completed_at' in order:
            try:
                created = datetime.fromisoformat(order['created_at'])
                completed = datetime.fromisoformat(order['completed_at'])
                duration = (completed - created).total_seconds()
                history_entry['duration_seconds'] = duration
            except:
                pass
        
        # Ensure groups is a list
        if isinstance(history_entry['groups'], str):
            history_entry['groups'] = [history_entry['groups']]
        
        # Append to history file
        with open(history_file, 'a') as f:
            f.write(json.dumps(history_entry) + '\n')
            
        logging.info(f"Saved completed order {order.get('id')} to history with {len(history_entry.get('extra_data', {}))} extra fields")
        
    except Exception as e:
        logging.error(f"Error saving order to history directly: {e}")

def increment_order_sent_count(order_id, increment=1):
    """
    Atomically increment the 'sent' count for an order.
    NO LONGER automatically marks as completed when quantity is reached.
    Returns (success, updated_order) tuple.
    """
    with SafeLock(orders_lock):
        start_time = time.time()
        current_thread = threading.current_thread().name
        thread_id = threading.get_ident()
        logging.debug(f"Thread {current_thread} (ID: {thread_id}) beginning increment_order_sent_count for order {order_id}")
        
        # Copy the current orders list for verification purposes
        orders_before = copy.deepcopy(ORDERS)
        
        for i, order in enumerate(ORDERS):
            if order['id'] == order_id:
                previous_sent = order['sent']
                
                # Additional check to prevent over-counting - but don't stop incrementing
                if previous_sent >= order['quantity']:
                    logging.info(f"Order {order_id} has sent count {previous_sent} >= quantity {order['quantity']}, but still incrementing as requested")
                
                # Verify no other thread has modified this order since we started the function
                if i < len(orders_before) and orders_before[i]['id'] == order_id and orders_before[i]['sent'] != previous_sent:
                    logging.warning(f"Order {order_id} sent count changed during processing from {orders_before[i]['sent']} to {previous_sent}, not incrementing")
                    return False, ORDERS[i].copy()
                
                # Increment without capping at quantity - allow over-fulfillment
                order['sent'] = previous_sent + increment
                
                # Update status to show fulfillment progress but DON'T mark as completed
                if order['sent'] >= order['quantity']:
                    # Change status to 'fulfilled' instead of 'completed' to keep it visible
                    order['status'] = 'fulfilled'
                    # Still add completed_at timestamp for history tracking
                    if 'completed_at' not in order:
                        order['completed_at'] = datetime.now().isoformat()
                    logging.info(f"Order {order_id} fulfilled (sent={order['sent']}, quantity={order['quantity']}) but keeping in active orders")
                elif order['sent'] > 0:
                    order['status'] = 'partial'
                
                save_data(ORDERS_FILE, ORDERS)
                logging.debug(f"Saved ORDERS_FILE after increment for order {order_id} to {order['sent']}")
                
                # Save to history when order reaches or exceeds quantity
                if order['sent'] >= order['quantity']:
                    try:
                        # Try to call the save_completed_order_to_history function if it exists
                        if hasattr(current_app, 'save_completed_order_to_history'):
                            current_app.save_completed_order_to_history(ORDERS[i])
                            logging.info(f"Saved fulfilled order {order_id} to history via Flask app")
                        else:
                            # Flask app exists but function not attached
                            logging.debug("Flask app found but save_completed_order_to_history not available, using direct method")
                            save_order_to_history_direct(ORDERS[i])
                    except RuntimeError as e:
                        # Specifically catch "working outside of application context" error
                        if "application context" in str(e):
                            logging.debug("Not in Flask context, saving directly")
                        else:
                            logging.debug(f"Flask runtime error, saving directly: {e}")
                        save_order_to_history_direct(ORDERS[i])
                    except Exception as e:
                        # Other errors
                        logging.debug(f"Could not use Flask app function, saving directly: {e}")
                        save_order_to_history_direct(ORDERS[i])
                
                elapsed = time.time() - start_time
                logging.debug(f"Thread {current_thread} completed order {order_id} increment operation in {elapsed:.4f}s (new sent={order['sent']})")
                return True, ORDERS[i].copy()
        
        logging.error(f"Failed to increment order {order_id}: order not found in {len(ORDERS)} orders")
        return False, None

def _do_reset_order_counts():
    """Internal function to do the actual reset work"""
    corrections = 0
    for order in ORDERS:
        if 'sent' in order and 'quantity' in order and order['sent'] > order['quantity']:
            logging.warning(f"Fixing order {order.get('id', 'unknown')} with sent count {order['sent']} > quantity {order['quantity']}")
            order['sent'] = order['quantity']
            if 'status' in order:
                order['status'] = 'completed'
            corrections += 1
    
    if corrections > 0:
        save_data(ORDERS_FILE, ORDERS)
        logging.info(f"Fixed {corrections} orders with excessive sent counts")
    
    return corrections

def reset_order_counts(inside_lock=False):
    """Reset order counts that exceed their quantity"""
    corrections = 0
    try:
        # Only acquire the lock if we're not already inside a lock
        if not inside_lock:
            with SafeLock(orders_lock):
                return _do_reset_order_counts()
        else:
            # We're already inside a lock, just do the work
            return _do_reset_order_counts()
    except Exception as e:
        logging.error(f"Error in reset_order_counts: {str(e)}")
        return 0

def create_print_transaction(order_id, printer_name):
    """Create a transaction record for tracking a print job"""
    transaction_id = str(uuid.uuid4())
    with SafeLock(print_transactions_lock):
        PRINT_TRANSACTIONS[transaction_id] = {
            'id': transaction_id,
            'order_id': order_id,
            'printer_name': printer_name,
            'start_time': time.time(),
            'status': 'pending',
            'verification_attempts': 0,
            'verification_success': False
        }
    return transaction_id

def update_print_transaction(transaction_id, status, verification_success=None):
    """Update the status of a print transaction"""
    with SafeLock(print_transactions_lock):
        if transaction_id in PRINT_TRANSACTIONS:
            PRINT_TRANSACTIONS[transaction_id]['status'] = status
            if verification_success is not None:
                PRINT_TRANSACTIONS[transaction_id]['verification_success'] = verification_success
            PRINT_TRANSACTIONS[transaction_id]['verification_attempts'] += 1
            PRINT_TRANSACTIONS[transaction_id]['last_update'] = time.time()
            return True
    return False

def get_print_transaction(transaction_id):
    """Get a print transaction record"""
    with SafeLock(print_transactions_lock):
        return PRINT_TRANSACTIONS.get(transaction_id, {}).copy()

def get_pending_transactions():
    """Get all pending print transactions that haven't been confirmed"""
    with SafeLock(print_transactions_lock):
        return {tid: tx.copy() for tid, tx in PRINT_TRANSACTIONS.items() 
                if tx['status'] in ['pending', 'verifying'] and 
                time.time() - tx['start_time'] < 3600}  # Only consider transactions from the last hour

def reconcile_order_counts():
    """
    Reconcile order counts with actual printer status
    Only increases counts when necessary and ensures they never exceed the quantity
    """
    changed_orders = []
    corrections = 0
    
    # Get all active orders
    with SafeLock(orders_lock):
        active_orders = [o for o in ORDERS if o['status'] != 'completed']
        if not active_orders:
            logging.debug("No active orders to reconcile")
            return 0, []
    
    # Get all printers
    with ReadLock(printers_rwlock):
        all_printers = copy.deepcopy(PRINTERS)
    
    # Build a map of what's actually printing
    order_print_count = {}
    for printer in all_printers:
        order_id = printer.get('order_id')
        if order_id and printer['state'] in ['PRINTING', 'PAUSED'] and 'file' in printer and printer['file']:
            if order_id not in order_print_count:
                order_print_count[order_id] = 0
            order_print_count[order_id] += 1
    
    # Compare with the recorded sent counts
    with SafeLock(orders_lock):
        for order in ORDERS:
            if order['id'] in order_print_count:
                actual_count = order_print_count[order['id']]
                max_count = order['quantity']
                
                # Only increase count if necessary and never exceed the quantity
                if order['sent'] < actual_count and actual_count <= max_count:
                    old_count = order['sent']
                    order['sent'] = actual_count
                    logging.warning(f"Order {order['id']} has sent count {old_count} but {actual_count} actual prints found. Increasing count.")
                    corrections += 1
                    changed_orders.append(order['id'])
                elif actual_count > max_count:
                    logging.error(f"Order {order['id']} has {actual_count} actual prints but quantity is only {max_count}. This suggests a synchronization issue.")
        
        if corrections > 0:
            save_data(ORDERS_FILE, ORDERS)
            logging.info(f"Corrected {corrections} order counts during reconciliation")
    
    return corrections, changed_orders

def check_deadlock():
    with SafeLock(lock_owners_lock):
        threads_waiting = {}
        current_thread_id = threading.get_ident()
        
        for thread_id, thread in threading._active.items():
            for lock_name, owner_id in lock_owners.items():
                if owner_id != thread_id:
                    if thread_id not in threads_waiting:
                        threads_waiting[thread_id] = set()
                    threads_waiting[thread_id].add(lock_name)
        
        for thread_id, waiting_for in threads_waiting.items():
            cycle = detect_cycle(thread_id, threads_waiting)
            if cycle:
                cycle_str = " -> ".join(str(t) for t in cycle)
                logging.critical(f"Potential deadlock detected! Thread chain: {cycle_str}")
                
                if current_thread_id in cycle:
                    logging.critical(f"Current thread {current_thread_id} is in a deadlock. Will attempt recovery.")
                    
                    owned_locks = []
                    for lock_name, owner_id in lock_owners.items():
                        if owner_id == current_thread_id:
                            owned_locks.append(lock_name)
                    
                    if owned_locks:
                        logging.warning(f"Thread {current_thread_id} owns these locks: {owned_locks}")
                
                return True
    return False

def detect_cycle(start, graph, visited=None, path=None):
    if visited is None:
        visited = set()
    if path is None:
        path = []
    
    visited.add(start)
    path.append(start)
    
    if start in graph:
        for node in graph[start]:
            if node not in visited:
                if detect_cycle(node, graph, visited, path):
                    return path
            elif node in path:
                path.append(node)
                return path
    
    path.pop()
    return None

def emergency_lock_reset():
    global lock_owners, lock_stats
    
    logging.critical("EMERGENCY: Resetting all locks due to deadlock")
    
    with lock_owners_lock:
        lock_owners.clear()
    
    with lock_stats_lock:
        for lock_data in lock_stats.values():
            lock_data["acquire_count"] = 0
            lock_data["total_time"] = 0
            lock_data["max_time"] = 0
    
    logging.critical(f"Active thread count: {threading.active_count()}")
    
    return True

def monitor_locks():
    while True:
        try:
            time.sleep(60)
            stats_to_report = []
            with lock_stats_lock:
                for lock_name, data in lock_stats.items():
                    if data["acquire_count"] > 0:
                        avg_time = data["total_time"] / data["acquire_count"]
                        stats_to_report.append(f"{lock_name}: count={data['acquire_count']}, avg={avg_time:.4f}s, max={data['max_time']:.4f}s")
                
                if stats_to_report:
                    for lock_data in lock_stats.values():
                        lock_data["acquire_count"] = 0
                        lock_data["total_time"] = 0
                        lock_data["max_time"] = 0
            
            if stats_to_report:
                logging.info(f"Lock statistics: {', '.join(stats_to_report)}")
        except Exception as e:
            logging.error(f"Error in lock monitoring: {str(e)}")
            time.sleep(60)

def monitor_memory_usage():
    import os
    try:
        import psutil
        process = psutil.Process(os.getpid())
        
        while True:
            try:
                memory_info = process.memory_info()
                memory_mb = memory_info.rss / (1024 * 1024)
                
                logging.info(f"Memory usage: {memory_mb:.2f} MB")
                
                if memory_mb > 500:
                    logging.warning(f"High memory usage detected: {memory_mb:.2f} MB")
                    
                time.sleep(300)
            except Exception as e:
                logging.error(f"Error monitoring memory: {e}")
                time.sleep(300)
    except ImportError:
        logging.warning("psutil not installed, memory monitoring disabled")

def reap_threads():
    while True:
        try:
            active_count = threading.active_count()
            logging.debug(f"Active thread count: {active_count}")
            
            clean_order_locks()
            cleanup_ejection_locks()  # Clean up ejection locks too
            
            time.sleep(60)
        except Exception as e:
            logging.error(f"Error in thread reaper: {e}")
            time.sleep(60)

def initialize_state():
    """Initialize application state from disk"""
    global PRINTERS, ORDERS, TOTAL_FILAMENT_CONSUMPTION, EJECTION_PAUSED, _STATE_INITIALIZED        # CRITICAL: Prevent re-initialization to avoid duplicates
    if _STATE_INITIALIZED:
        logging.warning("⚠️ BLOCKED RE-INITIALIZATION - State already loaded. This prevents duplicates.")
        return        
    logging.info("🔄 Initializing state for the first time...")
    
    with SafeLock(filament_lock):
        filament_data = load_data(TOTAL_FILAMENT_FILE, {"total_filament_used_g": 0})
        TOTAL_FILAMENT_CONSUMPTION = filament_data.get("total_filament_used_g", 0)
    
    with SafeLock(orders_lock):
        ORDERS.extend(load_data(ORDERS_FILE, []))
        for order in ORDERS:
            # Handle groups - keep them flexible (can be strings or integers)
            if 'groups' in order:
                processed_groups = []
                for g in order['groups']:
                    try:
                        # Try to convert to int if it's a numeric string
                        processed_groups.append(int(g))
                    except (ValueError, TypeError):
                        # Keep string groups as-is
                        logger.warning(f"Order {order.get('id', 'unknown')} has non-numeric group: {g}")
                        processed_groups.append(g)
                order['groups'] = processed_groups
            
            if 'sent' not in order:
                order['sent'] = 0
            if 'status' not in order:
                order['status'] = 'pending'
            if 'filament_g' not in order:
                order['filament_g'] = 0
            if 'deleted' not in order:
                order['deleted'] = False
        
        # Fix any incorrect order counts - pass True to indicate we're already inside the lock
        try:
            reset_order_counts(inside_lock=True)
        except Exception as e:
            logging.error(f"Error in reset_order_counts during initialization: {str(e)}")
    
    with WriteLock(printers_rwlock):
        PRINTERS.extend(load_data(PRINTERS_FILE, []))
        for printer in PRINTERS:
            # Handle group - keep it flexible (can be string or integer)
            if 'group' in printer:
                group_value = printer['group']
                # Only try to convert if it's a string that looks like a number
                if isinstance(group_value, str) and group_value.isdigit():
                    try:
                        printer['group'] = int(group_value)
                    except ValueError:
                        # Keep the string value
                        logger.warning(f"Printer {printer.get('name', 'unknown')} has non-numeric group: {group_value}")
                # If it's already an int or a non-numeric string, leave it as-is
                
            if 'filament_used_g' not in printer:
                printer['filament_used_g'] = 0
            if 'service_mode' not in printer:
                printer['service_mode'] = False
            if 'temps' not in printer:
                printer['temps'] = {"nozzle": 0, "bed": 0}
    
    # Load ejection paused state
    EJECTION_PAUSED = load_data(EJECTION_PAUSED_FILE, False)
    
    # Clean up all ejection states on startup
    cleanup_all_ejection_states()
    
    # Emergency reset on startup
    reset_all_ejection_states()
    
    logger.debug(f"State initialized: {len(PRINTERS)} printers, {len(ORDERS)} orders, {TOTAL_FILAMENT_CONSUMPTION}g filament, ejection_paused={EJECTION_PAUSED}")
    
    # Initialize Bambu connections
    from bambu_handler import connect_bambu_printer
    for printer in PRINTERS:
        if printer.get('type') == 'bambu':
            try:
                connect_bambu_printer(printer)
            except Exception as e:
                logger.error(f"Failed to connect Bambu printer {printer['name']} during initialization: {str(e)}")
    
    # Mark state as initialized to prevent duplicates
    _STATE_INITIALIZED = True
    logging.info("✅ State initialization complete - locked to prevent re-initialization")

def register_task(task_id, task_type, total):
    with SafeLock(tasks_lock):
        TASKS[task_id] = {
            'id': task_id,
            'type': task_type,
            'total': total,
            'completed': 0,
            'progress': 0,
            'status': 'running',
            'start_time': time.time(),
            'end_time': None
        }
    return TASKS[task_id]

def update_task_progress(task_id, completed=None, increment=None, message=None):
    with SafeLock(tasks_lock):
        if task_id not in TASKS:
            return None
        
        task = TASKS[task_id]
        if completed is not None:
            task['completed'] = completed
        elif increment is not None:
            task['completed'] += increment
        
        task['progress'] = int((task['completed'] / task['total']) * 100) if task['total'] > 0 else 0
        
        if message:
            task['message'] = message
            
        return task.copy()

def complete_task(task_id, success=True, message=None):
    with SafeLock(tasks_lock):
        if task_id not in TASKS:
            return None
        
        task = TASKS[task_id]
        task['status'] = 'success' if success else 'failed'
        task['end_time'] = time.time()
        task['progress'] = 100 if success else task['progress']
        
        if message:
            task['message'] = message
            
        return task.copy()

def validate_ejection_system():
    """Validate ejection system configuration"""
    issues = []
    
    # Check if Config is properly loaded
    try:
        timeout_config = Config.get_ejection_config()
        if timeout_config['timeout_minutes'] < 5:
            issues.append("Ejection timeout should be at least 5 minutes")
    except Exception as e:
        issues.append(f"Config validation failed: {e}")
    
    # Check ejection states
    with EJECTION_STATES_LOCK:
        active_ejections = len([s for s in EJECTION_STATES.values() if s['state'] in ['queued', 'in_progress']])
        if active_ejections > 0:
            issues.append(f"Found {active_ejections} active ejections on startup")
    
    return issues

# Start background threads
threading.Thread(target=monitor_locks, daemon=True).start()
try:
    import psutil
    threading.Thread(target=monitor_memory_usage, daemon=True).start()
    logging.info("Memory monitoring started")
except ImportError:
    logging.warning("psutil not installed, memory monitoring disabled")
threading.Thread(target=reap_threads, daemon=True).start()

def cleanup_mqtt_connections():
    """Clean up MQTT connections on shutdown"""
    from bambu_handler import disconnect_all_bambu_printers
    try:
        disconnect_all_bambu_printers()
    except Exception as e:
        logger.error(f"Error cleaning up MQTT connections: {str(e)}")

# Validate ejection system on startup
if __name__ != "__main__":
    ejection_issues = validate_ejection_system()
    if ejection_issues:
        print("Ejection system validation issues:")
        for issue in ejection_issues:
            print(f"  - {issue}")