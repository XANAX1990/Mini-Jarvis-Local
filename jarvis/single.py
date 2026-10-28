"""Only one `listen` at a time.

With no console window (pythonw) it's easy to start Jarvis twice, and then two
listeners react to the same F9 press and launch every preset twice. A Windows
named mutex is released by the OS when the process exits, even after a crash,
so there is no stale lock file to clean up.
"""
import ctypes

ERROR_ALREADY_EXISTS = 183
LISTEN_MUTEX = "Local\\JarvisListen"

_held = []  # keep handles referenced for the life of the process


def acquire(name=LISTEN_MUTEX):
    """Return a handle if we are the only holder of `name`, else None."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, name)
    already_exists = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
    if not handle:
        raise OSError(f"could not create mutex {name!r}")
    if already_exists:
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        return None
    _held.append(handle)
    return handle


def release(handle):
    ctypes.WinDLL("kernel32").CloseHandle(ctypes.c_void_p(handle))
    if handle in _held:
        _held.remove(handle)
