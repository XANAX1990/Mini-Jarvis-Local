from jarvis import stt


def test_build_prompt_joins_all_phrases():
    presets = {
        "game": {"phrases": ["เปิดโหมดเกม", "โหมดเล่นเกม"]},
        "work": {"phrases": ["เปิดโหมดทำงาน"]},
    }
    assert stt.build_prompt(presets) == "เปิดโหมดเกม โหมดเล่นเกม เปิดโหมดทำงาน"


def test_model_loaded_once_per_size(monkeypatch):
    loads = []
    monkeypatch.setattr(stt, "_models", {})
    monkeypatch.setattr(stt, "_load", lambda size: loads.append(size) or object())
    a = stt.get_model("small")
    b = stt.get_model("small")
    stt.get_model("medium")
    assert a is b
    assert loads == ["small", "medium"]
