import pytest

from jarvis import __main__ as app
from jarvis import privileges


def test_is_admin_answers_with_a_bool_and_does_not_raise():
    assert isinstance(privileges.is_admin(), bool)


def test_is_admin_is_false_when_windows_cannot_say(monkeypatch):
    class Broken:
        def IsUserAnAdmin(self):
            raise OSError("no")

    monkeypatch.setattr(privileges.ctypes, "windll", type("W", (), {"shell32": Broken()})(), raising=False)
    assert privileges.is_admin() is False


@pytest.mark.parametrize("argv", [["list"], ["listen"], ["run", "game"], ["say", "hi"], ["autostart", "status"]])
def test_every_command_refuses_to_run_as_administrator(argv, quiet_main, monkeypatch, capsys):
    monkeypatch.setattr(privileges, "is_admin", lambda: True)
    touched = []
    monkeypatch.setattr(app, "ensure_presets_file", lambda: touched.append("created presets.json"))
    monkeypatch.setattr(app, "ensure_programs_file", lambda: touched.append("created programs.json"))
    monkeypatch.setattr(app, "migrate_legacy_runs", lambda *a, **k: touched.append("migrated"))
    monkeypatch.setattr(app, "load_presets", lambda *a, **k: touched.append("presets"))
    assert app.main(argv) == 1
    assert "administrator" in capsys.readouterr().err
    assert touched == []  # it stopped before creating or reading presets, or starting anything


def test_a_normal_user_is_not_blocked(quiet_main, monkeypatch, capsys):
    monkeypatch.setattr(privileges, "is_admin", lambda: False)
    assert app.main(["list"]) == 0
    assert "game" in capsys.readouterr().out

