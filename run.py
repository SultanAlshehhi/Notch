"""Run Notch locally."""

import importlib.util
import os
import subprocess
import sys


def _has_module(name: str):
    return importlib.util.find_spec(name) is not None


def main():
    repo_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(repo_root)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    required_modules = ["PyQt5", "sounddevice", "numpy", "vosk", "thefuzz"]
    if any(not _has_module(module) for module in required_modules):
        print("Installing dependencies (first run)...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]
        )
        print("Done. Starting Notch...")

    import main as notch_main

    notch_main.main()


if __name__ == "__main__":
    main()
