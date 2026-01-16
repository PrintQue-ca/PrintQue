import os
import aiohttp
import asyncio
import requests
import time
import uuid
import threading
import re
from datetime import datetime
import tempfile
from threading import Lock
from services.state import (
    PRINTERS_FILE, TOTAL_FILAMENT_FILE, ORDERS_FILE,
    PRINTERS, TOTAL_FILAMENT_CONSUMPTION, ORDERS,
    save_data, load_data, encrypt_api_key, decrypt_api_key,
    logging, orders_lock, filament_lock, printers_rwlock, SafeLock, ReadLock, WriteLock,
    get_order_lock, acquire_locks, increment_order_sent_count,
    reconcile_order_counts, create_print_transaction, update_print_transaction, get_print_transaction,
    get_ejection_paused,
    set_printer_ejection_state, get_printer_ejection_state, clear_printer_ejection_state,
    is_ejection_in_progress_enhanced, get_ejection_lock, release_ejection_lock
)
from utils.config import Config
from utils.retry_utils import retry_async
from contextlib import asynccontextmanager
import copy
from utils.logger import (
    log_state_transition,
    log_distribution_event,
    log_job_lifecycle,
    log_api_poll_event,
    log_manual_action
)
# Bambu printer support
from services.bambu_handler import (
    connect_bambu_printer, get_bambu_status, send_bambu_print_command,
    stop_bambu_print, pause_bambu_print, resume_bambu_print,
    send_bambu_ejection_gcode,
    BAMBU_PRINTER_STATES, bambu_states_lock
)

thread_local = threading.local()
distribution_semaphore = threading.Semaphore(1)

# Ejection lock system to prevent multiple simultaneous ejections
EJECTION_LOCKS = {}  # Track which printers are currently ejecting
ejection_locks_lock = Lock()  # Protect the ejection locks dict


def deduplicate_printers():
    """Remove duplicate printers from the PRINTERS list - keep first occurrence"""
    global PRINTERS
    
    with WriteLock(printers_rwlock):
        seen_names = set()
        unique_printers = []
        duplicates_removed = 0
        
        for printer in PRINTERS:
            printer_name = printer.get('name')
            if printer_name and printer_name not in seen_names:
                seen_names.add(printer_name)
                unique_printers.append(printer)
            else:
                duplicates_removed += 1
                logging.warning(f"REMOVED DUPLICATE: Printer '{printer_name}' was duplicated")
                
        if duplicates_removed > 0:
            PRINTERS.clear()
            PRINTERS.extend(unique_printers)
            save_data(PRINTERS_FILE, PRINTERS)
            logging.warning(f"DEDUPLICATION: Removed {duplicates_removed} duplicate printers. Now have {len(PRINTERS)} unique printers")
        else:
            logging.info(f"DEDUPLICATION: No duplicates found. Have {len(PRINTERS)} unique printers")

def deduplicate_orders():
    """Remove duplicate orders from the ORDERS list - keep first occurrence"""
    global ORDERS
    
    with SafeLock(orders_lock):
        seen_ids = set()
        unique_orders = []
        duplicates_removed = 0
        
        for order in ORDERS:
            order_id = order.get('id')
            if order_id and order_id not in seen_ids:
                seen_ids.add(order_id)
                unique_orders.append(order)
            else:
                duplicates_removed += 1
                logging.warning(f"REMOVED DUPLICATE: Order '{order_id}' was duplicated")
                
        if duplicates_removed > 0:
            ORDERS.clear()
            ORDERS.extend(unique_orders)
            save_data(ORDERS_FILE, ORDERS)
            logging.warning(f"DEDUPLICATION: Removed {duplicates_removed} duplicate orders. Now have {len(ORDERS)} unique orders")
        else:
            logging.info(f"DEDUPLICATION: No duplicates found. Have {len(ORDERS)} unique orders")

def periodic_deduplication_check(socketio, app):
    """Periodically check for and remove duplicates"""
    while True:
        try:
            time.sleep(300)  # Check every 5 minutes
                        
            # Check for printer duplicates
            # Use ReadLock for the check before calling the function that uses WriteLock
            with ReadLock(printers_rwlock):
                printer_names = [p.get('name') for p in PRINTERS]
                if len(printer_names) != len(set(printer_names)):
                    logging.warning("DUPLICATE PRINTERS DETECTED! Running deduplication...")
                            
            deduplicate_printers()
                    
            # Check for order duplicates
            # Use SafeLock/orders_lock for the check before calling the function that uses SafeLock
            with SafeLock(orders_lock):
                order_ids = [o.get('id') for o in ORDERS]
                if len(order_ids) != len(set(order_ids)):
                    logging.warning("DUPLICATE ORDERS DETECTED! Running deduplication...")
                            
            deduplicate_orders()
                
        except Exception as e:
            logging.error(f"Error in periodic deduplication: {e}")

def get_minutes_since_finished(printer):
    """Calculate minutes elapsed since printer entered FINISHED state
    
    Args:
        printer: Dictionary containing printer data
        
    Returns:
        int: Minutes elapsed since finished, or None if not applicable
    """
    logging.debug(f"Checking finish time for {printer.get('name')}: "
                  f"state={printer.get('state')}, finish_time={printer.get('finish_time')}")
    
    if printer.get('state') != 'FINISHED' or not printer.get('finish_time'):
        return None
    
    current_time = time.time()
    finish_time = printer.get('finish_time', current_time)
    elapsed_seconds = current_time - finish_time
    
    minutes = int(elapsed_seconds / 60)
    
    logging.debug(f"Timer for {printer.get('name')}: {minutes} minutes")
    return minutes

def prepare_printer_data_for_broadcast(printers):
    """Prepare printer data with calculated fields for broadcasting"""
    printers_copy = copy.deepcopy(printers)
    
    # Add minutes since finished for each printer
    for printer in printers_copy:
        if printer.get('state') == 'FINISHED':
            minutes = get_minutes_since_finished(printer)
            if minutes is not None:
                printer['minutes_since_finished'] = minutes
            else:
                # If we can't calculate minutes, but printer is FINISHED, set to 0
                printer['minutes_since_finished'] = 0
                logging.warning(f"FINISHED printer {printer.get('name')} has no valid timer, setting to 0")
    
    return printers_copy

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
    except:
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
            except:
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
                    except:
                        pass
            if cleared_count > 0:
                logging.warning(f"CLEARED {cleared_count} stuck ejection locks")
            return cleared_count

def enhanced_prusa_ejection_monitoring():
    """
    Enhanced monitoring specifically for Prusa ejection completion
    This runs independently of the main API polling to catch completion
    """
    printers_to_check = []
    
    # Get printers currently in EJECTING state
    with ReadLock(printers_rwlock, timeout=5):
        for i, printer in enumerate(PRINTERS):
            if (printer.get('state') == 'EJECTING' and 
                printer.get('type', 'prusa') != 'bambu'):  # Only Prusa printers
                printers_to_check.append({
                    'index': i,
                    'name': printer['name'],
                    'ip': printer['ip'],
                    'api_key': printer.get('api_key'),
                    'ejection_file': printer.get('file', ''),
                    'ejection_start_time': printer.get('ejection_start_time', 0)
                })
    
    if not printers_to_check:
        return  # No Prusa printers ejecting
    
    # Check each printer's current status directly
    for printer_info in printers_to_check:
        try:
            # Direct API call to check current state
            headers = {"X-Api-Key": decrypt_api_key(printer_info['api_key'])} if printer_info['api_key'] else {}
            status_url = f"http://{printer_info['ip']}/api/v1/status"
            
            response = requests.get(status_url, headers=headers, timeout=5)
            if response.status_code == 200:
                status_data = response.json()
                current_api_state = status_data.get('printer', {}).get('state', 'UNKNOWN')
                current_api_file = status_data.get('job', {}).get('file', {}).get('name', '')
                
                # Log detailed status for debugging
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
                
                # Method 3: Ejection file no longer active (most reliable for Prusa)
                elif printer_info['ejection_file'] and 'ejection_' in printer_info['ejection_file']:
                    # If the current file is different from ejection file, ejection is complete
                    if not current_api_file or current_api_file != printer_info['ejection_file']:
                        ejection_complete = True
                        completion_reason = f"File changed from '{printer_info['ejection_file']}' to '{current_api_file}'"
                
                # Method 4: No file running at all (fallback)
                elif not current_api_file and current_api_state != 'PRINTING':
                    ejection_complete = True
                    completion_reason = "No file active and not printing"
                
                if ejection_complete:
                    logging.info(f"PRUSA EJECTION COMPLETE: {printer_info['name']} - {completion_reason}")
                    
                    # Force transition to READY
                    with WriteLock(printers_rwlock, timeout=10):
                        if printer_info['index'] < len(PRINTERS):
                            printer = PRINTERS[printer_info['index']]
                            if printer.get('state') == 'EJECTING':  # Double-check still ejecting
                                printer.update({
                                    "state": 'READY',
                                    "status": 'Ready',
                                    "progress": 0,
                                    "time_remaining": 0,
                                    "file": None,
                                    "job_id": None,
                                    "order_id": None,
                                    "manually_set": True,
                                    "ejection_processed": False,  # Reset for next job
                                    "ejection_in_progress": False, # Reset the in-progress flag
                                    "ejection_start_time": None,
                                    "finish_time": None,
                                    "last_ejection_time": time.time(),
                                    "count_incremented_for_current_job": False # Reset count flag
                                })
                                
                                # Clean up ejection state
                                release_ejection_lock(printer_info['name'])
                                clear_printer_ejection_state(printer_info['name'])
                                
                                logging.info(f"Successfully transitioned {printer_info['name']} from EJECTING to READY")
                                
                                # Save data and trigger distribution
                                save_data(PRINTERS_FILE, PRINTERS)
                                
                                # Trigger job distribution after a short delay
                                def trigger_distribution():
                                    try:
                                        # This will be called from the background thread
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
                time.sleep(10)  # Check every 10 seconds
            except Exception as e:
                logging.error(f"Error in Prusa ejection monitor: {e}")
                time.sleep(15)  # Wait longer on error
    
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True, name="PrusaEjectionMonitor")
    monitor_thread.start()
    logging.info("Started enhanced Prusa ejection monitoring thread")

def get_event_loop_for_thread():
    if not hasattr(thread_local, 'loop') or thread_local.loop.is_closed():
        thread_local.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(thread_local.loop)
    return thread_local.loop

state_map = {
    'IDLE': 'Ready', 'PRINTING': 'Printing', 'PAUSED': 'Paused', 'ERROR': 'Error',
    'FINISHED': 'Finished', 'READY': 'Ready', 'STOPPED': 'Stopped', 'ATTENTION': 'Attention',
    'EJECTING': 'Ejecting', 'PREPARE': 'Preparing', 'OFFLINE': 'Offline'
}

CONNECTION_POOL = None

def update_bambu_printer_states():
    """Update main printer states from Bambu MQTT data and track filament usage"""
    global TOTAL_FILAMENT_CONSUMPTION
    
    # Get Bambu states snapshot
    with bambu_states_lock:
        bambu_states = copy.deepcopy(BAMBU_PRINTER_STATES)
    
    # Log current filament total for debugging
    logging.debug(f"[FILAMENT DEBUG] Current TOTAL_FILAMENT_CONSUMPTION: {TOTAL_FILAMENT_CONSUMPTION}g")
    
    with WriteLock(printers_rwlock):
        for printer in PRINTERS:
            if printer.get('type') != 'bambu':
                continue
                
            printer_name = printer['name']
            if printer_name not in bambu_states:
                continue
                
            state_data = bambu_states[printer_name]
            
            # Store previous state for transition detection
            previous_state = printer.get('state', 'OFFLINE')
            previous_file = printer.get('file')
            
            # CRITICAL: Check if printer is manually set to READY - don't override it!
            if printer.get('manually_set', False) and printer.get('state') == 'READY':
                logging.debug(f"Preserving manually set READY state for Bambu printer {printer_name}")
                # Still update temperatures and other non-state data
                printer['temps'] = {
                    'nozzle': state_data.get('nozzle_temp', 0),
                    'bed': state_data.get('bed_temp', 0)
                }
                # Clear progress since it's marked as ready
                printer['progress'] = 0
                printer['time_remaining'] = 0
                printer['file'] = None
                continue  # Skip the rest of the state update logic
            
            # Map Bambu states to our standard states
            bambu_state = state_data.get('state', 'OFFLINE')
            gcode_state = state_data.get('gcode_state', 'UNKNOWN')
            
            # Log state changes for debugging
            if previous_state != bambu_state:
                logging.info(f"[FILAMENT DEBUG] Bambu printer {printer_name} state change: {previous_state} -> {bambu_state}")
            
            # Update printer state
            new_state = bambu_state
            printer['state'] = new_state
            printer['status'] = state_map.get(new_state, 'Unknown')
            
            # Update temperatures
            printer['temps'] = {
                'nozzle': state_data.get('nozzle_temp', 0),
                'bed': state_data.get('bed_temp', 0)
            }
            
            # Update progress
            printer['progress'] = state_data.get('progress', 0)
            
            # Update time remaining
            printer['time_remaining'] = state_data.get('time_remaining', 0)
            
            # Update current file
            if state_data.get('current_file'):
                printer['file'] = state_data['current_file']
            
            # Log print completion for debugging (but don't track filament here anymore)
            if previous_state == 'PRINTING' and new_state == 'FINISHED':
                logging.info(f"[PRINT COMPLETE] Bambu printer {printer_name} finished printing")
                logging.info(f"[DEBUG] Printer order_id: {printer.get('order_id')}")
                logging.info(f"[DEBUG] Printer current file: {printer.get('file')}")
                logging.info(f"[DEBUG] Printer filament_used_g: {printer.get('filament_used_g', 0)}")
                # Note: Filament is now tracked when the print starts, not when it finishes
        
        # Save printer states after updating
        save_data(PRINTERS_FILE, PRINTERS)

def ensure_finish_times():
    """Ensure all FINISHED printers have a finish_time set"""
    with WriteLock(printers_rwlock):
        updated = False
        for printer in PRINTERS:
            if printer.get('state') == 'FINISHED' and not printer.get('finish_time'):
                printer['finish_time'] = time.time()
                logging.info(f"Set missing finish_time for FINISHED printer {printer['name']}")
                updated = True
        
        if updated:
            save_data(PRINTERS_FILE, PRINTERS)
            logging.info("Updated finish_time for FINISHED printers")

def start_background_tasks(socketio, app):
    from flask import request
    
    logging.debug("Starting background tasks")

    # Run deduplication on startup
    deduplicate_printers()
    deduplicate_orders()
    
    @socketio.on('connect')
    def handle_connect():
        logging.debug(f"Client connected: {request.sid}")
    
    # Ensure all FINISHED printers have finish_time
    ensure_finish_times()
    
    # Start enhanced Prusa ejection monitoring
    start_prusa_ejection_monitor()
    
    def run_status_updates():
        try:
            # First update Bambu printer states from MQTT data
            logging.debug("[FILAMENT DEBUG] Updating Bambu printer states before status update")
            update_bambu_printer_states()
            
            batch_size = Config.STATUS_BATCH_SIZE
            
            with ReadLock(printers_rwlock):
                total_printers = len(PRINTERS)
            
            if total_printers == 0:
                return
                
            batch_count = (total_printers + batch_size - 1) // batch_size
            
            loop = get_event_loop_for_thread()
            
            for batch_index in range(batch_count):
                loop.run_until_complete(
                    get_printer_status_async(socketio, app, batch_index, batch_size)
                )
                
                if batch_index < batch_count - 1:
                    time.sleep(Config.STATUS_BATCH_INTERVAL)
                    
        except Exception as e:
            logging.error(f"Error in status update task: {str(e)}")
    
    @socketio.on('status_update_request')
    def handle_status_update_request():
        thread = threading.Thread(target=run_status_updates)
        thread.daemon = True
        thread.start()
    
    threading.Timer(5.0, lambda: start_background_distribution(socketio, app)).start()
    
    def schedule_distribution():
        while True:
            try:
                time.sleep(30)
                start_background_distribution(socketio, app)
            except Exception as e:
                logging.error(f"Error in distribution scheduler: {str(e)}")
                time.sleep(60)
    
    distribution_thread = threading.Thread(target=schedule_distribution)
    distribution_thread.daemon = True
    distribution_thread.start()
    
    def schedule_status_updates():
        while True:
            try:
                run_status_updates()
                time.sleep(Config.STATUS_REFRESH_INTERVAL)
            except Exception as e:
                logging.error(f"Error in status update scheduler: {str(e)}")
                time.sleep(30)
    
    status_thread = threading.Thread(target=schedule_status_updates)
    status_thread.daemon = True
    status_thread.start()
    
    def schedule_order_reconciliation():
        while True:
            try:
                time.sleep(900)
                
                logging.debug("Starting automatic order count reconciliation (counts will only increase, never decrease)")
                corrections, changed_orders = reconcile_order_counts()
                
                if corrections > 0:
                    logging.info(f"Auto-reconciliation increased {corrections} order counts")
                    
                    with SafeLock(filament_lock):
                        total_filament = TOTAL_FILAMENT_CONSUMPTION / 1000
                    with SafeLock(orders_lock):
                        orders_data = ORDERS.copy()
                    with ReadLock(printers_rwlock):
                        printers_copy = prepare_printer_data_for_broadcast(PRINTERS)
                        
                    socketio.emit('status_update', {
                        'printers': printers_copy,
                        'total_filament': total_filament,
                        'orders': orders_data
                    })
            except Exception as e:
                logging.error(f"Error in order reconciliation scheduler: {str(e)}")
                time.sleep(300)
    
    reconciliation_thread = threading.Thread(target=schedule_order_reconciliation)
    reconciliation_thread.daemon = True
    reconciliation_thread.start()
    
    # Add periodic deduplication check
    dedup_thread = threading.Thread(target=lambda: periodic_deduplication_check(socketio, app))
    dedup_thread.daemon = True
    dedup_thread.start()
    
    logging.debug("Background tasks started")

def get_connection_pool():
    logging.warning("Direct pool access is deprecated, use async context manager instead")
    global CONNECTION_POOL
    if CONNECTION_POOL is None or CONNECTION_POOL.closed:
        logging.debug("Creating new aiohttp ClientSession")
        CONNECTION_POOL = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=20, ttl_dns_cache=300),
            timeout=aiohttp.ClientTimeout(total=Config.API_TIMEOUT)
        )
    return CONNECTION_POOL

@asynccontextmanager
async def get_session():
    session = aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=20, ttl_dns_cache=300),
        timeout=aiohttp.ClientTimeout(total=Config.API_TIMEOUT)
    )
    try:
        yield session
    finally:
        if not session.closed:
            await session.close()

async def close_connection_pool():
    global CONNECTION_POOL
    if CONNECTION_POOL is not None and not CONNECTION_POOL.closed:
        try:
            await CONNECTION_POOL.close()
            CONNECTION_POOL = None
            logging.debug("Successfully closed aiohttp connection pool")
        except Exception as e:
            logging.error(f"Error closing connection pool: {e}")
    
    # Clean up Bambu MQTT connections
    from services.state import cleanup_mqtt_connections
    cleanup_mqtt_connections()

async def async_send_ejection_gcode(session, printer, headers, ejection_url, gcode_content, gcode_file_name):
    printer_name = printer['name']
    
    # NOTE: We intentionally do NOT check ejection_in_progress here!
    # That flag is set by handle_finished_state_ejection to prevent job distribution,
    # but this function SHOULD run even when that flag is True.
    # The pending_ejection field (which is cleared after pickup) is the actual lock.
        
    logging.info(f"EJECTION: Starting actual file transfer for {printer_name}")
    async def _send_gcode():
        if printer.get('type') == 'bambu':
            # For Bambu printers, send G-code directly via MQTT
            logging.info(f"EJECTION: Sending G-code to Bambu printer {printer_name} via MQTT")
            try:
                success = send_bambu_ejection_gcode(printer, gcode_content)
                if success:
                    logging.info(f"EJECTION: Successfully sent G-code to Bambu printer {printer_name}")
                    
                    # Count and filament already incremented when print started
                    # Just log ejection completion
                    order_id = printer.get('order_id')
                    logging.info(f"✓ EJECTION COMPLETE for Bambu {printer_name} - count already incremented at print start")
                                
                    printer['file'] = None  # CLEAR FILE immediately after successful send
                    printer['order_id'] = None  # CLEAR ORDER_ID 
                    printer['ejection_processed'] = True
                    printer['last_ejection_time'] = time.time()
                    
                    # CRITICAL FIX: Mark ejection as complete and trigger immediate transition
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
                        "ejection_processed": False,  # Reset for next job
                        "ejection_in_progress": False, # Reset the in-progress flag
                        "ejection_start_time": None,
                        "finish_time": None,  # CLEAR THIS
                        "count_incremented_for_current_job": False # NEW: Reset count flag
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
            logging.info(f"EJECTION: Uploading G-code to Prusa printer {printer_name} at {ejection_url}")
            try:
                async with session.put(
                    ejection_url,
                    data=gcode_content.encode('utf-8'),
                    headers={**headers, "Print-After-Upload": "?1"}
                ) as upload_resp:
                    logging.info(f"EJECTION: Upload response for {printer_name}: HTTP {upload_resp.status}")
                    if upload_resp.status == 201:
                        logging.info(f"EJECTION: Successfully uploaded and started ejection on {printer_name}")

                        # Count and filament already incremented when print started
                        # Just log ejection completion
                        order_id = printer.get('order_id')
                        logging.info(f"✓ EJECTION UPLOAD for Prusa {printer_name} - count already incremented at print start")

                        # CRITICAL FIX: Keep the ejection file name for tracking
                        printer['file'] = gcode_file_name 
                        printer['order_id'] = None  # CLEAR ORDER_ID (after incrementing!)
                        printer['ejection_processed'] = True
                        printer['last_ejection_time'] = time.time()
                        
                        # Don't immediately transition - let monitoring detect completion
                        set_printer_ejection_state(printer_name, 'running')
                        
                        logging.info(f"EJECTION STARTED: {printer_name} - G-code uploaded and printing")
                        return True
                    else:
                        response_text = await upload_resp.text()
                        logging.error(f"EJECTION: Failed to upload to {printer_name}: HTTP {upload_resp.status}, Response: {response_text}")
                        # On failure, release lock and reset in_progress
                        release_ejection_lock(printer_name)
                        # Don't reset ejection_in_progress here - let it stay so monitoring can clean up
                        return False
            except Exception as e:
                logging.error(f"EJECTION: Exception uploading to Prusa {printer_name}: {str(e)}")
                # On exception, release lock
                release_ejection_lock(printer_name)
                return False
    
    try:
        success = await retry_async(_send_gcode, max_retries=2, initial_backoff=1)
        if not success:
            logging.warning(f"EJECTION: All attempts failed for {printer_name}")
            # Mark as failed but let monitoring handle cleanup
            set_printer_ejection_state(printer_name, 'failed')
            release_ejection_lock(printer_name)
        else:
            logging.info(f"EJECTION: Successfully started for {printer_name}")
    except Exception as e:
        logging.error(f"EJECTION: Final error for {printer_name}: {str(e)}")
        set_printer_ejection_state(printer_name, 'failed')
        release_ejection_lock(printer_name)

def convert_mm_to_g(filament_mm, density):
    filament_radius = 1.75 / 2
    volume_cm3 = (3.14159 * (filament_radius ** 2) * (filament_mm / 10)) / 1000
    return volume_cm3 * density

def extract_filament_from_file(filepath, is_bgcode=False):
    filament_g = 0
    filament_mm = 0
    
    # Check if it's a .3mf file
    if filepath.endswith('.3mf'):
        try:
            import zipfile
            import xml.etree.ElementTree as ET
            
            # .3mf files are ZIP archives
            with zipfile.ZipFile(filepath, 'r') as zip_file:
                # Look for Metadata/Slic3r_PE.config or similar files
                for filename in zip_file.namelist():
                    if 'gcode' in filename.lower() and filename.endswith('.gcode'):
                        # Found a gcode file inside the 3mf
                        with zip_file.open(filename) as gcode_file:
                            content = gcode_file.read().decode('utf-8', errors='ignore')
                            for line in content.splitlines()[:100]:  # Check first 100 lines
                                if 'filament used [mm]' in line:
                                    filament_mm = float(line.split('=')[-1].strip())
                                elif 'filament used [g]' in line:
                                    filament_g = float(line.split('=')[-1].strip())
                                if filament_g > 0:
                                    break
                            if filament_g > 0:
                                break
                # If no filament found in gcode, try to extract from filename
                # e.g., "6_gram_vase.gcode.3mf" -> 6 grams
                if filament_g == 0:
                    import re
                    base_name = os.path.basename(filepath)
                    match = re.search(r'(\d+)_gram', base_name)
                    if match:
                        filament_g = float(match.group(1))
                        logging.info(f"Extracted filament from filename: {filament_g}g")
                        
        except Exception as e:
            logging.error(f"Error parsing filament from .3mf file {filepath}: {str(e)}")
            # Try to extract from filename as fallback
            import re
            base_name = os.path.basename(filepath)
            match = re.search(r'(\d+)_gram', base_name)
            if match:
                filament_g = float(match.group(1))
                logging.info(f"Extracted filament from filename pattern: {filament_g}g")
    else:
        # Original code for .gcode files
        try:
            with open(filepath, 'rb') as f:
                header = f.read(1024).decode('utf-8', errors='ignore')
                for line in header.splitlines():
                    if 'filament used [mm]' in line:
                        filament_mm = float(line.split('=')[-1].strip())
                    elif 'filament used [g]' in line:
                        filament_g = float(line.split('=')[-1].strip())
                if filament_g == 0 and filament_mm > 0:
                    filament_g = convert_mm_to_g(filament_mm, Config.DEFAULT_FILAMENT_DENSITY)
        except Exception as e:
            logging.error(f"Error parsing filament from {filepath}: {str(e)}")
    
    logging.debug(f"Extracted filament from {filepath}: {filament_g}g")
    return filament_g

async def fetch_status(session, printer):
    # Check if this is a Bambu printer
    if printer.get('type') == 'bambu':
        return get_bambu_status(printer)
    
    # Original Prusa code continues below
    url = f"http://{printer['ip']}/api/v1/status"
    headers = {"X-Api-Key": decrypt_api_key(printer['api_key'])}
    logging.debug(f"Fetching status for {printer['name']} at {url}")
    
    async def _fetch():
        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logging.debug(f"Successfully fetched status for {printer['name']}: {data['printer']['state']}")
                    return printer, data
                logging.warning(f"Failed to fetch status for {printer['name']}: HTTP {resp.status}")
                return printer, None
        except aiohttp.ClientError as e:
            logging.warning(f"Client error for {printer['name']}: {str(e)}")
            return printer, None
        except asyncio.CancelledError:
            logging.warning(f"Request cancelled for {printer['name']}")
            return printer, None
        except Exception as e:
            logging.error(f"Unexpected error for {printer['name']}: {str(e)}")
            return printer, None
    
    try:
        return await retry_async(_fetch, max_retries=2, initial_backoff=1)
    except Exception as e:
        logging.error(f"Error fetching status for {printer['name']} after retries: {str(e)}")
        return printer, None

async def stop_print(session, printer):
    # Check if this is a Bambu printer
    if printer.get('type') == 'bambu':
        success = stop_bambu_print(printer)
        if success:
            printer.update({
                "state": "IDLE",
                "status": "Idle",
                "progress": 0,
                "time_remaining": 0,
                "file": None,
                "job_id": None,
                "order_id": None,
                "from_queue": False,
                "count_incremented_for_current_job": False # NEW: Reset count flag
            })
        return success
    
    # Prusa API - try both v1 and legacy endpoints
    headers = {"X-Api-Key": decrypt_api_key(printer['api_key'])}
    
    async def _stop():
        # First try the v1 API endpoint
        url = f"http://{printer['ip']}/api/v1/job"
        try:
            async with session.post(url, 
                                  headers=headers, 
                                  json={"command": "cancel"}) as resp:
                if resp.status == 200:
                    logging.debug(f"Successfully stopped print on {printer['name']} using v1 API")
                    printer.update({
                        "state": "IDLE",
                        "status": "Idle",
                        "progress": 0,
                        "time_remaining": 0,
                        "file": None,
                        "job_id": None,
                        "order_id": None,
                        "from_queue": False,
                        "count_incremented_for_current_job": False # NEW: Reset count flag
                    })
                    return True
                elif resp.status == 405:
                    # Method not allowed - try the legacy endpoint
                    logging.debug(f"v1 API returned 405, trying legacy API for {printer['name']}")
        except Exception as e:
            logging.debug(f"v1 API error: {str(e)}, trying legacy API")
        
        # Try legacy API endpoint
        legacy_url = f"http://{printer['ip']}/api/job"
        try:
            async with session.post(legacy_url,
                                  headers=headers,
                                  json={"command": "cancel"}) as resp:
                success = resp.status in [200, 204]
                if success:
                    logging.debug(f"Successfully stopped print on {printer['name']} using legacy API")
                    printer.update({
                        "state": "IDLE",
                        "status": "Idle",
                        "progress": 0,
                        "time_remaining": 0,
                        "file": None,
                        "job_id": None,
                        "order_id": None,
                        "from_queue": False,
                        "count_incremented_for_current_job": False # NEW: Reset count flag
                    })
                else:
                    logging.error(f"Failed to stop print on {printer['name']}: HTTP {resp.status}")
                return success
        except Exception as e:
            logging.error(f"Failed to stop print on {printer['name']}: {str(e)}")
            return False
    
    try:
        return await retry_async(_stop, max_retries=2, initial_backoff=1)
    except Exception as e:
        logging.error(f"Error stopping print on {printer['name']} after retries: {str(e)}")
        return False

async def reset_printer_state(session, printer, headers):
    logging.debug(f"Attempting to reset state for printer {printer['name']}")
    
    try:
        try:
            async with session.post(f"http://{printer['ip']}/api/v1/job", 
                                  headers=headers, 
                                  json={"command": "cancel"}) as resp:
                if resp.status == 200:
                    logging.debug(f"Successfully cancelled any active job on {printer['name']}")
                    await asyncio.sleep(3)
                elif resp.status == 404:
                    logging.debug(f"No active job to cancel on {printer['name']}")
                else:
                    logging.error(f"Error cancelling job on {printer['name']}: HTTP {resp.status}")
        except Exception as e:
            logging.error(f"Error cancelling job: {str(e)}")
            
        try:
            async with session.post(f"http://{printer['ip']}/api/v1/connection", 
                                  headers=headers, 
                                  json={"command": "connect"}) as resp:
                logging.debug(f"Refreshed connection on {printer['name']}: {resp.status}")
                await asyncio.sleep(2)
        except Exception as e:
            logging.error(f"Error refreshing connection: {str(e)}")
                
        return True
    except Exception as e:
        logging.error(f"Error resetting printer state: {str(e)}")
        return False

async def reset_printer_state_async(session, printer):
    if printer.get('type') == 'bambu':
        # Bambu printer reset not implemented
        logging.warning(f"Reset not implemented for Bambu printer {printer['name']}")
        return False
        
    headers = {"X-Api-Key": decrypt_api_key(printer["api_key"])}
    
    log_state_transition(
        printer['name'],
        printer.get('state', 'UNKNOWN'),
        'RESETTING',
        'MANUAL_RESET_ATTEMPT',
        {'reason': 'User initiated reset'}
    )
    
    return await reset_printer_state(session, printer, headers)

def match_shortened_filename(full_filename, shortened_filename):
    if not full_filename or not shortened_filename:
        return False
        
    full_base = os.path.splitext(os.path.basename(full_filename))[0]
    short_base = os.path.splitext(os.path.basename(shortened_filename))[0]
    
    if full_base.upper() == short_base.upper():
        return True
        
    if len(short_base) >= 6 and short_base[:6].upper() == full_base[:6].upper() and '~' in short_base:
        return True
        
    if len(short_base) >= 3 and full_base.upper().startswith(short_base[:3].upper()):
        return True
        
    if len(short_base) >= 8 and short_base[:8].upper() == full_base[:8].upper():
        return True
        
    if short_base.upper() in full_base.upper() or full_base.upper() in short_base.upper():
        return True
        
    return False

async def verify_print_started(session, printer, filename, headers, max_attempts=3, initial_delay=20):
    if '/' in filename:
        base_filename = os.path.basename(filename)  
    else:
        base_filename = filename
        
    logging.debug(f"Starting verification for {printer['name']} with file {base_filename}")
    
    logging.debug(f"Starting verification for {printer['name']} with {max_attempts} attempts, waiting {initial_delay}s first")
    await asyncio.sleep(initial_delay)
    
    for attempt in range(max_attempts):
        try:
            async with session.get(f"http://{printer['ip']}/api/v1/status", headers=headers) as status_resp:
                if status_resp.status == 200:
                    status_data = await status_resp.json()
                    printer_state = status_data['printer']['state']
                    if printer_state in ['PRINTING', 'BUSY']:
                        logging.debug(f"Verified {printer['name']} is in {printer_state} state")
                        
                        async with session.get(f"http://{printer['ip']}/api/v1/job", headers=headers) as job_resp:
                            if job_resp.status == 200:
                                job_data = await job_resp.json()
                                job_filename = job_data.get('file', {}).get('name')
                                if job_filename and (job_filename == base_filename or 
                                                    match_shortened_filename(base_filename, job_filename)):
                                    logging.debug(f"Verified {printer['name']} is printing file {base_filename}")
                                    return True
                                if printer.get('state') in ['IDLE', 'READY', 'FINISHED', 'OFFLINE']:
                                    logging.debug(f"Printer {printer['name']} was previously idle and is now printing - considering SUCCESS")
                                    return True
                        if printer.get('state') in ['IDLE', 'READY', 'FINISHED', 'OFFLINE']:
                            logging.debug(f"Printer {printer['name']} state changed from idle to {printer_state} - considering SUCCESS")
                            return True
                    else:
                        if status_data['printer']['state'] in ['BUSY', 'PROCESSING', 'UPLOADING']:
                            logging.debug(f"Printer {printer['name']} still processing. State: {status_data['printer']['state']}")
                        else:
                            logging.debug(f"Printer {printer['name']} state is {status_data['printer']['state']}, not PRINTING or BUSY")
            
            if attempt < max_attempts - 1:
                wait_time = 10 * (1.5 ** attempt)
                logging.debug(f"Verification attempt {attempt+1}/{max_attempts} failed, waiting {wait_time}s before retry...")
                await asyncio.sleep(wait_time)
            
        except Exception as e:
            logging.error(f"Error in verification for {printer['name']}: {str(e)}")
            if attempt < max_attempts - 1:
                await asyncio.sleep(10)
        
    logging.debug(f"All verification attempts failed for {printer['name']}")
    return False

async def get_printer_status_async(socketio, app, batch_index=None, batch_size=None):
    global TOTAL_FILAMENT_CONSUMPTION
    
    # Clear any stuck ejection locks before processing
    clear_stuck_ejection_locks()
    
    # Update Bambu printer states first
    update_bambu_printer_states()
    
    if batch_size is None:
        batch_size = Config.STATUS_BATCH_SIZE
    
    printers_to_process = []
    printer_indices = []
    
    with ReadLock(printers_rwlock):
        all_printers = [p.copy() for p in PRINTERS if not p.get('service_mode', False)]
    
    if batch_index is not None:
        start_idx = batch_index * batch_size
        end_idx = min(start_idx + batch_size, len(all_printers))
        
        for i in range(start_idx, end_idx):
            if i < len(all_printers):
                printer_copy = all_printers[i]
                
                # Build minimal printer object based on printer type
                minimal_printer = {
                    'name': printer_copy['name'],
                    'ip': printer_copy['ip'],
                    'state': printer_copy.get('state', 'Unknown'),
                    'manually_set': printer_copy.get('manually_set', False),
                    'file': printer_copy.get('file', ''),
                    'order_id': printer_copy.get('order_id'),
                    'ejection_processed': printer_copy.get('ejection_processed', False),
                    'ejection_in_progress': printer_copy.get('ejection_in_progress', False), # Include in_progress
                    'manual_timeout': printer_copy.get('manual_timeout', 0),
                    'type': printer_copy.get('type', 'prusa'),  # Include printer type
                    'last_ejection_time': printer_copy.get('last_ejection_time', 0),  # Include ejection time
                    'finish_time': printer_copy.get('finish_time'), # Include finish time
                    'count_incremented_for_current_job': printer_copy.get('count_incremented_for_current_job', False) # NEW: Include count flag
                }
                
                # Only add api_key for Prusa printers
                if printer_copy.get('type') != 'bambu':
                    minimal_printer['api_key'] = printer_copy.get('api_key')
                else:
                    # For Bambu printers, include their specific fields
                    minimal_printer['device_id'] = printer_copy.get('device_id')
                    minimal_printer['serial_number'] = printer_copy.get('serial_number')
                    minimal_printer['access_code'] = printer_copy.get('access_code')
                
                printers_to_process.append(minimal_printer)
                printer_indices.append(i)
    else:
        for i, printer in enumerate(all_printers):
            # Build minimal printer object based on printer type
            minimal_printer = {
                'name': printer['name'],
                'ip': printer['ip'],
                'state': printer.get('state', 'Unknown'),
                'manually_set': printer.get('manually_set', False),
                'file': printer.get('file', ''),
                'order_id': printer.get('order_id'),
                'ejection_processed': printer.get('ejection_processed', False),
                'ejection_in_progress': printer.get('ejection_in_progress', False), # Include in_progress
                'manual_timeout': printer.get('manual_timeout', 0),
                'type': printer.get('type', 'prusa'),  # Include printer type
                'last_ejection_time': printer.get('last_ejection_time', 0),  # Include ejection time
                'finish_time': printer.get('finish_time'), # Include finish time
                'count_incremented_for_current_job': printer.get('count_incremented_for_current_job', False) # NEW: Include count flag
            }
            
            # Only add api_key for Prusa printers
            if printer.get('type') != 'bambu':
                minimal_printer['api_key'] = printer.get('api_key')
            else:
                # For Bambu printers, include their specific fields
                minimal_printer['device_id'] = printer.get('device_id')
                minimal_printer['serial_number'] = printer.get('serial_number')
                minimal_printer['access_code'] = printer.get('access_code')
            
            printers_to_process.append(minimal_printer)
            printer_indices.append(i)
    
    if not printers_to_process:
        logging.debug(f"No printers to process in batch {batch_index}")
        return
    
    await asyncio.sleep(0.01)
    
    printer_updates = []
    ejection_tasks = []
    
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=20, ttl_dns_cache=300),
        timeout=aiohttp.ClientTimeout(total=Config.API_TIMEOUT)
    ) as session:
        for idx, p in enumerate(printers_to_process):
            if p.get('manually_set', False):
                logging.debug(f"Processing manually set printer {p['name']}: Current state={p.get('state', 'Unknown')}")
        
        tasks = [fetch_status(session, p) for p in printers_to_process]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                logging.error(f"Error fetching status for {printers_to_process[idx]['name']}: {str(result)}")
                printer_updates.append({
                    'index': printer_indices[idx],
                    'updates': {
                        "state": "OFFLINE",
                        "status": "Offline",
                        "temps": {"nozzle": 0, "bed": 0},
                        "progress": 0,
                        "time_remaining": 0,
                        "file": "None",
                        "job_id": None,
                        "manually_set": False,
                        "ejection_in_progress": False, # Reset in_progress on offline
                        "finish_time": None, # Clear finish time on offline
                        "count_incremented_for_current_job": False # NEW: Reset count flag
                    }
                })
                continue
                
            printer, data = result
            if data:
                api_state = data['printer']['state']
                manually_set = printer.get('manually_set', False)
                current_state = printer.get('state', 'Unknown')
                ejection_processed = printer.get('ejection_processed', False)
                ejection_in_progress = printer.get('ejection_in_progress', False) # Get in_progress
                current_file = printer.get('file', '')
                current_order_id = printer.get('order_id')
                
                with ReadLock(printers_rwlock):
                    if printer_indices[idx] < len(PRINTERS):
                        database_state = PRINTERS[printer_indices[idx]].get('state', 'Unknown')
                        database_ejection_processed = PRINTERS[printer_indices[idx]].get('ejection_processed', False)
                        logging.debug(f"Printer {printer['name']}: API state={api_state}, Copied state={current_state}, Database state={database_state}, manually_set={manually_set}, ejection_processed={ejection_processed}, db_ejection_processed={database_ejection_processed}, ejection_in_progress={ejection_in_progress}")
                
                updates = {}
                
                if manually_set and api_state not in ['PRINTING', 'EJECTING']:
                    # CRITICAL FIX: Allow FINISHED state even when manually_set=True
                    # This ensures ejection logic can run for completed prints
                    if api_state == 'FINISHED':
                        logging.debug(f"Printer {printer['name']} has finished printing, using enhanced FINISHED handler")
                        handle_finished_state_ejection(printer, printer['name'], current_file, current_order_id, updates)
                        
                        # If ejection was started (Prusa logic updates main PRINTERS list directly), 
                        # ensure the local updates dictionary reflects the new state for the printer_updates list.
                        if updates.get('state') == 'EJECTING':
                            updates['ejection_in_progress'] = True
                        
                    else:
                        manual_timeout = printer.get('manual_timeout', 0)
                        current_time = time.time()
                        if manual_timeout > 0 and current_time < manual_timeout:
                            logging.debug(f"Manual state timeout active for {printer['name']}, preserving READY state")
                            updates = {
                                "state": "READY",
                                "status": "Ready",
                                "temps": {"bed": data['printer'].get('temp_bed', 0), "nozzle": data['printer'].get('temp_nozzle', 0)},
                                "z_height": data['printer'].get('axis_z', 0),
                                "progress": 0,
                                "time_remaining": 0,
                                "file": None,
                                "job_id": None,
                                "manually_set": True,
                                "ejection_processed": ejection_processed,
                                "ejection_in_progress": False,
                                "count_incremented_for_current_job": printer.get('count_incremented_for_current_job', False) # NEW: Preserve count flag
                            }
                        else:
                            logging.debug(f"Preserving manually set state for {printer['name']} despite API state {api_state}")
                            updates = {
                                "state": "READY",
                                "status": "Ready",
                                "temps": {"bed": data['printer'].get('temp_bed', 0), "nozzle": data['printer'].get('temp_nozzle', 0)},
                                "z_height": data['printer'].get('axis_z', 0),
                                "progress": 0,
                                "time_remaining": 0,
                                "file": None,
                                "job_id": None,
                                "manually_set": True,
                                "ejection_processed": ejection_processed,
                                "ejection_in_progress": False,
                                "count_incremented_for_current_job": printer.get('count_incremented_for_current_job', False) # NEW: Preserve count flag
                            }
                elif ejection_processed and current_state == 'READY':
                    logging.debug(f"Preserving READY state for {printer['name']} due to prior ejection, ignoring API state {api_state}")
                    updates = {
                        "state": 'READY',
                        "status": 'Ready',
                        "temps": {"bed": data['printer'].get('temp_bed', 0), "nozzle": data['printer'].get('temp_nozzle', 0)},
                        "z_height": data['printer'].get('axis_z', 0),
                        "progress": 0,
                        "time_remaining": 0,
                        "file": None,
                        "job_id": None,
                        "order_id": None,
                        "ejection_processed": True,
                        "ejection_in_progress": False,
                        "manually_set": True,
                        "count_incremented_for_current_job": printer.get('count_incremented_for_current_job', False) # NEW: Preserve count flag
                    }
                # Check for in-progress ejection which hasn't finished file upload yet
                elif ejection_in_progress and current_state == 'EJECTING' and api_state in ['IDLE', 'READY', 'OPERATIONAL', 'FINISHED']:
                    logging.debug(f"Maintaining EJECTING state for {printer['name']} as ejection is in progress internally, ignoring API state {api_state}")
                    updates = {
                        "state": 'EJECTING',
                        "status": 'Ejecting',
                        "temps": {"bed": data['printer'].get('temp_bed', 0), "nozzle": data['printer'].get('temp_nozzle', 0)},
                        "z_height": data['printer'].get('axis_z', 0),
                        "progress": 0,
                        "time_remaining": 0,
                        "file": current_file,
                        "job_id": None,
                        "manually_set": False,
                        "ejection_processed": ejection_processed,
                        "ejection_in_progress": ejection_in_progress,
                        "count_incremented_for_current_job": printer.get('count_incremented_for_current_job', False) # NEW: Preserve count flag
                    }
                elif current_state == 'EJECTING' and api_state == 'PRINTING' and current_file and 'ejection_' in current_file:
                    logging.debug(f"Maintaining EJECTING state for {printer['name']} as API reports PRINTING for ejection file {current_file}")
                    updates = {
                        "state": 'EJECTING',
                        "status": 'Ejecting',
                        "temps": {"bed": data['printer'].get('temp_bed', 0), "nozzle": data['printer'].get('temp_nozzle', 0)},
                        "z_height": data['printer'].get('axis_z', 0),
                        "progress": 0,
                        "time_remaining": 0,
                        "file": current_file,
                        "job_id": None,
                        "manually_set": False,
                        "ejection_processed": ejection_processed,
                        "ejection_in_progress": ejection_in_progress,
                        "count_incremented_for_current_job": printer.get('count_incremented_for_current_job', False) # NEW: Preserve count flag
                    }
                else:
                    # Handle Bambu printer state mapping
                    if printer.get('type') == 'bambu' and api_state in ['PREPARING']:
                        api_state = 'PREPARE'  # Normalize Bambu state
                    updates = {
                        "state": api_state,
                        "status": state_map.get(api_state, 'Unknown'),
                        "temps": {"bed": data['printer'].get('temp_bed', 0), "nozzle": data['printer'].get('temp_nozzle', 0)},
                        "z_height": data['printer'].get('axis_z', 0),
                        "ejection_in_progress": False # Reset the in-progress flag if state isn't EJECTING
                    }
                    # Log API polling discrepancy if states don't match
                    if api_state != current_state:
                        log_api_poll_event(
                            printer['name'],
                            api_state,
                            current_state,
                            'state_update' if not manually_set else 'manual_override',
                            {
                                'manually_set': manually_set,
                                'ejection_processed': ejection_processed
                            }
                        )
                
                    if api_state in ['PRINTING', 'PAUSED']:
                        # Only fetch job details for Prusa printers
                        if printer.get('type') != 'bambu':
                            headers = {"X-Api-Key": decrypt_api_key(printer['api_key'])}
                            try:
                                async with session.get(f"http://{printer['ip']}/api/v1/job", headers=headers) as job_res:
                                    if job_res.status == 200:
                                        job_data = await job_res.json()
                                        updates.update({
                                            "progress": job_data.get('progress', 0),
                                            "time_remaining": job_data.get('time_remaining', 0),
                                            "file": job_data.get('file', {}).get('display_name', 'Unknown'),
                                            "job_id": job_data.get('id'),
                                            "manually_set": manually_set,
                                            "ejection_processed": False,  # RESET when new print starts
                                            "ejection_in_progress": False,
                                            "finish_time": None, # Clear finish time on a new print
                                            "count_incremented_for_current_job": printer.get('count_incremented_for_current_job', False) # NEW: Preserve count flag
                                        })
                                    else:
                                        updates.update({"progress": 0, "time_remaining": 0, "file": "None", "job_id": None})
                            except Exception as e:
                                logging.error(f"Error fetching job for {printer['name']}: {str(e)}")
                                updates.update({"progress": 0, "time_remaining": 0, "file": "None", "job_id": None})
                        else:
                            # For Bambu printers, the job info comes from MQTT status updates
                            # The progress, time_remaining, and file info should already be in the data
                            updates.update({
                                "progress": data.get('progress', 0),
                                "time_remaining": data.get('time_remaining', 0),
                                "file": data.get('file', {}).get('display_name', data.get('file', 'Unknown')),
                                "job_id": None,  # Bambu doesn't use job IDs in the same way
                                "manually_set": manually_set,
                                "ejection_processed": False,  # RESET when new print starts
                                "ejection_in_progress": False,
                                "finish_time": None, # Clear finish time on a new print
                                "count_incremented_for_current_job": printer.get('count_incremented_for_current_job', False) # NEW: Preserve count flag
                            })
                    elif api_state == 'FINISHED':
                        # Use the enhanced FINISHED handler
                        handle_finished_state_ejection(printer, printer['name'], current_file, current_order_id, updates)
                        
                        # Add ejection tasks if needed
                        if updates.get('state') == 'EJECTING':
                            updates['ejection_in_progress'] = True
                        
                    elif api_state in ['IDLE', 'FINISHED', 'OPERATIONAL']:
                        original_printer_index = printer_indices[idx]
                        with ReadLock(printers_rwlock):
                            if 0 <= original_printer_index < len(PRINTERS):
                                stored_state = PRINTERS[original_printer_index].get('state', 'Unknown')
                                stored_finish_time = PRINTERS[original_printer_index].get('finish_time')
                                
                                logging.debug(f"Checking printer {printer['name']}: API state={api_state}, stored state={stored_state}, stored_finish_time={stored_finish_time}")
                                
                                # Preserve finish_time if it exists
                                if stored_finish_time:
                                    updates['finish_time'] = stored_finish_time
                                    logging.debug(f"Preserving existing finish_time for {printer['name']}: {stored_finish_time}")
                                elif stored_state == 'FINISHED' or api_state == 'FINISHED':
                                    # If printer is in FINISHED state but no finish_time, set it now
                                    finish_time = time.time()
                                    updates['finish_time'] = finish_time
                                    logging.info(f"Setting new finish_time for {printer['name']}: {finish_time}")
                                else:
                                    # Only clear finish_time if transitioning away from FINISHED state
                                    if stored_state == 'FINISHED' and api_state not in ['FINISHED', 'EJECTING']:
                                        updates['finish_time'] = None
                                        logging.info(f"Clearing finish_time for {printer['name']} - transitioning from FINISHED to {api_state}")
                                    else:
                                        updates['finish_time'] = None

                                # UPDATED LOGIC: Auto-transition FINISHED -> IDLE -> READY on manual reset
                                if stored_state == 'FINISHED' and api_state in ['IDLE', 'OPERATIONAL']:
                                    logging.info(f"Printer {printer['name']} manually reset from FINISHED to {api_state} - transitioning to READY")
                                    log_state_transition(
                                        printer['name'],
                                        'FINISHED',
                                        'READY',
                                        'MANUAL_RESET_DETECTED',
                                        {'api_state': api_state, 'reason': 'Manual reset detected, auto-transitioning to READY'}
                                    )
                                    updates.update({
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
                                        "finish_time": None,  # Clear finish time
                                        "count_incremented_for_current_job": False # NEW: Reset count flag
                                    })
                                    # Trigger distribution to assign new jobs
                                    threading.Timer(2.0, lambda: start_background_distribution(socketio, app)).start()
                                elif stored_state == 'EJECTING':
                                    logging.warning(f"IMPORTANT: Printer {printer['name']} completed ejection (API={api_state}), transitioning from EJECTING to READY")
                                    updates.update({
                                        "state": 'READY',
                                        "status": 'Ready',
                                        "progress": 0,
                                        "time_remaining": 0,
                                        "file": None,               # CLEAR FILE
                                        "job_id": None,
                                        "order_id": None,           # Clear order ID
                                        "manually_set": True,
                                        "ejection_processed": False,  # Reset for next job
                                        "ejection_in_progress": False, # Reset the in-progress flag
                                        "ejection_start_time": None,
                                        "last_ejection_time": time.time(),
                                        "finish_time": None, # Clear finish time on ejection complete
                                        "count_incremented_for_current_job": False # NEW: Reset count flag
                                    })
                                    # Clean up ejection state
                                    release_ejection_lock(printer['name'])
                                    clear_printer_ejection_state(printer['name'])
                                else:
                                    # Only update to IDLE if we're not in a protected state
                                    updates.update({
                                        "state": api_state,
                                        "status": state_map.get(api_state, 'Unknown'),
                                        "progress": 0,
                                        "time_remaining": 0,
                                        "file": "None",
                                        "job_id": None,
                                        "manually_set": False,
                                        "ejection_in_progress": False,
                                        "count_incremented_for_current_job": False # NEW: Reset count flag
                                    })
                    elif api_state not in ['PRINTING', 'PAUSED', 'FINISHED', 'EJECTING']:
                        updates.update({"progress": 0, "time_remaining": 0, "file": "None", "job_id": None, "manually_set": False, "finish_time": None, "ejection_in_progress": False, "count_incremented_for_current_job": False}) # NEW: Reset count flag
                
                printer_updates.append({
                    'index': printer_indices[idx],
                    'updates': updates
                })
                
                # FIX: Execute pending Prusa ejection tasks here
                if updates.get('state') == 'EJECTING':
                    # Check if printer has pending ejection details
                    with ReadLock(printers_rwlock):
                        original_printer = PRINTERS[printer_indices[idx]]
                        pending_ejection = original_printer.get('pending_ejection')
                        
                    if pending_ejection and printer.get('type') != 'bambu':
                        # Prusa ejection - use stored details
                        gcode_content = pending_ejection['gcode_content']
                        gcode_file_name = pending_ejection['gcode_file_name']
                        headers = {"X-Api-Key": decrypt_api_key(printer['api_key'])}
                        ejection_file_path = f"/usb/{gcode_file_name}"
                        ejection_url = f"http://{printer['ip']}/api/v1/files{ejection_file_path}"
                        
                        ejection_tasks.append(async_send_ejection_gcode(
                            session, printer, headers, ejection_url, 
                            gcode_content, gcode_file_name
                        ))
                        
                        # Clear pending ejection after queuing
                        with WriteLock(printers_rwlock):
                            # The check is redundant as we hold the lock, but safer to be explicit
                            if printer_indices[idx] < len(PRINTERS): 
                                PRINTERS[printer_indices[idx]]['pending_ejection'] = None
                                logging.info(f"EJECTION: Queued pending ejection task for {printer['name']}")
            else:
                printer_updates.append({
                    'index': printer_indices[idx],
                    'updates': {
                        "state": "OFFLINE",
                        "status": "Offline",
                        "temps": {"nozzle": 0, "bed": 0},
                        "progress": 0,
                        "time_remaining": 0,
                        "file": "None",
                        "job_id": None,
                        "manually_set": False,
                        "ejection_in_progress": False,
                        "finish_time": None, # Clear finish time on offline
                        "count_incremented_for_current_job": False # NEW: Reset count flag
                    }
                })
        
        if ejection_tasks:
            logging.info(f"EJECTION: Executing {len(ejection_tasks)} ejection tasks")
            ejection_results = await asyncio.gather(*ejection_tasks, return_exceptions=True)
            
            # Log results of ejection tasks
            for i, result in enumerate(ejection_results):
                if isinstance(result, Exception):
                    logging.error(f"EJECTION: Task {i} failed with exception: {str(result)}")
                else:
                    logging.info(f"EJECTION: Task {i} completed successfully")
        else:
            logging.debug("EJECTION: No ejection tasks to execute")
        
    with WriteLock(printers_rwlock):
        for update in printer_updates:
            if 0 <= update['index'] < len(PRINTERS):
                current_manually_set = PRINTERS[update['index']].get('manually_set', False)
                new_manually_set = update['updates'].get('manually_set', current_manually_set)
                if current_manually_set and not new_manually_set and update['updates'].get('state') != 'PRINTING':
                    logging.warning(f"WARNING: Printer {PRINTERS[update['index']]['name']} manually_set changing from True to False! Current state: {PRINTERS[update['index']]['state']}, new state: {update['updates'].get('state')}")
                    if current_manually_set and PRINTERS[update['index']]['state'] == 'READY':
                        logging.warning(f"Preventing manual flag from being cleared for READY printer {PRINTERS[update['index']]['name']}")
                        update['updates']['manually_set'] = True
                
                if (PRINTERS[update['index']].get('state') == 'READY' and 
                    update['updates'].get('state') == 'FINISHED' and
                    (PRINTERS[update['index']].get('file') is None or PRINTERS[update['index']].get('ejection_processed', False))):
                    logging.debug(f"Preserving READY state for {PRINTERS[update['index']]['name']} despite API FINISHED state")
                    update['updates']['state'] = 'READY'
                    update['updates']['status'] = 'Ready'
                    update['updates']['manually_set'] = True
                
                for key, value in update['updates'].items():
                    PRINTERS[update['index']][key] = value
        
        for i, printer in enumerate(PRINTERS):
            if printer.get('manually_set', False) and printer.get('state') not in ['READY', 'PRINTING', 'EJECTING']:
                logging.warning(f"Failsafe: Fixing printer {printer['name']} - has manually_set=True but state={printer['state']}. Setting back to READY")
                printer['state'] = 'READY'
                printer['status'] = 'Ready'
                printer['manually_set'] = True
                printer['count_incremented_for_current_job'] = False # NEW: Reset count flag on failsafe
        
        # Enhanced ejection completion monitoring - FIXED VERSION
        for i, printer in enumerate(PRINTERS):
            if printer.get('state') == 'EJECTING':
                printer_name = printer['name']
                printer_type = printer.get('type', 'prusa')
                current_time = time.time()
                ejection_start = printer.get('ejection_start_time', 0)
                elapsed_minutes = (current_time - ejection_start) / 60.0 if ejection_start else 0
                
                # Get the corresponding API update for this printer
                api_state = None
                current_api_file = None
                
                for update in printer_updates:
                    if update['index'] == i:
                        api_state = update['updates'].get('state')
                        current_api_file = update['updates'].get('file', '')
                        break
                
                logging.debug(f"Ejection check for {printer_name} (type: {printer_type}): api_state={api_state}, api_file='{current_api_file}', stored_file='{printer.get('file', '')}', elapsed={elapsed_minutes:.1f}min")
                
                ejection_complete = False
                completion_reason = ""
                
                # ENHANCED COMPLETION DETECTION
                
                # Method 1: Check ejection state manager first (highest priority)
                ejection_state = get_printer_ejection_state(printer_name)
                if ejection_state['state'] == 'completed':
                    ejection_complete = True
                    completion_reason = "State manager shows completed"
                
                # Method 2: API shows clear completion states
                elif api_state in ['IDLE', 'READY', 'OPERATIONAL']:
                    ejection_complete = True
                    completion_reason = f"API state = {api_state}"
                
                # Method 3: For Prusa printers - enhanced file-based detection
                elif printer_type != 'bambu':
                    stored_file = printer.get('file', '')
                    
                    # Check if we were running an ejection file and it's no longer active
                    if stored_file and 'ejection_' in stored_file:
                        if not current_api_file or current_api_file != stored_file:
                            ejection_complete = True
                            completion_reason = f"Ejection file '{stored_file}' no longer active (current: '{current_api_file}')"
                    
                    # Also check if API reports FINISHED (common with Prusa after ejection)
                    elif api_state == 'FINISHED':
                        # For Prusa, FINISHED often means ejection completed
                        ejection_complete = True
                        completion_reason = f"Prusa API shows FINISHED after ejection"
                
                # Method 4: Bambu-specific detection
                elif printer_type == 'bambu':
                    try:
                        from services.bambu_handler import BAMBU_PRINTER_STATES, bambu_states_lock
                        with bambu_states_lock:
                            if printer_name in BAMBU_PRINTER_STATES:
                                bambu_state = BAMBU_PRINTER_STATES[printer_name]
                                if bambu_state.get('ejection_complete', False):
                                    ejection_complete = True
                                    completion_reason = "Bambu ejection_complete flag"
                                elif bambu_state.get('state', '') in ['IDLE', 'READY']:
                                    ejection_complete = True
                                    completion_reason = f"Bambu state = {bambu_state.get('state', '')}"
                    except Exception as e:
                        logging.error(f"Error checking Bambu ejection state for {printer_name}: {e}")
                
                # PROCESS COMPLETION
                if ejection_complete:
                    logging.warning(f"EJECTION COMPLETE: {printer_name} transitioning from EJECTING to READY ({completion_reason})")
                    
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
                        "manual_timeout": time.time() + 300,  # 5 minutes manual override
                        "ejection_processed": False,  # Reset for next job
                        "ejection_in_progress": False, # Reset the in-progress flag
                        "ejection_start_time": None,
                        "finish_time": None,
                        "last_ejection_time": time.time(),
                        "count_incremented_for_current_job": False # NEW: Reset count flag
                    })
                    
                    # Clean up ejection state
                    release_ejection_lock(printer_name)
                    clear_printer_ejection_state(printer_name)
                    
                    # Trigger distribution for new jobs
                    threading.Timer(2.0, lambda: start_background_distribution(socketio, app)).start()
                    
                else:
                    # Log status for debugging stuck ejections
                    if elapsed_minutes > 5:  # Only log if ejection has been running for more than 5 minutes
                        logging.info(f"Ejection still in progress for {printer_name}: {elapsed_minutes:.1f} minutes elapsed, api_state={api_state}, waiting for completion signal")
        
        # No automatic safety timeout - ejections run until natural completion
        
        save_data(PRINTERS_FILE, PRINTERS)
    
    current_filament = None
    with SafeLock(filament_lock):
        filament_data = load_data(TOTAL_FILAMENT_FILE, {"total_filament_used_g": 0})
        TOTAL_FILAMENT_CONSUMPTION = filament_data.get("total_filament_used_g", 0)
        current_filament = TOTAL_FILAMENT_CONSUMPTION / 1000
        logging.debug(f"[FILAMENT DEBUG] Loaded filament data: {filament_data}, TOTAL_FILAMENT_CONSUMPTION: {TOTAL_FILAMENT_CONSUMPTION}g, current_filament: {current_filament}kg")
        
    current_orders = None
    with SafeLock(orders_lock):
        current_orders = copy.deepcopy(ORDERS)
    
    with ReadLock(printers_rwlock):
        printers_copy = prepare_printer_data_for_broadcast(PRINTERS)
    
    if batch_index is not None:
        logging.debug(f"[FILAMENT DEBUG] Emitting status_update with total_filament: {current_filament}kg")
        socketio.emit('status_update', {
            'printers': printers_copy,
            'total_filament': current_filament,
            'orders': current_orders
        })

async def check_and_start_print(session, printer, order, headers, batch_id, app):
    global TOTAL_FILAMENT_CONSUMPTION
    
    # FIXED SAFETY CHECK: Accept both READY and IDLE printers
    if printer.get('state') not in ['READY', 'IDLE']:
        logging.error(f"SAFETY: Attempted to start print on {printer['name']} in state {printer['state']} - ABORTING")
        return printer, order, False, batch_id

    # NEW: Reset the count increment flag for this new job
    printer['count_incremented_for_current_job'] = False
    logging.debug(f"Starting new job for {printer['name']} - reset count increment flag")
    
    # Handle Bambu printers differently
    if printer.get('type') == 'bambu':
        logging.debug(f"Starting Bambu print job for {printer['name']} with order {order['id']}")
        
        # Bambu requires .3mf extension
        filename = order['filename']
        if not filename.endswith('.3mf'):
            if filename.endswith('.gcode'):
                filename = filename.replace('.gcode', '.gcode.3mf')
            else:
                filename = filename + '.gcode.3mf'
        
        # Send print command with file upload
        # Pass the filepath so the file will be uploaded via FTP
        success = send_bambu_print_command(printer, filename, filepath=order['filepath'])
        
        if success:
            printer['state'] = 'PRINTING'
            printer['file'] = order['filename']
            printer['from_queue'] = True
            
            # ALWAYS increment count when print starts - regardless of ejection
            # For Bambu, we trust the send_bambu_print_command result since we control the FTP upload
            success_increment, updated_order = increment_order_sent_count(order['id'])
            if success_increment:
                logging.info(f"✓ Incremented sent count for Bambu order {order['id']} to {updated_order['sent']}")
                # INCREMENT FILAMENT IMMEDIATELY WHEN PRINT STARTS
                with SafeLock(filament_lock):
                    old_total = TOTAL_FILAMENT_CONSUMPTION
                    TOTAL_FILAMENT_CONSUMPTION += order['filament_g']
                    save_data(TOTAL_FILAMENT_FILE, {"total_filament_used_g": TOTAL_FILAMENT_CONSUMPTION})
                    logging.warning(f"[FILAMENT TRACKING] Print started on Bambu {printer['name']} - added {order['filament_g']}g ({old_total}g -> {TOTAL_FILAMENT_CONSUMPTION}g)")
                printer['order_id'] = order['id']
                printer['from_queue'] = True
                printer['finish_time'] = None
                printer['count_incremented_for_current_job'] = True  # Mark as counted
            
            printer['manually_set'] = False
            printer['ejection_processed'] = False
            printer['ejection_in_progress'] = False
        
        return printer, order, success, batch_id
    
    # Original Prusa code continues below
    
    file_path = f"/usb/{order['filename']}"
    file_url = f"http://{printer['ip']}/api/v1/files{file_path}"
    
    logging.debug(f"Starting print job for {printer['name']} with order {order['id']}")
    
    file_data = None
    try:
        with open(order['filepath'], "rb") as f:
            file_data = f.read()
    except Exception as e:
        logging.error(f"Error loading file {order['filepath']}: {str(e)}")
        return printer, order, False, batch_id

    try:
        logging.debug(f"Batch {batch_id}: Pre-emptively deleting file {order['filename']} from {printer['name']} to avoid conflicts")
        try:
            async with session.delete(file_url, headers=headers) as delete_resp:
                if delete_resp.status == 204:
                    logging.debug(f"Successfully deleted existing file")
                else:
                    logging.debug(f"Delete returned status {delete_resp.status}, continuing anyway")
        except Exception as e:
            logging.debug(f"Error during pre-emptive delete: {str(e)}")
        
        success = False
        logging.debug(f"Batch {batch_id}: File {order['filename']} exists on {printer['name']}, starting print...")
        
        async def _start_print():
            try:
                async with session.post(file_url, headers=headers) as start_resp:
                    if start_resp.status == 204:
                        logging.debug(f"Successfully started print on {printer['name']}")
                        return True
                    elif start_resp.status == 409:
                        logging.error(f"Batch {batch_id}: Start print returned 409 conflict")
                        await asyncio.sleep(3)
                        async with session.get(f"http://{printer['ip']}/api/v1/status", headers=headers) as status_resp:
                            if status_resp.status == 200:
                                status_data = await status_resp.json()
                                if status_data['printer']['state'] in ['PRINTING', 'BUSY']:
                                    logging.debug(f"Printer {printer['name']} is in printing state despite 409 - considering SUCCESS")
                                    return True
                        logging.error(f"Batch {batch_id}: Start print failed with 409 and printer is not printing")
                        return False
                    else:
                        logging.error(f"Batch {batch_id}: Start print failed: {start_resp.status}")
                        return False
            except Exception as e:
                logging.error(f"Error starting print: {str(e)}")
                return False
        
        logging.debug(f"Batch {batch_id}: File {order['filename']} not found, uploading...")
        
        async def _upload_file():
            try:
                try:
                    await asyncio.sleep(1)
                    async with session.delete(file_url, headers=headers) as delete_resp:
                        if delete_resp.status == 204:
                            logging.debug(f"Successfully deleted file before upload")
                        else:
                            logging.debug(f"Delete before upload returned {delete_resp.status}")
                        await asyncio.sleep(1)
                except Exception as e:
                    logging.debug(f"Error during re-upload delete: {str(e)}")
                
                async with session.put(
                    file_url, 
                    data=file_data, 
                    headers={**headers, "Print-After-Upload": "?1"}
                ) as upload_resp:
                    if upload_resp.status == 201:
                        logging.debug(f"Upload successful for {printer['name']}")
                        return True
                    elif upload_resp.status == 409:
                        logging.debug(f"Batch {batch_id}: File conflict during upload, trying one more time...")
                        await asyncio.sleep(2)
                        async with session.delete(file_url, headers=headers) as delete_resp:
                            await asyncio.sleep(2)
                            async with session.put(
                                file_url, 
                                data=file_data, 
                                headers={**headers, "Print-After-Upload": "?1"}
                            ) as retry_resp:
                                if retry_resp.status == 201:
                                    logging.debug(f"Retry successful for {printer['name']}")
                                    return True
                                else:
                                    logging.error(f"Second upload attempt failed: {retry_resp.status}")
                        await asyncio.sleep(3)
                        async with session.get(f"http://{printer['ip']}/api/v1/status", headers=headers) as status_resp:
                            if status_resp.status == 200:
                                status_data = await status_resp.json()
                                if status_data['printer']['state'] in ['PRINTING', 'BUSY']:
                                    logging.debug(f"Printer {printer['name']} is printing despite upload errors - SUCCESS")
                                    return True
                    logging.error(f"Batch {batch_id}: Upload failed: {upload_resp.status}")
                    return False
            except Exception as e:
                logging.error(f"Error uploading to {printer['name']}: {str(e)}")
                return False
        
        try:
            file_size = os.path.getsize(order['filepath'])
            initial_delay = 10 if file_size < 5*1024*1024 else 20
        except Exception as e:
            logging.error(f"Error getting file size: {str(e)}")
            initial_delay = 15

        file_exists = await retry_async(_start_print, max_retries=2, initial_backoff=1)
        if not file_exists:
            success = await retry_async(_upload_file, max_retries=2, initial_backoff=1)
        else:
            success = file_exists

        logging.debug(f"Running print verification for {printer['name']} with batch {batch_id}")
        verification_success = await verify_print_started(
            session, printer, order['filename'], headers, 
            max_attempts=3, initial_delay=initial_delay
        )

        if success != verification_success:
            logging.debug(f"API and verification disagree for {printer['name']} - performing additional checks")
            await asyncio.sleep(5)
            try:
                async with session.get(f"http://{printer['ip']}/api/v1/status", headers=headers) as status_resp:
                    if status_resp.status == 200:
                        status_data = await status_resp.json()
                        current_state = status_data['printer']['state']
                        if current_state in ['PRINTING', 'BUSY']:
                            logging.debug(f"Additional check confirms {printer['name']} is printing - considering SUCCESS")
                            success = True
                        else:
                            logging.debug(f"Additional check shows {printer['name']} is in {current_state} state - not printing")
                            if not verification_success:
                                success = False
            except Exception as e:
                logging.error(f"Error in additional verification for {printer['name']}: {str(e)}")

        if verification_success:
            if not success:
                logging.debug(f"API reported failure but verification shows print started on {printer['name']} - considering SUCCESS")
            success = True
        elif success:
            logging.debug(f"API reported success but verification failed for {printer['name']} - checking more thoroughly")
            verification_attempts = 3
            for attempt in range(verification_attempts):
                await asyncio.sleep(30 * (attempt + 1))
                try:
                    async with session.get(f"http://{printer['ip']}/api/v1/status", headers=headers) as status_resp:
                        if status_resp.status == 200:
                            status_data = await status_resp.json()
                            if status_data['printer']['state'] in ['PRINTING', 'BUSY']:
                                logging.debug(f"Attempt {attempt+1}: Printer {printer['name']} is printing - SUCCESS")
                                success = True
                                break
                            logging.debug(f"Attempt {attempt+1}: Printer state is {status_data['printer']['state']}, not printing")
                    async with session.get(f"http://{printer['ip']}/api/v1/job", headers=headers) as job_resp:
                        if job_resp.status == 200:
                            job_data = await job_resp.json()
                            job_filename = job_data.get('file', {}).get('name')
                            if job_filename and match_shortened_filename(order['filename'], job_filename):
                                logging.debug(f"Attempt {attempt+1}: Job check shows {printer['name']} is printing our file - SUCCESS")
                                success = True
                                break
                except Exception as e:
                    logging.error(f"Error in additional verification attempt {attempt+1}: {str(e)}")
            if not success:
                logging.debug(f"All verification attempts failed for {printer['name']} - marking as FAILED")

        if success:
            printer['state'] = 'PRINTING'
            printer['file'] = order['filename']
            printer['from_queue'] = True
            
            # Prusa filament/count deferral check (STEP 4 - PRUSA) - ENHANCED WITH FILENAME VERIFICATION
            if printer.get('type') != 'bambu':
                try:
                    logging.debug(f"Performing final verification for {printer['name']} before incrementing order count")
                    async with session.get(f"http://{printer['ip']}/api/v1/status", headers={"X-Api-Key": decrypt_api_key(printer['api_key'])}) as final_check:
                        if final_check.status == 200:
                            final_data = await final_check.json()
                            if final_data['printer']['state'] in ['PRINTING', 'BUSY']:
                                
                                # CRITICAL NEW CHECK: Verify the printer is printing OUR file, not a leftover job
                                should_increment = False
                                try:
                                    async with session.get(f"http://{printer['ip']}/api/v1/job", headers={"X-Api-Key": decrypt_api_key(printer['api_key'])}) as job_check:
                                        if job_check.status == 200:
                                            job_data = await job_check.json()
                                            current_file = job_data.get('file', {}).get('name', '')
                                            
                                            # Verify filename matches
                                            if match_shortened_filename(order['filename'], current_file):
                                                should_increment = True
                                                logging.debug(f"✓ Verified {printer['name']} is printing correct file: {current_file}")
                                            else:
                                                logging.warning(f"✗ Printer {printer['name']} is printing WRONG file '{current_file}' (expected '{order['filename']}') - NOT incrementing count")
                                        else:
                                            logging.warning(f"Could not verify job filename for {printer['name']} - HTTP {job_check.status}")
                                except Exception as e:
                                    logging.error(f"Error verifying filename for {printer['name']}: {str(e)}")
                                
                                # Only proceed if filename verification passed
                                if should_increment:
                                    # ALWAYS increment count when print starts - regardless of ejection
                                    success_increment, updated_order = increment_order_sent_count(order['id'])
                                    if success_increment:
                                        logging.info(f"✓ VERIFIED and incremented sent count for order {order['id']} to {updated_order['sent']}")
                                        # INCREMENT FILAMENT IMMEDIATELY WHEN PRINT STARTS
                                        with SafeLock(filament_lock):
                                            old_total = TOTAL_FILAMENT_CONSUMPTION
                                            TOTAL_FILAMENT_CONSUMPTION += order['filament_g']
                                            save_data(TOTAL_FILAMENT_FILE, {"total_filament_used_g": TOTAL_FILAMENT_CONSUMPTION})
                                            logging.warning(f"[FILAMENT TRACKING] Print started on {printer['name']} - added {order['filament_g']}g ({old_total}g -> {TOTAL_FILAMENT_CONSUMPTION}g)")
                                        printer['order_id'] = order['id']
                                        printer['from_queue'] = True
                                        printer['finish_time'] = None
                                        printer['count_incremented_for_current_job'] = True  # Mark as counted
                                else:
                                    logging.error(f"CRITICAL: Filename verification failed for {printer['name']} - count will NOT be incremented")
                            else:
                                logging.warning(f"Final verification failed: {printer['name']} is in state {final_data['printer']['state']} not PRINTING")
                        else:
                            logging.warning(f"Final verification failed: could not get status for {printer['name']}")
                except Exception as e:
                    logging.error(f"Error in final verification for {printer['name']}: {str(e)}")
            
            printer['total_filament_used_g'] = printer.get('total_filament_used_g', 0) + order['filament_g']
            printer['filament_used_g'] = order['filament_g']
            printer['manually_set'] = False
            printer['ejection_processed'] = False
            printer['ejection_in_progress'] = False
            printer['finish_time'] = None # Clear finish time on new print
            logging.debug(f"Batch {batch_id}: Sent {order['filename']} to {printer['name']}, filament: {order['filament_g']}, order_id: {order['id']}")
            logging.debug(f"Successfully configured {printer['name']} to print order {order['id']} in thread {threading.current_thread().name} ({threading.get_ident()})")
        
        return printer, order, success, batch_id
        
    except Exception as e:
        logging.error(f"Batch {batch_id}: Error processing {printer['name']}: {str(e)}")
        return printer, order, False, batch_id

def start_background_distribution(socketio, app, batch_size=10):
    if not distribution_semaphore.acquire(blocking=True, timeout=0.5):
        logging.debug(f"Distribution semaphore acquisition failed - already running. Thread: {threading.current_thread().name}, ID: {threading.get_ident()}")
        return None
    
    # Check if this is happening at night
    current_hour = datetime.now().hour
    if 0 <= current_hour < 6:
        import traceback
        log_distribution_event('MIDNIGHT_DISTRIBUTION_TRIGGERED', {
            'time': datetime.now().isoformat(),
            'triggered_by': str(traceback.extract_stack()[-2]),  # What called this?
            'hour': current_hour
        })
    
    task_id = str(uuid.uuid4())
    
    def run_with_semaphore():
        try:
            logging.debug(f"Starting distribution thread {task_id}")
            run_background_distribution(socketio, app, task_id, batch_size)
            logging.debug(f"Completed distribution thread {task_id}")
        except Exception as e:
            logging.error(f"Error in distribution thread {task_id}: {str(e)}")
        finally:
            logging.debug(f"Releasing distribution semaphore for {task_id}")
            distribution_semaphore.release()
    
    thread = threading.Thread(target=run_with_semaphore)
    thread.daemon = True
    thread.start()
    return task_id

def run_background_distribution(socketio, app, task_id, batch_size=10):
    try:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        loop.run_until_complete(distribute_orders_async(socketio, app, task_id, batch_size))
    except Exception as e:
        logging.error(f"Error in background distribution: {str(e)}")

async def distribute_orders_async(socketio, app, task_id=None, batch_size=10):
    thread_id = threading.get_ident()
    thread_name = threading.current_thread().name
    logging.debug(f"Starting distribute_orders_async in thread {thread_name} (ID: {thread_id}), task_id: {task_id}")
    
    # Check if this is a midnight run
    current_hour = datetime.now().hour
    if 0 <= current_hour < 6:
        log_distribution_event('MIDNIGHT_DISTRIBUTION_START', {
            'task_id': task_id,
            'time': datetime.now().isoformat(),
            'hour': current_hour
        })
    
    global TOTAL_FILAMENT_CONSUMPTION, ORDERS
    
    MAX_CONCURRENT_JOBS = 10
    
    current_filament = 0
    with SafeLock(filament_lock):
        filament_data = load_data(TOTAL_FILAMENT_FILE, {"total_filament_used_g": 0})
        current_filament = filament_data.get("total_filament_used_g", 0)
        TOTAL_FILAMENT_CONSUMPTION = current_filament
        logging.info(f"[FILAMENT DEBUG] Starting distribution - loaded TOTAL_FILAMENT_CONSUMPTION: {TOTAL_FILAMENT_CONSUMPTION}g")
    
    processed_order_printers = set()
    
    active_orders = []
    with SafeLock(orders_lock):
        active_orders = [o.copy() for o in ORDERS 
                        if o['status'] != 'completed' 
                        and o['sent'] < o['quantity']]
        logging.debug(f"Active orders: {[(o['id'], o['sent'], o['quantity']) for o in active_orders]}")
    
    if not active_orders:
        logging.debug("No active orders to distribute, skipping distribution")
        return

    ready_printers = []
    with ReadLock(printers_rwlock):
        all_printers = [p.copy() for p in PRINTERS if not p.get('service_mode', False)]
        # FIXED: Include both READY and IDLE printers for job distribution
        ready_printers = [p for p in all_printers if p['state'] in ['READY', 'IDLE']]
        
        printer_states = {}
        for p in all_printers:
            state = p['state']
            if state not in printer_states:
                printer_states[state] = []
            printer_states[state].append(p['name'])
        
        # Log FINISHED printers that are being skipped
        if 'FINISHED' in printer_states:
            logging.info(f"Skipping {len(printer_states['FINISHED'])} FINISHED printers: {printer_states['FINISHED']}")
        
        for state, printers in printer_states.items():
            logging.debug(f"Printers in state {state}: {len(printers)} ({', '.join(printers[:5])}{'...' if len(printers) > 5 else ''})")
        
        logging.debug(f"Found {len(ready_printers)} READY printers out of {len(all_printers)} total printers")
    
    log_distribution_event('DISTRIBUTION_START', {
        'task_id': task_id,
        'active_orders': len(active_orders),
        'ready_printers': len(ready_printers),
        'ready_printer_names': [p['name'] for p in ready_printers]
    })
    
    if not ready_printers:
        logging.debug("No ready printers available, skipping distribution")
        return
    
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=20, ttl_dns_cache=300),
        timeout=aiohttp.ClientTimeout(total=Config.API_TIMEOUT)
    ) as session:
        batch_id = str(uuid.uuid4())[:8]
        
        assigned_printers = set()
        all_jobs = []
        
        for order in active_orders:
            # UPDATED: Text-based group filtering
            eligible_printers = [
                p for p in ready_printers
                if str(p.get('group', 'Default')) in [str(g) for g in order.get('groups', ['Default'])] and
                p['name'] not in assigned_printers and
                f"{order['id']}:{p['name']}" not in processed_order_printers
            ]
            
            logging.debug(f"Order {order['id']}: Eligible printers before filtering: {[p['name'] for p in ready_printers]}")
            logging.debug(f"Order {order['id']}: After group filter (groups={order.get('groups', ['Default'])}): {[p['name'] for p in eligible_printers]}")
            
            def extract_number(printer):
                numbers = re.findall(r'\d+', printer['name'])
                return int(numbers[0]) if numbers else float('inf')
            eligible_printers.sort(key=extract_number)
            
            if not eligible_printers:
                logging.debug(f"No eligible printers for order {order['id']}")
                group_requirements = order.get('groups', ['Default'])
                matching_group_printers = [p['name'] for p in ready_printers if str(p.get('group', 'Default')) in [str(g) for g in group_requirements]]
                if matching_group_printers:
                    logging.debug(f"Found {len(matching_group_printers)} printers in matching groups, but already assigned or processed")
                else:
                    logging.debug(f"No printers in required groups {group_requirements}")
                continue
            
            copies_needed = min(order['quantity'] - order['sent'], len(eligible_printers))
            if copies_needed <= 0:
                logging.debug(f"Order {order['id']}: No copies needed (sent={order['sent']}, quantity={order['quantity']})")
                continue
                
            logging.debug(f"Found {len(eligible_printers)} available printers for order {order['id']}, need to distribute {copies_needed} copies")
            
            for i in range(copies_needed):
                if i >= len(eligible_printers):
                    break
                printer = eligible_printers[i]
                processed_order_printers.add(f"{order['id']}:{printer['name']}")
                job_data = {
                    'printer': printer,
                    'order': order
                }
                # Only add headers for Prusa printers
                if printer.get('type') != 'bambu':
                    job_data['headers'] = {"X-Api-Key": decrypt_api_key(printer['api_key'])}
                else:
                    job_data['headers'] = {}  # Empty headers for Bambu
                all_jobs.append(job_data)
                assigned_printers.add(printer['name'])
                logging.debug(f"Assigned printer {printer['name']} to order {order['id']}")
        
        total_processed = 0
        total_successful = 0
        updated_printers = {}
        
        logging.debug(f"Total assigned print jobs: {len(all_jobs)}")
        
        for i in range(0, len(all_jobs), MAX_CONCURRENT_JOBS):
            batch_jobs = all_jobs[i:i+MAX_CONCURRENT_JOBS]
            batch_tasks = []
            
            logging.debug(f"Processing batch {i//MAX_CONCURRENT_JOBS + 1} with {len(batch_jobs)} jobs")
            
            for job in batch_jobs:
                task = check_and_start_print(
                    session, job['printer'], job['order'], job['headers'], batch_id, app
                )
                batch_tasks.append(task)
            
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            for result in batch_results:
                total_processed += 1
                
                if isinstance(result, Exception):
                    logging.error(f"Error in print job: {str(result)}")
                    continue
                    
                if not isinstance(result, tuple) or len(result) < 3:
                    logging.error(f"Unexpected result format: {result}")
                    continue
                    
                printer, order, success, _ = result
                if success:
                    total_successful += 1
                    updated_printers[printer['name']] = printer
                    
                    # Log the job assignment
                    log_job_lifecycle(
                        order['id'],
                        printer['name'],
                        'JOB_ASSIGNED',
                        {
                            'filename': order['filename'],
                            'verification': success,
                            'batch_id': batch_id,
                            'task_id': task_id
                        }
                    )
                
                # NOTE: The filament and increment logic is now fully handled in check_and_start_print
                # for both Prusa (deferred) and Bambu (deferred) printers.
                # The logic for Prusa printers without ejection is also in check_and_start_print.
                
            if i + MAX_CONCURRENT_JOBS < len(all_jobs):
                await asyncio.sleep(1)
        
        logging.debug(f"Processed {total_processed} jobs, {total_successful} successful")
        
        if updated_printers:
            with WriteLock(printers_rwlock):
                for i, p in enumerate(PRINTERS):
                    if p['name'] in updated_printers:
                        for key, value in updated_printers[p['name']].items():
                            PRINTERS[i][key] = value
                            
                save_data(PRINTERS_FILE, PRINTERS)
    
    with SafeLock(filament_lock):
        total_filament = TOTAL_FILAMENT_CONSUMPTION / 1000
    
    with SafeLock(orders_lock):
        orders_data = ORDERS.copy()
        logging.debug(f"Post-distribution orders: {[(o['id'], o['sent'], o['quantity']) for o in orders_data if o['status'] != 'completed']}")
    
    with ReadLock(printers_rwlock):
        printers_copy = prepare_printer_data_for_broadcast(PRINTERS)
    
    logging.debug(f"Final summary: {total_processed} jobs processed, {total_successful} successful, {total_processed - total_successful} failed")
    
    socketio.emit('status_update', {
        'printers': printers_copy,
        'total_filament': total_filament,
        'orders': orders_data
    })

# Add these async wrapper functions that the new routes need
async def stop_print_async(session, printer):
    """Async wrapper for stop_print - used by the new routes"""
    return await stop_print(session, printer)

async def pause_print_async(session, printer):
    """Pause print on printer"""
    # Check if this is a Bambu printer
    if printer.get('type') == 'bambu':
        success = pause_bambu_print(printer)
        if success:
            printer['state'] = 'PAUSED'
            printer['status'] = 'Paused'
        return success
    
    # Prusa API - try both v1 and legacy endpoints
    headers = {"X-Api-Key": decrypt_api_key(printer['api_key'])}
    
    async def _pause():
        # First try the v1 API endpoint
        url = f"http://{printer['ip']}/api/v1/job"
        try:
            async with session.post(url, 
                                  headers=headers, 
                                  json={"command": "pause"}) as resp:
                if resp.status == 200:
                    logging.debug(f"Successfully paused print on {printer['name']} using v1 API")
                    printer['state'] = 'PAUSED'
                    printer['status'] = 'Paused'
                    return True
                elif resp.status == 405:
                    # Method not allowed - try the legacy endpoint
                    logging.debug(f"v1 API returned 405, trying legacy API for {printer['name']}")
        except Exception as e:
            logging.debug(f"v1 API error: {str(e)}, trying legacy API")
        
        # Try legacy API endpoint
        legacy_url = f"http://{printer['ip']}/api/job"
        try:
            async with session.post(legacy_url,
                                  headers=headers,
                                  json={"command": "pause"}) as resp:
                success = resp.status in [200, 204]
                if success:
                    logging.debug(f"Successfully paused print on {printer['name']} using legacy API")
                    printer['state'] = 'PAUSED'
                    printer['status'] = 'Paused'
                else:
                    logging.error(f"Failed to pause print on {printer['name']}: HTTP {resp.status}")
                return success
        except Exception as e:
            logging.error(f"Failed to pause print on {printer['name']}: {str(e)}")
            return False
    
    try:
        return await retry_async(_pause, max_retries=2, initial_backoff=1)
    except Exception as e:
        logging.error(f"Error pausing print on {printer['name']} after retries: {str(e)}")
        return False

async def resume_print_async(session, printer):
    """Resume print on printer"""
    # Check if this is a Bambu printer
    if printer.get('type') == 'bambu':
        success = resume_bambu_print(printer)
        if success:
            printer['state'] = 'PRINTING'
            printer['status'] = 'Printing'
        return success
    
    # Prusa API - try both v1 and legacy endpoints
    headers = {"X-Api-Key": decrypt_api_key(printer['api_key'])}
    
    async def _resume():
        # First try the v1 API endpoint
        url = f"http://{printer['ip']}/api/v1/job"
        try:
            async with session.post(url, 
                                  headers=headers, 
                                  json={"command": "resume"}) as resp:
                if resp.status == 200:
                    logging.debug(f"Successfully resumed print on {printer['name']} using v1 API")
                    printer['state'] = 'PRINTING'
                    printer['status'] = 'Printing'
                    return True
                elif resp.status == 405:
                    # Method not allowed - try the legacy endpoint
                    logging.debug(f"v1 API returned 405, trying legacy API for {printer['name']}")
        except Exception as e:
            logging.debug(f"v1 API error: {str(e)}, trying legacy API")
        
        # Try legacy API endpoint
        legacy_url = f"http://{printer['ip']}/api/job"
        try:
            async with session.post(legacy_url,
                                  headers=headers,
                                  json={"command": "resume"}) as resp:
                success = resp.status in [200, 204]
                if success:
                    logging.debug(f"Successfully resumed print on {printer['name']} using legacy API")
                    printer['state'] = 'PRINTING'
                    printer['status'] = 'Printing'
                else:
                    logging.error(f"Failed to resume print on {printer['name']}: HTTP {resp.status}")
                return success
        except Exception as e:
            logging.error(f"Failed to resume print on {printer['name']}: {str(e)}")
            return False
    
    try:
        return await retry_async(_resume, max_retries=2, initial_backoff=1)
    except Exception as e:
        logging.error(f"Error resuming print on {printer['name']} after retries: {str(e)}")
        return False

async def send_print_to_printer(session, printer, filepath, filename, order_id=None, filament_g=0):
    """Send a print directly to a printer (for manual prints)"""
    if printer.get('type') == 'bambu':
        # For Bambu printers, use the MQTT command
        success = send_bambu_print_command(printer, filename, filepath=filepath)
        if success:
            printer['state'] = 'PRINTING'
            printer['file'] = filename
            printer['from_queue'] = False
            printer['order_id'] = order_id
            printer['filament_used_g'] = filament_g
            printer['manually_set'] = False
            printer['ejection_processed'] = False
            printer['ejection_in_progress'] = False
            printer['finish_time'] = None # Clear finish time on new print
            printer['count_incremented_for_current_job'] = False # NEW: Reset count flag
        return success
    
    # Original Prusa code for manual prints
    file_path = f"/usb/{filename}"
    file_url = f"http://{printer['ip']}/api/v1/files{file_path}"
    headers = {"X-Api-Key": decrypt_api_key(printer['api_key'])}
    
    try:
        # Read the file
        with open(filepath, "rb") as f:
            file_data = f.read()
        
        # Upload and start print
        async with session.put(
            file_url,
            data=file_data,
            headers={**headers, "Print-After-Upload": "?1"}
        ) as resp:
            if resp.status == 201:
                logging.info(f"Successfully sent {filename} to {printer['name']}")
                return True
            else:
                logging.error(f"Failed to send print to {printer['name']}: HTTP {resp.status}")
                return False
                
    except Exception as e:
        logging.error(f"Error sending print to {printer['name']}: {str(e)}")
        return False

# Bambu printer helper functions
def pause_bambu_print_wrapper(printer):
    """Wrapper to handle Bambu pause in async context"""
    return pause_bambu_print(printer)

def resume_bambu_print_wrapper(printer):
    """Wrapper to handle Bambu resume in async context"""
    return resume_bambu_print(printer)

def is_bambu_printer(printer):
    """Check if printer is Bambu type"""
    return printer.get('type') == 'bambu'

# Enhanced ejection completion detection - SIMPLIFIED FUNCTION
def detect_ejection_completion(printer, api_state, current_api_file):
    """
    Simplified ejection completion detection
    Returns True if ejection is complete, False otherwise
    """
    printer_name = printer['name']
    current_state = printer.get('state')
    
    if current_state != 'EJECTING':
        return False
    
    # NEW: Check ejection state manager first
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
    if (stored_file and 'ejection_' in stored_file):
        # If API shows no file or different file, ejection is complete
        if not current_api_file or current_api_file != stored_file:
            logging.info(f"Ejection completion detected for {printer_name}: File changed from {stored_file} to {current_api_file or 'None'}")
            return True
    
    # Method 3: Bambu-specific completion detection
    if printer.get('type') == 'bambu':
        try:
            from services.bambu_handler import BAMBU_PRINTER_STATES, bambu_states_lock
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
        logging.info(f"Setting finish_time for {printer_name}: {finish_time}")
    else:
        # Preserve existing finish_time
        updates['finish_time'] = printer.get('finish_time')
    
    # CRITICAL FIX: Check if ejection has already been processed OR is currently in progress
    if printer.get('ejection_processed', False) or printer.get('ejection_in_progress', False):
        logging.debug(f"FINISHED->SKIP: {printer_name} (ejection already processed or in progress)")
        updates.update({
            "state": printer.get('state'), # Preserve the current state (FINISHED or EJECTING)
            "status": printer.get('status'), # Preserve the current status
            "progress": 100,
            "time_remaining": 0,
            "manually_set": False
        })
        return

    # Check if we have an order with ejection enabled
    with SafeLock(orders_lock):
        order = next((o for o in ORDERS if o['id'] == current_order_id), None)
    
    if not order or not order.get('ejection_enabled', False):
        # CRITICAL FIX: No ejection needed - STAY in FINISHED state (don't auto-transition to READY)
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

    # Try to acquire ejection lock
    ejection_lock = get_ejection_lock(printer_name)
    if not ejection_lock.acquire(blocking=False):
        logging.warning(f"FINISHED->WAIT: {printer_name} (ejection lock busy)")
        updates.update({
            "state": 'FINISHED',
            "status": 'Print Complete (Ejection Queued)',
            "progress": 100,
            "time_remaining": 0,
            "manually_set": False,
            "ejection_in_progress": False,
            "finish_time": time.time() # Ensure finish_time is set
        })
        return

    try:
        # Set ejection state to in_progress
        set_printer_ejection_state(printer_name, 'in_progress', {
            'order_id': current_order_id,
            'file': current_file
        })
        
        # CRITICAL FIX: Set the in_progress flag immediately
        printer['ejection_in_progress'] = True

        # Start ejection
        logging.info(f"FINISHED->EJECTING: {printer_name} starting ejection")
        updates.update({
            "state": 'EJECTING',
            "status": 'Ejecting',
            "ejection_start_time": time.time(),
            "ejection_processed": True,  # Mark immediately to prevent re-processing
            "ejection_in_progress": True,
            "manually_set": False,
            "finish_time": time.time() # Ensure finish_time is set
        })

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
                printer['ejection_in_progress'] = False # Reset on failure
        else:
            # CRITICAL FIX: Prusa ejection - store ejection details AND update main PRINTERS list immediately
            gcode_file_name = f"ejection_{printer_name}_{int(time.time())}.gcode"
            
            # Store pending ejection on the actual printer object in PRINTERS
            with WriteLock(printers_rwlock):
                # Find this printer in the main PRINTERS list
                for p in PRINTERS:
                    if p['name'] == printer_name:
                        p['pending_ejection'] = {
                            'gcode_content': gcode_content,
                            'gcode_file_name': gcode_file_name,
                            'timestamp': time.time()
                        }
                        # CRITICAL: Update state immediately to prevent job distribution
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
        printer['ejection_in_progress'] = False # Reset on error

def emergency_fix_stuck_printers():
    """Emergency function to fix stuck printers"""
    with WriteLock(printers_rwlock):
        fixed_count = 0
        for printer in PRINTERS:
            if printer.get('state') == 'FINISHED':
                # Force all FINISHED printers to READY
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
                    "finish_time": None,
                    "count_incremented_for_current_job": False # NEW: Reset count flag
                })
                fixed_count += 1
                logging.warning(f"EMERGENCY: Fixed stuck printer {printer['name']}")
        
        if fixed_count > 0:
            save_data(PRINTERS_FILE, PRINTERS)
            logging.warning(f"EMERGENCY: Fixed {fixed_count} stuck printers")
    
    return fixed_count

# Enhanced mass ejection function
def trigger_mass_ejection_for_finished_printers(socketio, app):
    """Trigger ejection for all FINISHED printers that have ejection enabled"""
    
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
                
                # Check if ejection is actually needed
                order_id = printer.get('order_id')
                if order_id:
                    with SafeLock(orders_lock):
                        order = next((o for o in ORDERS if o['id'] == order_id), None)
                        if order and order.get('ejection_enabled', False):
                            # Make sure not already in progress
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
                # Set ejection state to queued
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

# Add mark_group_ready function with text-based groups
def mark_group_ready(group_name, socketio=None):
    """Mark all FINISHED printers in a specific group as READY"""
    with WriteLock(printers_rwlock):
        count = 0
        for printer in PRINTERS:
            if str(printer.get('group', 'Default')) == str(group_name) and printer['state'] == 'FINISHED':
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
                    "count_incremented_for_current_job": False # NEW: Reset count flag
                })
                count += 1
                logging.info(f"Marked {printer['name']} in group {group_name} as READY")
        
        save_data(PRINTERS_FILE, PRINTERS)
        
        if count > 0:
            logging.info(f"Marked {count} printers in group {group_name} as READY")
            
            # Emit status update if socketio is available
            if socketio:
                with SafeLock(filament_lock):
                    total_filament = TOTAL_FILAMENT_CONSUMPTION / 1000
                with SafeLock(orders_lock):
                    orders_data = ORDERS.copy()
                printers_copy = prepare_printer_data_for_broadcast(PRINTERS)
                
                socketio.emit('status_update', {
                    'printers': printers_copy,
                    'total_filament': total_filament,
                    'orders': orders_data
                })
        
        return count