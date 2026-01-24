"""
Ejection Codes API Routes

Provides CRUD operations for managing ejection code presets.
Users can upload, store, and select ejection codes to use for auto-ejection after prints.
"""

import os
import uuid
import copy
import time
from datetime import datetime
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from services.state import (
    EJECTION_CODES, EJECTION_CODES_FILE, PRINTERS,
    save_data, SafeLock, ReadLock, logging,
    ejection_codes_lock, validate_ejection_file, printers_rwlock
)

ejection_codes_bp = Blueprint('ejection_codes', __name__)

# Store socketio reference for emitting updates
_socketio = None

def register_ejection_codes_routes(app, socketio):
    """Register ejection codes routes with the app"""
    global _socketio
    _socketio = socketio
    app.register_blueprint(ejection_codes_bp, url_prefix='/api/v1/ejection-codes')


@ejection_codes_bp.route('', methods=['GET'])
def get_ejection_codes():
    """Get all stored ejection codes"""
    try:
        with SafeLock(ejection_codes_lock):
            # Return a copy of the ejection codes list
            codes = [code.copy() for code in EJECTION_CODES]
        
        return jsonify({
            'success': True,
            'ejection_codes': codes
        })
    except Exception as e:
        logging.error(f"Error fetching ejection codes: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ejection_codes_bp.route('', methods=['POST'])
def create_ejection_code():
    """Create a new ejection code preset
    
    Accepts either:
    - JSON body with 'name' and 'gcode' fields
    - Multipart form with 'name' and 'file' (G-code file upload)
    """
    try:
        # Check if this is a file upload or JSON
        if request.content_type and 'multipart/form-data' in request.content_type:
            # File upload
            name = request.form.get('name', '').strip()
            file = request.files.get('file')
            
            if not name:
                return jsonify({
                    'success': False,
                    'error': 'Name is required'
                }), 400
            
            if not file:
                return jsonify({
                    'success': False,
                    'error': 'File is required'
                }), 400
            
            # Validate file
            valid, message = validate_ejection_file(file)
            if not valid:
                return jsonify({
                    'success': False,
                    'error': message
                }), 400
            
            # Read file contents
            try:
                gcode = file.read().decode('utf-8')
            except UnicodeDecodeError:
                return jsonify({
                    'success': False,
                    'error': 'File must be a valid text/G-code file'
                }), 400
        else:
            # JSON body
            data = request.get_json()
            if not data:
                return jsonify({
                    'success': False,
                    'error': 'No data provided'
                }), 400
            
            name = data.get('name', '').strip()
            gcode = data.get('gcode', '').strip()
            
            if not name:
                return jsonify({
                    'success': False,
                    'error': 'Name is required'
                }), 400
            
            if not gcode:
                return jsonify({
                    'success': False,
                    'error': 'G-code content is required'
                }), 400
        
        # Check for duplicate names
        with SafeLock(ejection_codes_lock):
            for existing in EJECTION_CODES:
                if existing['name'].lower() == name.lower():
                    return jsonify({
                        'success': False,
                        'error': f'An ejection code named "{name}" already exists'
                    }), 400
            
            # Create new ejection code
            new_code = {
                'id': str(uuid.uuid4()),
                'name': name,
                'gcode': gcode,
                'created_at': datetime.now().isoformat()
            }
            
            EJECTION_CODES.append(new_code)
            save_data(EJECTION_CODES_FILE, EJECTION_CODES)
            
            logging.info(f"Created new ejection code: {name} (ID: {new_code['id']})")
        
        return jsonify({
            'success': True,
            'ejection_code': new_code,
            'message': f'Ejection code "{name}" created successfully'
        }), 201
        
    except Exception as e:
        logging.error(f"Error creating ejection code: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ejection_codes_bp.route('/<code_id>', methods=['GET'])
def get_ejection_code(code_id):
    """Get a specific ejection code by ID"""
    try:
        with SafeLock(ejection_codes_lock):
            for code in EJECTION_CODES:
                if code['id'] == code_id:
                    return jsonify({
                        'success': True,
                        'ejection_code': code.copy()
                    })
        
        return jsonify({
            'success': False,
            'error': 'Ejection code not found'
        }), 404
        
    except Exception as e:
        logging.error(f"Error fetching ejection code {code_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ejection_codes_bp.route('/<code_id>', methods=['PUT', 'PATCH'])
def update_ejection_code(code_id):
    """Update an existing ejection code"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        name = data.get('name', '').strip() if data.get('name') else None
        gcode = data.get('gcode', '').strip() if data.get('gcode') else None
        
        with SafeLock(ejection_codes_lock):
            # Find the code
            target_code = None
            for code in EJECTION_CODES:
                if code['id'] == code_id:
                    target_code = code
                    break
            
            if not target_code:
                return jsonify({
                    'success': False,
                    'error': 'Ejection code not found'
                }), 404
            
            # Check for duplicate names (if name is being changed)
            if name and name.lower() != target_code['name'].lower():
                for existing in EJECTION_CODES:
                    if existing['id'] != code_id and existing['name'].lower() == name.lower():
                        return jsonify({
                            'success': False,
                            'error': f'An ejection code named "{name}" already exists'
                        }), 400
            
            # Update fields
            if name:
                target_code['name'] = name
            if gcode:
                target_code['gcode'] = gcode
            target_code['updated_at'] = datetime.now().isoformat()
            
            save_data(EJECTION_CODES_FILE, EJECTION_CODES)
            
            logging.info(f"Updated ejection code: {target_code['name']} (ID: {code_id})")
        
        return jsonify({
            'success': True,
            'ejection_code': target_code.copy(),
            'message': f'Ejection code updated successfully'
        })
        
    except Exception as e:
        logging.error(f"Error updating ejection code {code_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ejection_codes_bp.route('/<code_id>', methods=['DELETE'])
def delete_ejection_code(code_id):
    """Delete an ejection code"""
    try:
        with SafeLock(ejection_codes_lock):
            # Find and remove the code
            for i, code in enumerate(EJECTION_CODES):
                if code['id'] == code_id:
                    removed_code = EJECTION_CODES.pop(i)
                    save_data(EJECTION_CODES_FILE, EJECTION_CODES)
                    
                    logging.info(f"Deleted ejection code: {removed_code['name']} (ID: {code_id})")
                    
                    return jsonify({
                        'success': True,
                        'message': f'Ejection code "{removed_code["name"]}" deleted successfully'
                    })
        
        return jsonify({
            'success': False,
            'error': 'Ejection code not found'
        }), 404
        
    except Exception as e:
        logging.error(f"Error deleting ejection code {code_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ejection_codes_bp.route('/<code_id>/test', methods=['POST'])
def test_ejection_code(code_id):
    """Test an ejection code by sending it to a specific printer
    
    Expects JSON body with:
    - printer_name: Name of the printer to send the G-code to
    - force_reconnect: (optional) If true, force reconnect MQTT before sending (helps with stuck state)
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        printer_name = data.get('printer_name', '').strip()
        force_reconnect = data.get('force_reconnect', False)
        
        if not printer_name:
            return jsonify({
                'success': False,
                'error': 'Printer name is required'
            }), 400
        
        # Find the ejection code
        ejection_code = None
        with SafeLock(ejection_codes_lock):
            for code in EJECTION_CODES:
                if code['id'] == code_id:
                    ejection_code = code.copy()
                    break
        
        if not ejection_code:
            return jsonify({
                'success': False,
                'error': 'Ejection code not found'
            }), 404
        
        # Find the printer
        printer_copy = None
        printer_index = None
        with ReadLock(printers_rwlock):
            for i, printer in enumerate(PRINTERS):
                if printer['name'] == printer_name:
                    printer_copy = copy.deepcopy(printer)
                    printer_index = i
                    break
        
        if not printer_copy:
            return jsonify({
                'success': False,
                'error': f'Printer "{printer_name}" not found'
            }), 404
        
        gcode = ejection_code['gcode']
        printer_type = printer_copy.get('type', 'prusa')
        
        # For Bambu printers, skip strict state checking for test commands
        # M400 in G-code causes the printer to report RUNNING/PRINTING state briefly
        # which would block subsequent test commands. For debugging, allow more states.
        printer_state = printer_copy.get('state', '').upper()
        
        if printer_type == 'bambu':
            from services.bambu_handler import BAMBU_PRINTER_STATES, bambu_states_lock
            
            # Log state for debugging but don't block based on it
            with bambu_states_lock:
                if printer_name in BAMBU_PRINTER_STATES:
                    bambu_state = BAMBU_PRINTER_STATES[printer_name]
                    actual_state = bambu_state.get('state', 'UNKNOWN').upper()
                    gcode_state = bambu_state.get('gcode_state', 'UNKNOWN').upper()
                    waiting_m400 = bambu_state.get('waiting_for_m400', False)
                    ejection_in_progress = bambu_state.get('ejection_in_progress', False)
                    
                    logging.info(f"[TEST] {printer_name} states - PRINTERS: {printer_state}, BAMBU: {actual_state}, gcode_state: {gcode_state}, waiting_m400: {waiting_m400}, ejection_in_progress: {ejection_in_progress}")
                    
                    # Only block if printer is actively PRINTING a job (not just processing G-code commands)
                    # RUNNING/PRINTING from M400 should not block test commands
                    if actual_state == 'PRINTING' and gcode_state == 'RUNNING':
                        # Check if there's actually a print job vs just command processing
                        has_print_job = bool(bambu_state.get('current_file'))
                        if has_print_job:
                            return jsonify({
                                'success': False,
                                'error': f'Printer "{printer_name}" is currently printing a job. Wait for print to complete.',
                                'state': actual_state,
                                'gcode_state': gcode_state
                            }), 400
                        else:
                            logging.info(f"[TEST] {printer_name} is in {actual_state}/{gcode_state} but no print job - allowing test command")
                    
                    # Clear stuck M400 waiting state if it's been too long (over 5 minutes)
                    if waiting_m400:
                        ejection_start = bambu_state.get('ejection_start_time', 0)
                        if ejection_start and (time.time() - ejection_start > 300):
                            logging.warning(f"[TEST] Clearing stuck waiting_for_m400 flag for {printer_name} (over 5 minutes)")
                            bambu_state['waiting_for_m400'] = False
                            bambu_state['ejection_in_progress'] = False
                else:
                    logging.info(f"[TEST] No BAMBU_PRINTER_STATES for {printer_name}, proceeding with test")
        else:
            # For non-Bambu printers, check state normally
            allowed_states = ['IDLE', 'READY', 'FINISHED', 'OPERATIONAL']
            if printer_state not in allowed_states:
                return jsonify({
                    'success': False,
                    'error': f'Printer "{printer_name}" is not ready for testing. Current state: {printer_state}. Allowed states: {", ".join(allowed_states)}'
                }), 400
        
        # Count actual G-code commands (excluding comments)
        actual_commands = [line.split(';')[0].strip() for line in gcode.split('\n')]
        actual_commands = [line for line in actual_commands if line]
        command_count = len(actual_commands)
        
        # Check if M400 is in the G-code (causes printer to wait for moves to complete)
        has_m400 = any('M400' in cmd.upper() for cmd in actual_commands)
        has_temp_wait = any(cmd.upper().startswith(('M109', 'M190')) for cmd in actual_commands)
        
        logging.info(f"Testing ejection code '{ejection_code['name']}' on {printer_type} printer {printer_name} ({command_count} commands, M400: {has_m400}, temp_wait: {has_temp_wait})")
        
        # Send the G-code based on printer type
        if printer_type == 'bambu':
            from services.bambu_handler import send_bambu_gcode_command, MQTT_CLIENTS, connect_bambu_printer
            
            # Verify Bambu printer has required fields
            if not printer_copy.get('serial_number'):
                return jsonify({
                    'success': False,
                    'error': f'Bambu printer "{printer_name}" is missing serial number configuration'
                }), 400
            
            # Check/ensure MQTT connection
            if printer_name not in MQTT_CLIENTS or not MQTT_CLIENTS[printer_name].is_connected():
                logging.info(f"Attempting to connect to Bambu printer {printer_name} for test...")
                if not connect_bambu_printer(printer_copy):
                    return jsonify({
                        'success': False,
                        'error': f'Could not establish MQTT connection to Bambu printer {printer_name}'
                    }), 500
            
            # Send with force_reconnect if requested
            success = send_bambu_gcode_command(printer_copy, gcode, force_reconnect=force_reconnect)
            
            if success:
                logging.info(f"Test ejection code '{ejection_code['name']}' sent to Bambu printer {printer_name} ({command_count} commands)")
                
                # Build response message with warnings about blocking commands
                message = f'Ejection code "{ejection_code["name"]}" sent to {printer_name} ({command_count} G-code commands)'
                warnings = []
                if has_m400:
                    warnings.append('M400 detected - printer will wait for moves to complete before accepting new commands')
                if has_temp_wait:
                    warnings.append('Temperature wait commands detected (M109/M190) - may take time to complete')
                
                response = {
                    'success': True,
                    'message': message
                }
                if warnings:
                    response['warnings'] = warnings
                    response['note'] = 'You can send another test immediately - the printer will queue commands'
                
                return jsonify(response)
            else:
                return jsonify({
                    'success': False,
                    'error': f'Failed to send G-code to Bambu printer {printer_name}. Check that the printer is connected and not busy.',
                    'hint': 'Try with force_reconnect: true if MQTT seems stuck'
                }), 500
        else:
            # For Prusa/OctoPrint printers, use HTTP API
            import aiohttp
            import asyncio
            from services.state import decrypt_api_key
            
            async def send_gcode_to_prusa():
                try:
                    headers = {"X-Api-Key": decrypt_api_key(printer_copy.get("api_key", ""))}
                    async with aiohttp.ClientSession() as session:
                        # Send G-code line by line
                        gcode_lines = [line.strip() for line in gcode.strip().split('\n') if line.strip() and not line.strip().startswith(';')]
                        
                        for line in gcode_lines:
                            async with session.post(
                                f"http://{printer_copy['ip']}/api/v1/printer/command",
                                headers=headers,
                                json={"command": line},
                                timeout=10
                            ) as response:
                                if response.status not in [200, 204]:
                                    logging.warning(f"G-code line failed for {printer_name}: {line} (status: {response.status})")
                            
                            # Small delay between commands
                            await asyncio.sleep(0.1)
                        
                        return True
                except Exception as e:
                    logging.error(f"Error sending G-code to Prusa printer {printer_name}: {str(e)}")
                    return False
            
            # Run the async function
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                success = loop.run_until_complete(send_gcode_to_prusa())
            finally:
                loop.close()
            
            if success:
                logging.info(f"Test ejection code '{ejection_code['name']}' sent to Prusa printer {printer_name}")
                return jsonify({
                    'success': True,
                    'message': f'Ejection code "{ejection_code["name"]}" sent to {printer_name}'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': f'Failed to send G-code to printer {printer_name}'
                }), 500
                
    except Exception as e:
        logging.error(f"Error testing ejection code {code_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ejection_codes_bp.route('/test-connection/<printer_name>', methods=['POST'])
def test_printer_connection(printer_name):
    """Test basic G-code connectivity with a simple command
    
    Sends a simple M400 command (wait for moves to finish) to verify
    the printer accepts G-code commands via MQTT.
    """
    try:
        # Find the printer
        printer_copy = None
        with ReadLock(printers_rwlock):
            for printer in PRINTERS:
                if printer['name'] == printer_name:
                    printer_copy = copy.deepcopy(printer)
                    break
        
        if not printer_copy:
            return jsonify({
                'success': False,
                'error': f'Printer "{printer_name}" not found'
            }), 404
        
        printer_type = printer_copy.get('type', 'prusa')
        
        if printer_type != 'bambu':
            return jsonify({
                'success': False,
                'error': 'This test is only for Bambu printers'
            }), 400
        
        from services.bambu_handler import (
            MQTT_CLIENTS, connect_bambu_printer, 
            get_next_sequence_id, BAMBU_PRINTER_STATES, bambu_states_lock
        )
        import paho.mqtt.client as mqtt
        import json
        
        serial_number = printer_copy.get('serial_number', '')
        if not serial_number:
            return jsonify({
                'success': False,
                'error': 'Printer missing serial number'
            }), 400
        
        # Ensure connected
        if printer_name not in MQTT_CLIENTS or not MQTT_CLIENTS[printer_name].is_connected():
            logging.info(f"[CONNECTION_TEST] Connecting to {printer_name}...")
            if not connect_bambu_printer(printer_copy):
                return jsonify({
                    'success': False,
                    'error': 'Could not establish MQTT connection'
                }), 500
            import time
            time.sleep(2)
        
        client = MQTT_CLIENTS[printer_name]
        
        # Get current printer state
        with bambu_states_lock:
            current_state = BAMBU_PRINTER_STATES.get(printer_name, {})
        
        state_info = {
            'connected': client.is_connected(),
            'gcode_state': current_state.get('gcode_state', 'UNKNOWN'),
            'state': current_state.get('state', 'UNKNOWN'),
            'last_seen': current_state.get('last_seen', 0)
        }
        
        # Send a simple test command (M400 - wait for moves to complete)
        topic = f"device/{serial_number}/request"
        seq_id = get_next_sequence_id(printer_name)
        
        test_command = {
            "print": {
                "command": "gcode_line",
                "sequence_id": seq_id,
                "param": "M400"
            }
        }
        
        logging.info(f"[CONNECTION_TEST] Sending M400 to {printer_name} on topic {topic}")
        # Use QoS 0 (fire and forget) to prevent message queuing issues
        result = client.publish(topic, json.dumps(test_command), qos=0)
        
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            return jsonify({
                'success': False,
                'error': f'MQTT publish failed with rc={result.rc}',
                'state_info': state_info
            }), 500
        
        logging.info(f"[CONNECTION_TEST] M400 sent successfully to {printer_name}")
        
        return jsonify({
            'success': True,
            'message': f'Test command (M400) sent to {printer_name}. Check API logs for [GCODE_RESPONSE] messages.',
            'state_info': state_info,
            'topic': topic,
            'sequence_id': seq_id
        })
        
    except Exception as e:
        logging.error(f"[CONNECTION_TEST] Error: {str(e)}")
        import traceback
        logging.error(f"[CONNECTION_TEST] Traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ejection_codes_bp.route('/reset-ejection-state/<printer_name>', methods=['POST'])
def reset_ejection_state(printer_name):
    """Reset ejection state for a specific printer (for debugging)
    
    Clears any stuck ejection flags that might be preventing repeated ejection tests.
    
    Optional JSON body:
    - reconnect: If true, also force reconnect the MQTT client
    """
    try:
        from services.bambu_handler import BAMBU_PRINTER_STATES, bambu_states_lock, MQTT_CLIENTS, connect_bambu_printer
        
        # Check if reconnect is requested
        data = request.get_json() or {}
        should_reconnect = data.get('reconnect', False)
        
        # Find the printer
        printer_copy = None
        with ReadLock(printers_rwlock):
            for printer in PRINTERS:
                if printer['name'] == printer_name:
                    printer_copy = copy.deepcopy(printer)
                    break
        
        if not printer_copy:
            return jsonify({
                'success': False,
                'error': f'Printer "{printer_name}" not found'
            }), 404
        
        cleared_flags = []
        
        # Force reconnect MQTT if requested
        if should_reconnect and printer_copy.get('type') == 'bambu':
            logging.info(f"Force reconnecting MQTT for {printer_name}...")
            if printer_name in MQTT_CLIENTS:
                try:
                    old_client = MQTT_CLIENTS[printer_name]
                    old_client.loop_stop()
                    old_client.disconnect()
                except Exception as e:
                    logging.warning(f"Error disconnecting: {e}")
                del MQTT_CLIENTS[printer_name]
                cleared_flags.append('mqtt_client (disconnected)')
            
            time.sleep(1)
            
            if connect_bambu_printer(printer_copy):
                cleared_flags.append('mqtt_client (reconnected)')
            else:
                cleared_flags.append('mqtt_client (reconnect FAILED)')
        
        with bambu_states_lock:
            if printer_name in BAMBU_PRINTER_STATES:
                state = BAMBU_PRINTER_STATES[printer_name]
                
                # Clear ejection in progress flag
                if state.get('ejection_in_progress', False):
                    state['ejection_in_progress'] = False
                    cleared_flags.append('ejection_in_progress')
                
                # Clear last ejection time (removes cooldown)
                if state.get('last_ejection_time'):
                    old_time = state['last_ejection_time']
                    state['last_ejection_time'] = 0
                    cleared_flags.append(f'last_ejection_time (was {time.time() - old_time:.1f}s ago)')
                
                # Clear waiting for M400 flag
                if state.get('waiting_for_m400', False):
                    state['waiting_for_m400'] = False
                    cleared_flags.append('waiting_for_m400')
                
                # Clear ejection start time
                if state.get('ejection_start_time'):
                    state['ejection_start_time'] = None
                    cleared_flags.append('ejection_start_time')
                
                # If state is EJECTING, set to READY
                if state.get('state') == 'EJECTING':
                    state['state'] = 'READY'
                    cleared_flags.append('state (EJECTING -> READY)')
                
                logging.info(f"Reset ejection state for {printer_name}: {cleared_flags}")
            else:
                if not cleared_flags:
                    return jsonify({
                        'success': True,
                        'message': f'No ejection state found for {printer_name} (nothing to reset)',
                        'cleared_flags': []
                    })
        
        return jsonify({
            'success': True,
            'message': f'Ejection state reset for {printer_name}',
            'cleared_flags': cleared_flags
        })
        
    except Exception as e:
        logging.error(f"Error resetting ejection state for {printer_name}: {str(e)}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ejection_codes_bp.route('/debug-state/<printer_name>', methods=['GET'])
def debug_ejection_state(printer_name):
    """Get current ejection state for debugging"""
    try:
        from services.bambu_handler import BAMBU_PRINTER_STATES, bambu_states_lock
        
        with bambu_states_lock:
            if printer_name in BAMBU_PRINTER_STATES:
                state = BAMBU_PRINTER_STATES[printer_name].copy()
                
                # Calculate time since last ejection
                if state.get('last_ejection_time'):
                    state['seconds_since_last_ejection'] = time.time() - state['last_ejection_time']
                
                # Calculate ejection duration if in progress
                if state.get('ejection_start_time'):
                    state['ejection_duration_seconds'] = time.time() - state['ejection_start_time']
                
                return jsonify({
                    'success': True,
                    'printer_name': printer_name,
                    'state': state
                })
            else:
                return jsonify({
                    'success': True,
                    'printer_name': printer_name,
                    'state': None,
                    'message': 'No state found for this printer'
                })
                
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ejection_codes_bp.route('/upload', methods=['POST'])
def upload_ejection_code():
    """Upload a G-code file to create a new ejection code preset
    
    Expects multipart form with:
    - name: Name for the ejection code
    - file: The G-code file to upload
    """
    try:
        name = request.form.get('name', '').strip()
        file = request.files.get('file')
        
        if not name:
            return jsonify({
                'success': False,
                'error': 'Name is required'
            }), 400
        
        if not file:
            return jsonify({
                'success': False,
                'error': 'File is required'
            }), 400
        
        # Validate file
        valid, message = validate_ejection_file(file)
        if not valid:
            return jsonify({
                'success': False,
                'error': message
            }), 400
        
        # Read file contents
        try:
            gcode = file.read().decode('utf-8')
        except UnicodeDecodeError:
            return jsonify({
                'success': False,
                'error': 'File must be a valid text/G-code file'
            }), 400
        
        # Check for duplicate names
        with SafeLock(ejection_codes_lock):
            for existing in EJECTION_CODES:
                if existing['name'].lower() == name.lower():
                    return jsonify({
                        'success': False,
                        'error': f'An ejection code named "{name}" already exists'
                    }), 400
            
            # Create new ejection code
            new_code = {
                'id': str(uuid.uuid4()),
                'name': name,
                'gcode': gcode,
                'source_filename': secure_filename(file.filename),
                'created_at': datetime.now().isoformat()
            }
            
            EJECTION_CODES.append(new_code)
            save_data(EJECTION_CODES_FILE, EJECTION_CODES)
            
            logging.info(f"Uploaded new ejection code: {name} from {file.filename}")
        
        return jsonify({
            'success': True,
            'ejection_code': new_code,
            'message': f'Ejection code "{name}" uploaded successfully'
        }), 201
        
    except Exception as e:
        logging.error(f"Error uploading ejection code: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
