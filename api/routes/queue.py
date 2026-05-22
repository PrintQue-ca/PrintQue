"""REST API routes for the print queue."""

import logging

from flask import jsonify, request

from services.library_queue import (
    find_library_item,
    snapshot_queue_job_from_library,
    _next_int_id,
)
from services.printer_manager import start_background_distribution
from services.state import (
    LIBRARY_ITEMS,
    QUEUE_JOBS,
    QUEUE_FILE,
    PRINTERS,
    PRINTERS_FILE,
    apply_ejection_fields_to_order,
    auto_save_ejection_code,
    orders_lock,
    printers_rwlock,
    resolve_ejection_gcode,
    resolve_order_ejection_code_id,
    sanitize_group_name,
    save_data,
    SafeLock,
    WriteLock,
)


def _attach_ejection_name(job):
    row = job.copy()
    if row.get('ejection_code_id'):
        _, code_name = resolve_ejection_gcode(row['ejection_code_id'])
        if code_name:
            row['ejection_code_name'] = code_name
    return row


def register_queue_routes(app, socketio):
    """Register /api/v1/queue routes."""

    @app.route('/api/v1/queue', methods=['GET'])
    def api_get_queue():
        try:
            with SafeLock(orders_lock):
                jobs = [_attach_ejection_name(j) for j in QUEUE_JOBS if not j.get('deleted')]
            return jsonify(jobs)
        except Exception as e:
            logging.error(f"Error in api_get_queue: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/queue', methods=['POST'])
    def api_enqueue_job():
        """Enqueue a single job from a library item."""
        try:
            data = request.get_json() or {}
            library_item_id = data.get('library_item_id')
            quantity = int(data.get('quantity', 1))
            if quantity < 1:
                return jsonify({'error': 'quantity must be at least 1'}), 400
            if library_item_id is None:
                return jsonify({'error': 'library_item_id is required'}), 400

            groups_override = data.get('groups')
            if groups_override is not None:
                groups_override = [
                    sanitize_group_name(str(g)) for g in groups_override if g
                ] or ['Default']

            with SafeLock(orders_lock):
                item = find_library_item(LIBRARY_ITEMS, int(library_item_id))
                if not item:
                    return jsonify({'error': 'Library item not found'}), 404
                job_id = _next_int_id(QUEUE_JOBS)
                job = snapshot_queue_job_from_library(item, quantity, groups_override)
                job['id'] = job_id
                QUEUE_JOBS.append(job)
                save_data(QUEUE_FILE, QUEUE_JOBS)

            start_background_distribution(socketio, app)
            return jsonify({'success': True, 'queue_job_id': job_id})
        except Exception as e:
            logging.error(f"Error enqueueing job: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/queue/bulk', methods=['POST'])
    def api_bulk_enqueue():
        try:
            data = request.get_json() or {}
            items = data.get('items')
            if not items or not isinstance(items, list):
                return jsonify({'error': 'items array is required'}), 400

            created_ids = []
            with SafeLock(orders_lock):
                for entry in items:
                    library_item_id = entry.get('library_item_id')
                    quantity = int(entry.get('quantity', 1))
                    if quantity < 1:
                        return jsonify({'error': 'Each item quantity must be at least 1'}), 400
                    item = find_library_item(LIBRARY_ITEMS, int(library_item_id))
                    if not item:
                        return jsonify({
                            'error': f'Library item not found: {library_item_id}',
                        }), 404
                    groups_override = entry.get('groups')
                    if groups_override is not None:
                        groups_override = [
                            sanitize_group_name(str(g)) for g in groups_override if g
                        ] or ['Default']
                    job_id = _next_int_id(QUEUE_JOBS)
                    job = snapshot_queue_job_from_library(item, quantity, groups_override)
                    job['id'] = job_id
                    QUEUE_JOBS.append(job)
                    created_ids.append(job_id)
                save_data(QUEUE_FILE, QUEUE_JOBS)

            if created_ids:
                start_background_distribution(socketio, app)
            return jsonify({'success': True, 'created_ids': created_ids, 'count': len(created_ids)})
        except Exception as e:
            logging.error(f"Error in api_bulk_enqueue: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/queue/<int:job_id>', methods=['GET'])
    def api_get_queue_job(job_id):
        try:
            with SafeLock(orders_lock):
                for job in QUEUE_JOBS:
                    if job.get('id') == job_id and not job.get('deleted'):
                        return jsonify(_attach_ejection_name(job))
            return jsonify({'error': 'Queue job not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/queue/<int:job_id>', methods=['PATCH'])
    def api_update_queue_job(job_id):
        try:
            data = request.get_json() or {}
            quantity_updated = False
            with SafeLock(orders_lock):
                for job in QUEUE_JOBS:
                    if job.get('id') != job_id or job.get('deleted'):
                        continue
                    if 'quantity' in data:
                        new_qty = int(data['quantity'])
                        if new_qty < job.get('sent', 0):
                            return jsonify({
                                'error': f'Quantity cannot be less than {job["sent"]} (already sent)',
                            }), 400
                        job['quantity'] = new_qty
                        quantity_updated = True
                    if 'groups' in data:
                        job['groups'] = data['groups']
                    if 'name' in data:
                        job['name'] = data['name'].strip() if data['name'] else None
                    save_data(QUEUE_FILE, QUEUE_JOBS)
                    if quantity_updated and job.get('quantity', 0) > 0:
                        start_background_distribution(socketio, app)
                    return jsonify({'success': True})
            return jsonify({'error': 'Queue job not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/queue/<int:job_id>', methods=['DELETE'])
    def api_delete_queue_job(job_id):
        try:
            with SafeLock(orders_lock):
                for job in QUEUE_JOBS:
                    if job.get('id') == job_id:
                        job['deleted'] = True
                        save_data(QUEUE_FILE, QUEUE_JOBS)
                        return jsonify({'success': True})
            return jsonify({'error': 'Queue job not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/queue/bulk-delete', methods=['POST'])
    def api_bulk_delete_queue():
        try:
            data = request.get_json() or {}
            ids = data.get('ids')
            if not ids or not isinstance(ids, list):
                return jsonify({'error': 'ids array is required'}), 400
            id_set = {
                int(x) for x in ids
                if isinstance(x, (int, float)) and not isinstance(x, bool)
            }
            deleted_count = 0
            with SafeLock(orders_lock):
                for job in QUEUE_JOBS:
                    if job.get('id') in id_set:
                        job['deleted'] = True
                        deleted_count += 1
                if deleted_count > 0:
                    save_data(QUEUE_FILE, QUEUE_JOBS)
            return jsonify({'success': True, 'deleted_count': deleted_count})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/queue/<int:job_id>/ejection', methods=['PATCH'])
    def api_update_queue_ejection(job_id):
        try:
            data = request.get_json() or {}
            cooldown_provided = 'cooldown_temp' in data
            cooldown_value = None
            if cooldown_provided and data['cooldown_temp'] is not None:
                raw = data['cooldown_temp']
                if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                    return jsonify({'error': 'cooldown_temp must be an integer between 0 and 100, or null'}), 400
                cooldown_value = int(raw)
                if cooldown_value < 0 or cooldown_value > 100:
                    return jsonify({'error': 'cooldown_temp must be between 0 and 100'}), 400

            updated_job = None
            with SafeLock(orders_lock):
                for job in QUEUE_JOBS:
                    if job.get('id') != job_id:
                        continue
                    ejection_enabled = job.get('ejection_enabled', False)
                    if 'ejection_enabled' in data:
                        ejection_enabled = bool(data['ejection_enabled'])
                    ejection_code_id = data.get('ejection_code_id', job.get('ejection_code_id'))
                    end_gcode = data.get('end_gcode') if 'end_gcode' in data else None
                    if ejection_enabled and end_gcode is not None and str(end_gcode).strip():
                        ejection_code_id = auto_save_ejection_code(
                            str(end_gcode).strip(),
                            name_hint=job.get('filename') or job.get('name') or 'Custom',
                        )['id']
                    elif ejection_enabled and 'ejection_code_id' in data:
                        resolved = resolve_order_ejection_code_id(
                            ejection_code_id=ejection_code_id,
                            name_hint=job.get('filename') or 'Custom',
                        )
                        if resolved:
                            ejection_code_id = resolved
                    apply_ejection_fields_to_order(
                        job,
                        ejection_enabled=ejection_enabled,
                        ejection_code_id=ejection_code_id if ejection_enabled else None,
                        end_gcode=end_gcode if ejection_enabled and end_gcode else None,
                        name_hint=job.get('filename') or job.get('name') or 'Custom',
                    )
                    if cooldown_provided:
                        job['cooldown_temp'] = cooldown_value
                    save_data(QUEUE_FILE, QUEUE_JOBS)
                    updated_job = _attach_ejection_name(job)
                    break

            if updated_job is None:
                return jsonify({'error': 'Queue job not found'}), 404

            if cooldown_provided:
                with WriteLock(printers_rwlock):
                    for printer in PRINTERS:
                        if printer.get('state') == 'COOLING' and printer.get('cooldown_order_id') == job_id:
                            if cooldown_value is None:
                                printer['cooldown_target_temp'] = None
                                printer['cooldown_order_id'] = None
                            else:
                                printer['cooldown_target_temp'] = cooldown_value
                            save_data(PRINTERS_FILE, PRINTERS)

            return jsonify({'success': True, 'job': updated_job})
        except Exception as e:
            logging.error(f"Error updating queue ejection: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/queue/<int:job_id>/move', methods=['POST'])
    def api_move_queue_job(job_id):
        try:
            data = request.get_json() or {}
            direction = data.get('direction', 'up')
            with SafeLock(orders_lock):
                job_index = None
                for i, job in enumerate(QUEUE_JOBS):
                    if job.get('id') == job_id and not job.get('deleted'):
                        job_index = i
                        break
                if job_index is None:
                    return jsonify({'error': 'Queue job not found'}), 404
                if direction == 'up' and job_index > 0:
                    QUEUE_JOBS[job_index], QUEUE_JOBS[job_index - 1] = (
                        QUEUE_JOBS[job_index - 1],
                        QUEUE_JOBS[job_index],
                    )
                elif direction == 'down' and job_index < len(QUEUE_JOBS) - 1:
                    QUEUE_JOBS[job_index], QUEUE_JOBS[job_index + 1] = (
                        QUEUE_JOBS[job_index + 1],
                        QUEUE_JOBS[job_index],
                    )
                save_data(QUEUE_FILE, QUEUE_JOBS)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/queue/<int:job_id>/reorder', methods=['POST'])
    def api_reorder_queue_job(job_id):
        try:
            data = request.get_json() or {}
            new_index = data.get('new_index')
            if new_index is None:
                return jsonify({'error': 'new_index is required'}), 400

            with SafeLock(orders_lock):
                active_indices = [
                    i for i, job in enumerate(QUEUE_JOBS) if not job.get('deleted')
                ]
                current_active_index = None
                current_real_index = None
                for active_idx, real_idx in enumerate(active_indices):
                    if QUEUE_JOBS[real_idx].get('id') == job_id:
                        current_active_index = active_idx
                        current_real_index = real_idx
                        break
                if current_active_index is None:
                    return jsonify({'error': 'Queue job not found'}), 404

                new_index = max(0, min(new_index, len(active_indices) - 1))
                if current_active_index == new_index:
                    return jsonify({'success': True})

                job = QUEUE_JOBS.pop(current_real_index)
                active_indices_after = [
                    i for i, o in enumerate(QUEUE_JOBS) if not o.get('deleted')
                ]
                if new_index >= len(active_indices_after):
                    new_real_index = active_indices_after[-1] + 1 if active_indices_after else 0
                else:
                    new_real_index = active_indices_after[new_index]
                QUEUE_JOBS.insert(new_real_index, job)
                save_data(QUEUE_FILE, QUEUE_JOBS)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
