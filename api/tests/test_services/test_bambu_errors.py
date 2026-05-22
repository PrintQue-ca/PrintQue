"""Tests for Bambu error decoding helpers."""
from services.bambu_errors import (
    build_print_start_failure_detail,
    describe_print_error,
    format_hms_code,
    is_generic_bambu_reason,
)


def test_is_generic_bambu_reason():
    assert is_generic_bambu_reason('error string')
    assert is_generic_bambu_reason('fail')
    assert not is_generic_bambu_reason('filament runout')


def test_format_hms_code():
    assert format_hms_code(0x03000C0000010004) == '0300-0C00-0001-0004'


def test_describe_print_error():
    assert 'Invalid G-code' in describe_print_error(67108864)


def test_build_print_start_failure_detail_generic_reason():
    detail = build_print_start_failure_detail(
        cmd='gcode_file',
        response={
            'command': 'gcode_file',
            'result': 'fail',
            'reason': 'error string',
            'param': 'foo.gcode',
        },
        sent_command={'print': {'command': 'gcode_file', 'param': '/sdcard/foo.gcode'}},
        printer_state={'print_error': 67108864, 'gcode_state': 'IDLE'},
    )
    assert 'error string' in detail
    assert 'Invalid G-code' in detail
    assert 'gcode_state=IDLE' in detail
    assert '/sdcard/foo.gcode' in detail
