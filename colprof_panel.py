"""
Colprof panel - Create ICC profile from .ti3 measurement data.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QComboBox, QCheckBox, QLineEdit,
    QPushButton, QTextEdit, QFileDialog, QLabel, QMessageBox, QSpinBox
)
from PySide6.QtCore import Qt
from pathlib import Path
from process_runner import ArgyllProcess


class ColprofPanel(QWidget):
    """Configuration panel for colprof - ICC profile creation."""

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
        layout.addWidget(file_group)

        # --- Profile Type ---
        type_group = QGroupBox("Profile Type")
        type_layout = QFormLayout(type_group)

        self.quality_combo = QComboBox()
        self.quality_combo.addItems([
            "Low (-ql)",
            "Medium (-qm) (default)",
            "High (-qh)",
            "Ultra (-qu)",
        ])
        self.quality_combo.setCurrentIndex(1)
        type_layout.addRow("Quality (-q):", self.quality_combo)

        self.algorithm_combo = QComboBox()
        self.algorithm_combo.addItems([
            "Default (auto)",
            "XYZ cLUT (-ax)",
            "Lab cLUT (-al) (most common for CMYK)",
            "Gamma+Matrix (-ag) (RGB only)",
            "Shaper+Matrix (-as) (RGB only)",
        ])
        self.algorithm_combo.setCurrentIndex(2)  # Lab cLUT for CMYK
        type_layout.addRow("Algorithm (-a):", self.algorithm_combo)

        layout.addWidget(type_group)

        # --- Intents ---
        intent_group = QGroupBox("Rendering Intent Defaults")
        intent_layout = QFormLayout(intent_group)

        self.intent_combo = QComboBox()
        self.intent_combo.addItems([
            "Perceptual (p) (default for CMYK)",
            "Relative Colorimetric (r)",
            "Saturation (s)",
            "Absolute Colorimetric (a)",
        ])
        intent_layout.addRow("Default Intent:", self.intent_combo)

        layout.addWidget(intent_group)

        # --- Ink Limit ---
        ink_group = QGroupBox("Ink Limit")
        ink_layout = QFormLayout(ink_group)

        self.ink_limit_spin = QSpinBox()
        self.ink_limit_spin.setRange(0, 400)
        self.ink_limit_spin.setValue(0)
        self.ink_limit_spin.setSuffix(" %")
        self.ink_limit_spin.setToolTip("Override total ink limit. 0 = use value from .ti3")
        ink_layout.addRow("Total Ink Limit (-l):", self.ink_limit_spin)

        layout.addWidget(ink_group)

        # --- Description ---
        desc_group = QGroupBox("Profile Description")
        desc_layout = QFormLayout(desc_group)

        self.manufacturer_edit = QLineEdit()
        desc_layout.addRow("Manufacturer (-A):", self.manufacturer_edit)

        self.model_edit = QLineEdit()
        desc_layout.addRow("Model (-M):", self.model_edit)

        self.description_edit = QLineEdit()
        desc_layout.addRow("Description (-D):", self.description_edit)

        self.copyright_edit = QLineEdit()
        desc_layout.addRow("Copyright (-C):", self.copyright_edit)

        layout.addWidget(desc_group)

        # --- Advanced ---
        adv_group = QGroupBox("Advanced")
        adv_layout = QFormLayout(adv_group)

        self.bpo_check = QCheckBox("Black Point Compensation (-b)")
        adv_layout.addRow(self.bpo_check)

        self.extra_args_edit = QLineEdit()
        self.extra_args_edit.setPlaceholderText("Additional command-line arguments...")
        adv_layout.addRow("Extra Args:", self.extra_args_edit)

        layout.addWidget(adv_group)

        # --- Run ---
        run_layout = QHBoxLayout()
        self.run_btn = QPushButton("Create ICC Profile (.icc)")
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

    def set_context(self, work_dir, basename):
        if work_dir:
            self.work_dir_edit.setText(work_dir)
        if basename:
            self.basename_edit.setText(basename)

    def _build_args(self):
        args = ['-v']

        quality_flags = ['l', 'm', 'h', 'u']
        args.extend(['-q', quality_flags[self.quality_combo.currentIndex()]])

        algo_map = {
            0: [],
            1: ['-a', 'x'],
            2: ['-a', 'l'],
            3: ['-a', 'g'],
            4: ['-a', 's'],
        }
        args.extend(algo_map.get(self.algorithm_combo.currentIndex(), []))

        if self.ink_limit_spin.value() > 0:
            args.extend(['-l', str(self.ink_limit_spin.value())])

        if self.bpo_check.isChecked():
            args.append('-b')

        if self.manufacturer_edit.text():
            args.extend(['-A', self.manufacturer_edit.text()])
        if self.model_edit.text():
            args.extend(['-M', self.model_edit.text()])
        if self.description_edit.text():
            args.extend(['-D', self.description_edit.text()])
        if self.copyright_edit.text():
            args.extend(['-C', self.copyright_edit.text()])

        # Extra args
        if self.extra_args_edit.text():
            args.extend(self.extra_args_edit.text().split())

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
        self.log.append(f"Running: colprof {' '.join(self._build_args())}\n")
        self.process.start('colprof', self._build_args(), work_dir)

    def _on_output(self, text):
        self.log.append(text)

    def _on_finished(self, exit_code, status):
        self.run_btn.setEnabled(True)
        if exit_code == 0:
            self.log.append(f"\n--- Completed successfully ---")
            icc = Path(self.work_dir_edit.text()) / f"{self.basename_edit.text()}.icc"
            if icc.exists():
                self.log.append(f"Output: {icc}")
        else:
            self.log.append(f"\n--- Failed (exit code {exit_code}) ---")
