"""Command-line interface for laughter detection."""

import argparse
import json
import sys
from pathlib import Path

from .detector import LaughterDetector


def main():
    parser = argparse.ArgumentParser(
        description="Detect laughter in video/audio files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s video.mp4
  %(prog)s video.mp4 -o results.json
  %(prog)s video.mp4 --threshold 0.6 --min-duration 0.5
  %(prog)s video.mp4 --player
        """
    )

    parser.add_argument(
        "input",
        help="Path to the input video or audio file"
    )

    parser.add_argument(
        "-o", "--output",
        help="Path for the output JSON file (default: <input>_laughter.json)"
    )

    parser.add_argument(
        "-t", "--threshold",
        type=float,
        default=0.5,
        help="Laughter detection threshold (0-1, default: 0.5)"
    )

    parser.add_argument(
        "-m", "--min-duration",
        type=float,
        default=0.3,
        help="Minimum duration in seconds for a laughter segment (default: 0.3)"
    )

    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress output except for errors"
    )

    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Print JSON results to stdout"
    )

    parser.add_argument(
        "--player",
        action="store_true",
        help="After detection, launch a local web player that shows laughter markers on the video timeline"
    )

    parser.add_argument(
        "--player-port",
        type=int,
        default=8000,
        help="Preferred port for --player (falls back to a random free port if taken; default: 8000)"
    )

    parser.add_argument(
        "--no-open",
        action="store_true",
        help="With --player, do not auto-open the system browser"
    )

    args = parser.parse_args()

    input_path = Path(args.input)

    if not input_path.exists():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        output_path = str(input_path.with_suffix("")) + "_laughter.json"

    if not args.quiet:
        print(f"Processing: {input_path}")
        print(f"Threshold: {args.threshold}")
        print(f"Min duration: {args.min_duration}s")

    try:
        detector = LaughterDetector(
            threshold=args.threshold,
            min_duration=args.min_duration
        )

        results = detector.process_video(str(input_path), output_path)

        if not args.quiet:
            print(f"\nDetected {results['total_segments']} laughter segment(s)")

            if results['segments']:
                print("\nSegments:")
                for i, seg in enumerate(results['segments'], 1):
                    print(f"  {i}. {seg['start_time']:.2f}s - {seg['end_time']:.2f}s "
                          f"(duration: {seg['duration']:.2f}s, score: {seg['score']:.3f})")

            print(f"\nResults saved to: {output_path}")

        if args.print_json:
            print(json.dumps(results, indent=2))

        if args.player:
            from .player import serve_player
            serve_player(
                video_path=str(input_path),
                results=results,
                port=args.player_port,
                open_browser=not args.no_open,
            )

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
