# API Routes Package
import os
import logging
import platform
import json
from flask import redirect, url_for, flash, jsonify, request, current_app
from werkzeug.utils import secure_filename
from .printers import register_printer_routes
from .orders import register_order_routes
from .system import register_misc_routes
from .support import register_support_routes
from .history import register_history_routes
from .ejection_codes import register_ejection_codes_routes
from services.state import (
    get_ejection_paused, set_ejection_paused,
    PRINTERS, ORDERS,
    printers_rwlock, orders_lock, filament_lock,
    ReadLock, WriteLock, SafeLock,
    save_data, load_data, PRINTERS_FILE, ORDERS_FILE, TOTAL_FILAMENT_FILE,
    encrypt_api_key, sanitize_group_name
)
from services.printer_manager import prepare_printer_data_for_broadcast, start_background_distribution, extract_filament_from_file
from services.default_settings import load_default_settings, save_default_settings
from utils.logger import debug_log

__all__ = [
    'register_routes',
    'register_printer_routes',
    'register_order_routes',
    'register_misc_routes',
    'register_support_routes',
    'register_history_routes',
    'register_ejection_codes_routes',
]

def register_routes(app, socketio):
    register_printer_routes(app, socketio)
    register_order_routes(app, socketio)
    register_misc_routes(app, socketio)
    register_support_routes(app, socketio)
    register_history_routes(app, socketio)
    register_ejection_codes_routes(app, socketio)

    # Ejection control routes
    @app.route('/pause_ejection', methods=['POST'])
    def pause_ejection():
        """Pause ejection globally"""
        try:
            set_ejection_paused(True)
            flash("✅ Ejection paused globally. Completed prints will remain in FINISHED state.", "success")
            return redirect(url_for('index'))
        except Exception as e:
            flash(f"❌ Error pausing ejection: {str(e)}", "error")
            return redirect(url_for('index'))

    @app.route('/resume_ejection', methods=['POST'])
    def resume_ejection():
        """Resume ejection globally"""
        try:
            set_ejection_paused(False)

            # Import here to avoid circular imports
            from services.printer_manager import trigger_mass_ejection_for_finished_printers

            # Trigger mass ejection for all waiting FINISHED printers
            ejection_count = trigger_mass_ejection_for_finished_printers(socketio, app)

            if ejection_count > 0:
                flash(f"✅ Ejection resumed globally. {ejection_count} printers now ejecting.", "success")
            else:
                flash("✅ Ejection resumed globally. No printers were waiting for ejection.", "success")

            return redirect(url_for('index'))
        except Exception as e:
            flash(f"❌ Error resuming ejection: {str(e)}", "error")
            return redirect(url_for('index'))

    @app.route('/ejection_status', methods=['GET'])
    def ejection_status():
        """Get current ejection status"""
        return jsonify({
            'paused': get_ejection_paused(),
            'status': 'paused' if get_ejection_paused() else 'active'
        })

    # API v1 routes for React frontend
    @app.route('/api/v1/ejection/status', methods=['GET'])
    def api_ejection_status():
        """API: Get current ejection status"""
        return jsonify({
            'paused': get_ejection_paused(),
            'status': 'paused' if get_ejection_paused() else 'active'
        })

    @app.route('/api/v1/ejection/pause', methods=['POST'])
    def api_pause_ejection():
        """API: Pause ejection globally"""
        try:
            set_ejection_paused(True)
            return jsonify({'success': True, 'message': 'Ejection paused globally'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/v1/ejection/resume', methods=['POST'])
    def api_resume_ejection():
        """API: Resume ejection globally"""
        try:
            set_ejection_paused(False)
            from services.printer_manager import trigger_mass_ejection_for_finished_printers
            ejection_count = trigger_mass_ejection_for_finished_printers(socketio, app)
            return jsonify({
                'success': True,
                'message': 'Ejection resumed globally',
                'printers_ejecting': ejection_count
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    # ==================== API v1 Routes for React Frontend ====================

    # System routes
    @app.route('/api/v1/system/stats', methods=['GET'])
    def api_system_stats():
        """API: Get system statistics"""
        try:
            with SafeLock(filament_lock):
                filament_data = load_data(TOTAL_FILAMENT_FILE, {"total_filament_used_g": 0})
                total_filament_kg = filament_data.get("total_filament_used_g", 0) / 1000

            with ReadLock(printers_rwlock):
                printers_count = len(PRINTERS)
                active_prints = len([p for p in PRINTERS if p['state'] == 'PRINTING'])
                idle_printers = len([p for p in PRINTERS if p['state'] == 'READY'])

            with SafeLock(orders_lock):
                # Library count: total available files (non-deleted orders)
                library_count = len([o for o in ORDERS if not o.get('deleted', False)])
                # In queue: orders actively being printed (sent > 0 but not complete)
                in_queue_count = len([
                    o for o in ORDERS
                    if not o.get('deleted', False)
                    and o.get('sent', 0) > 0
                    and o.get('sent', 0) < o.get('quantity', 1)
                ])
                # Count orders completed today
                from datetime import datetime
                today = datetime.now().date()
                completed_today = len([
                    o for o in ORDERS
                    if o.get('sent', 0) >= o.get('quantity', 1)
                    and not o.get('deleted', False)
                    and o.get('completed_at')
                    and datetime.fromisoformat(o.get('completed_at', '').replace('Z', '+00:00')).date() == today
                ])

            # Return flat structure matching frontend Stats type
            return jsonify({
                'total_filament': total_filament_kg,
                'printers_count': printers_count,
                'library_count': library_count,
                'in_queue_count': in_queue_count,
                'active_prints': active_prints,
                'idle_printers': idle_printers,
                'completed_today': completed_today
            })
        except Exception as e:
            logging.error(f"Error in api_system_stats: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/system/filament', methods=['GET'])
    def api_system_filament():
        """API: Get total filament usage"""
        try:
            with SafeLock(filament_lock):
                filament_data = load_data(TOTAL_FILAMENT_FILE, {"total_filament_used_g": 0})
                total_filament_kg = filament_data.get("total_filament_used_g", 0) / 1000
            return jsonify({'total': total_filament_kg})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/system/license', methods=['GET'])
    def api_system_license():
        """API: Get license information - Open Source Edition"""
        return jsonify({
            'tier': 'OPEN_SOURCE',
            'valid': True,
            'max_printers': -1,  # Unlimited
            'features': ['all'],
            'message': 'PrintQue Open Source Edition - All features enabled'
        })

    @app.route('/api/v1/system/info', methods=['GET'])
    def api_system_info():
        """API: Get system information"""
        try:
            import sys
            import time
            import psutil

            # Get app version from api/__version__.py (single source of truth, updated by CI)
            version = app.config.get('APP_VERSION', '0.0.0')

            # Get uptime - use process start time
            process = psutil.Process()
            uptime_seconds = time.time() - process.create_time()

            # Get memory usage percentage
            memory = psutil.virtual_memory()
            memory_usage = memory.percent

            # Get CPU usage percentage
            cpu_usage = psutil.cpu_percent(interval=0.1)

            # Get Python version
            python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

            # Get platform info
            platform_info = f"{platform.system()} {platform.release()}"

            return jsonify({
                'version': version,
                'uptime': int(uptime_seconds),
                'memory_usage': memory_usage,
                'cpu_usage': cpu_usage,
                'python_version': python_version,
                'platform': platform_info
            })
        except Exception as e:
            logging.error(f"Error in api_system_info: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/system/groups', methods=['GET'])
    def api_system_groups():
        """API: Get all printer groups"""
        try:
            with ReadLock(printers_rwlock):
                groups = list(set(str(p.get('group', 'Default')) for p in PRINTERS))
                groups.sort()
            return jsonify([{'id': i, 'name': g} for i, g in enumerate(groups)])
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/system/groups', methods=['POST'])
    def api_create_group():
        """API: Create a new group (groups are created implicitly when adding printers)"""
        try:
            data = request.get_json()
            name = sanitize_group_name(data.get('name', 'Default'))
            # Groups are implicit - just return success
            return jsonify({'success': True, 'name': name})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # Logging control routes
    @app.route('/api/v1/system/logging', methods=['GET'])
    def api_get_logging_config():
        """API: Get current logging configuration"""
        try:
            from utils.logger import get_logging_config
            return jsonify(get_logging_config())
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/system/logging/level', methods=['POST'])
    def api_set_log_level():
        """API: Set console log level"""
        try:
            from utils.logger import set_console_log_level, get_console_log_level
            data = request.get_json()
            level = data.get('level', 'INFO').upper()

            if set_console_log_level(level):
                return jsonify({
                    'success': True,
                    'message': f'Console log level set to {level}',
                    'level': get_console_log_level()
                })
            else:
                return jsonify({
                    'success': False,
                    'error': f'Invalid log level: {level}. Valid levels: DEBUG, INFO, WARNING, ERROR, CRITICAL'
                }), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/system/logging/debug-flags', methods=['GET'])
    def api_get_debug_flags():
        """API: Get current debug flags"""
        try:
            from utils.logger import get_debug_flags
            return jsonify(get_debug_flags())
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/system/logging/debug-flags', methods=['POST'])
    def api_set_debug_flag():
        """API: Set a debug flag"""
        try:
            from utils.logger import set_debug_flag, get_debug_flags
            data = request.get_json()
            flag = data.get('flag')
            enabled = data.get('enabled', False)

            if not flag:
                return jsonify({'error': 'Flag name required'}), 400

            if set_debug_flag(flag, enabled):
                return jsonify({
                    'success': True,
                    'message': f"Debug flag '{flag}' set to {enabled}",
                    'flags': get_debug_flags()
                })
            else:
                available = list(get_debug_flags().keys())
                return jsonify({
                    'success': False,
                    'error': f"Unknown debug flag: {flag}. Available: {available}"
                }), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # Log path and download for debugging (no console when running as standalone)
    @app.route('/api/v1/system/logs/path', methods=['GET'])
    def api_get_logs_path():
        """API: Get log directory and file paths for debugging"""
        try:
            log_dir = app.config.get('LOG_DIR', '')
            if not log_dir:
                log_dir = os.path.join(os.path.expanduser("~"), "PrintQueData")
            app_log = os.path.join(log_dir, 'app.log')
            logs_subdir = os.path.join(log_dir, 'logs')
            return jsonify({
                'log_dir': log_dir,
                'app_log': app_log,
                'logs_subdir': logs_subdir,
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/system/logs/download', methods=['GET'])
    def api_download_logs():
        """API: Download recent logs as a text file (last 15 minutes)"""
        try:
            import io
            from datetime import datetime
            from utils.logger import get_recent_logs

            # Include main app log (PrintQueData/app.log) + logger's recent logs (PrintQueData/logs/*)
            log_dir = app.config.get('LOG_DIR', '')
            if not log_dir:
                log_dir = os.path.join(os.path.expanduser("~"), "PrintQueData")
            app_log = os.path.join(log_dir, 'app.log')

            parts = []
            if os.path.exists(app_log):
                try:
                    with open(app_log, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                    parts.append("=== MAIN APP LOG (app.log) - last 500 lines ===\n\n")
                    parts.extend(lines[-500:] if len(lines) > 500 else lines)
                    parts.append("\n\n")
                except Exception as e:
                    parts.append(f"Error reading app.log: {e}\n\n")

            parts.append(get_recent_logs(minutes=15))

            content = ''.join(parts)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'printque_logs_{timestamp}.txt'

            from flask import send_file
            return send_file(
                io.BytesIO(content.encode('utf-8')),
                mimetype='text/plain',
                as_attachment=True,
                download_name=filename,
            )
        except Exception as e:
            logging.error(f"Error in api_download_logs: {str(e)}")
            return jsonify({'error': str(e)}), 500

    # Printer routes
    @app.route('/api/v1/printers', methods=['GET'])
    def api_get_printers():
        """API: Get all printers"""
        try:
            with ReadLock(printers_rwlock):
                printers_data = prepare_printer_data_for_broadcast(PRINTERS)
            return jsonify(printers_data)
        except Exception as e:
            logging.error(f"Error in api_get_printers: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/printers', methods=['POST'])
    def api_add_printer():
        """API: Add a new printer"""
        try:
            data = request.get_json()
            name = data.get('name')
            ip = data.get('ip')
            printer_type = data.get('type', 'prusa')
            group = sanitize_group_name(data.get('group', 'Default'))

            if not name or not ip:
                return jsonify({'error': 'Name and IP address are required'}), 400

            # Check license limits
            with ReadLock(printers_rwlock):
                current_count = len(PRINTERS)

            max_printers = app.config.get('MAX_PRINTERS', 3)
            if current_count >= max_printers:
                return jsonify({'error': f'Printer limit reached ({max_printers})'}), 403

            new_printer = {
                "name": name,
                "ip": ip,
                "type": printer_type,
                "group": group,
                "state": "OFFLINE",
                "status": "Offline",
                "temps": {"nozzle": 0, "bed": 0},
                "progress": 0,
                "time_remaining": 0,
                "z_height": 0,
                "file": None,
                "filament_used_g": 0,
                "service_mode": False,
                "last_file": None,
                "manually_set": False
            }

            if printer_type == 'prusa':
                api_key = data.get('api_key')
                if not api_key:
                    return jsonify({'error': 'API Key is required for Prusa printers'}), 400
                new_printer["api_key"] = encrypt_api_key(api_key)
            elif printer_type == 'bambu':
                device_id = data.get('device_id')
                access_code = data.get('access_code')
                if not device_id or not access_code:
                    return jsonify({'error': 'Device ID and Access Code are required for Bambu printers'}), 400
                new_printer["device_id"] = device_id
                new_printer["serial_number"] = device_id
                new_printer["access_code"] = encrypt_api_key(access_code)

            with WriteLock(printers_rwlock):
                PRINTERS.append(new_printer)
                save_data(PRINTERS_FILE, PRINTERS)

            # Try to connect Bambu printers immediately (same as form-based add)
            if printer_type == 'bambu':
                try:
                    from services.bambu_handler import connect_bambu_printer
                    if connect_bambu_printer(new_printer):
                        logging.info(f"Bambu printer {name} connected successfully")
                    else:
                        logging.warning(f"Bambu printer {name} added but MQTT connection failed. Will retry automatically.")
                except Exception as e:
                    logging.error(f"Error connecting Bambu printer {name}: {str(e)}")

            return jsonify({'success': True, 'message': f'Printer {name} added successfully'})
        except Exception as e:
            logging.error(f"Error in api_add_printer: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/printers/<printer_name>', methods=['GET'])
    def api_get_printer(printer_name):
        """API: Get a specific printer by name"""
        try:
            with ReadLock(printers_rwlock):
                for printer in PRINTERS:
                    if printer['name'] == printer_name:
                        return jsonify(prepare_printer_data_for_broadcast([printer])[0])
            return jsonify({'error': 'Printer not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/printers/<printer_name>', methods=['PATCH'])
    def api_update_printer(printer_name):
        """API: Update a printer"""
        try:
            data = request.get_json()
            with WriteLock(printers_rwlock):
                for printer in PRINTERS:
                    if printer['name'] == printer_name:
                        if 'group' in data:
                            printer['group'] = sanitize_group_name(data['group'])
                        if 'name' in data and data['name'] != printer_name:
                            printer['name'] = data['name']
                        save_data(PRINTERS_FILE, PRINTERS)
                        return jsonify({'success': True})
            return jsonify({'error': 'Printer not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/printers/<printer_name>', methods=['DELETE'])
    def api_delete_printer(printer_name):
        """API: Delete a printer"""
        try:
            with WriteLock(printers_rwlock):
                for i, printer in enumerate(PRINTERS):
                    if printer['name'] == printer_name:
                        PRINTERS.pop(i)
                        save_data(PRINTERS_FILE, PRINTERS)
                        return jsonify({'success': True, 'message': f'Printer {printer_name} deleted'})
            return jsonify({'error': 'Printer not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/printers/<printer_name>/ready', methods=['POST'])
    def api_mark_printer_ready(printer_name):
        """API: Mark a printer as ready"""
        try:
            with WriteLock(printers_rwlock):
                for printer in PRINTERS:
                    if printer['name'] == printer_name:
                        if printer['state'] in ['FINISHED', 'EJECTING', 'COOLING']:
                            printer['state'] = 'READY'
                            printer['status'] = 'Ready'
                            printer['manually_set'] = True
                            printer['progress'] = 0
                            printer['time_remaining'] = 0
                            printer['file'] = None
                            printer['job_id'] = None
                            printer['order_id'] = None
                            # Clear cooldown state if skipping cooldown
                            printer['cooldown_target_temp'] = None
                            printer['cooldown_order_id'] = None
                            save_data(PRINTERS_FILE, PRINTERS)
                            start_background_distribution(socketio, app)
                            return jsonify({'success': True})
                        else:
                            return jsonify({'error': 'Printer is not in FINISHED, EJECTING, or COOLING state'}), 400
            return jsonify({'error': 'Printer not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/printers/<printer_name>/stop', methods=['POST'])
    def api_stop_printer(printer_name):
        """API: Stop a print on a printer"""
        # This would need async implementation - for now return a simple response
        return jsonify({'success': True, 'message': 'Stop command sent'})

    @app.route('/api/v1/printers/<printer_name>/pause', methods=['POST'])
    def api_pause_printer(printer_name):
        """API: Pause a print on a printer"""
        return jsonify({'success': True, 'message': 'Pause command sent'})

    @app.route('/api/v1/printers/<printer_name>/resume', methods=['POST'])
    def api_resume_printer(printer_name):
        """API: Resume a print on a printer"""
        return jsonify({'success': True, 'message': 'Resume command sent'})

    # Order routes
    @app.route('/api/v1/orders', methods=['GET'])
    def api_get_orders():
        """API: Get all orders"""
        try:
            with SafeLock(orders_lock):
                orders_data = [o for o in ORDERS if not o.get('deleted', False)]
            return jsonify(orders_data)
        except Exception as e:
            logging.error(f"Error in api_get_orders: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/orders', methods=['POST'])
    def api_create_order():
        """API: Create a new order"""
        try:
            file = request.files.get('file')
            if not file:
                return jsonify({'error': 'No file provided'}), 400

            # Validate file type
            filename = secure_filename(file.filename)
            valid_extensions = ['.gcode', '.3mf', '.stl']
            if not any(filename.lower().endswith(ext) for ext in valid_extensions):
                return jsonify({'error': 'Invalid file type. Must be .gcode, .3mf, or .stl'}), 400

            quantity = int(request.form.get('quantity', 0))

            # Handle optional order name
            order_name = request.form.get('name', '').strip()

            # Handle groups - can be JSON string or list
            groups_raw = request.form.get('groups', '[]')
            try:
                groups = json.loads(groups_raw) if groups_raw else []
            except json.JSONDecodeError:
                groups = [groups_raw] if groups_raw else []

            # Sanitize group names
            groups = [sanitize_group_name(str(g)) for g in groups if g]
            if not groups:
                groups = ['Default']

            # Load default settings
            default_settings = load_default_settings()

            # Handle ejection settings
            ejection_enabled = request.form.get('ejection_enabled', 'false').lower() == 'true'
            end_gcode = request.form.get('end_gcode', '').strip()
            ejection_code_id = request.form.get('ejection_code_id', '').strip() or None
            ejection_code_name = request.form.get('ejection_code_name', '').strip() or None

            # Handle cooldown temperature (Bambu printers only)
            cooldown_temp_str = request.form.get('cooldown_temp', '').strip()
            cooldown_temp = None
            if cooldown_temp_str:
                try:
                    cooldown_temp = int(cooldown_temp_str)
                    if cooldown_temp < 0 or cooldown_temp > 100:
                        debug_log('cooldown', f"cooldown_temp {cooldown_temp} out of range, ignoring", 'warning')
                        cooldown_temp = None  # Invalid range
                    else:
                        debug_log('cooldown', f"Parsed cooldown_temp as {cooldown_temp}°C")
                except ValueError:
                    debug_log('cooldown', f"Could not parse cooldown_temp '{cooldown_temp_str}'", 'warning')
                    cooldown_temp = None  # Invalid value

            # Use default if ejection enabled but no custom gcode provided
            if ejection_enabled and not end_gcode:
                end_gcode = default_settings.get('default_end_gcode', '')

            # Save file
            upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
            os.makedirs(upload_folder, exist_ok=True)
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)

            # Extract filament usage
            filament_g = extract_filament_from_file(filepath)

            with SafeLock(orders_lock):
                # Find next available ID
                existing_int_ids = []
                for order in ORDERS:
                    try:
                        int_id = int(order['id'])
                        existing_int_ids.append(int_id)
                    except (ValueError, TypeError):
                        pass

                order_id = max(existing_int_ids, default=0) + 1

                order = {
                    'id': order_id,
                    'filename': filename,
                    'name': order_name if order_name else None,
                    'filepath': filepath,
                    'quantity': quantity,
                    'sent': 0,
                    'status': 'pending',
                    'filament_g': filament_g,
                    'groups': groups,
                    'ejection_enabled': ejection_enabled,
                    'ejection_code_id': ejection_code_id,
                    'ejection_code_name': ejection_code_name,
                    'end_gcode': end_gcode,
                    'cooldown_temp': cooldown_temp,  # Bed temp to wait for before ejection (Bambu only)
                    'from_new_orders': True
                }
                ORDERS.append(order)
                save_data(ORDERS_FILE, ORDERS)
                logging.info(f"Created order {order_id}: {order_name or filename}, qty={quantity}")
                debug_log('cooldown', f"Order {order_id} created with cooldown_temp={cooldown_temp}")

            # Trigger distribution
            start_background_distribution(socketio, app)

            message = (
                'Order added to library (set quantity to start printing)' if quantity == 0
                else f'Order created for {quantity} print(s) of {filename}'
            )
            return jsonify({
                'success': True,
                'message': message,
                'order_id': order_id
            })

        except Exception as e:
            logging.error(f"Error creating order via API: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/orders/<int:order_id>', methods=['GET'])
    def api_get_order(order_id):
        """API: Get a specific order"""
        try:
            with SafeLock(orders_lock):
                for order in ORDERS:
                    if order.get('id') == order_id and not order.get('deleted', False):
                        return jsonify(order)
            return jsonify({'error': 'Order not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/orders/<int:order_id>', methods=['PATCH'])
    def api_update_order(order_id):
        """API: Update an order"""
        try:
            data = request.get_json()
            quantity_updated = False
            with SafeLock(orders_lock):
                for order in ORDERS:
                    if order.get('id') == order_id:
                        if 'quantity' in data:
                            order['quantity'] = int(data['quantity'])
                            quantity_updated = True
                        if 'groups' in data:
                            order['groups'] = data['groups']
                        if 'name' in data:
                            order['name'] = data['name'].strip() if data['name'] else None
                        save_data(ORDERS_FILE, ORDERS)
                        if quantity_updated and order.get('quantity', 0) > 0:
                            start_background_distribution(socketio, app)
                        return jsonify({'success': True})
            return jsonify({'error': 'Order not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/orders/<int:order_id>', methods=['DELETE'])
    def api_delete_order(order_id):
        """API: Delete an order"""
        try:
            with SafeLock(orders_lock):
                for order in ORDERS:
                    if order.get('id') == order_id:
                        order['deleted'] = True
                        save_data(ORDERS_FILE, ORDERS)
                        return jsonify({'success': True, 'message': 'Order deleted'})
            return jsonify({'error': 'Order not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/orders/<int:order_id>/ejection', methods=['PATCH'])
    def api_update_order_ejection(order_id):
        """API: Update order ejection settings"""
        try:
            data = request.get_json()
            with SafeLock(orders_lock):
                for order in ORDERS:
                    if order.get('id') == order_id:
                        if 'ejection_enabled' in data:
                            order['ejection_enabled'] = bool(data['ejection_enabled'])
                        if 'ejection_code_id' in data:
                            order['ejection_code_id'] = data['ejection_code_id']
                        if 'ejection_code_name' in data:
                            order['ejection_code_name'] = data['ejection_code_name']
                        if 'end_gcode' in data:
                            order['end_gcode'] = data['end_gcode']
                        save_data(ORDERS_FILE, ORDERS)
                        logging.info(f"Updated ejection settings for order {order_id}: enabled={order.get('ejection_enabled')}, code={order.get('ejection_code_name')}")
                        return jsonify({'success': True, 'order': order})
            return jsonify({'error': 'Order not found'}), 404
        except Exception as e:
            logging.error(f"Error updating order ejection: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/orders/<int:order_id>/move', methods=['POST'])
    def api_move_order(order_id):
        """API: Move an order up or down in priority"""
        try:
            data = request.get_json()
            direction = data.get('direction', 'up')

            with SafeLock(orders_lock):
                # Find the order index
                order_index = None
                for i, order in enumerate(ORDERS):
                    if order.get('id') == order_id and not order.get('deleted', False):
                        order_index = i
                        break

                if order_index is None:
                    return jsonify({'error': 'Order not found'}), 404

                if direction == 'up' and order_index > 0:
                    ORDERS[order_index], ORDERS[order_index - 1] = ORDERS[order_index - 1], ORDERS[order_index]
                elif direction == 'down' and order_index < len(ORDERS) - 1:
                    ORDERS[order_index], ORDERS[order_index + 1] = ORDERS[order_index + 1], ORDERS[order_index]

                save_data(ORDERS_FILE, ORDERS)

            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/orders/<int:order_id>/reorder', methods=['POST'])
    def api_reorder_order(order_id):
        """API: Move an order to a specific position (for drag and drop)"""
        try:
            data = request.get_json()
            new_index = data.get('new_index')

            if new_index is None:
                return jsonify({'error': 'new_index is required'}), 400

            with SafeLock(orders_lock):
                # Filter to only non-deleted orders for reordering
                active_indices = [i for i, order in enumerate(ORDERS) if not order.get('deleted', False)]

                # Find the order's current index in active orders
                current_active_index = None
                current_real_index = None
                for active_idx, real_idx in enumerate(active_indices):
                    if ORDERS[real_idx].get('id') == order_id:
                        current_active_index = active_idx
                        current_real_index = real_idx
                        break

                if current_active_index is None:
                    return jsonify({'error': 'Order not found'}), 404

                # Clamp new_index to valid range
                new_index = max(0, min(new_index, len(active_indices) - 1))

                if current_active_index == new_index:
                    return jsonify({'success': True})  # No change needed

                # Remove the order from its current position
                order = ORDERS.pop(current_real_index)

                # Calculate the new real index
                # Re-calculate active indices after removal
                active_indices_after = [i for i, o in enumerate(ORDERS) if not o.get('deleted', False)]

                if new_index >= len(active_indices_after):
                    # Insert at the end (after the last active order)
                    if active_indices_after:
                        new_real_index = active_indices_after[-1] + 1
                    else:
                        new_real_index = 0
                else:
                    new_real_index = active_indices_after[new_index]

                ORDERS.insert(new_real_index, order)
                save_data(ORDERS_FILE, ORDERS)

            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # Default ejection settings routes
    @app.route('/api/v1/settings/default-ejection', methods=['GET'])
    def api_get_default_ejection():
        """API: Get default ejection settings"""
        try:
            settings = load_default_settings()
            return jsonify({
                'ejection_enabled': settings.get('default_ejection_enabled', False),
                'end_gcode': settings.get('default_end_gcode', '')
            })
        except Exception as e:
            logging.error(f"Error getting default ejection settings: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/settings/default-ejection', methods=['POST'])
    def api_save_default_ejection():
        """API: Save default ejection settings"""
        try:
            data = request.get_json()

            # Load current settings
            current_settings = load_default_settings()

            # Update settings
            if 'ejection_enabled' in data:
                current_settings['default_ejection_enabled'] = bool(data['ejection_enabled'])
            if 'end_gcode' in data:
                current_settings['default_end_gcode'] = data['end_gcode'].strip()

            # Save settings
            success = save_default_settings(current_settings)

            if success:
                logging.info(f"API: Saved default ejection settings: enabled={current_settings.get('default_ejection_enabled')}")
                return jsonify({
                    'success': True,
                    'message': 'Default ejection settings saved'
                })
            else:
                return jsonify({'error': 'Failed to save settings'}), 500

        except Exception as e:
            logging.error(f"Error saving default ejection settings: {str(e)}")
            return jsonify({'error': str(e)}), 500
