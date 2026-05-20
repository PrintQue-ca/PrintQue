"""Tests for Bambu ejection M400 completion counting and FINISHED guards."""

from unittest.mock import MagicMock, patch

from services.bambu_handler import (
    BAMBU_PRINTER_STATES,
    bambu_states_lock,
    count_m400_in_gcode_lines,
    _complete_bambu_ejection,
    _publish_gcode_line_and_wait,
    _signal_gcode_line_ack,
)
from services.ejection_manager import handle_finished_state_ejection


class TestCountM400InGcodeLines:
    def test_counts_multiple_m400(self):
        lines = ['G90', 'M400', 'G1 X10', 'M400']
        assert count_m400_in_gcode_lines(lines) == 2

class TestCompleteBambuEjection:
    def setup_method(self):
        with bambu_states_lock:
            BAMBU_PRINTER_STATES.clear()

    def test_marks_ready_only_when_ejecting(self):
        with bambu_states_lock:
            BAMBU_PRINTER_STATES['lil'] = {
                'state': 'EJECTING',
                'waiting_for_m400': True,
                'ejection_m400_pending': 1,
            }
        _complete_bambu_ejection('lil', 'test')
        with bambu_states_lock:
            st = BAMBU_PRINTER_STATES['lil']
            assert st['state'] == 'READY'
            assert st['ejection_complete'] is True
            assert st['ejection_m400_pending'] == 0
            assert st['waiting_for_m400'] is False


class TestSequentialGcodeAck:
    def setup_method(self):
        with bambu_states_lock:
            BAMBU_PRINTER_STATES.clear()

    def test_publish_waits_for_matching_ack(self):
        printer = {'name': 'lil', 'serial_number': 'SN123'}
        client = MagicMock()
        client.publish.return_value = MagicMock(rc=0)

        def ack_after_publish(*_args, **_kwargs):
            _signal_gcode_line_ack('lil', 'G90', True)
            return MagicMock(rc=0)

        client.publish.side_effect = ack_after_publish

        assert _publish_gcode_line_and_wait(client, printer, 'lil', 'G90', timeout=2.0)

    def test_two_leading_m400s_do_not_complete_until_send_loop_finishes(self):
        """Regression: preamble M400s must not trigger early ejection complete."""
        with bambu_states_lock:
            BAMBU_PRINTER_STATES['lil'] = {
                'state': 'EJECTING',
                'waiting_for_m400': False,
                'ejection_sequential_active': True,
                'ejection_m400_pending': 0,
            }
        _signal_gcode_line_ack('lil', 'M400', True)
        _signal_gcode_line_ack('lil', 'M400', True)
        with bambu_states_lock:
            assert BAMBU_PRINTER_STATES['lil']['state'] == 'EJECTING'
            assert BAMBU_PRINTER_STATES['lil'].get('ejection_complete') is not True


class TestHandleFinishedEjectionGuard:
    def test_skips_ejection_when_job_never_started(self):
        printer = {
            'name': 'lil',
            'type': 'bambu',
            'state': 'FINISHED',
            'status': 'Print Complete',
            'count_incremented_for_current_job': False,
            'order_id': 10,
            'file': 'part.gcode',
        }
        updates = {}
        with patch('services.ejection_manager.SafeLock'), patch(
            'services.ejection_manager.ORDERS', []
        ):
            handle_finished_state_ejection(
                printer, 'lil', 'part.gcode', 10, updates
            )
        assert updates['state'] == 'READY'
        assert updates['order_id'] is None
        assert updates.get('ejection_in_progress') is False
