#!/usr/bin/env python3
"""Check filter_sets.filters for malformed nodes, invalid depth, invalid mode/operator.

Run from apps/api with: python scripts/check_filter_tree_integrity.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import psycopg2
from src.schema.filter_tree import is_legacy_filters, validate_filter_tree, canonicalize_filters


def get_db_config():
    return {
        "host": os.getenv("BIMATLAS_DB_HOST", "localhost"),
        "port": int(os.getenv("BIMATLAS_DB_PORT", "5432")),
        "dbname": os.getenv("BIMATLAS_DB_NAME", "bimatlas"),
        "user": os.getenv("BIMATLAS_DB_USER", "bimatlas"),
        "password": os.getenv("BIMATLAS_DB_PASSWORD", "bimatlas"),
    }


def main():
    conn = psycopg2.connect(**get_db_config())
    cur = conn.cursor()
    cur.execute(
        "SELECT filter_set_id, branch_id, name, logic, filters FROM filter_sets"
    )
    rows = cur.fetchall()
    issues = []
    legacy_count = 0

    for row in rows:
        fs_id, branch_id, name, logic, filters = row
        if is_legacy_filters(filters):
            legacy_count += 1
            tree = canonicalize_filters(filters, logic)
        else:
            tree = filters if isinstance(filters, dict) else {}
        errs = validate_filter_tree(tree)
        if errs:
            issues.append((name, fs_id, errs))

    cur.close()
    conn.close()

    if legacy_count:
        print(f"Legacy flat payloads: {legacy_count} (run migrate_filter_sets_to_tree.py to canonicalize)")
    if issues:
        print(f"\nIntegrity issues: {len(issues)}")
        for name, fs_id, errs in issues:
            print(f"  {name} ({fs_id}):")
            for e in errs:
                print(f"    - {e}")
        return 1
    print("All filter sets pass integrity check.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
