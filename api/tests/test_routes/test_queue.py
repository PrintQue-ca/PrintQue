"""Tests for /api/v1/queue endpoints."""

import os
from unittest.mock import patch

import pytest

from services.state import LIBRARY_ITEMS, QUEUE_JOBS, orders_lock, SafeLock


@pytest.fixture(autouse=True)
def clear_queue_state():
    with SafeLock(orders_lock):
        LIBRARY_ITEMS.clear()
        QUEUE_JOBS.clear()


@pytest.fixture
def library_item(app, temp_data_dir):
    uploads = app.config['UPLOAD_FOLDER']
    path = os.path.join(uploads, 'queue_test.gcode')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('; filament used [g] = 1.0\nG28\n')
    with SafeLock(orders_lock):
        LIBRARY_ITEMS.clear()
        LIBRARY_ITEMS.append({
            'id': 1,
            'filename': 'queue_test.gcode',
            'filepath': path,
            'name': 'Queue Test',
            'groups': ['Default'],
            'filament_g': 1.0,
            'estimated_print_seconds': 493,
            'ejection_enabled': False,
            'deleted': False,
            'created_at': '2024-01-01T00:00:00',
            'updated_at': '2024-01-01T00:00:00',
        })
        QUEUE_JOBS.clear()
    yield 1


class TestQueueAPI:
    def test_get_queue_empty(self, client):
        response = client.get('/api/v1/queue')
        assert response.status_code == 200
        assert response.get_json() == []

    def test_bulk_enqueue(self, client, library_item):
        response = client.post(
            '/api/v1/queue/bulk',
            json={'items': [{'library_item_id': library_item, 'quantity': 3}]},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['count'] == 1

        jobs = client.get('/api/v1/queue').get_json()
        assert len(jobs) == 1
        assert jobs[0]['quantity'] == 3
        assert jobs[0]['sent'] == 0
        assert jobs[0]['library_item_id'] == library_item
        assert jobs[0]['estimated_print_seconds'] == 493

    def test_patch_quantity_below_sent_rejected(self, client, library_item):
        client.post(
            '/api/v1/queue/bulk',
            json={'items': [{'library_item_id': library_item, 'quantity': 5}]},
        )
        job_id = client.get('/api/v1/queue').get_json()[0]['id']
        with SafeLock(orders_lock):
            for job in QUEUE_JOBS:
                if job['id'] == job_id:
                    job['sent'] = 3
                    break
        response = client.patch(f'/api/v1/queue/{job_id}', json={'quantity': 2})
        assert response.status_code == 400

    def test_patch_paused_persists_and_resume_restarts_distribution(self, client, library_item):
        client.post(
            '/api/v1/queue/bulk',
            json={'items': [{'library_item_id': library_item, 'quantity': 3}]},
        )
        job_id = client.get('/api/v1/queue').get_json()[0]['id']

        response = client.patch(f'/api/v1/queue/{job_id}', json={'paused': True})
        assert response.status_code == 200
        assert response.get_json()['job']['paused'] is True

        jobs = client.get('/api/v1/queue').get_json()
        assert jobs[0]['paused'] is True

        with patch('routes.queue.start_background_distribution') as start_distribution:
            response = client.patch(f'/api/v1/queue/{job_id}', json={'paused': False})

        assert response.status_code == 200
        assert response.get_json()['job']['paused'] is False
        start_distribution.assert_called_once()

    def test_patch_paused_requires_boolean(self, client, library_item):
        client.post(
            '/api/v1/queue/bulk',
            json={'items': [{'library_item_id': library_item, 'quantity': 1}]},
        )
        job_id = client.get('/api/v1/queue').get_json()[0]['id']

        response = client.patch(f'/api/v1/queue/{job_id}', json={'paused': 'yes'})

        assert response.status_code == 400

    def test_get_queue_includes_error_fields(self, client, library_item):
        client.post(
            '/api/v1/queue/bulk',
            json={'items': [{'library_item_id': library_item, 'quantity': 1}]},
        )
        job_id = client.get('/api/v1/queue').get_json()[0]['id']
        with SafeLock(orders_lock):
            for job in QUEUE_JOBS:
                if job['id'] == job_id:
                    job['last_error'] = 'Print file not found: /missing.gcode'
                    job['last_error_at'] = '2026-05-18T12:00:00'
                    job['last_error_printer'] = 'P1'
                    job['last_error_phase'] = 'file_missing'
                    job['error_events'] = [{
                        'at': '2026-05-18T12:00:00',
                        'message': 'Print file not found: /missing.gcode',
                        'phase': 'file_missing',
                    }]
                    break

        jobs = client.get('/api/v1/queue').get_json()
        assert jobs[0]['last_error'] == 'Print file not found: /missing.gcode'
        assert jobs[0]['last_error_phase'] == 'file_missing'
        assert len(jobs[0]['error_events']) == 1
