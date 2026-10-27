import argparse
import sys

from jarvis.presets import PresetError, load_presets, run_preset


def build_parser():
    parser = argparse.ArgumentParser(prog="jarvis", description="Local voice launcher.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list available presets")
    run = sub.add_parser("run", help="run a preset by name")
    run.add_argument("name")
    return parser


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
    except PresetError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
