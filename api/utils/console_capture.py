import sys
import io
import threading
from datetime import datetime, timedelta
from collections import deque
import time
import logging

class ConsoleCapture:
    """
    Captures stdout and stderr into a time-based memory buffer (deque).
    It acts as a 'Tee' by writing to both the original stream and the internal buffer.
    """
    def __init__(self, max_lines=10000, max_age_minutes=30):
        self.max_lines = max_lines
        self.max_age_minutes = max_age_minutes
        self.buffer = deque()
        self.lock = threading.Lock()
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        self.tee_stdout = None
        self.tee_stderr = None
        self._started = False

    def start(self):
        """Start capturing console output by replacing sys.stdout and sys.stderr."""
        if self._started:
            return
            
        self._started = True
        
        # Create tee outputs
        self.tee_stdout = TeeOutput(self.original_stdout, self, 'stdout')
        self.tee_stderr = TeeOutput(self.original_stderr, self, 'stderr')
        
        # Replace stdout and stderr
        sys.stdout = self.tee_stdout
        sys.stderr = self.tee_stderr
        
        # Also capture logging output by adding a handler
        self.setup_logging_capture()

    def setup_logging_capture(self):
        """Add a logging handler to capture all log messages"""
        # Create a custom logging handler
        class CaptureHandler(logging.Handler):
            def __init__(self, console_capture):
                super().__init__()
                self.console_capture = console_capture
                
            def emit(self, record):
                try:
                    msg = self.format(record)
                    # Add newline if not present
                    if not msg.endswith('\n'):
                        msg += '\n'
                    self.console_capture.write(msg, 'logging')
                except Exception:
                    pass
        
        # Add handler to root logger
        capture_handler = CaptureHandler(self)
        capture_handler.setLevel(logging.DEBUG)
        capture_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        
        # Get root logger and add our handler
        root_logger = logging.getLogger()
        root_logger.addHandler(capture_handler)
        
        # Also add to werkzeug logger (Flask's built-in server)
        werkzeug_logger = logging.getLogger('werkzeug')
        werkzeug_logger.addHandler(capture_handler)

    def stop(self):
        """Stop capturing console output and restore original streams."""
        if sys.stdout is self.tee_stdout:
            sys.stdout = self.original_stdout
        if sys.stderr is self.tee_stderr:
            sys.stderr = self.original_stderr
        self._started = False

    def write(self, text, stream_type='stdout'):
        """Write text to buffer with timestamp and perform buffer cleanup."""
        if not text:  # Skip completely empty writes
            return
            
        with self.lock:
            timestamp = datetime.now()
            
            # Handle different types of text input
            if isinstance(text, bytes):
                text = text.decode('utf-8', errors='replace')
            
            # Store the text as-is, preserving all formatting
            self.buffer.append({
                'timestamp': timestamp,
                'text': text,
                'type': stream_type
            })

            # Remove old entries (Line limit)
            while len(self.buffer) > self.max_lines:
                self.buffer.popleft()

            # Remove entries older than max age (Time limit)
            cutoff_time = datetime.now() - timedelta(minutes=self.max_age_minutes)
            while self.buffer and self.buffer[0]['timestamp'] < cutoff_time:
                self.buffer.popleft()

    def get_recent_output(self, minutes=5):
        """Get console output from the last N minutes."""
        with self.lock:
            cutoff_time = datetime.now() - timedelta(minutes=minutes)
            recent_lines = []

            for entry in self.buffer:
                if entry['timestamp'] >= cutoff_time:
                    # Format: timestamp - [type] text
                    timestamp_str = entry['timestamp'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    type_label = f"[{entry['type'].upper()}]" if entry['type'] != 'stdout' else ""
                    
                    # Split text into lines and format each
                    text_lines = entry['text'].splitlines(True)
                    for line in text_lines:
                        if line.strip():  # Only include non-empty lines in output
                            formatted_line = f"{timestamp_str} {type_label} {line}"
                            recent_lines.append(formatted_line)

            return recent_lines

    def get_all_output(self):
        """Get all captured console output."""
        with self.lock:
            all_lines = []
            for entry in self.buffer:
                timestamp_str = entry['timestamp'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                type_label = f"[{entry['type'].upper()}]" if entry['type'] != 'stdout' else ""
                
                # Split text into lines and format each
                text_lines = entry['text'].splitlines(True)
                for line in text_lines:
                    if line.strip():  # Only include non-empty lines
                        formatted_line = f"{timestamp_str} {type_label} {line}"
                        all_lines.append(formatted_line)
                        
            return all_lines

class TeeOutput:
    """Class to split output between original stream and our buffer"""
    def __init__(self, stream, console_capture, stream_type):
        self.stream = stream
        self.stream_type = stream_type
        self.console_capture = console_capture
        self.encoding = getattr(stream, 'encoding', 'utf-8')

    def write(self, text):
        try:
            # Write to original stream
            self.stream.write(text)
            self.stream.flush()
        except:
            pass  # Ignore errors writing to original stream
        
        # Always capture to buffer
        self.console_capture.write(text, self.stream_type)
        return len(text)

    def flush(self):
        try:
            self.stream.flush()
        except:
            pass

    def fileno(self):
        return self.stream.fileno()

    def isatty(self):
        return hasattr(self.stream, 'isatty') and self.stream.isatty()

    def __getattr__(self, attr):
        """Delegate any other attribute access to the original stream."""
        return getattr(self.stream, attr)

# Global console capture instance
console_capture = ConsoleCapture()