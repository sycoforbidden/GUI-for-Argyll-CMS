"""
Main window for ArgyllCMS GUI - workflow-based interface.
Steps: targen -> printtarg -> chartread -> printcal -> colprof
"""

import sys
import os
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QStatusBar, QToolBar, QPushButton, QMessageBox,
    QApplication, QStyleFactory
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QAction, QIcon

from targen_panel import TargenPanel
from printtarg_panel import PrinttargPanel
from chartread_panel import ChartreadPanel
from printcal_panel import PrintcalPanel
from colprof_panel import ColprofPanel


class MainWindow(QMainWindow):
    """Main application window with workflow tabs."""

    def __init__(self, bin_dir):
        super().__init__()
        self.bin_dir = bin_dir
        self.setWindowTitle("ArgyllCMS Profiling GUI - CMYK Workflow")
        self.setMinimumSize(1100, 800)
        self.resize(1280, 900)

        self._build_ui()
        self._build_menu()
        self.statusBar().showMessage("Ready - Select working directory and start workflow")

    def _build_ui(self):
        # Central tab widget
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.North)
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #ccc; }
            QTabBar::tab {
                padding: 8px 20px;
                font-size: 10pt;
                min-width: 120px;
            }
            QTabBar::tab:selected {
                font-weight: bold;
                background: #e8f0fe;
            }
        """)

        # Create panels
        self.targen_panel = TargenPanel(self.bin_dir)
        self.printtarg_panel = PrinttargPanel(self.bin_dir)
        self.chartread_panel = ChartreadPanel(self.bin_dir)
        self.printcal_panel = PrintcalPanel(self.bin_dir)
        self.colprof_panel = ColprofPanel(self.bin_dir)

        # Add tabs with step numbers
        self.tabs.addTab(self.targen_panel, "1. Generate Patches")
        self.tabs.addTab(self.printtarg_panel, "2. Layout Chart")
        self.tabs.addTab(self.chartread_panel, "3. Read Chart")
        self.tabs.addTab(self.printcal_panel, "4. Calibration")
        self.tabs.addTab(self.colprof_panel, "5. Create Profile")

        # Connect tab changes to propagate context
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.setCentralWidget(self.tabs)

        # Workflow navigation toolbar
        toolbar = QToolBar("Workflow")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))

        prev_action = QAction("Previous Step", self)
        prev_action.triggered.connect(self._prev_step)
        toolbar.addAction(prev_action)

        next_action = QAction("Next Step", self)
        next_action.triggered.connect(self._next_step)
        toolbar.addAction(next_action)

        toolbar.addSeparator()

        sync_action = QAction("Sync Dir/Name to All Steps", self)
        sync_action.triggered.connect(self._sync_context)
        toolbar.addAction(sync_action)

        self.addToolBar(toolbar)

    def _build_menu(self):
        menu = self.menuBar()

        file_menu = menu.addMenu("File")
        file_menu.addAction("Sync Settings to All Steps", self._sync_context)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        help_menu = menu.addMenu("Help")
        help_menu.addAction("About", self._show_about)

    def _on_tab_changed(self, index):
        """Propagate working dir and basename when switching tabs."""
        self._propagate_context_to(index)

    def _propagate_context_to(self, tab_index):
        """Push current working dir and basename to the target tab."""
        # Get context from targen (source of truth)
        work_dir = self.targen_panel.get_working_dir()
        basename = self.targen_panel.get_basename()

        panels = [
            None,  # targen is the source
            self.printtarg_panel,
            self.chartread_panel,
            self.printcal_panel,
            self.colprof_panel,
        ]

        if tab_index > 0 and tab_index < len(panels):
            panel = panels[tab_index]
            if panel and hasattr(panel, 'set_context'):
                panel.set_context(work_dir, basename)

    def _sync_context(self):
        """Sync working directory and basename from targen to all panels."""
        work_dir = self.targen_panel.get_working_dir()
        basename = self.targen_panel.get_basename()

        for panel in [self.printtarg_panel, self.chartread_panel,
                      self.printcal_panel, self.colprof_panel]:
            panel.set_context(work_dir, basename)

        self.statusBar().showMessage(
            f"Synced: dir={work_dir}, name={basename}")

    def _prev_step(self):
        idx = self.tabs.currentIndex()
        if idx > 0:
            self.tabs.setCurrentIndex(idx - 1)

    def _next_step(self):
        idx = self.tabs.currentIndex()
        if idx < self.tabs.count() - 1:
            self.tabs.setCurrentIndex(idx + 1)

    def _show_about(self):
        QMessageBox.about(self, "About ArgyllCMS GUI",
            "ArgyllCMS Profiling GUI\n\n"
            "A graphical interface for the ArgyllCMS CMYK printer\n"
            "profiling workflow.\n\n"
            "Wraps: targen, printtarg, chartread, printcal, colprof\n\n"
            f"Argyll bin: {self.bin_dir}")
