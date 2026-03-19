"""
Subprocess runner for ArgyllCMS command-line tools.
Wraps QProcess for async execution with signal-based output.
"""

import os
from PySide6.QtCore import QObject, Signal, QProcess, QTimer


class ArgyllProcess(QObject):
    """Manages an ArgyllCMS subprocess with async I/O."""

    output_received = Signal(str)   # stdout line
    error_received = Signal(str)    # stderr line
    finished = Signal(int, str)     # exit_code, exit_status_string
    started = Signal()

    def __init__(self, bin_dir, parent=None):
        super().__init__(parent)
        self.bin_dir = bin_dir
        self.process = None
        self._buffer = b''
        self._err_buffer = b''

    def start(self, exe_name, args, working_dir=None):
        """Start an ArgyllCMS executable with given arguments."""
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.kill()
            self.process.waitForFinished(3000)

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.SeparateChannels)

        if working_dir:
            self.process.setWorkingDirectory(str(working_dir))

        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_finished)
        self.process.started.connect(self.started.emit)

        exe_path = os.path.join(self.bin_dir, exe_name)
        if os.name == 'nt' and not exe_name.endswith('.exe'):
            exe_path += '.exe'

        self.process.start(exe_path, args)

    def send_input(self, text):
        """Send text to the process stdin."""
        if self.process and self.process.state() == QProcess.Running:
            self.process.write((text).encode('utf-8'))

    def send_key(self, key):
        """Send a single key/character to stdin."""
        self.send_input(key)

    def is_running(self):
        return self.process is not None and self.process.state() == QProcess.Running

    def terminate(self):
        """Terminate the running process."""
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.terminate()
            QTimer.singleShot(3000, self._force_kill)

    def kill(self):
        """Force kill the running process."""
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.kill()

    def _force_kill(self):
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.kill()

    def _on_stdout(self):
        data = self.process.readAllStandardOutput().data()
        self._buffer += data
        while b'\n' in self._buffer:
            line, self._buffer = self._buffer.split(b'\n', 1)
            text = line.decode('utf-8', errors='replace').rstrip('\r')
            self.output_received.emit(text)
        # Also emit partial lines (prompts don't end with newline)
        if self._buffer:
            # Check for common prompt patterns
            partial = self._buffer.decode('utf-8', errors='replace')
            if any(p in partial for p in [':', '?', '>', '(', 'key']):
                self.output_received.emit(partial)
                self._buffer = b''

    def _on_stderr(self):
        data = self.process.readAllStandardError().data()
        self._err_buffer += data
        while b'\n' in self._err_buffer:
            line, self._err_buffer = self._err_buffer.split(b'\n', 1)
            text = line.decode('utf-8', errors='replace').rstrip('\r')
            self.error_received.emit(text)
        if self._err_buffer:
            partial = self._err_buffer.decode('utf-8', errors='replace')
            self.error_received.emit(partial)
            self._err_buffer = b''

    def _on_finished(self, exit_code, exit_status):
        # Flush remaining buffers
        if self._buffer:
            self.output_received.emit(
                self._buffer.decode('utf-8', errors='replace').rstrip('\r'))
            self._buffer = b''
        if self._err_buffer:
            self.error_received.emit(
                self._err_buffer.decode('utf-8', errors='replace').rstrip('\r'))
            self._err_buffer = b''

        status_str = 'normal' if exit_status == QProcess.NormalExit else 'crashed'
        self.finished.emit(exit_code, status_str)
