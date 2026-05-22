"""Tests for /api/v1/library endpoints."""

import json
import os
from unittest.mock import patch

import pytest

from services.state import LIBRARY_ITEMS, QUEUE_JOBS, orders_lock, SafeLock


@pytest.fixture(autouse=True)
def clear_catalog():
    with SafeLock(orders_lock):
        LIBRARY_ITEMS.clear()
        QUEUE_JOBS.clear()


@pytest.fixture
def sample_gcode_in_uploads(app, temp_data_dir):
    uploads = app.config['UPLOAD_FOLDER']
    path = os.path.join(uploads, 'test_part.gcode')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('; filament used [g] = 5.0\nG28\n')
    return path


class TestLibraryAPI:
    def test_get_library_empty(self, client):
        response = client.get('/api/v1/library')
        assert response.status_code == 200
        assert response.get_json() == []

    def test_create_library_item(self, client, sample_gcode_in_uploads):
        with open(sample_gcode_in_uploads, 'rb') as f:
            response = client.post(
                '/api/v1/library',
                data={
                    'file': (f, 'test_part.gcode'),
                    'name': 'Test Part',
                    'groups': json.dumps(['Default']),
                },
                content_type='multipart/form-data',
            )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['library_item_id'] >= 1

        listed = client.get('/api/v1/library').get_json()
        assert len(listed) == 1
        assert listed[0]['name'] == 'Test Part'

    def test_patch_library_item(self, client, sample_gcode_in_uploads):
        with open(sample_gcode_in_uploads, 'rb') as f:
            client.post(
                '/api/v1/library',
                data={'file': (f, 'test_part.gcode')},
                content_type='multipart/form-data',
            )
        item_id = client.get('/api/v1/library').get_json()[0]['id']
        response = client.patch(
            f'/api/v1/library/{item_id}',
            json={'name': 'Renamed'},
        )
        assert response.status_code == 200
        item = client.get(f'/api/v1/library/{item_id}').get_json()
        assert item['name'] == 'Renamed'

    def _create_two_library_items(self, client, sample_gcode_in_uploads):
        ids = []
        for _ in range(2):
            with open(sample_gcode_in_uploads, 'rb') as f:
                client.post(
                    '/api/v1/library',
                    data={'file': (f, 'test_part.gcode')},
                    content_type='multipart/form-data',
                )
            ids.append(client.get('/api/v1/library').get_json()[-1]['id'])
        return ids

    def test_bulk_delete_library(self, client, sample_gcode_in_uploads):
        id1, id2 = self._create_two_library_items(client, sample_gcode_in_uploads)
        response = client.post('/api/v1/library/bulk-delete', json={'ids': [id1, id2]})
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['deleted_count'] == 2
        assert data['failures'] == []
        assert client.get('/api/v1/library').get_json() == []

    def test_bulk_delete_skips_active_prints(self, client, sample_gcode_in_uploads):
        item_id = self._create_two_library_items(client, sample_gcode_in_uploads)[0]
        with patch(
            'routes.library.library_item_has_active_prints',
            side_effect=lambda lib_id, *_: lib_id == item_id,
        ):
            response = client.post('/api/v1/library/bulk-delete', json={'ids': [item_id]})
        assert response.status_code == 200
        data = response.get_json()
        assert data['deleted_count'] == 0
        assert len(data['failures']) == 1
        assert 'prints in progress' in data['failures'][0]['error']
        assert client.get('/api/v1/library').get_json()

    def test_bulk_update_library(self, client, sample_gcode_in_uploads):
        id1, id2 = self._create_two_library_items(client, sample_gcode_in_uploads)
        response = client.post(
            '/api/v1/library/bulk-update',
            json={
                'ids': [id1, id2],
                'groups': ['GroupA'],
                'ejection_enabled': True,
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['updated_count'] == 2
        assert data['failures'] == []
        for item in client.get('/api/v1/library').get_json():
            assert item['groups'] == ['GroupA']
            assert item['ejection_enabled'] is True
