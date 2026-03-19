"""
Printtarg panel - Create printable test chart from .ti1 file.
Outputs TIFF + .ti2 for ColorMunki Photo / CMYK workflow.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QLineEdit,
    QPushButton, QTextEdit, QFileDialog, QLabel, QMessageBox
)
from PySide6.QtCore import Qt
from pathlib import Path
from process_runner import ArgyllProcess


class PrinttargPanel(QWidget):
    """Configuration panel for printtarg - test chart layout generation."""

    def __init__(self, bin_dir, parent=None):
        super().__init__(parent)
        self.bin_dir = bin_dir
        self.process = ArgyllProcess(bin_dir, self)
        self.process.output_received.connect(self._on_output)
        self.process.error_received.connect(self._on_output)
        self.process.finished.connect(self._on_finished)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # --- Input ---
        file_group = QGroupBox("Input / Output")
        file_layout = QFormLayout(file_group)
        self.work_dir_edit = QLineEdit()
        self.work_dir_edit.setPlaceholderText("Working directory (same as targen)...")
        dir_btn = QPushButton("Browse...")
        dir_btn.clicked.connect(self._browse_dir)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.work_dir_edit, 1)
        dir_row.addWidget(dir_btn)
        file_layout.addRow("Working Dir:", dir_row)

        self.basename_edit = QLineEdit("profile")
        file_layout.addRow("Base Name:", self.basename_edit)
        layout.addWidget(file_group)

        # --- Instrument ---
        inst_group = QGroupBox("Instrument & Layout")
        inst_layout = QFormLayout(inst_group)

        self.instrument_combo = QComboBox()
        self.instrument_combo.addItems([
            "CM - ColorMunki",
            "i1 - i1Pro (default)",
            "p3 - i1Pro3+",
            "SS - SpectroScan",
            "20 - DTP20",
            "22 - DTP22",
            "41 - DTP41",
            "51 - DTP51",
        ])
        self.instrument_combo.setCurrentIndex(0)  # ColorMunki default
        inst_layout.addRow("Instrument (-i):", self.instrument_combo)

        self.page_combo = QComboBox()
        self.page_combo.addItems([
            "A4    [210 x 297 mm]",
            "A4R   [297 x 210 mm]",
            "A3    [297 x 420 mm]",
            "A2    [420 x 594 mm]",
            "Letter [216 x 279 mm]",
            "LetterR [279 x 216 mm]",
            "Legal  [216 x 356 mm]",
            "11x17  [279 x 432 mm]",
            "Custom...",
        ])
        self.page_combo.setCurrentIndex(0)
        self.page_combo.currentIndexChanged.connect(self._on_page_changed)
        inst_layout.addRow("Page Size (-p):", self.page_combo)

        self.custom_size_edit = QLineEdit()
        self.custom_size_edit.setPlaceholderText("WWWxHHH (mm)")
        self.custom_size_edit.setVisible(False)
        inst_layout.addRow("Custom Size:", self.custom_size_edit)

        self.double_density_check = QCheckBox("Double density / Hex patches (-h)")
        self.double_density_check.setToolTip(
            "For ColorMunki: doubles patch count by halving row width")
        inst_layout.addRow(self.double_density_check)

        layout.addWidget(inst_group)

        # --- Output Format ---
        format_group = QGroupBox("Output Format")
        format_layout = QFormLayout(format_group)

        self.format_combo = QComboBox()
        self.format_combo.addItems([
            "TIFF 8-bit (-t)",
            "TIFF 16-bit (-T)",
            "PostScript (default)",
            "EPS (-e)",
        ])
        self.format_combo.setCurrentIndex(0)
        format_layout.addRow("Format:", self.format_combo)

        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 1200)
        self.dpi_spin.setValue(300)
        self.dpi_spin.setSuffix(" DPI")
        format_layout.addRow("Resolution:", self.dpi_spin)

        layout.addWidget(format_group)

        # --- Options ---
        opts_group = QGroupBox("Options")
        opts_layout = QFormLayout(opts_group)

        self.margin_spin = QDoubleSpinBox()
        self.margin_spin.setRange(0, 50)
        self.margin_spin.setValue(6.0)
        self.margin_spin.setSuffix(" mm")
        opts_layout.addRow("Page Margin (-m):", self.margin_spin)

        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.5, 3.0)
        self.scale_spin.setValue(1.0)
        self.scale_spin.setSingleStep(0.1)
        self.scale_spin.setToolTip("Scale patch and spacer size")
        opts_layout.addRow("Patch Scale (-a):", self.scale_spin)

        self.no_randomize_check = QCheckBox("Don't randomize patch locations (-r)")
        opts_layout.addRow(self.no_randomize_check)

        # Calibration file
        self.cal_edit = QLineEdit()
        self.cal_edit.setPlaceholderText("Optional .cal file from printcal...")
        cal_btn = QPushButton("Browse...")
        cal_btn.clicked.connect(self._browse_cal)
        cal_row = QHBoxLayout()
        cal_row.addWidget(self.cal_edit, 1)
        cal_row.addWidget(cal_btn)
        opts_layout.addRow("Calibration (-K):", cal_row)

        layout.addWidget(opts_group)

        # --- Run ---
        run_layout = QHBoxLayout()
        self.run_btn = QPushButton("Generate Chart (.ti2 + TIFF)")
        self.run_btn.setStyleSheet("QPushButton { padding: 8px 16px; font-weight: bold; }")
        self.run_btn.clicked.connect(self._run)
        run_layout.addStretch()
        run_layout.addWidget(self.run_btn)
        layout.addLayout(run_layout)

        # --- Log ---
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(200)
        self.log.setStyleSheet("QTextEdit { font-family: 'Consolas', 'Courier New', monospace; font-size: 9pt; }")
        layout.addWidget(self.log)

        layout.addStretch()

    def _on_page_changed(self, index):
        self.custom_size_edit.setVisible(index == self.page_combo.count() - 1)

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Working Directory")
        if d:
            self.work_dir_edit.setText(d)

    def _browse_cal(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Select Calibration File", "",
            "CAL Files (*.cal);;All Files (*)")
        if f:
            self.cal_edit.setText(f)

    def set_context(self, work_dir, basename):
        """Set working dir and basename from previous step."""
        if work_dir:
            self.work_dir_edit.setText(work_dir)
        if basename:
            self.basename_edit.setText(basename)

    def get_working_dir(self):
        return self.work_dir_edit.text()

    def get_basename(self):
        return self.basename_edit.text()

    def _get_instrument_code(self):
        text = self.instrument_combo.currentText()
        return text.split(' - ')[0].strip()

    def _get_page_size(self):
        page_names = ['A4', 'A4R', 'A3', 'A2', 'Letter', 'LetterR', 'Legal', '11x17']
        idx = self.page_combo.currentIndex()
        if idx < len(page_names):
            return page_names[idx]
        return self.custom_size_edit.text()

    def _build_args(self):
        args = ['-v']

        args.extend(['-i', self._get_instrument_code()])
        args.extend(['-p', self._get_page_size()])

        if self.double_density_check.isChecked():
            args.append('-h')

        fmt_idx = self.format_combo.currentIndex()
        if fmt_idx == 0:
            args.extend(['-t', str(self.dpi_spin.value())])
        elif fmt_idx == 1:
            args.extend(['-T', str(self.dpi_spin.value())])
        elif fmt_idx == 3:
            args.append('-e')

        if self.margin_spin.value() != 6.0:
            args.extend(['-m', str(self.margin_spin.value())])

        if self.scale_spin.value() != 1.0:
            args.extend(['-a', str(self.scale_spin.value())])

        if self.no_randomize_check.isChecked():
            args.append('-r')

        if self.cal_edit.text():
            args.extend(['-K', self.cal_edit.text()])

        args.append(self.basename_edit.text())
        return args

    def _run(self):
        work_dir = self.get_working_dir()
        if not work_dir:
            QMessageBox.warning(self, "Error", "Please select a working directory.")
            return

        ti1 = Path(work_dir) / f"{self.get_basename()}.ti1"
        if not ti1.exists():
            QMessageBox.warning(self, "Error",
                f"Input file not found: {ti1}\nRun targen first.")
            return

        self.log.clear()
        self.run_btn.setEnabled(False)
        self.log.append(f"Running: printtarg {' '.join(self._build_args())}\n")
        self.process.start('printtarg', self._build_args(), work_dir)

    def _on_output(self, text):
        self.log.append(text)

    def _on_finished(self, exit_code, status):
        self.run_btn.setEnabled(True)
        if exit_code == 0:
            self.log.append(f"\n--- Completed successfully ---")
            work_dir = Path(self.get_working_dir())
            for ext in ['.ti2', '.tif', '.ps', '.eps']:
                f = work_dir / f"{self.get_basename()}{ext}"
                if f.exists():
                    self.log.append(f"Output: {f}")
        else:
            self.log.append(f"\n--- Failed (exit code {exit_code}) ---")
