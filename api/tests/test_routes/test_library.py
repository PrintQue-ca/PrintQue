"""Tests for /api/v1/library endpoints."""

import json
import os

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
