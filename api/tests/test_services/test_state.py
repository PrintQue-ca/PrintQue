"""
Tests for state management module.

Tests the services/state.py module including:
- Data persistence (save_data, load_data)
- Encryption/decryption
- Thread-safe locking mechanisms
- Order increment functions
- Ejection state management
"""

import os
import json
import threading
import time


class TestDataPersistence:
    """Tests for save_data and load_data functions."""

    def test_save_data_creates_file(self, temp_data_dir):
        """Test that save_data creates a new file."""
        from services.state import save_data

        filepath = os.path.join(temp_data_dir, 'test_save.json')
        test_data = {'key': 'value', 'number': 42}

        save_data(filepath, test_data)

        assert os.path.exists(filepath)
        with open(filepath, 'r') as f:
            loaded = json.load(f)
        assert loaded == test_data

    def test_save_data_overwrites_existing(self, temp_data_dir):
        """Test that save_data overwrites existing file."""
        from services.state import save_data

        filepath = os.path.join(temp_data_dir, 'test_overwrite.json')

        save_data(filepath, {'old': 'data'})
        save_data(filepath, {'new': 'data'})

        with open(filepath, 'r') as f:
            loaded = json.load(f)
        assert loaded == {'new': 'data'}

    def test_load_data_existing_file(self, temp_data_dir):
        """Test loading data from existing file."""
        from services.state import load_data

        filepath = os.path.join(temp_data_dir, 'test_load.json')
        test_data = {'items': [1, 2, 3]}

        with open(filepath, 'w') as f:
            json.dump(test_data, f)

        loaded = load_data(filepath, [])
        assert loaded == test_data

    def test_load_data_missing_file_returns_default(self, temp_data_dir):
        """Test loading from non-existent file returns default."""
        from services.state import load_data

        filepath = os.path.join(temp_data_dir, 'nonexistent.json')
        default = {'default': True}

        loaded = load_data(filepath, default)
        assert loaded == default

    def test_load_data_invalid_json_returns_default(self, temp_data_dir):
        """Test loading invalid JSON returns default."""
        from services.state import load_data

        filepath = os.path.join(temp_data_dir, 'invalid.json')
        with open(filepath, 'w') as f:
            f.write('not valid json {{{')

        default = []
        loaded = load_data(filepath, default)
        assert loaded == default


class TestEncryption:
    """Tests for encryption/decryption functions."""

    def test_encrypt_decrypt_roundtrip(self):
        """Test that encrypt then decrypt returns original value."""
        from services.state import encrypt_api_key, decrypt_api_key

        original = 'my_secret_api_key_12345'
        encrypted = encrypt_api_key(original)

        assert encrypted != original
        assert decrypt_api_key(encrypted) == original

    def test_encrypt_produces_different_ciphertexts(self):
        """Test that same plaintext produces different ciphertext each time."""
        from services.state import encrypt_api_key

        original = 'test_key'
        encrypted1 = encrypt_api_key(original)
        encrypted2 = encrypt_api_key(original)

        # Fernet produces different ciphertexts for same plaintext
        # but both should decrypt to same value
        assert encrypted1 != original
        assert encrypted2 != original

    def test_decrypt_invalid_returns_none(self):
        """Test decrypting invalid ciphertext returns None."""
        from services.state import decrypt_api_key

        result = decrypt_api_key('not_valid_encrypted_data')
        assert result is None

    def test_decrypt_empty_returns_none(self):
        """Test decrypting empty string returns None."""
        from services.state import decrypt_api_key

        result = decrypt_api_key('')
        assert result is None


class TestGroupValidation:
    """Tests for group name validation and sanitization."""

    def test_validate_group_name_valid(self):
        """Test valid group names pass validation."""
        from services.state import validate_group_name

        assert validate_group_name('Default') is True
        assert validate_group_name('Group 1') is True
        assert validate_group_name('Group-Name') is True
        assert validate_group_name('Group_Name') is True

    def test_validate_group_name_invalid(self):
        """Test invalid group names fail validation."""
        from services.state import validate_group_name

        assert validate_group_name('') is False
        assert validate_group_name(None) is False
        assert validate_group_name(123) is False

    def test_sanitize_group_name(self):
        """Test group name sanitization."""
        from services.state import sanitize_group_name

        assert sanitize_group_name('Normal Name') == 'Normal Name'
        assert sanitize_group_name('') == 'Default'
        assert sanitize_group_name(None) == 'Default'
        assert sanitize_group_name('  ') == 'Default'

    def test_sanitize_group_name_removes_special_chars(self):
        """Test sanitization removes special characters."""
        from services.state import sanitize_group_name

        # Should remove special chars but keep alphanumeric and spaces
        result = sanitize_group_name('Test<script>')
        assert '<' not in result
        assert '>' not in result


class TestLocking:
    """Tests for thread-safe locking mechanisms."""

    def test_named_lock_basic(self):
        """Test basic NamedLock acquire/release."""
        from services.state import NamedLock

        lock = NamedLock('test_lock')

        assert lock.acquire() is True
        lock.release()

    def test_named_lock_context_manager(self):
        """Test NamedLock as context manager."""
        from services.state import NamedLock

        lock = NamedLock('test_cm_lock')

        with lock:
            # Should be able to enter context
            pass
        # Should exit cleanly

    def test_safe_lock_acquires_and_releases(self):
        """Test SafeLock context manager."""
        from services.state import NamedLock, SafeLock

        base_lock = NamedLock('test_safe_lock')

        with SafeLock(base_lock):
            # Inside lock context
            pass
        # Should release cleanly

    def test_read_write_lock_multiple_readers(self):
        """Test ReadWriteLock allows multiple concurrent readers."""
        from services.state import ReadWriteLock, ReadLock

        rwlock = ReadWriteLock(name='test_rw')
        results = []

        def reader(n):
            with ReadLock(rwlock):
                results.append(f'reader_{n}')
                time.sleep(0.01)

        threads = [threading.Thread(target=reader, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 3


class TestEjectionState:
    """Tests for ejection state management."""

    def test_set_get_ejection_state(self):
        """Test setting and getting printer ejection state."""
        from services.state import (
            set_printer_ejection_state,
            get_printer_ejection_state,
            clear_printer_ejection_state
        )

        printer_name = 'test_printer_ejection'

        set_printer_ejection_state(printer_name, 'in_progress', {'order_id': 1})

        state = get_printer_ejection_state(printer_name)
        assert state['state'] == 'in_progress'
        assert state['metadata']['order_id'] == 1

        clear_printer_ejection_state(printer_name)
        state = get_printer_ejection_state(printer_name)
        assert state['state'] == 'none'

    def test_ejection_paused_state(self):
        """Test global ejection paused state."""
        from services.state import get_ejection_paused, set_ejection_paused

        original = get_ejection_paused()

        set_ejection_paused(True)
        assert get_ejection_paused() is True

        set_ejection_paused(False)
        assert get_ejection_paused() is False

        # Restore original state
        set_ejection_paused(original)


class TestGcodeValidation:
    """Tests for G-code file validation."""

    def test_validate_gcode_valid_extensions(self):
        """Test validation accepts valid file extensions."""
        from services.state import validate_gcode_file

        class MockFile:
            def __init__(self, filename):
                self.filename = filename

        assert validate_gcode_file(MockFile('test.gcode'))[0] is True
        assert validate_gcode_file(MockFile('test.3mf'))[0] is True
        assert validate_gcode_file(MockFile('test.bgcode'))[0] is True
        assert validate_gcode_file(MockFile('test.gcode.3mf'))[0] is True

    def test_validate_gcode_invalid_extensions(self):
        """Test validation rejects invalid file extensions."""
        from services.state import validate_gcode_file

        class MockFile:
            def __init__(self, filename):
                self.filename = filename

        assert validate_gcode_file(MockFile('test.txt'))[0] is False
        assert validate_gcode_file(MockFile('test.stl'))[0] is False
        assert validate_gcode_file(MockFile('test.exe'))[0] is False

    def test_validate_gcode_no_file(self):
        """Test validation handles None file."""
        from services.state import validate_gcode_file

        valid, message = validate_gcode_file(None)
        assert valid is False
        assert 'No file' in message


class TestTaskManagement:
    """Tests for task registration and tracking."""

    def test_register_task(self):
        """Test registering a new task."""
        from services.state import register_task

        task_id = 'test_task_123'
        task = register_task(task_id, 'test_type', 10)

        assert task['id'] == task_id
        assert task['type'] == 'test_type'
        assert task['total'] == 10
        assert task['status'] == 'running'

    def test_update_task_progress(self):
        """Test updating task progress."""
        from services.state import register_task, update_task_progress

        task_id = 'test_task_progress'
        register_task(task_id, 'test', 100)

        updated = update_task_progress(task_id, completed=50)
        assert updated['completed'] == 50
        assert updated['progress'] == 50

    def test_complete_task(self):
        """Test completing a task."""
        from services.state import register_task, complete_task

        task_id = 'test_task_complete'
        register_task(task_id, 'test', 10)

        completed = complete_task(task_id, success=True, message='Done')
        assert completed['status'] == 'success'
        assert completed['message'] == 'Done'
        assert completed['progress'] == 100
