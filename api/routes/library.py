"""REST API routes for the print file library (catalog)."""

import csv
import io
import json
import logging
import os
import shutil
from datetime import datetime

from flask import jsonify, make_response, request, current_app
from werkzeug.utils import secure_filename

from services.default_settings import load_default_settings
from services.library_queue import (
    find_library_item,
    normalize_library_item,
    can_replace_library_file,
    update_pending_queue_snapshots_for_library,
    library_item_has_active_prints,
    apply_library_groups,
    apply_library_ejection_fields,
    parse_library_cooldown_temp,
    parse_library_id_list,
    LIBRARY_BULK_UPDATE_FIELDS,
    _next_int_id,
)
from services.printer_manager import extract_filament_from_file, extract_print_time_from_file
from services.state import (
    LIBRARY_ITEMS,
    LIBRARY_FILE,
    QUEUE_JOBS,
    QUEUE_FILE,
    PRINTERS,
    apply_ejection_fields_to_order,
    orders_lock,
    printers_rwlock,
    resolve_ejection_gcode,
    sanitize_group_name,
    save_data,
    SafeLock,
    WriteLock,
)


def _attach_ejection_name(item):
    row = item.copy()
    if row.get('ejection_code_id'):
        _, code_name = resolve_ejection_gcode(row['ejection_code_id'])
        if code_name:
            row['ejection_code_name'] = code_name
    return row


def register_library_routes(app, socketio):
    """Register /api/v1/library routes."""

    @app.route('/api/v1/library', methods=['GET'])
    def api_get_library():
        try:
            with SafeLock(orders_lock):
                items = [_attach_ejection_name(i) for i in LIBRARY_ITEMS if not i.get('deleted')]
            return jsonify(items)
        except Exception as e:
            logging.error(f"Error in api_get_library: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/library', methods=['POST'])
    def api_create_library_item():
        try:
            file = request.files.get('file')
            if not file:
                return jsonify({'error': 'No file provided'}), 400

            filename = secure_filename(file.filename)
            valid_extensions = ['.gcode', '.3mf', '.stl']
            if not any(filename.lower().endswith(ext) for ext in valid_extensions):
                return jsonify({'error': 'Invalid file type. Must be .gcode, .3mf, or .stl'}), 400

            order_name = request.form.get('name', '').strip()
            groups_raw = request.form.get('groups', '[]')
            try:
                groups = json.loads(groups_raw) if groups_raw else []
            except json.JSONDecodeError:
                groups = [groups_raw] if groups_raw else []
            groups = [sanitize_group_name(str(g)) for g in groups if g] or ['Default']

            default_settings = load_default_settings()
            ejection_enabled = request.form.get('ejection_enabled', 'false').lower() == 'true'
            end_gcode = request.form.get('end_gcode', '').strip() or None
            ejection_code_id = request.form.get('ejection_code_id', '').strip() or None

            cooldown_temp = None
            cooldown_temp_str = request.form.get('cooldown_temp', '').strip()
            if cooldown_temp_str:
                try:
                    cooldown_temp = int(cooldown_temp_str)
                    if cooldown_temp < 0 or cooldown_temp > 100:
                        cooldown_temp = None
                except ValueError:
                    cooldown_temp = None

            upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
            os.makedirs(upload_folder, exist_ok=True)
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            filament_g = extract_filament_from_file(filepath)
            estimated_print_seconds = extract_print_time_from_file(filepath)
            now = datetime.now().isoformat()

            with SafeLock(orders_lock):
                item_id = _next_int_id(LIBRARY_ITEMS)
                item = normalize_library_item({
                    'id': item_id,
                    'filename': filename,
                    'name': order_name or None,
                    'filepath': filepath,
                    'filament_g': filament_g,
                    'estimated_print_seconds': estimated_print_seconds,
                    'groups': groups,
                    'cooldown_temp': cooldown_temp,
                    'created_at': now,
                    'updated_at': now,
                })
                apply_ejection_fields_to_order(
                    item,
                    ejection_enabled=ejection_enabled,
                    ejection_code_id=ejection_code_id,
                    end_gcode=end_gcode,
                    name_hint=order_name or filename,
                    default_settings=default_settings,
                )
                LIBRARY_ITEMS.append(item)
                save_data(LIBRARY_FILE, LIBRARY_ITEMS)

            return jsonify({
                'success': True,
                'message': 'Added to library',
                'library_item_id': item_id,
            })
        except Exception as e:
            logging.error(f"Error creating library item: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/library/<int:item_id>', methods=['GET'])
    def api_get_library_item(item_id):
        try:
            with SafeLock(orders_lock):
                item = find_library_item(LIBRARY_ITEMS, item_id)
                if item:
                    return jsonify(_attach_ejection_name(item))
            return jsonify({'error': 'Library item not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/library/<int:item_id>', methods=['PATCH'])
    def api_update_library_item(item_id):
        try:
            data = request.get_json() or {}
            with SafeLock(orders_lock):
                for item in LIBRARY_ITEMS:
                    if item.get('id') != item_id or item.get('deleted'):
                        continue
                    if 'name' in data:
                        item['name'] = data['name'].strip() if data['name'] else None
                    if 'groups' in data:
                        apply_library_groups(item, data['groups'], sanitize_group_name)
                    item['updated_at'] = datetime.now().isoformat()
                    save_data(LIBRARY_FILE, LIBRARY_ITEMS)
                    return jsonify({'success': True, 'item': _attach_ejection_name(item)})
            return jsonify({'error': 'Library item not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/library/<int:item_id>/ejection', methods=['PATCH'])
    def api_update_library_ejection(item_id):
        try:
            data = request.get_json() or {}
            cooldown_provided, cooldown_value, cooldown_err = parse_library_cooldown_temp(data)
            if cooldown_err:
                return jsonify({'error': cooldown_err}), 400

            with SafeLock(orders_lock):
                for item in LIBRARY_ITEMS:
                    if item.get('id') != item_id or item.get('deleted'):
                        continue
                    apply_library_ejection_fields(
                        item,
                        data,
                        cooldown_provided=cooldown_provided,
                        cooldown_value=cooldown_value,
                    )
                    item['updated_at'] = datetime.now().isoformat()
                    save_data(LIBRARY_FILE, LIBRARY_ITEMS)
                    return jsonify({'success': True, 'item': _attach_ejection_name(item)})
            return jsonify({'error': 'Library item not found'}), 404
        except Exception as e:
            logging.error(f"Error updating library ejection: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/library/<int:item_id>', methods=['DELETE'])
    def api_delete_library_item(item_id):
        try:
            with SafeLock(orders_lock):
                for item in LIBRARY_ITEMS:
                    if item.get('id') == item_id:
                        with WriteLock(printers_rwlock):
                            if library_item_has_active_prints(item_id, QUEUE_JOBS, PRINTERS):
                                return jsonify({
                                    'error': 'Cannot delete: prints in progress for this library item',
                                }), 409
                        item['deleted'] = True
                        save_data(LIBRARY_FILE, LIBRARY_ITEMS)
                        return jsonify({'success': True})
            return jsonify({'error': 'Library item not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/library/bulk-delete', methods=['POST'])
    def api_bulk_delete_library():
        try:
            data = request.get_json() or {}
            id_set = parse_library_id_list(data.get('ids'))
            if id_set is None:
                return jsonify({'error': 'ids array is required'}), 400

            deleted_count = 0
            failures = []
            active_msg = 'Cannot delete: prints in progress for this library item'

            with SafeLock(orders_lock):
                with WriteLock(printers_rwlock):
                    for item_id in id_set:
                        item = None
                        for row in LIBRARY_ITEMS:
                            if row.get('id') == item_id:
                                item = row
                                break
                        if not item or item.get('deleted'):
                            failures.append({'id': item_id, 'error': 'Library item not found'})
                            continue
                        if library_item_has_active_prints(item_id, QUEUE_JOBS, PRINTERS):
                            failures.append({'id': item_id, 'error': active_msg})
                            continue
                        item['deleted'] = True
                        deleted_count += 1
                if deleted_count > 0:
                    save_data(LIBRARY_FILE, LIBRARY_ITEMS)

            return jsonify({
                'success': True,
                'deleted_count': deleted_count,
                'failures': failures,
            })
        except Exception as e:
            logging.error(f"Error in api_bulk_delete_library: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/library/bulk-update', methods=['POST'])
    def api_bulk_update_library():
        try:
            data = request.get_json() or {}
            id_set = parse_library_id_list(data.get('ids'))
            if id_set is None:
                return jsonify({'error': 'ids array is required'}), 400

            update_fields = {k: data[k] for k in LIBRARY_BULK_UPDATE_FIELDS if k in data}
            if not update_fields:
                return jsonify({'error': 'At least one update field is required'}), 400

            cooldown_provided, cooldown_value, cooldown_err = parse_library_cooldown_temp(data)
            if cooldown_err:
                return jsonify({'error': cooldown_err}), 400

            ejection_keys = {'ejection_enabled', 'ejection_code_id', 'end_gcode', 'cooldown_temp'}
            has_ejection_update = bool(ejection_keys & update_fields.keys())

            updated_count = 0
            failures = []

            with SafeLock(orders_lock):
                for item_id in id_set:
                    item = find_library_item(LIBRARY_ITEMS, item_id)
                    if not item:
                        failures.append({'id': item_id, 'error': 'Library item not found'})
                        continue
                    if 'groups' in update_fields:
                        apply_library_groups(
                            item, update_fields['groups'], sanitize_group_name
                        )
                    if has_ejection_update:
                        apply_library_ejection_fields(
                            item,
                            update_fields,
                            cooldown_provided=cooldown_provided,
                            cooldown_value=cooldown_value,
                        )
                    item['updated_at'] = datetime.now().isoformat()
                    updated_count += 1
                if updated_count > 0:
                    save_data(LIBRARY_FILE, LIBRARY_ITEMS)

            return jsonify({
                'success': True,
                'updated_count': updated_count,
                'failures': failures,
            })
        except Exception as e:
            logging.error(f"Error in api_bulk_update_library: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/library/<int:item_id>/file', methods=['PUT'])
    def api_replace_library_file(item_id):
        try:
            file = request.files.get('file')
            if not file:
                return jsonify({'error': 'No file provided'}), 400
            filename = secure_filename(file.filename)
            valid_extensions = ['.gcode', '.3mf', '.stl']
            if not any(filename.lower().endswith(ext) for ext in valid_extensions):
                return jsonify({'error': 'Invalid file type'}), 400

            upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
            os.makedirs(upload_folder, exist_ok=True)
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            filament_g = extract_filament_from_file(filepath)
            estimated_print_seconds = extract_print_time_from_file(filepath)

            with SafeLock(orders_lock):
                item = find_library_item(LIBRARY_ITEMS, item_id)
                if not item:
                    return jsonify({'error': 'Library item not found'}), 404
                with WriteLock(printers_rwlock):
                    if not can_replace_library_file(item_id, QUEUE_JOBS, PRINTERS):
                        return jsonify({
                            'error': 'Cannot replace file while prints are in progress for this item',
                        }), 409
                item['filename'] = filename
                item['filepath'] = filepath
                item['filament_g'] = filament_g
                item['estimated_print_seconds'] = estimated_print_seconds
                item['updated_at'] = datetime.now().isoformat()
                update_pending_queue_snapshots_for_library(item, QUEUE_JOBS)
                save_data(LIBRARY_FILE, LIBRARY_ITEMS)
                save_data(QUEUE_FILE, QUEUE_JOBS)
                return jsonify({'success': True, 'item': _attach_ejection_name(item)})
        except Exception as e:
            logging.error(f"Error replacing library file: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/library/export', methods=['GET'])
    def api_export_library():
        try:
            export_fields = [
                'id', 'filename', 'filepath', 'name', 'groups',
                'ejection_enabled', 'ejection_code_id', 'cooldown_temp', 'filament_g',
                'estimated_print_seconds',
            ]
            with SafeLock(orders_lock):
                items = []
                for i in LIBRARY_ITEMS:
                    if i.get('deleted'):
                        continue
                    row = {k: i.get(k) for k in export_fields if k in i}
                    if i.get('ejection_enabled') and i.get('ejection_code_id'):
                        gcode, code_name = resolve_ejection_gcode(i['ejection_code_id'])
                        if gcode:
                            row['end_gcode'] = gcode
                            row['ejection_code_name'] = code_name
                    items.append(row)
            body = json.dumps(items, indent=2)
            response = make_response(body)
            response.headers['Content-Type'] = 'application/json'
            response.headers['Content-Disposition'] = (
                f"attachment; filename=library_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            return response
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/library/import', methods=['POST'])
    def api_import_library():
        try:
            file = request.files.get('file')
            if not file or not file.filename:
                return jsonify({'error': 'No file provided'}), 400

            filename_lower = file.filename.lower()
            success_count = 0
            failures = []
            default_settings = load_default_settings()

            if filename_lower.endswith('.json'):
                data = json.load(file)
                if not isinstance(data, list):
                    return jsonify({'error': 'JSON must be an array'}), 400
                for idx, row in enumerate(data):
                    try:
                        filepath = row.get('filepath') or ''
                        fn = row.get('filename') or ''
                        if not filepath and fn:
                            filepath = os.path.join(
                                current_app.config.get('UPLOAD_FOLDER', 'uploads'), fn
                            )
                        if not filepath or not os.path.exists(filepath):
                            failures.append({'row': idx + 1, 'error': f'File not found: {filepath}'})
                            continue
                        groups = row.get('groups') or ['Default']
                        groups = [sanitize_group_name(str(g)) for g in groups if g] or ['Default']
                        with SafeLock(orders_lock):
                            item_id = _next_int_id(LIBRARY_ITEMS)
                            now = datetime.now().isoformat()
                            item = normalize_library_item({
                                'id': item_id,
                                'filename': fn or os.path.basename(filepath),
                                'filepath': filepath,
                                'name': row.get('name'),
                                'filament_g': row.get('filament_g', 0),
                                'estimated_print_seconds': row.get('estimated_print_seconds'),
                                'groups': groups,
                                'cooldown_temp': row.get('cooldown_temp'),
                                'created_at': now,
                                'updated_at': now,
                            })
                            apply_ejection_fields_to_order(
                                item,
                                ejection_enabled=bool(row.get('ejection_enabled', False)),
                                ejection_code_id=row.get('ejection_code_id'),
                                end_gcode=row.get('end_gcode'),
                                name_hint=fn or os.path.basename(filepath),
                                default_settings=default_settings,
                            )
                            LIBRARY_ITEMS.append(item)
                            success_count += 1
                    except Exception as e:
                        failures.append({'row': idx + 1, 'error': str(e)})
                with SafeLock(orders_lock):
                    save_data(LIBRARY_FILE, LIBRARY_ITEMS)

            elif filename_lower.endswith('.csv'):
                stream = io.StringIO(file.read().decode('utf-8', errors='replace'))
                reader = csv.DictReader(stream)
                upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
                os.makedirs(upload_folder, exist_ok=True)
                for row_index, row in enumerate(reader, start=2):
                    try:
                        row_clean = {
                            k.strip().lower().replace(' ', '_'): (v or '').strip()
                            for k, v in row.items()
                        }
                        folder_path = row_clean.get('folder_path', '')
                        fn = row_clean.get('filename', '')
                        groups_str = row_clean.get('printer_groups', 'Default')
                        groups = [
                            sanitize_group_name(g.strip())
                            for g in groups_str.split(',') if g.strip()
                        ] or ['Default']
                        if not folder_path or not fn:
                            failures.append({'row': row_index, 'error': 'Missing folder_path or filename'})
                            continue
                        full_path = os.path.normpath(os.path.join(folder_path, fn))
                        if not os.path.exists(full_path):
                            failures.append({'row': row_index, 'error': f'File not found: {full_path}'})
                            continue
                        upload_filename = secure_filename(fn)
                        upload_path = os.path.join(upload_folder, upload_filename)
                        shutil.copy2(full_path, upload_path)
                        filament_g = extract_filament_from_file(upload_path)
                        estimated_print_seconds = extract_print_time_from_file(upload_path)
                        with SafeLock(orders_lock):
                            item_id = _next_int_id(LIBRARY_ITEMS)
                            now = datetime.now().isoformat()
                            item = normalize_library_item({
                                'id': item_id,
                                'filename': upload_filename,
                                'filepath': upload_path,
                                'filament_g': filament_g,
                                'estimated_print_seconds': estimated_print_seconds,
                                'groups': groups,
                                'created_at': now,
                                'updated_at': now,
                            })
                            apply_ejection_fields_to_order(
                                item, ejection_enabled=False, default_settings=default_settings
                            )
                            LIBRARY_ITEMS.append(item)
                            success_count += 1
                    except Exception as e:
                        failures.append({'row': row_index, 'error': str(e)})
                with SafeLock(orders_lock):
                    save_data(LIBRARY_FILE, LIBRARY_ITEMS)
            else:
                return jsonify({'error': 'File must be .json or .csv'}), 400

            return jsonify({
                'success': True,
                'success_count': success_count,
                'failed_count': len(failures),
                'failures': failures,
            })
        except Exception as e:
            logging.error(f"Error in api_import_library: {e}")
            return jsonify({'error': str(e)}), 500
