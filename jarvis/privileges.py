"""Jarvis never runs as administrator (SECURITY.md): it can start programs, and an elevated copy would start
them elevated too, and see keys typed into elevated windows."""
import ctypes


def is_admin():
    """True if this process is elevated. If Windows cannot say, assume it is not."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False
