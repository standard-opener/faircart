from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .model import FairCartError, load_cart
from .report import demo_cases, render_dashboard
from .solver import compare_topup, optimize


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan group checkouts and protect individual payment limits.")
    parser.add_argument("--version", action="version", version=f"FairCart {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="Find the cheapest ordering plan and allocate payments")
    plan.add_argument("cart", type=Path)
    plan.add_argument("--format", choices=["text", "json", "html"], default="text")
    plan.add_argument("--output", type=Path)
    topup = commands.add_parser("topup", help="Compare checkout cost before and after adding an item")
    topup.add_argument("cart", type=Path)
    topup.add_argument("--owner", required=True)
    topup.add_argument("--price", required=True)
    topup.add_argument("--name", default="Extra item")
    topup.add_argument("--quantity", default=1, type=int)
    topup.add_argument("--output", type=Path)
    demo = commands.add_parser("demo", help="Create an editable offline calculator")
    demo.add_argument("--output", type=Path, default=Path("FairCart_Demo.html"))
    args = parser.parse_args(argv)
    try:
        code = 0
        if args.command == "demo":
            output = render_dashboard(demo_cases())
        elif args.command == "topup":
            result = compare_topup(load_cart(args.cart), owner=args.owner, price=args.price,
                                   name=args.name, quantity=args.quantity)
            output = json.dumps(result, indent=2)
        else:
            cart = load_cart(args.cart)
            result = optimize(cart)
            code = 0 if result.feasible else 1
            output = (result.to_text() if args.format == "text" else
                      json.dumps(result.to_dict(), indent=2) if args.format == "json" else
                      render_dashboard([{"id": "custom", "label": cart.title, "cart": cart.to_dict()}]))
        if args.output:
            with args.output.open("x", encoding="utf-8", newline="") as handle:
                handle.write(output + "\n")
            print(f"Saved: {args.output}", file=sys.stderr)
        else:
            print(output)
        return code
    except (FairCartError, OSError) as exc:
        print(f"FairCart: {exc}", file=sys.stderr)
        return 2
