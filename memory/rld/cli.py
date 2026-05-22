from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import RecursiveLatentDNA


def main() -> None:
    parser = argparse.ArgumentParser(description="Recursive Latent DNA reasoning memory")
    parser.add_argument("--storage", default=".rld/genes.json")
    subparsers = parser.add_subparsers(dest="command", required=True)

    observe = subparsers.add_parser("observe", help="Store a successful reasoning trajectory")
    observe.add_argument("task")
    observe.add_argument("--state", action="append", default=[])
    observe.add_argument("--action", action="append", default=[])
    observe.add_argument("--answer", default="")
    observe.add_argument("--tool", action="append", default=[])
    observe.add_argument("--failed", action="store_true")
    observe.add_argument("--utility", type=float, default=0.7)

    activate = subparsers.add_parser("activate", help="Activate DSM-selected reasoning genes")
    activate.add_argument("query")
    activate.add_argument("-k", "--top-k", type=int, default=None)
    activate.add_argument("--threshold", type=float, default=None)

    subparsers.add_parser("consolidate", help="Run the offline sleep phase")
    subparsers.add_parser("schema", help="Print the reasoning gene JSON schema")
    subparsers.add_parser("stats", help="Print RLD library stats")

    args = parser.parse_args()
    rld = RecursiveLatentDNA(Path(args.storage))

    if args.command == "observe":
        trajectory = rld.observe(
            args.task,
            states=args.state,
            actions=args.action,
            final_answer=args.answer,
            success=not args.failed,
            utility=args.utility,
            tools_used=args.tool,
        )
        rld.save()
        print(json.dumps({"trajectory_id": trajectory.id, **rld.stats()}, ensure_ascii=False, indent=2))
    elif args.command == "activate":
        context = rld.active_context(args.query, threshold=args.threshold, top_k=args.top_k)
        print(context.context_text)
    elif args.command == "consolidate":
        report = rld.consolidate()
        rld.save()
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    elif args.command == "stats":
        print(json.dumps(rld.stats(), ensure_ascii=False, indent=2))
    elif args.command == "schema":
        from rld import GENE_SCHEMA

        print(json.dumps(GENE_SCHEMA, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
