import argparse
import os
import sys
import time
from dataclasses import replace

from jarvis.audio import AudioError
from jarvis.matcher import MIN_THRESHOLD
from jarvis.presets import PresetError, get_preset, load_presets, run_preset, spending_period, spoken_reply


def threshold_arg(text):
    """SECURITY.md: below the match threshold Jarvis does nothing, it never guesses a preset.
    A threshold of 0 would turn that off, so the command line refuses anything under the floor."""
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a number") from None
    if not MIN_THRESHOLD <= value <= 100:  # also rejects nan
        raise argparse.ArgumentTypeError(
            f"must be between {MIN_THRESHOLD} and 100 (lower would mean guessing a preset)"
        )
    return value


def build_parser():
    parser = argparse.ArgumentParser(prog="jarvis", description="Local voice launcher.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list available presets")
    run = sub.add_parser("run", help="run a preset by name")
    run.add_argument("name")
    sub.add_parser("record", help="record until you stop talking; saves logs/last.wav")
    tr = sub.add_parser("transcribe", help="transcribe WAV files (default: logs/last.wav)")
    tr.add_argument("files", nargs="*", help="WAV files")
    tr.add_argument("--model", default="small", help="Whisper model size (default: small)")
    tr.add_argument("--compare", action="store_true", help="compare small vs medium")
    say = sub.add_parser("say", help="speak a sentence with the Piper voice (or beep)")
    say.add_argument("text")
    ls = sub.add_parser("listen", help="tap the hotkey, speak, run the matching preset")
    ls.add_argument("--model", default="small", help="Whisper model size (default: small)")
    ls.add_argument("--no-web", action="store_true", help="do not start the web API on 127.0.0.1:3003")
    ls.add_argument(
        "--threshold",
        type=threshold_arg,
        default=None,
        help=f"minimum match score {MIN_THRESHOLD}-100 (default: match_threshold in settings.json)",
    )
    for p in (tr, ls):
        p.add_argument(
            "--device",
            choices=["cpu", "cuda"],
            default="cpu",
            help="cuda tries the GPU and falls back to CPU if its libraries are missing",
        )
    auto = sub.add_parser("autostart", help="start `listen` automatically at login")
    auto.add_argument("action", choices=["install", "remove", "status"])
    return parser


def cmd_autostart(args):
    from jarvis import autostart

    if args.action == "install":
        print(f"created {autostart.install()} - Jarvis will start at your next login")
    elif args.action == "remove":
        print("removed" if autostart.remove() else "not installed")
    else:
        print(f"installed: {autostart.shortcut_path()}" if autostart.is_installed() else "not installed")


def redirect_output_if_windowless():
    """pythonw has no console (sys.stdout is None): send output to logs/listen.log."""
    if sys.stdout is None or sys.stderr is None:
        from jarvis.log import LOG_PATH, TimestampedWriter, prune_text_log

        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        listen_log = LOG_PATH.with_name("listen.log")
        try:
            prune_text_log(listen_log)  # before opening it: Windows cannot replace an open file
        except OSError:
            pass  # another Jarvis still holds it open; it is pruned the next time
        f = TimestampedWriter(open(listen_log, "a", encoding="utf-8", buffering=1))
        sys.stdout = sys.stdout or f
        sys.stderr = sys.stderr or f


def cmd_listen(args, presets):
    from jarvis import api, audio, single, stt
    from jarvis.engine import Engine
    from jarvis.hotkey import Hotkeys
    from jarvis.log import LOGS_DIR, RETENTION_DAYS, log_command, prune_command_files, prune_commands, prune_daily_logs
    from jarvis.matcher import match
    from jarvis.settings import SETTINGS_PATH, load_settings
    from jarvis.store import PresetStore
    from jarvis.tts import Speaker

    if single.acquire() is None:
        print("Jarvis is already running - not starting a second copy.")
        return 1

    if not args.no_web:
        from jarvis import server

        try:
            server.ensure_port_free(api.PORT)
        except server.PortInUse:
            print(f"Jarvis is already running (port {api.PORT} is taken) - not starting a second copy.")
            return 1

    settings = load_settings()
    if args.threshold is not None:
        settings = replace(settings, match_threshold=args.threshold)
    # transcripts are kept for a limited time only
    removed = prune_daily_logs() + prune_command_files() + prune_commands()
    if removed:
        print(f"removed {removed} log entries/files older than {RETENTION_DAYS} days")
    speaker = Speaker()
    print("loading models...")
    stt.get_model(args.model, args.device)
    speaker.warm()
    engine = Engine(
        presets,
        settings,
        record=audio.record_until_silence,
        transcribe=lambda samples, prompt: stt.transcribe_samples(samples, args.model, prompt, args.device),
        match=match,
        run_preset=run_preset,
        spoken_reply=spoken_reply,
        speak=speaker.speak,
        beep=audio.beep,
        log_command=log_command,
        hotkeys=Hotkeys(),
        build_prompt=stt.build_prompt,
        wait_speaking=speaker.wait,
        record_fixed=audio.record_fixed,
    )
    web = None
    if not args.no_web:
        app = api.create_app(
            engine, PresetStore(), settings_path=SETTINGS_PATH, logs_dir=LOGS_DIR, web_dir=api.WEB_DIR,
            dev=os.environ.get("JARVIS_DEV") == "1",
        )
        web = server.ApiServer(app, api.PORT)
        web.start()
        print(f"Web API on http://127.0.0.1:{api.PORT}")
    engine.set_armed(settings.armed_on_start)
    state = f"tap {settings.hotkey}" if settings.armed_on_start else "switched off (armed_on_start is false)"
    print(f"Ready: {state} and speak. Ctrl+C to quit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        engine.close()
        if web:
            web.stop()


def cmd_transcribe(args, presets):
    from jarvis import audio, stt

    files = args.files or [str(audio.LAST_WAV)]
    prompt = stt.build_prompt(presets)
    sizes = ["small", "medium"] if args.compare else [args.model]
    for size in sizes:
        print(f"== model: {size} (first use downloads it) ==")
        t0 = time.perf_counter()
        stt.get_model(size, args.device)
        print(f"loaded in {time.perf_counter() - t0:.1f}s")
        total = 0.0
        for f in files:
            text, secs = stt.transcribe(f, size, prompt, args.device)
            total += secs
            print(f"{f}: {text!r}  ({secs:.1f}s)")
        print(f"average {total / len(files):.1f}s per clip")


def main(argv=None):
    redirect_output_if_windowless()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        presets = load_presets()
        if args.command == "list":
            for name, preset in presets.items():
                print(f"{name}: {', '.join(preset['phrases'])}")
        elif args.command == "run":
            if spending_period(get_preset(presets, args.name)):
                from jarvis.tts import Speaker

                text = spoken_reply(presets[args.name])  # a question, not an action: say the answer
                print(text)
                speaker = Speaker()
                speaker.speak(text)
                speaker.wait()
            return 1 if run_preset(presets, args.name) else 0
        elif args.command == "transcribe":
            cmd_transcribe(args, presets)
        elif args.command == "autostart":
            cmd_autostart(args)
        elif args.command == "say":
            from jarvis.tts import Speaker

            speaker = Speaker()
            speaker.speak(args.text)
            speaker.wait()
        elif args.command == "listen":
            return cmd_listen(args, presets) or 0
        elif args.command == "record":
            import threading

            from jarvis import audio
            from jarvis.settings import load_settings

            print("Speak now (it stops by itself after a pause)...")
            samples, outcome = audio.record_until_silence(threading.Event(), load_settings())
            print(f"stopped: {outcome}")
            audio.save_wav(audio.LAST_WAV, samples)
            print(
                f"saved {audio.LAST_WAV} - "
                f"{audio.duration_seconds(samples):.2f}s, peak {audio.peak_level(samples):.2f}"
            )
    except (PresetError, AudioError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
