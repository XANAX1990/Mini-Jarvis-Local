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
    ls = sub.add_parser("listen", help="loop: hold F9, speak, run the matching preset")
    ls.add_argument("--model", default="small", help="Whisper model size (default: small)")
    ls.add_argument(
        "--threshold", type=float, default=70, help="minimum match score 0-100 (default: 70)"
    )
    return parser


def cmd_listen(args, presets):
    from jarvis import audio, stt
    from jarvis.log import log_command
    from jarvis.matcher import match

    prompt = stt.build_prompt(presets)
    print("loading model...")
    stt.get_model(args.model)
    print("Ready. Hold F9 and speak. Ctrl+C to quit.")
    try:
        while True:
            samples = audio.record_clip()
            text, secs = stt.transcribe_samples(samples, args.model, prompt)
            name, score = match(text, presets, args.threshold)
            log_command(text, name, score, secs)
            if name is None:
                print(f"ไม่เข้าใจ  (heard {text!r}, score {score:.0f})")
                continue
            print(f"{name}  (heard {text!r}, score {score:.0f}, {secs:.1f}s)")
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
        stt.get_model(size)
        print(f"loaded in {time.perf_counter() - t0:.1f}s")
        total = 0.0
        for f in files:
            text, secs = stt.transcribe(f, size, prompt)
            total += secs
            print(f"{f}: {text!r}  ({secs:.1f}s)")
        print(f"average {total / len(files):.1f}s per clip")


def main(argv=None):
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
        elif args.command == "listen":
            cmd_listen(args, presets)
        elif args.command == "record":
            from jarvis import audio

            print("Hold F9 and speak, release to stop...")
            samples = audio.record_clip()
            audio.save_wav(audio.LAST_WAV, samples)
            print(
                f"saved {audio.LAST_WAV} - "
                f"{audio.duration_seconds(samples):.2f}s, peak {audio.peak_level(samples):.2f}"
            )
    except (PresetError, AudioError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
