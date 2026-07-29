#!/usr/bin/env python
"""Initialize the ThingList database schema.

This script uses the application's configured database connection and creates
all SQLAlchemy tables for the current models.

Usage:
    .venv\\Scripts\\python.exe db_init.py
    .venv\\Scripts\\python.exe db_init.py --drop
"""

from __future__ import annotations

import argparse

from app import app, db


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize the ThingList database schema.")
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop all existing tables before creating the schema.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    with app.app_context():
        if args.drop:
            print("Dropping existing tables...")
            db.drop_all()

        print("Creating database tables...")
        db.create_all()
        db.session.commit()

    print("Database initialization complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())