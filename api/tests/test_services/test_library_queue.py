"""Unit tests for library_queue helpers."""

from services.library_queue import library_item_has_active_prints


class TestLibraryItemHasActivePrints:
    def test_fulfilled_job_does_not_block(self):
        queue = [
            {'id': 41, 'library_item_id': 14, 'sent': 2, 'quantity': 2, 'deleted': False},
        ]
        printers = [{'name': 'lil', 'order_id': 46, 'state': 'PRINTING'}]
        assert library_item_has_active_prints(14, queue, printers) is False

    def test_partial_sent_blocks(self):
        queue = [
            {'id': 41, 'library_item_id': 14, 'sent': 1, 'quantity': 2, 'deleted': False},
        ]
        assert library_item_has_active_prints(14, queue, []) is True

    def test_printer_printing_same_job_blocks(self):
        queue = [
            {'id': 41, 'library_item_id': 14, 'sent': 2, 'quantity': 2, 'deleted': False},
        ]
        printers = [{'name': 'p1', 'order_id': 41, 'state': 'PRINTING'}]
        assert library_item_has_active_prints(14, queue, printers) is True

    def test_finished_printer_state_does_not_block(self):
        queue = [
            {'id': 41, 'library_item_id': 14, 'sent': 0, 'quantity': 2, 'deleted': False},
        ]
        printers = [{'name': 'p1', 'order_id': 41, 'state': 'FINISHED'}]
        assert library_item_has_active_prints(14, queue, printers) is False

    def test_skips_deleted_queue_jobs(self):
        queue = [
            {'id': 42, 'library_item_id': 14, 'sent': 2, 'quantity': 2, 'deleted': True},
        ]
        assert library_item_has_active_prints(14, queue, []) is False
