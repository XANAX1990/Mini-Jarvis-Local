from pathlib import Path

import pytest

from jarvis import autostart


def test_shortcut_runs_venv_pythonw_listen(tmp_path):
    spec = autostart.shortcut_spec(tmp_path)
    assert Path(spec["target"]) == tmp_path / ".venv" / "Scripts" / "pythonw.exe"
    assert spec["args"] == "-m jarvis listen"
    assert spec["workdir"] == str(tmp_path)


def test_shortcut_lives_in_startup_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert autostart.shortcut_path().parent.name == "Startup"
    assert autostart.shortcut_path().name == "Jarvis.lnk"


def test_install_without_venv_is_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="pythonw.exe"):
        autostart.install(tmp_path)


def test_remove_and_is_installed(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert not autostart.is_installed()
    assert autostart.remove() is False
    lnk = autostart.shortcut_path()
    lnk.parent.mkdir(parents=True)
    lnk.write_bytes(b"x")
    assert autostart.is_installed()
    assert autostart.remove() is True
    assert not autostart.is_installed()
