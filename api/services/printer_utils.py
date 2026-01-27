"""
Printer utility functions for deduplication, filament calculation, connection management,
and emergency recovery operations.
"""
import os
import re
import time
import asyncio
import aiohttp
import threading
from contextlib import asynccontextmanager

from services.state import (
    PRINTERS_FILE, ORDERS_FILE,
    PRINTERS, ORDERS,
    save_data, logging, orders_lock, filament_lock, printers_rwlock,
    SafeLock, ReadLock, WriteLock,
    TOTAL_FILAMENT_CONSUMPTION
)
from utils.config import Config

# Thread-local storage for event loops
thread_local = threading.local()

# Global connection pool (deprecated - use get_session instead)
CONNECTION_POOL = None


def deduplicate_printers():
    """Remove duplicate printers from the PRINTERS list - keep first occurrence"""
    global PRINTERS

    with WriteLock(printers_rwlock):
        seen_names = set()
        unique_printers = []
        duplicates_removed = 0

        for printer in PRINTERS:
            printer_name = printer.get('name')
            if printer_name and printer_name not in seen_names:
                seen_names.add(printer_name)
                unique_printers.append(printer)
            else:
                duplicates_removed += 1
                logging.warning(f"REMOVED DUPLICATE: Printer '{printer_name}' was duplicated")

        if duplicates_removed > 0:
            PRINTERS.clear()
            PRINTERS.extend(unique_printers)
            save_data(PRINTERS_FILE, PRINTERS)
            logging.warning(f"DEDUPLICATION: Removed {duplicates_removed} duplicate printers. Now have {len(PRINTERS)} unique printers")
        else:
            logging.debug(f"DEDUPLICATION: No duplicates found. Have {len(PRINTERS)} unique printers")


def deduplicate_orders():
    """Remove duplicate orders from the ORDERS list - keep first occurrence"""
    global ORDERS

    with SafeLock(orders_lock):
        seen_ids = set()
        unique_orders = []
        duplicates_removed = 0

        for order in ORDERS:
            order_id = order.get('id')
            if order_id and order_id not in seen_ids:
                seen_ids.add(order_id)
                unique_orders.append(order)
            else:
                duplicates_removed += 1
                logging.warning(f"REMOVED DUPLICATE: Order '{order_id}' was duplicated")

        if duplicates_removed > 0:
            ORDERS.clear()
            ORDERS.extend(unique_orders)
            save_data(ORDERS_FILE, ORDERS)
            logging.warning(f"DEDUPLICATION: Removed {duplicates_removed} duplicate orders. Now have {len(ORDERS)} unique orders")
        else:
            logging.debug(f"DEDUPLICATION: No duplicates found. Have {len(ORDERS)} unique orders")


def periodic_deduplication_check(socketio, app):
    """Periodically check for and remove duplicates"""
    while True:
        try:
            time.sleep(300)  # Check every 5 minutes

            # Check for printer duplicates
            with ReadLock(printers_rwlock):
                printer_names = [p.get('name') for p in PRINTERS]
                if len(printer_names) != len(set(printer_names)):
                    logging.warning("DUPLICATE PRINTERS DETECTED! Running deduplication...")

            deduplicate_printers()

            # Check for order duplicates
            with SafeLock(orders_lock):
                order_ids = [o.get('id') for o in ORDERS]
                if len(order_ids) != len(set(order_ids)):
                    logging.warning("DUPLICATE ORDERS DETECTED! Running deduplication...")

            deduplicate_orders()

        except Exception as e:
            logging.error(f"Error in periodic deduplication: {e}")


def convert_mm_to_g(filament_mm, density):
    """Convert filament length in mm to weight in grams"""
    filament_radius = 1.75 / 2
    volume_cm3 = (3.14159 * (filament_radius ** 2) * (filament_mm / 10)) / 1000
    return volume_cm3 * density


def extract_filament_from_file(filepath, is_bgcode=False):
    """Extract filament usage from gcode or 3mf file"""
    filament_g = 0
    filament_mm = 0

    # Check if it's a .3mf file
    if filepath.endswith('.3mf'):
        try:
            import zipfile

            # .3mf files are ZIP archives
            with zipfile.ZipFile(filepath, 'r') as zip_file:
                # Look for Metadata/Slic3r_PE.config or similar files
                for filename in zip_file.namelist():
                    if 'gcode' in filename.lower() and filename.endswith('.gcode'):
                        # Found a gcode file inside the 3mf
                        with zip_file.open(filename) as gcode_file:
                            content = gcode_file.read().decode('utf-8', errors='ignore')
                            for line in content.splitlines()[:100]:  # Check first 100 lines
                                if 'filament used [mm]' in line:
                                    filament_mm = float(line.split('=')[-1].strip())
                                elif 'filament used [g]' in line:
                                    filament_g = float(line.split('=')[-1].strip())
                                if filament_g > 0:
                                    break
                            if filament_g > 0:
                                break
                # If no filament found in gcode, try to extract from filename
                if filament_g == 0:
                    base_name = os.path.basename(filepath)
                    match = re.search(r'(\d+)_gram', base_name)
                    if match:
                        filament_g = float(match.group(1))
                        logging.debug(f"Extracted filament from filename: {filament_g}g")

        except Exception as e:
            logging.error(f"Error parsing filament from .3mf file {filepath}: {str(e)}")
            # Try to extract from filename as fallback
            base_name = os.path.basename(filepath)
            match = re.search(r'(\d+)_gram', base_name)
            if match:
                filament_g = float(match.group(1))
                logging.debug(f"Extracted filament from filename pattern: {filament_g}g")
    else:
        # Original code for .gcode files
        try:
            with open(filepath, 'rb') as f:
                header = f.read(1024).decode('utf-8', errors='ignore')
                for line in header.splitlines():
                    if 'filament used [mm]' in line:
                        filament_mm = float(line.split('=')[-1].strip())
                    elif 'filament used [g]' in line:
                        filament_g = float(line.split('=')[-1].strip())
                if filament_g == 0 and filament_mm > 0:
                    filament_g = convert_mm_to_g(filament_mm, Config.DEFAULT_FILAMENT_DENSITY)
        except Exception as e:
            logging.error(f"Error parsing filament from {filepath}: {str(e)}")

    logging.debug(f"Extracted filament from {filepath}: {filament_g}g")
    return filament_g


def get_event_loop_for_thread():
    """Get or create an event loop for the current thread"""
    if not hasattr(thread_local, 'loop') or thread_local.loop.is_closed():
        thread_local.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(thread_local.loop)
    return thread_local.loop


def get_connection_pool():
    """Get the global connection pool (deprecated - use get_session instead)"""
    global CONNECTION_POOL
    logging.warning("Direct pool access is deprecated, use async context manager instead")
    if CONNECTION_POOL is None or CONNECTION_POOL.closed:
        logging.debug("Creating new aiohttp ClientSession")
        CONNECTION_POOL = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=20, ttl_dns_cache=300),
            timeout=aiohttp.ClientTimeout(total=Config.API_TIMEOUT)
        )
    return CONNECTION_POOL


@asynccontextmanager
async def get_session():
    """Async context manager for aiohttp sessions"""
    session = aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=20, ttl_dns_cache=300),
        timeout=aiohttp.ClientTimeout(total=Config.API_TIMEOUT)
    )
    try:
        yield session
    finally:
        if not session.closed:
            await session.close()


async def close_connection_pool():
    """Close the global connection pool and cleanup resources"""
    global CONNECTION_POOL
    if CONNECTION_POOL is not None and not CONNECTION_POOL.closed:
        try:
            await CONNECTION_POOL.close()
            CONNECTION_POOL = None
            logging.debug("Successfully closed aiohttp connection pool")
        except Exception as e:
            logging.error(f"Error closing connection pool: {e}")

    # Clean up Bambu MQTT connections
    from services.state import cleanup_mqtt_connections
    cleanup_mqtt_connections()


def emergency_fix_stuck_printers():
    """Emergency function to fix stuck printers"""
    with WriteLock(printers_rwlock):
        fixed_count = 0
        for printer in PRINTERS:
            if printer.get('state') == 'FINISHED':
                # Force all FINISHED printers to READY
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
                    "ejection_in_progress": False,
                    "finish_time": None,
                    "count_incremented_for_current_job": False
                })
                fixed_count += 1
                logging.warning(f"EMERGENCY: Fixed stuck printer {printer['name']}")

        if fixed_count > 0:
            save_data(PRINTERS_FILE, PRINTERS)
            logging.warning(f"EMERGENCY: Fixed {fixed_count} stuck printers")

    return fixed_count


def mark_group_ready(group_name, socketio=None):
    """Mark all FINISHED printers in a specific group as READY"""
    # Import here to avoid circular imports
    from services.status_poller import prepare_printer_data_for_broadcast

    with WriteLock(printers_rwlock):
        count = 0
        for printer in PRINTERS:
            if str(printer.get('group', 'Default')) == str(group_name) and printer['state'] == 'FINISHED':
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
                    "ejection_in_progress": False,
                    "ejection_start_time": None,
                    "finish_time": None,
                    "count_incremented_for_current_job": False
                })
                count += 1
                logging.info(f"Marked {printer['name']} in group {group_name} as READY")

        save_data(PRINTERS_FILE, PRINTERS)

        if count > 0:
            logging.info(f"Marked {count} printers in group {group_name} as READY")

            # Emit status update if socketio is available
            if socketio:
                with SafeLock(filament_lock):
                    total_filament = TOTAL_FILAMENT_CONSUMPTION / 1000
                with SafeLock(orders_lock):
                    orders_data = ORDERS.copy()
                printers_copy = prepare_printer_data_for_broadcast(PRINTERS)

                socketio.emit('status_update', {
                    'printers': printers_copy,
                    'total_filament': total_filament,
                    'orders': orders_data
                })

        return count
