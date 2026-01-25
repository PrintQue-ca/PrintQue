"""
Tests for system API routes.

Tests the /api/v1/system/* endpoints including:
- System stats
- License info
- System info
- Groups
- Logging configuration
"""

from unittest.mock import patch


class TestSystemStats:
    """Tests for /api/v1/system/stats endpoint."""

    def test_get_stats_empty_state(self, client):
        """Test stats endpoint returns correct structure with empty state."""
        with patch('routes.PRINTERS', []), \
             patch('routes.ORDERS', []):
            response = client.get('/api/v1/system/stats')

            assert response.status_code == 200
            data = response.get_json()

            # Verify required fields exist
            assert 'total_filament' in data
            assert 'printers_count' in data
            assert 'library_count' in data
            assert 'in_queue_count' in data
            assert 'active_prints' in data
            assert 'idle_printers' in data
            assert 'completed_today' in data

    def test_get_stats_with_printers(self, client, mock_printers):
        """Test stats reflect printer counts correctly."""
        with patch('routes.PRINTERS', mock_printers), \
             patch('routes.ORDERS', []):
            response = client.get('/api/v1/system/stats')

            assert response.status_code == 200
            data = response.get_json()

            assert data['printers_count'] == 2
            # One printer is PRINTING, one is READY
            assert data['active_prints'] == 1
            assert data['idle_printers'] == 1


class TestSystemLicense:
    """Tests for /api/v1/system/license endpoint."""

    def test_get_license_open_source(self, client):
        """Test license endpoint returns open source edition info."""
        response = client.get('/api/v1/system/license')

        assert response.status_code == 200
        data = response.get_json()

        assert data['tier'] == 'OPEN_SOURCE'
        assert data['valid'] is True
        assert data['max_printers'] == -1  # Unlimited
        assert 'all' in data['features']


class TestSystemInfo:
    """Tests for /api/v1/system/info endpoint."""

    def test_get_system_info(self, client):
        """Test system info returns expected fields."""
        response = client.get('/api/v1/system/info')

        assert response.status_code == 200
        data = response.get_json()

        assert 'version' in data
        assert 'uptime' in data
        assert 'memory_usage' in data
        assert 'cpu_usage' in data
        assert 'python_version' in data
        assert 'platform' in data

        # Uptime should be a positive number
        assert data['uptime'] >= 0


class TestSystemGroups:
    """Tests for /api/v1/system/groups endpoints."""

    def test_get_groups_empty(self, client):
        """Test getting groups with no printers returns empty list."""
        with patch('routes.PRINTERS', []):
            response = client.get('/api/v1/system/groups')

            assert response.status_code == 200
            data = response.get_json()
            assert isinstance(data, list)

    def test_get_groups_with_printers(self, client, mock_printers):
        """Test getting groups extracts unique groups from printers."""
        with patch('routes.PRINTERS', mock_printers):
            response = client.get('/api/v1/system/groups')

            assert response.status_code == 200
            data = response.get_json()

            # Should have Default group from mock printers
            group_names = [g['name'] for g in data]
            assert 'Default' in group_names

    def test_create_group(self, client):
        """Test creating a new group."""
        response = client.post('/api/v1/system/groups',
                              json={'name': 'Test Group'})

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['name'] == 'Test Group'

    def test_create_group_sanitizes_name(self, client):
        """Test group name is sanitized."""
        response = client.post('/api/v1/system/groups',
                              json={'name': 'Test<script>Group'})

        assert response.status_code == 200
        data = response.get_json()
        # Should have sanitized the name (removed special chars)
        assert '<script>' not in data['name']


class TestEjectionStatus:
    """Tests for /api/v1/ejection/* endpoints."""

    def test_get_ejection_status(self, client):
        """Test getting ejection status."""
        response = client.get('/api/v1/ejection/status')

        assert response.status_code == 200
        data = response.get_json()

        assert 'paused' in data
        assert 'status' in data
        assert data['status'] in ['paused', 'active']

    def test_pause_ejection(self, client):
        """Test pausing ejection."""
        response = client.post('/api/v1/ejection/pause')

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

    def test_resume_ejection(self, client):
        """Test resuming ejection."""
        with patch('services.printer_manager.trigger_mass_ejection_for_finished_printers', return_value=0):
            response = client.post('/api/v1/ejection/resume')

            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert 'printers_ejecting' in data
