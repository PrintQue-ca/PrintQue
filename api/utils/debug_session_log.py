"""Temporary debug logging for agent debug sessions (NDJSON to workspace log file)."""
import json
import time
from pathlib import Path

_LOG_PATH = Path(__file__).resolve().parents[2] / 'debug-6c1a97.log'
_SESSION = '6c1a97'


def agent_debug_log(location, message, data=None, hypothesis_id=None, run_id=None):
    # #region agent log
    try:
        payload = {
            'sessionId': _SESSION,
            'location': location,
            'message': message,
            'data': data or {},
            'timestamp': int(time.time() * 1000),
        }
        if hypothesis_id:
            payload['hypothesisId'] = hypothesis_id
        if run_id:
            payload['runId'] = run_id
        with open(_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps(payload) + '\n')
    except Exception:
        pass
    # #endregion
