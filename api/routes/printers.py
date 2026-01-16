import os
import asyncio
import aiohttp
import time
import uuid
import threading
from flask import Blueprint, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
from services.state import (
    PRINTERS, TOTAL_FILAMENT_CONSUMPTION, ORDERS, 
    save_data, load_data, encrypt_api_key, decrypt_api_key, 
    logging, orders_lock, filament_lock, printers_rwlock, SafeLock, ReadLock, WriteLock,
    PRINTERS_FILE, TOTAL_FILAMENT_FILE, validate_gcode_file,
    register_task, update_task_progress, complete_task,
    sanitize_group_name
)
from services.printer_manager import distribute_orders_async, extract_filament_from_file, start_background_distribution, send_print_to_printer, prepare_printer_data_for_broadcast
from utils.config import Config
from utils.retry_utils import retry_async
import copy
# Bambu printer support
from services.bambu_handler import (
    pause_bambu_print, resume_bambu_print, stop_bambu_print, connect_bambu_printer,
    send_bambu_print_command
)

printer_bp = Blueprint('printer_routes', __name__)

# Global variables to store app and socketio references
_app = None
_socketio = None

def get_app():
    """Get the Flask app instance"""
    return _app

def get_socketio():
    """Get the SocketIO instance"""
    return _socketio

async def fetch_printer_status(session, printer):
    # Skip Bambu printers - they use MQTT status updates
    if printer.get('type') == 'bambu':
        return
    
    try:
        headers = {"X-Api-Key": decrypt_api_key(printer["api_key"])}
        async with session.get(f"http://{printer['ip']}/api/v1/status", headers=headers, timeout=5) as response:
            if response.status == 200:
                data = await response.json()
                with WriteLock(printers_rwlock):
                    printer["state"] = data["printer"]["state"]
                    printer["status"] = data["printer"]["state"] if "printer" in data else "Idle"
                    printer["temps"] = {
                        "nozzle": data["printer"].get("temp_nozzle", 0),
                        "bed": data["printer"].get("temp_bed", 0)
                    }
                    printer["progress"] = data.get("progress", 0)
                    printer["time_remaining"] = data.get("time_remaining", 0)
                    printer["z_height"] = data["printer"].get("axis_z", 0)
                    printer["file"] = data.get("file", {}).get("name") if data.get("file") else None
                logging.debug(f"Successfully fetched status for {printer['name']}: {printer['state']}")
            else:
                with WriteLock(printers_rwlock):
                    printer["state"] = "OFFLINE"
                    printer["status"] = "Offline"
                    printer["temps"] = {"nozzle": 0, "bed": 0}
                    printer["progress"] = 0
                    printer["time_remaining"] = 0
                    printer["z_height"] = 0
                    printer["file"] = None
                logging.debug(f"Printer {printer['name']} is offline (status code: {response.status})")
    except asyncio.TimeoutError:
        with WriteLock(printers_rwlock):
            printer["state"] = "OFFLINE"
            printer["status"] = "Offline"
            printer["temps"] = {"nozzle": 0, "bed": 0}
            printer["progress"] = 0
            printer["time_remaining"] = 0
            printer["z_height"] = 0
            printer["file"] = None
        logging.debug(f"Timeout reaching printer {printer['name']}")
    except Exception as e:
        with WriteLock(printers_rwlock):
            printer["state"] = "OFFLINE"
            printer["status"] = "Offline"
            printer["temps"] = {"nozzle": 0, "bed": 0}
            printer["progress"] = 0
            printer["time_remaining"] = 0
            printer["z_height"] = 0
            printer["file"] = None
        logging.error(f"Error fetching status for {printer['name']}: {e}")

async def reset_printer_state_async(session, printer):
    if printer.get('type') == 'bambu':
        # Bambu printer reset not implemented
        logging.warning(f"Reset not implemented for Bambu printer {printer['name']}")
        return False
        
    headers = {"X-Api-Key": decrypt_api_key(printer["api_key"])}
    
    try:
        async with session.post(f"http://{printer['ip']}/api/v1/job", headers=headers, json={"command": "cancel"}) as resp:
            logging.debug(f"Cancel command response for {printer['name']}: {resp.status}")
            await asyncio.sleep(2)
    except Exception as e:
        logging.error(f"Error during cancel command for {printer['name']}: {str(e)}")
    
    try:
        async with session.post(f"http://{printer['ip']}/api/v1/connection", headers=headers, json={"command": "connect"}) as resp:
            logging.debug(f"Connection refresh response for {printer['name']}: {resp.status}")
            await asyncio.sleep(2)
    except Exception as e:
        logging.error(f"Error during connection refresh for {printer['name']}: {str(e)}")
    
    try:
        async with session.get(f"http://{printer['ip']}/api/v1/status", headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                actual_state = data['printer']['state']
                logging.debug(f"Printer {printer['name']} API state after reset: {actual_state}")
                return actual_state in ['IDLE', 'READY', 'OPERATIONAL']
    except Exception as e:
        logging.error(f"Error checking printer state for {printer['name']}: {str(e)}")
    
    return False

def process_multiple_prints_background(printer_ids, filepath, filename, task_id, socketio, app):
    total = len(printer_ids)
    completed = 0
    
    def background_task():
        nonlocal completed
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def process_printers():
            nonlocal completed
            session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(limit=20, ttl_dns_cache=300),
                timeout=aiohttp.ClientTimeout(total=Config.API_TIMEOUT)
            )
            
            results = []
            for idx, printer_id in enumerate(printer_ids):
                update_task_progress(task_id, completed, total, 
                                   f"Processing printer {idx + 1} of {total}")
                
                with ReadLock(printers_rwlock):
                    if 0 <= printer_id < len(PRINTERS):
                        printer = PRINTERS[printer_id].copy()
                    else:
                        results.append((printer_id, False, "Printer not found"))
                        completed += 1
                        continue
                
                success = await send_print_to_printer(session, printer, filepath, filename, None, None)
                results.append((printer_id, success, printer['name']))
                completed += 1
                
                if completed < total:
                    socketio.emit('task_progress', {
                        'task_id': task_id,
                        'current': completed,
                        'total': total,
                        'message': f"Sent to {completed} of {total} printers"
                    })
            
            await session.close()
            return results
        
        results = loop.run_until_complete(process_printers())
        loop.close()
        
        successful = sum(1 for _, success, _ in results if success)
        complete_task(task_id, 
                     f"Print sent to {successful} of {total} printers",
                     {'results': results})
        
        socketio.emit('task_complete', {
            'task_id': task_id,
            'message': f"Print sent to {successful} of {total} printers"
        })
    
    thread = threading.Thread(target=background_task)
    thread.daemon = True
    thread.start()

# All routes should be defined on the Blueprint, not inside register_printer_routes

@printer_bp.route('/add_printer', methods=['POST'])
def add_printer():
    global PRINTERS
    app = get_app()
    name = request.form.get('name')
    ip = request.form.get('ip')
    printer_type = request.form.get('printer_type', 'prusa')
    group = sanitize_group_name(request.form.get('group', 'Default'))  # Updated to use text-based groups

    if not name or not ip:
        flash("Name and IP address are required!")
        return redirect(url_for('index'))
    
    # Check license limits
    with ReadLock(printers_rwlock):
        current_printer_count = len(PRINTERS)
    
    max_printers = app.config.get('MAX_PRINTERS', 3)
    license_tier = app.config.get('LICENSE_TIER', 'free')
    
    if current_printer_count >= max_printers:
        flash(f"You have reached your printer limit ({max_printers}). Please upgrade your license to add more printers.")
        return redirect(url_for('index'))

    # Create new printer based on type
    new_printer = {
        "name": name,
        "ip": ip,
        "type": printer_type,
        "group": group,  # Now using sanitized string group
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

    # Add type-specific fields
    if printer_type == 'prusa':
        api_key = request.form.get('api_key')
        if not api_key:
            flash("API Key is required for Prusa printers!")
            return redirect(url_for('index'))
        new_printer["api_key"] = encrypt_api_key(api_key)

    elif printer_type == 'bambu':
        device_id = request.form.get('device_id')
        access_code = request.form.get('access_code')
        if not device_id or not access_code:
            flash("Device ID and Access Code are required for Bambu printers!")
            return redirect(url_for('index'))
        new_printer["device_id"] = device_id
        new_printer["serial_number"] = device_id
        new_printer["access_code"] = encrypt_api_key(access_code)
        
        # Try to connect immediately
        try:
            if connect_bambu_printer(new_printer):
                flash(f"Bambu printer {name} connected successfully!")
            else:
                flash(f"Added Bambu printer {name} but MQTT connection failed. Will retry automatically.")
        except Exception as e:
            logging.error(f"Error connecting Bambu printer: {str(e)}")
            flash(f"Added Bambu printer {name} but MQTT connection failed: {str(e)}")

    with WriteLock(printers_rwlock):
        PRINTERS.append(new_printer)
        save_data(PRINTERS_FILE, PRINTERS)

    flash(f"{name} added successfully")
    return redirect(url_for('index'))

@printer_bp.route('/add_printers_bulk', methods=['POST'])
def add_printers_bulk():
    app = get_app()
    try:
        data = request.get_json()
        if not data or 'printers' not in data:
            return jsonify({"success": False, "message": "No printer data provided"}), 400
        
        # Check current printer count and license limits
        with ReadLock(printers_rwlock):
            current_printer_count = len(PRINTERS)
        
        max_printers = app.config.get('MAX_PRINTERS', 3)
        license_tier = app.config.get('LICENSE_TIER', 'free')
        
        # Calculate how many we can add
        available_slots = max_printers - current_printer_count
        printers_to_add = data['printers'][:available_slots]
        
        if not printers_to_add:
            return jsonify({
                "success": False, 
                "message": f"You have reached your printer limit ({max_printers}). Please upgrade your license to add more printers.",
                "license_tier": license_tier,
                "max_printers": max_printers,
                "current_count": current_printer_count
            }), 403
        
        new_printers = []
        for printer_data in printers_to_add:
            name = printer_data.get('name')
            ip = printer_data.get('ip')
            printer_type = printer_data.get('printer_type', 'prusa')
            group = sanitize_group_name(printer_data.get('group', 'Default'))  # Updated for text-based groups
            
            if not name or not ip:
                continue
                
            new_printer = {
                "name": name,
                "ip": ip,
                "type": printer_type,
                "group": group,  # Now using sanitized string group
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
            
            # Add type-specific fields
            if printer_type == 'prusa':
                api_key = printer_data.get('api_key')
                if api_key:
                    new_printer["api_key"] = encrypt_api_key(api_key)
                else:
                    continue  # Skip printers without API key
                    
            elif printer_type == 'bambu':
                device_id = printer_data.get('device_id')
                access_code = printer_data.get('access_code')
                if device_id and access_code:
                    new_printer["device_id"] = device_id
                    new_printer["serial_number"] = device_id
                    new_printer["access_code"] = encrypt_api_key(access_code)
                else:
                    continue  # Skip Bambu printers without required fields
            
            new_printers.append(new_printer)
        
        # After the loop, connect Bambu printers
        for printer in new_printers:
            if printer['type'] == 'bambu':
                try:
                    connect_bambu_printer(printer)
                except Exception as e:
                    logging.error(f"Failed to connect Bambu printer {printer['name']}: {str(e)}")
        
        with WriteLock(printers_rwlock):
            PRINTERS.extend(new_printers)
            save_data(PRINTERS_FILE, PRINTERS)
        
        message = f"{len(new_printers)} printers added successfully"
        if len(new_printers) < len(data.get('printers', [])):
            message += f" (limited by your {license_tier} tier license)"
        
        flash(f"{message}")
        return jsonify({
            "success": True, 
            "message": message,
            "added_count": len(new_printers),
            "license_tier": license_tier,
            "max_printers": max_printers,
            "current_count": current_printer_count + len(new_printers)
        }), 200

    except Exception as e:
        logging.error(f"Error in bulk printer addition: {str(e)}")
        return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500

@printer_bp.route('/delete_printer/<int:printer_id>', methods=['POST'])
def delete_printer(printer_id):
    global PRINTERS
    with WriteLock(printers_rwlock):
        if 0 <= printer_id < len(PRINTERS):
            deleted_printer = PRINTERS.pop(printer_id)
            save_data(PRINTERS_FILE, PRINTERS)
            flash(f"Printer {deleted_printer['name']} deleted successfully")
        else:
            flash("Printer not found")
    return redirect(url_for('index'))

@printer_bp.route('/delete_all_printers', methods=['POST'])
def delete_all_printers():
    global PRINTERS
    with WriteLock(printers_rwlock):
        PRINTERS.clear()
        save_data(PRINTERS_FILE, PRINTERS)
    flash("All printers deleted successfully")
    return redirect(url_for('index'))

@printer_bp.route('/send_print/<int:printer_id>', methods=['POST'])
def send_print(printer_id):
    app = get_app()
    socketio = get_socketio()
    file = request.files.get('gcode_file')
    
    valid, message = validate_gcode_file(file)
    if not valid:
        flash(message)
        return redirect(url_for('index'))
    
    filename = secure_filename(file.filename)
    
    if filename.lower().endswith('.3mf'):
        filename = filename[:-4] + '.gcode.3mf'
    elif not filename.lower().endswith('.gcode'):
        filename += '.gcode'
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    printer_copy = None
    with ReadLock(printers_rwlock):
        if 0 <= printer_id < len(PRINTERS):
            printer_copy = PRINTERS[printer_id].copy()
    
    if not printer_copy:
        flash("Printer not found")
        return redirect(url_for('index'))
    
    def background_task():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def send_and_update():
            session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(limit=10, ttl_dns_cache=300),
                timeout=aiohttp.ClientTimeout(total=Config.API_TIMEOUT)
            )
            
            success = await send_print_to_printer(session, printer_copy, filepath, filename, None, None)
            
            await session.close()
            
            if success:
                with WriteLock(printers_rwlock):
                    if 0 <= printer_id < len(PRINTERS):
                        PRINTERS[printer_id]["state"] = "PRINTING"
                        PRINTERS[printer_id]["file"] = filename
                        PRINTERS[printer_id]["from_queue"] = False
                        save_data(PRINTERS_FILE, PRINTERS)
                
                with SafeLock(filament_lock):
                    total_filament = TOTAL_FILAMENT_CONSUMPTION / 1000
                with SafeLock(orders_lock):
                    orders_data = ORDERS.copy()
                with ReadLock(printers_rwlock):
                    printers_copy = copy.deepcopy(PRINTERS)
                socketio.emit('status_update', {'printers': printers_copy, 'total_filament': total_filament, 'orders': orders_data})
            
            return success
        
        loop.run_until_complete(send_and_update())
        loop.close()
    
    thread = threading.Thread(target=background_task)
    thread.daemon = True
    thread.start()
    
    flash(f"Sending {filename} to {printer_copy['name']}...")
    return redirect(url_for('index'))

@printer_bp.route('/send_print_multiple', methods=['POST'])
def send_print_multiple():
    app = get_app()
    socketio = get_socketio()
    file = request.files.get('gcode_file')
    printer_ids = request.form.getlist('printer_ids[]', type=int)
    
    if not printer_ids:
        flash("No printers selected")
        return redirect(url_for('index'))
    
    valid, message = validate_gcode_file(file)
    if not valid:
        flash(message)
        return redirect(url_for('index'))
    
    filename = secure_filename(file.filename)
    
    if filename.lower().endswith('.3mf'):
        filename = filename[:-4] + '.gcode.3mf'
    elif not filename.lower().endswith('.gcode'):
        filename += '.gcode'
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    # Register a new task
    task_id = str(uuid.uuid4())
    register_task(task_id, f"Sending {filename} to {len(printer_ids)} printers")
    
    # Process prints in background
    process_multiple_prints_background(printer_ids, filepath, filename, task_id, socketio, app)
    
    return jsonify({
        'success': True,
        'task_id': task_id,
        'message': f"Starting to send {filename} to {len(printer_ids)} printers..."
    })

@printer_bp.route('/stop_print/<int:printer_id>', methods=['POST'])
def stop_print(printer_id):
    socketio = get_socketio()
    try:
        printer_copy = None
        printer_name = None
        
        with ReadLock(printers_rwlock):
            if 0 <= printer_id < len(PRINTERS):
                printer_copy = copy.deepcopy(PRINTERS[printer_id])
                printer_name = printer_copy['name']
            else:
                flash("Printer not found")
                return redirect(url_for('index'))
        
        if not printer_copy:
            flash("Could not retrieve printer data")
            return redirect(url_for('index'))
            
        logging.info(f"Processing stop request for printer: {printer_name}")
        
        socketio.emit('print_stop_started', {
            'printer_id': printer_id,
            'printer_name': printer_name
        })
        
        def background_stop_task():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def execute_stop():
                    async with aiohttp.ClientSession(
                        connector=aiohttp.TCPConnector(limit=10, ttl_dns_cache=300),
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as session:
                        from services.printer_manager import stop_print_async
                        return await stop_print_async(session, printer_copy)
                
                success = loop.run_until_complete(execute_stop())
                loop.close()
                
                if success:
                    with WriteLock(printers_rwlock):
                        if 0 <= printer_id < len(PRINTERS):
                            PRINTERS[printer_id]["state"] = "IDLE"
                            PRINTERS[printer_id]["status"] = "Idle"
                            PRINTERS[printer_id]["progress"] = 0
                            PRINTERS[printer_id]["time_remaining"] = 0
                            PRINTERS[printer_id]["file"] = None
                            PRINTERS[printer_id]["job_id"] = None
                            PRINTERS[printer_id]["order_id"] = None
                            PRINTERS[printer_id]["from_queue"] = False
                            save_data(PRINTERS_FILE, PRINTERS)
                    
                    with SafeLock(filament_lock):
                        total_filament = TOTAL_FILAMENT_CONSUMPTION / 1000
                    with SafeLock(orders_lock):
                        orders_data = ORDERS.copy()
                    with ReadLock(printers_rwlock):
                        printers_data = copy.deepcopy(PRINTERS)
                    
                    socketio.emit('status_update', {
                        'printers': printers_data,
                        'total_filament': total_filament,
                        'orders': orders_data
                    })
                    
                    socketio.emit('print_stop_complete', {
                        'printer_id': printer_id,
                        'printer_name': printer_name,
                        'success': True
                    })
                    socketio.emit('flash_message', {
                        'message': f"Print stopped successfully on {printer_name}",
                        'category': 'success'
                    })
                else:
                    socketio.emit('print_stop_complete', {
                        'printer_id': printer_id,
                        'printer_name': printer_name,
                        'success': False
                    })
                    socketio.emit('flash_message', {
                        'message': f"Failed to stop print on {printer_name}",
                        'category': 'warning'
                    })
            
            except Exception as e:
                logging.error(f"Error in background stop task for {printer_name}: {str(e)}")
                socketio.emit('print_stop_complete', {
                    'printer_id': printer_id,
                    'printer_name': printer_name,
                    'success': False,
                    'error': str(e)
                })
                socketio.emit('flash_message', {
                    'message': f"Error stopping print on {printer_name}: {str(e)}",
                    'category': 'danger'
                })
        
        stop_thread = threading.Thread(target=background_stop_task)
        stop_thread.daemon = True
        stop_thread.start()
        
        flash(f"Stop command sent to {printer_name}. Processing...")
        return redirect(url_for('index'))
        
    except Exception as e:
        logging.error(f"Error initiating stop print: {str(e)}")
        flash(f"Error stopping print: {str(e)}")
        return redirect(url_for('index'))

@printer_bp.route('/pause_print/<int:printer_id>', methods=['POST'])
def pause_print(printer_id):
    socketio = get_socketio()
    try:
        printer_copy = None
        printer_name = None
        
        with ReadLock(printers_rwlock):
            if 0 <= printer_id < len(PRINTERS):
                printer_copy = copy.deepcopy(PRINTERS[printer_id])
                printer_name = printer_copy['name']
            else:
                flash("Printer not found")
                return redirect(url_for('index'))
        
        if not printer_copy:
            flash("Could not retrieve printer data")
            return redirect(url_for('index'))
            
        logging.info(f"Processing pause request for printer: {printer_name}")
        
        socketio.emit('print_pause_started', {
            'printer_id': printer_id,
            'printer_name': printer_name
        })
        
        def background_pause_task():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def execute_pause():
                    async with aiohttp.ClientSession(
                        connector=aiohttp.TCPConnector(limit=10, ttl_dns_cache=300),
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as session:
                        from services.printer_manager import pause_print_async
                        return await pause_print_async(session, printer_copy)
                
                success = loop.run_until_complete(execute_pause())
                loop.close()
                
                if success:
                    with WriteLock(printers_rwlock):
                        if 0 <= printer_id < len(PRINTERS):
                            PRINTERS[printer_id]["state"] = "PAUSED"
                            PRINTERS[printer_id]["status"] = "Paused"
                            save_data(PRINTERS_FILE, PRINTERS)
                    
                    with SafeLock(filament_lock):
                        total_filament = TOTAL_FILAMENT_CONSUMPTION / 1000
                    with SafeLock(orders_lock):
                        orders_data = ORDERS.copy()
                    with ReadLock(printers_rwlock):
                        printers_data = copy.deepcopy(PRINTERS)
                    
                    socketio.emit('status_update', {
                        'printers': printers_data,
                        'total_filament': total_filament,
                        'orders': orders_data
                    })
                    
                    socketio.emit('print_pause_complete', {
                        'printer_id': printer_id,
                        'printer_name': printer_name,
                        'success': True
                    })
                    socketio.emit('flash_message', {
                        'message': f"Print paused successfully on {printer_name}",
                        'category': 'success'
                    })
                else:
                    socketio.emit('print_pause_complete', {
                        'printer_id': printer_id,
                        'printer_name': printer_name,
                        'success': False
                    })
                    socketio.emit('flash_message', {
                        'message': f"Failed to pause print on {printer_name}",
                        'category': 'warning'
                    })
            
            except Exception as e:
                logging.error(f"Error in background pause task for {printer_name}: {str(e)}")
                socketio.emit('print_pause_complete', {
                    'printer_id': printer_id,
                    'printer_name': printer_name,
                    'success': False,
                    'error': str(e)
                })
                socketio.emit('flash_message', {
                    'message': f"Error pausing print on {printer_name}: {str(e)}",
                    'category': 'danger'
                })
        
        pause_thread = threading.Thread(target=background_pause_task)
        pause_thread.daemon = True
        pause_thread.start()
        
        flash(f"Pause command sent to {printer_name}. Processing...")
        return redirect(url_for('index'))
        
    except Exception as e:
        logging.error(f"Error initiating pause print: {str(e)}")
        flash(f"Error pausing print: {str(e)}")
        return redirect(url_for('index'))

@printer_bp.route('/resume_print/<int:printer_id>', methods=['POST'])
def resume_print(printer_id):
    socketio = get_socketio()
    try:
        printer_copy = None
        printer_name = None
        
        with ReadLock(printers_rwlock):
            if 0 <= printer_id < len(PRINTERS):
                printer_copy = copy.deepcopy(PRINTERS[printer_id])
                printer_name = printer_copy['name']
            else:
                flash("Printer not found")
                return redirect(url_for('index'))
        
        if not printer_copy:
            flash("Could not retrieve printer data")
            return redirect(url_for('index'))
            
        logging.info(f"Processing resume request for printer: {printer_name}")
        
        socketio.emit('print_resume_started', {
            'printer_id': printer_id,
            'printer_name': printer_name
        })
        
        def background_resume_task():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def execute_resume():
                    async with aiohttp.ClientSession(
                        connector=aiohttp.TCPConnector(limit=10, ttl_dns_cache=300),
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as session:
                        from services.printer_manager import resume_print_async
                        return await resume_print_async(session, printer_copy)
                
                success = loop.run_until_complete(execute_resume())
                loop.close()
                
                if success:
                    with WriteLock(printers_rwlock):
                        if 0 <= printer_id < len(PRINTERS):
                            PRINTERS[printer_id]["state"] = "PRINTING"
                            PRINTERS[printer_id]["status"] = "Printing"
                            save_data(PRINTERS_FILE, PRINTERS)
                    
                    with SafeLock(filament_lock):
                        total_filament = TOTAL_FILAMENT_CONSUMPTION / 1000
                    with SafeLock(orders_lock):
                        orders_data = ORDERS.copy()
                    with ReadLock(printers_rwlock):
                        printers_data = copy.deepcopy(PRINTERS)
                    
                    socketio.emit('status_update', {
                        'printers': printers_data,
                        'total_filament': total_filament,
                        'orders': orders_data
                    })
                    
                    socketio.emit('print_resume_complete', {
                        'printer_id': printer_id,
                        'printer_name': printer_name,
                        'success': True
                    })
                    socketio.emit('flash_message', {
                        'message': f"Print resumed successfully on {printer_name}",
                        'category': 'success'
                    })
                else:
                    socketio.emit('print_resume_complete', {
                        'printer_id': printer_id,
                        'printer_name': printer_name,
                        'success': False
                    })
                    socketio.emit('flash_message', {
                        'message': f"Failed to resume print on {printer_name}",
                        'category': 'warning'
                    })
            
            except Exception as e:
                logging.error(f"Error in background resume task for {printer_name}: {str(e)}")
                socketio.emit('print_resume_complete', {
                    'printer_id': printer_id,
                    'printer_name': printer_name,
                    'success': False,
                    'error': str(e)
                })
                socketio.emit('flash_message', {
                    'message': f"Error resuming print on {printer_name}: {str(e)}",
                    'category': 'danger'
                })
        
        resume_thread = threading.Thread(target=background_resume_task)
        resume_thread.daemon = True
        resume_thread.start()
        
        flash(f"Resume command sent to {printer_name}. Processing...")
        return redirect(url_for('index'))
        
    except Exception as e:
        logging.error(f"Error initiating resume print: {str(e)}")
        flash(f"Error resuming print: {str(e)}")
        return redirect(url_for('index'))

@printer_bp.route('/stop_all_printers', methods=['POST'])
def stop_all_printers():
    socketio = get_socketio()
    try:
        printers_to_stop = []
        with ReadLock(printers_rwlock):
            for i, printer in enumerate(PRINTERS):
                if printer["state"] in ["PRINTING", "PAUSED"]:
                    printers_to_stop.append({
                        'index': i,
                        'data': copy.deepcopy(printer)
                    })

        if not printers_to_stop:
            flash("No active prints to stop")
            return redirect(url_for('index'))
            
        count = len(printers_to_stop)
        flash(f"Stopping {count} printers. Processing...")
        
        def background_stop_all_task():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                async def stop_all():
                    session = aiohttp.ClientSession(
                        connector=aiohttp.TCPConnector(limit=20, ttl_dns_cache=300),
                        timeout=aiohttp.ClientTimeout(total=Config.API_TIMEOUT)
                    )
                    
                    success_count = 0
                    failure_count = 0
                    
                    for printer_info in printers_to_stop:
                        printer = printer_info['data']
                        idx = printer_info['index']
                        
                        try:
                            from services.printer_manager import stop_print_async
                            success = await stop_print_async(session, printer)
                            
                            if success:
                                with WriteLock(printers_rwlock):
                                    if 0 <= idx < len(PRINTERS):
                                        PRINTERS[idx]["state"] = "IDLE"
                                        PRINTERS[idx]["status"] = "Idle"
                                        PRINTERS[idx]["progress"] = 0
                                        PRINTERS[idx]["time_remaining"] = 0
                                        PRINTERS[idx]["file"] = None
                                        PRINTERS[idx]["job_id"] = None
                                        PRINTERS[idx]["order_id"] = None
                                        PRINTERS[idx]["manually_set"] = False
                                        success_count += 1
                            else:
                                failure_count += 1
                        except Exception as e:
                            logging.error(f"Error stopping printer {printer['name']}: {str(e)}")
                            failure_count += 1
                    
                    await session.close()
                    
                    if success_count > 0:
                        save_data(PRINTERS_FILE, PRINTERS)
                    
                    return success_count, failure_count
                
                success_count, failure_count = loop.run_until_complete(stop_all())
                
                with SafeLock(filament_lock):
                    total_filament = TOTAL_FILAMENT_CONSUMPTION / 1000
                with SafeLock(orders_lock):
                    orders_data = ORDERS.copy()
                with ReadLock(printers_rwlock):
                    printers_data = copy.deepcopy(PRINTERS)
                
                socketio.emit('status_update', {
                    'printers': printers_data,
                    'total_filament': total_filament,
                    'orders': orders_data
                })
                
                socketio.emit('flash_message', {
                    'message': f"Stopped {success_count} printers successfully. {failure_count} failed.",
                    'category': 'success' if failure_count == 0 else 'warning'
                })
                
            except Exception as e:
                logging.error(f"Error in stop all task: {str(e)}")
                socketio.emit('flash_message', {
                    'message': f"Error stopping printers: {str(e)}",
                    'category': 'danger'
                })
        
        stop_thread = threading.Thread(target=background_stop_all_task)
        stop_thread.daemon = True
        stop_thread.start()
        
        return redirect(url_for('index'))
            
    except Exception as e:
        logging.error(f"Error initiating stop_all_printers: {str(e)}")
        flash(f"Error stopping all printers: {str(e)}")
        return redirect(url_for('index'))

@printer_bp.route('/mark_ready/<int:printer_id>', methods=['POST'])
def mark_ready(printer_id):
    socketio = get_socketio()
    app = get_app()
    try:
        printer_copy = None
        printer_name = None
        
        with ReadLock(printers_rwlock, timeout=5):
            if 0 <= printer_id < len(PRINTERS):
                printer_copy = PRINTERS[printer_id].copy()
                printer_name = printer_copy['name']
            else:
                flash("Printer not found")
                return redirect(url_for('index'))
        
        if not printer_copy:
            flash("Printer not found")
            return redirect(url_for('index'))
            
        if printer_copy["state"] not in ["FINISHED", "EJECTING"]:
            flash(f"Printer {printer_name} is not in FINISHED or EJECTING state")
            return redirect(url_for('index'))
        
        def reset_printer_task():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            success = False
            try:
                session = aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(limit=20, ttl_dns_cache=300),
                    timeout=aiohttp.ClientTimeout(total=Config.API_TIMEOUT)
                )
                
                success = loop.run_until_complete(reset_printer_state_async(session, printer_copy))
                
                loop.run_until_complete(session.close())
                loop.close()
                
                logging.debug(f"Printer reset operation result for {printer_name}: {success}")
            except Exception as e:
                logging.error(f"Error in printer reset task for {printer_name}: {str(e)}")
            
            with WriteLock(printers_rwlock, timeout=30):
                if 0 <= printer_id < len(PRINTERS):
                    printer = PRINTERS[printer_id]
                    if printer["state"] in ["FINISHED", "EJECTING"]:
                        previous_state = printer["state"]
                        printer["state"] = "READY"
                        printer["status"] = "Ready"
                        printer["manually_set"] = True
                        printer["manual_timeout"] = time.time() + 3600
                        printer.pop("manual_state_time", None)
                        printer["progress"] = 0
                        printer["time_remaining"] = 0
                        printer["file"] = None
                        printer["job_id"] = None
                        printer["order_id"] = None
                        printer.pop("ejection_processed", None)
                        printer.pop("ejection_start_time", None)
                        printer.pop("ejection_timeout", None)
                        
                        save_data(PRINTERS_FILE, PRINTERS)
                        logging.debug(f"Marked {printer['name']} as READY from {previous_state} after physical reset. Reset success: {success}")
            
            start_background_distribution(socketio, app)
            
            with SafeLock(filament_lock):
                total_filament = TOTAL_FILAMENT_CONSUMPTION / 1000
            with SafeLock(orders_lock):
                orders_data = ORDERS.copy()
            with ReadLock(printers_rwlock):
                printers_copy = copy.deepcopy(PRINTERS)
            socketio.emit('status_update', {'printers': printers_copy, 'total_filament': total_filament, 'orders': orders_data})
        
        thread = threading.Thread(target=reset_printer_task)
        thread.daemon = True
        thread.start()
        
        flash(f"Marked {printer_name} as Ready and resetting printer state...")
        
    except TimeoutError as e:
        logging.error(f"Timeout in mark_ready: {str(e)}")
        flash(f"Operation timed out. Try resetting locks or restarting the server.")
    except Exception as e:
        logging.error(f"Error in mark_ready: {str(e)}")
        flash(f"Error: {str(e)}")
        
    return redirect(url_for('index'))

@printer_bp.route('/mark_ready_by_name', methods=['POST'])
def mark_ready_by_name():
    """Mark individual printer as ready by name"""
    socketio = get_socketio()
    printer_name = request.form.get('printer_name')

    if not printer_name:
        flash("Printer name not provided", "error")
        return redirect(url_for('index'))

    # Find and update the specific printer
    with WriteLock(printers_rwlock):
        printer_found = False
        for printer in PRINTERS:
            if printer['name'] == printer_name and printer['state'] in ['FINISHED', 'EJECTING']:
                printer.update({
                    "state": 'READY',
                    "status": 'Ready',
                    "progress": 0,
                    "time_remaining": 0,
                    "file": None,
                    "job_id": None,
                    "order_id": None,
                    "manually_set": True,
                    "ejection_processed": False,
                    "ejection_start_time": None,
                    "finish_time": None
                })
                printer_found = True
                logging.info(f"Marked printer {printer_name} as READY")
                break

        if not printer_found:
            flash(f"Printer '{printer_name}' not found or not in a finished state", "error")
            return redirect(url_for('index'))

        # Save the changes
        save_data(PRINTERS_FILE, PRINTERS)
        flash(f"✅ Printer '{printer_name}' marked as Ready", "success")

    # Emit status update
    if socketio:
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
        
    return redirect(url_for('index'))

@printer_bp.route('/mark_all_ready', methods=['POST'])
def mark_all_ready():
    socketio = get_socketio()
    app = get_app()
    try:
        printers_to_reset = []
        
        # First, quickly identify printers that need to be reset (minimal lock time)
        with ReadLock(printers_rwlock, timeout=5):
            for i, printer in enumerate(PRINTERS):
                if printer["state"] in ["FINISHED", "EJECTING"]:
                    printers_to_reset.append({
                        'index': i,
                        'name': printer['name']
                    })
        
        if not printers_to_reset:
            flash("No printers in FINISHED or EJECTING state to mark as Ready")
            return redirect(url_for('index'))
        
        # Process the updates in a background thread to avoid blocking the web request
        def background_mark_all_ready():
            success_count = 0
            
            # Update printer states without making API calls (instant operation)
            with WriteLock(printers_rwlock, timeout=10):
                for printer_info in printers_to_reset:
                    idx = printer_info['index']
                    if 0 <= idx < len(PRINTERS):
                        printer = PRINTERS[idx]
                        if printer["state"] in ["FINISHED", "EJECTING"]:
                            # Force immediate state change without API reset
                            printer["state"] = "READY"
                            printer["status"] = "Ready"
                            printer["manually_set"] = True
                            printer["manual_timeout"] = time.time() + 3600  # 1 hour
                            printer.pop("manual_state_time", None)
                            printer["progress"] = 0
                            printer["time_remaining"] = 0
                            printer["file"] = None
                            printer["job_id"] = None
                            printer["order_id"] = None
                            printer.pop("ejection_processed", None)
                            printer.pop("ejection_start_time", None)
                            printer.pop("ejection_timeout", None)
                            
                            logging.info(f"INSTANT_MARK_READY: {printer['name']} marked as READY instantly")
                            success_count += 1
                
                if success_count > 0:
                    save_data(PRINTERS_FILE, PRINTERS)
            
            # Trigger job distribution
            if success_count > 0:
                start_background_distribution(socketio, app)
            
            # Send updated status to frontend
            with SafeLock(filament_lock):
                total_filament = TOTAL_FILAMENT_CONSUMPTION / 1000
            with SafeLock(orders_lock):
                orders_data = ORDERS.copy()
            with ReadLock(printers_rwlock):
                printers_copy = copy.deepcopy(PRINTERS)
            
            socketio.emit('status_update', {
                'printers': printers_copy, 
                'total_filament': total_filament, 
                'orders': orders_data
            })
            
            logging.info(f"MARK_ALL_READY: Completed - {success_count} printers marked as ready")
        
        # Start background processing
        thread = threading.Thread(target=background_mark_all_ready)
        thread.daemon = True
        thread.start()
        
        # Return immediate response
        flash(f"Marking {len(printers_to_reset)} printers as Ready...")
        return redirect(url_for('index'))
        
    except TimeoutError as e:
        logging.error(f"Timeout in mark_all_ready: {str(e)}")
        flash("Operation timed out. Server may be busy. Try again in a moment.")
        return redirect(url_for('index'))
    except Exception as e:
        logging.error(f"Error in mark_all_ready: {str(e)}")
        flash(f"Error: {str(e)}")
        return redirect(url_for('index'))

@printer_bp.route('/mark_group_ready/<path:group>', methods=['POST']) # <-- THE CHANGE IS HERE
def mark_group_ready(group):
    """Mark all FINISHED printers in a specific group as READY"""
    socketio = get_socketio()
    app = get_app()
    try:
        printers_to_reset = []
        with ReadLock(printers_rwlock):
            # The 'path' converter ensures that 'group' contains the full, decoded URL segment
            for i, printer in enumerate(PRINTERS):
                # Now comparing text-based groups
                if printer["state"] in ["FINISHED", "EJECTING"] and printer["group"] == group:
                    printers_to_reset.append({
                        'index': i,
                        'data': printer.copy()
                    })
        
        if not printers_to_reset:
            flash(f"No printers in Group {group} in FINISHED or EJECTING state")
            return redirect(url_for('index'))
        
        def reset_group_printers_task():
            # Skip all the async reset operations - just mark printers as READY immediately
            success_count = 0
            with WriteLock(printers_rwlock):
                for printer_info in printers_to_reset:
                    idx = printer_info['index']
                    if 0 <= idx < len(PRINTERS):
                        printer = PRINTERS[idx]
                        previous_state = printer.get("state", "UNKNOWN")
                        
                        # Force state change immediately without any API calls
                        printer["state"] = "READY"
                        printer["status"] = "Ready"
                        printer["manually_set"] = True
                        printer["manual_timeout"] = time.time() + 3600
                        printer.pop("manual_state_time", None)
                        printer["progress"] = 0
                        printer["time_remaining"] = 0
                        printer["file"] = None
                        printer["job_id"] = None
                        printer["order_id"] = None
                        printer.pop("ejection_processed", None)
                        printer.pop("ejection_start_time", None)
                        printer.pop("ejection_timeout", None)
                        printer.pop("finish_time", None)
                        
                        logging.info(f"MANUAL_MARK_READY: Group {group} - {printer['name']} marked as READY from {previous_state} instantly")
                        success_count += 1
            
            if success_count > 0:
                save_data(PRINTERS_FILE, PRINTERS)
            
            # Log the group action
            try:
                from utils.logger import log_manual_action
                log_manual_action('MARK_GROUP_READY', f'group_{group}', {
                    'group': group,
                    'printers_affected': success_count,
                    'total_attempted': len(printers_to_reset)
                })
            except ImportError:
                logging.info(f"MANUAL_MARK_READY: Group {group} - {success_count} printers marked as ready")
            
            start_background_distribution(socketio, app)
            
            with SafeLock(filament_lock):
                total_filament = TOTAL_FILAMENT_CONSUMPTION / 1000
            with SafeLock(orders_lock):
                orders_data = ORDERS.copy()
            with ReadLock(printers_rwlock):
                printers_copy = copy.deepcopy(PRINTERS)
            socketio.emit('status_update', {'printers': printers_copy, 'total_filament': total_filament, 'orders': orders_data})
        
        thread = threading.Thread(target=reset_group_printers_task)
        thread.daemon = True
        thread.start()
        
        flash(f"Marking {len(printers_to_reset)} printers in Group {group} as Ready...")
        
    except Exception as e:
        logging.error(f"Error in mark_group_ready: {str(e)}")
        flash(f"Error: {str(e)}")
        
    return redirect(url_for('index'))

@printer_bp.route('/set_service/<int:printer_id>', methods=['POST'])
def set_service(printer_id):
    try:
        printer_info = None
        with ReadLock(printers_rwlock):
            if 0 <= printer_id < len(PRINTERS):
                printer_info = {
                    'name': PRINTERS[printer_id]['name'],
                    'exists': True
                }
            else:
                printer_info = {'exists': False}
        
        if printer_info and printer_info['exists']:
            with WriteLock(printers_rwlock):
                if 0 <= printer_id < len(PRINTERS):
                    PRINTERS[printer_id]["service_mode"] = True
                    save_data(PRINTERS_FILE, PRINTERS)
                    flash(f"Printer {printer_info['name']} set to service mode")
                else:
                    flash("Printer not found")
        else:
            flash("Printer not found")
            
        return redirect(url_for('index'))
    except Exception as e:
        logging.error(f"Error setting service mode: {str(e)}")
        flash(f"Error: {str(e)}")
        return redirect(url_for('index'))

@printer_bp.route('/service_complete/<int:printer_id>', methods=['POST'])
def service_complete(printer_id):
    try:
        printer_info = None
        with ReadLock(printers_rwlock):
            if 0 <= printer_id < len(PRINTERS):
                printer_info = {
                    'name': PRINTERS[printer_id]['name'],
                    'exists': True
                }
            else:
                printer_info = {'exists': False}
        
        if printer_info and printer_info['exists']:
            with WriteLock(printers_rwlock):
                if 0 <= printer_id < len(PRINTERS):
                    PRINTERS[printer_id]["service_mode"] = False
                    save_data(PRINTERS_FILE, PRINTERS)
                    flash(f"Service complete for {printer_info['name']}")
                else:
                    flash("Printer not found")
        else:
            flash("Printer not found")
            
        return redirect(url_for('index'))
    except Exception as e:
        logging.error(f"Error completing service: {str(e)}")
        flash(f"Error: {str(e)}")
        return redirect(url_for('index'))

@printer_bp.route('/stop_print_by_name', methods=['POST'])
def stop_print_by_name():
    printer_name = request.form.get('printer_name')
    
    with ReadLock(printers_rwlock):
        for i, printer in enumerate(PRINTERS):
            if printer['name'] == printer_name:
                return stop_print(i)
    
    flash(f"Printer {printer_name} not found")
    return redirect(url_for('index'))

@printer_bp.route('/pause_print_by_name', methods=['POST'])
def pause_print_by_name():
    printer_name = request.form.get('printer_name')
    
    with ReadLock(printers_rwlock):
        for i, printer in enumerate(PRINTERS):
            if printer['name'] == printer_name:
                return pause_print(i)
    
    flash(f"Printer {printer_name} not found")
    return redirect(url_for('index'))

@printer_bp.route('/resume_print_by_name', methods=['POST'])
def resume_print_by_name():
    printer_name = request.form.get('printer_name')
    
    with ReadLock(printers_rwlock):
        for i, printer in enumerate(PRINTERS):
            if printer['name'] == printer_name:
                return resume_print(i)
    
    flash(f"Printer {printer_name} not found")
    return redirect(url_for('index'))

@printer_bp.route('/set_service_by_name', methods=['POST'])
def set_service_by_name():
    printer_name = request.form.get('printer_name')
    
    with ReadLock(printers_rwlock):
        for i, printer in enumerate(PRINTERS):
            if printer['name'] == printer_name:
                return set_service(i)
    
    flash(f"Printer {printer_name} not found")
    return redirect(url_for('index'))

@printer_bp.route('/service_complete_by_name', methods=['POST'])
def service_complete_by_name():
    printer_name = request.form.get('printer_name')
    
    with ReadLock(printers_rwlock):
        for i, printer in enumerate(PRINTERS):
            if printer['name'] == printer_name:
                return service_complete(i)
    
    flash(f"Printer {printer_name} not found")
    return redirect(url_for('index'))

@printer_bp.route('/delete_printer_by_name', methods=['POST'])
def delete_printer_by_name():
    printer_name = request.form.get('printer_name')
    
    with WriteLock(printers_rwlock):
        for i, printer in enumerate(PRINTERS):
            if printer['name'] == printer_name:
                PRINTERS.pop(i)
                save_data(PRINTERS_FILE, PRINTERS)
                flash(f"Printer {printer_name} deleted successfully")
                return redirect(url_for('index'))
    
    flash(f"Printer {printer_name} not found")
    return redirect(url_for('index'))

def register_printer_routes(app, socketio):
    """Register the printer routes blueprint with the app"""
    global _app, _socketio
    _app = app
    _socketio = socketio
    app.register_blueprint(printer_bp)
