#!/usr/bin/env python3
"""Run the local Isekai RPG web server."""

import argparse
import time

from game_engine import GameEngine


def main():
    parser = argparse.ArgumentParser(description="Run the Isekai RPG web server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    GameEngine(
        start_web=True,
        open_browser=not args.no_browser,
        host=args.host,
        port=args.port,
    )

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
