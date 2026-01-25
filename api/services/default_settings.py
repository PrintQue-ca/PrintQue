import os
import json
import logging

# Use the same user data directory for settings as other files
USER_DATA_DIR = os.path.join(os.path.expanduser("~"), "PrintQueData")
DEFAULT_SETTINGS_FILE = os.path.join(USER_DATA_DIR, "default_settings.json")

def load_default_settings():
    """Load default settings from file or return defaults if file doesn't exist"""
    # Ensure directory exists
    os.makedirs(USER_DATA_DIR, exist_ok=True)

    if os.path.exists(DEFAULT_SETTINGS_FILE):
        try:
            with open(DEFAULT_SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading default settings from {DEFAULT_SETTINGS_FILE}: {e}")

    # Default settings if file doesn't exist or can't be loaded
    return {
        "default_end_gcode": "",
        "default_ejection_enabled": False  # Already False as requested
    }

def save_default_settings(settings):
    """Save default settings to file"""
    try:
        # Ensure directory exists
        os.makedirs(USER_DATA_DIR, exist_ok=True)

        with open(DEFAULT_SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
        logging.debug(f"Saved default settings to {DEFAULT_SETTINGS_FILE}: {settings}")
        return True
    except Exception as e:
        logging.error(f"Error saving default settings to {DEFAULT_SETTINGS_FILE}: {e}")
        return False
