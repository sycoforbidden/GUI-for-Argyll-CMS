"""
Printcal panel - Create printer linearization calibration (.cal) from .ti3.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QDoubleSpinBox, QComboBox, QCheckBox, QLineEdit,
    QPushButton, QTextEdit, QFileDialog, QLabel, QMessageBox, QSpinBox
)
from PySide6.QtCore import Qt
from pathlib import Path
from process_runner import ArgyllProcess


class PrintcalPanel(QWidget):
    """Configuration panel for printcal - linearization calibration."""

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

        # --- Files ---
        file_group = QGroupBox("Input / Output")
        file_layout = QFormLayout(file_group)

        self.work_dir_edit = QLineEdit()
        dir_btn = QPushButton("Browse...")
        dir_btn.clicked.connect(self._browse_dir)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.work_dir_edit, 1)
        dir_row.addWidget(dir_btn)
        file_layout.addRow("Working Dir:", dir_row)

        self.basename_edit = QLineEdit("profile")
        file_layout.addRow("Base Name:", self.basename_edit)

        self.prevcal_edit = QLineEdit()
        self.prevcal_edit.setPlaceholderText("Previous .cal (for recal/verify only)...")
        prevcal_btn = QPushButton("Browse...")
        prevcal_btn.clicked.connect(self._browse_prevcal)
        prevcal_row = QHBoxLayout()
        prevcal_row.addWidget(self.prevcal_edit, 1)
        prevcal_row.addWidget(prevcal_btn)
        file_layout.addRow("Previous Cal:", prevcal_row)

        layout.addWidget(file_group)

        # --- Mode ---
        mode_group = QGroupBox("Calibration Mode")
        mode_layout = QFormLayout(mode_group)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "Initial calibration (-i)",
            "Re-calibrate (-r)",
            "Verify (-e)",
            "Imitation target (-I)",
        ])
        mode_layout.addRow("Mode:", self.mode_combo)
        layout.addWidget(mode_group)

        # --- Options ---
        opts_group = QGroupBox("Options")
        opts_layout = QFormLayout(opts_group)

        self.smoothing_spin = QDoubleSpinBox()
        self.smoothing_spin.setRange(0.1, 5.0)
        self.smoothing_spin.setValue(1.0)
        self.smoothing_spin.setSingleStep(0.1)
        opts_layout.addRow("Smoothing (-s):", self.smoothing_spin)

        self.resolution_spin = QSpinBox()
        self.resolution_spin.setRange(16, 4096)
        self.resolution_spin.setValue(256)
        opts_layout.addRow("Curve Resolution (-z):", self.resolution_spin)

        self.plot_check = QCheckBox("Plot graphs (-p)")
        opts_layout.addRow(self.plot_check)

        layout.addWidget(opts_group)

        # --- Description ---
        desc_group = QGroupBox("Description (Optional)")
        desc_layout = QFormLayout(desc_group)

        self.manufacturer_edit = QLineEdit()
        desc_layout.addRow("Manufacturer (-A):", self.manufacturer_edit)

        self.model_edit = QLineEdit()
        desc_layout.addRow("Model (-M):", self.model_edit)

        self.description_edit = QLineEdit()
        desc_layout.addRow("Description (-D):", self.description_edit)

        layout.addWidget(desc_group)

        # --- Run ---
        run_layout = QHBoxLayout()
        self.run_btn = QPushButton("Create Calibration (.cal)")
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

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Working Directory")
        if d:
            self.work_dir_edit.setText(d)

    def _browse_prevcal(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Select Previous Calibration", "",
            "CAL Files (*.cal);;All Files (*)")
        if f:
            self.prevcal_edit.setText(f)

    def set_context(self, work_dir, basename):
        if work_dir:
            self.work_dir_edit.setText(work_dir)
        if basename:
            self.basename_edit.setText(basename)

    def _build_args(self):
        args = ['-v']

        mode_flags = ['-i', '-r', '-e', '-I']
        args.append(mode_flags[self.mode_combo.currentIndex()])

        if self.smoothing_spin.value() != 1.0:
            args.extend(['-s', str(self.smoothing_spin.value())])

        if self.resolution_spin.value() != 256:
            args.extend(['-z', str(self.resolution_spin.value())])

        if self.plot_check.isChecked():
            args.append('-p')

        if self.manufacturer_edit.text():
            args.extend(['-A', self.manufacturer_edit.text()])
        if self.model_edit.text():
            args.extend(['-M', self.model_edit.text()])
        if self.description_edit.text():
            args.extend(['-D', self.description_edit.text()])

        # Previous cal file (for recal/verify modes)
        mode_idx = self.mode_combo.currentIndex()
        if mode_idx in (1, 2) and self.prevcal_edit.text():
            args.append(self.prevcal_edit.text())

        args.append(self.basename_edit.text())
        return args

    def _run(self):
        work_dir = self.work_dir_edit.text()
        if not work_dir:
            QMessageBox.warning(self, "Error", "Please select a working directory.")
            return

        ti3 = Path(work_dir) / f"{self.basename_edit.text()}.ti3"
        if not ti3.exists():
            QMessageBox.warning(self, "Error",
                f"Input file not found: {ti3}\nRun chartread first.")
            return

        self.log.clear()
        self.run_btn.setEnabled(False)
        self.log.append(f"Running: printcal {' '.join(self._build_args())}\n")
        self.process.start('printcal', self._build_args(), work_dir)

    def _on_output(self, text):
        self.log.append(text)

    def _on_finished(self, exit_code, status):
        self.run_btn.setEnabled(True)
        if exit_code == 0:
            self.log.append(f"\n--- Completed successfully ---")
            cal = Path(self.work_dir_edit.text()) / f"{self.basename_edit.text()}.cal"
            if cal.exists():
                self.log.append(f"Output: {cal}")
        else:
            self.log.append(f"\n--- Failed (exit code {exit_code}) ---")
