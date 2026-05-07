# scrcpy_device/__main__.py
import argparse
import logging
import sys
from .api import ScrcpyClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main():
    parser = argparse.ArgumentParser(description="scrcpy_device - Quick test & utilities")
    parser.add_argument("--serial", type=str, help="Device serial")
    parser.add_argument("--max-size", type=int, default=1080, help="Video max size")
    parser.add_argument("--bitrate", type=int, default=8000000, help="Video bitrate")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("screenshot", help="Take a screenshot and save as screenshot.png")
    subparsers.add_parser("info", help="Show device info")
    subparsers.add_parser("interact", help="Open interactive Python REPL with client")

    args = parser.parse_args()

    with ScrcpyClient(serial=args.serial, max_size=args.max_size, bitrate=args.bitrate) as client:
        if args.command == "screenshot":
            frame = client.get_frame()
            try:
                from PIL import Image
                img = Image.fromarray(frame)
                img.save("screenshot.png")
                print("Screenshot saved to screenshot.png")
            except ImportError:
                print("Pillow not installed, cannot save image. Install with: pip install Pillow")

        elif args.command == "info":
            print(f"Device: {client.device_name}")
            print(f"Resolution: {client.resolution}")
            print(f"Codec: {client.codec_name}")

        elif args.command == "interact":
            import code
            print("Interactive scrcpy client. 'client' is available.")
            code.interact(local=dict(client=client))


if __name__ == "__main__":
    main()