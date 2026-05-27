from datetime import datetime
import importlib.util
import json
import os
import shutil
import tempfile
import threading
import logging
import time
from cryptography.fernet import Fernet
from utils.config import Config
from utils.paths import (
    LazyPath,
    get_data_dir,
    get_ejection_codes_file,
    get_ejection_paused_file,
    get_library_file,
    get_log_file,
    get_orders_file,
    get_printers_file,
    get_print_history_file,
    get_queue_file,
    get_total_filament_file,
    get_user_home_printque_dir,
    get_backups_dir,
)
from services.library_queue import (
    migrate_orders_to_library_and_queue,
    normalize_library_item,
    normalize_queue_job,
)
from services.filename_matching import match_shortened_filename
import copy
import uuid
import re
from flask import current_app
from utils.threading_compat import native_threading, spawn_os_daemon

_threading = native_threading()

# Lazy paths — resolved on each use so DATA_DIR / test isolation stays correct
LOG_DIR = LazyPath(get_data_dir)
LOG_FILE = LazyPath(get_log_file)
USER_DATA_DIR = LOG_DIR
PRINTERS_FILE = LazyPath(get_printers_file)
TOTAL_FILAMENT_FILE = LazyPath(get_total_filament_file)
ORDERS_FILE = LazyPath(get_orders_file)
LIBRARY_FILE = LazyPath(get_library_file)
QUEUE_FILE = LazyPath(get_queue_file)
EJECTION_CODES_FILE = LazyPath(get_ejection_codes_file)

# Note: Main logging configuration is done in app.py to support dynamic log levels
logger = logging.getLogger(__name__)

# Global state variables
PRINTERS = []
TOTAL_FILAMENT_CONSUMPTION = 0
LIBRARY_ITEMS = []
QUEUE_JOBS = []
ORDERS = QUEUE_JOBS  # Backward-compatible alias for print queue
EJECTION_CODES = []  # List of stored ejection code presets
_STATE_INITIALIZED = False  # ← ADDED THIS LINE

# Global ejection control
EJECTION_PAUSED = False
EJECTION_PAUSED_FILE = LazyPath(get_ejection_paused_file)

# Enhanced ejection state tracking
EJECTION_STATES = {}  # Track ejection state per printer
EJECTION_STATES_LOCK = _threading.Lock()

# Ejection locks for each printer
EJECTION_LOCKS = {}
EJECTION_LOCKS_LOCK = _threading.Lock()

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
    "ejection_locks_lock": 10,
    "ejection_codes_lock": 11
}

class NamedLock:
    def __init__(self, name=None):
        self._lock = _threading.RLock()
        self.name = name or str(id(self._lock))
        self._owner = None
        self._acquire_time = None

    def acquire(self, timeout=None):
        current_thread = _threading.get_ident()
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
        self.thread_id = _threading.get_ident()
        self.thread_name = _threading.current_thread().name

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
            thread_id = _threading.get_ident()
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
        self._read_ready = _threading.Condition(_threading.Lock())
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
ejection_codes_lock = NamedLock("ejection_codes_lock")

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
    "ejection_locks_lock": {"acquire_count": 0, "total_time": 0, "max_time": 0},
    "ejection_codes_lock": {"acquire_count": 0, "total_time": 0, "max_time": 0}
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
            except Exception:
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
        logger.error(
            "Decryption failed for API key: %s. "
            "If you reset data or use a different machine, re-enter the printer access code in the Printers settings.",
            e,
        )
        return None

def _resolve_path(filename) -> str:
    return os.fspath(filename)


def _is_printers_path(path: str) -> bool:
    printers_path = os.path.normcase(os.path.realpath(os.fspath(PRINTERS_FILE)))
    path_norm = os.path.normcase(os.path.realpath(path))
    return path_norm == printers_path


def _printers_backup_path(path: str) -> str:
    return f"{path}.bak"


def _load_json_file(path: str):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _atomic_write_json(path: str, data) -> None:
    directory = os.path.dirname(path) or '.'
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{os.path.basename(path)}.",
        suffix=".tmp",
        dir=directory,
        text=True,
    )
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _backup_valid_json(path: str, backup_path: str) -> bool:
    if not os.path.exists(path):
        return False
    try:
        _load_json_file(path)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        logger.warning("Skipping backup for invalid JSON file %s: %s", path, e)
        return False
    shutil.copy2(path, backup_path)
    return True


def _assert_safe_write_path(filename) -> None:
    """Block pytest from writing to real ~/PrintQueData if paths were bound too early."""
    if not os.environ.get('PYTEST_CURRENT_TEST'):
        return
    path = _resolve_path(filename)
    try:
        real_home = os.path.normcase(os.path.realpath(get_user_home_printque_dir()))
        path_norm = os.path.normcase(os.path.realpath(path))
        data_norm = os.path.normcase(os.path.realpath(get_data_dir()))
    except OSError:
        return
    if path_norm.startswith(real_home) and not path_norm.startswith(data_norm):
        raise RuntimeError(
            f"Refusing to write {path} during tests: path is under real user data "
            f"({real_home}) but tests must only write under {data_norm}. "
            f"Ensure DATA_DIR is set in api/tests/conftest.py before importing services.state."
        )


def backup_data_files_before_migration(*filenames: str) -> str | None:
    """Copy data files to PrintQueData/backups/{timestamp}/ before a migration write."""
    if not filenames:
        return None
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = os.path.join(get_backups_dir(), f'migration_{stamp}')
    os.makedirs(backup_dir, exist_ok=True)
    data_dir = get_data_dir()
    for name in filenames:
        src = os.path.join(data_dir, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(backup_dir, name))
    logging.info("Pre-migration backup saved to %s", backup_dir)
    return backup_dir


def _should_skip_empty_printers_save(path: str, data) -> bool:
    """Refuse to overwrite a populated printers.json with an empty list."""
    if not _is_printers_path(path):
        return False
    if data != []:
        return False
    if not os.path.exists(path):
        return False
    try:
        with open(path, encoding='utf-8') as f:
            existing = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not read existing printers file %s: %s", path, e)
        return False
    if isinstance(existing, list) and len(existing) > 0:
        logger.error(
            "Refusing to save empty printers list over %d existing printer(s) in %s",
            len(existing),
            path,
        )
        return True
    return False


def save_data(filename, data, *, allow_empty_printers=False):
    _assert_safe_write_path(filename)
    path = _resolve_path(filename)
    if not allow_empty_printers and _should_skip_empty_printers_save(path, data):
        return
    try:
        if _is_printers_path(path):
            _backup_valid_json(path, _printers_backup_path(path))
            _atomic_write_json(path, data)
        else:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        logger.debug(f"Saved data to {path}")
    except Exception as e:
        logger.error(f"Failed to save data to {path}: {str(e)}")

def load_data(filename, default_value):
    path = _resolve_path(filename)
    is_printers_file = _is_printers_path(path)
    bundle_path = os.path.join(os.path.dirname(__file__), os.path.basename(path))
    load_path = path if os.path.exists(path) else bundle_path
    if os.path.exists(load_path):
        try:
            data = _load_json_file(load_path)
            logger.debug(f"Loaded data from {load_path}")
            return data
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Error reading {load_path}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error loading {load_path}: {e}")

        if not is_printers_file:
            return default_value

    if is_printers_file:
        backup_path = _printers_backup_path(path)
        if os.path.exists(backup_path):
            try:
                data = _load_json_file(backup_path)
                logger.warning(
                    "Loaded printers from backup %s after primary %s was missing or invalid",
                    backup_path,
                    path,
                )
                try:
                    _assert_safe_write_path(path)
                    _atomic_write_json(path, data)
                    logger.warning("Restored printers file %s from backup", path)
                except Exception as restore_error:
                    logger.error(
                        "Loaded printers from backup but failed to restore %s: %s",
                        path,
                        restore_error,
                    )
                return data
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.error(f"Error reading printers backup {backup_path}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error loading printers backup {backup_path}: {e}")

    logger.debug(f"No {load_path} found, returning default")
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


def _normalize_gcode_for_compare(gcode):
    """Normalize G-code for deduplication (strip comments/whitespace)."""
    if not gcode:
        return ''
    lines = []
    for line in gcode.strip().split('\n'):
        stripped = line.split(';')[0].strip()
        if stripped:
            lines.append(stripped.upper())
    return '\n'.join(lines)


def resolve_ejection_gcode(ejection_code_id):
    """Resolve ejection code ID to G-code content. Returns (gcode, name) or (None, None)."""
    if not ejection_code_id:
        return None, None
    with SafeLock(ejection_codes_lock):
        for code in EJECTION_CODES:
            if code['id'] == ejection_code_id:
                return code.get('gcode', ''), code.get('name', '')
    return None, None


def auto_save_ejection_code(gcode_content, name_hint="Custom"):
    """Auto-save custom G-code as a preset. Deduplicates by content. Returns the code dict."""
    gcode_content = (gcode_content or '').strip()
    if not gcode_content:
        raise ValueError("G-code content is required")

    normalized = _normalize_gcode_for_compare(gcode_content)

    with SafeLock(ejection_codes_lock):
        for existing in EJECTION_CODES:
            if _normalize_gcode_for_compare(existing.get('gcode', '')) == normalized:
                return existing.copy()

        base_name = (name_hint or 'Custom').strip() or 'Custom'
        name = base_name
        suffix = 1
        existing_names = {c['name'].lower() for c in EJECTION_CODES}
        while name.lower() in existing_names:
            suffix += 1
            name = f"{base_name} ({suffix})"

        new_code = {
            'id': str(uuid.uuid4()),
            'name': name,
            'gcode': gcode_content,
            'created_at': datetime.now().isoformat(),
        }
        EJECTION_CODES.append(new_code)
        save_data(EJECTION_CODES_FILE, EJECTION_CODES)
        logger.info(f"Auto-saved ejection code: {name} (ID: {new_code['id']})")
        return new_code.copy()


def resolve_order_ejection_code_id(ejection_code_id=None, end_gcode=None, name_hint="Custom", default_settings=None):
    """Resolve the ejection_code_id to store on an order when ejection is enabled."""
    if ejection_code_id and ejection_code_id not in ('default', 'custom'):
        gcode, _ = resolve_ejection_gcode(ejection_code_id)
        if gcode:
            return ejection_code_id

    if ejection_code_id == 'default' and default_settings:
        default_id = default_settings.get('default_ejection_code_id')
        if default_id:
            gcode, _ = resolve_ejection_gcode(default_id)
            if gcode:
                return default_id
        legacy_gcode = (default_settings.get('default_end_gcode') or '').strip()
        if legacy_gcode:
            return auto_save_ejection_code(legacy_gcode, 'Default')['id']

    if end_gcode and end_gcode.strip():
        return auto_save_ejection_code(end_gcode.strip(), name_hint)['id']

    if default_settings:
        default_id = default_settings.get('default_ejection_code_id')
        if default_id:
            gcode, _ = resolve_ejection_gcode(default_id)
            if gcode:
                return default_id
        legacy_gcode = (default_settings.get('default_end_gcode') or '').strip()
        if legacy_gcode:
            return auto_save_ejection_code(legacy_gcode, 'Default')['id']

    return None


def apply_ejection_fields_to_order(order, ejection_enabled, ejection_code_id=None, end_gcode=None,
                                   name_hint="Custom", default_settings=None):
    """Set ejection fields on an order dict (ID reference only, no embedded G-code)."""
    order['ejection_enabled'] = bool(ejection_enabled)
    order.pop('end_gcode', None)
    order.pop('ejection_code_name', None)

    if not ejection_enabled:
        order.pop('ejection_code_id', None)
        return

    resolved_id = resolve_order_ejection_code_id(
        ejection_code_id=ejection_code_id,
        end_gcode=end_gcode,
        name_hint=name_hint,
        default_settings=default_settings,
    )
    if resolved_id:
        order['ejection_code_id'] = resolved_id
    else:
        order.pop('ejection_code_id', None)


def _migrate_ejection_fields_on_items(items):
    migrated = False
    for order in items:
            legacy_gcode = (order.pop('end_gcode', None) or '').strip()
            order.pop('ejection_code_name', None)

            if not order.get('ejection_enabled'):
                continue

            existing_id = order.get('ejection_code_id')
            if existing_id:
                gcode, _ = resolve_ejection_gcode(existing_id)
                if gcode:
                    migrated = True
                    continue
                if legacy_gcode:
                    order['ejection_code_id'] = auto_save_ejection_code(
                        legacy_gcode,
                        name_hint=order.get('filename') or order.get('name') or 'Custom',
                    )['id']
                    migrated = True
                    continue

            if legacy_gcode:
                order['ejection_code_id'] = auto_save_ejection_code(
                    legacy_gcode,
                    name_hint=order.get('filename') or order.get('name') or 'Custom',
                )['id']
                migrated = True
    return migrated


def migrate_legacy_order_ejection_fields():
    """Convert orders with embedded end_gcode to ejection_code_id references."""
    migrated = False
    with SafeLock(orders_lock):
        all_items = LIBRARY_ITEMS + QUEUE_JOBS
        needs_backup = any(
            order.get('ejection_enabled')
            and (order.get('end_gcode') or '').strip()
            for order in all_items
        )
        if needs_backup:
            backup_data_files_before_migration(
                'library.json', 'queue.json', 'orders.json', 'ejection_codes.json'
            )

        if _migrate_ejection_fields_on_items(LIBRARY_ITEMS):
            migrated = True
        if _migrate_ejection_fields_on_items(QUEUE_JOBS):
            migrated = True

        if migrated:
            save_data(LIBRARY_FILE, LIBRARY_ITEMS)
            save_data(QUEUE_FILE, QUEUE_JOBS)
            logger.info("Migrated legacy ejection fields to ejection_code_id references")

    return migrated


def count_orders_using_ejection_code(ejection_code_id):
    """Count non-deleted library/queue items referencing an ejection code."""
    count = 0
    with SafeLock(orders_lock):
        for order in LIBRARY_ITEMS + QUEUE_JOBS:
            if order.get('deleted'):
                continue
            if order.get('ejection_code_id') == ejection_code_id:
                count += 1
    return count


def _join_natural(items):
    """Join strings for human-readable error messages (a, b, and c)."""
    if not items:
        return ''
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f'{items[0]} and {items[1]}'
    return ', '.join(items[:-1]) + f', and {items[-1]}'


def describe_ejection_code_delete_blockers(ejection_code_id):
    """Return reasons why an ejection preset cannot be deleted (empty if deletable)."""
    blockers = []
    library_count = 0
    queue_count = 0
    with SafeLock(orders_lock):
        for item in LIBRARY_ITEMS:
            if item.get('deleted'):
                continue
            if item.get('ejection_code_id') == ejection_code_id:
                library_count += 1
        for job in QUEUE_JOBS:
            if job.get('deleted'):
                continue
            if job.get('ejection_code_id') == ejection_code_id:
                queue_count += 1

    if library_count:
        noun = 'item' if library_count == 1 else 'items'
        blockers.append(f'{library_count} library {noun}')
    if queue_count:
        noun = 'job' if queue_count == 1 else 'jobs'
        blockers.append(f'{queue_count} queue {noun}')

    from services.default_settings import load_default_settings

    settings = load_default_settings()
    if settings.get('default_ejection_code_id') == ejection_code_id:
        blockers.append('the default ejection setting')

    return blockers


def format_ejection_code_delete_error(ejection_code_id):
    """User-facing message when delete is blocked, or None if allowed."""
    blockers = describe_ejection_code_delete_blockers(ejection_code_id)
    if not blockers:
        return None
    return f'Cannot delete: this preset is used by {_join_natural(blockers)}.'


def get_order_lock(order_id):
    with SafeLock(order_locks_lock):
        if order_id not in order_locks:
            lock = NamedLock(f"order_lock_{order_id}")
            order_locks[order_id] = lock
        return order_locks[order_id]

def clean_order_locks():
    with SafeLock(order_locks_lock):
        with SafeLock(orders_lock):
            active_order_ids = {o['id'] for o in QUEUE_JOBS}
            for order_id in list(order_locks.keys()):
                if order_id not in active_order_ids:
                    del order_locks[order_id]

def save_order_to_history_direct(order):
    """Direct method to save completed order to history when Flask context is not available"""
    try:
        history_file = get_print_history_file()

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
            except Exception:
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

def increment_queue_sent_count(job_id, increment=1):
    """
    Atomically increment the 'sent' count for a queue job.
    Returns (success, updated_job) tuple.
    """
    with SafeLock(orders_lock):
        start_time = time.time()
        current_thread = threading.current_thread().name
        thread_id = threading.get_ident()
        logging.debug(
            f"Thread {current_thread} (ID: {thread_id}) beginning increment_queue_sent_count for job {job_id}"
        )

        jobs_before = copy.deepcopy(QUEUE_JOBS)

        for i, order in enumerate(QUEUE_JOBS):
            if order['id'] == job_id:
                previous_sent = order['sent']

                if previous_sent >= order['quantity']:
                    logging.info(
                        f"Queue job {job_id} has sent count {previous_sent} >= quantity "
                        f"{order['quantity']}, but still incrementing as requested"
                    )

                if (
                    i < len(jobs_before)
                    and jobs_before[i]['id'] == job_id
                    and jobs_before[i]['sent'] != previous_sent
                ):
                    logging.warning(
                        f"Queue job {job_id} sent count changed during processing from "
                        f"{jobs_before[i]['sent']} to {previous_sent}, not incrementing"
                    )
                    return False, QUEUE_JOBS[i].copy()

                order['sent'] = previous_sent + increment

                if order['sent'] >= order['quantity']:
                    order['status'] = 'fulfilled'
                    if 'completed_at' not in order:
                        order['completed_at'] = datetime.now().isoformat()
                    logging.info(
                        f"Queue job {job_id} fulfilled (sent={order['sent']}, quantity={order['quantity']})"
                    )
                elif order['sent'] > 0:
                    order['status'] = 'partial'

                save_data(QUEUE_FILE, QUEUE_JOBS)
                logging.debug(f"Saved QUEUE_FILE after increment for job {job_id} to {order['sent']}")

                if order['sent'] >= order['quantity']:
                    try:
                        if hasattr(current_app, 'save_completed_order_to_history'):
                            current_app.save_completed_order_to_history(QUEUE_JOBS[i])
                            logging.info(f"Saved fulfilled queue job {job_id} to history via Flask app")
                        else:
                            save_order_to_history_direct(QUEUE_JOBS[i])
                    except RuntimeError as e:
                        if "application context" in str(e):
                            logging.debug("Not in Flask context, saving directly")
                        else:
                            logging.debug(f"Flask runtime error, saving directly: {e}")
                        save_order_to_history_direct(QUEUE_JOBS[i])
                    except Exception as e:
                        logging.debug(f"Could not use Flask app function, saving directly: {e}")
                        save_order_to_history_direct(QUEUE_JOBS[i])

                elapsed = time.time() - start_time
                logging.debug(
                    f"Thread {current_thread} completed queue job {job_id} increment in "
                    f"{elapsed:.4f}s (new sent={order['sent']})"
                )
                return True, QUEUE_JOBS[i].copy()

        logging.error(f"Failed to increment queue job {job_id}: not found in {len(QUEUE_JOBS)} jobs")
        return False, None


def increment_order_sent_count(order_id, increment=1):
    """Backward-compatible alias for increment_queue_sent_count."""
    return increment_queue_sent_count(order_id, increment)


def _do_reset_order_counts():
    """Internal function to do the actual reset work"""
    corrections = 0
    for order in QUEUE_JOBS:
        if 'sent' in order and 'quantity' in order and order['sent'] > order['quantity']:
            logging.warning(f"Fixing order {order.get('id', 'unknown')} with sent count {order['sent']} > quantity {order['quantity']}")
            order['sent'] = order['quantity']
            if 'status' in order:
                order['status'] = 'completed'
            corrections += 1

    if corrections > 0:
        save_data(QUEUE_FILE, QUEUE_JOBS)
        logging.info(f"Fixed {corrections} queue jobs with excessive sent counts")

    return corrections

def reset_order_counts(inside_lock=False):
    """Reset order counts that exceed their quantity"""
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


ACTIVE_ORPHAN_PRINT_STATES = {'PRINTING', 'PAUSED', 'PREPARING', 'PREPARE', 'COOLING', 'EJECTING'}


def _queue_job_has_pending_copies(job):
    try:
        sent = int(job.get('sent', 0) or 0)
        quantity = int(job.get('quantity', 0) or 0)
    except (TypeError, ValueError):
        return False
    return sent < quantity


def _queue_job_sort_id(job):
    job_id = job.get('id')
    if isinstance(job_id, int):
        return job_id
    if isinstance(job_id, str) and job_id.isdigit():
        return int(job_id)
    return float('inf')


def relink_orphaned_active_prints():
    """Recover printer->queue links when active printer state survived but order_id did not."""
    with SafeLock(orders_lock):
        candidate_jobs = [
            copy.deepcopy(job)
            for job in QUEUE_JOBS
            if not job.get('deleted', False) and _queue_job_has_pending_copies(job)
        ]

    if not candidate_jobs:
        return 0

    relinked = 0
    with WriteLock(printers_rwlock):
        for printer in PRINTERS:
            if printer.get('order_id') or printer.get('queue_job_id'):
                continue

            state = str(printer.get('state') or printer.get('status') or '').upper()
            if state not in ACTIVE_ORPHAN_PRINT_STATES:
                continue

            printer_file = printer.get('file')
            if not printer_file:
                continue

            matches = [
                job
                for job in candidate_jobs
                if match_shortened_filename(job.get('filename'), printer_file)
            ]
            if not matches:
                continue

            job = min(matches, key=_queue_job_sort_id)
            printer['order_id'] = job.get('id')
            printer['from_queue'] = True
            relinked += 1
            logger.warning(
                "Relinked active printer %s to queue job %s by matching file %s",
                printer.get('name'),
                job.get('id'),
                printer_file,
            )

        if relinked:
            save_data(PRINTERS_FILE, PRINTERS)

    return relinked


def reconcile_order_counts():
    """
    Reconcile order counts with actual printer status
    Only increases counts when necessary and ensures they never exceed the quantity
    """
    changed_orders = []
    corrections = 0

    # Get all active orders
    with SafeLock(orders_lock):
        active_orders = [o for o in QUEUE_JOBS if o['status'] != 'completed']
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
        for order in QUEUE_JOBS:
            if order['id'] in order_print_count:
                actual_count = order_print_count[order['id']]
                max_count = order['quantity']

                # Only increase count if necessary and never exceed the quantity
                if order['sent'] < actual_count and actual_count <= max_count:
                    old_count = order['sent']
                    order['sent'] = actual_count
                    logging.warning(f"Queue job {order['id']} has sent count {old_count} but {actual_count} actual prints found. Increasing count.")
                    corrections += 1
                    changed_orders.append(order['id'])
                elif actual_count > max_count:
                    logging.error(f"Queue job {order['id']} has {actual_count} actual prints but quantity is only {max_count}. This suggests a synchronization issue.")

        if corrections > 0:
            save_data(QUEUE_FILE, QUEUE_JOBS)
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

def _load_library_and_queue():
    """Load or migrate library.json and queue.json."""
    library_path = str(LIBRARY_FILE)
    queue_path = str(QUEUE_FILE)
    orders_path = str(ORDERS_FILE)

    if not os.path.exists(library_path) and not os.path.exists(queue_path) and os.path.exists(orders_path):
        legacy_orders = load_data(ORDERS_FILE, [])
        migrate_orders_to_library_and_queue(
            legacy_orders,
            LIBRARY_ITEMS,
            QUEUE_JOBS,
            backup_data_files_before_migration,
        )
        save_data(LIBRARY_FILE, LIBRARY_ITEMS)
        save_data(QUEUE_FILE, QUEUE_JOBS)
        logger.info(
            f"Migrated {len(legacy_orders)} legacy orders to "
            f"{len(LIBRARY_ITEMS)} library items and {len(QUEUE_JOBS)} queue jobs"
        )
    else:
        LIBRARY_ITEMS.extend(load_data(LIBRARY_FILE, []))
        QUEUE_JOBS.extend(load_data(QUEUE_FILE, []))

    for item in LIBRARY_ITEMS:
        normalize_library_item(item)
    for job in QUEUE_JOBS:
        normalize_queue_job(job)


def initialize_state():
    """Initialize application state from disk"""
    global PRINTERS, TOTAL_FILAMENT_CONSUMPTION, EJECTION_PAUSED, EJECTION_CODES, _STATE_INITIALIZED
    if _STATE_INITIALIZED:
        logging.warning("⚠️ BLOCKED RE-INITIALIZATION - State already loaded. This prevents duplicates.")
        return
    logging.info("🔄 Initializing state for the first time...")

    with SafeLock(filament_lock):
        filament_data = load_data(TOTAL_FILAMENT_FILE, {"total_filament_used_g": 0})
        TOTAL_FILAMENT_CONSUMPTION = filament_data.get("total_filament_used_g", 0)

    with SafeLock(orders_lock):
        _load_library_and_queue()
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

    # Load ejection codes
    with SafeLock(ejection_codes_lock):
        EJECTION_CODES.extend(load_data(EJECTION_CODES_FILE, []))
        logger.debug(f"Loaded {len(EJECTION_CODES)} ejection codes")

    migrate_legacy_order_ejection_fields()

    # Clean up all ejection states on startup
    cleanup_all_ejection_states()

    # Emergency reset on startup
    reset_all_ejection_states()

    relinked = relink_orphaned_active_prints()
    if relinked:
        logging.warning(f"Relinked {relinked} active printer(s) to queue jobs on startup")

    logger.debug(
        f"State initialized: {len(PRINTERS)} printers, {len(LIBRARY_ITEMS)} library items, "
        f"{len(QUEUE_JOBS)} queue jobs, {len(EJECTION_CODES)} ejection codes, "
        f"{TOTAL_FILAMENT_CONSUMPTION}g filament, ejection_paused={EJECTION_PAUSED}"
    )

    # NOTE: Bambu connections are deferred to start_background_tasks()
    # so they don't block the server from starting up.

    # Mark state as initialized to prevent duplicates
    _STATE_INITIALIZED = True
    logging.info("State initialization complete - locked to prevent re-initialization")

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

# Start background threads on real OS threads (eventlet patches threading.Thread)
spawn_os_daemon(monitor_locks, name='LockMonitor')
# Check if psutil is available before starting memory monitoring
if importlib.util.find_spec("psutil") is not None:
    spawn_os_daemon(monitor_memory_usage, name='MemoryMonitor')
    logging.info("Memory monitoring started")
else:
    logging.warning("psutil not installed, memory monitoring disabled")
spawn_os_daemon(reap_threads, name='ThreadReaper')

def cleanup_mqtt_connections():
    """Clean up MQTT connections on shutdown"""
    from services.bambu_handler import disconnect_all_bambu_printers
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
