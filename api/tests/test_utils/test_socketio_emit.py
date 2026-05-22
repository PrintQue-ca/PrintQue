"""Tests for socketio_emit payload enrichment."""

from utils.socketio_emit import _enrich_status_payload


def test_enrich_adds_queue_from_orders():
    payload = {'printers': [], 'orders': [{'id': 1}]}
    out = _enrich_status_payload(payload)
    assert out['queue'] == [{'id': 1}]
    assert out['orders'] == [{'id': 1}]


def test_enrich_adds_orders_from_queue():
    payload = {'printers': [], 'queue': [{'id': 2}]}
    out = _enrich_status_payload(payload)
    assert out['queue'] == [{'id': 2}]
    assert out['orders'] == [{'id': 2}]


def test_enrich_printers_only_unchanged():
    payload = {'printers': [{'name': 'P1'}], 'total_filament': 1.0}
    out = _enrich_status_payload(payload)
    assert 'queue' not in out
    assert 'orders' not in out
