"""Run Notch locally. From repo root or from windows/:  python windows/run.py"""

import os
import subprocess
import sys

def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(repo_root)
    sys.path.insert(0, repo_root)

    # Ensure dependencies
    try:
        import PyQt5
        import sounddevice
    except ImportError:
        print("Installing dependencies (first run)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("Done. Starting Notch...")

    import main as notch_main
    notch_main.main()

if __name__ == "__main__":
    main()
