"""
Shared pytest fixtures for PrintQue API tests.

DATA_DIR is set in pytest_configure before test modules import services.state.
"""

import atexit
import json
import os
import shutil
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# Add api directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

_TEST_DATA_BASE = None


def _cleanup_test_data_dir():
    if _TEST_DATA_BASE:
        shutil.rmtree(_TEST_DATA_BASE, ignore_errors=True)


def pytest_configure(config):
    """Set DATA_DIR before collection imports any test module that loads state."""
    global _TEST_DATA_BASE
    if _TEST_DATA_BASE is None:
        _TEST_DATA_BASE = tempfile.mkdtemp(prefix='printque_pytest_')
        os.environ['DATA_DIR'] = _TEST_DATA_BASE
        atexit.register(_cleanup_test_data_dir)


def _printque_data_root(base_dir: str) -> str:
    """Match production layout: {DATA_DIR}/PrintQueData."""
    root = os.path.join(base_dir, 'PrintQueData')
    os.makedirs(root, exist_ok=True)
    return root


@pytest.fixture(scope='session')
def temp_data_dir():
    """Session temp base; DATA_DIR is set in pytest_configure."""
    if _TEST_DATA_BASE is None:
        pytest_configure(None)
    yield _TEST_DATA_BASE
    _cleanup_test_data_dir()


@pytest.fixture(autouse=True)
def isolate_state(temp_data_dir, monkeypatch):
    """Ensure DATA_DIR points at the session temp dir and seed data files."""
    monkeypatch.setenv('DATA_DIR', temp_data_dir)
    data_root = _printque_data_root(temp_data_dir)

    for filename in [
        'printers.json', 'orders.json', 'library.json', 'queue.json',
        'total_filament.json', 'ejection_codes.json',
    ]:
        filepath = os.path.join(data_root, filename)
        if not os.path.exists(filepath):
            with open(filepath, 'w', encoding='utf-8') as f:
                if filename == 'total_filament.json':
                    json.dump({'total_filament_used_g': 0}, f)
                else:
                    json.dump([], f)


@pytest.fixture
def app(temp_data_dir, monkeypatch):
    """Create Flask application for testing."""
    monkeypatch.setenv('DATA_DIR', temp_data_dir)

    from app import app as flask_app

    flask_app.config['TESTING'] = True
    uploads = os.path.join(_printque_data_root(temp_data_dir), 'uploads')
    flask_app.config['UPLOAD_FOLDER'] = uploads
    os.makedirs(uploads, exist_ok=True)

    yield flask_app


@pytest.fixture
def client(app):
    """Create Flask test client."""
    return app.test_client()


@pytest.fixture
def mock_printers():
    """Sample printer data for testing."""
    return [
        {
            'name': 'Test Printer 1',
            'ip': '192.168.1.100',
            'type': 'prusa',
            'group': 'Default',
            'state': 'READY',
            'status': 'Ready',
            'temps': {'nozzle': 0, 'bed': 0},
            'progress': 0,
            'time_remaining': 0,
            'z_height': 0,
            'file': None,
            'filament_used_g': 0,
            'service_mode': False,
            'api_key': 'encrypted_key_1',
        },
        {
            'name': 'Test Printer 2',
            'ip': '192.168.1.101',
            'type': 'bambu',
            'group': 'Default',
            'state': 'PRINTING',
            'status': 'Printing',
            'temps': {'nozzle': 210, 'bed': 60},
            'progress': 45,
            'time_remaining': 3600,
            'z_height': 12.5,
            'file': 'test_print.gcode',
            'filament_used_g': 25.5,
            'service_mode': False,
            'device_id': 'BAMBU123',
            'access_code': 'encrypted_code',
        },
    ]


@pytest.fixture
def mock_orders():
    """Sample order data for testing."""
    return [
        {
            'id': 1,
            'filename': 'test_part.gcode',
            'name': 'Test Order 1',
            'filepath': '/uploads/test_part.gcode',
            'quantity': 5,
            'sent': 2,
            'status': 'partial',
            'filament_g': 15.5,
            'groups': ['Default'],
            'ejection_enabled': True,
            'ejection_code_id': 'ejection-1',
            'deleted': False,
        },
        {
            'id': 2,
            'filename': 'another_part.3mf',
            'name': None,
            'filepath': '/uploads/another_part.3mf',
            'quantity': 1,
            'sent': 0,
            'status': 'pending',
            'filament_g': 8.2,
            'groups': ['Default'],
            'ejection_enabled': False,
            'deleted': False,
        },
    ]


@pytest.fixture
def mock_ejection_codes():
    """Sample ejection code presets for testing."""
    return [
        {
            'id': 'ejection-1',
            'name': 'Standard Eject',
            'gcode': 'G28 X Y\nM84',
            'created_at': '2024-01-01T00:00:00',
        },
        {
            'id': 'ejection-2',
            'name': 'Bed Slide',
            'gcode': 'G1 Y200 F3000\nG28 X',
            'created_at': '2024-01-02T00:00:00',
        },
    ]


@pytest.fixture
def populated_state(temp_data_dir, mock_printers, mock_orders):
    """Populate state files with test data."""
    data_root = _printque_data_root(temp_data_dir)
    printers_file = os.path.join(data_root, 'printers.json')
    orders_file = os.path.join(data_root, 'orders.json')

    with open(printers_file, 'w', encoding='utf-8') as f:
        json.dump(mock_printers, f)

    with open(orders_file, 'w', encoding='utf-8') as f:
        json.dump(mock_orders, f)

    return {
        'printers_file': printers_file,
        'orders_file': orders_file,
        'printers': mock_printers,
        'orders': mock_orders,
    }


@pytest.fixture
def mock_socketio():
    """Mock SocketIO for testing real-time events."""
    mock = MagicMock()
    mock.emit = MagicMock()
    return mock


@pytest.fixture
def sample_gcode_file(temp_data_dir):
    """Create a sample gcode file for upload testing."""
    filepath = os.path.join(temp_data_dir, 'test_upload.gcode')
    gcode_content = """; Sample G-code for testing
; filament used [g] = 10.5
G28 ; Home
G1 Z5 F3000
G1 X100 Y100 F6000
M104 S200
M140 S60
; End of test file
"""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(gcode_content)
    return filepath


@pytest.fixture
def mock_mqtt_client():
    """Mock MQTT client for Bambu printer tests."""
    with patch('paho.mqtt.client.Client') as mock_client:
        instance = MagicMock()
        mock_client.return_value = instance
        instance.connect.return_value = 0
        instance.is_connected.return_value = True
        yield instance


@pytest.fixture
def mock_aiohttp_session():
    """Mock aiohttp session for async HTTP tests."""
    with patch('aiohttp.ClientSession') as mock_session:
        instance = MagicMock()
        mock_session.return_value.__aenter__ = MagicMock(return_value=instance)
        mock_session.return_value.__aexit__ = MagicMock(return_value=None)
        yield instance
