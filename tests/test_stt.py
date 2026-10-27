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
    monkeypatch.setattr(stt, "_load", lambda size, device: loads.append(size) or object())
    a = stt.get_model("small")
    b = stt.get_model("small")
    stt.get_model("medium")
    assert a is b
    assert loads == ["small", "medium"]


def test_cuda_failure_falls_back_to_cpu_and_logs(monkeypatch):
    made, logs = [], []

    def make(size, device):
        made.append(device)
        return f"model-{device}"

    def warmup(model):
        if model == "model-cuda":
            raise RuntimeError("Library cublas64_12.dll is not found")

    monkeypatch.setattr(stt, "_make", make)
    monkeypatch.setattr(stt, "_warmup", warmup)
    assert stt._load("small", "cuda", log=logs.append) == "model-cpu"
    assert made == ["cuda", "cpu"]
    assert "falling back to CPU" in logs[0] and "cublas" in logs[0]


def test_cuda_success_stays_on_gpu(monkeypatch):
    logs = []
    monkeypatch.setattr(stt, "_make", lambda size, device: f"model-{device}")
    monkeypatch.setattr(stt, "_warmup", lambda model: None)
    assert stt._load("small", "cuda", log=logs.append) == "model-cuda"
    assert "GPU" in logs[0]


def test_cpu_never_touches_cuda(monkeypatch):
    made = []
    monkeypatch.setattr(stt, "_make", lambda size, device: made.append(device) or "m")
    monkeypatch.setattr(stt, "_warmup", lambda model: made.append("warmup"))
    stt._load("small", "cpu")
    assert made == ["cpu"]
