"""Manual smoke-test CLI for the game agent (coordinates are raw screen pixels)."""

from __future__ import annotations

import argparse
import json
import sys

from .client import AgentClient, AgentError
from .imaging import render


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="game-harness")
    ap.add_argument("--url", help="agent base URL (default $GAME_AGENT_URL or http://192.168.1.77:8765)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("health")
    sub.add_parser("windows")
    p = sub.add_parser("screenshot")
    p.add_argument("out")
    p.add_argument("--grid", action="store_true")
    p = sub.add_parser("click")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)
    p.add_argument("--button", default="left")
    p = sub.add_parser("move")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)
    p = sub.add_parser("key")
    p.add_argument("combo")
    p = sub.add_parser("type")
    p.add_argument("text")
    p = sub.add_parser("focus")
    p.add_argument("title")
    args = ap.parse_args(argv)

    try:
        c = AgentClient(args.url)
        if args.cmd == "health":
            print(json.dumps(c.health(), indent=2))
        elif args.cmd == "windows":
            for w in c.windows():
                print(("* " if w["foreground"] else "  ") + w["title"])
        elif args.cmd == "screenshot":
            png = c.screenshot()
            if args.grid or args.out.lower().endswith((".jpg", ".jpeg")):
                png, _ = render(png, max_side=10_000, grid=args.grid)
            with open(args.out, "wb") as f:
                f.write(png)
            print(f"wrote {args.out}")
        elif args.cmd == "click":
            print(c.click(args.x, args.y, args.button))
        elif args.cmd == "move":
            print(c.move(args.x, args.y))
        elif args.cmd == "key":
            print(c.key(args.combo))
        elif args.cmd == "type":
            print(c.type_text(args.text))
        elif args.cmd == "focus":
            print(c.focus(args.title))
    except AgentError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
