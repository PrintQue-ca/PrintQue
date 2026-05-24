import json
import logging
import os

from utils.paths import LazyPath, get_data_dir, get_default_settings_file

DEFAULT_SETTINGS_FILE = LazyPath(get_default_settings_file)

DEFAULT_EJECTION_GCODE = """\
; A1 Mini — G90 absolute machine coords (center ≈ X180 Y180). Sent verbatim via MQTT.
; Bed cooldown via PrintQue job settings. M211 allows moves past soft limits (e.g. X60, Y-4).
; Park left with X60 (X50 may leave printable area). Tune back Y if sweep is too short.
G90
M211 X0 Y0 Z0
G1 X60 Z1 F6000
G1 Y300 F6000
G1 Y-4 F300
M400
M211 S1
"""


def _default_settings_dict():
    return {
        "default_ejection_code_id": None,
        "default_ejection_enabled": False,
    }


def migrate_default_settings(settings):
    """Migrate legacy default_end_gcode to default_ejection_code_id."""
    if settings.get('default_ejection_code_id'):
        return settings

    legacy_gcode = (settings.get('default_end_gcode') or '').strip()
    if not legacy_gcode:
        settings.pop('default_end_gcode', None)
        settings.setdefault('default_ejection_code_id', None)
        return settings

    # Deferred import avoids circular dependency at module load
    from services.state import auto_save_ejection_code, backup_data_files_before_migration

    backup_data_files_before_migration('default_settings.json', 'ejection_codes.json')
    code = auto_save_ejection_code(legacy_gcode, 'Default')
    settings['default_ejection_code_id'] = code['id']
    settings.pop('default_end_gcode', None)
    save_default_settings(settings)
    logging.info(f"Migrated default_end_gcode to default_ejection_code_id: {code['id']}")
    return settings


def load_default_settings():
    """Load default settings from file or return defaults if file doesn't exist."""
    settings_path = get_default_settings_file()
    os.makedirs(get_data_dir(), exist_ok=True)

    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                return migrate_default_settings(settings)
        except Exception as e:
            logging.error(f"Error loading default settings from {settings_path}: {e}")

    return _default_settings_dict()


def save_default_settings(settings):
    """Save default settings to file"""
    settings_path = get_default_settings_file()
    try:
        os.makedirs(get_data_dir(), exist_ok=True)

        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=4)
        logging.debug(f"Saved default settings to {settings_path}: {settings}")
        return True
    except Exception as e:
        logging.error(f"Error saving default settings to {settings_path}: {e}")
        return False
