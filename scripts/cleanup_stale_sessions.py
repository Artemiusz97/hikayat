#!/usr/bin/env python3
"""
Hikayat Database Maintenance: Stale & Orphaned Session Cleanup
Safely removes:
  1. Orphaned ghost sessions where the player character was deleted.
  2. Concluded sessions with status='finished' (from /adventure leave or starting new runs).

SAFETY GUARANTEE:
  Never touches active player characters, unspent stat points, inventory,
  or active ongoing sessions.

Usage:
  python scripts/cleanup_stale_sessions.py             # Dry-run inspection (no changes)
  python scripts/cleanup_stale_sessions.py --execute   # Perform cleanup
  python scripts/cleanup_stale_sessions.py --execute --vacuum  # Clean up and reclaim disk space
"""
import os
import sys
import argparse

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
from config import DB_PATH


def format_bytes(size_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


def main():
    parser = argparse.ArgumentParser(description="Clean up orphaned ghost sessions and vacuum Hikayat DB.")
    parser.add_argument("--execute", action="store_true", help="Execute the deletion (default is dry-run)")
    parser.add_argument("--vacuum", action="store_true", help="Run VACUUM to reclaim disk space after pruning")
    args = parser.parse_args()

    dry_run = not args.execute

    if not os.path.exists(DB_PATH):
        print(f"Error: Database file not found at {DB_PATH}")
        sys.exit(1)

    initial_size = os.path.getsize(DB_PATH)

    print("=" * 70)
    print("  HIKAYAT DATABASE MAINTENANCE & SESSION CLEANUP")
    print("=" * 70)
    print(f"Database Path: {DB_PATH}")
    print(f"Initial Size:  {format_bytes(initial_size)}")
    print(f"Mode:          {'DRY-RUN (Preview Only - No Changes Made)' if dry_run else 'EXECUTE (Applying Deletions)'}")
    print("-" * 70)

    # Run pruning
    results = db.prune_orphaned_and_finished_sessions(dry_run=dry_run)
    identified = results["sessions_identified"]

    print(f"\n[+] Stale Sessions Identified: {identified}")
    if identified == 0:
        print("    No orphaned or finished sessions found. Database is already clean!")
    else:
        print("\nRecords to be purged" if dry_run else "\nRecords successfully purged:")
        print(f"  {'Table':<25} {'Count':>10}")
        print("  " + "-" * 37)
        for tbl, cnt in results["deleted_by_table"].items():
            if cnt > 0:
                print(f"  {tbl:<25} {cnt:>10,}")

    if not dry_run and args.vacuum:
        print("\n[+] Running SQLite VACUUM to rebuild database and reclaim disk space...")
        db.vacuum_database()
        final_size = os.path.getsize(DB_PATH)
        reclaimed = initial_size - final_size
        print(f"    Size Before: {format_bytes(initial_size)}")
        print(f"    Size After:  {format_bytes(final_size)}")
        print(f"    Reclaimed:   {format_bytes(reclaimed)} ({reclaimed / initial_size * 100:.1f}%)")
    elif dry_run:
        print("\n[!] To execute these deletions and shrink the database, run:")
        print("    python scripts/cleanup_stale_sessions.py --execute --vacuum\n")
    else:
        print("\n[*] Deletions applied. Run with --vacuum to shrink the .db file on disk.\n")


if __name__ == "__main__":
    main()
