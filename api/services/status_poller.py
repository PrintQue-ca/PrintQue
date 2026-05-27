"""
Status polling and broadcasting for printer status updates.
Handles fetching printer status from APIs and broadcasting to clients.
"""
import json
import os
import time
import asyncio
import aiohttp
import copy

from services.state import (
    PRINTERS_FILE, TOTAL_FILAMENT_FILE, TOTAL_FILAMENT_CONSUMPTION,
    PRINTERS, ORDERS, save_data, load_data, decrypt_api_key,
    logging, orders_lock, filament_lock, printers_rwlock,
    SafeLock, ReadLock, WriteLock,
    get_printer_ejection_state, clear_printer_ejection_state,
    resolve_ejection_gcode,
    increment_queue_sent_count,
    relink_orphaned_active_prints,
)
from services.default_settings import DEFAULT_EJECTION_GCODE
from services.library_queue import clear_queue_job_error, record_queue_job_error
from services.bambu_handler import (
    get_bambu_status, send_bambu_ejection_gcode,
    BAMBU_PRINTER_STATES, BAMBU_LIVE_STATUS_SEEN, bambu_states_lock,
    clear_bambu_print_assignment,
    clear_stale_bambu_error_if_idle,
)
from services.ejection_manager import (
    clear_stuck_ejection_locks, release_ejection_lock,
    handle_finished_state_ejection, async_send_ejection_gcode
)
from utils.config import Config
from utils.retry_utils import retry_async
from utils.logger import log_state_transition, log_api_poll_event
from utils.threading_compat import os_timer
from utils.socketio_emit import emit_status_update

# Re-export pure/near-pure helpers so existing imports keep working
from utils.status_poller_helpers import (           # noqa: F401
    state_map,
    get_minutes_since_finished,
    prepare_printer_data_for_broadcast,
    bed_temp_reached_cooldown_target,
    bed_temp_needs_cooling,
    _build_minimal_printer,
    _offline_update,
    _ready_update,
    _api_temps,
)

# Set from start_background_tasks so MQTT-driven cooling checks can broadcast.
_status_broadcast_refs = {'socketio': None, 'app': None}

# Session-only: Prusa/Octoprint printers with a successful HTTP status this process.
PRUSA_LIVE_STATUS_SEEN: set[str] = set()
PRUSA_OFFLINE_POLL_FAILURES: dict[str, int] = {}
PRUSA_LIVE_MAX_OFFLINE_POLLS = 3


def _should_preserve_on_unreachable(printer: dict) -> bool:
    """Skip OFFLINE downgrade during API restart reconnect (before live status)."""
    name = printer['name']
    if printer.get('state', 'READY') == 'OFFLINE':
        return False
    if printer.get('type') == 'bambu':
        return name not in BAMBU_LIVE_STATUS_SEEN
    if name in PRUSA_LIVE_STATUS_SEEN:
        return False
    failures = PRUSA_OFFLINE_POLL_FAILURES.get(name, 0) + 1
    PRUSA_OFFLINE_POLL_FAILURES[name] = failures
    return failures < PRUSA_LIVE_MAX_OFFLINE_POLLS
_cooling_check_timers = {}
_cooling_ui_broadcast_last = {}
_cooling_printer_names: set = set()
_COOLING_CHECK_DEBOUNCE_SEC = 2.0
_COOLING_UI_BROADCAST_INTERVAL_SEC = 3.0

# Bambu queue "sent" counts only when a newly distributed copy leaves prepare and starts printing.
_BAMBU_SENT_COUNT_START_STATES = frozenset({'PREPARING', 'PREPARE'})
_COOLING_MAINTAIN_INTERVAL_SEC = 12.0

# #region agent log
_AGENT_DEBUG_LOG = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'debug-e398f0.log')
)


def _agent_debug_log(location, message, data, hypothesis_id):
    try:
        with open(_AGENT_DEBUG_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps({
                'sessionId': 'e398f0',
                'location': location,
                'message': message,
                'data': data,
                'hypothesisId': hypothesis_id,
                'timestamp': int(time.time() * 1000),
            }) + '\n')
    except Exception:
        pass
# #endregion


def set_status_broadcast_refs(socketio, app):
    """Register Socket.IO + Flask app for background status broadcasts."""
    _status_broadcast_refs['socketio'] = socketio
    _status_broadcast_refs['app'] = app


def is_cooling_printer(printer_name: str) -> bool:
    """Fast check for MQTT handlers (updated by cooling maintenance loop)."""
    return printer_name in _cooling_printer_names


def _refresh_cooling_printer_names():
    global _cooling_printer_names
    try:
        with ReadLock(printers_rwlock):
            _cooling_printer_names = {
                p['name']
                for p in PRINTERS
                if p.get('type') == 'bambu' and p.get('state') == 'COOLING'
            }
    except TimeoutError:
        logging.debug('Could not refresh COOLING printer list (lock timeout)')


def maintain_cooling_printers():
    """While printers are COOLING: MQTT pushall + threshold checks + UI broadcasts."""
    from services.bambu_handler import request_bambu_status_for_cooling

    while True:
        try:
            time.sleep(_COOLING_MAINTAIN_INTERVAL_SEC)
            _refresh_cooling_printer_names()
            if not _cooling_printer_names:
                continue

            with ReadLock(printers_rwlock):
                cooling_printers = [
                    p for p in PRINTERS
                    if p.get('name') in _cooling_printer_names
                ]

            for printer in cooling_printers:
                name = printer['name']
                request_bambu_status_for_cooling(printer, force=True)
                with bambu_states_lock:
                    bambu = BAMBU_PRINTER_STATES.get(name, {})
                    bed = bambu.get('bed_temp')
                    updated_at = bambu.get('bed_temp_updated_at', 0)
                if updated_at and time.time() - updated_at > 45:
                    logging.warning(
                        f"COOLING {name}: bed_temp MQTT stale "
                        f"({bed}°C cached, no bed_temper for "
                        f"{time.time() - updated_at:.0f}s) — requested pushall"
                    )
                schedule_cooling_ejection_check(name)
        except Exception as e:
            logging.error(f"Error in maintain_cooling_printers: {e}")


def start_cooling_maintenance():
    from services.printer_utils import spawn_os_thread
    spawn_os_thread(maintain_cooling_printers, daemon=True, name='CoolingMaintain')


def _get_bambu_bed_temp(printer_name):
    try:
        with bambu_states_lock:
            if printer_name in BAMBU_PRINTER_STATES:
                return float(BAMBU_PRINTER_STATES[printer_name].get('bed_temp', 0) or 0)
    except Exception as e:
        logging.warning(f"Could not get bed temp for {printer_name}: {e}")
    return 0.0


def _get_bambu_nozzle_temp(printer_name):
    try:
        with bambu_states_lock:
            if printer_name in BAMBU_PRINTER_STATES:
                return float(BAMBU_PRINTER_STATES[printer_name].get('nozzle_temp', 0) or 0)
    except Exception as e:
        logging.warning(f"Could not get nozzle temp for {printer_name}: {e}")
    return 0.0


def _coerce_cooldown_target(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_cooling_order(cooldown_order_id):
    if cooldown_order_id is None:
        return None
    with SafeLock(orders_lock):
        return next((o for o in ORDERS if o['id'] == cooldown_order_id), None)


def _sync_cooling_temps(printer):
    """Copy live MQTT temps onto the printer record while in COOLING."""
    printer_name = printer['name']
    bed_temp = _get_bambu_bed_temp(printer_name)
    nozzle_temp = _get_bambu_nozzle_temp(printer_name)
    printer['bed_temp'] = bed_temp
    printer['nozzle_temp'] = nozzle_temp
    if 'temps' not in printer or not isinstance(printer.get('temps'), dict):
        printer['temps'] = {}
    printer['temps']['bed'] = bed_temp
    printer['temps']['nozzle'] = nozzle_temp
    return bed_temp, nozzle_temp


def _maybe_broadcast_cooling_ui(printer_name, *, force=False):
    """Push live COOLING temps to the UI (throttled)."""
    socketio = _status_broadcast_refs.get('socketio')
    app = _status_broadcast_refs.get('app')
    if not socketio or not app:
        return
    now = time.time()
    last = _cooling_ui_broadcast_last.get(printer_name, 0)
    if not force and (now - last) < _COOLING_UI_BROADCAST_INTERVAL_SEC:
        return
    _cooling_ui_broadcast_last[printer_name] = now
    _broadcast_status_snapshot(socketio, app)


def _broadcast_status_snapshot(socketio, app):
    if not socketio or not app:
        return
    current_filament = None
    with SafeLock(filament_lock):
        filament_data = load_data(TOTAL_FILAMENT_FILE, {"total_filament_used_g": 0})
        current_filament = filament_data.get("total_filament_used_g", 0) / 1000
    with ReadLock(printers_rwlock):
        printers_copy = prepare_printer_data_for_broadcast(PRINTERS)
    emit_status_update(socketio, app, {
        'printers': printers_copy,
        'total_filament': current_filament,
    })


def _complete_cooling_ejection_send(printer_name, gcode_content, socketio=None, app=None):
    """Send Bambu ejection G-code outside printers_rwlock, then fix up state on failure."""
    socketio = socketio or _status_broadcast_refs.get('socketio')
    app = app or _status_broadcast_refs.get('app')

    with ReadLock(printers_rwlock):
        printer = next((p for p in PRINTERS if p.get('name') == printer_name), None)
        if not printer:
            return
        printer_snapshot = copy.deepcopy(printer)

    success = send_bambu_ejection_gcode(printer_snapshot, gcode_content)

    need_save = False
    try:
        with WriteLock(printers_rwlock):
            printer = next((p for p in PRINTERS if p.get('name') == printer_name), None)
            if not printer:
                return
            if not success and printer.get('state') == 'EJECTING':
                logging.error(f"Bambu ejection failed for {printer_name} after cooling")
                printer.update({
                    "state": 'READY',
                    "status": 'Ready',
                    "ejection_processed": False,
                    "ejection_in_progress": False,
                    "manually_set": True,
                })
                need_save = True
    except TimeoutError as e:
        logging.error(f"Could not update printer after cooling ejection for {printer_name}: {e}")
        return

    if need_save:
        save_data(PRINTERS_FILE, PRINTERS)
    _broadcast_status_snapshot(socketio, app)


def schedule_cooling_ejection_check(printer_name):
    """Debounced COOLING threshold check (e.g. after MQTT bed temp update)."""
    from utils.threading_compat import os_timer

    existing = _cooling_check_timers.pop(printer_name, None)
    if existing is not None:
        try:
            existing.cancel()
        except Exception:
            pass

    def _fire():
        _cooling_check_timers.pop(printer_name, None)
        _run_cooling_ejection_check(printer_name)

    _cooling_check_timers[printer_name] = os_timer(
        _COOLING_CHECK_DEBOUNCE_SEC, _fire
    )


def _run_cooling_ejection_check(printer_name):
    socketio = _status_broadcast_refs.get('socketio')
    app = _status_broadcast_refs.get('app')
    pending = None

    need_save = False
    try:
        with WriteLock(printers_rwlock):
            printer = next((p for p in PRINTERS if p.get('name') == printer_name), None)
            if not printer or printer.get('state') != 'COOLING':
                return
            pending = _monitor_cooling_state(printer)
            need_save = True
    except TimeoutError:
        logging.error(
            f"Cooling ejection check timed out acquiring printers lock for {printer_name}"
        )
        return

    if need_save:
        save_data(PRINTERS_FILE, PRINTERS)

    if pending and pending.get('action') == 'eject':
        _complete_cooling_ejection_send(
            printer_name, pending['gcode'], socketio=socketio, app=app
        )
    elif pending and pending.get('action') == 'state_only':
        _maybe_broadcast_cooling_ui(printer_name, force=True)
    else:
        # Still cooling — refresh UI temps / status text.
        _maybe_broadcast_cooling_ui(printer_name)


def update_bambu_printer_states():
    """Update main printer states from Bambu MQTT data and track filament usage"""
    global TOTAL_FILAMENT_CONSUMPTION

    # Get Bambu states snapshot
    with bambu_states_lock:
        bambu_states = copy.deepcopy(BAMBU_PRINTER_STATES)

    if not bambu_states:
        return

    updates_made = False
    pending_sent_increments = []
    pending_filament_g = []
    flag_updates_need_save = False

    with WriteLock(printers_rwlock):
        for printer in PRINTERS:
            if printer.get('type') != 'bambu':
                continue

            printer_name = printer.get('name')
            if printer_name not in bambu_states:
                continue

            bambu_state = bambu_states[printer_name]
            current_state = printer.get('state', 'Unknown')

            # COOLING state is managed by the cooling monitor; still sync live MQTT temps.
            if current_state == 'COOLING':
                if 'nozzle_temp' in bambu_state:
                    printer['nozzle_temp'] = bambu_state['nozzle_temp']
                if 'bed_temp' in bambu_state:
                    printer['bed_temp'] = bambu_state['bed_temp']
                if isinstance(printer.get('temps'), dict):
                    if 'nozzle_temp' in bambu_state:
                        printer['temps']['nozzle'] = bambu_state['nozzle_temp']
                    if 'bed_temp' in bambu_state:
                        printer['temps']['bed'] = bambu_state['bed_temp']
                continue

            # Get the new state from Bambu MQTT
            new_state = bambu_state.get('state', current_state)

            # Protect manually-set READY state from being overwritten by stale MQTT states
            # (e.g., FINISHED, PREPARING after user cancel), but still allow real activity
            # (PRINTING, EJECTING) when a new job actually starts.
            if printer.get('manually_set', False) and current_state == 'READY':
                pending_file = bambu_state.get('pending_print_file')
                if new_state in ('PREPARING', 'PREPARE') and not pending_file:
                    logging.debug(
                        f"Bambu {printer_name}: preserving manually-set READY "
                        f"(ignoring stale MQTT {new_state} after cancel)"
                    )
                    # #region agent log
                    if printer.get('order_id'):
                        _agent_debug_log(
                            'status_poller.py:manual_ready_ignore_preparing',
                            'manually_set READY ignored PREPARING while job assigned',
                            {
                                'printer': printer_name,
                                'order_id': printer.get('order_id'),
                                'new_state': new_state,
                                'pending_file': pending_file,
                            },
                            'H2',
                        )
                    # #endregion
                    if 'nozzle_temp' in bambu_state:
                        printer['nozzle_temp'] = bambu_state['nozzle_temp']
                    if 'bed_temp' in bambu_state:
                        printer['bed_temp'] = bambu_state['bed_temp']
                    continue
                if new_state not in ['PRINTING', 'PREPARING', 'EJECTING', 'PREPARE', 'PAUSED']:
                    if new_state == 'ERROR':
                        if clear_stale_bambu_error_if_idle(printer_name):
                            if 'nozzle_temp' in bambu_state:
                                printer['nozzle_temp'] = bambu_state['nozzle_temp']
                            if 'bed_temp' in bambu_state:
                                printer['bed_temp'] = bambu_state['bed_temp']
                            continue
                    else:
                        logging.debug(
                            f"Bambu {printer_name}: preserving manually-set READY state "
                            f"(ignoring MQTT state {new_state})"
                        )
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
            if new_state in ('PRINTING', 'PREPARING'):
                if 'progress' in bambu_state:
                    printer['progress'] = bambu_state['progress']
                if 'time_remaining' in bambu_state:
                    printer['time_remaining'] = bambu_state['time_remaining']
                # Bambu MQTT stores current file under 'current_file'; support both for compatibility
                if 'current_file' in bambu_state:
                    printer['file'] = bambu_state['current_file']
                elif 'file' in bambu_state:
                    printer['file'] = bambu_state['file']

            # Count queue job as sent when prepare finishes and the copy actually starts printing.
            # #region agent log
            if (
                new_state == 'PRINTING'
                and printer.get('from_queue')
                and printer.get('order_id')
            ):
                _agent_debug_log(
                    'status_poller.py:sent_count_check',
                    'Evaluating Bambu sent-count increment conditions',
                    {
                        'printer': printer_name,
                        'order_id': printer.get('order_id'),
                        'current_state': current_state,
                        'new_state': new_state,
                        'start_state_match': current_state in _BAMBU_SENT_COUNT_START_STATES,
                        'count_incremented': printer.get('count_incremented_for_current_job'),
                        'job_reached_running': bambu_state.get('job_reached_running'),
                        'progress': bambu_state.get('progress'),
                        'manually_set': printer.get('manually_set'),
                    },
                    'H1',
                )
            # #endregion
            if (
                new_state == 'PRINTING'
                and current_state in _BAMBU_SENT_COUNT_START_STATES
                and printer.get('from_queue')
                and printer.get('order_id')
                and not printer.get('count_incremented_for_current_job')
            ):
                job_id = printer['order_id']
                pending_sent_increments.append((printer_name, job_id))
                # #region agent log
                _agent_debug_log(
                    'status_poller.py:sent_count_queued',
                    'Queued sent-count increment for Bambu queue job',
                    {'printer': printer_name, 'order_id': job_id},
                    'H1',
                )
                # #endregion
                filament_g = printer.get('filament_used_g', 0)
                if filament_g and printer.get('from_queue'):
                    pending_filament_g.append((printer_name, filament_g))

            # Ignore spurious FINISHED when the assigned job never started printing.
            if (
                new_state == 'FINISHED'
                and not printer.get('count_incremented_for_current_job', False)
            ):
                if current_state == 'READY' and not printer.get('order_id'):
                    if 'nozzle_temp' in bambu_state:
                        printer['nozzle_temp'] = bambu_state['nozzle_temp']
                    if 'bed_temp' in bambu_state:
                        printer['bed_temp'] = bambu_state['bed_temp']
                    continue

                logging.warning(
                    f"Bambu {printer_name}: ignoring FINISHED (job never reached RUNNING)"
                )
                # #region agent log
                _job_id = printer.get('order_id')
                _queue_job = next((j for j in ORDERS if j.get('id') == _job_id), None)
                _agent_debug_log(
                    'status_poller.py:bambu_never_running',
                    'FINISHED rejected — count_incremented still false',
                    {
                        'printer': printer_name,
                        'order_id': _job_id,
                        'sent': (_queue_job or {}).get('sent'),
                        'quantity': (_queue_job or {}).get('quantity'),
                        'current_state': current_state,
                        'new_state': new_state,
                        'count_incremented': printer.get('count_incremented_for_current_job'),
                        'job_reached_running': bambu_state.get('job_reached_running'),
                        'gcode_state': bambu_state.get('gcode_state'),
                        'progress': bambu_state.get('progress'),
                        'manually_set': printer.get('manually_set'),
                        'from_queue': printer.get('from_queue'),
                        'file': printer.get('file'),
                    },
                    'H3',
                )
                # #endregion
                clear_bambu_print_assignment(printer_name)
                if bambu_state.get('error'):
                    new_state = 'ERROR'
                else:
                    new_state = 'READY'
                if printer.get('order_id'):
                    rejection = bambu_state.get('last_print_rejection') or {}
                    err_msg = rejection.get('detail') or bambu_state.get('error')
                    if not err_msg:
                        err_msg = 'Bambu job finished without reaching RUNNING'
                    record_queue_job_error(
                        printer['order_id'],
                        err_msg,
                        printer_name=printer_name,
                        phase='bambu_never_running',
                    )
                    printer['order_id'] = None
                    printer['file'] = None
                    updates_made = True
                printer['manually_set'] = True
                printer['manual_timeout'] = time.time() + 3600

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
                    if new_state in ['PRINTING', 'PREPARING', 'EJECTING', 'PREPARE'] and printer.get('manually_set', False):
                        logging.info(f"Bambu {printer_name}: clearing manually_set flag on transition to {new_state}")
                        printer['manually_set'] = False

                    # Set finish_time when transitioning to FINISHED
                    if new_state == 'FINISHED' and current_state != 'FINISHED':
                        printer['finish_time'] = time.time()

    if updates_made:
        save_data(PRINTERS_FILE, PRINTERS)

    for printer_name, job_id in pending_sent_increments:
        success_inc, updated_job = increment_queue_sent_count(job_id)
        # #region agent log
        _agent_debug_log(
            'status_poller.py:sent_count_result',
            'Applied queued sent-count increment',
            {
                'printer': printer_name,
                'order_id': job_id,
                'success': success_inc,
                'updated_sent': (updated_job or {}).get('sent'),
            },
            'H5',
        )
        # #endregion
        if success_inc:
            clear_queue_job_error(job_id)
            try:
                with WriteLock(printers_rwlock):
                    printer = next(
                        (p for p in PRINTERS if p.get('name') == printer_name), None
                    )
                    if printer:
                        printer['count_incremented_for_current_job'] = True
                        flag_updates_need_save = True
            except TimeoutError:
                logging.error(
                    f"Could not mark count_incremented for {printer_name} after sent increment"
                )
            logging.info(
                f"Bambu {printer_name}: incremented sent for queue job "
                f"{job_id} on PRINTING"
            )

    if flag_updates_need_save:
        save_data(PRINTERS_FILE, PRINTERS)

    if pending_filament_g:
        with SafeLock(filament_lock):
            for printer_name, filament_g in pending_filament_g:
                old_total = TOTAL_FILAMENT_CONSUMPTION
                TOTAL_FILAMENT_CONSUMPTION += filament_g
                logging.info(
                    f"[FILAMENT TRACKING] Bambu {printer_name} RUNNING - "
                    f"added {filament_g}g ({old_total}g -> {TOTAL_FILAMENT_CONSUMPTION}g)"
                )
            save_data(
                TOTAL_FILAMENT_FILE,
                {"total_filament_used_g": TOTAL_FILAMENT_CONSUMPTION},
            )


def ensure_finish_times():
    """Ensure all FINISHED printers have a finish_time set"""
    need_save = False
    with WriteLock(printers_rwlock):
        for printer in PRINTERS:
            if printer.get('state') == 'FINISHED' and not printer.get('finish_time'):
                printer['finish_time'] = time.time()
                need_save = True
                logging.debug(f"Set missing finish_time for {printer.get('name')}")
    if need_save:
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
                    PRUSA_LIVE_STATUS_SEEN.add(printer['name'])
                    PRUSA_OFFLINE_POLL_FAILURES.pop(printer['name'], None)
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


def _apply_printer_updates(printer_updates):
    """Apply collected updates to PRINTERS and run manually_set failsafe.

    Must be called while holding ``WriteLock(printers_rwlock)``.
    """
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
        if printer.get('manually_set', False) and printer.get('state') not in [
            'READY', 'PRINTING', 'PAUSED', 'EJECTING', 'ERROR', 'OFFLINE',
            'PREPARING', 'PREPARE', 'COOLING', 'FINISHED',
        ]:
            logging.warning(f"Failsafe: Fixing printer {printer['name']} - has manually_set=True but state={printer['state']}. Setting back to READY")
            printer['state'] = 'READY'
            printer['status'] = 'Ready'
            printer['manually_set'] = True
            printer['count_incremented_for_current_job'] = False


def _monitor_ejection_completion(printer, printer_index, printer_updates, start_bg_dist):
    """Check if an EJECTING printer has completed and transition to READY.

    Must be called while holding ``WriteLock(printers_rwlock)``.
    *start_bg_dist* is a callable that triggers background order distribution.
    """
    printer_name = printer['name']
    printer_type = printer.get('type', 'prusa')
    current_time = time.time()
    ejection_start = printer.get('ejection_start_time', 0)
    elapsed_minutes = (current_time - ejection_start) / 60.0 if ejection_start else 0

    # Find the API state from the latest update for this printer
    api_state = None
    current_api_file = None
    for update in printer_updates:
        if update['index'] == printer_index:
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
    elif printer_type == 'bambu':
        try:
            with bambu_states_lock:
                if printer_name in BAMBU_PRINTER_STATES:
                    bambu_state = BAMBU_PRINTER_STATES[printer_name]
                    pending_m400 = bambu_state.get('ejection_m400_pending', 0)
                    waiting_m400 = bambu_state.get('waiting_for_m400', False)
                    if pending_m400 > 0 or waiting_m400:
                        ejection_complete = False
                    elif bambu_state.get('ejection_complete', False):
                        ejection_complete = True
                        completion_reason = "Bambu ejection_complete flag"
        except Exception as e:
            logging.error(f"Error checking Bambu ejection state for {printer_name}: {e}")
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

    if ejection_complete:
        logging.warning(f"EJECTION COMPLETE: {printer_name} transitioning from EJECTING to READY ({completion_reason})")

        printer.update(_ready_update(
            order_id=None, ejection_processed=False,
            manual_timeout=time.time() + 300,
            ejection_start_time=None, finish_time=None,
            last_ejection_time=time.time(),
            count_incremented_for_current_job=False,
        ))

        release_ejection_lock(printer_name)
        clear_printer_ejection_state(printer_name)
        start_bg_dist()
    else:
        if elapsed_minutes > 5:
            logging.info(f"Ejection still in progress for {printer_name}: {elapsed_minutes:.1f} minutes elapsed")


def _monitor_cooling_state(printer):
    """Check if a COOLING printer has reached target temp and transition state.

    Must be called while holding ``WriteLock(printers_rwlock)``.
    Does not call MQTT (use returned dict with action ``eject`` for that).

    Returns:
        None — still cooling
        ``{'action': 'state_only'}`` — moved to READY without ejection
        ``{'action': 'eject', 'gcode': str}`` — set EJECTING; send gcode outside the lock
    """
    if printer.get('state') != 'COOLING':
        return None

    printer_name = printer['name']
    cooldown_target = _coerce_cooldown_target(printer.get('cooldown_target_temp'))
    cooldown_order_id = printer.get('cooldown_order_id')
    current_bed_temp, _ = _sync_cooling_temps(printer)

    if cooldown_target is None:
        logging.warning(
            f"COOLING->READY: {printer_name} (missing cooldown_target_temp)"
        )
        printer.update({
            "state": 'READY', "status": 'Ready',
            "progress": 0, "time_remaining": 0,
            "manually_set": True,
            "cooldown_target_temp": None, "cooldown_order_id": None,
        })
        return {'action': 'state_only'}

    printer['status'] = f'Cooling ({current_bed_temp:.1f}°C → {cooldown_target}°C)'

    if bed_temp_needs_cooling(current_bed_temp, cooldown_target):
        finish_time = printer.get('finish_time', time.time())
        cooling_minutes = (time.time() - finish_time) / 60.0
        if int(cooling_minutes) % 2 == 0 and cooling_minutes > 0:
            logging.debug(
                f"COOLING: {printer_name} at {current_bed_temp}°C, "
                f"target {cooldown_target}°C ({cooling_minutes:.1f}min elapsed)"
            )
        return None

    logging.info(
        f"COOLING->EJECTING: {printer_name} "
        f"(bed {current_bed_temp}°C at/below target {cooldown_target}°C)"
    )

    order = _resolve_cooling_order(cooldown_order_id)

    if order and order.get('ejection_enabled', False):
        gcode_content, _ = resolve_ejection_gcode(order.get('ejection_code_id'))
        if gcode_content:
            gcode_content = gcode_content.strip()
        if not gcode_content:
            gcode_content = DEFAULT_EJECTION_GCODE

        printer.update({
            "state": 'EJECTING', "status": 'Ejecting',
            "ejection_start_time": time.time(),
            "ejection_processed": True, "ejection_in_progress": True,
            "manually_set": False,
            "cooldown_target_temp": None, "cooldown_order_id": None,
        })
        return {'action': 'eject', 'gcode': gcode_content}

    logging.warning(
        f"COOLING->READY: {printer_name} "
        f"(order {cooldown_order_id} not found or ejection not enabled)"
    )
    printer.update({
        "state": 'READY', "status": 'Ready',
        "progress": 0, "time_remaining": 0,
        "manually_set": True,
        "cooldown_target_temp": None, "cooldown_order_id": None,
    })
    return {'action': 'state_only'}


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

    with ReadLock(printers_rwlock):
        all_printers = [p.copy() for p in PRINTERS if not p.get('service_mode', False)]

    # Select the slice of printers for this batch
    if batch_index is not None:
        start_idx = batch_index * batch_size
        batch_printers = all_printers[start_idx:start_idx + batch_size]
    else:
        start_idx = 0
        batch_printers = all_printers

    printers_to_process = [_build_minimal_printer(p) for p in batch_printers]
    printer_indices = list(range(start_idx, start_idx + len(printers_to_process)))

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
                if _should_preserve_on_unreachable(printers_to_process[idx]):
                    logging.debug(
                        f"Preserving state for {printers_to_process[idx]['name']} "
                        "(fetch error before live status)"
                    )
                    continue
                printer_updates.append({
                    'index': printer_indices[idx],
                    'updates': _offline_update(),
                })
                continue

            printer, data = result
            if not data:
                if _should_preserve_on_unreachable(printer):
                    logging.debug(
                        f"Preserving state for {printer['name']} "
                        "(no API data before live status)"
                    )
                    continue
                printer_updates.append({
                    'index': printer_indices[idx],
                    'updates': _offline_update(),
                })
                continue

            if data:
                api_state = data['printer']['state']
                if api_state == 'OFFLINE' and _should_preserve_on_unreachable(printer):
                    logging.debug(
                        f"Preserving state for {printer['name']} "
                        "(OFFLINE API response before live status)"
                    )
                    continue
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
                        if manual_timeout > 0 and time.time() < manual_timeout:
                            logging.debug(f"Manual state timeout active for {printer['name']}, preserving READY state")
                        else:
                            logging.debug(f"Preserving manually set state for {printer['name']} despite API state {api_state}")
                        updates = _ready_update(
                            **_api_temps(data),
                            ejection_processed=ejection_processed,
                            count_incremented_for_current_job=printer.get('count_incremented_for_current_job', False),
                        )
                elif ejection_processed and current_state == 'READY':
                    logging.debug(f"Preserving READY state for {printer['name']} due to prior ejection, ignoring API state {api_state}")
                    updates = _ready_update(
                        **_api_temps(data),
                        order_id=None,
                        ejection_processed=True,
                        count_incremented_for_current_job=printer.get('count_incremented_for_current_job', False),
                    )
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
                                    updates.update(_ready_update(
                                        order_id=None, ejection_processed=False,
                                        ejection_start_time=None, finish_time=None,
                                        count_incremented_for_current_job=False,
                                    ))
                                    os_timer(2.0, lambda: start_background_distribution(socketio, app))
                                elif stored_state == 'EJECTING':
                                    logging.warning(f"IMPORTANT: Printer {printer['name']} completed ejection (API={api_state}), transitioning from EJECTING to READY")
                                    updates.update(_ready_update(
                                        order_id=None, ejection_processed=False,
                                        ejection_start_time=None, finish_time=None,
                                        last_ejection_time=time.time(),
                                        count_incremented_for_current_job=False,
                                    ))
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
                                        "count_incremented_for_current_job": False,
                                    })
                    elif api_state not in ['PRINTING', 'PAUSED', 'FINISHED', 'EJECTING']:
                        updates.update({
                            "progress": 0,
                            "time_remaining": 0,
                            "file": "None",
                            "job_id": None,
                            "manually_set": False,
                            "finish_time": None,
                            "ejection_in_progress": False,
                            "count_incremented_for_current_job": False,
                        })

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

    # Apply updates and handle state transitions (no disk I/O while holding write lock)
    cooling_ejections = []
    printers_need_save = bool(printer_updates)
    with WriteLock(printers_rwlock):
        _apply_printer_updates(printer_updates)

        def start_bg_dist():
            os_timer(2.0, lambda: start_background_distribution(socketio, app))

        for i, printer in enumerate(PRINTERS):
            if printer.get('state') == 'EJECTING':
                _monitor_ejection_completion(printer, i, printer_updates, start_bg_dist)
                printers_need_save = True
            elif printer.get('state') == 'COOLING':
                pending = _monitor_cooling_state(printer)
                printers_need_save = True
                if pending and pending.get('action') == 'eject':
                    cooling_ejections.append(
                        (printer['name'], pending['gcode'])
                    )
                elif pending and pending.get('action') == 'state_only':
                    pass

    if printers_need_save:
        save_data(PRINTERS_FILE, PRINTERS)

    relink_orphaned_active_prints()

    for printer_name, gcode_content in cooling_ejections:
        _complete_cooling_ejection_send(
            printer_name, gcode_content, socketio=socketio, app=app
        )

    # Load and emit current state
    current_filament = None
    with SafeLock(filament_lock):
        filament_data = load_data(TOTAL_FILAMENT_FILE, {"total_filament_used_g": 0})
        TOTAL_FILAMENT_CONSUMPTION = filament_data.get("total_filament_used_g", 0)
        current_filament = TOTAL_FILAMENT_CONSUMPTION / 1000
        logging.debug(f"Loaded filament data: total={TOTAL_FILAMENT_CONSUMPTION}g ({current_filament}kg)")

    with ReadLock(printers_rwlock):
        printers_copy = prepare_printer_data_for_broadcast(PRINTERS)

    if batch_index is not None:
        logging.debug(f"Emitting status_update with total_filament: {current_filament}kg")
        emit_status_update(socketio, app, {
            'printers': printers_copy,
            'total_filament': current_filament,
        })
