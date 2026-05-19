"""Decode and format Bambu printer MQTT/HMS error information."""

from __future__ import annotations

from typing import Any

# Mirrors common codes from bambu_handler.BAMBU_ERROR_CODES (subset for lookup without import cycle).
PRINT_ERROR_MESSAGES: dict[int, str] = {
    83935248: "File not found or invalid format",
    50348044: "Print preparation failed",
    84033543: "Printer busy or in error state",
    50331648: "No print job active or print job ended",
    50331649: "Print cancelled by user",
    50331650: "Print failed - check printer status",
    50331651: "Filament runout detected",
    50331652: "Hotend temperature error",
    50331653: "Heatbed temperature error",
    50331656: "SD card error",
    50331657: "File transfer error",
    67108864: "Invalid G-code file",
    67108865: "File too large",
    67108866: "Unsupported file format",
    67108867: "File corrupted",
    100663298: "Invalid command format",
    100663299: "Command queue full",
}

GENERIC_BAMBU_REASONS = frozenset({
    'error string',
    'error',
    'fail',
    'failed',
    'unknown',
})


def is_generic_bambu_reason(reason: str | None) -> bool:
    if not reason:
        return True
    return reason.strip().lower() in GENERIC_BAMBU_REASONS


def format_hms_code(value: Any) -> str:
    """Format HMS attr/code as XXXX-XXXX-XXXX-XXXX for wiki lookup."""
    if value is None:
        return ''
    if isinstance(value, str):
        raw = value.replace('_', '').replace('-', '').upper()
        if raw.startswith('0X'):
            raw = raw[2:]
    else:
        try:
            raw = f"{int(value):X}".upper()
        except (TypeError, ValueError):
            return str(value)
    if not raw:
        return ''
    raw = raw.zfill(16)[-16:]
    return f"{raw[0:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:16]}"


def describe_hms_alerts(hms_list: list | None) -> list[str]:
    if not hms_list:
        return []
    lines = []
    for alert in hms_list:
        if not isinstance(alert, dict):
            continue
        attr = alert.get('attr')
        code = alert.get('code')
        if attr is not None:
            formatted = format_hms_code(attr)
            wiki = "https://wiki.bambulab.com/en/hms/home"
            lines.append(
                f"HMS {formatted} (attr={attr}, code={code}) — search at {wiki}"
            )
        elif code is not None:
            lines.append(f"HMS code={code}")
    return lines


def describe_print_error(print_error: Any) -> str | None:
    if print_error is None:
        return None
    try:
        code = int(print_error)
    except (TypeError, ValueError):
        return None
    if code == 0:
        return None
    return PRINT_ERROR_MESSAGES.get(code, f"print_error code {code} (0x{code:X})")


def build_print_start_failure_detail(
    *,
    cmd: str,
    response: dict,
    sent_command: dict | None = None,
    printer_state: dict | None = None,
) -> str:
    """
    Build a human-readable rejection message from MQTT command ack + cached state.

    Bambu often returns reason='error string' with no detail; print_error and HMS
  usually arrive in the next push_status (or the same packet if present).
    """
    reason = (response.get('reason') or '').strip()
    result = response.get('result', '')
    parts: list[str] = []

    if is_generic_bambu_reason(reason):
        parts.append(
            f"Printer returned generic reason '{reason or result}' "
            "(firmware placeholder — see print_error/HMS below if present)"
        )
    else:
        parts.append(f"reason={reason or result}")

    print_error = response.get('print_error')
    if print_error is None and printer_state:
        print_error = printer_state.get('last_print_error') or printer_state.get('print_error')
    err_text = describe_print_error(print_error)
    if err_text:
        parts.append(err_text)

    hms = response.get('hms')
    if not hms and printer_state:
        hms = printer_state.get('hms_alerts_raw')
    if hms:
        parts.extend(describe_hms_alerts(hms if isinstance(hms, list) else []))

    gcode_state = response.get('gcode_state')
    if gcode_state:
        parts.append(f"gcode_state={gcode_state}")
    elif printer_state and printer_state.get('gcode_state'):
        parts.append(f"gcode_state={printer_state.get('gcode_state')}")

    if sent_command:
        parts.append(f"sent_command={sent_command}")

    param = response.get('param')
    if param and sent_command:
        sent_param = (sent_command.get('print') or {}).get('param')
        if sent_param and param != sent_param:
            parts.append(
                f"note: printer echoed param={param!r} but we sent param={sent_param!r}"
            )

    if not parts:
        return f"Print start failed ({cmd}): {response!r}"
    return f"Print start failed ({cmd}): " + "; ".join(parts)
