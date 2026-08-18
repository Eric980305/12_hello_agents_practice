#!/usr/bin/env python
"""Delete expert-platform data from SQLite, files, and Qdrant."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from expert_platform.backend.app.admin_deletion import (  # noqa: E402
    AdminDeleteError,
    DeletePlan,
    DeleteTarget,
    build_plan,
    default_qdrant,
    default_settings,
    execute_delete,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)

    user_parser = subparsers.add_parser("user", help="Delete users and all owned data.")
    user_parser.add_argument("--user-id", nargs="+", required=True)

    expert_parser = subparsers.add_parser("expert", help="Delete private experts.")
    expert_parser.add_argument("--user-id", required=True)
    expert_parser.add_argument("--expert-id", nargs="+", required=True)

    document_parser = subparsers.add_parser("document", help="Delete expert documents.")
    document_parser.add_argument("--user-id", required=True)
    document_parser.add_argument("--expert-id", required=True)
    document_parser.add_argument("--document-id", nargs="+", required=True)

    for command in (user_parser, expert_parser, document_parser):
        command.add_argument(
            "--execute",
            action="store_true",
            help="Perform deletion. Without this flag the command is a dry run.",
        )
        command.add_argument(
            "--yes",
            action="store_true",
            help="Skip the interactive ID confirmation; requires --execute.",
        )
    return parser


def _unique(values: list[str], name: str) -> list[str]:
    if len(values) != len(set(values)):
        raise AdminDeleteError(f"duplicate {name} values are not allowed.")
    return values


def targets_from_args(args: argparse.Namespace) -> list[DeleteTarget]:
    if args.action == "user":
        return [
            DeleteTarget(action="user", user_id=user_id)
            for user_id in _unique(args.user_id, "user_id")
        ]
    if args.action == "expert":
        return [
            DeleteTarget(action="expert", user_id=args.user_id, expert_id=expert_id)
            for expert_id in _unique(args.expert_id, "expert_id")
        ]
    return [
        DeleteTarget(
            action="document",
            user_id=args.user_id,
            expert_id=args.expert_id,
            document_id=document_id,
        )
        for document_id in _unique(args.document_id, "document_id")
    ]


def confirmation_text(targets: list[DeleteTarget]) -> str:
    if len(targets) > 1:
        return f"DELETE {len(targets)}"
    target = targets[0]
    return target.document_id or target.expert_id or target.user_id


def main(argv: list[str] | None = None) -> int:
    load_dotenv(WORKSPACE_ROOT / ".env", override=False)
    args = build_parser().parse_args(argv)
    if args.yes and not args.execute:
        raise AdminDeleteError("--yes may only be used together with --execute.")
    settings = default_settings()
    qdrant = default_qdrant(settings)
    targets = targets_from_args(args)
    plans = [build_plan(settings, target, qdrant) for target in targets]
    print(
        json.dumps(
            {
                "target_count": len(plans),
                "targets": [plan.to_dict() for plan in plans],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not args.execute:
        print("DRY RUN: no data was deleted. Add --execute after stopping the backend.")
        return 0

    expected = confirmation_text(targets)
    if not args.yes:
        entered = input(f"Type '{expected}' to confirm permanent deletion: ").strip()
        if entered != expected:
            print("Confirmation did not match; nothing was deleted.", file=sys.stderr)
            return 2
    deleted: list[DeletePlan] = []
    for target in targets:
        try:
            deleted.append(execute_delete(settings, target, qdrant))
        except Exception as error:
            reason = str(error) if isinstance(error, AdminDeleteError) else type(error).__name__
            raise AdminDeleteError(
                f"batch stopped after deleting {len(deleted)} of {len(targets)} targets; "
                f"previous targets remain deleted. Failure: {reason}"
            ) from error
    print(
        json.dumps(
            {"deleted_count": len(deleted), "deleted": [plan.to_dict() for plan in deleted]},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AdminDeleteError, sqlite3.Error, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    except Exception as error:
        print(
            f"ERROR: {type(error).__name__}; no deletion success was reported.",
            file=sys.stderr,
        )
        raise SystemExit(1) from error
