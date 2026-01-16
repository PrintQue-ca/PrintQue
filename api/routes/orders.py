import os
import asyncio
from datetime import datetime
from flask import Blueprint, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
from services.state import (
    PRINTERS, TOTAL_FILAMENT_CONSUMPTION, ORDERS, 
    save_data, load_data, encrypt_api_key, decrypt_api_key, 
    logging, orders_lock, filament_lock, printers_rwlock, SafeLock, ReadLock, WriteLock, get_order_lock,
    PRINTERS_FILE, TOTAL_FILAMENT_FILE, ORDERS_FILE,
    validate_gcode_file, increment_order_sent_count, sanitize_group_name
)
from services.printer_manager import distribute_orders_async, extract_filament_from_file, start_background_distribution
from utils.config import Config
from services.default_settings import load_default_settings, save_default_settings

order_bp = Blueprint('order_routes', __name__)

def safe_int_conversion(value):
    """Safely convert a value to int, handling UUIDs and other non-numeric strings"""
    try:
        return int(value)
    except (ValueError, TypeError):
        # If it's a UUID or other non-numeric string, return a hash-based integer
        # This ensures consistent comparison while avoiding conversion errors
        return hash(str(value)) % (10**9)  # Keep it within reasonable range

def compare_order_ids(order_id1, order_id2):
    """Compare two order IDs safely, handling mixed types"""
    # Convert both to string for comparison to handle UUIDs and integers consistently
    return str(order_id1) == str(order_id2)

def register_order_routes(app, socketio):
    app.register_blueprint(order_bp)

    @app.route('/start_print', methods=['POST'])
    def start_print():
        global TOTAL_FILAMENT_CONSUMPTION, ORDERS
        
        file = request.files.get('gcode_file')
        valid, message = validate_gcode_file(file)
        if not valid:
            flash(message)
            return redirect(url_for('index'))
        
        quantity = request.form.get('quantity', type=int, default=1)
        # Updated to handle text-based groups with sanitization
        groups = [sanitize_group_name(g) for g in request.form.getlist('groups') if g.strip()]
        if not groups:
            flash("No printer groups selected")
            return redirect(url_for('index'))
            
        default_settings = load_default_settings()
        default_ejection = default_settings.get('default_ejection_enabled', False)
        
        ejection_enabled = request.form.get('ejection_enabled') == 'on'
        
        end_gcode = request.form.get('end_gcode', '').strip()
        if ejection_enabled and not end_gcode:
            end_gcode = default_settings.get('default_end_gcode', '')

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        file.save(filepath)
        filament_g = extract_filament_from_file(filepath)

        with SafeLock(orders_lock):
            # Find the highest integer ID from existing orders
            existing_int_ids = []
            for order in ORDERS:
                try:
                    # Try to convert to int - if successful, it's a numeric ID
                    int_id = int(order['id'])
                    existing_int_ids.append(int_id)
                except (ValueError, TypeError):
                    # If it fails, it's a UUID or other string - skip for max calculation
                    pass
            
            # Find next available integer ID
            order_id = max(existing_int_ids, default=0) + 1
            
            order = {
                'id': order_id,  # Always use integer for new orders
                'filename': filename,
                'filepath': filepath,
                'quantity': quantity,
                'sent': 0,
                'status': 'pending',
                'filament_g': filament_g,
                'groups': groups,  # Now contains sanitized strings instead of integers
                'ejection_enabled': ejection_enabled,
                'end_gcode': end_gcode,
                'from_new_orders': True
            }
            ORDERS.append(order)
            save_data(ORDERS_FILE, ORDERS)
            logging.debug(f"New order {order_id}: ejection_enabled={ejection_enabled}, end_gcode={end_gcode}, ORDERS IDs: {[o['id'] for o in ORDERS]}")
            logging.debug(f"New order created with filename '{filename}' and ejection_enabled={ejection_enabled}")
        
        flash(f"✅ Order for {quantity} print(s) of {filename} added successfully")
        
        start_background_distribution(socketio, app)
        
        return redirect(url_for('index'))

    @app.route('/save_default_end_gcode', methods=['POST'])
    def save_default_end_gcode():
        """Save default end G-code settings"""
        try:
            data = request.get_json()
            default_gcode = data.get('default_gcode', '').strip()
            ejection_enabled = data.get('ejection_enabled', False)
            
            # Load current settings
            current_settings = load_default_settings()
            
            # Update settings
            current_settings['default_end_gcode'] = default_gcode
            current_settings['default_ejection_enabled'] = ejection_enabled
            
            # Save settings
            success = save_default_settings(current_settings)
            
            if success:
                logging.info(f"Default settings saved: ejection_enabled={ejection_enabled}, gcode_length={len(default_gcode)}")
                return jsonify({
                    'success': True, 
                    'message': 'Default end G-code settings saved successfully!'
                })
            else:
                logging.error("Failed to save default settings")
                return jsonify({
                    'success': False, 
                    'message': 'Failed to save default settings. Please check the logs.'
                }), 500
                
        except Exception as e:
            logging.error(f"Error saving default end G-code: {str(e)}")
            return jsonify({
                'success': False, 
                'message': f'Error saving settings: {str(e)}'
            }), 500

    @app.route('/start_specific_print', methods=['POST'])
    def start_specific_print():
        order_id = request.form.get('order_id', type=int)
        printer_id = request.form.get('printer_id', type=int)
        
        # Find the order
        selected_order = None
        with SafeLock(orders_lock):
            for order in ORDERS:
                if compare_order_ids(order['id'], order_id):
                    selected_order = order.copy()
                    break
        
        if not selected_order:
            flash(f"Order {order_id} not found")
            return redirect(url_for('index'))
        
        # Find the printer
        with ReadLock(printers_rwlock):
            if 0 <= printer_id < len(PRINTERS):
                printer = PRINTERS[printer_id]
                if printer['state'] not in ['READY', 'IDLE']:
                    flash(f"⚠️ Printer {printer['name']} is not ready")
                    return redirect(url_for('index'))
            else:
                flash("Printer not found")
                return redirect(url_for('index'))
        
        # Trigger a background distribution
        start_background_distribution(socketio, app)
        
        flash(f"Print distribution started. Checking if order {order_id} can be sent to printer {printer_id}...")
        return redirect(url_for('index'))

    @app.route('/move_order_up', methods=['POST'])
    def move_order_up():
        data = request.get_json()
        order_id = data.get('order_id')
            
        with SafeLock(orders_lock):
            for i, order in enumerate(ORDERS):
                if compare_order_ids(order['id'], order_id) and i > 0:
                    ORDERS[i], ORDERS[i-1] = ORDERS[i-1], ORDERS[i]
                    save_data(ORDERS_FILE, ORDERS)
                    logging.debug(f"Moved order {order_id} up. New order: {[o['id'] for o in ORDERS]}")
                    with SafeLock(filament_lock):
                        total_filament = TOTAL_FILAMENT_CONSUMPTION / 1000
                    orders_data = ORDERS.copy()
                    with ReadLock(printers_rwlock):
                        socketio.emit('status_update', {'printers': PRINTERS, 'total_filament': total_filament, 'orders': orders_data})
                    return '', 200
            logging.error(f"Failed to move order {order_id} up: not found or already at top")
            return 'Order not found or already at top', 400

    @app.route('/move_order_down', methods=['POST'])
    def move_order_down():
        data = request.get_json()
        order_id = data.get('order_id')
            
        with SafeLock(orders_lock):
            for i, order in enumerate(ORDERS):
                if compare_order_ids(order['id'], order_id) and i < len(ORDERS) - 1:
                    ORDERS[i], ORDERS[i+1] = ORDERS[i+1], ORDERS[i]
                    save_data(ORDERS_FILE, ORDERS)
                    logging.debug(f"Moved order {order_id} down. New order: {[o['id'] for o in ORDERS]}")
                    with SafeLock(filament_lock):
                        total_filament = TOTAL_FILAMENT_CONSUMPTION / 1000
                    orders_data = ORDERS.copy()
                    with ReadLock(printers_rwlock):
                        socketio.emit('status_update', {'printers': PRINTERS, 'total_filament': total_filament, 'orders': orders_data})
                    return '', 200
            logging.error(f"Failed to move order {order_id} down: not found or already at bottom")
            return 'Order not found or already at bottom', 400

    @app.route('/delete_order/<order_id>', methods=['POST'])
    def delete_order(order_id):
        # Don't convert - work with the ID as received to handle both UUIDs and integers
        with SafeLock(get_order_lock(order_id)):
            with SafeLock(orders_lock):
                for i, order in enumerate(ORDERS):
                    # Use safe comparison function
                    if compare_order_ids(order['id'], order_id):
                        # Hard delete the order by removing it from the list
                        removed_order = ORDERS.pop(i)
                        save_data(ORDERS_FILE, ORDERS)
                        logging.debug(f"Hard deleted order {order_id}. Remaining ORDERS IDs: {[o['id'] for o in ORDERS]}")
                        
                        with SafeLock(filament_lock):
                            total_filament = TOTAL_FILAMENT_CONSUMPTION / 1000
                        orders_data = ORDERS.copy()
                        with ReadLock(printers_rwlock):
                            socketio.emit('status_update', {'printers': PRINTERS, 'total_filament': total_filament, 'orders': orders_data})
                        
                        flash(f"✅ Order {order_id} permanently deleted")
                        return redirect(url_for('index'))
                flash(f"⚠️ Order {order_id} not found")
                return redirect(url_for('index'))

    @app.route('/update_order_quantity/<order_id>', methods=['POST'])
    def update_order_quantity(order_id):
        """Update the quantity for an existing order"""
        try:
            data = request.get_json()
            new_quantity = data.get('quantity')
            
            if new_quantity is None:
                return jsonify({'success': False, 'error': 'No quantity provided'}), 400
            
            try:
                new_quantity = int(new_quantity)
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid quantity value'}), 400
            
            with SafeLock(get_order_lock(order_id)):
                with SafeLock(orders_lock):
                    # Find the order
                    order_found = False
                    for order in ORDERS:
                        if compare_order_ids(order['id'], order_id):
                            order_found = True
                            
                            # Validate new quantity
                            if new_quantity < order['sent']:
                                return jsonify({
                                    'success': False, 
                                    'error': f'Quantity cannot be less than {order["sent"]} (already sent)'
                                }), 400
                            
                            # Update the quantity
                            old_quantity = order['quantity']
                            order['quantity'] = new_quantity
                            
                            # Update status based on new quantity
                            # Use 'fulfilled' instead of 'completed' to keep it in active orders
                            if order['sent'] >= order['quantity']:
                                order['status'] = 'fulfilled'
                                if 'completed_at' not in order:
                                    order['completed_at'] = datetime.now().isoformat()
                            elif order['sent'] > 0:
                                order['status'] = 'partial'
                            else:
                                order['status'] = 'pending'
                            
                            save_data(ORDERS_FILE, ORDERS)
                            
                            # Emit update
                            with SafeLock(filament_lock):
                                total_filament = TOTAL_FILAMENT_CONSUMPTION / 1000
                            with ReadLock(printers_rwlock):
                                printers_data = PRINTERS.copy()
                            
                            socketio.emit('status_update', {
                                'printers': printers_data,
                                'total_filament': total_filament,
                                'orders': ORDERS.copy()
                            })
                            
                            return jsonify({
                                'success': True,
                                'order_id': order_id,
                                'old_quantity': old_quantity,
                                'new_quantity': new_quantity,
                                'sent': order['sent'],
                                'status': order['status']
                            })
                    
                    if not order_found:
                        return jsonify({'success': False, 'error': 'Order not found'}), 404
                        
        except Exception as e:
            logging.error(f"Error updating order quantity: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500