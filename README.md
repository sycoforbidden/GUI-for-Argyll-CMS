# ArgyllCMS Profiling GUI

A graphical interface for the ArgyllCMS CMYK printer profiling workflow, built with Python and PySide6.

Wraps 5 ArgyllCMS command-line tools into a step-by-step workflow with the main focus on **chartread** — providing real-time visual feedback of expected vs measured patch colors so you can catch misreadings before they ruin your profile.

## The Problem This Solves

When using ArgyllCMS from the command line, `chartread` gives you no visual feedback. If the instrument catches a neighbouring patch (e.g. reads blue instead of pink), you have no way to see it. You only discover the error later when the resulting ICC profile produces garbage. This GUI shows you every reading as it happens, with Delta E comparison and colour preview, so you can immediately spot and re-read bad strips.

## Requirements

- **Python 3.9+**
- **PySide6** (Qt for Python)
- **ArgyllCMS** binaries (included in the parent `bin/` directory)

## Installation

```bash
cd gui
pip install -r requirements.txt
```

## Running

**Windows:**
```
run_gui.bat
```

**Any platform:**
```bash
cd gui
python main.py
```

The GUI auto-detects the ArgyllCMS `bin/` directory relative to its own location (`../bin/`).

## Workflow

The GUI follows the standard ArgyllCMS printer profiling workflow in 5 tabs:

### Tab 1 — Generate Patches (`targen`)

Generates test target device values (`.ti1` file).

- Set colourspace to CMYK (default)
- Configure total patch count (default 836 for one A3 sheet)
- Set total ink limit (TAC) — typically 280–320% for CMYK
- Choose patch distribution algorithm (OFPS default)
- Optionally provide a pre-conditioning ICC profile for better distribution

### Tab 2 — Layout Chart (`printtarg`)

Creates a printable test chart from the `.ti1` file.

- Instrument pre-set to **ColorMunki** (changeable)
- Choose page size (A4, A3, Letter, etc.)
- Output as TIFF (default, 300 DPI) or PostScript
- Apply calibration curves from a `.cal` file if available
- Produces `.ti2` (layout data) + `.tif` (print file)

**Print the TIFF on your printer with no colour management.**

### Tab 3 — Read Chart (`chartread`) ⭐ Main Feature

Read the printed chart with your ColorMunki Photo instrument.

**Visual features:**
- **Patch grid** — every patch displayed in a strip-by-strip grid, coloured with its expected CMYK value
- **Split-view swatches** — once measured, each patch shows expected (left) vs measured (right) colour
- **Delta E borders** — patches are outlined by measurement quality:
  - Green border = good (dE94 < 5)
  - Orange border = warning (dE94 5–10)
  - Red border = likely misread (dE94 > 10)
- **Strip progress** — strips highlighted blue (currently reading) or green (completed)
- **Misread table** — all patches with dE94 > 5 are automatically collected in a warning table
- **Patch detail panel** — click any patch to see side-by-side expected/measured swatches with full Lab values and Delta E

**Interactive controls:**
- Enter, Space, d (done), q (quit) buttons for common chartread prompts
- Custom input line for any other commands
- Full console output visible in dark terminal-style panel

**Post-read analysis:**
- After chartread finishes, the `.ti3` file is parsed and all patches are re-evaluated
- Final misread summary with patch locations, CMYK values, expected vs measured Lab, and Delta E

### Tab 4 — Calibration (`printcal`)

Creates linearisation calibration curves (`.cal` file) from measurement data.

- Initial calibration, re-calibration, or verify modes
- Adjustable smoothing and curve resolution
- The resulting `.cal` can be fed back into Tab 2 for calibrated profiling charts

### Tab 5 — Create Profile (`colprof`)

Generates an ICC profile from the `.ti3` measurement data.

- Quality levels: low / medium / high / ultra
- Algorithm selection (Lab cLUT default for CMYK)
- Ink limit override
- Profile description fields (manufacturer, model, copyright)

## File Flow

```
targen ──> .ti1 ──> printtarg ──> .ti2 + .tif
                                     │
                              (print & measure)
                                     │
                    chartread ──> .ti3 ──┬──> printcal ──> .cal
                                        │
                                        └──> colprof  ──> .icc
```

## Project Structure

```
gui/
├── main.py              # Entry point
├── main_window.py       # Main window with workflow tabs
├── cgats.py             # CGATS file parser (.ti1, .ti2, .ti3, .cal)
├── color_utils.py       # Colour conversions (CMYK/Lab/XYZ → RGB, Delta E)
├── process_runner.py    # QProcess wrapper for ArgyllCMS executables
├── targen_panel.py      # Step 1: patch generation
├── printtarg_panel.py   # Step 2: chart layout
├── chartread_panel.py   # Step 3: chart reading with visual feedback
├── printcal_panel.py    # Step 4: linearisation calibration
├── colprof_panel.py     # Step 5: ICC profile creation
├── requirements.txt     # Python dependencies
├── run_gui.bat          # Windows launcher
└── README.md            # This file
```

## Tips

- **Working directory**: set it once in Tab 1 and click "Sync Dir/Name to All Steps" in the toolbar — it propagates to all tabs automatically.
- **Patch count**: for ColorMunki on A4, ~90 patches per sheet (or ~210 with `-h` double density). Use the targen reference table in the ArgyllCMS docs to pick good counts.
- **Ink limit**: start with 300% for a standard CMYK inkjet. Reduce if you see pooling or bleeding.
- **Misreads**: if chartread shows red-bordered patches, re-read that strip. A single misread patch in a critical area (neutrals, skin tones) can ruin the whole profile.
- **Calibration first**: for best results, run the workflow twice — first with `targen -s 33` (single-channel wedges only) to create a `.cal` with printcal, then again with full patches and the `.cal` applied via `printtarg -K`.

## Licence

This GUI wrapper is provided as-is. ArgyllCMS itself is copyright Graeme Gill — see the ArgyllCMS `License.txt` for details.
