"""
audio_worker.py — Microphone audio worker running on a QThread.

Reads raw PCM from the microphone via sounddevice and emits volume levels
for voice-activity-driven scrolling. Optionally uses offline speech
recognition for word alignment; volume detection always works independently.
"""

import json
import os
import queue
import sys
import traceback
from typing import Optional

import numpy as np
import sounddevice as sd

from PyQt5.QtCore import QThread, pyqtSignal


class AudioWorker(QThread):
    """Continuously streams microphone audio and emits volume levels."""

    # ── Signals ──────────────────────────────────────────────────────
    volume_level_signal = pyqtSignal(float)  # RMS volume 0.0 – 1.0
    speaking_signal     = pyqtSignal(bool)   # True = speaking, False = silent
    speech_text_signal  = pyqtSignal(str, bool)  # text, is_final
    error_signal        = pyqtSignal(str)    # fatal errors
    status_signal       = pyqtSignal(str)    # status messages

    SAMPLE_RATE = 16_000  # 16 kHz mono

    @staticmethod
    def _resolve_vosk_model_dir(model_path: str) -> str:
        """
        Make model loading resilient to common zip-extract layouts.

        Expected structure (directly in model_path):
          model_path\\conf\\...
          model_path\\am\\...

        But the data is sometimes in a subfolder. If we detect that,
        we automatically use the inner folder.
        """
        try:
            if not model_path:
                return model_path
            if not os.path.isdir(model_path):
                return model_path

            # If it already looks like the expected data folder, keep it.
            if os.path.isdir(os.path.join(model_path, "conf")) and os.path.isdir(os.path.join(model_path, "am")):
                return model_path

            # Look one directory down for a folder that looks like a model.
            subdirs = [
                os.path.join(model_path, name)
                for name in os.listdir(model_path)
                if os.path.isdir(os.path.join(model_path, name))
            ]
            for sd_path in subdirs:
                if os.path.isdir(os.path.join(sd_path, "conf")) and os.path.isdir(os.path.join(sd_path, "am")):
                    return sd_path
        except Exception:
            pass
        return model_path

    @staticmethod
    def _log_frozen_error(message: str):
        """
        In the windowed PyInstaller build, stdout isn't visible.
        Write key failures to notch.log in the exe install directory for debugging.
        """
        try:
            if getattr(sys, "frozen", False):
                log_dir = os.path.dirname(sys.executable)
            else:
                log_dir = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
                log_dir = os.path.join(log_dir, "Notch")
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, "notch.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(message.rstrip() + "\n")
        except Exception:
            pass

    def __init__(self, device_index: Optional[int] = None,
                 noise_gate: float = 0.01, input_gain: float = 2.0,
                 model_path: str = "model", parent=None):
        super().__init__(parent)
        self.device_index = device_index
        self.noise_gate = noise_gate
        self.input_gain = max(0.1, min(input_gain, 10.0))
        self.model_path = model_path
        self._running = False
        self._audio_queue: queue.Queue = queue.Queue()

        # Speech state tracking
        self._is_speaking = False
        self._silence_frames = 0
        # How many consecutive silent frames before we declare "not speaking"
        # Each frame is ~250ms, so 3 frames ≈ 750ms of silence to stop
        self._silence_threshold = 3
        # Mute: do not emit speech (overlay toggles); reset recognizer on unmute to clear backlog
        self._muted = False
        self._reset_recognizer_requested = False

    # ── Public helpers ───────────────────────────────────────────────
    def set_muted(self, muted: bool):
        self._muted = bool(muted)
        if not self._muted:
            self._reset_recognizer_requested = True  # clear backlog when unmuting

    def request_reset_recognizer(self):
        """Call when unmuting so recognizer state is cleared and we don't get backlog text."""
        self._reset_recognizer_requested = True

    def set_device(self, index: Optional[int]):
        self.device_index = index

    def set_noise_gate(self, value: float):
        self.noise_gate = max(0.0, min(value, 1.0))

    def set_input_gain(self, value: float):
        self.input_gain = max(0.1, min(value, 10.0))

    def stop(self):
        self._running = False

    # ── sounddevice callback (called from audio thread) ──────────────
    def _audio_callback(self, indata: np.ndarray, frames: int,
                        time_info, status):
        if status:
            pass  # drop-outs are non-fatal
        self._audio_queue.put(bytes(indata))

    # ── Main thread loop ─────────────────────────────────────────────
    def run(self):
        self._running = True
        print("[Notch] Audio worker thread started", flush=True)
        if getattr(sys, "frozen", False):
            self._log_frozen_error("[Notch] Audio worker started")

        # Open microphone stream
        try:
            dev = "default" if self.device_index is None else f"device #{self.device_index}"
            print(f"[Notch] Opening microphone ({dev})...", flush=True)
            stream = sd.RawInputStream(
                samplerate=self.SAMPLE_RATE,
                blocksize=4000,          # ~250 ms chunks
                dtype="int16",
                channels=1,
                device=self.device_index,
                callback=self._audio_callback,
            )
            stream.start()
            print("[Notch] Microphone opened — listening", flush=True)
            self.status_signal.emit("Listening...")
        except Exception as exc:
            print(f"[Notch] Microphone error: {exc}", flush=True)
            self.error_signal.emit(f"Microphone error:\n{exc}")
            return

        # Optional speech recognizer (use instance attrs so we can reset on unmute)
        self._vosk_model = None
        self._recognizer = None
        last_partial = ""
        try:
            from vosk import Model, KaldiRecognizer
            model_dir = self._resolve_vosk_model_dir(self.model_path)
            if os.path.isdir(model_dir):
                self._vosk_model = Model(model_dir)
                self._recognizer = KaldiRecognizer(self._vosk_model, self.SAMPLE_RATE)
                print("[Notch] Speech recognition on", flush=True)
                if getattr(sys, "frozen", False):
                    self._log_frozen_error(f"Speech data loaded from: {model_dir}")
            else:
                print("[Notch] Speech recognition off (data folder not found)", flush=True)
                if getattr(sys, "frozen", False):
                    self._log_frozen_error(f"Speech data NOT found at: {model_dir}")
                self.status_signal.emit("Speech recognition unavailable — voice match off")
                self.error_signal.emit(
                    f"Speech data folder not found at:\n{model_dir}\n\n"
                    "Voice-follow and word highlighting need the data folder. "
                    "If you installed via the installer, reinstall and ensure the full package was used."
                )
        except Exception as e:
            print(f"[Notch] Speech recognition load failed: {e}", flush=True)
            traceback.print_exc()
            try:
                self._log_frozen_error("Speech load failed:\n" + "".join(traceback.format_exc()))
            except Exception:
                pass
            self.error_signal.emit(
                f"Speech recognition failed to load:\n{e}\n\n"
                "Check that the data folder exists next to the app and contains the required files."
            )
            self._recognizer = None

        # Processing loop — volume detection + VAD + optional speech recognition
        try:
            while self._running:
                try:
                    data = self._audio_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                # ── Reset recognizer (e.g. on unmute to clear backlog) ─
                if self._reset_recognizer_requested and self._vosk_model is not None:
                    self._reset_recognizer_requested = False
                    self._recognizer = KaldiRecognizer(self._vosk_model, self.SAMPLE_RATE)
                    last_partial = ""
                    # Drain queued audio from during mute so we don't feed stale audio
                    for _ in range(12):  # ~3 s at 0.25 s per chunk
                        try:
                            self._audio_queue.get_nowait()
                        except queue.Empty:
                            break

                # ── Speech recognition (optional) ───────────────────
                if self._recognizer is not None and not self._muted:
                    try:
                        if self._recognizer.AcceptWaveform(data):
                            result = json.loads(self._recognizer.Result())
                            text = result.get("text", "").strip()
                            if text:
                                print(f"[Notch audio] (final): {text!r}", flush=True)
                                self.speech_text_signal.emit(text, True)
                                last_partial = ""
                        else:
                            partial = json.loads(self._recognizer.PartialResult()).get("partial", "").strip()
                            if partial and partial != last_partial:
                                print(f"[Notch audio] (partial): {partial!r}", flush=True)
                                self.speech_text_signal.emit(partial, False)
                                last_partial = partial
                    except Exception:
                        pass

                # ── Volume metering ──────────────────────────────────
                samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                rms = np.sqrt(np.mean(samples ** 2)) / 32768.0
                rms = min(rms * self.input_gain, 1.0)
                level = min(rms * 5.0, 1.0)  # amplified for UI
                self.volume_level_signal.emit(level)

                # ── Voice Activity Detection ─────────────────────────
                if rms >= self.noise_gate:
                    # Voice detected
                    self._silence_frames = 0
                    if not self._is_speaking:
                        self._is_speaking = True
                        self.speaking_signal.emit(True)
                else:
                    # Silence
                    self._silence_frames += 1
                    if self._is_speaking and self._silence_frames >= self._silence_threshold:
                        self._is_speaking = False
                        self.speaking_signal.emit(False)
        finally:
            stream.stop()
            stream.close()
