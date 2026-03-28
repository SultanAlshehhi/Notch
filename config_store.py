"""Runtime path helpers for Notch."""

from __future__ import annotations

import os
import sys
from pathlib import Path


APP_ID = "ae.socia.Notch"
APP_DIRNAME = "notch"
DEFAULT_MODEL_NAME = "vosk-model-small-en-us-0.15"


def _xdg_dir(env_name: str, fallback_suffix: str) -> Path:
    value = os.getenv(env_name)
    if value:
        return Path(value).expanduser()
    return Path.home() / fallback_suffix


def data_dir() -> Path:
    return _xdg_dir("XDG_DATA_HOME", ".local/share") / APP_DIRNAME


def model_dir() -> Path:
    return data_dir() / "model"


def resolve_model_path() -> str:
    explicit = os.getenv("NOTCH_MODEL_PATH")
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser())

    here = Path(__file__).resolve().parent
    candidates.append(here / "model")

    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "model")

    candidates.append(Path.cwd() / "model")
    candidates.append(model_dir())
    candidates.append(model_dir() / DEFAULT_MODEL_NAME)

    seen = set()
    deduped = []
    for candidate in candidates:
        text = str(candidate)
        if text in seen:
            continue
        seen.add(text)
        deduped.append(candidate)

    for candidate in deduped:
        if candidate.is_dir():
            return str(candidate)

    return str(deduped[0]) if deduped else "model"
