"""
Tests for printers API routes.

Tests the /api/v1/printers/* endpoints including:
- List printers
- Add printer
- Get single printer
- Update printer
- Delete printer
- Printer actions (ready, stop, pause, resume)
"""

import pytest
from unittest.mock import patch, MagicMock


class TestListPrinters:
    """Tests for GET /api/v1/printers endpoint."""

    def test_get_printers_empty(self, client):
        """Test getting printers when none exist."""
        with patch('routes.PRINTERS', []), \
             patch('routes.prepare_printer_data_for_broadcast', return_value=[]):
            response = client.get('/api/v1/printers')
            
            assert response.status_code == 200
            data = response.get_json()
            assert isinstance(data, list)
            assert len(data) == 0

    def test_get_printers_returns_list(self, client, mock_printers):
        """Test getting printers returns list with expected structure."""
        with patch('routes.PRINTERS', mock_printers), \
             patch('routes.prepare_printer_data_for_broadcast', return_value=mock_printers):
            response = client.get('/api/v1/printers')
            
            assert response.status_code == 200
            data = response.get_json()
            assert isinstance(data, list)
            assert len(data) == 2

    def test_get_printers_has_required_fields(self, client, mock_printers):
        """Test that printers contain required fields."""
        with patch('routes.PRINTERS', mock_printers), \
             patch('routes.prepare_printer_data_for_broadcast', return_value=mock_printers):
            response = client.get('/api/v1/printers')
            
            data = response.get_json()
            printer = data[0]
            
            assert 'name' in printer
            assert 'ip' in printer
            assert 'type' in printer
            assert 'state' in printer
            assert 'temps' in printer


class TestGetPrinter:
    """Tests for GET /api/v1/printers/<name> endpoint."""

    def test_get_printer_exists(self, client, mock_printers):
        """Test getting a specific printer by name."""
        with patch('routes.PRINTERS', mock_printers), \
             patch('routes.prepare_printer_data_for_broadcast', 
                   return_value=[mock_printers[0]]):
            response = client.get('/api/v1/printers/Test%20Printer%201')
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['name'] == 'Test Printer 1'

    def test_get_printer_not_found(self, client, mock_printers):
        """Test getting non-existent printer returns 404."""
        with patch('routes.PRINTERS', mock_printers):
            response = client.get('/api/v1/printers/NonExistent')
            
            assert response.status_code == 404


class TestAddPrinter:
    """Tests for POST /api/v1/printers endpoint."""

    def test_add_prusa_printer(self, client):
        """Test adding a Prusa printer."""
        with patch('routes.PRINTERS', []), \
             patch('routes.encrypt_api_key', return_value='encrypted'):
            response = client.post('/api/v1/printers',
                                  json={
                                      'name': 'New Prusa',
                                      'ip': '192.168.1.50',
                                      'type': 'prusa',
                                      'api_key': 'test_key',
                                      'group': 'Default'
                                  })
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True

    def test_add_printer_missing_name(self, client):
        """Test adding printer without name returns error."""
        response = client.post('/api/v1/printers',
                              json={
                                  'ip': '192.168.1.50',
                                  'type': 'prusa'
                              })
        
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_add_printer_missing_ip(self, client):
        """Test adding printer without IP returns error."""
        response = client.post('/api/v1/printers',
                              json={
                                  'name': 'Test',
                                  'type': 'prusa'
                              })
        
        assert response.status_code == 400

    def test_add_prusa_missing_api_key(self, client):
        """Test adding Prusa without API key returns error."""
        with patch('routes.PRINTERS', []):
            response = client.post('/api/v1/printers',
                                  json={
                                      'name': 'Test Prusa',
                                      'ip': '192.168.1.50',
                                      'type': 'prusa'
                                  })
            
            assert response.status_code == 400
            data = response.get_json()
            assert 'API Key' in data['error']

    def test_add_bambu_missing_device_id(self, client):
        """Test adding Bambu without device ID returns error."""
        with patch('routes.PRINTERS', []):
            response = client.post('/api/v1/printers',
                                  json={
                                      'name': 'Test Bambu',
                                      'ip': '192.168.1.50',
                                      'type': 'bambu',
                                      'access_code': 'code'
                                  })
            
            assert response.status_code == 400


class TestUpdatePrinter:
    """Tests for PATCH /api/v1/printers/<name> endpoint."""

    def test_update_printer_group(self, client, mock_printers):
        """Test updating printer group."""
        with patch('routes.PRINTERS', mock_printers):
            response = client.patch('/api/v1/printers/Test%20Printer%201',
                                   json={'group': 'New Group'})
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True

    def test_update_printer_not_found(self, client, mock_printers):
        """Test updating non-existent printer returns 404."""
        with patch('routes.PRINTERS', mock_printers):
            response = client.patch('/api/v1/printers/NonExistent',
                                   json={'group': 'New Group'})
            
            assert response.status_code == 404


class TestDeletePrinter:
    """Tests for DELETE /api/v1/printers/<name> endpoint."""

    def test_delete_printer(self, client, mock_printers):
        """Test deleting a printer."""
        printers_copy = mock_printers.copy()
        with patch('routes.PRINTERS', printers_copy):
            response = client.delete('/api/v1/printers/Test%20Printer%201')
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True

    def test_delete_printer_not_found(self, client, mock_printers):
        """Test deleting non-existent printer returns 404."""
        with patch('routes.PRINTERS', mock_printers):
            response = client.delete('/api/v1/printers/NonExistent')
            
            assert response.status_code == 404


class TestPrinterReady:
    """Tests for POST /api/v1/printers/<name>/ready endpoint."""

    def test_mark_finished_printer_ready(self, client, mock_printers):
        """Test marking a FINISHED printer as ready."""
        printers = mock_printers.copy()
        printers[0]['state'] = 'FINISHED'
        
        with patch('routes.PRINTERS', printers), \
             patch('routes.start_background_distribution'):
            response = client.post('/api/v1/printers/Test%20Printer%201/ready')
            
            assert response.status_code == 200

    def test_mark_non_finished_printer_ready_fails(self, client, mock_printers):
        """Test marking a non-FINISHED printer as ready returns error."""
        with patch('routes.PRINTERS', mock_printers):
            # First printer is in READY state
            response = client.post('/api/v1/printers/Test%20Printer%201/ready')
            
            assert response.status_code == 400


class TestPrinterActions:
    """Tests for printer action endpoints (stop, pause, resume)."""

    def test_stop_printer(self, client, mock_printers):
        """Test stopping a printer."""
        response = client.post('/api/v1/printers/Test%20Printer%202/stop')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

    def test_pause_printer(self, client, mock_printers):
        """Test pausing a printer."""
        response = client.post('/api/v1/printers/Test%20Printer%202/pause')
        
        assert response.status_code == 200

    def test_resume_printer(self, client, mock_printers):
        """Test resuming a printer."""
        response = client.post('/api/v1/printers/Test%20Printer%202/resume')
        
        assert response.status_code == 200
