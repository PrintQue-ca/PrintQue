"""
Order distribution logic - handles assigning orders to available printers.
"""
import os
import re
import time
import uuid
import asyncio
import aiohttp
import threading
from datetime import datetime

from services.state import (
    PRINTERS_FILE, TOTAL_FILAMENT_FILE, PRINTERS, QUEUE_JOBS, save_data, load_data, decrypt_api_key,
    logging, orders_lock, filament_lock, printers_rwlock,
    SafeLock, ReadLock, WriteLock
)
from services.print_jobs import check_and_start_print
from services.library_queue import record_queue_job_error
from services.printer_utils import run_async_in_thread, spawn_os_thread
from services.status_poller import prepare_printer_data_for_broadcast
from utils.config import Config
from utils.logger import log_distribution_event, log_job_lifecycle
from utils.threading_compat import native_threading
from utils.socketio_emit import emit_status_update
from services.bambu_handler import (
    BAMBU_PRINTER_STATES,
    bambu_states_lock,
    clear_stale_bambu_error_if_idle,
)

# Semaphore to prevent concurrent distribution runs (native — acquired from OS threads)
distribution_semaphore = native_threading().Semaphore(1)


def _printer_available_for_distribution(printer: dict) -> bool:
    """True if printer can accept a new queue job (not mid-ejection)."""
    if printer.get('state') not in ('READY', 'IDLE'):
        return False
    if printer.get('ejection_in_progress'):
        return False
    if printer.get('state') == 'EJECTING':
        return False
    if printer.get('type') == 'bambu':
        name = printer.get('name')
        with bambu_states_lock:
            bambu = BAMBU_PRINTER_STATES.get(name, {})
        if bambu.get('state') == 'EJECTING':
            return False
        if bambu.get('waiting_for_m400') or bambu.get('ejection_m400_pending', 0) > 0:
            return False
        if bambu.get('state') == 'ERROR':
            if not clear_stale_bambu_error_if_idle(name):
                return False
            with bambu_states_lock:
                bambu = BAMBU_PRINTER_STATES.get(name, {})
    return True


def has_pending_queue_copies() -> bool:
    """True if any queue job still needs more copies (same filter as distribute_orders_async)."""
    with SafeLock(orders_lock):
        for job in QUEUE_JOBS:
            if (
                not job.get('deleted', False)
                and job.get('status') != 'completed'
                and job.get('sent', 0) < job.get('quantity', 1)
            ):
                return True
    return False


def count_distributable_printers() -> int:
    """Count non-service printers that can accept a new queue job."""
    with ReadLock(printers_rwlock):
        return sum(
            1
            for p in PRINTERS
            if not p.get('service_mode', False) and _printer_available_for_distribution(p)
        )


def pending_distribution_needed() -> bool:
    """True when pending copies exist and at least one printer can take a job."""
    return has_pending_queue_copies() and count_distributable_printers() > 0


def periodic_pending_distribution_check(socketio, app):
    """Periodically trigger distribution when partial jobs and ready printers coexist."""
    interval = Config.DISTRIBUTION_INTERVAL
    while True:
        try:
            time.sleep(interval)
            if pending_distribution_needed():
                logging.debug(
                    "Periodic check: pending queue copies and distributable printers — "
                    "starting distribution"
                )
                start_background_distribution(socketio, app)
        except Exception as e:
            logging.error(f"Error in periodic pending distribution check: {e}")
            time.sleep(interval)


def start_background_distribution(socketio, app, batch_size=10):
    """Start order distribution in a background thread"""
    # Non-blocking acquire only — avoid blocking the caller when distribution is busy.
    if not distribution_semaphore.acquire(blocking=False):
        logging.debug(
            "Distribution already running (thread=%s id=%s)",
            threading.current_thread().name,
            threading.get_ident(),
        )
        return None

    # Check if this is happening at night
    current_hour = datetime.now().hour
    if 0 <= current_hour < 6:
        import traceback
        log_distribution_event('MIDNIGHT_DISTRIBUTION_TRIGGERED', {
            'time': datetime.now().isoformat(),
            'triggered_by': str(traceback.extract_stack()[-2]),
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

    spawn_os_thread(run_with_semaphore, daemon=True, name=f'Distribution-{task_id[:8]}')
    return task_id


def run_background_distribution(socketio, app, task_id, batch_size=10):
    """Run the async distribution in a synchronous context"""
    try:
        run_async_in_thread(distribute_orders_async(socketio, app, task_id, batch_size))
    except Exception as e:
        logging.error(f"Error in background distribution: {str(e)}")


async def distribute_orders_async(socketio, app, task_id=None, batch_size=10):
    """Main order distribution logic - assigns pending orders to available printers"""
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

    global TOTAL_FILAMENT_CONSUMPTION

    MAX_CONCURRENT_JOBS = 10

    current_filament = 0
    with SafeLock(filament_lock):
        filament_data = load_data(TOTAL_FILAMENT_FILE, {"total_filament_used_g": 0})
        current_filament = filament_data.get("total_filament_used_g", 0)
        TOTAL_FILAMENT_CONSUMPTION = current_filament
        logging.debug(f"Starting distribution - total filament: {TOTAL_FILAMENT_CONSUMPTION}g")

    processed_order_printers = set()

    active_orders = []
    with SafeLock(orders_lock):
        active_orders = [o.copy() for o in QUEUE_JOBS
                        if not o.get('deleted', False)
                        and o['status'] != 'completed'
                        and o['sent'] < o['quantity']]
        logging.debug(f"Active orders: {[(o['id'], o['sent'], o['quantity']) for o in active_orders]}")

    if not active_orders:
        logging.debug("No active orders to distribute, skipping distribution")
        return

    ready_printers = []
    with ReadLock(printers_rwlock):
        all_printers = [p.copy() for p in PRINTERS if not p.get('service_mode', False)]
        # Include both READY and IDLE printers for job distribution
        ready_printers = [p for p in all_printers if _printer_available_for_distribution(p)]

        printer_states = {}
        for p in all_printers:
            state = p['state']
            if state not in printer_states:
                printer_states[state] = []
            printer_states[state].append(p['name'])

        # Log FINISHED printers that are being skipped
        if 'FINISHED' in printer_states:
            logging.debug(f"Skipping {len(printer_states['FINISHED'])} FINISHED printers: {printer_states['FINISHED']}")

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
            # Text-based group filtering
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

            filepath = order.get('filepath') or ''
            if not filepath or not os.path.exists(filepath):
                record_queue_job_error(
                    order['id'],
                    f"Print file not found: {filepath or '(empty path)'}",
                    phase='file_missing',
                    batch_id=batch_id,
                    task_id=task_id,
                )
                continue

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
                    job_data['headers'] = {}
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

            for job, result in zip(batch_jobs, batch_results):
                total_processed += 1
                order = job['order']
                printer = job['printer']

                if isinstance(result, Exception):
                    err_msg = str(result)
                    logging.error(f"Error in print job for order {order['id']}: {err_msg}")
                    phase = 'bambu_start' if printer.get('type') == 'bambu' else 'prusa_upload'
                    record_queue_job_error(
                        order['id'],
                        err_msg,
                        printer_name=printer['name'],
                        phase=phase,
                        batch_id=batch_id,
                        task_id=task_id,
                    )
                    continue

                if not isinstance(result, tuple) or len(result) < 4:
                    logging.error(f"Unexpected result format: {result}")
                    record_queue_job_error(
                        order['id'],
                        f"Unexpected print start result: {result!r}",
                        printer_name=printer['name'],
                        phase='unknown',
                        batch_id=batch_id,
                        task_id=task_id,
                    )
                    continue

                result_printer, result_order, success = result[0], result[1], result[2]
                error_message = result[4] if len(result) > 4 else None
                printer = result_printer
                order = result_order

                if success:
                    total_successful += 1
                    updated_printers[printer['name']] = printer

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
                else:
                    phase = 'bambu_start' if printer.get('type') == 'bambu' else 'prusa_upload'
                    record_queue_job_error(
                        order['id'],
                        error_message or 'Print start failed',
                        printer_name=printer['name'],
                        phase=phase,
                        batch_id=batch_id,
                        task_id=task_id,
                    )

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
        orders_data = QUEUE_JOBS.copy()
        logging.debug(f"Post-distribution orders: {[(o['id'], o['sent'], o['quantity']) for o in orders_data if o['status'] != 'completed']}")

    with ReadLock(printers_rwlock):
        printers_copy = prepare_printer_data_for_broadcast(PRINTERS)

    logging.debug(f"Final summary: {total_processed} jobs processed, {total_successful} successful, {total_processed - total_successful} failed")

    emit_status_update(socketio, app, {
        'printers': printers_copy,
        'total_filament': total_filament,
        'queue': orders_data,
    })
