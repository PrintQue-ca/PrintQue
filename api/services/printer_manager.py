"""
Printer Manager - Facade module that re-exports from focused submodules.

This module maintains backward compatibility by re-exporting all public functions
from the following submodules:
- printer_utils: Utility functions (deduplication, filament, connection management)
- ejection_manager: Ejection lock and handling
- print_jobs: Print job control (start/stop/pause/resume)
- status_poller: Status polling and broadcasting
- order_distributor: Order distribution logic
"""
import time
import threading
import asyncio

from services.state import (
    PRINTERS, ORDERS, TOTAL_FILAMENT_CONSUMPTION,
    logging, orders_lock, filament_lock, printers_rwlock,
    SafeLock, ReadLock, reconcile_order_counts
)
from utils.config import Config

# Re-export from printer_utils
from services.printer_utils import (
    deduplicate_printers,
    deduplicate_orders,
    periodic_deduplication_check,
    convert_mm_to_g,
    extract_filament_from_file,
    get_event_loop_for_thread,
    get_connection_pool,
    get_session,
    close_connection_pool,
    emergency_fix_stuck_printers,
    mark_group_ready,
    thread_local,
    CONNECTION_POOL,
)

# Re-export from ejection_manager
from services.ejection_manager import (
    EJECTION_LOCKS,
    ejection_locks_lock,
    get_ejection_lock,
    is_ejection_in_progress,
    release_ejection_lock,
    force_release_all_ejection_locks,
    clear_stuck_ejection_locks,
    detect_ejection_completion,
    handle_finished_state_ejection,
    async_send_ejection_gcode,
    enhanced_prusa_ejection_monitoring,
    start_prusa_ejection_monitor,
    trigger_mass_ejection_for_finished_printers,
)

# Re-export from print_jobs
from services.print_jobs import (
    match_shortened_filename,
    verify_print_started,
    stop_print,
    stop_print_async,
    pause_print_async,
    resume_print_async,
    reset_printer_state,
    reset_printer_state_async,
    send_print_to_printer,
    check_and_start_print,
    pause_bambu_print_wrapper,
    resume_bambu_print_wrapper,
    is_bambu_printer,
)

# Re-export from status_poller
from services.status_poller import (
    state_map,
    get_minutes_since_finished,
    prepare_printer_data_for_broadcast,
    update_bambu_printer_states,
    ensure_finish_times,
    fetch_status,
    get_printer_status_async,
)

# Re-export from order_distributor
from services.order_distributor import (
    distribution_semaphore,
    start_background_distribution,
    run_background_distribution,
    distribute_orders_async,
)


def start_background_tasks(socketio, app):
    """
    Start all background tasks for the printer management system.
    This coordinates startup across all submodules.
    """
    from services.status_poller import get_printer_status_async, prepare_printer_data_for_broadcast
    from services.printer_utils import periodic_deduplication_check
    from services.ejection_manager import start_prusa_ejection_monitor

    # Start enhanced Prusa ejection monitoring
    start_prusa_ejection_monitor()

    # Ensure all FINISHED printers have finish_time
    ensure_finish_times()

    # Connect Bambu printers in a background thread so the server isn't blocked
    from services.bambu_handler import connect_bambu_printer

    def _connect_bambu_printers():
        with ReadLock(printers_rwlock):
            bambu_printers = [p for p in PRINTERS if p.get('type') == 'bambu']
        for printer in bambu_printers:
            try:
                connect_bambu_printer(printer)
            except Exception as e:
                logging.error(f"Failed to connect Bambu printer {printer['name']}: {e}")

    bambu_thread = threading.Thread(target=_connect_bambu_printers, daemon=True)
    bambu_thread.start()

    def schedule_status_polling():
        batch_index = 0
        while True:
            try:
                with ReadLock(printers_rwlock):
                    total_printers = len([p for p in PRINTERS if not p.get('service_mode', False)])

                if total_printers == 0:
                    logging.debug("No printers configured, waiting...")
                    time.sleep(Config.STATUS_REFRESH_INTERVAL)
                    continue

                num_batches = (total_printers + Config.STATUS_BATCH_SIZE - 1) // Config.STATUS_BATCH_SIZE

                logging.debug(f"Processing batch {batch_index + 1}/{num_batches}")

                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                loop.run_until_complete(get_printer_status_async(socketio, app, batch_index, Config.STATUS_BATCH_SIZE))

                batch_index = (batch_index + 1) % num_batches
                time.sleep(Config.STATUS_REFRESH_INTERVAL)

            except Exception as e:
                logging.error(f"Error in status polling: {str(e)}")
                time.sleep(Config.STATUS_REFRESH_INTERVAL)

    status_thread = threading.Thread(target=schedule_status_polling)
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


# Export all public symbols for backward compatibility
__all__ = [
    # printer_utils
    'deduplicate_printers',
    'deduplicate_orders',
    'periodic_deduplication_check',
    'convert_mm_to_g',
    'extract_filament_from_file',
    'get_event_loop_for_thread',
    'get_connection_pool',
    'get_session',
    'close_connection_pool',
    'emergency_fix_stuck_printers',
    'mark_group_ready',
    'thread_local',
    'CONNECTION_POOL',
    # ejection_manager
    'EJECTION_LOCKS',
    'ejection_locks_lock',
    'get_ejection_lock',
    'is_ejection_in_progress',
    'release_ejection_lock',
    'force_release_all_ejection_locks',
    'clear_stuck_ejection_locks',
    'detect_ejection_completion',
    'handle_finished_state_ejection',
    'async_send_ejection_gcode',
    'enhanced_prusa_ejection_monitoring',
    'start_prusa_ejection_monitor',
    'trigger_mass_ejection_for_finished_printers',
    # print_jobs
    'match_shortened_filename',
    'verify_print_started',
    'stop_print',
    'stop_print_async',
    'pause_print_async',
    'resume_print_async',
    'reset_printer_state',
    'reset_printer_state_async',
    'send_print_to_printer',
    'check_and_start_print',
    'pause_bambu_print_wrapper',
    'resume_bambu_print_wrapper',
    'is_bambu_printer',
    # status_poller
    'state_map',
    'get_minutes_since_finished',
    'prepare_printer_data_for_broadcast',
    'update_bambu_printer_states',
    'ensure_finish_times',
    'fetch_status',
    'get_printer_status_async',
    # order_distributor
    'distribution_semaphore',
    'start_background_distribution',
    'run_background_distribution',
    'distribute_orders_async',
    # Main function
    'start_background_tasks',
]
