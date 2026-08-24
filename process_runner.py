"""
Subprocess runner for ArgyllCMS command-line tools.
Wraps QProcess for async execution with signal-based output.
"""

import os
from PySide6.QtCore import QObject, Signal, QProcess, QTimer

"""
Subprocess runner for ArgyllCMS command-line tools.
Wraps subprocess and QProcess for terminal or async execution.
"""

import os
import subprocess
from PySide6.QtCore import QObject, Signal, QProcess, QTimer


class ArgyllProcess(QObject):
    """Manages an ArgyllCMS subprocess with terminal or async I/O."""

    output_received = Signal(str)   # stdout line
    error_received = Signal(str)    # stderr line
    finished = Signal(int, str)     # exit_code, exit_status_string
    started = Signal()

    def __init__(self, bin_dir, parent=None):
        super().__init__(parent)
        self.bin_dir = bin_dir
        self.process = None
        self.native_proc = None
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(500)
        self._poll_timer.timeout.connect(self._check_native_finished)

    def start_in_console(self, exe_name, args, working_dir=None):
        exe_path = os.path.join(self.bin_dir, exe_name)
        if os.name == 'nt' and not exe_name.endswith('.exe'):
            exe_path += '.exe'

        if os.name == 'nt':
            # Use /c so cmd.exe closes naturally when chartread finishes
            cmd = ['cmd.exe', '/c', exe_path] + list(args)
            creationflags = subprocess.CREATE_NEW_CONSOLE
        else:
            cmd = [exe_path] + list(args)
            creationflags = 0

        self.native_proc = subprocess.Popen(
            cmd,
            cwd=str(working_dir) if working_dir else None,
            creationflags=creationflags
        )
        self.started.emit()
        self._poll_timer.start()

    def _check_native_finished(self):
        if self.native_proc is not None:
            ret_code = self.native_proc.poll()
            if ret_code is not None:
                self._poll_timer.stop()
                self.native_proc = None
                
                # Convert unsigned 32-bit uint to signed 32-bit int
                if ret_code > 2147483647:
                    ret_code -= 4294967296

                # 0 = clean exit, -1073741510 / 1 = user quit / closed window
                if ret_code in (0, 1, -1073741510):
                    status = 'normal'
                else:
                    status = 'error'

                self.finished.emit(ret_code, status)

    def send_input(self, text):
        pass  # Keyboard input goes straight into the opened console window

    def send_key(self, key):
        pass

    def is_running(self):
        if self.native_proc:
            return self.native_proc.poll() is None
        return self.process is not None and self.process.state() == QProcess.Running

    def terminate(self):
        if self.native_proc and self.native_proc.poll() is None:
            self.native_proc.terminate()