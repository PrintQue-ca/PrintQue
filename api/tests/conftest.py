"""
Shared pytest fixtures for PrintQue API tests.

This module provides fixtures for:
- Flask test client
- Mock printer data
- Mock order data
- Temporary data directories
- State isolation
"""

import os
import sys
import json
import pytest
import tempfile
import shutil
from unittest.mock import patch, MagicMock

# Add api directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture(scope='session')
def temp_data_dir():
    """Create a temporary directory for test data that persists across tests."""
    temp_dir = tempfile.mkdtemp(prefix='printque_test_')
    yield temp_dir
    # Cleanup after all tests
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolate_state(temp_data_dir, monkeypatch):
    """Isolate state for each test by using temp directory and resetting globals."""
    # Patch data directory paths before importing state
    monkeypatch.setenv('DATA_DIR', temp_data_dir)
    
    # Create empty data files
    for filename in ['printers.json', 'orders.json', 'total_filament.json', 'ejection_codes.json']:
        filepath = os.path.join(temp_data_dir, filename)
        if not os.path.exists(filepath):
            with open(filepath, 'w') as f:
                if filename == 'total_filament.json':
                    json.dump({'total_filament_used_g': 0}, f)
                else:
                    json.dump([], f)


@pytest.fixture
def app(temp_data_dir, monkeypatch):
    """Create Flask application for testing."""
    # Set environment before imports
    monkeypatch.setenv('DATA_DIR', temp_data_dir)
    
    # Mock eventlet monkey patching
    with patch('eventlet.monkey_patch'):
        # Import after patching
        from app import app as flask_app
        
        flask_app.config['TESTING'] = True
        flask_app.config['UPLOAD_FOLDER'] = os.path.join(temp_data_dir, 'uploads')
        os.makedirs(flask_app.config['UPLOAD_FOLDER'], exist_ok=True)
        
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
            'api_key': 'encrypted_key_1'
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
            'access_code': 'encrypted_code'
        }
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
            'end_gcode': 'G28 X Y',
            'deleted': False
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
            'deleted': False
        }
    ]


@pytest.fixture
def mock_ejection_codes():
    """Sample ejection code presets for testing."""
    return [
        {
            'id': 'ejection-1',
            'name': 'Standard Eject',
            'gcode': 'G28 X Y\nM84',
            'created_at': '2024-01-01T00:00:00'
        },
        {
            'id': 'ejection-2',
            'name': 'Bed Slide',
            'gcode': 'G1 Y200 F3000\nG28 X',
            'created_at': '2024-01-02T00:00:00'
        }
    ]


@pytest.fixture
def populated_state(temp_data_dir, mock_printers, mock_orders):
    """Populate state files with test data."""
    printers_file = os.path.join(temp_data_dir, 'printers.json')
    orders_file = os.path.join(temp_data_dir, 'orders.json')
    
    with open(printers_file, 'w') as f:
        json.dump(mock_printers, f)
    
    with open(orders_file, 'w') as f:
        json.dump(mock_orders, f)
    
    return {
        'printers_file': printers_file,
        'orders_file': orders_file,
        'printers': mock_printers,
        'orders': mock_orders
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
    with open(filepath, 'w') as f:
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
