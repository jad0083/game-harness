"""Helper script to drive the game harness and save current_screen.jpg for visual inspection."""

import argparse
from pathlib import Path

from harness.client import AgentClient
from harness.session import GAME_WINDOW, Session

OUT_PATH = Path("current_screen.jpg")


def main() -> None:
    parser = argparse.ArgumentParser(description="Drive the game agent")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # screenshot
    p_shot = sub.add_parser("screenshot")
    p_shot.add_argument("--no-grid", action="store_true", help="Disable coordinate grid overlay")

    # click
    p_click = sub.add_parser("click")
    p_click.add_argument("x", type=float, help="X in last image coordinates (1568 width)")
    p_click.add_argument("y", type=float, help="Y in last image coordinates (882 height)")
    p_click.add_argument("--button", default="left", choices=["left", "right", "middle"])
    p_click.add_argument("--count", type=int, default=1)
    p_click.add_argument("--wait", type=float, default=0.8)
    p_click.add_argument("--no-grid", action="store_true")

    # key
    p_key = sub.add_parser("key")
    p_key.add_argument("combo", help="Key combo e.g. tab, enter, c, esc, space")
    p_key.add_argument("--repeat", type=int, default=1)
    p_key.add_argument("--wait", type=float, default=0.8)
    p_key.add_argument("--no-grid", action="store_true")

    # type
    p_type = sub.add_parser("type")
    p_type.add_argument("text")
    p_type.add_argument("--wait", type=float, default=0.5)

    # hover
    p_hover = sub.add_parser("hover")
    p_hover.add_argument("x", type=float)
    p_hover.add_argument("y", type=float)
    p_hover.add_argument("--wait", type=float, default=1.0)
    p_hover.add_argument("--no-grid", action="store_true")

    # zoom
    p_zoom = sub.add_parser("zoom")
    p_zoom.add_argument("x", type=float)
    p_zoom.add_argument("y", type=float)
    p_zoom.add_argument("w", type=float)
    p_zoom.add_argument("h", type=float)
    p_zoom.add_argument("--no-grid", action="store_true")

    # wait
    p_wait = sub.add_parser("wait")
    p_wait.add_argument("seconds", type=float)
    p_wait.add_argument("--no-grid", action="store_true")

    # focus
    p_focus = sub.add_parser("focus")
    p_focus.add_argument("--title", default=GAME_WINDOW)

    # turn (fast automated turn completion)
    p_turn = sub.add_parser("turn")
    p_turn.add_argument("--idle-ships", type=int, default=4, help="How many idle ships to cycle and auto-order")
    p_turn.add_argument("--wait", type=float, default=3.0, help="Wait for AI turn processing in seconds")
    p_turn.add_argument("--no-grid", action="store_true")

    # settle
    p_settle = sub.add_parser("settle")
    p_settle.add_argument("--timeout", type=float, default=30.0)
    p_settle.add_argument("--threshold", type=float, default=0.02)
    p_settle.add_argument("--no-grid", action="store_true")

    # diff
    p_diff = sub.add_parser("diff")
    p_diff.add_argument("--threshold", type=int, default=25)
    p_diff.add_argument("--no-grid", action="store_true")

    args = parser.parse_args()

    client = AgentClient()
    s = Session(client, save_dir=Path("screenshots"))

    grid = not getattr(args, "no_grid", False)

    if args.cmd != "screenshot":
        s.focus_game(GAME_WINDOW)

    if args.cmd == "focus":
        focused = s.focus_game(args.title)
        print(f"Focused: {focused}")
        jpeg, view = s.settle_and_screenshot(wait=1.0, grid=grid)
    elif args.cmd == "screenshot":
        jpeg, view = s.screenshot(grid=grid)
    elif args.cmd == "click":
        # First ensure session has a view
        s.screenshot()
        sx, sy = s.click(args.x, args.y, button=args.button, count=args.count)
        print(f"Clicked {args.button} x{args.count} at screen ({sx}, {sy}) [image ({args.x}, {args.y})]")
        jpeg, view = s.settle_and_screenshot(wait=args.wait, grid=grid)
    elif args.cmd == "key":
        s.screenshot()
        s.key(args.combo, repeat=args.repeat)
        print(f"Pressed {args.combo} x{args.repeat}")
        jpeg, view = s.settle_and_screenshot(wait=args.wait, grid=grid)
    elif args.cmd == "type":
        s.screenshot()
        s.type_text(args.text)
        print(f"Typed {args.text!r}")
        jpeg, view = s.settle_and_screenshot(wait=args.wait, grid=grid)
    elif args.cmd == "hover":
        s.screenshot()
        sx, sy = s.move(args.x, args.y)
        print(f"Hovering at screen ({sx}, {sy}) [image ({args.x}, {args.y})]")
        jpeg, view = s.settle_and_screenshot(wait=args.wait, grid=grid)
    elif args.cmd == "zoom":
        s.screenshot()
        jpeg, view = s.zoom(args.x, args.y, args.w, args.h, grid=grid)
        print(f"Zoomed region ({args.x}, {args.y}, {args.w}, {args.h}) -> {view.width}x{view.height}")
    elif args.cmd == "wait":
        print(f"Waiting {args.seconds}s...")
        jpeg, view = s.settle_and_screenshot(wait=args.seconds, grid=grid)
    elif args.cmd == "turn":
        s.focus_game(GAME_WINDOW)
        # Cycle idle ships and auto-colonize
        acts = []
        for _ in range(args.idle_ships):
            acts.append({"action": "key", "combo": "tab"})
            acts.append({"action": "wait", "seconds": 0.1})
            acts.append({"action": "key", "combo": "c"})
            acts.append({"action": "wait", "seconds": 0.1})
        s.batch(acts)
        # End turn
        s.key("enter")
        print(f"Advanced turn; waiting {args.wait}s for AI turns...")
        jpeg, view = s.settle_and_screenshot(wait=args.wait, grid=grid)
    elif args.cmd == "settle":
        res = s.wait_settle(timeout=args.timeout, threshold=args.threshold)
        print(f"Settle result: {res}")
        jpeg, view = s.screenshot(grid=grid)
    elif args.cmd == "diff":
        jpeg, view, bbox = s.diff_and_screenshot(grid=grid, threshold=args.threshold)
        print(f"Diff result: changed bbox={bbox}")

    OUT_PATH.write_bytes(jpeg)
    print(f"Saved {OUT_PATH} ({view.width}x{view.height})")


if __name__ == "__main__":
    main()
