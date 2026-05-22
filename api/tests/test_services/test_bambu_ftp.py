"""Tests for Bambu FTP filename normalization and print URLs."""
from services.bambu_ftp import (
    normalize_bambu_remote_filename,
    bambu_project_file_url,
    bambu_ftp_stor_path,
    paths_for_stor,
    prepare_gcode_for_bambu,
)


def test_normalize_gcode_dot_3mf():
    assert normalize_bambu_remote_filename('poker-vase-mode.gcode.3mf') == 'poker-vase-mode.3mf'


def test_normalize_plain_3mf_unchanged():
    assert normalize_bambu_remote_filename('model.3mf') == 'model.3mf'


def test_project_file_url_root_upload_maps_to_sdcard():
    assert bambu_project_file_url('foo.gcode') == 'file:///sdcard/foo.gcode'


def test_ftp_stor_path_is_root_filename():
    assert bambu_ftp_stor_path('foo.gcode.3mf') == 'foo.3mf'


def test_paths_for_stor_root_upload():
    paths = paths_for_stor('part.gcode')
    assert paths['stor_path'] == 'part.gcode'
    assert paths['gcode_param'] == '/sdcard/part.gcode'
    assert paths['project_url'] == 'file:///sdcard/part.gcode'


def test_prepare_renames_gcode_dot_3mf(tmp_path):
    f = tmp_path / 'part.gcode.3mf'
    f.write_bytes(b'x')
    ok, path, remote = prepare_gcode_for_bambu(str(f), str(tmp_path))
    assert ok
    assert remote == 'part.3mf'
    assert path == str(f)
