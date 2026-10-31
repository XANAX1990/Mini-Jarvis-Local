import hashlib
from pathlib import Path

import pytest

from jarvis import __main__ as app
from jarvis.programs import Migration

ROOT = Path(__file__).resolve().parent.parent
OWNERS_FILES = [ROOT / "presets.json", ROOT / "programs.json", ROOT / "settings.json"]


def _fingerprint():
    return {f.name: (hashlib.sha256(f.read_bytes()).hexdigest() if f.exists() else None) for f in OWNERS_FILES}


@pytest.fixture(scope="session", autouse=True)
def the_tests_never_change_the_owners_files():
    """Guard: the real presets.json / programs.json / settings.json are the owner's. Once a test run
    migrated them by accident (main() ran the migration on the real files), so this fails the run if any
    of them changed while the tests ran."""
    before = _fingerprint()
    yield
    assert _fingerprint() == before, "a test changed presets.json, programs.json or settings.json in the project folder"


class NoStore:
    programs = {}

    def load(self):
        return self.programs


@pytest.fixture(autouse=True)
def quiet_main(monkeypatch):
    """`app.main` never touches the real presets.json / programs.json: nothing is created, copied or moved.

    Every test gets this; a test that wants other behaviour patches the same names itself."""
    monkeypatch.setattr(app, "ensure_presets_file", lambda: False)
    monkeypatch.setattr(app, "ensure_programs_file", lambda: False)
    monkeypatch.setattr(app, "migrate_legacy_steps", lambda *a, **k: Migration())
    monkeypatch.setattr(app, "ProgramStore", NoStore)
    monkeypatch.setattr(app, "load_presets", lambda *a, **k: {"game": {"phrases": ["เปิดโหมดเกม"]}})
    return app
