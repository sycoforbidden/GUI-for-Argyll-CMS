"""
ArgyllCMS Profiling GUI - Entry Point
Launch this to start the application.
"""

import sys
import os
from pathlib import Path

# Add gui directory to path for imports
gui_dir = Path(__file__).parent
sys.path.insert(0, str(gui_dir))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from main_window import MainWindow


def find_bin_dir():
    """Locate the ArgyllCMS bin directory relative to this script."""
    # Expected layout: Argyll_V3.5.0/gui/main.py -> Argyll_V3.5.0/bin/
    base = gui_dir.parent
    bin_dir = base / 'bin'
    if bin_dir.exists():
        return str(bin_dir)

    # Fallback: check if bin is in PATH
    for p in os.environ.get('PATH', '').split(os.pathsep):
        if (Path(p) / 'targen.exe').exists() or (Path(p) / 'targen').exists():
            return p

    return str(bin_dir)  # Return expected path even if not found


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ArgyllCMS GUI")
    app.setStyle('Fusion')

    # Set a clean default font
    font = app.font()
    font.setPointSize(10)
    app.setFont(font)

    bin_dir = find_bin_dir()
    window = MainWindow(bin_dir)
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
