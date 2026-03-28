<div align="center">

  <img src="/assets/Notch_Clear_1.png" alt="Notch Logo" width="120" />

  # Notch
  **Local Offline Teleprompter**

  [![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
  [![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](https://github.com/SultanAlshehhi/Notch)
  [![Python](https://img.shields.io/badge/python-3.8+-yellow.svg)](https://www.python.org/downloads/)

  <p>
    <b>A privacy-first teleprompter that listens to your voice.</b><br>
    Pins to the top of your screen. Scrolls when you speak. Pauses when you stop.<br>
    <i>No Cloud. No API Keys. 100% Offline.</i>
  </p>

   <!-- Auto-playing demo GIF -->
![Notch Demo](assets/NotchDemo.gif)

</div>




---

## ⚡ Features

| Feature | Description |
| :--- | :--- |
| 🎙️ **Voice Activation** | The script scrolls automatically as you speak and pauses when you stop. |
| 🔒 **Privacy First** | All audio processing is local. Your voice data never leaves your machine. |
| 📌 **Always on Top** | Designed as a slim overlay to sit near your webcam. |
| 🎚️ **Manual Control** | Toggle scrolling with **Space** or adjust speed manually. |
| 🎨 **Smart Highlighting** | Spoken words light up; future text remains dimmed for focus. |
| ⚙️ **Audio Tuning** | Built-in Noise Gate, Input Gain, and VU Meter for any environment. |

---

## 🚀 Installation

### Windows / macOS / Linux
```bash
python run.py
```

*On the first run, Notch will automatically install required dependencies.*

Optional on Linux with Nix:

```bash
nix run .#notch
```

*The Nix package includes the local speech model and supports x86_64 + aarch64 Linux.*

---

## 🎮 Usage Guide

**1. Load a Script**
Drag and drop any `.txt` file directly onto the Notch window.

**2. Select Mode**
Right-click the window to access the menu:
*   **Notch Mode (Auto):** The microphone drives the scroll speed.
*   **Manual Mode:** Scroll runs on a timer. Press **Space** to start/stop.

**3. Adjust Settings**
If the scrolling is too sensitive or not sensitive enough:
1.  Open **Settings**.
2.  Adjust the **Noise Gate**.
    *   *High Gate:* Filters out background noise (requires louder speech).
    *   *Low Gate:* Detects whispers (more sensitive).

### Keyboard Shortcuts

| Key | Action |
| :--- | :--- |
| <kbd>Space</kbd> | Toggle scrolling (Manual Mode) |
| <kbd>Esc</kbd> | Close Application |

---

<details>
<summary>📂 <b>Developer: Directory Structure</b> (Click to expand)</summary>

```text
Notch/
├── run.py               # Run Notch (installs deps on first run)
├── main.py              # Application Entry Point
├── ui_overlay.py        # GUI & Overlay Logic
├── audio_worker.py      # Audio Processing & VAD
├── matching_engine.py   # Text Alignment Algorithms
├── settings_dialog.py   # Configuration UI
├── requirements.txt     # Dependencies
└── assets/              # Images for README only
```
</details>

---

## 📄 License

Distributed under the MIT License. See [LICENSE](LICENSE) for more information.
