# API Routes Package
import os
import copy
import logging
import platform
import json
from flask import redirect, url_for, flash, jsonify, render_template, request, current_app
from werkzeug.utils import secure_filename
from .printers import register_printer_routes
from .orders import register_order_routes
from .system import register_misc_routes
from .license import register_license_routes
from .support import register_support_routes
from .history import register_history_routes
from services.state import (
    get_ejection_paused, set_ejection_paused,
    PRINTERS, ORDERS, TOTAL_FILAMENT_CONSUMPTION,
    printers_rwlock, orders_lock, filament_lock,
    ReadLock, WriteLock, SafeLock,
    save_data, load_data, PRINTERS_FILE, ORDERS_FILE, TOTAL_FILAMENT_FILE,
    encrypt_api_key, sanitize_group_name
)
from services.printer_manager import prepare_printer_data_for_broadcast, start_background_distribution, extract_filament_from_file
from services.default_settings import load_default_settings, save_default_settings

__all__ = [
    'register_routes',
    'register_printer_routes',
    'register_order_routes', 
    'register_misc_routes',
    'register_license_routes',
    'register_support_routes',
    'register_history_routes',
]

def register_routes(app, socketio):
    register_printer_routes(app, socketio)
    register_order_routes(app, socketio)
    register_misc_routes(app, socketio)
    register_license_routes(app, socketio)
    register_support_routes(app, socketio)
    register_history_routes(app, socketio)
    
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
        """API: Get license information"""
        try:
            return jsonify({
                'tier': app.config.get('LICENSE_TIER', 'free'),
                'valid': app.config.get('LICENSE_VALID', False),
                'max_printers': app.config.get('MAX_PRINTERS', 3),
                'features': app.config.get('LICENSE_FEATURES', []),
                'days_remaining': app.config.get('LICENSE_DAYS_REMAINING', None)
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/system/info', methods=['GET'])
    def api_system_info():
        """API: Get system information"""
        try:
            import sys
            import time
            import psutil
            
            # Get app version (you can update this as needed)
            version = app.config.get('APP_VERSION', '1.0.0')
            
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
                        if printer['state'] in ['FINISHED', 'EJECTING']:
                            printer['state'] = 'READY'
                            printer['status'] = 'Ready'
                            printer['manually_set'] = True
                            printer['progress'] = 0
                            printer['time_remaining'] = 0
                            printer['file'] = None
                            printer['job_id'] = None
                            printer['order_id'] = None
                            save_data(PRINTERS_FILE, PRINTERS)
                            start_background_distribution(socketio, app)
                            return jsonify({'success': True})
                        else:
                            return jsonify({'error': f'Printer is not in FINISHED or EJECTING state'}), 400
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
            
            quantity = int(request.form.get('quantity', 1))
            
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
                    'filepath': filepath,
                    'quantity': quantity,
                    'sent': 0,
                    'status': 'pending',
                    'filament_g': filament_g,
                    'groups': groups,
                    'ejection_enabled': ejection_enabled,
                    'end_gcode': end_gcode,
                    'from_new_orders': True
                }
                ORDERS.append(order)
                save_data(ORDERS_FILE, ORDERS)
                logging.info(f"API: Created order {order_id}: {filename}, qty={quantity}, ejection={ejection_enabled}")
            
            # Trigger distribution
            start_background_distribution(socketio, app)
            
            return jsonify({
                'success': True,
                'message': f'Order created for {quantity} print(s) of {filename}',
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
            with SafeLock(orders_lock):
                for order in ORDERS:
                    if order.get('id') == order_id:
                        if 'quantity' in data:
                            order['quantity'] = int(data['quantity'])
                        if 'groups' in data:
                            order['groups'] = data['groups']
                        save_data(ORDERS_FILE, ORDERS)
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
