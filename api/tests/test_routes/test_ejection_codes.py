"""
Tests for ejection codes API routes.

Tests the /api/v1/ejection-codes/* endpoints for managing
G-code presets used for automatic print ejection.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestListEjectionCodes:
    """Tests for GET /api/v1/ejection-codes endpoint."""

    def test_get_codes_empty(self, client):
        """Test getting codes when none exist."""
        with patch('routes.ejection_codes.EJECTION_CODES', []):
            response = client.get('/api/v1/ejection-codes')
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert isinstance(data['ejection_codes'], list)

    def test_get_codes_returns_list(self, client, mock_ejection_codes):
        """Test getting codes returns expected list."""
        with patch('routes.ejection_codes.EJECTION_CODES', mock_ejection_codes):
            response = client.get('/api/v1/ejection-codes')
            
            assert response.status_code == 200
            data = response.get_json()
            assert len(data['ejection_codes']) == 2


class TestGetEjectionCode:
    """Tests for GET /api/v1/ejection-codes/<id> endpoint."""

    def test_get_code_exists(self, client, mock_ejection_codes):
        """Test getting a specific ejection code."""
        with patch('routes.ejection_codes.EJECTION_CODES', mock_ejection_codes):
            response = client.get('/api/v1/ejection-codes/ejection-1')
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert data['ejection_code']['name'] == 'Standard Eject'

    def test_get_code_not_found(self, client, mock_ejection_codes):
        """Test getting non-existent code returns 404."""
        with patch('routes.ejection_codes.EJECTION_CODES', mock_ejection_codes):
            response = client.get('/api/v1/ejection-codes/nonexistent')
            
            assert response.status_code == 404


class TestCreateEjectionCode:
    """Tests for POST /api/v1/ejection-codes endpoint."""

    def test_create_code(self, client):
        """Test creating a new ejection code."""
        with patch('routes.ejection_codes.EJECTION_CODES', []):
            response = client.post('/api/v1/ejection-codes',
                                  json={
                                      'name': 'New Code',
                                      'gcode': 'G28 X Y\nM84'
                                  })
            
            assert response.status_code in [200, 201]
            data = response.get_json()
            assert data['success'] is True

    def test_create_code_missing_name(self, client):
        """Test creating code without name returns error."""
        response = client.post('/api/v1/ejection-codes',
                              json={'gcode': 'G28'})
        
        assert response.status_code == 400

    def test_create_code_missing_gcode(self, client):
        """Test creating code without gcode returns error."""
        response = client.post('/api/v1/ejection-codes',
                              json={'name': 'Test'})
        
        assert response.status_code == 400


class TestUpdateEjectionCode:
    """Tests for PATCH /api/v1/ejection-codes/<id> endpoint."""

    def test_update_code(self, client, mock_ejection_codes):
        """Test updating an ejection code."""
        with patch('routes.ejection_codes.EJECTION_CODES', mock_ejection_codes):
            response = client.patch('/api/v1/ejection-codes/ejection-1',
                                   json={'name': 'Updated Name'})
            
            assert response.status_code == 200

    def test_update_code_not_found(self, client, mock_ejection_codes):
        """Test updating non-existent code returns 404."""
        with patch('routes.ejection_codes.EJECTION_CODES', mock_ejection_codes):
            response = client.patch('/api/v1/ejection-codes/nonexistent',
                                   json={'name': 'Test'})
            
            assert response.status_code == 404


class TestDeleteEjectionCode:
    """Tests for DELETE /api/v1/ejection-codes/<id> endpoint."""

    def test_delete_code(self, client, mock_ejection_codes):
        """Test deleting an ejection code."""
        codes = mock_ejection_codes.copy()
        with patch('routes.ejection_codes.EJECTION_CODES', codes):
            response = client.delete('/api/v1/ejection-codes/ejection-1')
            
            assert response.status_code == 200

    def test_delete_code_not_found(self, client, mock_ejection_codes):
        """Test deleting non-existent code returns 404."""
        with patch('routes.ejection_codes.EJECTION_CODES', mock_ejection_codes):
            response = client.delete('/api/v1/ejection-codes/nonexistent')
            
            assert response.status_code == 404
