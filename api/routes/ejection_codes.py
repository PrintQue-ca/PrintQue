"""
Ejection Codes API Routes

Provides CRUD operations for managing ejection code presets.
Users can upload, store, and select ejection codes to use for auto-ejection after prints.
"""

import os
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from services.state import (
    EJECTION_CODES, EJECTION_CODES_FILE,
    save_data, SafeLock, logging,
    ejection_codes_lock, validate_ejection_file
)

ejection_codes_bp = Blueprint('ejection_codes', __name__)

def register_ejection_codes_routes(app, socketio):
    """Register ejection codes routes with the app"""
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
