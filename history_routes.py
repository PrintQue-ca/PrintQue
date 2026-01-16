from flask import render_template, jsonify, request
from datetime import datetime, timedelta
import os
import json
import logging
import uuid
from state import ORDERS, SafeLock, orders_lock, load_data
import traceback

def register_history_routes(app, socketio):
    """Register print history related routes"""

    @app.route('/print_history')
    def print_history():
        """Render the print history page"""
        return render_template('print_history.html')

    @app.route('/api/print_history')
    def api_print_history():
        """API endpoint to get print history data including active orders"""
        try:
            # Get LOG_DIR from app config - this was the main issue!
            log_dir = app.config.get('LOG_DIR')
            if not log_dir:
                # Fallback to default location
                log_dir = os.path.join(os.path.expanduser("~"), "PrintQueData")
                logging.warning(f"LOG_DIR not found in app config, using fallback: {log_dir}")
            
            # Use direct path to history file (not nested in 'logs' subfolder)
            history_file = os.path.join(log_dir, 'print_history.json')
            history_data = []

            # Debug logging to help troubleshoot
            logging.info(f"Looking for print history file at: {history_file}")
            logging.info(f"History file exists: {os.path.exists(history_file)}")
            logging.info(f"Log directory exists: {os.path.exists(log_dir)}")

            # Try to load existing history
            if os.path.exists(history_file):
                try:
                    with open(history_file, 'r', encoding='utf-8') as f:
                        line_count = 0
                        for line in f:
                            line = line.strip()
                            if line:  # Skip empty lines
                                try:
                                    entry = json.loads(line)
                                    entry['is_active'] = False  # Mark as historical
                                    # Ensure extra_data exists
                                    if 'extra_data' not in entry:
                                        entry['extra_data'] = {}
                                    # Ensure required fields exist with defaults
                                    entry.setdefault('groups', [])
                                    entry.setdefault('quantity', 1)
                                    entry.setdefault('filament_g', 0)
                                    entry.setdefault('sent', entry.get('quantity', 1))  # Default sent to quantity for completed orders
                                    history_data.append(entry)
                                    line_count += 1
                                except json.JSONDecodeError as e:
                                    logging.warning(f"Failed to parse history line: {line[:100]}... Error: {e}")
                                    continue
                        logging.info(f"Successfully loaded {line_count} entries from history file")
                except Exception as e:
                    logging.error(f"Error reading history file: {e}")
            else:
                logging.info("No history file found - starting with empty history")
            
            # Get all orders (both active and completed) from current state
            with SafeLock(orders_lock):
                active_order_count = 0
                logging.info(f"Processing {len(ORDERS)} orders from current state")
                
                for order in ORDERS:
                    if not order.get('deleted', False):  # Include all non-deleted orders
                        active_order_count += 1
                        
                        # Calculate duration if we have timestamps
                        duration = None
                        if 'created_at' in order and order['created_at']:
                            try:
                                # Handle different datetime formats
                                created_str = order['created_at']
                                if created_str.endswith('Z'):
                                    created_str = created_str.replace('Z', '+00:00')
                                created = datetime.fromisoformat(created_str)
                                
                                if order.get('completed_at'):
                                    completed_str = order['completed_at']
                                    if completed_str.endswith('Z'):
                                        completed_str = completed_str.replace('Z', '+00:00')
                                    completed = datetime.fromisoformat(completed_str)
                                    duration = (completed - created).total_seconds()
                                else:
                                    # For active orders, calculate current duration
                                    current_time = datetime.now()
                                    if created.tzinfo:
                                        from datetime import timezone
                                        current_time = current_time.replace(tzinfo=timezone.utc)
                                    duration = (current_time - created).total_seconds()
                            except (ValueError, TypeError) as e:
                                logging.warning(f"Error calculating duration for order {order.get('id')}: {e}")
                                duration = None

                        # Determine if this is truly "completed" (fulfilled AND deleted)
                        # or just "fulfilled" (quantity met but still active)
                        is_fulfilled = order.get('quantity', 0) <= order.get('sent', 0)
                        is_deleted = order.get('deleted', False)
                        is_truly_completed = is_fulfilled and is_deleted

                        history_item = {
                            'id': order.get('id', str(uuid.uuid4())),
                            'filename': order.get('filename', 'Unknown'),
                            'quantity': order.get('quantity', 0),
                            'sent': order.get('sent', 0),
                            'groups': order.get('groups', order.get('printer_group', ['Unknown'])),
                            'filament_g': order.get('filament_g', 0),
                            'ejection_enabled': order.get('ejection_enabled', False),
                            'source': order.get('source', 'unknown'),
                            'extra_data': order.get('extra_data', {}),
                            'created_at': order.get('created_at'),
                            'completed_at': order.get('completed_at'),  # Will be set when quantity is reached
                            'duration_seconds': duration,
                            'status': order.get('status', 'pending'),
                            'is_active': not is_truly_completed  # Active unless both fulfilled AND deleted
                        }

                        # Ensure groups is a list
                        if isinstance(history_item['groups'], str):
                            history_item['groups'] = [history_item['groups']]
                        elif not history_item['groups']:  # Handle empty/None groups
                            history_item['groups'] = ['Unknown']

                        # Check if this order is already in history_data from file
                        existing_entry = next((h for h in history_data if h.get('id') == order.get('id') and not h.get('is_active')), None)
                        if not existing_entry:
                            history_data.append(history_item)
                            
                            # If it's truly completed (fulfilled and deleted), save to history file
                            if is_truly_completed:
                                try:
                                    save_completed_order_to_history(order, history_file)
                                except Exception as e:
                                    logging.error(f"Error saving completed order to history: {e}")
                
                logging.info(f"Processed {active_order_count} active orders from current state")

            # Sort by creation date (newest first), with active orders at the top
            # Handle None values in dates properly
            def get_sort_key(item):
                is_active = item.get('is_active', False)
                date_str = item.get('completed_at') or item.get('created_at') or ''
                # Convert boolean to int for sorting (True=1, False=0), then negate for reverse
                return (not is_active, date_str)

            history_data.sort(key=get_sort_key, reverse=True)

            # Get unique printer groups - FIX THE MIXED DATA TYPE ISSUE
            all_groups = set()
            for item in history_data:
                groups = item.get('groups', [])
                if isinstance(groups, list):
                    all_groups.update(groups)
                elif isinstance(groups, str):
                    all_groups.add(groups)

            # Remove empty/None groups
            all_groups.discard('')
            all_groups.discard(None)

            # Convert all groups to strings before sorting to avoid type mismatch
            all_groups_str = [str(group) for group in all_groups]

            result = {
                'success': True,
                'history': history_data,
                'groups': sorted(all_groups_str)  # Now all strings, can be sorted
            }
            
            logging.info(f"Returning {len(history_data)} history items with {len(all_groups_str)} unique groups")
            return jsonify(result)

        except Exception as e:
            logging.error(f"Error getting print history: {e}")
            logging.error(f"Traceback: {traceback.format_exc()}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    def save_completed_order_to_history(order, history_file):
        """Save a completed order to the history file"""
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(history_file), exist_ok=True)
            
            # Prepare history entry
            history_entry = {
                'id': order.get('id'),
                'filename': order.get('filename', 'Unknown'),
                'quantity': order.get('quantity', 0),
                'sent': order.get('sent', order.get('quantity', 0)),  # Default sent to quantity for completed orders
                'groups': order.get('groups', order.get('printer_group', ['Unknown'])),
                'filament_g': order.get('filament_g', 0),
                'ejection_enabled': order.get('ejection_enabled', False),
                'source': order.get('source', 'unknown'),
                'extra_data': order.get('extra_data', {}),
                'created_at': order.get('created_at'),
                'completed_at': order.get('completed_at', datetime.now().isoformat()),
                'duration_seconds': None
            }
            
            # Calculate duration if possible
            if 'created_at' in order and order['created_at']:
                try:
                    created_str = order['created_at']
                    if created_str.endswith('Z'):
                        created_str = created_str.replace('Z', '+00:00')
                    created = datetime.fromisoformat(created_str)
                    
                    if order.get('completed_at'):
                        completed_str = order['completed_at']
                        if completed_str.endswith('Z'):
                            completed_str = completed_str.replace('Z', '+00:00')
                        completed = datetime.fromisoformat(completed_str)
                    else:
                        completed = datetime.now()
                        if created.tzinfo:
                            from datetime import timezone
                            completed = completed.replace(tzinfo=timezone.utc)
                    
                    duration = (completed - created).total_seconds()
                    history_entry['duration_seconds'] = duration
                except (ValueError, TypeError) as e:
                    logging.warning(f"Error calculating duration for completed order {order.get('id')}: {e}")
            
            # Ensure groups is a list
            if isinstance(history_entry['groups'], str):
                history_entry['groups'] = [history_entry['groups']]
            elif not history_entry['groups']:
                history_entry['groups'] = ['Unknown']
            
            # Append to history file (one JSON object per line)
            with open(history_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(history_entry) + '\n')
                
            logging.info(f"Saved completed order {order.get('id')} to history file")
            
        except Exception as e:
            logging.error(f"Error saving order to history file: {e}")
            raise

    # Export this function so it can be called when orders are completed
    app.save_completed_order_to_history = lambda order: save_completed_order_to_history(order, os.path.join(app.config.get('LOG_DIR', ''), 'print_history.json'))