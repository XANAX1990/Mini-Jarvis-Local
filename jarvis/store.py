"""Saving presets.json: validate first (callers do), write a .tmp file, keep the old file as .bak,
then os.replace. A failed save never leaves a half-written presets.json.
"""
import json
import os
import shutil
from pathlib import Path

from jarvis.presets import PRESETS_PATH


class PresetStore:
    def __init__(self, path=PRESETS_PATH):
        self.path = Path(path)

    def save(self, presets):
        tmp = self.path.with_name(self.path.name + ".tmp")
        bak = self.path.with_name(self.path.name + ".bak")
        try:
            tmp.write_text(json.dumps(presets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
            if self.path.exists():
                shutil.copyfile(self.path, bak)
            os.replace(tmp, self.path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
