"""Tests for stale Bambu ERROR recovery in the MQTT cache."""

from unittest.mock import patch

from services.bambu_handler import (
    BAMBU_PRINTER_STATES,
    bambu_error_looks_stale,
    clear_stale_bambu_error_if_idle,
)
from services.order_distributor import _printer_available_for_distribution


class TestBambuErrorLooksStale:
    def test_idle_gcode_is_stale(self):
        assert bambu_error_looks_stale({
            'state': 'ERROR',
            'gcode_state': 'IDLE',
            'error': 'previous rejection',
        }) is True

    def test_failed_no_job_is_stale(self):
        assert bambu_error_looks_stale({
            'state': 'ERROR',
            'gcode_state': 'FAILED',
            'last_print_error': 50331648,
        }) is True

    def test_hms_alerts_not_stale(self):
        assert bambu_error_looks_stale({
            'state': 'ERROR',
            'gcode_state': 'IDLE',
            'hms_alerts': ['Filament runout'],
        }) is False

    def test_running_not_stale(self):
        assert bambu_error_looks_stale({
            'state': 'ERROR',
            'gcode_state': 'RUNNING',
            'last_print_error': 123,
        }) is False


class TestClearStaleBambuError:
    def setup_method(self):
        BAMBU_PRINTER_STATES.clear()

    def test_clears_stale_error(self):
        BAMBU_PRINTER_STATES['lil'] = {
            'state': 'ERROR',
            'gcode_state': 'IDLE',
            'error': 'Print rejected',
            'last_print_rejection': {'detail': 'Print rejected'},
        }
        assert clear_stale_bambu_error_if_idle('lil') is True
        assert BAMBU_PRINTER_STATES['lil']['state'] == 'READY'
        assert BAMBU_PRINTER_STATES['lil']['error'] is None
        assert 'last_print_rejection' not in BAMBU_PRINTER_STATES['lil']

    def test_keeps_real_error(self):
        BAMBU_PRINTER_STATES['lil'] = {
            'state': 'ERROR',
            'gcode_state': 'RUNNING',
            'error': 'Heater fault',
        }
        assert clear_stale_bambu_error_if_idle('lil') is False
        assert BAMBU_PRINTER_STATES['lil']['state'] == 'ERROR'


class TestDistributionStaleError:
    def setup_method(self):
        BAMBU_PRINTER_STATES.clear()

    def test_excludes_real_bambu_error(self):
        BAMBU_PRINTER_STATES['lil'] = {
            'state': 'ERROR',
            'gcode_state': 'RUNNING',
            'error': 'Heater fault',
        }
        printer = {
            'name': 'lil',
            'type': 'bambu',
            'state': 'READY',
            'manually_set': True,
        }
        with patch('services.order_distributor.BAMBU_PRINTER_STATES', BAMBU_PRINTER_STATES):
            assert _printer_available_for_distribution(printer) is False

    def test_clears_stale_error_and_allows_distribution(self):
        BAMBU_PRINTER_STATES['lil'] = {
            'state': 'ERROR',
            'gcode_state': 'IDLE',
            'error': 'Old rejection',
        }
        printer = {
            'name': 'lil',
            'type': 'bambu',
            'state': 'READY',
            'manually_set': True,
        }
        with patch('services.order_distributor.BAMBU_PRINTER_STATES', BAMBU_PRINTER_STATES):
            assert _printer_available_for_distribution(printer) is True
        assert BAMBU_PRINTER_STATES['lil']['state'] == 'READY'
