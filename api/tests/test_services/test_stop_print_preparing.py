"""Tests for cancel/stop while printer is PREPARING."""

import pytest
from unittest.mock import patch, MagicMock

from services.print_jobs import (
    stop_print,
    is_printer_stoppable,
    schedule_stop_print_by_name,
)
from services.status_poller import update_bambu_printer_states


@pytest.mark.asyncio
async def test_stop_bambu_preparing_always_clears_local_state():
    printer = {
        'name': 'Bambu1',
        'type': 'bambu',
        'state': 'PREPARING',
        'serial_number': 'SN1',
        'order_id': 5,
        'file': 'part.gcode',
    }
    session = MagicMock()

    with patch('services.print_jobs.stop_bambu_print', return_value=False), \
         patch('services.print_jobs.clear_bambu_print_assignment'):
        success = await stop_print(session, printer)

    assert success is True
    assert printer['state'] == 'READY'
    assert printer['order_id'] is None


@pytest.mark.asyncio
async def test_stop_prusa_preparing_clears_when_cancel_fails():
    printer = {
        'name': 'Prusa1',
        'type': 'prusa',
        'state': 'PREPARING',
        'ip': '192.168.1.10',
        'api_key': 'key',
        'order_id': 3,
    }
    session = MagicMock()

    class FakeResp:
        status = 500

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    async def fake_retry(fn, **kwargs):
        return await fn()

    session.post = MagicMock(return_value=FakeResp())

    with patch('services.print_jobs.retry_async', side_effect=fake_retry), \
         patch('services.print_jobs.decrypt_api_key', return_value='plain'):
        success = await stop_print(session, printer)

    assert success is True
    assert printer['state'] == 'READY'
    assert printer['order_id'] is None


def test_bambu_poller_ignores_stale_preparing_after_cancel():
    """Manually-set READY must not revert to PREPARING when pending file was cleared."""
    printers = [{
        'name': 'Bambu1',
        'type': 'bambu',
        'state': 'READY',
        'status': 'Ready',
        'manually_set': True,
        'order_id': None,
        'from_queue': False,
    }]
    bambu_states = {
        'Bambu1': {
            'state': 'PREPARING',
            'nozzle_temp': 200,
            'bed_temp': 60,
        },
    }

    with patch('services.status_poller.PRINTERS', printers), \
         patch('services.status_poller.BAMBU_PRINTER_STATES', bambu_states), \
         patch('services.status_poller.bambu_states_lock'), \
         patch('services.status_poller.save_data'):
        update_bambu_printer_states()

    assert printers[0]['state'] == 'READY'
    assert printers[0]['manually_set'] is True


def test_is_printer_stoppable_ready_with_order_id():
    printer = {
        'name': 'Bambu1',
        'type': 'bambu',
        'state': 'READY',
        'order_id': 9,
    }
    assert is_printer_stoppable(printer) is True


def test_schedule_stop_clears_ready_with_stuck_order_id():
    printers = [{
        'name': 'Bambu1',
        'type': 'bambu',
        'state': 'READY',
        'order_id': 9,
        'serial_number': 'SN1',
    }]
    socketio = MagicMock()
    app = MagicMock()

    with patch('services.state.PRINTERS', printers), \
         patch('services.print_jobs.stop_bambu_print', return_value=True), \
         patch('services.print_jobs.clear_bambu_print_assignment'), \
         patch('services.state.save_data'), \
         patch('services.print_jobs._emit_printer_status_after_stop'):
        result = schedule_stop_print_by_name('Bambu1', socketio, app)

    assert result is True
    assert printers[0]['state'] == 'READY'
    assert printers[0]['order_id'] is None
    assert printers[0]['manually_set'] is True


def test_bambu_poller_ignores_repeat_finished_when_already_ready():
    """Stale MQTT FINISHED must not re-process after job was already cleared."""
    printers = [{
        'name': 'Bambu1',
        'type': 'bambu',
        'state': 'READY',
        'status': 'Ready',
        'manually_set': True,
        'order_id': None,
    }]
    bambu_states = {
        'Bambu1': {
            'state': 'FINISHED',
            'nozzle_temp': 200,
            'bed_temp': 60,
        },
    }

    with patch('services.status_poller.PRINTERS', printers), \
         patch('services.status_poller.BAMBU_PRINTER_STATES', bambu_states), \
         patch('services.status_poller.bambu_states_lock'), \
         patch('services.status_poller.save_data') as mock_save, \
         patch('services.status_poller.clear_bambu_print_assignment') as mock_clear, \
         patch('services.status_poller.record_queue_job_error') as mock_err:
        update_bambu_printer_states()

    assert printers[0]['state'] == 'READY'
    mock_clear.assert_not_called()
    mock_err.assert_not_called()
    mock_save.assert_not_called()
