"""Runs the API with uvicorn in a background thread, bound to 127.0.0.1 only (SECURITY.md)."""
import socket
import threading
import time

import uvicorn

HOST = "127.0.0.1"  # never 0.0.0.0


class PortInUse(OSError):
    pass


def ensure_port_free(port):
    """Raise PortInUse if something already listens on 127.0.0.1:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((HOST, port))
        except OSError:
            raise PortInUse(f"port {port} is already in use") from None


class ApiServer:
    def __init__(self, app, port):
        self.config = uvicorn.Config(
            app, host=HOST, port=port, log_config=None, log_level="warning",
            access_log=False, lifespan="off", ws="none", http="h11",
        )
        self._server = uvicorn.Server(self.config)
        self._thread = threading.Thread(target=self._server.run, name="jarvis-api", daemon=True)

    def start(self, timeout=10.0):
        self._thread.start()
        deadline = time.monotonic() + timeout
        while not self._server.started:
            if not self._thread.is_alive() or time.monotonic() > deadline:
                raise OSError("the web API did not start")
            time.sleep(0.02)

    def stop(self):
        self._server.should_exit = True
        self._thread.join(3)
