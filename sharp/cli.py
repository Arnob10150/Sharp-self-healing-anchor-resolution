from __future__ import annotations

import argparse
import json
from pathlib import Path

from .resolver import AnchorStore, resolve, store_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sharp", description="Content-anchored folder resolver")
    parser.add_argument("--store", default=".sharp_anchors.json", help="anchor store JSON path")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="create or replace an anchor")
    add.add_argument("alias")
    add.add_argument("folder")

    resolve_cmd = sub.add_parser("resolve", help="resolve an anchor")
    resolve_cmd.add_argument("alias")
    resolve_cmd.add_argument("--root", action="append", help="search root; can be repeated")
    resolve_cmd.add_argument("--max-depth", type=int, default=4)

    go = sub.add_parser("go", help="print only the resolved path")
    go.add_argument("alias")
    go.add_argument("--root", action="append")
    go.add_argument("--max-depth", type=int, default=4)

    sub.add_parser("doctor", help="show anchor store status")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = AnchorStore(Path(args.store))

    if args.command == "add":
        record = store.add(args.alias, args.folder)
        print(json.dumps(record.to_dict(), indent=2))
        return 0

    if args.command in {"resolve", "go"}:
        result = resolve(args.alias, store, roots=args.root, max_depth=args.max_depth)
        if args.command == "go":
            if result.path and result.decision.label in {"accept", "ask"}:
                print(result.path)
                return 0
            return 2
        print(json.dumps({
            "alias": result.alias,
            "path": result.path,
            "decision": result.decision.label,
            "score": result.decision.score,
            "reason": result.decision.reason,
            "candidates_scored": result.candidates_scored,
        }, indent=2))
        return 0 if result.decision.label == "accept" else 2

    if args.command == "doctor":
        print(json.dumps(store_summary(store), indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
