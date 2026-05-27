"""Library catalog and print queue helpers."""

import logging
from datetime import datetime

MAX_QUEUE_JOB_ERROR_EVENTS = 10



def _next_int_id(items):
    ids = []
    for item in items:
        try:
            ids.append(int(item['id']))
        except (ValueError, TypeError, KeyError):
            pass
    return max(ids, default=0) + 1


def normalize_groups(groups):
    if not groups:
        return ['Default']
    processed = []
    for g in groups:
        try:
            processed.append(int(g))
        except (ValueError, TypeError):
            processed.append(g)
    return processed or ['Default']


def normalize_library_item(item):
    item.setdefault('deleted', False)
    item.setdefault('filament_g', 0)
    item.setdefault('estimated_print_seconds', None)
    item.setdefault('groups', ['Default'])
    item['groups'] = normalize_groups(item.get('groups'))
    item.setdefault('ejection_enabled', False)
    item.setdefault('created_at', datetime.now().isoformat())
    item.setdefault('updated_at', item['created_at'])
    return item


def normalize_queue_job(job):
    job.setdefault('deleted', False)
    job.setdefault('paused', False)
    job.setdefault('sent', 0)
    job.setdefault('status', 'pending')
    job.setdefault('filament_g', 0)
    job.setdefault('estimated_print_seconds', None)
    job.setdefault('groups', ['Default'])
    job['groups'] = normalize_groups(job.get('groups'))
    job.setdefault('ejection_enabled', False)
    job.setdefault('library_item_id', None)
    job.setdefault('created_at', datetime.now().isoformat())
    job.setdefault('last_error', None)
    job.setdefault('last_error_at', None)
    job.setdefault('last_error_printer', None)
    job.setdefault('last_error_phase', None)
    job.setdefault('error_events', [])
    return job


def record_queue_job_error(
    job_id,
    message,
    *,
    printer_name=None,
    phase=None,
    batch_id=None,
    task_id=None,
):
    """Persist a start/distribution failure on the queue job and log lifecycle."""
    from services.state import QUEUE_JOBS, QUEUE_FILE, orders_lock, save_data, SafeLock
    from utils.logger import log_job_lifecycle

    now = datetime.now().isoformat()
    event = {
        'at': now,
        'message': message,
    }
    if printer_name:
        event['printer'] = printer_name
    if phase:
        event['phase'] = phase
    if batch_id:
        event['batch_id'] = batch_id
    if task_id:
        event['task_id'] = task_id

    updated = False
    filename = None
    with SafeLock(orders_lock):
        for job in QUEUE_JOBS:
            if job.get('id') != job_id or job.get('deleted'):
                continue
            job['last_error'] = message
            job['last_error_at'] = now
            job['last_error_printer'] = printer_name
            job['last_error_phase'] = phase
            events = list(job.get('error_events') or [])
            events.append(event)
            job['error_events'] = events[-MAX_QUEUE_JOB_ERROR_EVENTS:]
            filename = job.get('filename')
            updated = True
            break
        if updated:
            save_data(QUEUE_FILE, QUEUE_JOBS)

    if not updated:
        logging.warning(f"record_queue_job_error: queue job {job_id} not found")
        return False

    log_job_lifecycle(
        job_id,
        printer_name or '',
        'JOB_START_FAILED',
        {
            'message': message,
            'phase': phase,
            'batch_id': batch_id,
            'task_id': task_id,
            'filename': filename,
        },
    )
    logging.error(
        f"Queue job {job_id} start failed"
        f"{f' on {printer_name}' if printer_name else ''}"
        f"{f' ({phase})' if phase else ''}: {message}"
    )
    return True


def clear_queue_job_error(job_id):
    """Clear last_error fields after a copy successfully starts."""
    from services.state import QUEUE_JOBS, QUEUE_FILE, orders_lock, save_data, SafeLock

    updated = False
    with SafeLock(orders_lock):
        for job in QUEUE_JOBS:
            if job.get('id') != job_id or job.get('deleted'):
                continue
            if not job.get('last_error'):
                return False
            job['last_error'] = None
            job['last_error_at'] = None
            job['last_error_printer'] = None
            job['last_error_phase'] = None
            updated = True
            break
        if updated:
            save_data(QUEUE_FILE, QUEUE_JOBS)
    return updated


def library_item_from_order(order, library_id):
    now = datetime.now().isoformat()
    return normalize_library_item({
        'id': library_id,
        'filename': order.get('filename', ''),
        'filepath': order.get('filepath', ''),
        'name': order.get('name'),
        'groups': order.get('groups', ['Default']),
        'filament_g': order.get('filament_g', 0),
        'estimated_print_seconds': order.get('estimated_print_seconds'),
        'ejection_enabled': order.get('ejection_enabled', False),
        'ejection_code_id': order.get('ejection_code_id'),
        'cooldown_temp': order.get('cooldown_temp'),
        'created_at': order.get('created_at', now),
        'updated_at': now,
        'deleted': False,
    })


def queue_job_from_order(order, library_item_id):
    return normalize_queue_job({
        'id': order['id'],
        'library_item_id': library_item_id,
        'filename': order.get('filename', ''),
        'filepath': order.get('filepath', ''),
        'name': order.get('name'),
        'quantity': order.get('quantity', 0),
        'sent': order.get('sent', 0),
        'status': order.get('status', 'pending'),
        'groups': order.get('groups', ['Default']),
        'filament_g': order.get('filament_g', 0),
        'estimated_print_seconds': order.get('estimated_print_seconds'),
        'ejection_enabled': order.get('ejection_enabled', False),
        'ejection_code_id': order.get('ejection_code_id'),
        'cooldown_temp': order.get('cooldown_temp'),
        'created_at': order.get('created_at', datetime.now().isoformat()),
        'deleted': order.get('deleted', False),
    })


def snapshot_queue_job_from_library(library_item, quantity, groups_override=None):
    groups = groups_override if groups_override is not None else library_item.get('groups', ['Default'])
    return normalize_queue_job({
        'library_item_id': library_item['id'],
        'filename': library_item['filename'],
        'filepath': library_item['filepath'],
        'name': library_item.get('name'),
        'quantity': quantity,
        'sent': 0,
        'status': 'pending',
        'groups': groups,
        'filament_g': library_item.get('filament_g', 0),
        'estimated_print_seconds': library_item.get('estimated_print_seconds'),
        'ejection_enabled': library_item.get('ejection_enabled', False),
        'ejection_code_id': library_item.get('ejection_code_id'),
        'cooldown_temp': library_item.get('cooldown_temp'),
        'created_at': datetime.now().isoformat(),
        'deleted': False,
    })


def migrate_orders_to_library_and_queue(orders, library_items, queue_jobs, backup_fn):
    """Migrate legacy orders.json into library + queue lists."""
    if backup_fn:
        backup_fn('orders.json', 'library.json', 'queue.json')

    filepath_to_library_id = {}
    next_library_id = 1
    next_queue_id = 1

    for order in orders:
        if order.get('deleted'):
            continue

        filepath = order.get('filepath') or ''
        if filepath and filepath not in filepath_to_library_id:
            lib_id = next_library_id
            next_library_id += 1
            library_items.append(library_item_from_order(order, lib_id))
            filepath_to_library_id[filepath] = lib_id
        elif filepath:
            lib_id = filepath_to_library_id[filepath]
        else:
            lib_id = None
            lib_id_val = next_library_id
            next_library_id += 1
            library_items.append(library_item_from_order(order, lib_id_val))
            lib_id = lib_id_val

        quantity = int(order.get('quantity', 0))
        sent = int(order.get('sent', 0))
        if quantity > 0 or sent > 0:
            try:
                queue_id = int(order['id'])
            except (ValueError, TypeError, KeyError):
                queue_id = next_queue_id
                next_queue_id += 1
            else:
                next_queue_id = max(next_queue_id, queue_id + 1)

            job = queue_job_from_order(order, lib_id)
            job['id'] = queue_id
            queue_jobs.append(job)

    return library_items, queue_jobs


def find_library_item(library_items, item_id):
    for item in library_items:
        if item.get('id') == item_id and not item.get('deleted'):
            return item
    return None


def parse_library_cooldown_temp(data):
    """Return (cooldown_provided, cooldown_value, error_message)."""
    if 'cooldown_temp' not in data:
        return False, None, None
    if data['cooldown_temp'] is None:
        return True, None, None
    raw = data['cooldown_temp']
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return True, None, 'cooldown_temp must be an integer between 0 and 100, or null'
    cooldown_value = int(raw)
    if cooldown_value < 0 or cooldown_value > 100:
        return True, None, 'cooldown_temp must be between 0 and 100'
    return True, cooldown_value, None


def apply_library_groups(item, groups, sanitize_fn):
    item['groups'] = [sanitize_fn(str(g)) for g in groups if g] or ['Default']


def apply_library_ejection_fields(item, data, *, cooldown_provided=False, cooldown_value=None):
    from services.state import (
        apply_ejection_fields_to_order,
        auto_save_ejection_code,
        resolve_order_ejection_code_id,
    )

    ejection_enabled = item.get('ejection_enabled', False)
    if 'ejection_enabled' in data:
        ejection_enabled = bool(data['ejection_enabled'])
    ejection_code_id = data.get('ejection_code_id', item.get('ejection_code_id'))
    end_gcode = data.get('end_gcode') if 'end_gcode' in data else None
    if ejection_enabled and end_gcode is not None and str(end_gcode).strip():
        ejection_code_id = auto_save_ejection_code(
            str(end_gcode).strip(),
            name_hint=item.get('filename') or item.get('name') or 'Custom',
        )['id']
    elif ejection_enabled and 'ejection_code_id' in data:
        resolved = resolve_order_ejection_code_id(
            ejection_code_id=ejection_code_id,
            name_hint=item.get('filename') or 'Custom',
        )
        if resolved:
            ejection_code_id = resolved
    apply_ejection_fields_to_order(
        item,
        ejection_enabled=ejection_enabled,
        ejection_code_id=ejection_code_id if ejection_enabled else None,
        end_gcode=end_gcode if ejection_enabled and end_gcode else None,
        name_hint=item.get('filename') or item.get('name') or 'Custom',
    )
    if cooldown_provided:
        item['cooldown_temp'] = cooldown_value


LIBRARY_BULK_UPDATE_FIELDS = frozenset({
    'groups',
    'ejection_enabled',
    'ejection_code_id',
    'end_gcode',
    'cooldown_temp',
})


def parse_library_id_list(ids):
    if not ids or not isinstance(ids, list):
        return None
    return {
        int(x) for x in ids
        if isinstance(x, (int, float)) and not isinstance(x, bool)
    }


_PRINTER_ACTIVE_STATES = frozenset({'PRINTING', 'COOLING', 'EJECTING'})


def library_item_has_active_prints(library_id, queue_jobs, printers):
    for job in queue_jobs:
        if job.get('deleted'):
            continue
        if job.get('library_item_id') != library_id:
            continue
        sent = int(job.get('sent', 0) or 0)
        quantity = int(job.get('quantity', 1) or 1)
        if sent > 0 and sent < quantity:
            return True
        job_id = job.get('id')
        for printer in printers:
            if printer.get('order_id') == job_id:
                state = printer.get('state', '')
                if state in _PRINTER_ACTIVE_STATES:
                    return True
    return False


def can_replace_library_file(library_id, queue_jobs, printers):
    return not library_item_has_active_prints(library_id, queue_jobs, printers)


def update_pending_queue_snapshots_for_library(library_item, queue_jobs):
    """Refresh file metadata for queue jobs with sent==0 linked to this library item."""
    for job in queue_jobs:
        if job.get('deleted'):
            continue
        if job.get('library_item_id') != library_item['id']:
            continue
        if job.get('sent', 0) != 0:
            continue
        job['filepath'] = library_item['filepath']
        job['filename'] = library_item['filename']
        job['filament_g'] = library_item.get('filament_g', 0)
        job['estimated_print_seconds'] = library_item.get('estimated_print_seconds')
