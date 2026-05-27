import zipfile

from services.printer_utils import extract_print_time_from_file


def test_extracts_prusa_orca_estimated_print_time_from_footer(tmp_path):
    path = tmp_path / 'footer_time.gcode'
    path.write_text(
        'G28\n'
        'G1 X10 Y10\n'
        '; estimated printing time (normal mode) = 1h 2m 3s\n',
        encoding='utf-8',
    )

    assert extract_print_time_from_file(str(path)) == 3723


def test_extracts_cura_time_header_seconds(tmp_path):
    path = tmp_path / 'cura_time.gcode'
    path.write_text(';TIME:12345\nG28\n', encoding='utf-8')

    assert extract_print_time_from_file(str(path)) == 12345


def test_extracts_cura_time_header_float_seconds(tmp_path):
    path = tmp_path / 'cura_float_time.gcode'
    path.write_text(';TIME:209.287\nG28\n', encoding='utf-8')

    assert extract_print_time_from_file(str(path)) == 209


def test_extracts_partial_time_components(tmp_path):
    path = tmp_path / 'partial_time.gcode'
    path.write_text(
        '; estimated printing time (normal mode) = 8m 13s\nG28\n',
        encoding='utf-8',
    )

    assert extract_print_time_from_file(str(path)) == 493


def test_returns_none_when_print_time_metadata_missing(tmp_path):
    path = tmp_path / 'no_time.gcode'
    path.write_text('; filament used [g] = 5.0\nG28\n', encoding='utf-8')

    assert extract_print_time_from_file(str(path)) is None


def test_extracts_print_time_from_embedded_3mf_gcode(tmp_path):
    path = tmp_path / 'with_gcode.3mf'
    with zipfile.ZipFile(path, 'w') as zip_file:
        zip_file.writestr(
            'Metadata/plate_1.gcode',
            'G28\n; estimated printing time (normal mode) = 2h 5m\n',
        )

    assert extract_print_time_from_file(str(path)) == 7500
