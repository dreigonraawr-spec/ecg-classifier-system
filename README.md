# CardiBeat v2.0 — ECG Intelligent Monitoring System

> Biomedical Electronics Final Project · Group 1 · 2026

CardiBeat is a standalone desktop application for electrocardiogram signal processing and cardiac health analysis. It accepts either a synthetic ECG signal from the built-in simulator or real data from a CSV file, runs a full clinical-grade processing pipeline, and presents the results across an interactive multi-tab interface.
---
## Features

### Signal Input
- **ECG Simulator** — Gaussian PQRST waveform synthesis with configurable heart rate, duration, and arrhythmia mode (Normal · AFib · PVC · Missed Beat)
- **CSV File Loader** — automatic column detection via pandas; compatible with standard ECG hardware exports and public datasets

### Signal Processing Pipeline
| Stage | Method |
|---|---|
| Bandpass Filter | 4th-order Butterworth, 0.5–40 Hz, zero-phase (`sosfiltfilt`) |
| R-Peak Detection | Adaptive threshold + refractory period (`scipy.signal.find_peaks`) |
| Heart Rate | Mean RR interval → BPM; classified as bradycardia / normal / tachycardia |
| Arrhythmia Detection | RR variability + morphology rules (AFib · PVC · Missed Beat) |
| ST Segment Analysis | Isoelectric baseline subtraction; elevation and depression in mV |
| QRS Duration | S-wave to J-point width measurement |
| PR Interval | P-wave onset to QRS onset conduction time |
| Time-Domain HRV | SDNN · RMSSD · pNN50 |
| Frequency-Domain HRV | Welch PSD → LF · HF · LF/HF ratio |
| Poincaré Metrics | SD1 · SD2 from successive-difference scatter |
| Lead Derivation | Einthoven triangle → Lead I · II · III · aVR · aVF |
| Signal Quality Index | Noise floor estimation from filtered residual |
| Cardiac Health Score | Composite 0–100 score (HR 30 pts · HRV 25 pts · Arrhythmia 25 pts · ST 20 pts) |

### Visualization
- **Monitor Tab** — raw vs. filtered ECG overlay, HR tachogram
- **Live ECG Tab** — real-time scrolling waveform at 20 fps using matplotlib blitting
- **Multi-Lead Tab** — simultaneous display of 5 derived leads
- **Clinical Analysis Tab** — full metrics report + Poincaré scatter plot
- **History Tab** — session log (sortable `ttk.Treeview`)
- **Validation Tab** — 6 automated self-tests with PASS/FAIL output

### Export
- **PDF Clinical Report** — 2-page A4 via `matplotlib.backends.backend_pdf.PdfPages`
- **CSV History Export** — all session records via `pandas.DataFrame.to_csv`

---

## Screenshots

> *(Monitor Tab · Clinical Analysis Tab · Live ECG Tab · Multi-Lead Tab)*

---

## Requirements

```
Python >= 3.10
numpy
scipy
matplotlib
pandas
```

Install dependencies:

```bash
pip install numpy scipy matplotlib pandas
```

---

## Running the Application

```bash
python ecg_monitor.py
```

Or run the prebuilt executable (Windows):

```
dist/CardiBeat.exe
```

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+G` | Generate ECG signal |
| `Ctrl+R` | Run full analysis |
| `Ctrl+E` | Export PDF report |
| `Space` | Toggle Live ECG playback |

---

## Building the Executable

Requires PyInstaller:

```bash
pip install pyinstaller
pyinstaller CardiBeat.spec
```

Output: `dist/CardiBeat.exe`

---

## Project Structure

```
CardiBeat/
├── ecg_monitor.py            # Main application
├── CardiBeat.spec            # PyInstaller build spec
├── dist/
│   └── CardiBeat.exe         # Prebuilt Windows executable
├── data/
│   └── image.png             # Application icon / asset
├── CardiBeat_Documentation.html   # Full technical documentation
├── CardiBeat_BlockDiagram.html    # UML software block diagram
├── CardiBeat_BlockDiagram.png     # Block diagram (PNG, 150 DPI)
└── generate_diagram.py            # Diagram generation script
```

---

## Technical Notes

**Startup performance** — Heavy scientific libraries are imported on a background thread while the splash screen renders, keeping the UI responsive from launch.

**Zero-phase filtering** — `sosfiltfilt` applies the Butterworth filter forward and backward, cancelling group delay and preserving the exact timing of all waveform features — critical for accurate PR interval and QRS duration measurements.

**Live ECG rendering** — Matplotlib blitting (`copy_from_bbox` / `restore_region`) separates the static axes background from the dynamic ECG line, reducing per-frame render cost by ~85% and enabling stable 20 fps animation.

**Health Score weighting** — Weights are derived from the relative clinical severity of each domain: ST deviation and arrhythmia carry higher penalty per unit deviation than mild HRV reduction, consistent with acute vs. chronic risk stratification.

---

## Authors

** Christian Andrei T. Generoso
** BS Biomedical Engineering | Batangas State University - The National Engineering University

---

## License

## License

This project is licensed under the **GNU General Public License v3.0**.  
See the [LICENSE](LICENSE) file for details.

> This software is for academic and educational use only. It is not a certified
> medical device and must not be used for clinical diagnosis or medical
> decision-making.
