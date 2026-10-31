"""The local web API, served by the Jarvis process on 127.0.0.1 only.

This API can start programs on the PC, so SECURITY.md ("Local web API") rules apply to every line:
Host allow-list, Origin + X-Jarvis + JSON on every non-GET, no CORS outside dev mode, bodies
validated by pydantic with unknown fields refused, and short errors with no paths or stack traces.
"""
import copy
import threading
from datetime import datetime
from pathlib import Path as FilePath
from typing import Annotated, Optional, Union

from fastapi import FastAPI, Path, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, ValidationError, field_validator
from rapidfuzz import fuzz
from starlette.datastructures import Headers, MutableHeaders

from jarvis import log as jarvis_log
from jarvis.audio import AudioError
from jarvis.engine import Refused
from jarvis.matcher import normalize
from jarvis.models import ACTION_TYPES, NAME_PATTERN, Name, Preset, PresetCreate, missing_paths
from jarvis.presets import PresetError
from jarvis.settings import BOUNDS, Settings, save_settings, validate_hotkey

PORT = 3003
DEV_ORIGIN = "http://localhost:3004"
MAX_BODY_BYTES = 64 * 1024
SIMILAR_SCORE = 90
MAX_WARNINGS = 20
UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
CAPTURE_SECONDS = 10
WEB_DIR = FilePath(__file__).resolve().parent.parent / "web" / "out"
# The static export inlines its bootstrap scripts, hence 'unsafe-inline'; nothing is loaded from elsewhere.
CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
MISSING_WEB = (
    '<!doctype html><meta charset="utf-8"><title>Jarvis</title>'
    "<body style=\"font-family:sans-serif;background:#0b1120;color:#e2e8f0;padding:2rem\">"
    "<h1>Jarvis</h1><p>The web UI is not built yet. Run <code>npm run build</code> in <code>web/</code>, "
    "then restart Jarvis.</p><p>API: <a href=\"/api/state\" style=\"color:#38bdf8\">/api/state</a></p>"
)


# ---- security middleware ----

class _TooLarge(Exception):
    pass


class SecurityMiddleware:
    """Host allow-list for every request; Origin, X-Jarvis, JSON content type and a size cap for
    everything except GET. Pure ASGI so it also sees requests the router would reject."""

    def __init__(self, app, port=PORT, dev=False):
        self.app = app
        self.hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self.origins = {f"http://{host}" for host in self.hosts} | ({DEV_ORIGIN} if dev else set())

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http":  # no websockets are served
            await send({"type": "websocket.close", "code": 1008})
            return
        problem = self._problem(scope)
        if problem:
            status, error = problem
            await JSONResponse({"error": error}, status_code=status)(scope, receive, self._headers(scope, send))
            return
        total = 0
        started = False

        async def limited_receive():
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > MAX_BODY_BYTES:
                    raise _TooLarge
            return message

        async def tracking_send(message):
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await self._headers(scope, send)(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _TooLarge:
            if not started:
                await JSONResponse({"error": "too_large"}, status_code=413)(scope, receive, self._headers(scope, send))

    def _problem(self, scope):
        headers = Headers(scope=scope)
        if headers.get("host", "").lower() not in self.hosts:
            return 403, "forbidden_host"
        if scope["method"] in ("GET", "HEAD"):  # HEAD: the browser's link prefetch; it changes nothing
            return None
        if headers.get("x-jarvis") != "1":
            return 403, "missing_x_jarvis"
        if headers.get("origin") not in self.origins:
            return 403, "forbidden_origin"
        if headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            return 403, "json_only"
        length = headers.get("content-length", "")
        if length.isdigit() and int(length) > MAX_BODY_BYTES:
            return 413, "too_large"
        return None

    @staticmethod
    def _headers(scope, send):
        async def wrapped(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
                if scope["path"].startswith("/api/"):
                    headers["Cache-Control"] = "no-store"
                else:
                    headers["Cache-Control"] = "no-cache"  # revalidate, so a rebuilt UI shows up at once
                    headers["Content-Security-Policy"] = CSP
            await send(message)

        return wrapped


# ---- errors: short message + field name, never exception text, paths or input ----

class ApiError(Exception):
    def __init__(self, status, error, fields=None):
        self.status, self.error, self.fields = status, error, fields or []


_TAGS = {t["type"] for t in ACTION_TYPES}  # pydantic adds the action type to the location


def _field_errors(errors):
    """[{field, message}] from pydantic errors. Only location and message: never the input value."""
    out = []
    for err in errors:
        where = list(err["loc"])
        if where and where[0] in ("body", "query", "path"):  # which part of the request, not a field
            where = where[1:]
        loc = [p for p in where if p not in _TAGS]
        out.append({"field": ".".join(str(p) for p in loc), "message": err["msg"].removeprefix("Value error, ")})
    return out


# ---- request bodies ----

class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArmedBody(_Body):
    armed: StrictBool


class AddPhraseBody(_Body):
    preset: Name


Number = Union[StrictInt, StrictFloat]


class SettingsBody(_Body):
    hotkey: Optional[StrictStr] = None
    armed_on_start: Optional[StrictBool] = None
    silence_ms: Optional[StrictInt] = Field(None, ge=BOUNDS["silence_ms"][0], le=BOUNDS["silence_ms"][1])
    min_threshold: Optional[Number] = Field(None, ge=BOUNDS["min_threshold"][0], le=BOUNDS["min_threshold"][1])
    max_seconds: Optional[StrictInt] = Field(None, ge=BOUNDS["max_seconds"][0], le=BOUNDS["max_seconds"][1])
    beep: Optional[StrictBool] = None
    match_threshold: Optional[Number] = Field(None, ge=BOUNDS["match_threshold"][0], le=BOUNDS["match_threshold"][1])

    @field_validator("hotkey")
    @classmethod
    def _usable(cls, value):
        if value is None:
            return value
        hotkey, reason = validate_hotkey(value)
        if reason:
            raise ValueError(reason)
        return hotkey


# ---- phrase rules ----

def check_phrases(presets, name):
    """(errors, warnings) for preset `name`'s phrases against every other preset.

    The same phrase (after the matcher's normalization) in two presets is an error: Jarvis couldn't
    tell them apart. Very similar phrases are only a warning."""
    others = {}
    for other, preset in presets.items():
        if other != name:
            for phrase in preset["phrases"]:
                others.setdefault(normalize(phrase), (other, phrase))
    errors, warnings = [], []
    for phrase in presets[name]["phrases"]:
        heard = normalize(phrase)
        if heard in others:
            errors.append({"field": "phrases", "message": f"'{phrase}' is already used by preset '{others[heard][0]}'"})
            continue
        for known, (other, other_phrase) in others.items():
            score = fuzz.ratio(heard, known)
            if score >= SIMILAR_SCORE and len(warnings) < MAX_WARNINGS:
                warnings.append({"phrase": phrase, "preset": other, "similar_to": other_phrase, "score": round(score)})
    return errors, warnings


# ---- the app ----

def create_app(engine, store, *, settings_path, logs_dir, port=PORT, dev=False, capture=None, web_dir=None,
               log=print):
    app = FastAPI(title="Jarvis", docs_url=None, redoc_url=None, openapi_url=None)
    preset_lock = threading.Lock()
    capture_lock = threading.Lock()

    @app.exception_handler(ApiError)
    async def api_error(request, exc):
        return JSONResponse({"error": exc.error, "fields": exc.fields}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return JSONResponse({"error": "invalid", "fields": _field_errors(exc.errors())}, status_code=422)

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        log(f"api error: {type(exc).__name__}")  # type only: the message may hold paths
        return JSONResponse({"error": "internal"}, status_code=500)

    # -- state --

    def state():
        last = engine.last
        return {
            "armed": engine.armed,
            "state": engine.state,
            "hotkey": engine.settings.hotkey,
            "preset": engine.current_preset,
            "last": None if last is None else {k: last.get(k) for k in ("time", "transcript", "preset", "score", "result")},
        }

    @app.get("/api/state")
    def get_state():
        return state()

    @app.post("/api/armed")
    def set_armed(body: ArmedBody):
        engine.set_armed(body.armed)
        return state()

    @app.post("/api/listen/toggle")
    def toggle():
        accepted = engine.toggle_listen("web")
        return {"accepted": accepted, **state()}

    # -- presets --

    def listing():
        return [{"name": name, **preset} for name, preset in engine.presets.items()]

    def commit(new_presets, name, preset=None):
        """Path and phrase checks, then save + reload. Returns warnings.

        All problems are reported together; the file is untouched if there is any."""
        errors, warnings = check_phrases(new_presets, name)
        if preset is not None:  # saved from the web: the files it starts must exist
            errors = [{"field": f, "message": m} for f, m in missing_paths(preset)] + errors
        if errors:
            raise ApiError(422, "invalid", errors)
        try:
            store.save(new_presets)
        except OSError:
            raise ApiError(500, "could_not_save") from None
        engine.reload_presets(new_presets)
        return warnings

    @app.get("/api/presets")
    def list_presets():
        return {"presets": listing()}

    @app.post("/api/presets", status_code=201)
    def create_preset(body: PresetCreate):
        with preset_lock:
            presets = copy.deepcopy(engine.presets)
            if body.name in presets:
                raise ApiError(409, "exists", [{"field": "name", "message": "a preset with this name already exists"}])
            presets[body.name] = body.model_dump(exclude={"name"}, exclude_unset=True)
            warnings = commit(presets, body.name, body)
        return {"name": body.name, "warnings": warnings}

    @app.put("/api/presets/{name}")
    def replace_preset(name: Annotated[str, Path(pattern=NAME_PATTERN)], body: Preset):
        with preset_lock:
            presets = copy.deepcopy(engine.presets)
            if name not in presets:
                raise ApiError(404, "not_found")
            presets[name] = body.model_dump(exclude_unset=True)
            warnings = commit(presets, name, body)
        return {"name": name, "warnings": warnings}

    @app.delete("/api/presets/{name}")
    def delete_preset(name: Annotated[str, Path(pattern=NAME_PATTERN)]):
        with preset_lock:
            presets = copy.deepcopy(engine.presets)
            if name not in presets:
                raise ApiError(404, "not_found")
            if len(presets) == 1:
                raise ApiError(409, "last_preset", [{"field": "name", "message": "at least one preset must remain"}])
            del presets[name]
            try:
                store.save(presets)
            except OSError:
                raise ApiError(500, "could_not_save") from None
            engine.reload_presets(presets)
        return {"name": name}

    @app.post("/api/presets/{name}/test")
    def test_preset(name: Annotated[str, Path(pattern=NAME_PATTERN)]):
        # runs the saved preset only; no request body is read
        try:
            started = engine.run_preset(name, "test")
        except PresetError:
            raise ApiError(404, "not_found") from None
        if not started:
            raise ApiError(409, "busy")
        return {"started": True}

    @app.get("/api/action-types")
    def action_types():
        return {"types": ACTION_TYPES}

    # -- logs --

    @app.get("/api/logs")
    def get_logs(date: Annotated[Optional[str], Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None):
        day = date or jarvis_log.today()
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            raise ApiError(422, "invalid", [{"field": "date", "message": "not a real date"}]) from None
        return {"date": day, "entries": jarvis_log.read_day(day, logs_dir)}

    @app.get("/api/logs/dates")
    def get_log_dates():
        return {"dates": jarvis_log.list_days(logs_dir)}

    @app.post("/api/logs/{entry_id}/add-phrase")
    def add_phrase(entry_id: Annotated[str, Path(pattern=UUID_PATTERN)], body: AddPhraseBody):
        entry = jarvis_log.find_entry(entry_id, logs_dir)
        if entry is None:
            raise ApiError(404, "not_found")
        transcript = str(entry.get("transcript") or "").strip()
        if not normalize(transcript):
            raise ApiError(422, "invalid", [{"field": "transcript", "message": "this log line has no transcript"}])
        with preset_lock:
            presets = copy.deepcopy(engine.presets)
            if body.preset not in presets:
                raise ApiError(404, "not_found")
            phrases = presets[body.preset]["phrases"]
            if normalize(transcript) in {normalize(p) for p in phrases}:
                return {"name": body.preset, "warnings": [], "added": False}
            phrases.append(transcript)
            try:
                Preset.model_validate(presets[body.preset])
            except ValidationError as e:
                raise ApiError(422, "invalid", _field_errors(e.errors())) from None
            warnings = commit(presets, body.preset)
        return {"name": body.preset, "warnings": warnings, "added": True}

    # -- settings and hotkey --

    @app.get("/api/settings")
    def get_settings():
        return engine.settings.to_dict()

    @app.put("/api/settings")
    def put_settings(body: SettingsBody):
        changes = body.model_dump(exclude_none=True)
        if "min_threshold" in changes:
            changes["min_threshold"] = float(changes["min_threshold"])
        if "match_threshold" in changes:
            changes["match_threshold"] = float(changes["match_threshold"])
        if "hotkey" in changes:
            reason = engine.check_hotkey(changes["hotkey"])
            if reason:
                raise ApiError(422, "invalid", [{"field": "hotkey", "message": reason}])
        new = Settings(**{**engine.settings.to_dict(), **changes})
        try:
            save_settings(new, settings_path)
        except OSError:
            raise ApiError(500, "could_not_save") from None
        engine.update_settings(new)
        return new.to_dict()

    @app.post("/api/mic/test")
    def mic_test():
        # listens for 3 s because the person clicked the button; keeps nothing
        try:
            return engine.mic_test()
        except Refused as e:
            raise ApiError(409, e.reason) from None
        except AudioError:
            raise ApiError(503, "no_microphone") from None

    @app.post("/api/hotkey/capture")
    def capture_hotkey():
        if not capture_lock.acquire(blocking=False):
            raise ApiError(409, "busy")
        try:
            run = capture or _default_capture
            combo = engine.capture_hotkey(lambda: run(CAPTURE_SECONDS))
        finally:
            capture_lock.release()
        if combo is None:  # not an HTTP error: browsers may retry a 408 by themselves
            return {"hotkey": None, "ok": False, "reason": "timeout"}
        hotkey, reason = validate_hotkey(combo)
        return {"hotkey": hotkey or combo, "ok": reason is None, "reason": reason}

    if web_dir is not None:  # last, so every /api route wins
        if FilePath(web_dir).is_dir():
            app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
        else:
            @app.get("/", include_in_schema=False)
            def web_not_built():
                return HTMLResponse(MISSING_WEB)

    app.add_middleware(SecurityMiddleware, port=port, dev=dev)
    if dev:  # outermost: answers the preflight for the dev web server, and nobody else
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[DEV_ORIGIN],
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["Content-Type", "X-Jarvis"],
            allow_credentials=False,
        )
    return app


def _default_capture(timeout):
    from jarvis import hotkey

    return hotkey.capture(timeout)
