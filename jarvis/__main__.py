import argparse
import sys
import time

from jarvis.audio import AudioError
from jarvis.presets import PresetError, load_presets, run_preset


def build_parser():
    parser = argparse.ArgumentParser(prog="jarvis", description="Local voice launcher.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list available presets")
    run = sub.add_parser("run", help="run a preset by name")
    run.add_argument("name")
    sub.add_parser("record", help="hold F9 to record; saves logs/last.wav")
    tr = sub.add_parser("transcribe", help="transcribe WAV files (default: logs/last.wav)")
    tr.add_argument("files", nargs="*", help="WAV files")
    tr.add_argument("--model", default="small", help="Whisper model size (default: small)")
    tr.add_argument("--compare", action="store_true", help="compare small vs medium")
    say = sub.add_parser("say", help="speak a sentence with the Piper voice (or beep)")
    say.add_argument("text")
    ls = sub.add_parser("listen", help="loop: hold F9, speak, run the matching preset")
    ls.add_argument("--model", default="small", help="Whisper model size (default: small)")
    ls.add_argument(
        "--threshold", type=float, default=70, help="minimum match score 0-100 (default: 70)"
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
        from jarvis.log import LOG_PATH

        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        f = open(LOG_PATH.with_name("listen.log"), "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or f
        sys.stderr = sys.stderr or f


def cmd_listen(args, presets):
    from jarvis import audio, stt
    from jarvis.log import log_command
    from jarvis import single
    from jarvis.matcher import match
    from jarvis.tts import NO_MATCH_REPLY, Speaker

    if single.acquire() is None:
        print("Jarvis is already running - not starting a second copy.")
        return 1

    prompt = stt.build_prompt(presets)
    speaker = Speaker()
    print("loading models...")
    stt.get_model(args.model, args.device)
    speaker.warm()
    print("Ready. Hold F9 and speak. Ctrl+C to quit.")
    try:
        while True:
            samples = audio.record_clip()
            text, secs = stt.transcribe_samples(samples, args.model, prompt, args.device)
            name, score = match(text, presets, args.threshold)
            log_command(text, name, score, secs)
            if name is None:
                print(f"ไม่เข้าใจ  (heard {text!r}, score {score:.0f})")
                speaker.speak(NO_MATCH_REPLY)
                continue
            print(f"{name}  (heard {text!r}, score {score:.0f}, {secs:.1f}s)")
            speaker.speak(presets[name]["reply"])  # before the preset: it may wait/sleep
            run_preset(presets, name)
    except KeyboardInterrupt:
        print("\nbye")


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
            from jarvis import audio

            print("Hold F9 and speak, release to stop...")
            samples = audio.record_clip()
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
