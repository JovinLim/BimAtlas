#!/usr/bin/env python3
"""Migrate legacy flat filter_sets.filters to canonical tree shape.

Run from apps/api with: python scripts/migrate_filter_sets_to_tree.py

Uses BIMATLAS_DB_* env vars. Dry-run by default; pass --apply to write.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure src is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import psycopg2
from src.schema.filter_tree import canonicalize_filters, is_legacy_filters


def get_db_config():
    return {
        "host": os.getenv("BIMATLAS_DB_HOST", "localhost"),
        "port": int(os.getenv("BIMATLAS_DB_PORT", "5432")),
        "dbname": os.getenv("BIMATLAS_DB_NAME", "bimatlas"),
        "user": os.getenv("BIMATLAS_DB_USER", "bimatlas"),
        "password": os.getenv("BIMATLAS_DB_PASSWORD", "bimatlas"),
    }


def main():
    import json
    apply = "--apply" in sys.argv
    conn = psycopg2.connect(**get_db_config())
    cur = conn.cursor()
    cur.execute(
        "SELECT filter_set_id, branch_id, name, logic, filters FROM filter_sets"
    )
    rows = cur.fetchall()
    migrated = 0
    skipped = 0
    errors = []

    for row in rows:
        fs_id, branch_id, name, logic, filters = row
        if not is_legacy_filters(filters):
            skipped += 1
            continue
        try:
            tree = canonicalize_filters(filters, logic)
            if apply:
                cur.execute(
                    "UPDATE filter_sets SET filters = %s::jsonb WHERE filter_set_id = %s",
                    (json.dumps(tree), fs_id),
                )
            migrated += 1
            print(f"  {name} ({fs_id}): legacy -> tree")
        except Exception as e:
            errors.append((name, str(e)))
            print(f"  {name} ({fs_id}): ERROR {e}")

    if apply:
        conn.commit()
        print(f"\nApplied: {migrated} migrated, {skipped} already tree")
    else:
        print(f"\nDry-run: {migrated} would migrate, {skipped} already tree")
        print("Pass --apply to write changes")

    if errors:
        print(f"\nErrors: {len(errors)}")
        for name, msg in errors:
            print(f"  {name}: {msg}")

    cur.close()
    conn.close()
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
