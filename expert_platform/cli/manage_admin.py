#!/usr/bin/env python
"""Create and manage local administrator accounts for the expert platform."""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Sequence
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

from expert_platform.backend.app.config import default_settings
from expert_platform.backend.app.services import SessionService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create a new account and grant admin access.")
    create.add_argument("username", help="New administrator username.")

    grant = subparsers.add_parser("grant", help="Grant admin access to an existing account.")
    grant.add_argument("username", help="Existing username.")

    revoke = subparsers.add_parser("revoke", help="Revoke admin access and all sessions.")
    revoke.add_argument("username", help="Existing administrator username.")

    subparsers.add_parser("list", help="List administrator identities without credentials.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv(WORKSPACE_ROOT / ".env")
    sessions = SessionService(default_settings())

    try:
        if args.command == "create":
            password = getpass.getpass("New admin password: ")
            confirmation = getpass.getpass("Confirm password: ")
            if password != confirmation:
                raise ValueError("两次输入的密码不一致。")
            if len(password) < 12:
                raise ValueError("管理员密码至少需要 12 位。")
            sessions.users.register(args.username, password)
            user = sessions.grant_admin(args.username)
            print(f"Created administrator: {user['username']} ({user['user_id']})")
        elif args.command == "grant":
            user = sessions.grant_admin(args.username)
            print(f"Granted administrator: {user['username']} ({user['user_id']})")
        elif args.command == "revoke":
            user = sessions.revoke_admin(args.username)
            print(f"Revoked administrator and sessions: {user['username']} ({user['user_id']})")
        else:
            for user in sessions.list_admins():
                print(f"{user['username']}\t{user['user_id']}\t{user['granted_at']}")
    except ValueError as error:
        print(f"Error: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
