from flask import render_template, request, redirect, url_for, flash, jsonify, make_response, current_app
from services.state import (
    ReadLock, WriteLock, SafeLock, printers_rwlock, PRINTERS, 
    orders_lock, ORDERS, filament_lock, TOTAL_FILAMENT_CONSUMPTION,
    save_data, load_data, PRINTERS_FILE, ORDERS_FILE, TOTAL_FILAMENT_FILE,
    sanitize_group_name
)
from services.default_settings import load_default_settings
import os
import uuid
import logging
from datetime import datetime
import csv
import io
from services.printer_manager import start_background_distribution, extract_filament_from_file
from werkzeug.utils import secure_filename
import shutil


def register_misc_routes(app, socketio):
    """Register miscellaneous routes for the Flask app"""
    
    @app.route("/")
    def index():
        """Main dashboard page - serves React frontend or legacy templates"""
        import sys
        from flask import send_file
        
        # Determine base directory for packaged vs development mode
        if getattr(sys, 'frozen', False):
            base_dir = sys._MEIPASS
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Check if React frontend exists (packaged build)
        frontend_folder = os.path.join(base_dir, 'frontend_dist')
        if os.path.exists(frontend_folder):
            # Serve React frontend - try index.html or _shell.html (TanStack)
            for html_file in ['index.html', '_shell.html']:
                html_path = os.path.join(frontend_folder, html_file)
                if os.path.exists(html_path):
                    return send_file(html_path)
        
        # Fallback to legacy template rendering
        # Get filament data
        with SafeLock(filament_lock):
            filament_data = load_data(TOTAL_FILAMENT_FILE, {"total_filament_used_g": 0})
            total_filament_kg = filament_data.get("total_filament_used_g", 0) / 1000
        
        # Get active orders
        with SafeLock(orders_lock):
            active_orders = [o for o in ORDERS if not o.get('deleted', False)]
            logging.debug(f"Rendering index. Printers: {len(PRINTERS)}, Active orders: {len(active_orders)}, Total orders: {len(ORDERS)}, Loaded TOTAL_FILAMENT_CONSUMPTION: {TOTAL_FILAMENT_CONSUMPTION}")
        
        # Get printer groups
        with ReadLock(printers_rwlock):
            groups = sorted(set(str(p.get('group', 'Default')) for p in PRINTERS)) if PRINTERS else ['Default']
        
        # Load default settings for the template
        default_settings = load_default_settings()
        default_end_gcode = default_settings.get('default_end_gcode', '')
        default_ejection_enabled = default_settings.get('default_ejection_enabled', False)
        
        # Get license information
        license_tier = app.config.get('LICENSE_TIER', 'free')
        license_valid = app.config.get('LICENSE_VALID', False)
        max_printers = app.config.get('MAX_PRINTERS', 3)
        
        # Count printers to show limit usage
        with ReadLock(printers_rwlock):
            printer_count = len(PRINTERS)
        
        return render_template("index.html", 
                              printers=PRINTERS, 
                              total_filament=total_filament_kg,
                              total_filament_consumption=total_filament_kg,
                              orders=active_orders, 
                              default_end_gcode=default_end_gcode,
                              default_ejection_enabled=default_ejection_enabled,
                              last_refresh=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                              total_printers=len(PRINTERS),
                              groups=groups,
                              license_tier=license_tier,
                              license_valid=license_valid,
                              max_printers=max_printers,
                              printer_count=printer_count)

    @app.route("/printers")
    def printers():
        """Printers management page"""
        # Get license information
        license_tier = app.config.get('LICENSE_TIER', 'free')
        license_valid = app.config.get('LICENSE_VALID', False)
        max_printers = app.config.get('MAX_PRINTERS', 3)
        
        with ReadLock(printers_rwlock):
            printer_count = len(PRINTERS)
        
        return render_template("printers.html",
                              printers=PRINTERS,
                              license_tier=license_tier,
                              license_valid=license_valid,
                              max_printers=max_printers,
                              printer_count=printer_count)

    @app.route("/stats")
    def stats():
        """Statistics page"""
        with SafeLock(filament_lock):
            filament_data = load_data(TOTAL_FILAMENT_FILE, {"total_filament_used_g": 0})
            total_filament_kg = filament_data.get("total_filament_used_g", 0) / 1000
        
        with ReadLock(printers_rwlock):
            printer_stats = {
                'total': len(PRINTERS),
                'online': len([p for p in PRINTERS if p['state'] != 'OFFLINE']),
                'printing': len([p for p in PRINTERS if p['state'] == 'PRINTING']),
                'ready': len([p for p in PRINTERS if p['state'] == 'READY'])
            }
        
        with SafeLock(orders_lock):
            order_stats = {
                'total': len(ORDERS),
                'active': len([o for o in ORDERS if not o.get('deleted', False)]),
                'fulfilled': len([o for o in ORDERS if o.get('status') == 'fulfilled']),
                'deleted': len([o for o in ORDERS if o.get('deleted', False)])
            }
        
        return render_template("stats.html",
                              printer_stats=printer_stats,
                              order_stats=order_stats,
                              total_filament=total_filament_kg)

    @app.route("/bulk_upload")
    def bulk_upload():
        """Render the bulk upload page"""
        # Get license information for any restrictions
        license_tier = app.config.get('LICENSE_TIER', 'free')
        license_valid = app.config.get('LICENSE_VALID', False)
        max_printers = app.config.get('MAX_PRINTERS', 3)
        
        # Get available printer groups
        groups = None
        with ReadLock(printers_rwlock):
            groups = sorted(set(str(p.get('group', 'Default')) for p in PRINTERS)) if PRINTERS else ['Default']
        
        return render_template("bulk_upload.html", 
                              license_tier=license_tier,
                              license_valid=license_valid,
                              max_printers=max_printers,
                              available_groups=groups)

    @app.route('/clear_all_data', methods=['POST'])
    def clear_all_data():
        """Clear all application data"""
        try:
            # Clear in-memory data
            with WriteLock(printers_rwlock):
                PRINTERS.clear()
                save_data(PRINTERS_FILE, PRINTERS)
            
            with SafeLock(orders_lock, 'clear_all_data'):
                ORDERS.clear()
                save_data(ORDERS_FILE, ORDERS)
            
            with SafeLock(filament_lock, 'clear_all_data'):
                global TOTAL_FILAMENT_CONSUMPTION
                TOTAL_FILAMENT_CONSUMPTION = 0
                save_data(TOTAL_FILAMENT_FILE, {"total_filament_used_g": TOTAL_FILAMENT_CONSUMPTION})
            
            flash("All data cleared successfully")
            return redirect(url_for('index'))
        except Exception as e:
            logging.error(f"Error clearing data: {str(e)}")
            flash(f"Error clearing data: {str(e)}")
            return redirect(url_for('index'))

    @app.route('/distribute', methods=['POST'])
    def distribute():
        """Manually trigger order distribution"""
        try:
            task_id = start_background_distribution(socketio)
            return jsonify({
                'success': True,
                'task_id': task_id,
                'message': 'Distribution started'
            })
        except Exception as e:
            logging.error(f"Error starting distribution: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/export_orders', methods=['GET'])
    def export_orders():
        """Export orders to CSV"""
        try:
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write headers
            writer.writerow(['ID', 'Name', 'Filename', 'Quantity', 'Sent', 'Groups', 'Status', 'Created At'])
            
            # Write order data
            with SafeLock(orders_lock, 'export_orders'):
                for order in ORDERS:
                    writer.writerow([
                        order['id'],
                        order.get('name', ''),
                        order['filename'],
                        order['quantity'],
                        order.get('sent', 0),
                        ', '.join(order.get('groups', [])),
                        order.get('status', 'pending'),
                        order.get('created_at', '')
                    ])
            
            # Create response
            output.seek(0)
            response = make_response(output.getvalue())
            response.headers["Content-Disposition"] = f"attachment; filename=orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            response.headers["Content-type"] = "text/csv"
            
            return response
        except Exception as e:
            logging.error(f"Error exporting orders: {str(e)}")
            flash(f"Error exporting orders: {str(e)}")
            return redirect(url_for('index'))

    @app.route('/system-info')
    def system_info():
        """Display system information including Machine ID"""
        from utils.license_validator import get_machine_id
        import platform
        
        info = {
            'machine_id': get_machine_id(),
            'hostname': platform.node(),
            'system': platform.system(),
            'release': platform.release(),
            'processor': platform.processor()
        }
        
        return render_template('system_info.html', info=info)
    
    @app.route('/api/bulk_print', methods=['POST'])
    def api_bulk_print():
        """API endpoint for bulk print job submission"""
        try:
            data = request.get_json()
            
            if not data or 'jobs' not in data:
                return jsonify({'error': 'No print jobs provided'}), 400
            
            jobs = data['jobs']
            if not isinstance(jobs, list):
                return jsonify({'error': 'Jobs must be an array'}), 400
            
            # Get license limits
            license_tier = current_app.config.get('LICENSE_TIER', 'free')
            max_jobs = get_max_jobs_per_batch(license_tier)
            
            if len(jobs) > max_jobs:
                return jsonify({
                    'error': f'Too many jobs. Your {license_tier} tier allows up to {max_jobs} jobs per batch.'
                }), 403
            
            # Process jobs
            queued_count = 0
            failed_jobs = []
            
            # Get available printer groups
            with ReadLock(printers_rwlock):
                available_groups = list(set(p.get('group', 'Default') for p in PRINTERS))
            
            for job in jobs:
                try:
                    # Validate job data
                    if 'filename' not in job or 'quantity' not in job:
                        failed_jobs.append(f"Invalid job data: missing filename or quantity")
                        continue
                    
                    # Validate printer groups if specified
                    if 'printer_groups' in job:
                        # Handle both string and list formats
                        if isinstance(job['printer_groups'], str):
                            requested_groups = [g.strip() for g in job['printer_groups'].split(',')]
                        elif isinstance(job['printer_groups'], list):
                            requested_groups = job['printer_groups']
                        else:
                            requested_groups = ['Default']
                        
                        # Validate groups exist or use Default
                        valid_groups = []
                        for group in requested_groups:
                            group = sanitize_group_name(group)
                            if group in available_groups:
                                valid_groups.append(group)
                            else:
                                # Fallback to Default group for invalid groups
                                if 'Default' not in valid_groups and ('Default' in available_groups or len(PRINTERS) == 0):
                                    valid_groups.append('Default')
                        
                        if not valid_groups:
                            valid_groups = ['Default']  # Default fallback
                        
                        job['printer_groups'] = valid_groups
                    
                    # Create the print job using existing order creation logic
                    success = create_bulk_print_job(job)
                    if success:
                        queued_count += 1
                    else:
                        failed_jobs.append(f"Failed to queue {job['filename']}")
                        
                except Exception as e:
                    failed_jobs.append(f"Error processing {job.get('filename', 'unknown')}: {str(e)}")
            
            # Prepare response
            response_data = {
                'queued_count': queued_count,
                'total_jobs': len(jobs),
                'failed_count': len(failed_jobs)
            }
            
            if failed_jobs:
                response_data['failures'] = failed_jobs
                
            # Return success if at least some jobs were queued
            if queued_count > 0:
                return jsonify(response_data), 200
            else:
                return jsonify(response_data), 400
                
        except Exception as e:
            logging.error(f"Error in bulk print jobs API: {str(e)}")
            return f"Internal server error: {str(e)}", 500

    @app.route("/api/bulk_print_jobs", methods=['POST'])
    def api_bulk_print_jobs():
        """API endpoint to process bulk print jobs from CSV data"""
        try:
            data = request.get_json()
            if not data or 'jobs' not in data:
                return "Missing jobs data", 400
            
            jobs = data['jobs']
            if not isinstance(jobs, list) or len(jobs) == 0:
                return "No jobs provided", 400
            
            # Validate license limits (if applicable)
            license_tier = app.config.get('LICENSE_TIER', 'free')
            max_jobs_per_batch = get_max_jobs_per_batch(license_tier)
            
            if len(jobs) > max_jobs_per_batch:
                return f"Batch size ({len(jobs)}) exceeds license limit ({max_jobs_per_batch})", 400
            
            # Sort jobs by their order_index to maintain CSV row order
            jobs.sort(key=lambda x: x.get('order_index', 0))
            
            # Process each job
            queued_count = 0
            failed_jobs = []
            
            for job in jobs:
                try:
                    # Validate required fields
                    required_fields = ['full_path', 'filename', 'printer_groups']
                    if not all(field in job for field in required_fields):
                        failed_jobs.append(f"Missing required fields for {job.get('filename', 'unknown')}")
                        continue
                    
                    # FIX: Normalize the file path to use proper OS path separators
                    job['full_path'] = os.path.normpath(job['full_path'])
                    
                    # Validate file exists
                    if not os.path.exists(job['full_path']):
                        failed_jobs.append(f"File not found: {job['full_path']}")
                        continue
                    
                    # Validate ejection file if specified
                    ejection_enabled = False
                    ejection_gcode = ''
                    
                    if job.get('ejection_enabled') and job.get('ejection_path'):
                        # FIX: Normalize the ejection path as well
                        job['ejection_path'] = os.path.normpath(job['ejection_path'])
                        
                        if not os.path.exists(job['ejection_path']):
                            logging.warning(f"Ejection file not found: {job['ejection_path']} - disabling ejection for {job.get('filename', 'unknown')}")
                            # Don't fail the job, just disable ejection
                            ejection_enabled = False
                        else:
                            # Read ejection G-code from file
                            try:
                                with open(job['ejection_path'], 'r', encoding='utf-8') as f:
                                    ejection_gcode = f.read().strip()
                                    ejection_enabled = True
                                    logging.info(f"Loaded ejection G-code from {job['ejection_path']} for {job.get('filename', 'unknown')}")
                            except Exception as e:
                                logging.warning(f"Error reading ejection file {job['ejection_path']}: {str(e)} - disabling ejection for {job.get('filename', 'unknown')}")
                                # Don't fail the job, just disable ejection
                                ejection_enabled = False
                                ejection_gcode = ''
                    
                    # Store ejection settings in job data
                    job['ejection_enabled'] = ejection_enabled
                    job['ejection_gcode'] = ejection_gcode
                    
                    # Validate printer groups exist
                    with ReadLock(printers_rwlock):
                        available_groups = [p['group'] for p in PRINTERS]
                        valid_groups = []
                        
                        for group in job['printer_groups']:
                            if group in available_groups or len(PRINTERS) == 0:
                                valid_groups.append(group)
                            else:
                                # Fallback to Default group for invalid groups
                                if 'Default' not in valid_groups and ('Default' in available_groups or len(PRINTERS) == 0):
                                    valid_groups.append('Default')
                        
                        if not valid_groups:
                            valid_groups = ['Default']  # Default fallback
                        
                        job['printer_groups'] = valid_groups
                    
                    # Create the print job using existing order creation logic
                    success = create_bulk_print_job(job)
                    if success:
                        queued_count += 1
                    else:
                        failed_jobs.append(f"Failed to queue {job['filename']}")
                        
                except Exception as e:
                    failed_jobs.append(f"Error processing {job.get('filename', 'unknown')}: {str(e)}")
            
            # Prepare response
            response_data = {
                'queued_count': queued_count,
                'total_jobs': len(jobs),
                'failed_count': len(failed_jobs)
            }
            
            if failed_jobs:
                response_data['failures'] = failed_jobs
                
            # Return success if at least some jobs were queued
            if queued_count > 0:
                return jsonify(response_data), 200
            else:
                return jsonify(response_data), 400
                
        except Exception as e:
            logging.error(f"Error in bulk print jobs API: {str(e)}")
            return f"Internal server error: {str(e)}", 500

    # Add update_group_by_name route if it doesn't exist
    @app.route('/update_group_by_name/<group_name>', methods=['POST'])
    def update_group_by_name(group_name):
        """Update the group name for all printers in a specific group"""
        new_group = sanitize_group_name(request.form.get('new_group', 'Default'))
        
        if not new_group:
            flash("Invalid group name")
            return redirect(url_for('index'))
        
        # Update all printers in the old group to the new group
        with WriteLock(printers_rwlock):
            updated_count = 0
            for printer in PRINTERS:
                if printer.get('group') == group_name:
                    printer['group'] = new_group
                    updated_count += 1
            
            if updated_count > 0:
                save_data(PRINTERS_FILE, PRINTERS)
                flash(f"Updated {updated_count} printers from group '{group_name}' to '{new_group}'")
            else:
                flash(f"No printers found in group '{group_name}'")
        
        return redirect(url_for('index'))

    # NEW ROUTE: Update individual printer
    @app.route('/update_printer', methods=['POST'])
    def update_printer():
        """Update individual printer name and group"""
        printer_name = request.form.get('printer_name')
        new_name = request.form.get('new_name', '').strip()
        new_group = sanitize_group_name(request.form.get('new_group', 'Default'))
        
        if not printer_name:
            flash("Printer name not provided")
            return redirect(url_for('index'))
        
        if not new_name:
            flash("New printer name cannot be empty")
            return redirect(url_for('index'))
        
        # Check if new name would create a duplicate
        with ReadLock(printers_rwlock):
            if new_name != printer_name and any(p['name'] == new_name for p in PRINTERS):
                flash(f"A printer named '{new_name}' already exists")
                return redirect(url_for('index'))
        
        # Update the printer
        with WriteLock(printers_rwlock):
            updated = False
            for printer in PRINTERS:
                if printer['name'] == printer_name:
                    printer['name'] = new_name
                    printer['group'] = new_group
                    updated = True
                    break
            
            if updated:
                save_data(PRINTERS_FILE, PRINTERS)
                flash(f"Printer updated successfully")
            else:
                flash(f"Printer '{printer_name}' not found")
        
        return redirect(url_for('index'))

    # REMOVED THE CONFLICTING mark_group_ready ROUTE!
    # The correct implementation is in printer_routes.py
    
    @app.route('/submit_bulk_orders', methods=['POST'])
    def submit_bulk_orders():
        """Process bulk order uploads from CSV with support for extra data columns"""
        try:
            data = request.get_json()
            jobs = data.get('jobs', [])
            
            if not jobs:
                return jsonify({'success': False, 'error': 'No jobs provided'}), 400
            
            successful_orders = []
            failed_orders = []
            
            # Process each job from the CSV
            for job_index, job in enumerate(jobs):
                try:
                    # Construct the full path
                    folder_path = job.get('folder_path', '').strip()
                    filename = job.get('filename', '').strip()
                    
                    if not folder_path or not filename:
                        failed_orders.append({
                            'row': job.get('source_row', job_index + 1),
                            'error': 'Missing folder_path or filename'
                        })
                        continue
                    
                    # Build the full file path
                    if os.name == 'nt':  # Windows
                        full_path = os.path.join(folder_path, filename)
                    else:  # Unix/Linux
                        full_path = os.path.join(folder_path, filename)
                    
                    # Validate file exists
                    if not os.path.exists(full_path):
                        failed_orders.append({
                            'row': job.get('source_row', job_index + 1),
                            'error': f'File not found: {full_path}'
                        })
                        continue
                    
                    # Validate file type
                    if not any(filename.lower().endswith(ext) for ext in ['.gcode', '.bgcode', '.3mf', '.gcode.3mf', '.stl']):
                        failed_orders.append({
                            'row': job.get('source_row', job_index + 1),
                            'error': f'Invalid file type: {filename}'
                        })
                        continue
                    
                    # Copy file to upload directory
                    upload_filename = secure_filename(filename)
                    upload_path = os.path.join(app.config['UPLOAD_FOLDER'], upload_filename)
                    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                    
                    try:
                        shutil.copy2(full_path, upload_path)
                    except Exception as e:
                        failed_orders.append({
                            'row': job.get('source_row', job_index + 1),
                            'error': f'Failed to copy file: {str(e)}'
                        })
                        continue
                    
                    # Extract filament usage
                    filament_g = extract_filament_from_file(upload_path)
                    
                    # Process ejection settings
                    ejection_enabled = job.get('ejection_enabled', False)
                    end_gcode = ''
                    
                    if ejection_enabled:
                        ejection_path = job.get('ejection_path')
                        if ejection_path and os.path.exists(ejection_path):
                            try:
                                with open(ejection_path, 'r') as f:
                                    end_gcode = f.read()
                            except:
                                ejection_enabled = False
                        else:
                            # Use default if no custom ejection file
                            default_settings = load_default_settings()
                            end_gcode = default_settings.get('default_end_gcode', '')
                    
                    # Extract extra data columns (up to 20 or more)
                    extra_data = job.get('extra_data', {})
                    
                    # Validate extra data doesn't have too many columns (optional limit)
                    if len(extra_data) > 20:
                        # You can either truncate or warn
                        logging.warning(f"Job has {len(extra_data)} extra columns, limiting to 20")
                        # Optionally limit to first 20 keys
                        extra_data = dict(list(extra_data.items())[:20])
                    
                    # Generate order ID
                    with SafeLock(orders_lock):
                        existing_int_ids = []
                        for order in ORDERS:
                            try:
                                int_id = int(order['id'])
                                existing_int_ids.append(int_id)
                            except (ValueError, TypeError):
                                pass
                        
                        order_id = max(existing_int_ids, default=0) + 1
                        
                        # Create the order with extra data
                        order = {
                            'id': order_id,
                            'filename': upload_filename,
                            'filepath': upload_path,
                            'quantity': job.get('quantity', 1),
                            'sent': 0,
                            'status': 'pending',
                            'filament_g': filament_g,
                            'groups': job.get('printer_groups', ['Default']),
                            'ejection_enabled': ejection_enabled,
                            'end_gcode': end_gcode,
                            'extra_data': extra_data,  # Store all extra columns
                            'source': 'csv_upload',
                            'created_at': datetime.now().isoformat(),
                            'from_new_orders': True
                        }
                        
                        ORDERS.append(order)
                        successful_orders.append({
                            'row': job.get('source_row', job_index + 1),
                            'order_id': order_id,
                            'filename': upload_filename
                        })
                
                except Exception as e:
                    failed_orders.append({
                        'row': job.get('source_row', job_index + 1),
                        'error': str(e)
                    })
            
            # Save all orders
            with SafeLock(orders_lock):
                save_data(ORDERS_FILE, ORDERS)
            
            # Trigger distribution
            if successful_orders:
                start_background_distribution(socketio, app)
            
            return jsonify({
                'success': True,
                'successful_count': len(successful_orders),
                'failed_count': len(failed_orders),
                'successful_orders': successful_orders,
                'failed_orders': failed_orders
            })
            
        except Exception as e:
            logging.error(f"Error in submit_bulk_orders: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

def get_max_jobs_per_batch(license_tier):
    """Get maximum jobs per batch based on license tier"""
    limits = {
        'free': 50,
        'standard': 200,
        'professional': 500,
        'enterprise': 1000
    }
    return limits.get(license_tier.lower(), 50)

def create_bulk_print_job(job_data):
    """Create a print job from API data or bulk upload data"""
    try:
        with SafeLock(orders_lock, 'create_bulk_print_job'):
            # Determine the source and structure of job_data
            if 'full_path' in job_data:  # Bulk upload format
                # Safe way to get the next order ID
                if not ORDERS:
                    # If no orders exist, start with ID 1
                    order_id = 1
                else:
                    # Get all numeric IDs
                    numeric_ids = []
                    for order in ORDERS:
                        order_id_val = order.get('id')
                        if isinstance(order_id_val, int):
                            numeric_ids.append(order_id_val)
                        elif isinstance(order_id_val, str) and order_id_val.isdigit():
                            numeric_ids.append(int(order_id_val))
                    
                    # Get the next ID
                    if numeric_ids:
                        order_id = max(numeric_ids) + 1
                    else:
                        order_id = 1
                
                ejection_enabled = job_data.get('ejection_enabled', False)
                ejection_gcode = job_data.get('ejection_gcode', '') if ejection_enabled else ''
                
                new_order = {
                    'id': order_id,
                    'filepath': job_data['full_path'],
                    'filename': job_data['filename'],
                    'printer_group': job_data['printer_groups'][0] if job_data.get('printer_groups') else 'Default',
                    'groups': job_data.get('printer_groups', ['Default']),
                    'priority': 'normal',
                    'quantity': int(job_data.get('quantity', 1)),
                    'sent': 0,
                    'status': 'pending',
                    'created_at': datetime.now().isoformat(),
                    'attempts': 0,
                    'max_attempts': 3,
                    'source': 'bulk_upload',
                    'filament_g': 0,
                    'deleted': False,
                    'order_index': job_data.get('order_index', 0),
                    'ejection_enabled': ejection_enabled,
                    'end_gcode': ejection_gcode
                }
            else:  # API format
                # Safe way to get the next order ID for API format
                if not ORDERS:
                    order_id = 1
                else:
                    numeric_ids = []
                    for order in ORDERS:
                        order_id_val = order.get('id')
                        if isinstance(order_id_val, int):
                            numeric_ids.append(order_id_val)
                        elif isinstance(order_id_val, str) and order_id_val.isdigit():
                            numeric_ids.append(int(order_id_val))
                    
                    if numeric_ids:
                        order_id = max(numeric_ids) + 1
                    else:
                        order_id = 1
                
                new_order = {
                    'id': order_id,
                    'filename': job_data.get('filename', 'Unknown'),
                    'quantity': int(job_data.get('quantity', 1)),
                    'sent': 0,
                    'groups': job_data.get('printer_groups', ['Default']),
                    'status': 'pending',
                    'created_at': datetime.now().isoformat(),
                    'ejection_enabled': job_data.get('ejection_enabled', True),
                    'source': 'api'
                }
            
            ORDERS.append(new_order)
            save_data(ORDERS_FILE, ORDERS)
            
            return True
    except Exception as e:
        logging.error(f"Error creating bulk print job: {str(e)}")
        logging.error(f"Job data: {job_data}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")
        return False