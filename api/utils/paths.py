"""Centralized PrintQue data directory resolution."""

import os


def get_data_base() -> str:
    """Parent directory for PrintQueData (DATA_DIR env or user home)."""
    return os.environ.get('DATA_DIR', os.path.expanduser('~'))


def get_data_dir() -> str:
    """Writable PrintQue data root ({base}/PrintQueData)."""
    root = os.path.join(get_data_base(), 'PrintQueData')
    os.makedirs(root, exist_ok=True)
    return root


def get_user_home_printque_dir() -> str:
    """Real user data directory, ignoring DATA_DIR (for test safety checks)."""
    return os.path.join(os.path.expanduser('~'), 'PrintQueData')


def get_logs_dir() -> str:
    root = os.path.join(get_data_dir(), 'logs')
    os.makedirs(root, exist_ok=True)
    return root


def get_certs_dir() -> str:
    root = os.path.join(get_data_dir(), 'certs')
    os.makedirs(root, exist_ok=True)
    return root


def get_uploads_dir() -> str:
    root = os.path.join(get_data_dir(), 'uploads')
    os.makedirs(root, exist_ok=True)
    return root


def get_backups_dir() -> str:
    root = os.path.join(get_data_dir(), 'backups')
    os.makedirs(root, exist_ok=True)
    return root


def get_log_file() -> str:
    return os.path.join(get_data_dir(), 'app.log')


def get_printers_file() -> str:
    return os.path.join(get_data_dir(), 'printers.json')


def get_total_filament_file() -> str:
    return os.path.join(get_data_dir(), 'total_filament.json')


def get_orders_file() -> str:
    return os.path.join(get_data_dir(), 'orders.json')


def get_library_file() -> str:
    return os.path.join(get_data_dir(), 'library.json')


def get_queue_file() -> str:
    return os.path.join(get_data_dir(), 'queue.json')


def get_ejection_codes_file() -> str:
    return os.path.join(get_data_dir(), 'ejection_codes.json')


def get_ejection_paused_file() -> str:
    return os.path.join(get_data_dir(), 'ejection_paused.json')


def get_default_settings_file() -> str:
    return os.path.join(get_data_dir(), 'default_settings.json')


def get_logging_settings_file() -> str:
    return os.path.join(get_data_dir(), 'logging_settings.json')


def get_print_history_file() -> str:
    return os.path.join(get_data_dir(), 'print_history.json')


class LazyPath:
    """Path resolved on each use so DATA_DIR is respected after import."""

    def __init__(self, getter):
        self._getter = getter

    def __fspath__(self):
        return self._getter()

    def __str__(self):
        return self._getter()

    def __repr__(self):
        return repr(self._getter())

    def __eq__(self, other):
        return str(self) == str(other)

    def __hash__(self):
        return hash(str(self))
