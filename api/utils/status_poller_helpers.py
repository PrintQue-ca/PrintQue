"""
Pure / near-pure helpers used by the status poller.

These functions have no side-effects on global state (or at most read
from a single global).  They are extracted here to keep status_poller.py
focused on orchestration and mutable-state management.
"""
import time
import copy

from services.state import logging
from services.bambu_handler import BAMBU_PRINTER_STATES, bambu_states_lock

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


def _build_minimal_printer(printer):
    """Build a lightweight copy of a printer dict for status polling."""
    mp = {
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
        'count_incremented_for_current_job': printer.get('count_incremented_for_current_job', False),
    }
    if printer.get('type') != 'bambu':
        mp['api_key'] = printer.get('api_key')
    else:
        mp['device_id'] = printer.get('device_id')
        mp['serial_number'] = printer.get('serial_number')
        mp['access_code'] = printer.get('access_code')
    return mp


def _offline_update():
    """Standard update dict for an unreachable / offline printer."""
    return {
        "state": "OFFLINE", "status": "Offline",
        "temps": {"nozzle": 0, "bed": 0},
        "progress": 0, "time_remaining": 0, "file": "None", "job_id": None,
        "manually_set": False, "ejection_in_progress": False,
        "finish_time": None, "count_incremented_for_current_job": False,
    }


def _ready_update(**overrides):
    """Base update dict for transitioning a printer to READY state.

    Contains only the universally-common fields.  Callers add extras
    (temps, order_id, ejection_processed, finish_time, etc.) via *overrides*.
    """
    base = {
        "state": "READY", "status": "Ready",
        "progress": 0, "time_remaining": 0,
        "file": None, "job_id": None,
        "manually_set": True,
        "ejection_in_progress": False,
    }
    base.update(overrides)
    return base


def _api_temps(data):
    """Extract temperature and z-height values from an API response."""
    return {
        "temps": {"bed": data['printer'].get('temp_bed', 0),
                  "nozzle": data['printer'].get('temp_nozzle', 0)},
        "z_height": data['printer'].get('axis_z', 0),
    }
