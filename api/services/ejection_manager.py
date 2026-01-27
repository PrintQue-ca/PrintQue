"""
Ejection management for 3D printers - handles ejection locks, monitoring,
and GCODE sending for both Prusa and Bambu printers.
"""
import time
import threading
import requests
from threading import Lock

from services.state import (
    PRINTERS_FILE, PRINTERS, ORDERS, save_data, decrypt_api_key,
    logging, orders_lock, printers_rwlock,
    SafeLock, ReadLock, WriteLock,
    get_ejection_paused, set_printer_ejection_state,
    get_printer_ejection_state, clear_printer_ejection_state
)
from services.bambu_handler import (
    send_bambu_ejection_gcode, BAMBU_PRINTER_STATES, bambu_states_lock
)
from utils.retry_utils import retry_async
from utils.logger import debug_log

# Ejection lock system to prevent multiple simultaneous ejections
EJECTION_LOCKS = {}  # Track which printers are currently ejecting
ejection_locks_lock = Lock()  # Protect the ejection locks dict


def get_ejection_lock(printer_name):
    """Get or create an ejection lock for a printer"""
    with ejection_locks_lock:
        if printer_name not in EJECTION_LOCKS:
            EJECTION_LOCKS[printer_name] = Lock()
        return EJECTION_LOCKS[printer_name]


def is_ejection_in_progress(printer_name):
    """Check if ejection is currently in progress for THIS SPECIFIC printer"""
    ejection_lock = get_ejection_lock(printer_name)
    # Try to acquire lock without blocking - if we can't, ejection is in progress FOR THIS PRINTER
    acquired = ejection_lock.acquire(blocking=False)
    if acquired:
        ejection_lock.release()
        logging.debug(f"EJECTION LOCK CHECK: {printer_name} - lock available (not in progress)")
        return False
    logging.warning(f"EJECTION LOCK CHECK: {printer_name} - lock busy (ejection in progress for THIS printer)")
    return True


def release_ejection_lock(printer_name):
    """Release the ejection lock for a printer"""
    ejection_lock = get_ejection_lock(printer_name)
    try:
        ejection_lock.release()
        logging.info(f"EJECTION COMPLETE: Released lock for {printer_name}")
    except Exception:
        pass  # Lock may already be released


def force_release_all_ejection_locks():
    """Force release all ejection locks - use for debugging stuck locks"""
    with ejection_locks_lock:
        released_count = 0
        for printer_name, lock in EJECTION_LOCKS.items():
            try:
                # Try to release the lock (may fail if not acquired)
                lock.release()
                released_count += 1
                logging.warning(f"FORCE RELEASED: Ejection lock for {printer_name}")
            except Exception:
                pass  # Lock wasn't acquired
        logging.warning(f"FORCE RELEASED: {released_count} ejection locks")
        return released_count


def clear_stuck_ejection_locks():
    """Clear locks for printers not actually in EJECTING state"""
    with ejection_locks_lock:
        with ReadLock(printers_rwlock):
            cleared_count = 0
            for printer_name, lock in list(EJECTION_LOCKS.items()):
                # Find the printer's current state
                printer = next((p for p in PRINTERS if p['name'] == printer_name), None)
                if printer and printer.get('state') != 'EJECTING':
                    # Printer is not ejecting but has a lock - clear it
                    try:
                        lock.release()
                        cleared_count += 1
                        logging.warning(f"CLEARED STUCK LOCK: {printer_name} (state: {printer.get('state')})")
                    except Exception:
                        pass
            if cleared_count > 0:
                logging.warning(f"CLEARED {cleared_count} stuck ejection locks")
            return cleared_count


def detect_ejection_completion(printer, api_state, current_api_file):
    """
    Simplified ejection completion detection
    Returns True if ejection is complete, False otherwise
    """
    printer_name = printer['name']
    current_state = printer.get('state')

    if current_state != 'EJECTING':
        return False

    # Check ejection state manager first
    ejection_state = get_printer_ejection_state(printer_name)
    if ejection_state['state'] == 'completed':
        logging.info(f"Ejection completion detected for {printer_name}: State manager shows completed")
        return True

    # Method 1: API shows completion states (most reliable)
    if api_state in ['IDLE', 'FINISHED', 'READY', 'OPERATIONAL']:
        logging.info(f"Ejection completion detected for {printer_name}: API state = {api_state}")
        return True

    # Method 2: For Prusa printers - ejection file no longer running
    stored_file = printer.get('file', '')
    if stored_file and 'ejection_' in stored_file:
        # If API shows no file or different file, ejection is complete
        if not current_api_file or current_api_file != stored_file:
            logging.info(f"Ejection completion detected for {printer_name}: File changed from {stored_file} to {current_api_file or 'None'}")
            return True

    # Method 3: Bambu-specific completion detection
    if printer.get('type') == 'bambu':
        try:
            with bambu_states_lock:
                if printer_name in BAMBU_PRINTER_STATES:
                    bambu_state = BAMBU_PRINTER_STATES[printer_name]
                    if bambu_state.get('ejection_complete', False):
                        logging.info(f"Bambu ejection completion detected for {printer_name}")
                        return True
                    # Also check if Bambu state shows completion
                    bambu_api_state = bambu_state.get('state', '')
                    if bambu_api_state in ['IDLE', 'READY']:
                        logging.info(f"Bambu ejection completion detected via state: {bambu_api_state}")
                        return True
        except Exception as e:
            logging.debug(f"Bambu state check failed for {printer_name}: {e}")

    return False


def handle_finished_state_ejection(printer, printer_name, current_file, current_order_id, updates):
    """Enhanced handler for FINISHED state that checks for and processes ejection if needed"""

    # CRITICAL: Always ensure finish_time is set when entering FINISHED state
    if not printer.get('finish_time'):
        finish_time = time.time()
        updates['finish_time'] = finish_time
        logging.debug(f"Setting finish_time for {printer_name}: {finish_time}")
    else:
        # Preserve existing finish_time
        updates['finish_time'] = printer.get('finish_time')

    # CRITICAL FIX: Check if ejection has already been processed OR is currently in progress
    if printer.get('ejection_processed', False) or printer.get('ejection_in_progress', False):
        logging.debug(f"FINISHED->SKIP: {printer_name} (ejection already processed or in progress)")
        updates.update({
            "state": printer.get('state'),
            "status": printer.get('status'),
            "progress": 100,
            "time_remaining": 0,
            "manually_set": False
        })
        return

    # Check if we have an order with ejection enabled
    with SafeLock(orders_lock):
        order = next((o for o in ORDERS if o['id'] == current_order_id), None)
        if order:
            debug_log('cooldown', f"Found order {current_order_id}: ejection={order.get('ejection_enabled')}, cooldown={order.get('cooldown_temp')}, file={order.get('filename')}")
        else:
            debug_log('cooldown', f"Order {current_order_id} NOT FOUND! Available: {[o['id'] for o in ORDERS]}", 'warning')

    if not order or not order.get('ejection_enabled', False):
        # No ejection needed - STAY in FINISHED state
        logging.info(f"FINISHED->STAY: {printer_name} (no ejection enabled - staying in FINISHED)")
        updates.update({
            "state": 'FINISHED',
            "status": 'Print Complete',
            "progress": 100,
            "time_remaining": 0,
            "manually_set": False,
            "ejection_processed": False,
            "ejection_in_progress": False,
            "ejection_start_time": None,
            "finish_time": time.time()
        })
        return

    # Check global ejection pause state
    ejection_paused = get_ejection_paused()
    if ejection_paused:
        logging.info(f"FINISHED->PAUSED: {printer_name} (ejection globally paused)")
        set_printer_ejection_state(printer_name, 'queued', {'reason': 'global_pause'})
        updates.update({
            "state": "FINISHED",
            "status": "Print Complete (Ejection Paused)",
            "progress": 100,
            "time_remaining": 0,
            "manually_set": False,
            "ejection_in_progress": False,
            "finish_time": time.time()
        })
        return

    # BAMBU COOLDOWN FEATURE: Check if we need to wait for bed to cool before ejection
    order_cooldown = order.get('cooldown_temp') if order else None
    is_bambu = printer.get('type') == 'bambu'
    has_cooldown = order_cooldown is not None

    debug_log('cooldown', f"{printer_name}: type={printer.get('type')}, order_id={current_order_id}, cooldown={order_cooldown}")
    debug_log('cooldown', f"{printer_name}: is_bambu={is_bambu}, has_cooldown={has_cooldown}, will_check={is_bambu and has_cooldown}")

    if is_bambu and has_cooldown:
        cooldown_temp = int(order_cooldown)

        # Get current bed temperature from Bambu MQTT state
        current_bed_temp = 0
        try:
            with bambu_states_lock:
                if printer_name in BAMBU_PRINTER_STATES:
                    current_bed_temp = BAMBU_PRINTER_STATES[printer_name].get('bed_temp', 0)
                    debug_log('cooldown', f"{printer_name}: bed_temp={current_bed_temp}°C from MQTT")
                else:
                    debug_log('cooldown', f"{printer_name}: NOT in BAMBU_PRINTER_STATES!", 'warning')
        except Exception as e:
            logging.warning(f"Could not get bed temp for {printer_name}: {e}")

        debug_log('cooldown', f"{printer_name}: bed={current_bed_temp}°C vs target={cooldown_temp}°C, needs_cooling={current_bed_temp > cooldown_temp}")

        if current_bed_temp > cooldown_temp:
            logging.info(f"FINISHED->COOLING: {printer_name} (bed temp {current_bed_temp}°C > target {cooldown_temp}°C)")
            updates.update({
                "state": 'COOLING',
                "status": f'Cooling ({current_bed_temp}°C → {cooldown_temp}°C)',
                "progress": 100,
                "time_remaining": 0,
                "manually_set": False,
                "ejection_in_progress": False,
                "cooldown_target": cooldown_temp
            })
            return

    # All checks passed - start ejection
    logging.info(f"FINISHED->EJECTING: {printer_name} (starting ejection)")

    # Mark as ejection in progress BEFORE acquiring lock
    updates.update({
        "state": 'EJECTING',
        "status": 'Ejecting',
        "progress": 100,
        "time_remaining": 0,
        "manually_set": False,
        "ejection_in_progress": True,
        "ejection_processed": True,
        "ejection_start_time": time.time()
    })

    # Try to acquire ejection lock
    ejection_lock = get_ejection_lock(printer_name)
    if not ejection_lock.acquire(blocking=False):
        logging.warning(f"EJECTION: Could not acquire lock for {printer_name} - ejection already in progress")
        return

    try:
        set_printer_ejection_state(printer_name, 'in_progress')

        # Execute ejection based on printer type
        gcode_content = order.get('end_gcode', '').strip()
        if not gcode_content:
            gcode_content = "G28 X Y\nM84"  # Default ejection

        if printer.get('type') == 'bambu':
            # Bambu ejection
            success = send_bambu_ejection_gcode(printer, gcode_content)
            if not success:
                logging.error(f"Bambu ejection failed for {printer_name}")
                set_printer_ejection_state(printer_name, 'completed')
                ejection_lock.release()
                printer['ejection_in_progress'] = False
        else:
            # Prusa ejection - store ejection details AND update main PRINTERS list immediately
            gcode_file_name = f"ejection_{printer_name}_{int(time.time())}.gcode"

            # Store pending ejection on the actual printer object in PRINTERS
            with WriteLock(printers_rwlock):
                for p in PRINTERS:
                    if p['name'] == printer_name:
                        p['pending_ejection'] = {
                            'gcode_content': gcode_content,
                            'gcode_file_name': gcode_file_name,
                            'timestamp': time.time()
                        }
                        # Update state immediately to prevent job distribution
                        p['state'] = 'EJECTING'
                        p['status'] = 'Ejecting'
                        p['ejection_in_progress'] = True
                        p['ejection_processed'] = True
                        p['ejection_start_time'] = time.time()
                        p['manually_set'] = False
                        logging.info(f"EJECTION: Updated {printer_name} to EJECTING state in main PRINTERS list")
                        break
            logging.info(f"EJECTION: Stored pending ejection for {printer_name} - will be processed in next API poll")

    except Exception as e:
        logging.error(f"Ejection setup error for {printer_name}: {e}")
        set_printer_ejection_state(printer_name, 'completed')
        ejection_lock.release()
        printer['ejection_in_progress'] = False


async def async_send_ejection_gcode(session, printer, headers, ejection_url, gcode_content, gcode_file_name):
    """Send ejection GCODE to printer asynchronously"""
    printer_name = printer['name']

    logging.debug(f"EJECTION: Starting actual file transfer for {printer_name}")

    async def _send_gcode():
        if printer.get('type') == 'bambu':
            # For Bambu printers, send G-code directly via MQTT
            logging.debug(f"EJECTION: Sending G-code to Bambu printer {printer_name} via MQTT")
            try:
                success = send_bambu_ejection_gcode(printer, gcode_content)
                if success:
                    logging.debug(f"EJECTION: Successfully sent G-code to Bambu printer {printer_name}")

                    printer['file'] = None
                    printer['order_id'] = None
                    printer['ejection_processed'] = True
                    printer['last_ejection_time'] = time.time()

                    # Mark ejection as complete and trigger immediate transition
                    set_printer_ejection_state(printer_name, 'completed')
                    release_ejection_lock(printer_name)

                    # Force immediate transition to READY
                    printer.update({
                        "state": 'READY',
                        "status": 'Ready',
                        "progress": 0,
                        "time_remaining": 0,
                        "file": None,
                        "job_id": None,
                        "order_id": None,
                        "manually_set": True,
                        "ejection_processed": False,
                        "ejection_in_progress": False,
                        "ejection_start_time": None,
                        "finish_time": None,
                        "count_incremented_for_current_job": False
                    })
                    logging.info(f"EJECTION COMPLETE: {printer_name} immediately transitioned to READY")
                    return True
                else:
                    logging.error(f"EJECTION: Failed to send G-code to Bambu printer {printer_name}")
                    return False
            except Exception as e:
                logging.error(f"EJECTION: Exception sending to Bambu {printer_name}: {str(e)}")
                return False
        else:
            # For Prusa printers - upload via HTTP API
            logging.debug(f"EJECTION: Uploading G-code to Prusa printer {printer_name} at {ejection_url}")
            try:
                async with session.put(
                    ejection_url,
                    data=gcode_content.encode('utf-8'),
                    headers={**headers, "Print-After-Upload": "?1"}
                ) as upload_resp:
                    logging.debug(f"EJECTION: Upload response for {printer_name}: HTTP {upload_resp.status}")
                    if upload_resp.status == 201:
                        printer['file'] = gcode_file_name
                        printer['order_id'] = None
                        printer['ejection_processed'] = True
                        printer['last_ejection_time'] = time.time()

                        # Don't immediately transition - let monitoring detect completion
                        set_printer_ejection_state(printer_name, 'running')

                        logging.info(f"EJECTION STARTED: {printer_name} - G-code uploaded and printing")
                        return True
                    else:
                        response_text = await upload_resp.text()
                        logging.error(f"EJECTION: Failed to upload to {printer_name}: HTTP {upload_resp.status}, Response: {response_text}")
                        release_ejection_lock(printer_name)
                        return False
            except Exception as e:
                logging.error(f"EJECTION: Exception uploading to Prusa {printer_name}: {str(e)}")
                release_ejection_lock(printer_name)
                return False

    try:
        success = await retry_async(_send_gcode, max_retries=2, initial_backoff=1)
        if not success:
            logging.warning(f"EJECTION: All attempts failed for {printer_name}")
            set_printer_ejection_state(printer_name, 'failed')
            release_ejection_lock(printer_name)
        else:
            logging.info(f"EJECTION: Successfully started for {printer_name}")
    except Exception as e:
        logging.error(f"EJECTION: Final error for {printer_name}: {str(e)}")
        set_printer_ejection_state(printer_name, 'failed')
        release_ejection_lock(printer_name)


def enhanced_prusa_ejection_monitoring():
    """
    Enhanced monitoring specifically for Prusa ejection completion.
    This runs independently of the main API polling to catch completion.
    """
    printers_to_check = []

    # Get printers currently in EJECTING state
    with ReadLock(printers_rwlock, timeout=5):
        for i, printer in enumerate(PRINTERS):
            if (printer.get('state') == 'EJECTING' and
                printer.get('type', 'prusa') != 'bambu'):
                printers_to_check.append({
                    'index': i,
                    'name': printer['name'],
                    'ip': printer['ip'],
                    'api_key': printer.get('api_key'),
                    'ejection_file': printer.get('file', ''),
                    'ejection_start_time': printer.get('ejection_start_time', 0)
                })

    if not printers_to_check:
        return

    # Check each printer's current status directly
    for printer_info in printers_to_check:
        try:
            headers = {"X-Api-Key": decrypt_api_key(printer_info['api_key'])} if printer_info['api_key'] else {}
            status_url = f"http://{printer_info['ip']}/api/v1/status"

            response = requests.get(status_url, headers=headers, timeout=5)
            if response.status_code == 200:
                status_data = response.json()
                current_api_state = status_data.get('printer', {}).get('state', 'UNKNOWN')
                current_api_file = status_data.get('job', {}).get('file', {}).get('name', '')

                logging.debug(f"Direct ejection check for {printer_info['name']}: API_state={current_api_state}, API_file='{current_api_file}', stored_ejection_file='{printer_info['ejection_file']}'")

                ejection_complete = False
                completion_reason = ""

                # Method 1: Check ejection state manager
                ejection_state = get_printer_ejection_state(printer_info['name'])
                if ejection_state['state'] == 'completed':
                    ejection_complete = True
                    completion_reason = "State manager shows completed"

                # Method 2: API shows non-printing/ejecting states
                elif current_api_state in ['IDLE', 'READY', 'OPERATIONAL', 'FINISHED']:
                    ejection_complete = True
                    completion_reason = f"API state changed to {current_api_state}"

                # Method 3: Ejection file no longer active
                elif printer_info['ejection_file'] and 'ejection_' in printer_info['ejection_file']:
                    if not current_api_file or current_api_file != printer_info['ejection_file']:
                        ejection_complete = True
                        completion_reason = f"File changed from '{printer_info['ejection_file']}' to '{current_api_file}'"

                # Method 4: No file running at all
                elif not current_api_file and current_api_state != 'PRINTING':
                    ejection_complete = True
                    completion_reason = "No file active and not printing"

                if ejection_complete:
                    logging.info(f"PRUSA EJECTION COMPLETE: {printer_info['name']} - {completion_reason}")

                    with WriteLock(printers_rwlock, timeout=10):
                        if printer_info['index'] < len(PRINTERS):
                            printer = PRINTERS[printer_info['index']]
                            if printer.get('state') == 'EJECTING':
                                printer.update({
                                    "state": 'READY',
                                    "status": 'Ready',
                                    "progress": 0,
                                    "time_remaining": 0,
                                    "file": None,
                                    "job_id": None,
                                    "order_id": None,
                                    "manually_set": True,
                                    "ejection_processed": False,
                                    "ejection_in_progress": False,
                                    "ejection_start_time": None,
                                    "finish_time": None,
                                    "last_ejection_time": time.time(),
                                    "count_incremented_for_current_job": False
                                })

                                release_ejection_lock(printer_info['name'])
                                clear_printer_ejection_state(printer_info['name'])

                                logging.info(f"Successfully transitioned {printer_info['name']} from EJECTING to READY")
                                save_data(PRINTERS_FILE, PRINTERS)

                                # Trigger job distribution after a short delay
                                def trigger_distribution():
                                    try:
                                        from services.order_distributor import start_background_distribution
                                        from app import socketio, app
                                        start_background_distribution(socketio, app)
                                    except Exception as e:
                                        logging.error(f"Error triggering distribution after ejection: {e}")

                                threading.Timer(2.0, trigger_distribution).start()

            else:
                logging.warning(f"Failed to check ejection status for {printer_info['name']}: HTTP {response.status_code}")

        except Exception as e:
            logging.error(f"Error checking ejection status for {printer_info['name']}: {e}")


def start_prusa_ejection_monitor():
    """Start background thread for enhanced Prusa ejection monitoring"""
    def monitor_loop():
        while True:
            try:
                enhanced_prusa_ejection_monitoring()
                time.sleep(10)
            except Exception as e:
                logging.error(f"Error in Prusa ejection monitor: {e}")
                time.sleep(15)

    monitor_thread = threading.Thread(target=monitor_loop, daemon=True, name="PrusaEjectionMonitor")
    monitor_thread.start()
    logging.info("Started enhanced Prusa ejection monitoring thread")


def trigger_mass_ejection_for_finished_printers(socketio, app):
    """Trigger ejection for all FINISHED printers that have ejection enabled"""
    # Import here to avoid circular imports
    from services.order_distributor import start_background_distribution

    if get_ejection_paused():
        logging.warning("Mass ejection requested but ejection is still paused - aborting")
        return 0

    logging.info("=== MASS EJECTION INITIATED ===")

    # Find printers ready for mass ejection
    ready_printers = []
    with ReadLock(printers_rwlock):
        for printer in PRINTERS:
            if (printer.get('state') == 'FINISHED' and
                printer.get('status') == 'Print Complete (Ejection Paused)'):

                order_id = printer.get('order_id')
                if order_id:
                    with SafeLock(orders_lock):
                        order = next((o for o in ORDERS if o['id'] == order_id), None)
                        if order and order.get('ejection_enabled', False):
                            ejection_state = get_printer_ejection_state(printer['name'])
                            if ejection_state['state'] not in ['in_progress', 'completed']:
                                ready_printers.append({
                                    'name': printer['name'],
                                    'order_id': order_id,
                                    'file': printer.get('file', 'unknown')
                                })

    if not ready_printers:
        logging.info("No printers ready for mass ejection")
        return 0

    logging.info(f"Found {len(ready_printers)} printers ready for mass ejection")

    # Mark all as queued first, then start ejections
    ejection_count = 0
    with WriteLock(printers_rwlock):
        for printer in PRINTERS:
            if any(p['name'] == printer['name'] for p in ready_printers):
                set_printer_ejection_state(printer['name'], 'queued', {'trigger': 'mass_ejection'})

                logging.info(f"MASS EJECTION: Queuing {printer['name']} for ejection")
                printer.update({
                    "state": 'FINISHED',
                    "status": 'Print Complete (Ejection Queued)',
                    "manually_set": False
                })
                ejection_count += 1

        save_data(PRINTERS_FILE, PRINTERS)

    # Trigger status update to process the queued ejections
    threading.Timer(1.0, lambda: start_background_distribution(socketio, app)).start()

    logging.info(f"=== MASS EJECTION: {ejection_count} printers queued ===")
    return ejection_count
