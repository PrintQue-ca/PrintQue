"""Tests for orders.json → library + queue migration."""

import json
import os

import pytest

from services import state as st


@pytest.fixture
def fresh_state_module(temp_data_dir, monkeypatch):
    """Re-run initialize_state with legacy orders.json only."""
    monkeypatch.setenv('DATA_DIR', temp_data_dir)
    data_root = os.path.join(temp_data_dir, 'PrintQueData')
    os.makedirs(data_root, exist_ok=True)

    orders_path = os.path.join(data_root, 'orders.json')
    library_path = os.path.join(data_root, 'library.json')
    queue_path = os.path.join(data_root, 'queue.json')

    for p in (library_path, queue_path):
        if os.path.exists(p):
            os.remove(p)

    legacy = [
        {
            'id': 10,
            'filename': 'a.gcode',
            'filepath': os.path.join(data_root, 'uploads', 'a.gcode'),
            'quantity': 2,
            'sent': 1,
            'status': 'partial',
            'groups': ['Default'],
            'filament_g': 5,
            'deleted': False,
        },
        {
            'id': 11,
            'filename': 'b.gcode',
            'filepath': os.path.join(data_root, 'uploads', 'b.gcode'),
            'quantity': 0,
            'sent': 0,
            'status': 'pending',
            'groups': ['Default'],
            'filament_g': 3,
            'deleted': False,
        },
    ]
    os.makedirs(os.path.dirname(legacy[0]['filepath']), exist_ok=True)
    for o in legacy:
        with open(o['filepath'], 'w', encoding='utf-8') as f:
            f.write('G28\n')
    with open(orders_path, 'w', encoding='utf-8') as f:
        json.dump(legacy, f)

    st.LIBRARY_ITEMS.clear()
    st.QUEUE_JOBS.clear()
    st._STATE_INITIALIZED = False
    st.initialize_state()

    yield
    st._STATE_INITIALIZED = False


def test_migration_splits_library_and_queue(fresh_state_module):
    assert len(st.LIBRARY_ITEMS) == 2
    assert len(st.QUEUE_JOBS) == 1
    job = st.QUEUE_JOBS[0]
    assert job['id'] == 10
    assert job['sent'] == 1
    assert job['quantity'] == 2
    assert job['library_item_id'] is not None
