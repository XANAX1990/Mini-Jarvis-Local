"""Start `listen` at login via a shortcut in the user's Startup folder.

Not a Windows Service: services can't open apps on the user's desktop.
`pythonw` runs without a console window; output goes to logs/listen.log.
"""
import os
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
SHORTCUT_NAME = "Jarvis.lnk"

# Reads everything from env vars, so no path is ever spliced into script text.
_PS_CREATE = (
    "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:JARVIS_LNK);"
    "$s.TargetPath = $env:JARVIS_TARGET;"
    "$s.Arguments = $env:JARVIS_ARGS;"
    "$s.WorkingDirectory = $env:JARVIS_WORKDIR;"
    "$s.Description = 'Jarvis voice launcher';"
    "$s.Save()"
)


def startup_dir():
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def shortcut_path():
    return startup_dir() / SHORTCUT_NAME


def shortcut_spec(project_dir=PROJECT_DIR):
    """What the shortcut runs: the venv's pythonw with `-m jarvis listen`."""
    pythonw = Path(project_dir) / ".venv" / "Scripts" / "pythonw.exe"
    return {
        "target": str(pythonw),
        "args": "-m jarvis listen",
        "workdir": str(project_dir),
    }


def install(project_dir=PROJECT_DIR):
    spec = shortcut_spec(project_dir)
    if not Path(spec["target"]).is_file():
        raise FileNotFoundError(f"{spec['target']} not found - create the .venv first")
    lnk = shortcut_path()
    lnk.parent.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "JARVIS_LNK": str(lnk),
        "JARVIS_TARGET": spec["target"],
        "JARVIS_ARGS": spec["args"],
        "JARVIS_WORKDIR": spec["workdir"],
    }
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_CREATE],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not lnk.exists():
        raise OSError(f"could not create the shortcut: {result.stderr.strip() or 'unknown error'}")
    return lnk


def remove():
    """Delete the shortcut. Returns True if it existed."""
    lnk = shortcut_path()
    if lnk.exists():
        lnk.unlink()
        return True
    return False


def is_installed():
    return shortcut_path().exists()
