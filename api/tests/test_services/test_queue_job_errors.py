"""Tests for queue job error recording."""

import json
import os

import pytest

from services.library_queue import (
    clear_queue_job_error,
    normalize_queue_job,
    record_queue_job_error,
)
from services.state import QUEUE_FILE, QUEUE_JOBS, orders_lock, save_data, SafeLock
from utils.paths import get_queue_file


@pytest.fixture(autouse=True)
def clear_queue():
    with SafeLock(orders_lock):
        QUEUE_JOBS.clear()
        save_data(QUEUE_FILE, QUEUE_JOBS)
    yield
    with SafeLock(orders_lock):
        QUEUE_JOBS.clear()
        save_data(QUEUE_FILE, QUEUE_JOBS)


def test_normalize_queue_job_error_defaults():
    job = normalize_queue_job({'id': 1, 'filename': 'a.gcode', 'quantity': 1})
    assert job['last_error'] is None
    assert job['error_events'] == []


def test_record_and_clear_queue_job_error(temp_data_dir):
    with SafeLock(orders_lock):
        QUEUE_JOBS.append(
            normalize_queue_job({
                'id': 42,
                'filename': 'part.gcode',
                'filepath': '/tmp/part.gcode',
                'quantity': 2,
            })
        )

    assert record_queue_job_error(
        42,
        'Upload failed: HTTP 500',
        printer_name='Printer 1',
        phase='prusa_upload',
        batch_id='abc123',
    )

    with SafeLock(orders_lock):
        job = QUEUE_JOBS[0]
        assert job['last_error'] == 'Upload failed: HTTP 500'
        assert job['last_error_printer'] == 'Printer 1'
        assert job['last_error_phase'] == 'prusa_upload'
        assert len(job['error_events']) == 1
        assert job['error_events'][0]['message'] == 'Upload failed: HTTP 500'
        assert job['error_events'][0]['batch_id'] == 'abc123'

    queue_path = get_queue_file()
    assert os.path.exists(queue_path)
    with open(queue_path, encoding='utf-8') as f:
        on_disk = json.load(f)
    assert on_disk[0]['last_error'] == 'Upload failed: HTTP 500'

    assert clear_queue_job_error(42) is True
    with SafeLock(orders_lock):
        job = QUEUE_JOBS[0]
        assert job['last_error'] is None
        assert len(job['error_events']) == 1


def test_error_events_ring_buffer(temp_data_dir):
    with SafeLock(orders_lock):
        QUEUE_JOBS.append(
            normalize_queue_job({'id': 1, 'filename': 'a.gcode', 'quantity': 1})
        )

    for i in range(12):
        record_queue_job_error(1, f'error {i}', phase='test')

    with SafeLock(orders_lock):
        events = QUEUE_JOBS[0]['error_events']
    assert len(events) == 10
    assert events[0]['message'] == 'error 2'
    assert events[-1]['message'] == 'error 11'


def test_record_unknown_job_returns_false():
    assert record_queue_job_error(999, 'missing') is False
