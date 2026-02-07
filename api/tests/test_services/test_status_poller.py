"""
Characterization tests for status_poller.py

These tests capture the current behavior of the status polling system
before refactoring.  They serve as a safety net: if all tests pass after
refactoring, the external behavior is preserved.
"""

import time
import copy
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_printer(**overrides):
    """Create a printer dict with sensible defaults for testing."""
    base = {
        'name': 'Printer1',
        'ip': '192.168.1.100',
        'type': 'prusa',
        'group': 'Default',
        'state': 'READY',
        'status': 'Ready',
        'temps': {'nozzle': 25, 'bed': 22},
        'progress': 0,
        'time_remaining': 0,
        'z_height': 0,
        'file': None,
        'api_key': 'test_key',
        'manually_set': False,
        'order_id': None,
        'ejection_processed': False,
        'ejection_in_progress': False,
        'manual_timeout': 0,
        'last_ejection_time': 0,
        'finish_time': None,
        'service_mode': False,
        'count_incremented_for_current_job': False,
        'print_started_at': None,
        'ejection_start_time': None,
    }
    base.update(overrides)
    return base


def make_api_response(state='IDLE', temp_bed=25, temp_nozzle=30, axis_z=0):
    """Create a Prusa-style API /status response."""
    return {
        'printer': {
            'state': state,
            'temp_bed': temp_bed,
            'temp_nozzle': temp_nozzle,
            'axis_z': axis_z,
        }
    }


def make_job_response(progress=0, time_remaining=0, file_name='test.gcode', job_id=123):
    """Create a Prusa-style API /job response."""
    return {
        'progress': progress,
        'time_remaining': time_remaining,
        'file': {'display_name': file_name},
        'id': job_id,
    }


# ===========================================================================
# get_minutes_since_finished  (pure function)
# ===========================================================================

class TestGetMinutesSinceFinished:
    """Verify the elapsed-time calculator for FINISHED printers."""

    def test_finished_five_minutes_ago(self):
        from services.status_poller import get_minutes_since_finished
        printer = {'state': 'FINISHED', 'finish_time': time.time() - 300, 'name': 'P1'}
        assert get_minutes_since_finished(printer) == 5

    def test_finished_one_hour_ago(self):
        from services.status_poller import get_minutes_since_finished
        printer = {'state': 'FINISHED', 'finish_time': time.time() - 3600, 'name': 'P1'}
        assert get_minutes_since_finished(printer) == 60

    def test_returns_none_when_not_finished(self):
        from services.status_poller import get_minutes_since_finished
        printer = {'state': 'PRINTING', 'finish_time': time.time() - 300, 'name': 'P1'}
        assert get_minutes_since_finished(printer) is None

    def test_returns_none_when_finish_time_is_none(self):
        from services.status_poller import get_minutes_since_finished
        assert get_minutes_since_finished({'state': 'FINISHED', 'finish_time': None, 'name': 'P1'}) is None

    def test_returns_none_when_finish_time_missing(self):
        from services.status_poller import get_minutes_since_finished
        assert get_minutes_since_finished({'state': 'FINISHED', 'name': 'P1'}) is None

    def test_returns_zero_for_just_finished(self):
        from services.status_poller import get_minutes_since_finished
        printer = {'state': 'FINISHED', 'finish_time': time.time() - 15, 'name': 'P1'}
        assert get_minutes_since_finished(printer) == 0


# ===========================================================================
# prepare_printer_data_for_broadcast  (most widely-used export)
# ===========================================================================

class TestPreparePrinterDataForBroadcast:
    """Lock in the broadcast data mapping and per-state enrichment logic."""

    # -- field mappings --

    @patch('utils.status_poller_helpers.BAMBU_PRINTER_STATES', {})
    def test_maps_file_to_current_file(self):
        from services.status_poller import prepare_printer_data_for_broadcast
        result = prepare_printer_data_for_broadcast(
            [make_printer(file='test.gcode', state='PRINTING')]
        )
        assert result[0]['current_file'] == 'test.gcode'

    @patch('utils.status_poller_helpers.BAMBU_PRINTER_STATES', {})
    def test_maps_state_to_status(self):
        from services.status_poller import prepare_printer_data_for_broadcast
        result = prepare_printer_data_for_broadcast([make_printer(state='PRINTING')])
        # status is overwritten to match state (raw value)
        assert result[0]['status'] == 'PRINTING'

    # -- print_stage / stage_detail for every state --

    @patch('utils.status_poller_helpers.BAMBU_PRINTER_STATES', {})
    def test_stage_ready(self):
        from services.status_poller import prepare_printer_data_for_broadcast
        r = prepare_printer_data_for_broadcast([make_printer(state='READY')])[0]
        assert r['print_stage'] == 'ready'
        assert r['stage_detail'] == 'Ready for next job'

    @patch('utils.status_poller_helpers.BAMBU_PRINTER_STATES', {})
    def test_stage_printing(self):
        from services.status_poller import prepare_printer_data_for_broadcast
        r = prepare_printer_data_for_broadcast(
            [make_printer(state='PRINTING', progress=45)]
        )[0]
        assert r['print_stage'] == 'printing'
        assert '45%' in r['stage_detail']

    @patch('utils.status_poller_helpers.BAMBU_PRINTER_STATES', {})
    def test_stage_finished_with_time(self):
        from services.status_poller import prepare_printer_data_for_broadcast
        r = prepare_printer_data_for_broadcast(
            [make_printer(state='FINISHED', finish_time=time.time() - 600)]
        )[0]
        assert r['print_stage'] == 'finished'
        assert r['minutes_since_finished'] == 10
        assert '10m ago' in r['stage_detail']

    @patch('utils.status_poller_helpers.BAMBU_PRINTER_STATES', {})
    def test_stage_finished_without_time(self):
        from services.status_poller import prepare_printer_data_for_broadcast
        r = prepare_printer_data_for_broadcast(
            [make_printer(state='FINISHED', finish_time=None)]
        )[0]
        assert r['print_stage'] == 'finished'
        assert r['stage_detail'] == 'Print complete'

    @patch('utils.status_poller_helpers.BAMBU_PRINTER_STATES', {})
    def test_stage_ejecting(self):
        from services.status_poller import prepare_printer_data_for_broadcast
        r = prepare_printer_data_for_broadcast([make_printer(state='EJECTING')])[0]
        assert r['print_stage'] == 'ejecting'
        assert r['stage_detail'] == 'Ejecting print'

    @patch('utils.status_poller_helpers.BAMBU_PRINTER_STATES', {})
    def test_stage_cooling(self):
        from services.status_poller import prepare_printer_data_for_broadcast
        r = prepare_printer_data_for_broadcast(
            [make_printer(state='COOLING', cooldown_target_temp=40)]
        )[0]
        assert r['print_stage'] == 'cooling'
        assert '40' in r['stage_detail']

    @patch('utils.status_poller_helpers.BAMBU_PRINTER_STATES', {})
    def test_stage_paused(self):
        from services.status_poller import prepare_printer_data_for_broadcast
        r = prepare_printer_data_for_broadcast([make_printer(state='PAUSED')])[0]
        assert r['print_stage'] == 'paused'
        assert r['stage_detail'] == 'Print paused'

    @patch('utils.status_poller_helpers.BAMBU_PRINTER_STATES', {})
    def test_stage_error_with_message(self):
        from services.status_poller import prepare_printer_data_for_broadcast
        r = prepare_printer_data_for_broadcast(
            [make_printer(state='ERROR', error_message='Thermal runaway')]
        )[0]
        assert r['print_stage'] == 'error'
        assert r['stage_detail'] == 'Thermal runaway'

    @patch('utils.status_poller_helpers.BAMBU_PRINTER_STATES', {})
    def test_stage_error_default_message(self):
        from services.status_poller import prepare_printer_data_for_broadcast
        r = prepare_printer_data_for_broadcast([make_printer(state='ERROR')])[0]
        assert r['print_stage'] == 'error'
        assert r['stage_detail'] == 'Printer error'

    @patch('utils.status_poller_helpers.BAMBU_PRINTER_STATES', {})
    def test_stage_idle_fallback(self):
        from services.status_poller import prepare_printer_data_for_broadcast
        r = prepare_printer_data_for_broadcast([make_printer(state='IDLE')])[0]
        assert r['print_stage'] == 'idle'

    # -- temperature handling --

    @patch('utils.status_poller_helpers.BAMBU_PRINTER_STATES', {})
    def test_temps_from_temps_dict(self):
        from services.status_poller import prepare_printer_data_for_broadcast
        r = prepare_printer_data_for_broadcast(
            [make_printer(temps={'nozzle': 210, 'bed': 60})]
        )[0]
        assert r['nozzle_temp'] == 210
        assert r['bed_temp'] == 60

    @patch('utils.status_poller_helpers.BAMBU_PRINTER_STATES', {})
    def test_direct_temp_fields_override_dict(self):
        from services.status_poller import prepare_printer_data_for_broadcast
        r = prepare_printer_data_for_broadcast(
            [make_printer(temps={'nozzle': 100, 'bed': 50}, nozzle_temp=215, bed_temp=65)]
        )[0]
        assert r['nozzle_temp'] == 215
        assert r['bed_temp'] == 65

    def test_bambu_mqtt_temps_override(self):
        from services.status_poller import prepare_printer_data_for_broadcast
        with patch('utils.status_poller_helpers.BAMBU_PRINTER_STATES', {
            'BambuP1': {'nozzle_temp': 220, 'bed_temp': 70, 'state': 'PRINTING'}
        }):
            r = prepare_printer_data_for_broadcast(
                [make_printer(name='BambuP1', type='bambu', state='PRINTING')]
            )[0]
            assert r['nozzle_temp'] == 220
            assert r['bed_temp'] == 70

    # -- Bambu error messages --

    def test_bambu_error_from_error_field(self):
        from services.status_poller import prepare_printer_data_for_broadcast
        with patch('utils.status_poller_helpers.BAMBU_PRINTER_STATES', {
            'B1': {'state': 'ERROR', 'nozzle_temp': 0, 'bed_temp': 0,
                   'error': 'Motor stall detected', 'hms_alerts': []}
        }):
            r = prepare_printer_data_for_broadcast(
                [make_printer(name='B1', type='bambu', state='ERROR')]
            )[0]
            assert r['error_message'] == 'Motor stall detected'

    def test_bambu_error_from_hms_alerts(self):
        from services.status_poller import prepare_printer_data_for_broadcast
        with patch('utils.status_poller_helpers.BAMBU_PRINTER_STATES', {
            'B1': {'state': 'ERROR', 'nozzle_temp': 0, 'bed_temp': 0,
                   'error': None, 'hms_alerts': ['Nozzle clog', 'AMS jam']}
        }):
            r = prepare_printer_data_for_broadcast(
                [make_printer(name='B1', type='bambu', state='ERROR')]
            )[0]
            assert 'Nozzle clog' in r['error_message']
            assert 'AMS jam' in r['error_message']

    def test_bambu_error_unknown_fallback(self):
        from services.status_poller import prepare_printer_data_for_broadcast
        with patch('utils.status_poller_helpers.BAMBU_PRINTER_STATES', {
            'B1': {'state': 'ERROR', 'nozzle_temp': 0, 'bed_temp': 0,
                   'error': None, 'hms_alerts': []}
        }):
            r = prepare_printer_data_for_broadcast(
                [make_printer(name='B1', type='bambu', state='ERROR')]
            )[0]
            assert r['error_message'] == 'Unknown error'

    # -- invariants --

    @patch('utils.status_poller_helpers.BAMBU_PRINTER_STATES', {})
    def test_does_not_mutate_input(self):
        from services.status_poller import prepare_printer_data_for_broadcast
        printers = [make_printer(state='PRINTING', progress=50)]
        original = copy.deepcopy(printers)
        prepare_printer_data_for_broadcast(printers)
        assert printers == original

    @patch('utils.status_poller_helpers.BAMBU_PRINTER_STATES', {})
    def test_timestamps_preserved(self):
        from services.status_poller import prepare_printer_data_for_broadcast
        now = time.time()
        r = prepare_printer_data_for_broadcast([make_printer(
            state='FINISHED', print_started_at=now - 3600,
            finish_time=now - 60, ejection_start_time=now - 30,
        )])[0]
        assert r['print_started_at'] == now - 3600
        assert r['finish_time'] == now - 60
        assert r['ejection_start_time'] == now - 30

    @patch('utils.status_poller_helpers.BAMBU_PRINTER_STATES', {})
    def test_multiple_printers(self):
        from services.status_poller import prepare_printer_data_for_broadcast
        result = prepare_printer_data_for_broadcast([
            make_printer(name='P1', state='READY'),
            make_printer(name='P2', state='PRINTING', progress=50),
            make_printer(name='P3', state='FINISHED', finish_time=time.time() - 120),
        ])
        assert len(result) == 3
        assert result[0]['print_stage'] == 'ready'
        assert result[1]['print_stage'] == 'printing'
        assert result[2]['print_stage'] == 'finished'


# ===========================================================================
# update_bambu_printer_states  (MQTT -> PRINTERS sync)
# ===========================================================================

class TestUpdateBambuPrinterStates:
    """Verify Bambu MQTT state sync logic."""

    def _run(self, printers, bambu_states):
        """Run update_bambu_printer_states with mocked globals.  Returns save_data mock."""
        with patch('services.status_poller.PRINTERS', printers), \
             patch('services.status_poller.BAMBU_PRINTER_STATES', bambu_states), \
             patch('services.status_poller.save_data') as mock_save, \
             patch('services.status_poller.PRINTERS_FILE', '/tmp/test.json'):
            from services.status_poller import update_bambu_printer_states
            update_bambu_printer_states()
            return mock_save

    def test_propagates_state_and_data(self):
        printers = [make_printer(name='B1', type='bambu', state='READY')]
        bambu = {'B1': {'state': 'PRINTING', 'nozzle_temp': 220, 'bed_temp': 60,
                        'progress': 50, 'time_remaining': 1800, 'current_file': 'test.3mf'}}
        mock_save = self._run(printers, bambu)
        assert printers[0]['state'] == 'PRINTING'
        assert printers[0]['nozzle_temp'] == 220
        assert printers[0]['bed_temp'] == 60
        assert printers[0]['progress'] == 50
        assert printers[0]['file'] == 'test.3mf'
        mock_save.assert_called_once()

    def test_skips_non_bambu(self):
        printers = [make_printer(name='P1', type='prusa', state='READY')]
        self._run(printers, {'P1': {'state': 'PRINTING'}})
        assert printers[0]['state'] == 'READY'

    def test_skips_cooling(self):
        printers = [make_printer(name='B1', type='bambu', state='COOLING')]
        self._run(printers, {'B1': {'state': 'IDLE', 'nozzle_temp': 30, 'bed_temp': 25}})
        assert printers[0]['state'] == 'COOLING'

    def test_preserves_manual_ready_on_idle(self):
        printers = [make_printer(name='B1', type='bambu', state='READY', manually_set=True)]
        self._run(printers, {'B1': {'state': 'IDLE', 'nozzle_temp': 30, 'bed_temp': 25}})
        assert printers[0]['state'] == 'READY'
        assert printers[0]['nozzle_temp'] == 30   # temps still updated

    def test_manual_ready_allows_printing(self):
        printers = [make_printer(name='B1', type='bambu', state='READY', manually_set=True)]
        self._run(printers, {'B1': {'state': 'PRINTING', 'nozzle_temp': 220, 'bed_temp': 60,
                                    'progress': 10, 'time_remaining': 3600}})
        assert printers[0]['state'] == 'PRINTING'
        assert printers[0]['manually_set'] is False

    def test_blocks_finished_to_ready(self):
        printers = [make_printer(name='B1', type='bambu', state='FINISHED')]
        mock_save = self._run(printers, {'B1': {'state': 'READY', 'nozzle_temp': 30, 'bed_temp': 25}})
        assert printers[0]['state'] == 'FINISHED'
        mock_save.assert_not_called()

    def test_sets_finish_time_on_transition(self):
        printers = [make_printer(name='B1', type='bambu', state='PRINTING')]
        before = time.time()
        self._run(printers, {'B1': {'state': 'FINISHED', 'nozzle_temp': 200, 'bed_temp': 55}})
        after = time.time()
        assert printers[0]['state'] == 'FINISHED'
        assert before <= printers[0]['finish_time'] <= after

    def test_noop_when_no_bambu_states(self):
        printers = [make_printer(name='B1', type='bambu', state='READY')]
        mock_save = self._run(printers, {})
        assert printers[0]['state'] == 'READY'
        mock_save.assert_not_called()

    def test_clears_manual_on_ejecting(self):
        printers = [make_printer(name='B1', type='bambu', state='READY', manually_set=True)]
        self._run(printers, {'B1': {'state': 'EJECTING', 'nozzle_temp': 200, 'bed_temp': 55}})
        assert printers[0]['state'] == 'EJECTING'
        assert printers[0]['manually_set'] is False

    def test_file_fallback_key(self):
        """Falls back to 'file' key when 'current_file' absent."""
        printers = [make_printer(name='B1', type='bambu', state='READY')]
        self._run(printers, {'B1': {'state': 'PRINTING', 'file': 'fallback.3mf'}})
        assert printers[0]['file'] == 'fallback.3mf'


# ===========================================================================
# get_printer_status_async  (state-machine integration tests)
# ===========================================================================

class TestStateTransitions:
    """Test the state machine inside get_printer_status_async.

    Each test sets up a known PRINTERS state, provides a controlled API
    response via a mocked ``fetch_status``, runs the poller, and asserts
    the resulting printer state.
    """

    # -- helpers --

    @staticmethod
    def _make_session_mock(job_response=None):
        """Build aiohttp.ClientSession mock that returns *job_response* on GET.

        Uses MagicMock for the session and context-manager wrapper because
        aiohttp's ``session.get(url)`` returns a context-manager object (not a
        coroutine).  Only ``__aenter__`` / ``__aexit__`` need to be async.
        """
        mock_job_resp = MagicMock()
        if job_response:
            mock_job_resp.status = 200
            mock_job_resp.json = AsyncMock(return_value=job_response)
        else:
            mock_job_resp.status = 404
            mock_job_resp.json = AsyncMock(return_value={})

        mock_session = MagicMock()
        mock_get_cm = MagicMock()
        mock_get_cm.__aenter__ = AsyncMock(return_value=mock_job_resp)
        mock_get_cm.__aexit__ = AsyncMock(return_value=False)
        mock_session.get.return_value = mock_get_cm

        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)
        return mock_session_cm

    async def _run_poll(self, printers, api_responses, job_response=None,
                        bambu_states=None, orders=None):
        """Execute one poll cycle and return (printers, mock_socketio).

        *api_responses*: ``{printer_name: api_data_or_None}``
        *bambu_states*:  Optional dict to use as ``BAMBU_PRINTER_STATES``.
        *orders*:        Optional list to use as ``ORDERS``.
        """
        from services.status_poller import get_printer_status_async

        mock_socketio = MagicMock()
        mock_app = MagicMock()

        async def _fetch(session, printer):
            return printer, api_responses.get(printer['name'])

        _bs = bambu_states if bambu_states is not None else {}
        with patch('services.status_poller.PRINTERS', printers), \
             patch('services.status_poller.ORDERS', orders or []), \
             patch('services.status_poller.BAMBU_PRINTER_STATES', _bs), \
             patch('utils.status_poller_helpers.BAMBU_PRINTER_STATES', _bs), \
             patch('services.status_poller.save_data'), \
             patch('services.status_poller.load_data',
                   return_value={'total_filament_used_g': 0}), \
             patch('services.status_poller.PRINTERS_FILE', '/tmp/t.json'), \
             patch('services.status_poller.TOTAL_FILAMENT_FILE', '/tmp/tf.json'), \
             patch('services.status_poller.clear_stuck_ejection_locks'), \
             patch('services.status_poller.update_bambu_printer_states'), \
             patch('services.status_poller.fetch_status', new=_fetch), \
             patch('services.status_poller.decrypt_api_key', return_value='k'), \
             patch('services.status_poller.handle_finished_state_ejection'), \
             patch('services.status_poller.release_ejection_lock'), \
             patch('services.status_poller.clear_printer_ejection_state'), \
             patch('services.status_poller.get_printer_ejection_state',
                   return_value={'state': 'none'}), \
             patch('services.status_poller.log_api_poll_event'), \
             patch('services.status_poller.log_state_transition'), \
             patch('aiohttp.ClientSession',
                   return_value=self._make_session_mock(job_response)), \
             patch('threading.Timer', return_value=MagicMock()):
            await get_printer_status_async(
                mock_socketio, mock_app, batch_index=0, batch_size=10
            )

        return printers, mock_socketio

    # -- OFFLINE --

    @pytest.mark.asyncio
    async def test_offline_when_api_returns_none(self):
        printers = [make_printer()]
        result, _ = await self._run_poll(printers, {'Printer1': None})
        assert result[0]['state'] == 'OFFLINE'

    @pytest.mark.asyncio
    async def test_offline_on_fetch_exception(self):
        """fetch_status raising maps to OFFLINE."""
        from services.status_poller import get_printer_status_async

        printers = [make_printer()]
        mock_sio = MagicMock()

        async def _boom(session, printer):
            raise ConnectionError("refused")

        with patch('services.status_poller.PRINTERS', printers), \
             patch('services.status_poller.ORDERS', []), \
             patch('services.status_poller.BAMBU_PRINTER_STATES', {}), \
             patch('utils.status_poller_helpers.BAMBU_PRINTER_STATES', {}), \
             patch('services.status_poller.save_data'), \
             patch('services.status_poller.load_data',
                   return_value={'total_filament_used_g': 0}), \
             patch('services.status_poller.PRINTERS_FILE', '/tmp/t.json'), \
             patch('services.status_poller.TOTAL_FILAMENT_FILE', '/tmp/tf.json'), \
             patch('services.status_poller.clear_stuck_ejection_locks'), \
             patch('services.status_poller.update_bambu_printer_states'), \
             patch('services.status_poller.fetch_status', new=_boom), \
             patch('services.status_poller.decrypt_api_key', return_value='k'), \
             patch('services.status_poller.handle_finished_state_ejection'), \
             patch('services.status_poller.release_ejection_lock'), \
             patch('services.status_poller.clear_printer_ejection_state'), \
             patch('services.status_poller.get_printer_ejection_state',
                   return_value={'state': 'none'}), \
             patch('services.status_poller.log_api_poll_event'), \
             patch('services.status_poller.log_state_transition'), \
             patch('aiohttp.ClientSession',
                   return_value=self._make_session_mock()), \
             patch('threading.Timer', return_value=MagicMock()):
            await get_printer_status_async(mock_sio, MagicMock(), batch_index=0, batch_size=10)

        assert printers[0]['state'] == 'OFFLINE'

    # -- manually_set preservation --

    @pytest.mark.asyncio
    async def test_manual_ready_stays_ready_on_idle(self):
        printers = [make_printer(state='READY', manually_set=True)]
        result, _ = await self._run_poll(printers, {
            'Printer1': make_api_response(state='IDLE')
        })
        assert result[0]['state'] == 'READY'
        assert result[0]['manually_set'] is True

    @pytest.mark.asyncio
    async def test_manual_ready_transitions_to_printing(self):
        printers = [make_printer(state='READY', manually_set=True)]
        job = make_job_response(progress=10, file_name='part.gcode')
        result, _ = await self._run_poll(
            printers,
            {'Printer1': make_api_response(state='PRINTING')},
            job_response=job,
        )
        assert result[0]['state'] == 'PRINTING'

    # -- ejection-processed preservation --

    @pytest.mark.asyncio
    async def test_ejection_processed_ready_stays_ready(self):
        printers = [make_printer(state='READY', ejection_processed=True)]
        result, _ = await self._run_poll(printers, {
            'Printer1': make_api_response(state='IDLE')
        })
        assert result[0]['state'] == 'READY'

    # -- EJECTING preservation --

    @pytest.mark.asyncio
    async def test_ejecting_stays_while_in_progress(self):
        printers = [make_printer(state='EJECTING', ejection_in_progress=True)]
        result, _ = await self._run_poll(printers, {
            'Printer1': make_api_response(state='IDLE')
        })
        assert result[0]['state'] == 'EJECTING'

    @pytest.mark.asyncio
    async def test_ejecting_stays_with_ejection_file_printing(self):
        printers = [make_printer(state='EJECTING', file='ejection_test.gcode')]
        result, _ = await self._run_poll(printers, {
            'Printer1': make_api_response(state='PRINTING')
        })
        assert result[0]['state'] == 'EJECTING'

    # -- COOLING skip --

    @pytest.mark.asyncio
    async def test_cooling_preserves_state(self):
        """COOLING printer stays COOLING when bed temp is still above target."""
        printers = [make_printer(
            name='Printer1', type='bambu', state='COOLING',
            cooldown_target_temp=40, cooldown_order_id=1,
            finish_time=time.time() - 60,
        )]
        # Bed temp (50) still above target (40) -> stays COOLING
        bambu = {'Printer1': {'bed_temp': 50, 'state': 'IDLE'}}
        result, _ = await self._run_poll(
            printers,
            {'Printer1': make_api_response(state='IDLE', temp_bed=50)},
            bambu_states=bambu,
        )
        assert result[0]['state'] == 'COOLING'

    # -- stored FINISHED + API IDLE -> READY --

    @pytest.mark.asyncio
    async def test_stored_finished_api_idle_goes_ready(self):
        printers = [make_printer(state='FINISHED', finish_time=time.time() - 300)]
        result, _ = await self._run_poll(printers, {
            'Printer1': make_api_response(state='IDLE')
        })
        assert result[0]['state'] == 'READY'
        assert result[0]['manually_set'] is True

    # -- stored EJECTING + API IDLE -> READY --

    @pytest.mark.asyncio
    async def test_stored_ejecting_api_idle_goes_ready(self):
        printers = [make_printer(state='EJECTING', ejection_in_progress=False)]
        result, _ = await self._run_poll(printers, {
            'Printer1': make_api_response(state='IDLE')
        })
        assert result[0]['state'] == 'READY'
        assert result[0]['manually_set'] is True

    # -- socket emission --

    @pytest.mark.asyncio
    async def test_emits_status_update(self):
        printers = [make_printer()]
        _, mock_sio = await self._run_poll(printers, {
            'Printer1': make_api_response(state='IDLE')
        })
        mock_sio.emit.assert_called_once()
        event, payload = mock_sio.emit.call_args[0]
        assert event == 'status_update'
        assert 'printers' in payload
        assert 'total_filament' in payload
        assert 'orders' in payload

    # -- normal PRINTING updates --

    @pytest.mark.asyncio
    async def test_printing_updates_progress(self):
        printers = [make_printer(state='READY')]
        job = make_job_response(progress=42, time_remaining=900, file_name='widget.gcode')
        result, _ = await self._run_poll(
            printers,
            {'Printer1': make_api_response(state='PRINTING')},
            job_response=job,
        )
        assert result[0]['state'] == 'PRINTING'
        assert result[0]['progress'] == 42
        assert result[0]['file'] == 'widget.gcode'

    # -- service_mode printers are skipped --

    @pytest.mark.asyncio
    async def test_service_mode_printer_skipped(self):
        printers = [make_printer(state='READY', service_mode=True)]
        # No API response needed because it should never be fetched
        result, mock_sio = await self._run_poll(printers, {})
        # Printer state should be unchanged - the poller skips service_mode printers
        # (they are excluded from all_printers at line 307)
        # Socket still emits but with no printer changes
        assert result[0]['state'] == 'READY'
