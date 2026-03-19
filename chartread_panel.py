"""
Chartread panel - Read printer test chart with visual feedback.
This is the main focus of the GUI: shows expected vs measured patch colors,
highlights misreadings, and provides strip-by-strip progress tracking.

Designed for ColorMunki Photo / CMYK workflow.
"""

import re
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QComboBox, QCheckBox, QLineEdit, QPushButton, QTextEdit,
    QFileDialog, QLabel, QMessageBox, QSplitter, QScrollArea,
    QGridLayout, QFrame, QToolTip, QSizePolicy, QHeaderView,
    QTableWidget, QTableWidgetItem, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QColor, QPainter, QFont, QBrush, QPen, QCursor

from cgats import CGATSFile
from color_utils import (
    cmyk_to_rgb, lab_to_rgb, xyz_to_rgb, xyz_to_lab,
    delta_e_94, delta_e_76, rgb_to_hex, device_color_to_rgb
)
from process_runner import ArgyllProcess


# ---------------------------------------------------------------------------
# Patch swatch widget - shows a single color patch with optional comparison
# ---------------------------------------------------------------------------
class PatchSwatch(QFrame):
    """A clickable color patch that shows expected and optionally measured color."""

    clicked = Signal(int)  # patch index

    def __init__(self, index, parent=None):
        super().__init__(parent)
        self.index = index
        self.location = ""
        self.expected_rgb = (200, 200, 200)
        self.measured_rgb = None
        self.delta_e = None
        self.is_read = False
        self.is_current_strip = False
        self.cmyk = (0, 0, 0, 0)
        self.expected_lab = None
        self.measured_lab = None

        self.setMinimumSize(18, 18)
        self.setMaximumSize(40, 40)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.PointingHandCursor)

    def set_expected(self, rgb, cmyk=None, lab=None, location=""):
        self.expected_rgb = rgb
        self.cmyk = cmyk or (0, 0, 0, 0)
        self.expected_lab = lab
        self.location = location
        self.update()

    def set_measured(self, rgb, lab=None, delta_e=None):
        self.measured_rgb = rgb
        self.measured_lab = lab
        self.delta_e = delta_e
        self.is_read = True
        self.update()

    def set_current_strip(self, is_current):
        self.is_current_strip = is_current
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)

        if self.is_read and self.measured_rgb:
            # Split view: left = expected, right = measured
            mid = rect.width() // 2
            left_rect = rect.adjusted(0, 0, -(rect.width() - mid), 0)
            right_rect = rect.adjusted(mid, 0, 0, 0)

            p.fillRect(left_rect, QColor(*self.expected_rgb))
            p.fillRect(right_rect, QColor(*self.measured_rgb))
        else:
            p.fillRect(rect, QColor(*self.expected_rgb))

        # Border
        if self.delta_e is not None and self.delta_e > 10:
            # High delta E - red warning border
            p.setPen(QPen(QColor(255, 0, 0), 3))
        elif self.delta_e is not None and self.delta_e > 5:
            # Medium delta E - orange border
            p.setPen(QPen(QColor(255, 165, 0), 2))
        elif self.is_current_strip:
            p.setPen(QPen(QColor(0, 120, 255), 2))
        elif self.is_read:
            p.setPen(QPen(QColor(0, 180, 0), 1))
        else:
            p.setPen(QPen(QColor(100, 100, 100), 1))

        p.drawRect(rect)
        p.end()

    def mousePressEvent(self, event):
        self.clicked.emit(self.index)

    def enterEvent(self, event):
        tip_parts = [f"Patch: {self.location}"]
        tip_parts.append(
            f"CMYK: {self.cmyk[0]:.1f} {self.cmyk[1]:.1f} "
            f"{self.cmyk[2]:.1f} {self.cmyk[3]:.1f}")
        if self.expected_lab:
            tip_parts.append(
                f"Expected Lab: {self.expected_lab[0]:.1f} "
                f"{self.expected_lab[1]:.1f} {self.expected_lab[2]:.1f}")
        if self.measured_lab:
            tip_parts.append(
                f"Measured Lab: {self.measured_lab[0]:.1f} "
                f"{self.measured_lab[1]:.1f} {self.measured_lab[2]:.1f}")
        if self.delta_e is not None:
            tip_parts.append(f"Delta E94: {self.delta_e:.2f}")
        QToolTip.showText(QCursor.pos(), "\n".join(tip_parts))


# ---------------------------------------------------------------------------
# Chart grid widget - shows all patches organized by strip
# ---------------------------------------------------------------------------
class ChartGrid(QScrollArea):
    """Scrollable grid showing all patches organized by strip rows."""

    patch_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.patches = []  # list of PatchSwatch widgets
        self.strip_labels = {}  # strip_name -> QLabel
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setSpacing(2)
        self.grid.setContentsMargins(4, 4, 4, 4)
        self.setWidget(self.container)
        self.setWidgetResizable(True)

    def load_chart(self, ti2_data, color_space='CMYK'):
        """Load chart layout from parsed .ti2 CGATS data."""
        # Clear existing
        for p in self.patches:
            p.deleteLater()
        self.patches.clear()
        for lbl in self.strip_labels.values():
            lbl.deleteLater()
        self.strip_labels.clear()

        # Remove old layout items
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        strips = ti2_data.get_strip_layout()
        if not strips:
            # No SAMPLE_LOC field - create a simple sequential layout
            self._load_sequential(ti2_data, color_space)
            return

        device_fields = ti2_data.get_device_fields()
        has_xyz = 'XYZ_X' in ti2_data.fields

        row = 0
        for strip_name in sorted(strips.keys()):
            # Strip label
            lbl = QLabel(f" {strip_name} ")
            lbl.setStyleSheet(
                "QLabel { font-weight: bold; background: #e0e0e0; "
                "padding: 2px 6px; border-radius: 3px; }")
            lbl.setAlignment(Qt.AlignCenter)
            self.grid.addWidget(lbl, row, 0)
            self.strip_labels[strip_name] = lbl

            for col_idx, (data_idx, patch_num, loc, data_row) in enumerate(strips[strip_name]):
                dev_vals = [float(data_row.get(f, 0)) for f in device_fields]
                rgb = device_color_to_rgb(dev_vals, color_space)

                lab = None
                if has_xyz:
                    xyz = ti2_data.get_xyz_values(data_row)
                    if len(xyz) == 3:
                        lab = xyz_to_lab(*xyz)
                        rgb = xyz_to_rgb(*xyz)

                swatch = PatchSwatch(data_idx, self.container)
                cmyk = tuple(dev_vals[:4]) if len(dev_vals) >= 4 else (0, 0, 0, 0)
                swatch.set_expected(rgb, cmyk=cmyk, lab=lab, location=loc)
                swatch.clicked.connect(self.patch_clicked.emit)
                self.grid.addWidget(swatch, row, col_idx + 1)
                self.patches.append(swatch)

            row += 1

    def _load_sequential(self, ti2_data, color_space):
        """Fallback: arrange patches in a simple grid."""
        device_fields = ti2_data.get_device_fields()
        cols_per_row = 21  # typical ColorMunki strip length
        row = 0
        col = 0
        for idx, data_row in enumerate(ti2_data.data):
            dev_vals = [float(data_row.get(f, 0)) for f in device_fields]
            rgb = device_color_to_rgb(dev_vals, color_space)
            cmyk = tuple(dev_vals[:4]) if len(dev_vals) >= 4 else (0, 0, 0, 0)

            swatch = PatchSwatch(idx, self.container)
            loc = data_row.get('SAMPLE_LOC', f'#{idx+1}')
            swatch.set_expected(rgb, cmyk=cmyk, location=str(loc))
            swatch.clicked.connect(self.patch_clicked.emit)
            self.grid.addWidget(swatch, row, col)
            self.patches.append(swatch)

            col += 1
            if col >= cols_per_row:
                col = 0
                row += 1

    def highlight_strip(self, strip_name):
        """Highlight the current strip being read."""
        strips = {}
        for p in self.patches:
            if p.location:
                match = re.match(r'^([A-Z]+)', p.location)
                if match:
                    s = match.group(1)
                    if s not in strips:
                        strips[s] = []
                    strips[s].append(p)

        for s, patches in strips.items():
            is_current = (s == strip_name)
            for p in patches:
                p.set_current_strip(is_current)

        # Highlight strip label
        for name, lbl in self.strip_labels.items():
            if name == strip_name:
                lbl.setStyleSheet(
                    "QLabel { font-weight: bold; background: #4090ff; "
                    "color: white; padding: 2px 6px; border-radius: 3px; }")
            else:
                lbl.setStyleSheet(
                    "QLabel { font-weight: bold; background: #e0e0e0; "
                    "padding: 2px 6px; border-radius: 3px; }")

    def mark_strip_done(self, strip_name):
        """Mark a strip label as completed."""
        lbl = self.strip_labels.get(strip_name)
        if lbl:
            lbl.setStyleSheet(
                "QLabel { font-weight: bold; background: #40c040; "
                "color: white; padding: 2px 6px; border-radius: 3px; }")

    def get_patch_by_index(self, data_idx):
        """Find patch swatch by data index."""
        for p in self.patches:
            if p.index == data_idx:
                return p
        return None

    def get_patch_by_location(self, location):
        """Find patch swatch by location string (e.g. 'A5')."""
        for p in self.patches:
            if p.location == location:
                return p
        return None


# ---------------------------------------------------------------------------
# Patch detail panel - shows detailed info for selected patch
# ---------------------------------------------------------------------------
class PatchDetailPanel(QFrame):
    """Shows detailed comparison for a selected patch."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumWidth(280)
        layout = QVBoxLayout(self)

        self.title_lbl = QLabel("Select a patch to see details")
        self.title_lbl.setStyleSheet("font-weight: bold; font-size: 12pt;")
        layout.addWidget(self.title_lbl)

        # Color swatches side by side
        swatch_layout = QHBoxLayout()

        self.expected_frame = QFrame()
        self.expected_frame.setMinimumSize(80, 80)
        self.expected_frame.setStyleSheet("background: #cccccc; border: 2px solid #888;")
        exp_layout = QVBoxLayout()
        exp_layout.addWidget(QLabel("Expected"))
        exp_layout.addWidget(self.expected_frame)
        swatch_layout.addLayout(exp_layout)

        self.measured_frame = QFrame()
        self.measured_frame.setMinimumSize(80, 80)
        self.measured_frame.setStyleSheet("background: #cccccc; border: 2px solid #888;")
        meas_layout = QVBoxLayout()
        meas_layout.addWidget(QLabel("Measured"))
        meas_layout.addWidget(self.measured_frame)
        swatch_layout.addLayout(meas_layout)

        layout.addLayout(swatch_layout)

        # Values
        self.info_table = QTableWidget(6, 2)
        self.info_table.setHorizontalHeaderLabels(["Property", "Value"])
        self.info_table.horizontalHeader().setStretchLastSection(True)
        self.info_table.verticalHeader().setVisible(False)
        self.info_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.info_table.setSelectionMode(QAbstractItemView.NoSelection)
        layout.addWidget(self.info_table)

        self.delta_e_lbl = QLabel("")
        self.delta_e_lbl.setStyleSheet("font-size: 14pt; font-weight: bold;")
        self.delta_e_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.delta_e_lbl)

        layout.addStretch()

    def show_patch(self, patch):
        """Update display for given PatchSwatch."""
        self.title_lbl.setText(f"Patch {patch.location}")

        # Expected color
        r, g, b = patch.expected_rgb
        self.expected_frame.setStyleSheet(
            f"background: {rgb_to_hex(r, g, b)}; border: 2px solid #888;")

        # Measured color
        if patch.measured_rgb:
            r2, g2, b2 = patch.measured_rgb
            self.measured_frame.setStyleSheet(
                f"background: {rgb_to_hex(r2, g2, b2)}; border: 2px solid #888;")
        else:
            self.measured_frame.setStyleSheet(
                "background: #cccccc; border: 2px dashed #888;")

        # Info table
        rows = []
        rows.append(("Location", patch.location))
        c, m, y, k = patch.cmyk
        rows.append(("CMYK", f"{c:.1f}  {m:.1f}  {y:.1f}  {k:.1f}"))
        if patch.expected_lab:
            L, a, b = patch.expected_lab
            rows.append(("Expected Lab", f"{L:.1f}  {a:.1f}  {b:.1f}"))
        if patch.measured_lab:
            L, a, b = patch.measured_lab
            rows.append(("Measured Lab", f"{L:.1f}  {a:.1f}  {b:.1f}"))
        if patch.delta_e is not None:
            rows.append(("Delta E94", f"{patch.delta_e:.2f}"))
        rows.append(("Status", "Read" if patch.is_read else "Not read"))

        self.info_table.setRowCount(len(rows))
        for i, (prop, val) in enumerate(rows):
            self.info_table.setItem(i, 0, QTableWidgetItem(prop))
            self.info_table.setItem(i, 1, QTableWidgetItem(str(val)))

        # Delta E display
        if patch.delta_e is not None:
            de = patch.delta_e
            if de > 10:
                color = "#ff0000"
                verdict = "BAD - likely misread!"
            elif de > 5:
                color = "#ff8800"
                verdict = "Warning - check"
            elif de > 2:
                color = "#888800"
                verdict = "Acceptable"
            else:
                color = "#008800"
                verdict = "Good"
            self.delta_e_lbl.setText(f"dE94 = {de:.2f}  ({verdict})")
            self.delta_e_lbl.setStyleSheet(
                f"font-size: 14pt; font-weight: bold; color: {color};")
        else:
            self.delta_e_lbl.setText("")


# ---------------------------------------------------------------------------
# Main Chartread Panel
# ---------------------------------------------------------------------------
class ChartreadPanel(QWidget):
    """Full chartread interface with visual chart, measurement feedback."""

    def __init__(self, bin_dir, parent=None):
        super().__init__(parent)
        self.bin_dir = bin_dir
        self.process = ArgyllProcess(bin_dir, self)
        self.process.output_received.connect(self._on_output)
        self.process.error_received.connect(self._on_error)
        self.process.finished.connect(self._on_finished)

        self.ti2_data = None
        self.current_strip = None
        self.readings = {}        # patch_index -> measured Lab
        self.strip_status = {}    # strip_name -> 'reading'|'done'
        self._output_lines = []   # buffer for parsing multi-line output
        self._misread_count = 0
        self._total_read = 0

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # --- Top: file selection and options ---
        top_bar = QHBoxLayout()

        self.work_dir_edit = QLineEdit()
        self.work_dir_edit.setPlaceholderText("Working directory...")
        dir_btn = QPushButton("Browse...")
        dir_btn.clicked.connect(self._browse_dir)
        top_bar.addWidget(QLabel("Dir:"))
        top_bar.addWidget(self.work_dir_edit, 1)
        top_bar.addWidget(dir_btn)

        self.basename_edit = QLineEdit("profile")
        self.basename_edit.setMaximumWidth(150)
        top_bar.addWidget(QLabel("Name:"))
        top_bar.addWidget(self.basename_edit)

        self.load_btn = QPushButton("Load Chart")
        self.load_btn.clicked.connect(self._load_chart)
        top_bar.addWidget(self.load_btn)

        layout.addLayout(top_bar)

        # --- Main splitter: chart grid + detail panel ---
        splitter = QSplitter(Qt.Horizontal)

        # Left: chart grid + progress
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Stats bar
        self.stats_lbl = QLabel("No chart loaded")
        self.stats_lbl.setStyleSheet(
            "QLabel { padding: 4px; background: #f0f0f0; border-radius: 3px; }")
        left_layout.addWidget(self.stats_lbl)

        # Chart grid
        self.chart_grid = ChartGrid()
        self.chart_grid.patch_clicked.connect(self._on_patch_clicked)
        left_layout.addWidget(self.chart_grid, 1)

        splitter.addWidget(left_widget)

        # Right: patch detail
        self.detail_panel = PatchDetailPanel()
        splitter.addWidget(self.detail_panel)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        # --- Options bar ---
        opts_layout = QHBoxLayout()

        self.resume_check = QCheckBox("Resume (-r)")
        self.resume_check.setToolTip("Resume partly read chart")
        opts_layout.addWidget(self.resume_check)

        self.patch_mode_check = QCheckBox("Patch-by-patch (-p)")
        self.patch_mode_check.setToolTip("Measure patch by patch instead of strips")
        opts_layout.addWidget(self.patch_mode_check)

        self.no_spectral_check = QCheckBox("No spectral (-n)")
        opts_layout.addWidget(self.no_spectral_check)

        self.save_lab_check = QCheckBox("Save Lab (-L)")
        self.save_lab_check.setChecked(True)
        opts_layout.addWidget(self.save_lab_check)

        self.suppress_warn_check = QCheckBox("Suppress warnings (-S)")
        opts_layout.addWidget(self.suppress_warn_check)

        opts_layout.addStretch()
        layout.addLayout(opts_layout)

        # --- Control buttons ---
        ctrl_layout = QHBoxLayout()

        self.start_btn = QPushButton("Start Chartread")
        self.start_btn.setStyleSheet(
            "QPushButton { padding: 8px 16px; font-weight: bold; "
            "background: #2196F3; color: white; }")
        self.start_btn.clicked.connect(self._start_reading)
        ctrl_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet(
            "QPushButton { padding: 8px 16px; background: #f44336; color: white; }")
        self.stop_btn.clicked.connect(self._stop_reading)
        self.stop_btn.setEnabled(False)
        ctrl_layout.addWidget(self.stop_btn)

        ctrl_layout.addStretch()

        # Quick-send buttons for common chartread prompts
        self.send_enter_btn = QPushButton("Enter (confirm)")
        self.send_enter_btn.clicked.connect(lambda: self._send_key('\n'))
        self.send_enter_btn.setEnabled(False)
        ctrl_layout.addWidget(self.send_enter_btn)

        self.send_space_btn = QPushButton("Space (trigger)")
        self.send_space_btn.clicked.connect(lambda: self._send_key(' '))
        self.send_space_btn.setEnabled(False)
        ctrl_layout.addWidget(self.send_space_btn)

        self.send_d_btn = QPushButton("d (done)")
        self.send_d_btn.clicked.connect(lambda: self._send_key('d\n'))
        self.send_d_btn.setEnabled(False)
        ctrl_layout.addWidget(self.send_d_btn)

        self.send_q_btn = QPushButton("q (quit)")
        self.send_q_btn.clicked.connect(lambda: self._send_key('q\n'))
        self.send_q_btn.setEnabled(False)
        ctrl_layout.addWidget(self.send_q_btn)

        layout.addLayout(ctrl_layout)

        # --- Console I/O ---
        console_group = QGroupBox("Chartread Console")
        console_layout = QVBoxLayout(console_group)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumHeight(180)
        self.console.setStyleSheet(
            "QTextEdit { font-family: 'Consolas', 'Courier New', monospace; "
            "font-size: 9pt; background: #1e1e1e; color: #d4d4d4; }")
        console_layout.addWidget(self.console)

        # Input line for custom commands
        input_layout = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("Type command and press Enter to send to chartread...")
        self.input_edit.returnPressed.connect(self._send_input_line)
        self.input_edit.setEnabled(False)
        input_layout.addWidget(self.input_edit)

        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self._send_input_line)
        self.send_btn.setEnabled(False)
        input_layout.addWidget(self.send_btn)

        console_layout.addLayout(input_layout)
        layout.addWidget(console_group)

        # --- Misread summary table ---
        self.misread_group = QGroupBox("Potential Misreads (dE94 > 5)")
        misread_layout = QVBoxLayout(self.misread_group)
        self.misread_table = QTableWidget(0, 5)
        self.misread_table.setHorizontalHeaderLabels([
            "Patch", "CMYK", "Expected Lab", "Measured Lab", "dE94"])
        self.misread_table.horizontalHeader().setStretchLastSection(True)
        self.misread_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.misread_table.setMaximumHeight(120)
        misread_layout.addWidget(self.misread_table)
        self.misread_group.setVisible(False)
        layout.addWidget(self.misread_group)

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Working Directory")
        if d:
            self.work_dir_edit.setText(d)

    def set_context(self, work_dir, basename):
        if work_dir:
            self.work_dir_edit.setText(work_dir)
        if basename:
            self.basename_edit.setText(basename)

    def _load_chart(self):
        """Load the .ti2 file and display the chart grid."""
        work_dir = self.work_dir_edit.text()
        basename = self.basename_edit.text()
        if not work_dir or not basename:
            QMessageBox.warning(self, "Error", "Set working directory and base name first.")
            return

        ti2_path = Path(work_dir) / f"{basename}.ti2"
        if not ti2_path.exists():
            QMessageBox.warning(self, "Error",
                f"File not found: {ti2_path}\nRun printtarg first.")
            return

        try:
            self.ti2_data = CGATSFile.parse(ti2_path)
        except Exception as e:
            QMessageBox.critical(self, "Parse Error", f"Failed to parse .ti2:\n{e}")
            return

        cs = self.ti2_data.get_color_space() or 'CMYK'
        self.chart_grid.load_chart(self.ti2_data, cs)

        n = self.ti2_data.get_num_patches()
        strips = self.ti2_data.get_strip_layout()
        n_strips = len(strips) if strips else '?'
        self.stats_lbl.setText(
            f"Chart loaded: {n} patches, {n_strips} strips | "
            f"Read: 0/{n} | Misreads: 0")

        self.console.append(f"Loaded chart: {ti2_path}")
        self.console.append(f"  {n} patches, {n_strips} strips, colorspace: {cs}")

    def _build_args(self):
        args = ['-v']

        if self.resume_check.isChecked():
            args.append('-r')
        if self.patch_mode_check.isChecked():
            args.append('-p')
        if self.no_spectral_check.isChecked():
            args.append('-n')
        if self.save_lab_check.isChecked():
            args.append('-L')
        if self.suppress_warn_check.isChecked():
            args.append('-S')

        args.append(self.basename_edit.text())
        return args

    def _start_reading(self):
        work_dir = self.work_dir_edit.text()
        if not work_dir:
            QMessageBox.warning(self, "Error", "Set working directory first.")
            return

        ti2 = Path(work_dir) / f"{self.basename_edit.text()}.ti2"
        if not ti2.exists():
            QMessageBox.warning(self, "Error", f"No .ti2 file found: {ti2}")
            return

        # Load chart if not already loaded
        if not self.ti2_data:
            self._load_chart()

        self.console.clear()
        self._misread_count = 0
        self._total_read = 0
        self.misread_table.setRowCount(0)
        self.misread_group.setVisible(False)

        args = self._build_args()
        self.console.append(f"Starting: chartread {' '.join(args)}\n")

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.send_enter_btn.setEnabled(True)
        self.send_space_btn.setEnabled(True)
        self.send_d_btn.setEnabled(True)
        self.send_q_btn.setEnabled(True)
        self.input_edit.setEnabled(True)
        self.send_btn.setEnabled(True)

        self.process.start('chartread', args, work_dir)

    def _stop_reading(self):
        self.process.terminate()

    def _send_key(self, key):
        self.process.send_key(key)

    def _send_input_line(self):
        text = self.input_edit.text()
        if text:
            self.process.send_input(text + '\n')
            self.console.append(f"> {text}")
            self.input_edit.clear()

    def _on_output(self, text):
        """Parse chartread stdout for readings and status."""
        self.console.append(text)
        self._output_lines.append(text)

        # --- Detect strip prompts ---
        # Pattern: "Ready to read strip X" or "Strip X:"
        strip_match = re.search(
            r'(?:strip|Strip|STRIP)\s+(?:pass\s+)?(\d+)\s*\(([A-Z]+)\)', text)
        if not strip_match:
            strip_match = re.search(r'(?:strip|Strip)\s+([A-Z]+)', text)
        if strip_match:
            strip_name = strip_match.group(strip_match.lastindex)
            self.current_strip = strip_name
            self.strip_status[strip_name] = 'reading'
            self.chart_grid.highlight_strip(strip_name)
            self.console.append(f"  >> Now reading strip {strip_name}")

        # --- Detect reading results ---
        # chartread outputs measured values - look for Lab or XYZ values
        # Typical: "Result is XYZ: 12.34 56.78 90.12" or patch-by-patch output
        # Also: location-based readings like "A5: ..."

        # Try to detect patch readings with location
        loc_match = re.search(
            r'([A-Z]+\d+)\s*:\s*.*?'
            r'(?:XYZ|Lab)\s*[:=]?\s*([\d.+-]+)\s+([\d.+-]+)\s+([\d.+-]+)', text)
        if loc_match:
            location = loc_match.group(1)
            v1 = float(loc_match.group(2))
            v2 = float(loc_match.group(3))
            v3 = float(loc_match.group(4))

            is_lab = 'Lab' in text or 'lab' in text
            if is_lab:
                measured_lab = (v1, v2, v3)
            else:
                measured_lab = xyz_to_lab(v1, v2, v3)

            self._update_patch_measurement(location, measured_lab)

        # Detect XYZ values in standard output format
        xyz_match = re.search(
            r'(?:^|\s)(\d+)\s+.*?'
            r'XYZ\s*[:=]?\s*([\d.+-]+)\s+([\d.+-]+)\s+([\d.+-]+)', text)
        if xyz_match and not loc_match:
            patch_id = int(xyz_match.group(1))
            X = float(xyz_match.group(2))
            Y = float(xyz_match.group(3))
            Z = float(xyz_match.group(4))
            measured_lab = xyz_to_lab(X, Y, Z)
            self._update_patch_by_id(patch_id, measured_lab)

        # Detect strip completion
        if self.current_strip and any(
            p in text.lower() for p in ['strip read', 'accepted', 'ok']):
            self.strip_status[self.current_strip] = 'done'
            self.chart_grid.mark_strip_done(self.current_strip)

        # Detect "got" readings (common chartread output for patch readings)
        got_match = re.search(
            r'(?:got|Got)\s+(\d+)\s+.*?([\d.]+)\s+([\d.+-]+)\s+([\d.+-]+)', text)
        if got_match:
            pass  # These are summary lines, individual patches handled above

    def _on_error(self, text):
        """Handle stderr output."""
        self.console.append(f'<span style="color: #ff6666;">{text}</span>')

    def _update_patch_measurement(self, location, measured_lab):
        """Update a patch with measured values by location string."""
        patch = self.chart_grid.get_patch_by_location(location)
        if not patch:
            return

        measured_rgb = lab_to_rgb(*measured_lab)

        # Calculate delta E if we have expected values
        delta_e = None
        if patch.expected_lab:
            delta_e = delta_e_94(patch.expected_lab, measured_lab)

        patch.set_measured(measured_rgb, lab=measured_lab, delta_e=delta_e)
        self.readings[patch.index] = measured_lab
        self._total_read += 1

        # Track misreads
        if delta_e is not None and delta_e > 5:
            self._misread_count += 1
            self._add_misread_row(patch, measured_lab, delta_e)

        self._update_stats()

    def _update_patch_by_id(self, patch_id, measured_lab):
        """Update a patch by sample ID (1-based index)."""
        patch = self.chart_grid.get_patch_by_index(patch_id - 1)
        if not patch:
            return

        measured_rgb = lab_to_rgb(*measured_lab)
        delta_e = None
        if patch.expected_lab:
            delta_e = delta_e_94(patch.expected_lab, measured_lab)

        patch.set_measured(measured_rgb, lab=measured_lab, delta_e=delta_e)
        self.readings[patch.index] = measured_lab
        self._total_read += 1

        if delta_e is not None and delta_e > 5:
            self._misread_count += 1
            self._add_misread_row(patch, measured_lab, delta_e)

        self._update_stats()

    def _add_misread_row(self, patch, measured_lab, delta_e):
        """Add a row to the misread warning table."""
        self.misread_group.setVisible(True)
        row = self.misread_table.rowCount()
        self.misread_table.insertRow(row)

        self.misread_table.setItem(row, 0, QTableWidgetItem(patch.location))

        c, m, y, k = patch.cmyk
        self.misread_table.setItem(row, 1,
            QTableWidgetItem(f"{c:.0f} {m:.0f} {y:.0f} {k:.0f}"))

        if patch.expected_lab:
            L, a, b = patch.expected_lab
            self.misread_table.setItem(row, 2,
                QTableWidgetItem(f"{L:.1f} {a:.1f} {b:.1f}"))

        L, a, b = measured_lab
        self.misread_table.setItem(row, 3,
            QTableWidgetItem(f"{L:.1f} {a:.1f} {b:.1f}"))

        de_item = QTableWidgetItem(f"{delta_e:.2f}")
        if delta_e > 10:
            de_item.setBackground(QBrush(QColor(255, 100, 100)))
        else:
            de_item.setBackground(QBrush(QColor(255, 200, 100)))
        self.misread_table.setItem(row, 4, de_item)

    def _update_stats(self):
        """Update the statistics label."""
        total = self.ti2_data.get_num_patches() if self.ti2_data else 0
        strips = self.ti2_data.get_strip_layout() if self.ti2_data else {}
        done_strips = sum(1 for s in self.strip_status.values() if s == 'done')

        warning = ""
        if self._misread_count > 0:
            warning = f"  *** {self._misread_count} POTENTIAL MISREADS ***"

        self.stats_lbl.setText(
            f"Read: {self._total_read}/{total} patches | "
            f"Strips: {done_strips}/{len(strips)} | "
            f"Misreads (dE>5): {self._misread_count}{warning}")

        if self._misread_count > 0:
            self.stats_lbl.setStyleSheet(
                "QLabel { padding: 4px; background: #ffcccc; "
                "border-radius: 3px; font-weight: bold; }")
        else:
            self.stats_lbl.setStyleSheet(
                "QLabel { padding: 4px; background: #ccffcc; "
                "border-radius: 3px; }")

    def _on_patch_clicked(self, index):
        """Show detail for clicked patch."""
        patch = self.chart_grid.get_patch_by_index(index)
        if patch:
            self.detail_panel.show_patch(patch)

    def _on_finished(self, exit_code, status):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.send_enter_btn.setEnabled(False)
        self.send_space_btn.setEnabled(False)
        self.send_d_btn.setEnabled(False)
        self.send_q_btn.setEnabled(False)
        self.input_edit.setEnabled(False)
        self.send_btn.setEnabled(False)

        if exit_code == 0:
            self.console.append("\n--- Chartread completed successfully ---")
            ti3 = Path(self.work_dir_edit.text()) / f"{self.basename_edit.text()}.ti3"
            if ti3.exists():
                self.console.append(f"Output: {ti3}")
                # Parse .ti3 and update all patch measurements
                self._load_ti3_results(ti3)
        else:
            self.console.append(f"\n--- Chartread exited (code {exit_code}, {status}) ---")

    def _load_ti3_results(self, ti3_path):
        """After chartread completes, load .ti3 and update all patch visuals."""
        try:
            ti3 = CGATSFile.parse(ti3_path)
        except Exception as e:
            self.console.append(f"Warning: couldn't parse .ti3: {e}")
            return

        if not self.ti2_data:
            return

        has_lab = 'LAB_L' in ti3.fields
        has_xyz = 'XYZ_X' in ti3.fields

        if not has_lab and not has_xyz:
            self.console.append("Warning: .ti3 has no Lab or XYZ values")
            return

        self.console.append(f"\nLoading {len(ti3.data)} measurements from .ti3...")
        self._misread_count = 0
        self._total_read = 0
        self.misread_table.setRowCount(0)

        for ti3_row in ti3.data:
            sample_id = ti3_row.get('SAMPLE_ID', ti3_row.get('SampleID', None))
            loc = ti3_row.get('SAMPLE_LOC', '')

            if has_lab:
                measured_lab = (
                    float(ti3_row.get('LAB_L', 0)),
                    float(ti3_row.get('LAB_A', 0)),
                    float(ti3_row.get('LAB_B', 0))
                )
            elif has_xyz:
                X = float(ti3_row.get('XYZ_X', 0))
                Y = float(ti3_row.get('XYZ_Y', 0))
                Z = float(ti3_row.get('XYZ_Z', 0))
                measured_lab = xyz_to_lab(X, Y, Z)
            else:
                continue

            measured_rgb = lab_to_rgb(*measured_lab)

            # Find corresponding patch
            patch = None
            if loc:
                patch = self.chart_grid.get_patch_by_location(loc)
            if not patch and sample_id is not None:
                patch = self.chart_grid.get_patch_by_index(int(sample_id) - 1)

            if patch:
                delta_e = None
                if patch.expected_lab:
                    delta_e = delta_e_94(patch.expected_lab, measured_lab)

                patch.set_measured(measured_rgb, lab=measured_lab, delta_e=delta_e)
                self._total_read += 1

                if delta_e is not None and delta_e > 5:
                    self._misread_count += 1
                    self._add_misread_row(patch, measured_lab, delta_e)

        # Mark all strips as done
        strips = self.ti2_data.get_strip_layout()
        for strip_name in strips:
            self.chart_grid.mark_strip_done(strip_name)
            self.strip_status[strip_name] = 'done'

        self._update_stats()
        self.console.append(
            f"Loaded {self._total_read} measurements. "
            f"Misreads (dE>5): {self._misread_count}")
