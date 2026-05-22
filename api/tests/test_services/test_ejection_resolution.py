"""Tests for ejection code ID resolution and auto-save helpers."""

from unittest.mock import patch

import pytest

from services.state import (
    EJECTION_CODES,
    ORDERS,
    auto_save_ejection_code,
    apply_ejection_fields_to_order,
    count_orders_using_ejection_code,
    migrate_legacy_order_ejection_fields,
    resolve_ejection_gcode,
)


@pytest.fixture(autouse=True)
def mock_persistence():
    """Unit tests for ejection logic should not write JSON to disk."""
    with patch('services.state.save_data'):
        yield


@pytest.fixture(autouse=True)
def reset_ejection_state():
    """Isolate global ejection state between tests."""
    EJECTION_CODES.clear()
    ORDERS.clear()
    yield
    EJECTION_CODES.clear()
    ORDERS.clear()


class TestResolveEjectionGcode:
    def test_resolve_existing_code(self):
        EJECTION_CODES.append({
            'id': 'code-1',
            'name': 'Test',
            'gcode': 'G28 X Y',
        })
        gcode, name = resolve_ejection_gcode('code-1')
        assert gcode == 'G28 X Y'
        assert name == 'Test'

    def test_resolve_missing_code(self):
        gcode, name = resolve_ejection_gcode('missing')
        assert gcode is None
        assert name is None


class TestAutoSaveEjectionCode:
    def test_creates_new_preset(self):
        code = auto_save_ejection_code('G28 X Y\nM84', 'My Custom')
        assert code['id']
        assert code['name'] == 'My Custom'
        assert len(EJECTION_CODES) == 1

    def test_deduplicates_by_content(self):
        first = auto_save_ejection_code('G28 X Y ; comment', 'First')
        second = auto_save_ejection_code('G28 X Y', 'Second')
        assert first['id'] == second['id']
        assert len(EJECTION_CODES) == 1


class TestApplyEjectionFieldsToOrder:
    def test_stores_id_not_gcode(self):
        preset = auto_save_ejection_code('G1 X10', 'Preset A')
        order = {}
        apply_ejection_fields_to_order(
            order,
            ejection_enabled=True,
            ejection_code_id=preset['id'],
        )
        assert order['ejection_code_id'] == preset['id']
        assert 'end_gcode' not in order

    def test_auto_saves_custom_gcode(self):
        order = {}
        apply_ejection_fields_to_order(
            order,
            ejection_enabled=True,
            end_gcode='G28 X Y',
            name_hint='part.gcode',
        )
        assert order['ejection_code_id']
        gcode, _ = resolve_ejection_gcode(order['ejection_code_id'])
        assert gcode == 'G28 X Y'


class TestMigrateLegacyOrders:
    def test_migrates_end_gcode_to_id(self):
        ORDERS.append({
            'id': 1,
            'ejection_enabled': True,
            'end_gcode': 'G28 X Y',
            'filename': 'test.gcode',
        })
        migrate_legacy_order_ejection_fields()
        assert 'end_gcode' not in ORDERS[0]
        assert ORDERS[0]['ejection_code_id']
        gcode, _ = resolve_ejection_gcode(ORDERS[0]['ejection_code_id'])
        assert gcode == 'G28 X Y'


class TestCountOrdersUsingEjectionCode:
    def test_counts_references(self):
        code = auto_save_ejection_code('G28', 'Ref')
        ORDERS.append({'id': 1, 'ejection_code_id': code['id'], 'deleted': False})
        ORDERS.append({'id': 2, 'ejection_code_id': code['id'], 'deleted': True})
        assert count_orders_using_ejection_code(code['id']) == 1
