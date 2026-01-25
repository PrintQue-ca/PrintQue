"""
Bambu Labs Printer Handler - Fixed Certificate Management and Error Handling
Now includes FTP upload capability for sending files directly to printers
"""
import paho.mqtt.client as mqtt
import ssl
import json
import os
import time
import threading
from typing import Dict, Any, Optional, Tuple
from services.state import MQTT_CLIENTS, logging, decrypt_api_key
from services.bambu_ftp import upload_to_bambu, prepare_gcode_for_bambu

# Bambu Lab CA Certificate
BAMBU_CA_CERT = """-----BEGIN CERTIFICATE-----
MIIDZTCCAk2gAwIBAgIUV1FckwXElyek1onFnQ9kL7Bk4N8wDQYJKoZIhvcNAQEL
BQAwQjELMAkGA1UEBhMCQ04xIjAgBgNVBAoMGUJCTCBUZWNobm9sb2dpZXMgQ28u
LCBMdGQxDzANBgNVBAMMBkJCLCBDQTAeFw0yMjA0MDQwMzQyMTFaFw0zMjA0MDEw
MzQyMTFaMEIxCzAJBgNVBAYTAkNOMSIwIAYDVQQKDBlCQkwgVGVjaG5vbG9naWVz
IENvLiwgTHRkMQ8wDQYDVQQDDAZCQkwgQ0EwggEiMA0GCSqGSIb3DQEBAQUAA4IB
DwAwggEKAoIBAQDL3pnDdxGOk5Z6vugiT4dpM0ju+3Xatxz09UY7mbj4tkIdby4H
oeEdiYSZjc5LJngJuCHwtEbBJt1BriRdSVrF6M9D2UaBDyamEo0dxwSaVxZiDVWC
eeCPdELpFZdEhSNTaT4O7zgvcnFsfHMa/0vMAkvE7i0qp3mjEzYLfz60axcDoJLk
p7n6xKXI+cJbA4IlToFjpSldPmC+ynOo7YAOsXt7AYKY6Glz0BwUVzSJxU+/+VFy
/QrmYGNwlrQtdREHeRi0SNK32x1+bOndfJP0sojuIrDjKsdCLye5CSZIvqnbowwW
1jRwZgTBR29Zp2nzCoxJYcU9TSQp/4KZuWNVAgMBAAGjUzBRMB0GA1UdDgQWBBSP
NEJo3GdOj8QinsV8SeWr3US+HjAfBgNVHSMEGDAWgBSPNEJo3GdOj8QinsV8SeWr
3US+HjAPBgNVHRMBAf8EBTADAQH/MA0GCSqGSIb3DQEBCwUAA4IBAQABlBIT5ZeG
fgcK1LOh1CN9sTzxMCLbtTPFF1NGGA13mApu6j1h5YELbSKcUqfXzMnVeAb06Htu
3CoCoe+wj7LONTFO++vBm2/if6Jt/DUw1CAEcNyqeh6ES0NX8LJRVSe0qdTxPJuA
BdOoo96iX89rRPoxeed1cpq5hZwbeka3+CJGV76itWp35Up5rmmUqrlyQOr/Wax6
itosIzG0MfhgUzU51A2P/hSnD3NDMXv+wUY/AvqgIL7u7fbDKnku1GzEKIKkfH8hm
Rs6d8SCU89xyrwzQ0PR853irHas3WrHVqab3P+qNwR0YirL0Qk7Xt/q3O1griNg2
Blbjg3obpHo9
-----END CERTIFICATE-----"""

# Global certificate file path
BAMBU_CERT_FILE = None
BAMBU_CERT_LOCK = threading.Lock()

def get_bambu_cert_file():
    """Get or create the Bambu certificate file"""
    global BAMBU_CERT_FILE

    with BAMBU_CERT_LOCK:
        if BAMBU_CERT_FILE is None or not os.path.exists(BAMBU_CERT_FILE):
            # Create in a persistent location
            cert_dir = os.path.join(os.path.expanduser("~"), "PrintQueData", "certs")
            os.makedirs(cert_dir, exist_ok=True)
            BAMBU_CERT_FILE = os.path.join(cert_dir, "bambu_ca.pem")

            # Always rewrite the certificate to ensure it's properly formatted
            try:
                with open(BAMBU_CERT_FILE, 'w', encoding='utf-8') as f:
                    f.write(BAMBU_CA_CERT)
                logging.info(f"Created Bambu certificate file at {BAMBU_CERT_FILE}")

                # Verify the certificate file is valid
                with open(BAMBU_CERT_FILE, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if "-----BEGIN CERTIFICATE-----" not in content:
                        raise ValueError("Invalid certificate format")

            except Exception as e:
                logging.error(f"Error creating certificate file: {str(e)}")
                # Try alternative approach - write bytes
                try:
                    with open(BAMBU_CERT_FILE, 'wb') as f:
                        f.write(BAMBU_CA_CERT.encode('utf-8'))
                    logging.info(f"Created Bambu certificate file (binary mode) at {BAMBU_CERT_FILE}")
                except Exception as e2:
                    logging.error(f"Failed to create certificate file: {str(e2)}")
                    raise

        return BAMBU_CERT_FILE

# State mapping from Bambu to PrintQue states
BAMBU_STATE_MAP = {
    'IDLE': 'READY',
    'PREPARE': 'PREPARING',
    'RUNNING': 'PRINTING',
    'PAUSE': 'PAUSED',
    'FAILED': 'ERROR',  # Default FAILED to ERROR - will be overridden by error checking
    'FINISH': 'FINISHED',
    'UNKNOWN': 'OFFLINE'
}

# Error code mappings - Extended list
BAMBU_ERROR_CODES = {
    # Original codes
    83935248: "File not found or invalid format",
    50348044: "Print preparation failed",
    84033543: "Printer busy or in error state",

    # Additional common error codes
    50331648: "No print job active or print job ended",
    50331649: "Print cancelled by user",
    50331650: "Print failed - check printer status",
    50331651: "Filament runout detected",
    50331652: "Hotend temperature error",
    50331653: "Heatbed temperature error",
    50331654: "Print head blocked or jammed",
    50331655: "Power loss recovery failed",
    50331656: "SD card error",
    50331657: "File transfer error",
    50331658: "Calibration required",
    50331659: "Hardware fault detected",

    # HMS (Health Management System) related
    65539: "General hardware alert - check printer",
    65543: "Heatbed error",
    65544: "Hotend thermistor error",
    65545: "Extruder motor error",
    65546: "X-axis motor error",
    65547: "Y-axis motor error",
    65548: "Z-axis motor error",

    # File and job related
    67108864: "Invalid G-code file",
    67108865: "File too large",
    67108866: "Unsupported file format",
    67108867: "File corrupted",

    # Network and communication
    100663296: "Network timeout",
    100663297: "MQTT connection lost",
    100663298: "Invalid command format",
    100663299: "Command queue full",
}

# Store printer states (since MQTT is async)
BAMBU_PRINTER_STATES = {}
bambu_states_lock = threading.Lock()

# Store sequence IDs for commands
SEQUENCE_IDS = {}
sequence_lock = threading.Lock()

# Connection retry tracking
CONNECTION_RETRIES = {}
retry_lock = threading.Lock()

class BambuMQTTClient(mqtt.Client):
    """Custom MQTT client that handles Bambu's server name requirements"""
    def __init__(self, *args, server_name=None, **kwargs):
        # Handle both old and new paho-mqtt versions
        if args and len(args) > 0 and hasattr(mqtt, 'CallbackAPIVersion'):
            # New version - skip the API version if present
            if isinstance(args[0], mqtt.CallbackAPIVersion):
                args = args[1:]
        super().__init__(*args, **kwargs)
        self._server_name = server_name

    def _ssl_wrap_socket(self, sock):
        orig_host = self._host
        if self._server_name:
            self._host = self._server_name
        result = super()._ssl_wrap_socket(sock)
        self._host = orig_host
        return result

def get_next_sequence_id(printer_name: str) -> str:
    """Get next sequence ID for commands"""
    with sequence_lock:
        if printer_name not in SEQUENCE_IDS:
            SEQUENCE_IDS[printer_name] = 1
        seq_id = str(SEQUENCE_IDS[printer_name])
        SEQUENCE_IDS[printer_name] += 1
        return seq_id

def on_connect(client, userdata, flags, rc):
    """MQTT connection callback"""
    printer_name = userdata['printer_name']
    if rc == 0:
        logging.info(f"Bambu printer {printer_name} connected via MQTT")
        # Subscribe to report topic
        serial_number = userdata['serial_number']
        topic = f"device/{serial_number}/report"
        client.subscribe(topic)

        # Update state
        with bambu_states_lock:
            if printer_name not in BAMBU_PRINTER_STATES:
                BAMBU_PRINTER_STATES[printer_name] = {}
            BAMBU_PRINTER_STATES[printer_name]['connected'] = True
            BAMBU_PRINTER_STATES[printer_name]['last_seen'] = time.time()
            BAMBU_PRINTER_STATES[printer_name]['connection_time'] = time.time()
            # Clear any previous disconnect reason
            BAMBU_PRINTER_STATES[printer_name].pop('disconnect_reason', None)
            BAMBU_PRINTER_STATES[printer_name].pop('last_error', None)
            # If state was OFFLINE due to disconnect, we'll wait for status update to set proper state
            # Don't automatically set to READY - let the printer report its actual state
            if BAMBU_PRINTER_STATES[printer_name].get('state') == 'OFFLINE':
                logging.info(f"Bambu printer {printer_name} reconnected, waiting for status update")

        # Reset retry count on successful connection
        with retry_lock:
            if printer_name in CONNECTION_RETRIES:
                CONNECTION_RETRIES[printer_name] = 0
    else:
        error_msg = {
            1: "Incorrect protocol version",
            2: "Invalid client identifier",
            3: "Server unavailable",
            4: "Bad username or password",
            5: "Not authorized"
        }.get(rc, f"Unknown error code: {rc}")
        logging.error(f"Bambu printer {printer_name} connection failed: {error_msg}")
        with bambu_states_lock:
            if printer_name not in BAMBU_PRINTER_STATES:
                BAMBU_PRINTER_STATES[printer_name] = {}
            BAMBU_PRINTER_STATES[printer_name]['connected'] = False
            BAMBU_PRINTER_STATES[printer_name]['state'] = 'OFFLINE'
            BAMBU_PRINTER_STATES[printer_name]['last_error'] = error_msg

def on_disconnect(client, userdata, rc):
    """MQTT disconnection callback"""
    printer_name = userdata['printer_name']
    if rc == 0:
        logging.info(f"Bambu printer {printer_name} disconnected cleanly")
    else:
        logging.warning(f"Bambu printer {printer_name} disconnected unexpectedly (rc={rc})")

    with bambu_states_lock:
        if printer_name in BAMBU_PRINTER_STATES:
            BAMBU_PRINTER_STATES[printer_name]['connected'] = False
            # CRITICAL FIX: Update state to OFFLINE when connection is lost unexpectedly
            # This prevents the UI from showing "READY" when the printer can't receive commands
            if rc != 0:
                previous_state = BAMBU_PRINTER_STATES[printer_name].get('state', 'UNKNOWN')
                BAMBU_PRINTER_STATES[printer_name]['state'] = 'OFFLINE'
                BAMBU_PRINTER_STATES[printer_name]['disconnect_reason'] = f"Connection lost (rc={rc})"
                logging.warning(f"Bambu printer {printer_name} state changed from {previous_state} to OFFLINE due to disconnect")
            # Calculate connection duration
            if 'connection_time' in BAMBU_PRINTER_STATES[printer_name]:
                duration = time.time() - BAMBU_PRINTER_STATES[printer_name]['connection_time']
                logging.info(f"Bambu printer {printer_name} was connected for {duration:.1f} seconds")

    # Check if we should attempt reconnection
    if rc != 0 and printer_name in MQTT_CLIENTS:
        with retry_lock:
            retries = CONNECTION_RETRIES.get(printer_name, 0)
            if retries < 5:  # Max 5 retry attempts
                CONNECTION_RETRIES[printer_name] = retries + 1
                delay = min(5 * (retries + 1), 30)  # Exponential backoff, max 30 seconds
                logging.info(f"Will attempt to reconnect {printer_name} in {delay} seconds (retry {retries + 1}/5)")
                threading.Timer(delay, lambda: reconnect_bambu_printer(printer_name)).start()
            else:
                logging.error(f"Max reconnection attempts reached for {printer_name}")

def reconnect_bambu_printer(printer_name: str) -> None:
    """Attempt to reconnect a Bambu printer"""
    from services.state import PRINTERS, printers_rwlock, ReadLock

    with ReadLock(printers_rwlock):
        printer = next((p for p in PRINTERS if p['name'] == printer_name and p.get('type') == 'bambu'), None)

    if printer:
        logging.info(f"Attempting to reconnect Bambu printer {printer_name}")
        connect_bambu_printer(printer)

def on_message(client, userdata, msg):
    """MQTT message callback"""
    printer_name = userdata['printer_name']
    try:
        data = json.loads(msg.payload.decode())
        logging.debug(f"Bambu {printer_name} message on topic {msg.topic}: {json.dumps(data, indent=2)[:500]}...")

        with bambu_states_lock:
            if printer_name not in BAMBU_PRINTER_STATES:
                BAMBU_PRINTER_STATES[printer_name] = {}

            # Update last seen time
            BAMBU_PRINTER_STATES[printer_name]['last_seen'] = time.time()

            # Process print data
            if "print" in data:
                print_data = data["print"]

                # Command responses
                if "command" in print_data and "result" in print_data:
                    cmd = print_data['command']
                    result = print_data['result']
                    param = print_data.get('param', '')
                    reason = print_data.get('reason', '')

                    # Log gcode_line responses at INFO level for debugging
                    if cmd == 'gcode_line':
                        if result == 'success':
                            logging.info(f"[GCODE_RESPONSE] {printer_name}: '{param}' -> SUCCESS")
                        else:
                            logging.warning(f"[GCODE_RESPONSE] {printer_name}: '{param}' -> {result} (reason: {reason})")
                    else:
                        logging.debug(f"Bambu {printer_name} response: {cmd} = {result}")

                    if reason and cmd != 'gcode_line':
                        logging.warning(f"Bambu {printer_name} reason: {reason}")

                    # Check for M400 completion if we're waiting for it
                    if (BAMBU_PRINTER_STATES[printer_name].get('waiting_for_m400', False) and
                        print_data.get('command') == 'gcode_line' and
                        print_data.get('param', '').strip().upper() == 'M400' and
                        print_data.get('result') == 'success'):

                        current_state = BAMBU_PRINTER_STATES[printer_name].get('state')
                        if current_state == 'EJECTING':
                            logging.info(f"Bambu printer {printer_name} M400 complete - ejection finished, transitioning to READY")
                            BAMBU_PRINTER_STATES[printer_name]['state'] = 'READY'
                            BAMBU_PRINTER_STATES[printer_name]['ejection_complete'] = True
                            BAMBU_PRINTER_STATES[printer_name]['gcode_state'] = 'IDLE'
                            BAMBU_PRINTER_STATES[printer_name]['waiting_for_m400'] = False
                            BAMBU_PRINTER_STATES[printer_name]['last_ejection_time'] = time.time()

                # Get current state and error code
                gcode_state = print_data.get('gcode_state', 'UNKNOWN')
                print_error = print_data.get('print_error', 0)

                # State updates
                if "gcode_state" in print_data:
                    old_state = BAMBU_PRINTER_STATES[printer_name].get('gcode_state', 'UNKNOWN')
                    if old_state != gcode_state:
                        logging.info(f"Bambu {printer_name} state changed: {old_state} -> {gcode_state}")

                    BAMBU_PRINTER_STATES[printer_name]['gcode_state'] = gcode_state

                    # CRITICAL: Check if we're in EJECTING state
                    current_state = BAMBU_PRINTER_STATES[printer_name].get('state')
                    if current_state == 'EJECTING':
                        # Check if ejection has been running for more than 15 seconds
                        ejection_start = BAMBU_PRINTER_STATES[printer_name].get('ejection_start_time', 0)
                        if ejection_start and (time.time() - ejection_start > 15):
                            logging.info(f"Bambu printer {printer_name} ejection complete (15s elapsed) - transitioning to READY")
                            BAMBU_PRINTER_STATES[printer_name]['state'] = 'READY'
                            BAMBU_PRINTER_STATES[printer_name]['ejection_complete'] = True
                            BAMBU_PRINTER_STATES[printer_name]['gcode_state'] = 'IDLE'
                            # Don't process normal state mapping for this update
                        else:
                            # Still ejecting, keep the state
                            pass
                    elif gcode_state == 'FAILED':
                        # Check if it's a real error or just "no job active"
                        if print_error == 50331648:
                            # No job active - printer is ready
                            BAMBU_PRINTER_STATES[printer_name]['state'] = 'READY'
                            BAMBU_PRINTER_STATES[printer_name]['error'] = None
                            logging.info(f"Bambu {printer_name} is ready (no active job)")
                        elif print_error == 0:
                            # No specific error code but in FAILED state
                            # Check if there are HMS alerts
                            if "hms" in print_data and print_data["hms"]:
                                BAMBU_PRINTER_STATES[printer_name]['state'] = 'ERROR'
                                logging.error(f"Bambu {printer_name} has HMS alerts")
                            else:
                                # No error code and no HMS alerts, treat as ready
                                BAMBU_PRINTER_STATES[printer_name]['state'] = 'READY'
                                BAMBU_PRINTER_STATES[printer_name]['error'] = None
                        else:
                            # Real error occurred
                            BAMBU_PRINTER_STATES[printer_name]['state'] = 'ERROR'
                            error_msg = BAMBU_ERROR_CODES.get(print_error, f"Unknown error: {print_error}")
                            BAMBU_PRINTER_STATES[printer_name]['error'] = error_msg
                            logging.error(f"Bambu {printer_name} error: {error_msg}")
                    elif gcode_state == 'IDLE':
                        # IDLE means ready in Bambu terms
                        BAMBU_PRINTER_STATES[printer_name]['state'] = 'READY'
                        BAMBU_PRINTER_STATES[printer_name]['error'] = None
                    else:
                        # Use normal state mapping
                        mapped_state = BAMBU_STATE_MAP.get(gcode_state, 'OFFLINE')
                        BAMBU_PRINTER_STATES[printer_name]['state'] = mapped_state
                        # Clear error unless we're in ERROR state
                        if mapped_state != 'ERROR':
                            BAMBU_PRINTER_STATES[printer_name]['error'] = None

                    # In the state updates section where you check for EJECTING state
                    if current_state == 'EJECTING':
                        # If we're ejecting and the printer reports IDLE/FINISH state
                        if gcode_state in ['IDLE', 'FINISH']:
                            logging.info(f"Bambu printer {printer_name} completed ejection sequence")
                            BAMBU_PRINTER_STATES[printer_name]['state'] = 'READY'
                            BAMBU_PRINTER_STATES[printer_name]['ejection_complete'] = True
                            BAMBU_PRINTER_STATES[printer_name]['gcode_state'] = 'IDLE'
                        else:
                            # Just log progress periodically (no timeout)
                            if 'ejection_start_time' in BAMBU_PRINTER_STATES[printer_name]:
                                ejection_duration = time.time() - BAMBU_PRINTER_STATES[printer_name]['ejection_start_time']

                                # Log every 2 minutes that we're still waiting
                                if ejection_duration > 120 and not BAMBU_PRINTER_STATES[printer_name].get('long_ejection_logged', False):
                                    logging.info(f"Bambu printer {printer_name} still ejecting after {ejection_duration/60:.1f} minutes - waiting for completion (temperature waits may be active)")
                                    BAMBU_PRINTER_STATES[printer_name]['long_ejection_logged'] = True
                                elif ejection_duration > 600 and not BAMBU_PRINTER_STATES[printer_name].get('very_long_ejection_logged', False):
                                    logging.info(f"Bambu printer {printer_name} still ejecting after {ejection_duration/60:.1f} minutes - this is normal if cooling down")
                                    BAMBU_PRINTER_STATES[printer_name]['very_long_ejection_logged'] = True

                # Progress
                if "mc_percent" in print_data:
                    BAMBU_PRINTER_STATES[printer_name]['progress'] = print_data['mc_percent']

                # Temperatures
                if "nozzle_temper" in print_data:
                    BAMBU_PRINTER_STATES[printer_name]['nozzle_temp'] = print_data['nozzle_temper']
                if "bed_temper" in print_data:
                    BAMBU_PRINTER_STATES[printer_name]['bed_temp'] = print_data['bed_temper']

                # Current file
                if "gcode_file" in print_data:
                    BAMBU_PRINTER_STATES[printer_name]['current_file'] = print_data['gcode_file']

                # Time remaining (calculate from other fields if available)
                if "mc_remaining_time" in print_data:
                    # Convert minutes to seconds for consistency with UI
                    BAMBU_PRINTER_STATES[printer_name]['time_remaining'] = print_data['mc_remaining_time'] * 60
                    logging.debug(f"Bambu {printer_name} time remaining: {print_data['mc_remaining_time']} minutes ({print_data['mc_remaining_time'] * 60} seconds)")
                elif "mc_left_time" in print_data:
                    # Alternative field name some Bambu printers use
                    BAMBU_PRINTER_STATES[printer_name]['time_remaining'] = print_data['mc_left_time'] * 60
                    logging.debug(f"Bambu {printer_name} time remaining (mc_left_time): {print_data['mc_left_time']} minutes ({print_data['mc_left_time'] * 60} seconds)")
                elif "remaining_time" in print_data:
                    # Another possible field name
                    BAMBU_PRINTER_STATES[printer_name]['time_remaining'] = print_data['remaining_time'] * 60
                    logging.debug(f"Bambu {printer_name} time remaining (remaining_time): {print_data['remaining_time']} minutes ({print_data['remaining_time'] * 60} seconds)")
                else:
                    # Log available fields to help debug
                    if BAMBU_PRINTER_STATES[printer_name].get('state') in ['PRINTING', 'PAUSED']:
                        available_fields = [k for k in print_data.keys() if 'time' in k.lower() or 'remaining' in k.lower()]
                        if available_fields:
                            logging.debug(f"Bambu {printer_name} has time-related fields: {available_fields}")

                # HMS alerts
                if "hms" in print_data and print_data["hms"]:
                    hms_errors = []
                    for alert in print_data["hms"]:
                        if isinstance(alert, dict) and "code" in alert:
                            alert_code = alert['code']
                            alert_msg = BAMBU_ERROR_CODES.get(alert_code, f"HMS Alert: {alert_code}")
                            hms_errors.append(alert_msg)
                    if hms_errors:
                        BAMBU_PRINTER_STATES[printer_name]['hms_alerts'] = hms_errors
                        # If we have HMS alerts and no other error, set state to ERROR
                        if BAMBU_PRINTER_STATES[printer_name].get('state') != 'ERROR':
                            BAMBU_PRINTER_STATES[printer_name]['state'] = 'ERROR'
                            BAMBU_PRINTER_STATES[printer_name]['error'] = f"HMS Alert: {', '.join(hms_errors)}"
                        logging.warning(f"Bambu {printer_name} HMS alerts: {hms_errors}")
                else:
                    BAMBU_PRINTER_STATES[printer_name]['hms_alerts'] = []

            # Log current state for debugging
            current_state = BAMBU_PRINTER_STATES[printer_name].get('state', 'UNKNOWN')
            current_error = BAMBU_PRINTER_STATES[printer_name].get('error', 'None')
            logging.debug(f"Bambu {printer_name} current state: {current_state}, error: {current_error}")

    except Exception as e:
        logging.error(f"Error processing Bambu message for {printer_name}: {str(e)}")

def connect_bambu_printer(printer: Dict[str, Any]) -> bool:
    """Connect to a Bambu printer via MQTT"""
    printer_name = printer['name']

    # Check if already connected
    if printer_name in MQTT_CLIENTS:
        client = MQTT_CLIENTS[printer_name]
        if client.is_connected():
            logging.debug(f"Bambu printer {printer_name} already connected")
            return True
        else:
            # Clean up disconnected client
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:
                pass
            del MQTT_CLIENTS[printer_name]

    try:
        # Create client
        client_id = f"printque_{printer_name}_{int(time.time())}"
        client = BambuMQTTClient(
            client_id=client_id,
            clean_session=True,
            server_name=printer['serial_number']
        )

        # CRITICAL: Disable message queuing to prevent old commands from replaying
        # This prevents the "stuck commands replaying on restart" issue
        try:
            client.max_queued_messages_set(0)  # Don't queue messages
            client.max_inflight_messages_set(1)  # Only 1 message in flight at a time
        except AttributeError:
            # Older paho-mqtt versions might not have these
            logging.warning(f"Could not set MQTT queue limits for {printer_name}")

        # Set up userdata for callbacks
        client.user_data_set({
            'printer_name': printer_name,
            'serial_number': printer['serial_number']
        })

        # Set up callbacks
        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message

        # Get persistent certificate file
        ca_file_path = get_bambu_cert_file()

        # Set up TLS with better error handling
        try:
            # Try with the certificate file
            context = ssl.create_default_context(cafile=ca_file_path)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_REQUIRED
            client.tls_set_context(context)
        except ssl.SSLError as e:
            logging.warning(f"SSL error with certificate file, trying without verification: {str(e)}")
            # Fallback to unverified connection
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            client.tls_set_context(context)

        # Set credentials
        access_code = decrypt_api_key(printer['access_code'])
        client.username_pw_set("bblp", access_code)

        # Connect
        logging.info(f"Connecting to Bambu printer {printer_name} at {printer['ip']}:8883")
        client.connect(printer['ip'], 8883, keepalive=60)
        client.loop_start()

        # Store client
        MQTT_CLIENTS[printer_name] = client

        # Wait a bit longer for connection to stabilize
        time.sleep(3)

        # Check if connected
        if client.is_connected():
            logging.info(f"Bambu printer {printer_name} connection established")
            # Wait a bit more before requesting status
            time.sleep(2)
            # Request initial status
            request_bambu_status(printer)
            return True
        else:
            logging.warning(f"Bambu printer {printer_name} not connected after wait period")
            # Clean up
            if printer_name in MQTT_CLIENTS:
                del MQTT_CLIENTS[printer_name]
            return False

    except Exception as e:
        logging.error(f"Failed to connect Bambu printer {printer_name}: {str(e)}")
        # Clean up on failure
        if printer_name in MQTT_CLIENTS:
            try:
                MQTT_CLIENTS[printer_name].loop_stop()
            except Exception:
                pass
            del MQTT_CLIENTS[printer_name]
        return False

def disconnect_bambu_printer(printer_name: str) -> None:
    """Disconnect a Bambu printer and clear any queued messages"""
    if printer_name not in MQTT_CLIENTS:
        logging.debug(f"Bambu printer {printer_name} not in MQTT_CLIENTS, nothing to disconnect")
        return

    try:
        client = MQTT_CLIENTS[printer_name]
        # Remove from dict first to prevent double disconnect
        del MQTT_CLIENTS[printer_name]

        # Clear any pending/queued messages to prevent replay on reconnect
        try:
            # Reinitialize the message queue to clear it
            client._out_messages = []
            client._out_message_mutex = threading.Lock() if not hasattr(client, '_out_message_mutex') else client._out_message_mutex
            logging.debug(f"Cleared message queue for {printer_name}")
        except Exception as e:
            logging.debug(f"Could not clear message queue for {printer_name}: {e}")

        # Then stop the client
        try:
            client.loop_stop()
        except Exception as e:
            logging.debug(f"Error stopping loop for {printer_name}: {str(e)}")

        try:
            client.disconnect()
        except Exception as e:
            logging.debug(f"Error disconnecting {printer_name}: {str(e)}")

        logging.info(f"Disconnected Bambu printer {printer_name}")

        # Reset retry count
        with retry_lock:
            if printer_name in CONNECTION_RETRIES:
                CONNECTION_RETRIES[printer_name] = 0

    except Exception as e:
        logging.error(f"Error disconnecting Bambu printer {printer_name}: {str(e)}")

def request_bambu_status(printer: Dict[str, Any]) -> None:
    """Request status update from Bambu printer"""
    printer_name = printer['name']
    if printer_name not in MQTT_CLIENTS:
        return

    client = MQTT_CLIENTS[printer_name]
    if not client.is_connected():
        return

    try:
        command = {
            "pushing": {
                "command": "pushall",
                "sequence_id": get_next_sequence_id(printer_name),
                "version": 1,
                "push_target": 1
            }
        }

        topic = f"device/{printer['serial_number']}/request"
        client.publish(topic, json.dumps(command), qos=0)
        logging.debug(f"Requested status update from Bambu printer {printer_name}")

    except Exception as e:
        logging.error(f"Error requesting Bambu status for {printer_name}: {str(e)}")

def get_bambu_status(printer: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Get current status of Bambu printer"""
    printer_name = printer['name']

    # CRITICAL: Check if printer is manually set to READY first
    if printer.get('manually_set', False) and printer.get('state') == 'READY':
        logging.debug(f"Bambu printer {printer_name} is manually set to READY, returning READY state")
        return printer, {
            "printer": {
                "state": "READY",
                "temp_nozzle": 0,
                "temp_bed": 0,
                "axis_z": 0
            }
        }

    # CRITICAL: Preserve COOLING state - this is managed by PrintQue, not the printer
    # Return COOLING state with current temperatures so cooling monitoring can work
    if printer.get('state') == 'COOLING':
        with bambu_states_lock:
            bed_temp = 0
            nozzle_temp = 0
            if printer_name in BAMBU_PRINTER_STATES:
                bed_temp = BAMBU_PRINTER_STATES[printer_name].get('bed_temp', 0)
                nozzle_temp = BAMBU_PRINTER_STATES[printer_name].get('nozzle_temp', 0)
        logging.debug(f"Bambu printer {printer_name} is COOLING, returning COOLING state (bed: {bed_temp}°C)")
        return printer, {
            "printer": {
                "state": "COOLING",
                "temp_nozzle": nozzle_temp,
                "temp_bed": bed_temp,
                "axis_z": 0
            }
        }

    # Ensure connected
    if printer_name not in MQTT_CLIENTS or not MQTT_CLIENTS[printer_name].is_connected():
        if not connect_bambu_printer(printer):
            # CRITICAL FIX: Also update cached state to OFFLINE when connection fails
            with bambu_states_lock:
                if printer_name in BAMBU_PRINTER_STATES:
                    BAMBU_PRINTER_STATES[printer_name]['state'] = 'OFFLINE'
                    BAMBU_PRINTER_STATES[printer_name]['connected'] = False
            return printer, {
                "printer": {
                    "state": "OFFLINE",
                    "temp_nozzle": 0,
                    "temp_bed": 0,
                    "axis_z": 0
                }
            }

    # Get cached state
    with bambu_states_lock:
        if printer_name not in BAMBU_PRINTER_STATES:
            # Initialize with OFFLINE state if no data exists
            BAMBU_PRINTER_STATES[printer_name] = {
                'state': 'OFFLINE',
                'gcode_state': 'UNKNOWN',
                'last_seen': 0,
                'connected': False
            }

        state_data = BAMBU_PRINTER_STATES[printer_name].copy()

    # Check if data is stale (more than 30 seconds old)
    last_seen = state_data.get('last_seen', 0)
    time_since_seen = time.time() - last_seen

    if time_since_seen > 30:
        request_bambu_status(printer)

    # CRITICAL FIX: If data is very stale (60+ seconds) AND we haven't received any updates,
    # the printer is likely offline or unreachable
    if time_since_seen > 60 and not state_data.get('connected', False):
        logging.warning(f"Bambu printer {printer_name} data is stale ({time_since_seen:.0f}s) and not connected, marking OFFLINE")
        with bambu_states_lock:
            BAMBU_PRINTER_STATES[printer_name]['state'] = 'OFFLINE'
        state_data['state'] = 'OFFLINE'

    # CRITICAL FIX: Also check the connected flag - if disconnected, state should be OFFLINE
    if not state_data.get('connected', False) and state_data.get('state') not in ['OFFLINE', 'EJECTING']:
        # Double-check if we're actually connected
        if printer_name in MQTT_CLIENTS and MQTT_CLIENTS[printer_name].is_connected():
            # We are connected, update the flag
            with bambu_states_lock:
                BAMBU_PRINTER_STATES[printer_name]['connected'] = True
        else:
            # Not connected, force OFFLINE state
            logging.debug(f"Bambu printer {printer_name} shows {state_data.get('state')} but is not connected, returning OFFLINE")
            state_data['state'] = 'OFFLINE'

    # Format response similar to Prusa
    status = {
        "printer": {
            "state": state_data.get('state', 'OFFLINE'),
            "temp_nozzle": state_data.get('nozzle_temp', 0),
            "temp_bed": state_data.get('bed_temp', 0),
            "axis_z": 0  # Bambu doesn't report Z height in status
        }
    }

    # CRITICAL: Add ejection tracking info
    if state_data.get('ejection_complete'):
        status['ejection_complete'] = True
    if state_data.get('last_ejection_time'):
        status['last_ejection_time'] = state_data.get('last_ejection_time')

    # Add error information if present
    if state_data.get('error'):
        status['error'] = state_data['error']

    # Add HMS alerts if present
    if state_data.get('hms_alerts'):
        status['hms_alerts'] = state_data['hms_alerts']

    # Add job info if printing
    if state_data.get('state') in ['PRINTING', 'PAUSED']:
        status['progress'] = state_data.get('progress', 0)
        status['time_remaining'] = state_data.get('time_remaining', 0)
        status['file'] = {
            'name': state_data.get('current_file', 'Unknown'),
            'display_name': state_data.get('current_file', 'Unknown')
        }

    return printer, status

def clear_bambu_error(printer: Dict[str, Any]) -> bool:
    """Clear error state for a Bambu printer"""
    printer_name = printer['name']

    with bambu_states_lock:
        if printer_name in BAMBU_PRINTER_STATES:
            BAMBU_PRINTER_STATES[printer_name]['state'] = 'READY'
            BAMBU_PRINTER_STATES[printer_name]['error'] = None
            BAMBU_PRINTER_STATES[printer_name]['hms_alerts'] = []
            logging.info(f"Cleared error state for Bambu printer {printer_name}")
            return True

    return False

def send_bambu_print_command(printer: Dict[str, Any], filename: str, filepath: str = None, gcode_content: str = None) -> bool:
    """
    Send print command to Bambu printer
    Now includes FTP upload if filepath is provided

    Args:
        printer: Printer dictionary
        filename: Filename to print (as it should appear on the printer)
        filepath: Optional path to local file to upload first
        gcode_content: Optional G-code content for direct commands

    Returns:
        bool: Success status
    """
    printer_name = printer['name']

    # Check if printer is in error state
    with bambu_states_lock:
        if printer_name in BAMBU_PRINTER_STATES:
            state = BAMBU_PRINTER_STATES[printer_name].get('state')
            if state == 'ERROR':
                logging.error(f"Cannot send print command - Bambu printer {printer_name} is in ERROR state")
                return False

    # If we have a filepath, upload the file first
    if filepath and os.path.exists(filepath):
        logging.info(f"Uploading file to Bambu printer {printer_name} before starting print")

        # Prepare the file for Bambu
        success, prepared_path, remote_filename = prepare_gcode_for_bambu(
            filepath,
            os.path.dirname(filepath)
        )

        if not success:
            logging.error(f"Failed to prepare file for Bambu printer {printer_name}")
            return False

        # Upload the file via FTP
        upload_success, upload_msg = upload_to_bambu(printer, prepared_path, remote_filename)

        if not upload_success:
            logging.error(f"Failed to upload file to Bambu printer {printer_name}: {upload_msg}")
            return False

        logging.info(f"Successfully uploaded {remote_filename} to Bambu printer {printer_name}")

        # Use the remote filename for the print command
        filename = remote_filename

    # Ensure filename has correct extension for print command
    if not filename.endswith('.3mf'):
        if filename.endswith('.gcode'):
            filename = filename.replace('.gcode', '.gcode.3mf')
        else:
            filename = filename + '.gcode.3mf'

    # Ensure connected
    if printer_name not in MQTT_CLIENTS or not MQTT_CLIENTS[printer_name].is_connected():
        if not connect_bambu_printer(printer):
            logging.error(f"Cannot send print command - Bambu printer {printer_name} not connected")
            # CRITICAL FIX: Update cached state to OFFLINE when connection fails
            with bambu_states_lock:
                if printer_name in BAMBU_PRINTER_STATES:
                    BAMBU_PRINTER_STATES[printer_name]['state'] = 'OFFLINE'
                    BAMBU_PRINTER_STATES[printer_name]['connected'] = False
                    BAMBU_PRINTER_STATES[printer_name]['disconnect_reason'] = 'Failed to connect for print command'
            return False

    client = MQTT_CLIENTS[printer_name]

    try:
        # Build command
        command = {
            "print": {
                "command": "project_file",
                "sequence_id": get_next_sequence_id(printer_name),
                "param": "Metadata/plate_1.gcode",
                "file": "",
                "url": f"file:///sdcard/{filename}",
                "bed_leveling": True,
                "use_ams": True
            }
        }

        topic = f"device/{printer['serial_number']}/request"
        result = client.publish(topic, json.dumps(command), qos=0)

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logging.info(f"Sent print command for {filename} to Bambu printer {printer_name}")
            return True
        else:
            logging.error(f"Failed to send print command to Bambu printer {printer_name}: {result.rc}")
            # Update state on publish failure
            with bambu_states_lock:
                if printer_name in BAMBU_PRINTER_STATES:
                    BAMBU_PRINTER_STATES[printer_name]['disconnect_reason'] = f'Publish failed (rc={result.rc})'
            return False

    except Exception as e:
        logging.error(f"Error sending print command to Bambu printer {printer_name}: {str(e)}")
        return False

def send_bambu_gcode_command(printer: Dict[str, Any], gcode: str, force_reconnect: bool = False) -> bool:
    """Send raw G-code command to Bambu printer

    Filters out comment-only lines and sends actual G-code commands via MQTT.
    Uses QoS 0 (fire and forget) for reliable repeated testing.

    Args:
        printer: Printer dictionary
        gcode: G-code commands to send
        force_reconnect: If True, disconnect and reconnect before sending (helps clear stuck state)
    """
    printer_name = printer['name']
    serial_number = printer.get('serial_number', '')

    logging.info(f"[GCODE_TEST] Starting G-code send to Bambu printer {printer_name} (serial: {serial_number})")

    # Force reconnect if requested (helps clear stuck MQTT state)
    if force_reconnect and printer_name in MQTT_CLIENTS:
        logging.info(f"[GCODE_TEST] Force reconnecting {printer_name} to clear MQTT state...")
        try:
            old_client = MQTT_CLIENTS[printer_name]
            old_client.loop_stop()
            old_client.disconnect()
        except Exception as e:
            logging.warning(f"[GCODE_TEST] Error disconnecting old client: {e}")
        if printer_name in MQTT_CLIENTS:
            del MQTT_CLIENTS[printer_name]
        time.sleep(1)

    # Ensure connected
    if printer_name not in MQTT_CLIENTS or not MQTT_CLIENTS[printer_name].is_connected():
        logging.info(f"[GCODE_TEST] Printer {printer_name} not connected, attempting connection...")
        if not connect_bambu_printer(printer):
            logging.error(f"[GCODE_TEST] Cannot send G-code - Bambu printer {printer_name} not connected")
            with bambu_states_lock:
                if printer_name in BAMBU_PRINTER_STATES:
                    BAMBU_PRINTER_STATES[printer_name]['state'] = 'OFFLINE'
                    BAMBU_PRINTER_STATES[printer_name]['connected'] = False
                    BAMBU_PRINTER_STATES[printer_name]['disconnect_reason'] = 'Failed to connect for G-code command'
            return False
        # Wait for connection to stabilize
        time.sleep(2)

    client = MQTT_CLIENTS[printer_name]

    # Verify connection is actually established
    if not client.is_connected():
        logging.error(f"[GCODE_TEST] MQTT client reports not connected for {printer_name}")
        with bambu_states_lock:
            if printer_name in BAMBU_PRINTER_STATES:
                BAMBU_PRINTER_STATES[printer_name]['state'] = 'OFFLINE'
                BAMBU_PRINTER_STATES[printer_name]['connected'] = False
                BAMBU_PRINTER_STATES[printer_name]['disconnect_reason'] = 'MQTT client not connected'
        return False

    logging.info(f"[GCODE_TEST] MQTT connection confirmed for {printer_name}")

    try:
        # Parse G-code lines, removing comments and empty lines
        gcode_lines = []
        for line in gcode.strip().split('\n'):
            # Remove comments (everything after ;) and whitespace
            clean_line = line.split(';')[0].strip()
            if clean_line:  # Only add non-empty lines (actual G-code commands)
                gcode_lines.append(clean_line)

        if not gcode_lines:
            logging.warning(f"[GCODE_TEST] No valid G-code commands to send to Bambu printer {printer_name}")
            return False

        logging.info(f"[GCODE_TEST] Parsed {len(gcode_lines)} G-code commands for {printer_name}")
        logging.info(f"[GCODE_TEST] First 5 commands: {gcode_lines[:5]}")

        topic = f"device/{serial_number}/request"
        logging.info(f"[GCODE_TEST] Publishing to topic: {topic}")

        sent_count = 0
        failed_count = 0

        for i, line in enumerate(gcode_lines):
            seq_id = get_next_sequence_id(printer_name)
            command = {
                "print": {
                    "command": "gcode_line",
                    "sequence_id": seq_id,
                    "param": line
                }
            }

            # Use QoS 0 (fire and forget) to avoid message queue buildup
            # QoS 1 was causing messages to queue and block subsequent sends
            result = client.publish(topic, json.dumps(command), qos=0)

            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                logging.error(f"[GCODE_TEST] MQTT publish failed for '{line}': rc={result.rc}")
                failed_count += 1
                # Don't return immediately - try to send remaining commands
                continue

            sent_count += 1

            # Log every 10th command or first few
            if i < 3 or i % 10 == 0:
                logging.info(f"[GCODE_TEST] Sent ({i+1}/{len(gcode_lines)}): {line} [seq={seq_id}]")

            # Small delay between commands
            time.sleep(0.1)

        if failed_count > 0:
            logging.warning(f"[GCODE_TEST] Sent {sent_count}/{len(gcode_lines)} commands, {failed_count} failed for {printer_name}")
        else:
            logging.info(f"[GCODE_TEST] Successfully sent {sent_count}/{len(gcode_lines)} G-code commands to {printer_name}")

        # Request status update to see if printer state changed
        time.sleep(0.3)
        request_bambu_status(printer)

        return sent_count > 0

    except Exception as e:
        logging.error(f"[GCODE_TEST] Error sending G-code to Bambu printer {printer_name}: {str(e)}")
        import traceback
        logging.error(f"[GCODE_TEST] Traceback: {traceback.format_exc()}")
        return False

def send_bambu_ejection_gcode(printer: Dict[str, Any], end_gcode: str, force: bool = False) -> bool:
    """Send ejection G-code commands directly to Bambu printer via MQTT

    Args:
        printer: Printer dictionary
        end_gcode: G-code commands to send
        force: If True, bypass cooldown and in-progress checks (for debugging)
    """
    printer_name = printer['name']

    # CRITICAL: Check if we're already ejecting or have recently ejected
    with bambu_states_lock:
        if printer_name in BAMBU_PRINTER_STATES:
            # Check if ejection is already in progress
            if BAMBU_PRINTER_STATES[printer_name].get('ejection_in_progress', False):
                if force:
                    logging.warning(f"Force-clearing ejection_in_progress flag for Bambu printer {printer_name}")
                    BAMBU_PRINTER_STATES[printer_name]['ejection_in_progress'] = False
                else:
                    logging.warning(f"Ejection already in progress for Bambu printer {printer_name} - skipping (use force=True to override)")
                    return False

            # Check if we recently completed ejection (within last 10 seconds for safety, reduced from 60)
            # This prevents rapid double-triggering but allows reasonable re-testing
            cooldown_seconds = 10
            last_ejection = BAMBU_PRINTER_STATES[printer_name].get('last_ejection_time', 0)
            time_since_last = time.time() - last_ejection
            if time_since_last < cooldown_seconds:
                if force:
                    logging.warning(f"Force-bypassing {cooldown_seconds}s cooldown for Bambu printer {printer_name} (last ejection {time_since_last:.1f}s ago)")
                else:
                    logging.warning(f"Ejection cooldown active for Bambu printer {printer_name} - {cooldown_seconds - time_since_last:.1f}s remaining (use force=True to override)")
                    return False

            # Mark ejection as in progress
            BAMBU_PRINTER_STATES[printer_name]['ejection_in_progress'] = True

    # Ensure connected
    if printer_name not in MQTT_CLIENTS or not MQTT_CLIENTS[printer_name].is_connected():
        logging.error(f"Cannot send ejection G-code - Bambu printer {printer_name} not connected")
        with bambu_states_lock:
            if printer_name in BAMBU_PRINTER_STATES:
                BAMBU_PRINTER_STATES[printer_name]['ejection_in_progress'] = False
                # CRITICAL FIX: Update state to OFFLINE when connection fails
                BAMBU_PRINTER_STATES[printer_name]['state'] = 'OFFLINE'
                BAMBU_PRINTER_STATES[printer_name]['connected'] = False
                BAMBU_PRINTER_STATES[printer_name]['disconnect_reason'] = 'Not connected for ejection G-code'
        return False

    client = MQTT_CLIENTS[printer_name]

    try:
        # Parse the G-code into individual commands
        gcode_lines = []
        for line in end_gcode.strip().split('\n'):
            # Remove comments and whitespace
            line = line.split(';')[0].strip()
            if line:  # Only add non-empty lines
                gcode_lines.append(line)

        # AUTOMATIC M400 ADDITION - Only for Bambu printers
        # Check if M400 is already present
        has_m400 = any('M400' in line.upper() for line in gcode_lines)

        if not has_m400:
            # Automatically append M400 to ensure completion detection
            gcode_lines.append('M400')
            logging.info(f"Automatically added M400 to ejection G-code for Bambu printer {printer_name}")

        logging.info(f"Sending {len(gcode_lines)} ejection G-code lines to Bambu printer {printer_name}")

        # Update printer state to EJECTING
        with bambu_states_lock:
            if printer_name in BAMBU_PRINTER_STATES:
                BAMBU_PRINTER_STATES[printer_name]['state'] = 'EJECTING'
                BAMBU_PRINTER_STATES[printer_name]['ejection_complete'] = False
                BAMBU_PRINTER_STATES[printer_name]['ejection_start_time'] = time.time()
                # Mark that we're waiting for M400 completion
                BAMBU_PRINTER_STATES[printer_name]['waiting_for_m400'] = True

        # Send each command
        for line in gcode_lines:
            command = {
                "print": {
                    "command": "gcode_line",
                    "sequence_id": get_next_sequence_id(printer_name),
                    "param": line
                }
            }

            topic = f"device/{printer['serial_number']}/request"
            result = client.publish(topic, json.dumps(command), qos=0)

            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                logging.error(f"Failed to send G-code line '{line}' to Bambu printer {printer_name}: {result.rc}")
                with bambu_states_lock:
                    BAMBU_PRINTER_STATES[printer_name]['ejection_in_progress'] = False
                    BAMBU_PRINTER_STATES[printer_name]['waiting_for_m400'] = False
                return False

            # Small delay between commands to avoid overwhelming the printer
            time.sleep(0.1)

        logging.info(f"Successfully sent ejection G-code to Bambu printer {printer_name}")

        # Mark ejection as sent but not complete
        with bambu_states_lock:
            BAMBU_PRINTER_STATES[printer_name]['ejection_in_progress'] = False
            # Don't set last_ejection_time until actual completion

        return True

    except Exception as e:
        logging.error(f"Error sending ejection G-code to Bambu printer {printer_name}: {str(e)}")
        with bambu_states_lock:
            BAMBU_PRINTER_STATES[printer_name]['ejection_in_progress'] = False
            BAMBU_PRINTER_STATES[printer_name]['waiting_for_m400'] = False
        return False

def stop_bambu_print(printer: Dict[str, Any]) -> bool:
    """Stop current print on Bambu printer"""
    printer_name = printer['name']

    if printer_name not in MQTT_CLIENTS or not MQTT_CLIENTS[printer_name].is_connected():
        logging.error(f"Cannot stop print - Bambu printer {printer_name} not connected")
        return False

    client = MQTT_CLIENTS[printer_name]

    try:
        command = {
            "print": {
                "command": "stop",
                "sequence_id": get_next_sequence_id(printer_name),
                "param": ""
            }
        }

        topic = f"device/{printer['serial_number']}/request"
        client.publish(topic, json.dumps(command), qos=0)

        logging.info(f"Sent stop command to Bambu printer {printer_name}")
        return True

    except Exception as e:
        logging.error(f"Error stopping print on Bambu printer {printer_name}: {str(e)}")
        return False

def pause_bambu_print(printer: Dict[str, Any]) -> bool:
    """Pause current print on Bambu printer"""
    printer_name = printer['name']

    if printer_name not in MQTT_CLIENTS or not MQTT_CLIENTS[printer_name].is_connected():
        logging.error(f"Cannot pause print - Bambu printer {printer_name} not connected")
        return False

    client = MQTT_CLIENTS[printer_name]

    try:
        command = {
            "print": {
                "command": "pause",
                "sequence_id": get_next_sequence_id(printer_name),
                "param": ""
            }
        }

        topic = f"device/{printer['serial_number']}/request"
        client.publish(topic, json.dumps(command), qos=0)

        logging.info(f"Sent pause command to Bambu printer {printer_name}")
        return True

    except Exception as e:
        logging.error(f"Error pausing print on Bambu printer {printer_name}: {str(e)}")
        return False

def resume_bambu_print(printer: Dict[str, Any]) -> bool:
    """Resume paused print on Bambu printer"""
    printer_name = printer['name']

    if printer_name not in MQTT_CLIENTS or not MQTT_CLIENTS[printer_name].is_connected():
        logging.error(f"Cannot resume print - Bambu printer {printer_name} not connected")
        return False

    client = MQTT_CLIENTS[printer_name]

    try:
        command = {
            "print": {
                "command": "resume",
                "sequence_id": get_next_sequence_id(printer_name),
                "param": ""
            }
        }

        topic = f"device/{printer['serial_number']}/request"
        client.publish(topic, json.dumps(command), qos=0)

        logging.info(f"Sent resume command to Bambu printer {printer_name}")
        return True

    except Exception as e:
        logging.error(f"Error resuming print on Bambu printer {printer_name}: {str(e)}")
        return False

def check_bambu_connection(printer_name: str) -> bool:
    """Check if a Bambu printer is actually connected"""
    if printer_name not in MQTT_CLIENTS:
        return False

    client = MQTT_CLIENTS[printer_name]
    if not client.is_connected():
        return False

    # Check if we've received recent data
    with bambu_states_lock:
        if printer_name in BAMBU_PRINTER_STATES:
            last_seen = BAMBU_PRINTER_STATES[printer_name].get('last_seen', 0)
            if time.time() - last_seen > 60:  # No data for 60 seconds
                logging.warning(f"Bambu printer {printer_name} hasn't sent data in 60 seconds")
                return False

    return True

def maintain_bambu_connections():
    """Periodically check and maintain Bambu printer connections"""
    while True:
        try:
            time.sleep(30)  # Check every 30 seconds

            for printer_name in list(MQTT_CLIENTS.keys()):
                if not check_bambu_connection(printer_name):
                    logging.info(f"Bambu printer {printer_name} connection lost, attempting reconnect")
                    # Get printer info from state
                    from services.state import PRINTERS, printers_rwlock, ReadLock
                    with ReadLock(printers_rwlock):
                        printer = next((p for p in PRINTERS if p['name'] == printer_name), None)

                    if printer and printer.get('type') == 'bambu':
                        disconnect_bambu_printer(printer_name)
                        time.sleep(2)
                        connect_bambu_printer(printer)

        except Exception as e:
            logging.error(f"Error in maintain_bambu_connections: {str(e)}")

# Start the connection maintenance thread
threading.Thread(target=maintain_bambu_connections, daemon=True).start()

def disconnect_all_bambu_printers():
    """Disconnect all Bambu printers - call during shutdown"""
    for printer_name in list(MQTT_CLIENTS.keys()):
        disconnect_bambu_printer(printer_name)
