"""
Status polling and broadcasting for printer status updates.
Handles fetching printer status from APIs and broadcasting to clients.
"""
import time
import asyncio
import aiohttp
import threading
import copy

from services.state import (
    PRINTERS_FILE, TOTAL_FILAMENT_FILE,
    PRINTERS, ORDERS, save_data, load_data, decrypt_api_key,
    logging, orders_lock, filament_lock, printers_rwlock,
    SafeLock, ReadLock, WriteLock,
    get_printer_ejection_state, clear_printer_ejection_state
)
from services.bambu_handler import (
    get_bambu_status, send_bambu_ejection_gcode,
    BAMBU_PRINTER_STATES, bambu_states_lock
)
from services.ejection_manager import (
    clear_stuck_ejection_locks, release_ejection_lock,
    handle_finished_state_ejection, async_send_ejection_gcode
)
from utils.config import Config
from utils.retry_utils import retry_async
from utils.logger import log_state_transition, log_api_poll_event

# State mapping for printer states
state_map = {
    'IDLE': 'Ready', 'PRINTING': 'Printing', 'PAUSED': 'Paused', 'ERROR': 'Error',
    'FINISHED': 'Finished', 'READY': 'Ready', 'STOPPED': 'Stopped', 'ATTENTION': 'Attention',
    'EJECTING': 'Ejecting', 'PREPARE': 'Preparing', 'OFFLINE': 'Offline',
    'COOLING': 'Cooling'
}


def get_minutes_since_finished(printer):
    """Calculate minutes elapsed since printer entered FINISHED state"""
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

    for printer in printers_copy:
        # Map backend field names to frontend expected names
        if 'file' in printer:
            printer['current_file'] = printer.get('file')

        if 'state' in printer:
            printer['status'] = printer.get('state')

        # Extract temperature values
        temps = printer.get('temps', {})
        nozzle_temp = temps.get('nozzle', 0) if temps else 0
        bed_temp = temps.get('bed', 0) if temps else 0

        if 'nozzle_temp' in printer and printer['nozzle_temp']:
            nozzle_temp = printer['nozzle_temp']
        if 'bed_temp' in printer and printer['bed_temp']:
            bed_temp = printer['bed_temp']

        # Check Bambu MQTT state directly for real-time temps and error info
        if printer.get('type') == 'bambu':
            printer_name = printer.get('name')
            if printer_name:
                with bambu_states_lock:
                    if printer_name in BAMBU_PRINTER_STATES:
                        bambu_state = BAMBU_PRINTER_STATES[printer_name]
                        if bambu_state.get('nozzle_temp') is not None:
                            nozzle_temp = bambu_state.get('nozzle_temp', 0)
                        if bambu_state.get('bed_temp') is not None:
                            bed_temp = bambu_state.get('bed_temp', 0)

                        if bambu_state.get('state') == 'ERROR' or printer.get('state') == 'ERROR':
                            error_msg = bambu_state.get('error')
                            hms_alerts = bambu_state.get('hms_alerts', [])

                            if error_msg:
                                printer['error_message'] = error_msg
                            elif hms_alerts:
                                printer['error_message'] = '; '.join(hms_alerts)
                            else:
                                printer['error_message'] = 'Unknown error'

        printer['nozzle_temp'] = nozzle_temp
        printer['bed_temp'] = bed_temp

        # Calculate minutes since finished
        minutes_since_finished = get_minutes_since_finished(printer)
        printer['minutes_since_finished'] = minutes_since_finished

        # Add print stage info
        state = printer.get('state', 'Unknown')
        print_stage = 'idle'
        stage_detail = ''

        if state == 'PRINTING':
            print_stage = 'printing'
            stage_detail = f"{printer.get('progress', 0)}% complete"
        elif state == 'FINISHED':
            print_stage = 'finished'
            if minutes_since_finished is not None:
                stage_detail = f'Finished {minutes_since_finished}m ago'
            else:
                stage_detail = 'Print complete'
        elif state == 'EJECTING':
            print_stage = 'ejecting'
            stage_detail = 'Ejecting print'
        elif state == 'COOLING':
            print_stage = 'cooling'
            cooldown_target = printer.get('cooldown_target_temp', 0)
            stage_detail = f'Cooling bed to {cooldown_target}°C'
        elif state == 'READY':
            print_stage = 'ready'
            stage_detail = 'Ready for next job'
        elif state == 'PAUSED':
            print_stage = 'paused'
            stage_detail = 'Print paused'
        elif state == 'ERROR':
            print_stage = 'error'
            stage_detail = printer.get('error_message', 'Printer error')

        printer['print_stage'] = print_stage
        printer['stage_detail'] = stage_detail

        # Add timestamps for timeline tracking
        printer['print_started_at'] = printer.get('print_started_at')
        printer['finish_time'] = printer.get('finish_time')
        printer['ejection_start_time'] = printer.get('ejection_start_time')

    return printers_copy


def update_bambu_printer_states():
    """Update main printer states from Bambu MQTT data and track filament usage"""
    global TOTAL_FILAMENT_CONSUMPTION

    # Get Bambu states snapshot
    with bambu_states_lock:
        bambu_states = copy.deepcopy(BAMBU_PRINTER_STATES)

    if not bambu_states:
        return

    updates_made = False

    with WriteLock(printers_rwlock):
        for printer in PRINTERS:
            if printer.get('type') != 'bambu':
                continue

            printer_name = printer.get('name')
            if printer_name not in bambu_states:
                continue

            bambu_state = bambu_states[printer_name]
            current_state = printer.get('state', 'Unknown')

            # Skip updates for printers in COOLING state - managed by cooling monitor
            if current_state == 'COOLING':
                continue

            # Get the new state from Bambu MQTT
            new_state = bambu_state.get('state', current_state)

            # Protect manually-set READY state from being overwritten by stale MQTT states
            # (e.g., FINISHED), but still allow real activity (PRINTING, EJECTING, PREPARE)
            # to come through so the printer can transition when a job actually starts.
            if (printer.get('manually_set', False) and current_state == 'READY'
                    and new_state not in ['PRINTING', 'EJECTING', 'PREPARE', 'PAUSED']):
                logging.debug(f"Bambu {printer_name}: preserving manually-set READY state (ignoring MQTT state {new_state})")
                # Still update temperatures even when preserving manual state
                if 'nozzle_temp' in bambu_state:
                    printer['nozzle_temp'] = bambu_state['nozzle_temp']
                if 'bed_temp' in bambu_state:
                    printer['bed_temp'] = bambu_state['bed_temp']
                continue

            # Update temperatures
            if 'nozzle_temp' in bambu_state:
                printer['nozzle_temp'] = bambu_state['nozzle_temp']
            if 'bed_temp' in bambu_state:
                printer['bed_temp'] = bambu_state['bed_temp']

            # Update progress and time remaining for printing states
            if new_state == 'PRINTING':
                if 'progress' in bambu_state:
                    printer['progress'] = bambu_state['progress']
                if 'time_remaining' in bambu_state:
                    printer['time_remaining'] = bambu_state['time_remaining']
                # Bambu MQTT stores current file under 'current_file'; support both for compatibility
                if 'current_file' in bambu_state:
                    printer['file'] = bambu_state['current_file']
                elif 'file' in bambu_state:
                    printer['file'] = bambu_state['file']

            # Handle state transitions
            # Don't overwrite FINISHED with READY when Bambu reports IDLE after completion.
            # Stay in FINISHED until user clicks "Mark Ready" or ejection completes.
            if new_state != current_state:
                if current_state == 'FINISHED' and new_state == 'READY':
                    logging.debug(f"Bambu {printer_name}: keeping FINISHED (ignore IDLE->READY until user marks ready)")
                    # Skip this transition - do not update state
                else:
                    logging.info(f"Bambu {printer_name} state change: {current_state} -> {new_state}")
                    printer['state'] = new_state
                    printer['status'] = state_map.get(new_state, 'Unknown')
                    updates_made = True

                    # Clear manually_set when printer starts real activity
                    if new_state in ['PRINTING', 'EJECTING', 'PREPARE'] and printer.get('manually_set', False):
                        logging.info(f"Bambu {printer_name}: clearing manually_set flag on transition to {new_state}")
                        printer['manually_set'] = False

                    # Set finish_time when transitioning to FINISHED
                    if new_state == 'FINISHED' and current_state != 'FINISHED':
                        printer['finish_time'] = time.time()

    if updates_made:
        save_data(PRINTERS_FILE, PRINTERS)


def ensure_finish_times():
    """Ensure all FINISHED printers have a finish_time set"""
    with WriteLock(printers_rwlock):
        for printer in PRINTERS:
            if printer.get('state') == 'FINISHED' and not printer.get('finish_time'):
                printer['finish_time'] = time.time()
                logging.debug(f"Set missing finish_time for {printer.get('name')}")
        save_data(PRINTERS_FILE, PRINTERS)


async def fetch_status(session, printer):
    """Fetch status from a printer's API"""
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


async def get_printer_status_async(socketio, app, batch_index=None, batch_size=None):
    """Main status polling function - fetches status from all printers and updates state"""
    # Import here to avoid circular imports
    from services.order_distributor import start_background_distribution

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

                minimal_printer = {
                    'name': printer_copy['name'],
                    'ip': printer_copy['ip'],
                    'state': printer_copy.get('state', 'Unknown'),
                    'manually_set': printer_copy.get('manually_set', False),
                    'file': printer_copy.get('file', ''),
                    'order_id': printer_copy.get('order_id'),
                    'ejection_processed': printer_copy.get('ejection_processed', False),
                    'ejection_in_progress': printer_copy.get('ejection_in_progress', False),
                    'manual_timeout': printer_copy.get('manual_timeout', 0),
                    'type': printer_copy.get('type', 'prusa'),
                    'last_ejection_time': printer_copy.get('last_ejection_time', 0),
                    'finish_time': printer_copy.get('finish_time'),
                    'count_incremented_for_current_job': printer_copy.get('count_incremented_for_current_job', False)
                }

                if printer_copy.get('type') != 'bambu':
                    minimal_printer['api_key'] = printer_copy.get('api_key')
                else:
                    minimal_printer['device_id'] = printer_copy.get('device_id')
                    minimal_printer['serial_number'] = printer_copy.get('serial_number')
                    minimal_printer['access_code'] = printer_copy.get('access_code')

                printers_to_process.append(minimal_printer)
                printer_indices.append(i)
    else:
        for i, printer in enumerate(all_printers):
            minimal_printer = {
                'name': printer['name'],
                'ip': printer['ip'],
                'state': printer.get('state', 'Unknown'),
                'manually_set': printer.get('manually_set', False),
                'file': printer.get('file', ''),
                'order_id': printer.get('order_id'),
                'ejection_processed': printer.get('ejection_processed', False),
                'ejection_in_progress': printer.get('ejection_in_progress', False),
                'manual_timeout': printer.get('manual_timeout', 0),
                'type': printer.get('type', 'prusa'),
                'last_ejection_time': printer.get('last_ejection_time', 0),
                'finish_time': printer.get('finish_time'),
                'count_incremented_for_current_job': printer.get('count_incremented_for_current_job', False)
            }

            if printer.get('type') != 'bambu':
                minimal_printer['api_key'] = printer.get('api_key')
            else:
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
                        "ejection_in_progress": False,
                        "finish_time": None,
                        "count_incremented_for_current_job": False
                    }
                })
                continue

            printer, data = result
            if data:
                api_state = data['printer']['state']
                manually_set = printer.get('manually_set', False)
                current_state = printer.get('state', 'Unknown')
                ejection_processed = printer.get('ejection_processed', False)
                ejection_in_progress = printer.get('ejection_in_progress', False)
                current_file = printer.get('file', '')
                current_order_id = printer.get('order_id')

                with ReadLock(printers_rwlock):
                    if printer_indices[idx] < len(PRINTERS):
                        database_state = PRINTERS[printer_indices[idx]].get('state', 'Unknown')
                        database_ejection_processed = PRINTERS[printer_indices[idx]].get('ejection_processed', False)
                        logging.debug(f"Printer {printer['name']}: API state={api_state}, Copied state={current_state}, Database state={database_state}, manually_set={manually_set}, ejection_processed={ejection_processed}, db_ejection_processed={database_ejection_processed}, ejection_in_progress={ejection_in_progress}")

                updates = {}

                # Skip normal state updates for printers in COOLING state
                with ReadLock(printers_rwlock):
                    if printer_indices[idx] < len(PRINTERS):
                        actual_db_state = PRINTERS[printer_indices[idx]].get('state', 'Unknown')
                        if actual_db_state == 'COOLING':
                            logging.debug(f"Skipping status update for {printer['name']} - in COOLING state (API reports: {api_state})")
                            printer_updates.append({
                                'index': printer_indices[idx],
                                'updates': {
                                    "temps": {"bed": data['printer'].get('temp_bed', 0), "nozzle": data['printer'].get('temp_nozzle', 0)},
                                    "bed_temp": data['printer'].get('temp_bed', 0),
                                }
                            })
                            continue

                if manually_set and api_state not in ['PRINTING', 'EJECTING']:
                    if api_state == 'FINISHED':
                        logging.debug(f"Printer {printer['name']} has finished printing, using enhanced FINISHED handler")
                        handle_finished_state_ejection(printer, printer['name'], current_file, current_order_id, updates)

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
                                "count_incremented_for_current_job": printer.get('count_incremented_for_current_job', False)
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
                                "count_incremented_for_current_job": printer.get('count_incremented_for_current_job', False)
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
                        "count_incremented_for_current_job": printer.get('count_incremented_for_current_job', False)
                    }
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
                        "count_incremented_for_current_job": printer.get('count_incremented_for_current_job', False)
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
                        "count_incremented_for_current_job": printer.get('count_incremented_for_current_job', False)
                    }
                else:
                    # Handle Bambu printer state mapping
                    if printer.get('type') == 'bambu' and api_state in ['PREPARING']:
                        api_state = 'PREPARE'
                    updates = {
                        "state": api_state,
                        "status": state_map.get(api_state, 'Unknown'),
                        "temps": {"bed": data['printer'].get('temp_bed', 0), "nozzle": data['printer'].get('temp_nozzle', 0)},
                        "z_height": data['printer'].get('axis_z', 0),
                        "ejection_in_progress": False
                    }

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
                                            "ejection_processed": False,
                                            "ejection_in_progress": False,
                                            "finish_time": None,
                                            "count_incremented_for_current_job": printer.get('count_incremented_for_current_job', False)
                                        })
                                    else:
                                        updates.update({"progress": 0, "time_remaining": 0, "file": "None", "job_id": None})
                            except Exception as e:
                                logging.error(f"Error fetching job for {printer['name']}: {str(e)}")
                                updates.update({"progress": 0, "time_remaining": 0, "file": "None", "job_id": None})
                        else:
                            updates.update({
                                "progress": data.get('progress', 0),
                                "time_remaining": data.get('time_remaining', 0),
                                "file": data.get('file', {}).get('display_name', data.get('file', 'Unknown')),
                                "job_id": None,
                                "manually_set": manually_set,
                                "ejection_processed": False,
                                "ejection_in_progress": False,
                                "finish_time": None,
                                "count_incremented_for_current_job": printer.get('count_incremented_for_current_job', False)
                            })
                    elif api_state == 'FINISHED':
                        handle_finished_state_ejection(printer, printer['name'], current_file, current_order_id, updates)

                        if updates.get('state') == 'EJECTING':
                            updates['ejection_in_progress'] = True

                    elif api_state in ['IDLE', 'FINISHED', 'OPERATIONAL']:
                        original_printer_index = printer_indices[idx]
                        with ReadLock(printers_rwlock):
                            if 0 <= original_printer_index < len(PRINTERS):
                                stored_state = PRINTERS[original_printer_index].get('state', 'Unknown')
                                stored_finish_time = PRINTERS[original_printer_index].get('finish_time')

                                logging.debug(f"Checking printer {printer['name']}: API state={api_state}, stored state={stored_state}, stored_finish_time={stored_finish_time}")

                                if stored_finish_time:
                                    updates['finish_time'] = stored_finish_time
                                    logging.debug(f"Preserving existing finish_time for {printer['name']}: {stored_finish_time}")
                                elif stored_state == 'FINISHED' or api_state == 'FINISHED':
                                    finish_time = time.time()
                                    updates['finish_time'] = finish_time
                                    logging.debug(f"Setting new finish_time for {printer['name']}: {finish_time}")
                                else:
                                    if stored_state == 'FINISHED' and api_state not in ['FINISHED', 'EJECTING']:
                                        updates['finish_time'] = None
                                        logging.info(f"Clearing finish_time for {printer['name']} - transitioning from FINISHED to {api_state}")
                                    else:
                                        updates['finish_time'] = None

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
                                        "finish_time": None,
                                        "count_incremented_for_current_job": False
                                    })
                                    threading.Timer(2.0, lambda: start_background_distribution(socketio, app)).start()
                                elif stored_state == 'EJECTING':
                                    logging.warning(f"IMPORTANT: Printer {printer['name']} completed ejection (API={api_state}), transitioning from EJECTING to READY")
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
                                        "last_ejection_time": time.time(),
                                        "finish_time": None,
                                        "count_incremented_for_current_job": False
                                    })
                                    release_ejection_lock(printer['name'])
                                    clear_printer_ejection_state(printer['name'])
                                else:
                                    updates.update({
                                        "state": api_state,
                                        "status": state_map.get(api_state, 'Unknown'),
                                        "progress": 0,
                                        "time_remaining": 0,
                                        "file": "None",
                                        "job_id": None,
                                        "manually_set": False,
                                        "ejection_in_progress": False,
                                        "count_incremented_for_current_job": False
                                    })
                    elif api_state not in ['PRINTING', 'PAUSED', 'FINISHED', 'EJECTING']:
                        updates.update({"progress": 0, "time_remaining": 0, "file": "None", "job_id": None, "manually_set": False, "finish_time": None, "ejection_in_progress": False, "count_incremented_for_current_job": False})

                printer_updates.append({
                    'index': printer_indices[idx],
                    'updates': updates
                })

                # Execute pending Prusa ejection tasks
                if updates.get('state') == 'EJECTING':
                    with ReadLock(printers_rwlock):
                        original_printer = PRINTERS[printer_indices[idx]]
                        pending_ejection = original_printer.get('pending_ejection')

                    if pending_ejection and printer.get('type') != 'bambu':
                        gcode_content = pending_ejection['gcode_content']
                        gcode_file_name = pending_ejection['gcode_file_name']
                        headers = {"X-Api-Key": decrypt_api_key(printer['api_key'])}
                        ejection_file_path = f"/usb/{gcode_file_name}"
                        ejection_url = f"http://{printer['ip']}/api/v1/files{ejection_file_path}"

                        ejection_tasks.append(async_send_ejection_gcode(
                            session, printer, headers, ejection_url,
                            gcode_content, gcode_file_name
                        ))

                        with WriteLock(printers_rwlock):
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
                        "finish_time": None,
                        "count_incremented_for_current_job": False
                    }
                })

        if ejection_tasks:
            logging.info(f"EJECTION: Executing {len(ejection_tasks)} ejection tasks")
            ejection_results = await asyncio.gather(*ejection_tasks, return_exceptions=True)

            for i, result in enumerate(ejection_results):
                if isinstance(result, Exception):
                    logging.error(f"EJECTION: Task {i} failed with exception: {str(result)}")
                else:
                    logging.info(f"EJECTION: Task {i} completed successfully")
        else:
            logging.debug("EJECTION: No ejection tasks to execute")

    # Apply updates and handle state transitions
    with WriteLock(printers_rwlock):
        for update in printer_updates:
            if 0 <= update['index'] < len(PRINTERS):
                current_manually_set = PRINTERS[update['index']].get('manually_set', False)
                new_manually_set = update['updates'].get('manually_set', current_manually_set)
                if current_manually_set and not new_manually_set and update['updates'].get('state') != 'PRINTING':
                    logging.warning(f"WARNING: Printer {PRINTERS[update['index']]['name']} manually_set changing from True to False!")
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

                old_state = PRINTERS[update['index']].get('state')
                new_state = update['updates'].get('state')
                if new_state and old_state != new_state:
                    logging.info(f"Printer {PRINTERS[update['index']]['name']} state: {old_state} -> {new_state}")

                for key, value in update['updates'].items():
                    PRINTERS[update['index']][key] = value

        # Failsafe for manually_set printers
        for i, printer in enumerate(PRINTERS):
            if printer.get('manually_set', False) and printer.get('state') not in ['READY', 'PRINTING', 'EJECTING']:
                logging.warning(f"Failsafe: Fixing printer {printer['name']} - has manually_set=True but state={printer['state']}. Setting back to READY")
                printer['state'] = 'READY'
                printer['status'] = 'Ready'
                printer['manually_set'] = True
                printer['count_incremented_for_current_job'] = False

        # Enhanced ejection completion monitoring
        for i, printer in enumerate(PRINTERS):
            if printer.get('state') == 'EJECTING':
                printer_name = printer['name']
                printer_type = printer.get('type', 'prusa')
                current_time = time.time()
                ejection_start = printer.get('ejection_start_time', 0)
                elapsed_minutes = (current_time - ejection_start) / 60.0 if ejection_start else 0

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

                ejection_state = get_printer_ejection_state(printer_name)
                if ejection_state['state'] == 'completed':
                    ejection_complete = True
                    completion_reason = "State manager shows completed"
                elif api_state in ['IDLE', 'READY', 'OPERATIONAL']:
                    ejection_complete = True
                    completion_reason = f"API state = {api_state}"
                elif printer_type != 'bambu':
                    stored_file = printer.get('file', '')
                    if stored_file and 'ejection_' in stored_file:
                        if not current_api_file or current_api_file != stored_file:
                            ejection_complete = True
                            completion_reason = f"Ejection file '{stored_file}' no longer active"
                    elif api_state == 'FINISHED':
                        ejection_complete = True
                        completion_reason = "Prusa API shows FINISHED after ejection"
                elif printer_type == 'bambu':
                    try:
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

                if ejection_complete:
                    logging.warning(f"EJECTION COMPLETE: {printer_name} transitioning from EJECTING to READY ({completion_reason})")

                    printer.update({
                        "state": 'READY',
                        "status": 'Ready',
                        "progress": 0,
                        "time_remaining": 0,
                        "file": None,
                        "job_id": None,
                        "order_id": None,
                        "manually_set": True,
                        "manual_timeout": time.time() + 300,
                        "ejection_processed": False,
                        "ejection_in_progress": False,
                        "ejection_start_time": None,
                        "finish_time": None,
                        "last_ejection_time": time.time(),
                        "count_incremented_for_current_job": False
                    })

                    release_ejection_lock(printer_name)
                    clear_printer_ejection_state(printer_name)

                    threading.Timer(2.0, lambda: start_background_distribution(socketio, app)).start()
                else:
                    if elapsed_minutes > 5:
                        logging.info(f"Ejection still in progress for {printer_name}: {elapsed_minutes:.1f} minutes elapsed")

        # COOLING STATE MONITORING
        for i, printer in enumerate(PRINTERS):
            if printer.get('state') == 'COOLING':
                printer_name = printer['name']
                cooldown_target = printer.get('cooldown_target_temp', 0)
                cooldown_order_id = printer.get('cooldown_order_id')

                current_bed_temp = 0
                try:
                    with bambu_states_lock:
                        if printer_name in BAMBU_PRINTER_STATES:
                            current_bed_temp = BAMBU_PRINTER_STATES[printer_name].get('bed_temp', 0)
                except Exception as e:
                    logging.warning(f"Could not get bed temp for {printer_name}: {e}")

                printer['status'] = f'Cooling ({current_bed_temp}°C → {cooldown_target}°C)'

                if current_bed_temp <= cooldown_target:
                    logging.info(f"COOLING->EJECTING: {printer_name} (bed temp {current_bed_temp}°C <= target {cooldown_target}°C)")

                    with SafeLock(orders_lock):
                        order = next((o for o in ORDERS if o['id'] == cooldown_order_id), None)

                    if order and order.get('ejection_enabled', False):
                        gcode_content = order.get('end_gcode', '').strip()
                        if not gcode_content:
                            gcode_content = "G28 X Y\nM84"

                        printer.update({
                            "state": 'EJECTING',
                            "status": 'Ejecting',
                            "ejection_start_time": time.time(),
                            "ejection_processed": True,
                            "ejection_in_progress": True,
                            "manually_set": False,
                            "cooldown_target_temp": None,
                            "cooldown_order_id": None
                        })

                        success = send_bambu_ejection_gcode(printer, gcode_content)
                        if not success:
                            logging.error(f"Bambu ejection failed for {printer_name} after cooling")
                            printer.update({
                                "state": 'READY',
                                "status": 'Ready',
                                "ejection_processed": False,
                                "ejection_in_progress": False,
                                "manually_set": True
                            })
                    else:
                        logging.warning(f"COOLING->READY: {printer_name} (order not found or ejection not enabled)")
                        printer.update({
                            "state": 'READY',
                            "status": 'Ready',
                            "progress": 0,
                            "time_remaining": 0,
                            "manually_set": True,
                            "cooldown_target_temp": None,
                            "cooldown_order_id": None
                        })
                else:
                    finish_time = printer.get('finish_time', time.time())
                    cooling_minutes = (time.time() - finish_time) / 60.0
                    if int(cooling_minutes) % 2 == 0 and cooling_minutes > 0:
                        logging.debug(f"COOLING: {printer_name} at {current_bed_temp}°C, target {cooldown_target}°C ({cooling_minutes:.1f}min elapsed)")

        save_data(PRINTERS_FILE, PRINTERS)

    # Load and emit current state
    current_filament = None
    with SafeLock(filament_lock):
        filament_data = load_data(TOTAL_FILAMENT_FILE, {"total_filament_used_g": 0})
        TOTAL_FILAMENT_CONSUMPTION = filament_data.get("total_filament_used_g", 0)
        current_filament = TOTAL_FILAMENT_CONSUMPTION / 1000
        logging.debug(f"Loaded filament data: total={TOTAL_FILAMENT_CONSUMPTION}g ({current_filament}kg)")

    current_orders = None
    with SafeLock(orders_lock):
        current_orders = copy.deepcopy(ORDERS)

    with ReadLock(printers_rwlock):
        printers_copy = prepare_printer_data_for_broadcast(PRINTERS)

    if batch_index is not None:
        logging.debug(f"Emitting status_update with total_filament: {current_filament}kg")
        socketio.emit('status_update', {
            'printers': printers_copy,
            'total_filament': current_filament,
            'orders': current_orders
        })
