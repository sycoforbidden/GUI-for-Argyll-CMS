"""
Targen panel - Generate profiling test target values (.ti1).
Focused on CMYK with ColorMunki Photo.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QLineEdit,
    QPushButton, QTextEdit, QFileDialog, QLabel, QMessageBox
)
from PySide6.QtCore import Qt
from pathlib import Path
from process_runner import ArgyllProcess


class TargenPanel(QWidget):
    """Configuration panel for targen - test target generation."""

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

        # --- Output file ---
        file_group = QGroupBox("Output")
        file_layout = QFormLayout(file_group)
        self.work_dir_edit = QLineEdit()
        self.work_dir_edit.setPlaceholderText("Working directory...")
        dir_btn = QPushButton("Browse...")
        dir_btn.clicked.connect(self._browse_dir)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.work_dir_edit, 1)
        dir_row.addWidget(dir_btn)
        file_layout.addRow("Working Dir:", dir_row)

        self.basename_edit = QLineEdit("profile")
        self.basename_edit.setPlaceholderText("Base filename (no extension)")
        file_layout.addRow("Base Name:", self.basename_edit)
        layout.addWidget(file_group)

        # --- Patch Configuration ---
        patch_group = QGroupBox("Patch Configuration")
        patch_layout = QFormLayout(patch_group)

        # ADD THIS: Color Space selector
        self.color_space_combo = QComboBox()
        self.color_space_combo.addItems(["CMYK", "RGB"])
        self.color_space_combo.currentTextChanged.connect(self._on_color_space_changed)
        patch_layout.addRow("Color Space:", self.color_space_combo)

        self.total_patches_spin = QSpinBox()
        self.total_patches_spin.setRange(50, 10000)
        self.total_patches_spin.setValue(836)
        self.total_patches_spin.setToolTip("Total number of patches including all types")
        patch_layout.addRow("Total Patches (-f):", self.total_patches_spin)

        self.white_patches_spin = QSpinBox()
        self.white_patches_spin.setRange(0, 50)
        self.white_patches_spin.setValue(4)
        patch_layout.addRow("White Patches (-e):", self.white_patches_spin)

        self.single_steps_spin = QSpinBox()
        self.single_steps_spin.setRange(0, 100)
        self.single_steps_spin.setValue(0)
        self.single_steps_spin.setToolTip("Per-colorant wedge steps")
        patch_layout.addRow("Single Channel Steps (-s):", self.single_steps_spin)

        self.gray_steps_spin = QSpinBox()
        self.gray_steps_spin.setRange(0, 100)
        self.gray_steps_spin.setValue(0)
        self.gray_steps_spin.setToolTip("Gray axis CMY steps")
        patch_layout.addRow("Gray Axis Steps (-g):", self.gray_steps_spin)

        layout.addWidget(patch_group)

        # --- Ink Limit ---
        ink_group = QGroupBox("Ink Limit")
        ink_layout = QFormLayout(ink_group)

        self.ink_limit_spin = QDoubleSpinBox()
        self.ink_limit_spin.setRange(0, 400)
        self.ink_limit_spin.setValue(300)
        self.ink_limit_spin.setSuffix(" %")
        self.ink_limit_spin.setToolTip("Total ink limit (TAC). 0 = none")
        ink_layout.addRow("Total Ink Limit (-l):", self.ink_limit_spin)

        layout.addWidget(ink_group)

        # --- Algorithm ---
        algo_group = QGroupBox("Distribution Algorithm")
        algo_layout = QFormLayout(algo_group)

        self.algo_combo = QComboBox()
        self.algo_combo.addItems([
            "OFPS - Optimised Farthest Point (default)",
            "Incremental Far Point (-t)",
            "Device Random (-r)",
            "Perceptual Random (-R)",
            "Device Quasi-Random (-q)",
            "Perceptual Quasi-Random (-Q)",
            "Device BCC Grid (-i)",
            "Perceptual BCC Grid (-I)",
        ])
        algo_layout.addRow("Algorithm:", self.algo_combo)

        self.good_check = QCheckBox("Good quality (slower) (-G)")
        algo_layout.addRow(self.good_check)

        layout.addWidget(algo_group)

        # --- Pre-conditioning Profile ---
        profile_group = QGroupBox("Pre-conditioning (Optional)")
        profile_layout = QFormLayout(profile_group)

        self.precond_edit = QLineEdit()
        self.precond_edit.setPlaceholderText("Optional ICC/MPP profile for better distribution...")
        precond_btn = QPushButton("Browse...")
        precond_btn.clicked.connect(self._browse_precond)
        precond_row = QHBoxLayout()
        precond_row.addWidget(self.precond_edit, 1)
        precond_row.addWidget(precond_btn)
        profile_layout.addRow("Profile (-c):", precond_row)

        self.neutral_emphasis_spin = QDoubleSpinBox()
        self.neutral_emphasis_spin.setRange(0, 1)
        self.neutral_emphasis_spin.setValue(0.50)
        self.neutral_emphasis_spin.setSingleStep(0.1)
        profile_layout.addRow("Neutral Emphasis (-N):", self.neutral_emphasis_spin)

        layout.addWidget(profile_group)

        # --- Run ---
        run_layout = QHBoxLayout()
        self.run_btn = QPushButton("Generate Target (.ti1)")
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

    def _browse_precond(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Select Pre-conditioning Profile", "",
            "ICC/MPP Profiles (*.icc *.icm *.mpp);;All Files (*)")
        if f:
            self.precond_edit.setText(f)

    def get_working_dir(self):
        return self.work_dir_edit.text()

    def get_basename(self):
        return self.basename_edit.text()

    def _build_args(self):
        args = ['-v']

        # Determine device color space flag: -d 2 for RGB, -d 4 for CMYK
        is_rgb = (self.color_space_combo.currentText() == "RGB")
        args.extend(['-d', '2' if is_rgb else '4'])

        args.extend(['-f', str(self.total_patches_spin.value())])
        args.extend(['-e', str(self.white_patches_spin.value())])

        if self.single_steps_spin.value() > 0:
            args.extend(['-s', str(self.single_steps_spin.value())])
        if self.gray_steps_spin.value() > 0:
            args.extend(['-g', str(self.gray_steps_spin.value())])

        # Apply ink limit ONLY if CMYK is selected
        if not is_rgb and self.ink_limit_spin.value() > 0:
            args.extend(['-l', str(self.ink_limit_spin.value())])

        algo_map = {
            0: [],           # default OFPS
            1: ['-t'],
            2: ['-r'],
            3: ['-R'],
            4: ['-q'],
            5: ['-Q'],
            6: ['-i'],
            7: ['-I'],
        }
        args.extend(algo_map.get(self.algo_combo.currentIndex(), []))

        if self.good_check.isChecked():
            args.append('-G')

        if self.precond_edit.text():
            args.extend(['-c', self.precond_edit.text()])

        if self.neutral_emphasis_spin.value() != 0.5:
            args.extend(['-N', str(self.neutral_emphasis_spin.value())])

        args.append(self.basename_edit.text())
        return args

    def _run(self):
        work_dir = self.get_working_dir()
        if not work_dir:
            QMessageBox.warning(self, "Error", "Please select a working directory.")
            return
        if not self.get_basename():
            QMessageBox.warning(self, "Error", "Please enter a base filename.")
            return

        self.log.clear()
        self.run_btn.setEnabled(False)
        self.log.append(f"Running: targen {' '.join(self._build_args())}\n")

        self.process.start('targen', self._build_args(), work_dir)

    def _on_output(self, text):
        self.log.append(text)

    def _on_color_space_changed(self, text):
        """Toggle CMYK-only controls when switching between CMYK and RGB."""
        is_cmyk = (text == "CMYK")
        self.ink_limit_spin.setEnabled(is_cmyk)

    def _on_finished(self, exit_code, status):
        self.run_btn.setEnabled(True)
        if exit_code == 0:
            self.log.append(f"\n--- Completed successfully ---")
            ti1 = Path(self.get_working_dir()) / f"{self.get_basename()}.ti1"
            if ti1.exists():
                self.log.append(f"Output: {ti1}")
        else:
            self.log.append(f"\n--- Failed (exit code {exit_code}) ---")
