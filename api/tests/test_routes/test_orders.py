"""
Tests for orders API routes.

Tests the /api/v1/orders/* endpoints including:
- List orders
- Create order
- Get single order
- Update order
- Delete order
- Order ejection settings
- Order reordering
"""

import pytest
import io
from unittest.mock import patch, MagicMock


class TestListOrders:
    """Tests for GET /api/v1/orders endpoint."""

    def test_get_orders_empty(self, client):
        """Test getting orders when none exist."""
        with patch('routes.ORDERS', []):
            response = client.get('/api/v1/orders')
            
            assert response.status_code == 200
            data = response.get_json()
            assert isinstance(data, list)
            assert len(data) == 0

    def test_get_orders_excludes_deleted(self, client, mock_orders):
        """Test that deleted orders are excluded."""
        orders_with_deleted = mock_orders.copy()
        orders_with_deleted[0]['deleted'] = True
        
        with patch('routes.ORDERS', orders_with_deleted):
            response = client.get('/api/v1/orders')
            
            assert response.status_code == 200
            data = response.get_json()
            # Should only return non-deleted orders
            assert len(data) == 1
            assert data[0]['id'] == 2

    def test_get_orders_returns_all_fields(self, client, mock_orders):
        """Test that orders contain expected fields."""
        with patch('routes.ORDERS', mock_orders):
            response = client.get('/api/v1/orders')
            
            assert response.status_code == 200
            data = response.get_json()
            
            order = data[0]
            assert 'id' in order
            assert 'filename' in order
            assert 'quantity' in order
            assert 'sent' in order
            assert 'status' in order
            assert 'groups' in order


class TestGetOrder:
    """Tests for GET /api/v1/orders/<id> endpoint."""

    def test_get_order_exists(self, client, mock_orders):
        """Test getting a specific order by ID."""
        with patch('routes.ORDERS', mock_orders):
            response = client.get('/api/v1/orders/1')
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['id'] == 1
            assert data['filename'] == 'test_part.gcode'

    def test_get_order_not_found(self, client, mock_orders):
        """Test getting non-existent order returns 404."""
        with patch('routes.ORDERS', mock_orders):
            response = client.get('/api/v1/orders/999')
            
            assert response.status_code == 404
            data = response.get_json()
            assert 'error' in data


class TestCreateOrder:
    """Tests for POST /api/v1/orders endpoint."""

    def test_create_order_no_file(self, client):
        """Test creating order without file returns error."""
        response = client.post('/api/v1/orders')
        
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_create_order_invalid_file_type(self, client):
        """Test creating order with invalid file type returns error."""
        data = {
            'file': (io.BytesIO(b'test content'), 'test.txt'),
            'quantity': '1'
        }
        response = client.post('/api/v1/orders',
                              data=data,
                              content_type='multipart/form-data')
        
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data
        assert 'Invalid file type' in data['error']


class TestUpdateOrder:
    """Tests for PATCH /api/v1/orders/<id> endpoint."""

    def test_update_order_quantity(self, client, mock_orders):
        """Test updating order quantity."""
        with patch('routes.ORDERS', mock_orders):
            response = client.patch('/api/v1/orders/1',
                                   json={'quantity': 10})
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True

    def test_update_order_name(self, client, mock_orders):
        """Test updating order name."""
        with patch('routes.ORDERS', mock_orders):
            response = client.patch('/api/v1/orders/1',
                                   json={'name': 'New Order Name'})
            
            assert response.status_code == 200

    def test_update_order_not_found(self, client, mock_orders):
        """Test updating non-existent order returns 404."""
        with patch('routes.ORDERS', mock_orders):
            response = client.patch('/api/v1/orders/999',
                                   json={'quantity': 10})
            
            assert response.status_code == 404


class TestDeleteOrder:
    """Tests for DELETE /api/v1/orders/<id> endpoint."""

    def test_delete_order(self, client, mock_orders):
        """Test soft-deleting an order."""
        with patch('routes.ORDERS', mock_orders):
            response = client.delete('/api/v1/orders/1')
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True

    def test_delete_order_not_found(self, client, mock_orders):
        """Test deleting non-existent order returns 404."""
        with patch('routes.ORDERS', mock_orders):
            response = client.delete('/api/v1/orders/999')
            
            assert response.status_code == 404


class TestOrderEjection:
    """Tests for PATCH /api/v1/orders/<id>/ejection endpoint."""

    def test_update_ejection_settings(self, client, mock_orders):
        """Test updating order ejection settings."""
        with patch('routes.ORDERS', mock_orders):
            response = client.patch('/api/v1/orders/1/ejection',
                                   json={
                                       'ejection_enabled': True,
                                       'end_gcode': 'G28 X Y\nM84'
                                   })
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True


class TestOrderMove:
    """Tests for POST /api/v1/orders/<id>/move endpoint."""

    def test_move_order_up(self, client, mock_orders):
        """Test moving order up in priority."""
        with patch('routes.ORDERS', mock_orders):
            response = client.post('/api/v1/orders/2/move',
                                  json={'direction': 'up'})
            
            assert response.status_code == 200

    def test_move_order_down(self, client, mock_orders):
        """Test moving order down in priority."""
        with patch('routes.ORDERS', mock_orders):
            response = client.post('/api/v1/orders/1/move',
                                  json={'direction': 'down'})
            
            assert response.status_code == 200


class TestDefaultEjection:
    """Tests for /api/v1/settings/default-ejection endpoints."""

    def test_get_default_ejection(self, client):
        """Test getting default ejection settings."""
        with patch('routes.load_default_settings', return_value={
            'default_ejection_enabled': False,
            'default_end_gcode': ''
        }):
            response = client.get('/api/v1/settings/default-ejection')
            
            assert response.status_code == 200
            data = response.get_json()
            assert 'ejection_enabled' in data
            assert 'end_gcode' in data

    def test_save_default_ejection(self, client):
        """Test saving default ejection settings."""
        with patch('routes.load_default_settings', return_value={}), \
             patch('routes.save_default_settings', return_value=True):
            
            response = client.post('/api/v1/settings/default-ejection',
                                  json={
                                      'ejection_enabled': True,
                                      'end_gcode': 'G28 X Y'
                                  })
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
