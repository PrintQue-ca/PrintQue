"""Tests for periodic pending-distribution helpers."""

from unittest.mock import patch

from services.library_queue import normalize_queue_job
from services.order_distributor import pending_distribution_needed


def make_bambu_printer(name='Bambu1', state='READY', **overrides):
    base = {
        'name': name,
        'type': 'bambu',
        'state': state,
        'status': 'Ready',
        'service_mode': False,
        'ejection_in_progress': False,
    }
    base.update(overrides)
    return base


def make_partial_job(job_id=1, sent=1, quantity=2):
    return normalize_queue_job({
        'id': job_id,
        'filename': 'part.gcode',
        'filepath': '/tmp/part.gcode',
        'quantity': quantity,
        'sent': sent,
        'status': 'partial',
    })


class TestPendingDistributionNeeded:
    def test_no_pending_jobs_ready_printer(self):
        printers = [make_bambu_printer()]
        with patch('services.order_distributor.QUEUE_JOBS', []), \
             patch('services.order_distributor.PRINTERS', printers), \
             patch('services.order_distributor.BAMBU_PRINTER_STATES', {}):
            assert pending_distribution_needed() is False

    def test_partial_job_ready_bambu(self):
        printers = [make_bambu_printer()]
        jobs = [make_partial_job()]
        with patch('services.order_distributor.QUEUE_JOBS', jobs), \
             patch('services.order_distributor.PRINTERS', printers), \
             patch('services.order_distributor.BAMBU_PRINTER_STATES', {}):
            assert pending_distribution_needed() is True

    def test_partial_job_finished_printer(self):
        printers = [make_bambu_printer(state='FINISHED')]
        jobs = [make_partial_job()]
        with patch('services.order_distributor.QUEUE_JOBS', jobs), \
             patch('services.order_distributor.PRINTERS', printers), \
             patch('services.order_distributor.BAMBU_PRINTER_STATES', {}):
            assert pending_distribution_needed() is False

    def test_partial_job_bambu_m400_pending(self):
        printers = [make_bambu_printer()]
        jobs = [make_partial_job()]
        bambu_states = {
            'Bambu1': {
                'ejection_m400_pending': 1,
                'waiting_for_m400': False,
            },
        }
        with patch('services.order_distributor.QUEUE_JOBS', jobs), \
             patch('services.order_distributor.PRINTERS', printers), \
             patch('services.order_distributor.BAMBU_PRINTER_STATES', bambu_states):
            assert pending_distribution_needed() is False

    def test_fulfilled_job_ready_printer(self):
        printers = [make_bambu_printer()]
        job = make_partial_job(sent=2, quantity=2)
        job['status'] = 'fulfilled'
        jobs = [job]
        with patch('services.order_distributor.QUEUE_JOBS', jobs), \
             patch('services.order_distributor.PRINTERS', printers), \
             patch('services.order_distributor.BAMBU_PRINTER_STATES', {}):
            assert pending_distribution_needed() is False
