"""Regression tests: pytest must not use or write real ~/PrintQueData."""

import os

import pytest

from utils.paths import get_data_dir, get_orders_file, get_user_home_printque_dir


def test_data_dir_points_at_session_temp(temp_data_dir):
    assert os.environ.get('DATA_DIR') == temp_data_dir
    expected = os.path.join(temp_data_dir, 'PrintQueData')
    assert os.path.normcase(os.path.realpath(get_data_dir())) == os.path.normcase(
        os.path.realpath(expected)
    )


def test_orders_file_under_test_data_dir(temp_data_dir):
    orders_file = os.path.normcase(os.path.realpath(get_orders_file()))
    temp_base = os.path.normcase(os.path.realpath(temp_data_dir))
    assert orders_file.startswith(temp_base)


def test_save_data_refuses_real_home_when_misconfigured(monkeypatch, temp_data_dir):
    """Guard must block writes to ~/PrintQueData if paths were resolved incorrectly."""
    from services.state import save_data

    monkeypatch.setenv('PYTEST_CURRENT_TEST', 'test_data_isolation.py::guard')
    real_orders = os.path.join(get_user_home_printque_dir(), 'orders.json')
    data_dir = get_data_dir()
    if os.path.normcase(os.path.realpath(real_orders)).startswith(
        os.path.normcase(os.path.realpath(data_dir))
    ):
        pytest.skip('Test home and DATA_DIR coincide on this machine')

    with pytest.raises(RuntimeError, match='Refusing to write'):
        save_data(real_orders, [])
