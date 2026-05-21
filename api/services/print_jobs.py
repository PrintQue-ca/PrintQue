"""
Print job control functions for starting, stopping, pausing, and resuming prints
on both Prusa and Bambu printers.
"""
import os
import time
import asyncio
import threading
import copy

import aiohttp

from services.state import (
    TOTAL_FILAMENT_FILE,
    TOTAL_FILAMENT_CONSUMPTION,
    save_data, decrypt_api_key,
    logging, filament_lock, SafeLock, increment_order_sent_count
)
from services.bambu_handler import (
    send_bambu_print_command,
    stop_bambu_print,
    pause_bambu_print,
    resume_bambu_print,
    clear_bambu_print_assignment,
)
from services.library_queue import clear_queue_job_error
from utils.retry_utils import retry_async
from utils.logger import log_state_transition


def match_shortened_filename(full_filename, shortened_filename):
    """Match potentially shortened filenames (for 8.3 FAT compatibility)"""
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
    """Verify that a print has successfully started on a printer"""
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


def apply_cancelled_print_state(printer):
    """Reset printer to ready after stop/cancel."""
    printer.update({
        "state": "READY",
        "status": "Ready",
        "progress": 0,
        "time_remaining": 0,
        "file": None,
        "job_id": None,
        "order_id": None,
        "from_queue": False,
        "count_incremented_for_current_job": False,
        "manually_set": True,
        "manual_timeout": time.time() + 3600,
        "ejection_processed": False,
        "ejection_in_progress": False,
        "ejection_start_time": None,
        "finish_time": None,
        "cooldown_target_temp": None,
        "cooldown_order_id": None,
    })


async def stop_print(session, printer):
    """Stop a print on a printer"""
    state = printer.get('state')
    is_preparing = state == 'PREPARING'

    # Check if this is a Bambu printer
    if printer.get('type') == 'bambu':
        clear_bambu_print_assignment(printer['name'])
        hardware_ok = stop_bambu_print(printer)
        if is_preparing or hardware_ok:
            apply_cancelled_print_state(printer)
            logging.info(
                f"Cancelled print on Bambu printer {printer['name']} "
                f"(preparing={is_preparing}, hardware_ok={hardware_ok})"
            )
            return True
        return False

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
                    return True
                elif resp.status == 405:
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
                if not success:
                    logging.error(f"Failed to stop print on {printer['name']}: HTTP {resp.status}")
                return success
        except Exception as e:
            logging.error(f"Failed to stop print on {printer['name']}: {str(e)}")
            return False

    try:
        hardware_ok = await retry_async(_stop, max_retries=2, initial_backoff=1)
    except Exception as e:
        logging.error(f"Error stopping print on {printer['name']} after retries: {str(e)}")
        hardware_ok = False

    if is_preparing or hardware_ok:
        apply_cancelled_print_state(printer)
        return True
    return False


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


async def reset_printer_state(session, printer, headers):
    """Reset printer state by cancelling jobs and refreshing connection"""
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
    """Async wrapper for reset_printer_state"""
    if printer.get('type') == 'bambu':
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


async def send_print_to_printer(session, printer, filepath, filename, order_id=None, filament_g=0):
    """Send a print directly to a printer (for manual prints)"""
    if printer.get('type') == 'bambu':
        # For Bambu printers, use the MQTT command
        success, _err = send_bambu_print_command(printer, filename, filepath=filepath)
        if success:
            printer['state'] = 'PREPARING'
            printer['file'] = filename
            printer['from_queue'] = False
            printer['order_id'] = order_id
            printer['filament_used_g'] = filament_g
            printer['manually_set'] = False
            printer['ejection_processed'] = False
            printer['ejection_in_progress'] = False
            printer['finish_time'] = None
            printer['count_incremented_for_current_job'] = False
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


async def check_and_start_print(session, printer, order, headers, batch_id, app):
    """Check if print can start and initiate print job on printer.

    Returns (printer, order, success, batch_id, error_message).
    """
    global TOTAL_FILAMENT_CONSUMPTION

    # Safety check: Accept both READY and IDLE printers
    if printer.get('state') not in ['READY', 'IDLE']:
        msg = (
            f"Cannot start print on {printer['name']}: printer state is "
            f"{printer.get('state')} (expected READY or IDLE)"
        )
        logging.error(f"SAFETY: {msg} - ABORTING")
        return printer, order, False, batch_id, msg

    # Reset the count increment flag for this new job
    printer['count_incremented_for_current_job'] = False
    logging.debug(f"Starting new job for {printer['name']} - reset count increment flag")

    # Handle Bambu printers differently
    if printer.get('type') == 'bambu':
        logging.debug(f"Starting Bambu print job for {printer['name']} with order {order['id']}")

        # Send print command with file upload (prepare_gcode_for_bambu handles extensions)
        success, error_message = send_bambu_print_command(
            printer, order['filename'], filepath=order['filepath']
        )

        if success:
            old_state = printer.get('state', 'UNKNOWN')
            printer['state'] = 'PREPARING'
            printer['file'] = order['filename']
            printer['from_queue'] = True
            printer['order_id'] = order['id']
            printer['filament_used_g'] = order.get('filament_g', 0)
            printer['finish_time'] = None
            printer['count_incremented_for_current_job'] = False
            printer['manually_set'] = False
            printer['ejection_processed'] = False
            printer['ejection_in_progress'] = False
            logging.info(
                f"Printer {printer['name']} print requested: {old_state} -> PREPARING "
                f"(file: {order['filename']}, waiting for MQTT RUNNING)"
            )
            return printer, order, True, batch_id, None

        return printer, order, False, batch_id, error_message or 'Bambu print command failed'

    # Original Prusa code continues below
    file_path = f"/usb/{order['filename']}"
    file_url = f"http://{printer['ip']}/api/v1/files{file_path}"

    logging.debug(f"Starting print job for {printer['name']} with order {order['id']}")

    file_data = None
    try:
        with open(order['filepath'], "rb") as f:
            file_data = f.read()
    except Exception as e:
        msg = f"Cannot read print file {order['filepath']}: {e}"
        logging.error(msg)
        return printer, order, False, batch_id, msg

    try:
        logging.debug(f"Batch {batch_id}: Pre-emptively deleting file {order['filename']} from {printer['name']} to avoid conflicts")
        try:
            async with session.delete(file_url, headers=headers) as delete_resp:
                if delete_resp.status == 204:
                    logging.debug("Successfully deleted existing file")
                else:
                    logging.debug(f"Delete returned status {delete_resp.status}, continuing anyway")
        except Exception as e:
            logging.debug(f"Error during pre-emptive delete: {str(e)}")

        upload_error = {'message': 'Prusa upload failed'}

        logging.debug(f"Batch {batch_id}: File {order['filename']} not found, uploading...")

        async def _upload_file():
            try:
                try:
                    await asyncio.sleep(1)
                    async with session.delete(file_url, headers=headers) as delete_resp:
                        if delete_resp.status == 204:
                            logging.debug("Successfully deleted file before upload")
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
                        async with session.put(
                            file_url,
                            data=file_data,
                            headers={**headers, "Print-After-Upload": "?1", "Overwrite": "?1"}
                        ) as retry_resp:
                            if retry_resp.status == 201:
                                logging.debug(f"Upload successful on retry for {printer['name']}")
                                return True
                            upload_error['message'] = (
                                f"Upload failed on retry: HTTP {retry_resp.status}"
                            )
                            logging.error(f"Batch {batch_id}: {upload_error['message']}")
                            return False
                    else:
                        upload_error['message'] = f"Upload failed: HTTP {upload_resp.status}"
                        logging.error(f"Batch {batch_id}: {upload_error['message']}")
                        return False
            except Exception as e:
                upload_error['message'] = f"Error uploading file: {e}"
                logging.error(upload_error['message'])
                return False

        success = await retry_async(_upload_file, max_retries=2, initial_backoff=2)

        if success:
            old_state = printer.get('state', 'UNKNOWN')
            printer['state'] = 'PRINTING'
            printer['file'] = order['filename']
            printer['from_queue'] = True
            logging.info(f"Printer {printer['name']} started printing: {old_state} -> PRINTING (file: {order['filename']})")

            # Increment count when print starts
            success_increment, updated_order = increment_order_sent_count(order['id'])
            if success_increment:
                clear_queue_job_error(order['id'])
                logging.info(f"Incremented sent count for Prusa order {order['id']} to {updated_order['sent']}")
                # Increment filament immediately
                with SafeLock(filament_lock):
                    old_total = TOTAL_FILAMENT_CONSUMPTION
                    TOTAL_FILAMENT_CONSUMPTION += order['filament_g']
                    save_data(TOTAL_FILAMENT_FILE, {"total_filament_used_g": TOTAL_FILAMENT_CONSUMPTION})
                    logging.warning(f"[FILAMENT TRACKING] Print started on Prusa {printer['name']} - added {order['filament_g']}g ({old_total}g -> {TOTAL_FILAMENT_CONSUMPTION}g)")
                printer['order_id'] = order['id']
                printer['from_queue'] = True
                printer['finish_time'] = None
                printer['count_incremented_for_current_job'] = True

            # Run verification in background
            async def verify_and_update():
                await asyncio.sleep(5)
                try:
                    verified = await verify_print_started(session, printer, order['filename'], headers)
                    if verified:
                        logging.debug(f"Verified print start for {printer['name']}")
                    else:
                        logging.warning(f"Final verification failed: could not get status for {printer['name']}")
                except Exception as e:
                    logging.error(f"Error in final verification for {printer['name']}: {str(e)}")

            asyncio.create_task(verify_and_update())

            printer['total_filament_used_g'] = printer.get('total_filament_used_g', 0) + order['filament_g']
            printer['filament_used_g'] = order['filament_g']
            printer['manually_set'] = False
            printer['ejection_processed'] = False
            printer['ejection_in_progress'] = False
            printer['finish_time'] = None
            logging.debug(f"Batch {batch_id}: Sent {order['filename']} to {printer['name']}, filament: {order['filament_g']}, order_id: {order['id']}")
            logging.debug(f"Successfully configured {printer['name']} to print order {order['id']} in thread {threading.current_thread().name} ({threading.get_ident()})")
            return printer, order, True, batch_id, None

        return printer, order, False, batch_id, upload_error['message']

    except Exception as e:
        msg = f"Error processing print on {printer['name']}: {e}"
        logging.error(f"Batch {batch_id}: {msg}")
        return printer, order, False, batch_id, msg


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


def _emit_printer_status_after_stop(socketio, app):
    """Broadcast printer/order state after stop or cancel."""
    from services.state import (
        PRINTERS,
        ORDERS,
        printers_rwlock,
        orders_lock,
        filament_lock,
        TOTAL_FILAMENT_CONSUMPTION,
        ReadLock,
        SafeLock,
    )
    from services.printer_manager import (
        prepare_printer_data_for_broadcast,
        start_background_distribution,
    )
    from utils.socketio_emit import emit_status_update

    with SafeLock(filament_lock):
        total_filament = TOTAL_FILAMENT_CONSUMPTION / 1000
    with SafeLock(orders_lock):
        orders_data = copy.deepcopy(ORDERS)
    with ReadLock(printers_rwlock):
        printers_data = prepare_printer_data_for_broadcast(PRINTERS)

    emit_status_update(socketio, app, {
        'printers': printers_data,
        'total_filament': total_filament,
        'orders': orders_data,
    })
    start_background_distribution(socketio, app)


_BAMBU_ACTIVE_MQTT_STATES = frozenset({
    'PREPARING', 'PREPARE', 'PRINTING', 'PAUSED', 'RUNNING',
})


def _bambu_mqtt_shows_active_job(printer_name: str) -> bool:
    """True when Bambu MQTT cache still reports an in-flight job."""
    from services.bambu_handler import BAMBU_PRINTER_STATES, bambu_states_lock

    with bambu_states_lock:
        mqtt_state = BAMBU_PRINTER_STATES.get(printer_name, {}).get('state')
    return mqtt_state in _BAMBU_ACTIVE_MQTT_STATES


def is_printer_stoppable(printer: dict) -> bool:
    """Whether stop/cancel should be accepted for this printer snapshot."""
    state = printer.get('state')
    if state in ('PRINTING', 'PAUSED', 'PREPARING'):
        return True
    # Stuck assignment after spurious FINISHED or failed prep
    if printer.get('order_id') and state in ('READY', 'FINISHED', 'ERROR'):
        return True
    if printer.get('type') == 'bambu' and _bambu_mqtt_shows_active_job(printer['name']):
        return True
    return False


def _needs_sync_cancel(printer: dict) -> bool:
    """Jobs that should be cleared under the printers write lock (no background thread)."""
    state = printer.get('state')
    if state == 'PREPARING':
        return True
    if printer.get('order_id') and state in ('READY', 'FINISHED', 'ERROR'):
        return True
    if printer.get('type') == 'bambu' and _bambu_mqtt_shows_active_job(printer['name']):
        return state not in ('PRINTING', 'PAUSED')
    return False


def _cancel_print_sync_locked(printer: dict, printer_name: str) -> None:
    """Reset printer job state. Caller must hold WriteLock(printers_rwlock)."""
    from services.state import PRINTERS, PRINTERS_FILE, save_data

    if printer.get('type') == 'bambu':
        clear_bambu_print_assignment(printer_name)
        stop_bambu_print(printer)
    apply_cancelled_print_state(printer)
    save_data(PRINTERS_FILE, PRINTERS)
    logging.info(f"Synchronously cancelled print on {printer_name}")


def cancel_preparing_print_sync(printer_name, socketio, app):
    """Cancel a stuck PREPARING job immediately (no background thread)."""
    from services.state import PRINTERS, printers_rwlock, WriteLock

    cancelled = False
    with WriteLock(printers_rwlock):
        for printer in PRINTERS:
            if printer['name'] != printer_name:
                continue
            if not is_printer_stoppable(printer):
                return None
            _cancel_print_sync_locked(printer, printer_name)
            cancelled = True
            break
    if cancelled:
        _emit_printer_status_after_stop(socketio, app)
        return True
    return False


def schedule_stop_print_by_name(printer_name, socketio, app):
    """Run stop/cancel; returns False if printer not found, None if not stoppable."""
    from services.state import (
        PRINTERS,
        printers_rwlock,
        WriteLock,
        save_data,
        PRINTERS_FILE,
    )
    from utils.threading_compat import spawn_os_daemon

    printer_copy = None
    printer_idx = None
    sync_cancelled = False

    with WriteLock(printers_rwlock):
        for i, printer in enumerate(PRINTERS):
            if printer['name'] != printer_name:
                continue
            if not is_printer_stoppable(printer):
                return None
            if _needs_sync_cancel(printer):
                _cancel_print_sync_locked(printer, printer_name)
                sync_cancelled = True
                break
            printer_copy = copy.deepcopy(printer)
            printer_idx = i
            break

    if sync_cancelled:
        _emit_printer_status_after_stop(socketio, app)
        return True

    if printer_copy is None or printer_idx is None:
        return False

    def background_stop_task():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def execute_stop():
                async with aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(limit=10, ttl_dns_cache=300),
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as session:
                    return await stop_print(session, printer_copy)

            success = loop.run_until_complete(execute_stop())
            loop.close()

            if success:
                with WriteLock(printers_rwlock):
                    if 0 <= printer_idx < len(PRINTERS):
                        apply_cancelled_print_state(PRINTERS[printer_idx])
                        save_data(PRINTERS_FILE, PRINTERS)
                _emit_printer_status_after_stop(socketio, app)
        except Exception as e:
            logging.error(f"Error stopping print on {printer_name}: {e}")

    spawn_os_daemon(background_stop_task, name=f"stop-print-{printer_name}")
    return True
