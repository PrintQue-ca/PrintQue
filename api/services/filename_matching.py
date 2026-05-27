"""Shared filename matching helpers for printer-reported file names."""

import os


def match_shortened_filename(full_filename, shortened_filename):
    """Match potentially shortened filenames (for 8.3 FAT compatibility)."""
    if not full_filename or not shortened_filename:
        return False

    full_base = os.path.splitext(os.path.basename(full_filename))[0]
    short_base = os.path.splitext(os.path.basename(shortened_filename))[0]

    if full_base.upper() == short_base.upper():
        return True

    if len(short_base) >= 6 and short_base[:6].upper() == full_base[:6].upper() and '~' in short_base:
        return True

    if len(short_base) >= 3 and full_base.upper().startswith(short_base[:3].upper()):
        return True

    if len(short_base) >= 8 and short_base[:8].upper() == full_base[:8].upper():
        return True

    if short_base.upper() in full_base.upper() or full_base.upper() in short_base.upper():
        return True

    return False
