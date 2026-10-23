import pytest
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import db
import mechanics.social.genealogy as genealogy


def test_concurrent_create_household_race_condition():
    """Verify db.create_household handles concurrent inserts for the same session and key without IntegrityError."""
    session_id = 88776655
    household_key = f"concurrent_test_hh_{session_id}"

    try:
        # Clean up any existing records
        with db.get_conn() as conn:
            conn.execute("DELETE FROM households WHERE session_id = ?", (session_id,))

        def _worker(idx):
            return db.create_household(
                session_id=session_id,
                household_key=household_key,
                surname="Sterling",
                residence_location="Sterling Estate"
            )

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(_worker, range(16)))

        first_id = results[0]
        assert first_id > 0, "Household ID should be a positive integer"
        # All concurrent threads must return the exact same household ID
        assert all(hh_id == first_id for hh_id in results), "All threads must return the same household ID"

        # Verify only 1 row was created in SQLite
        with db.get_conn() as conn:
            row_count = conn.execute(
                "SELECT count(*) as cnt FROM households WHERE session_id = ? AND household_key = ?",
                (session_id, household_key)
            ).fetchone()["cnt"]
            assert row_count == 1

    finally:
        with db.get_conn() as conn:
            conn.execute("DELETE FROM households WHERE session_id = ?", (session_id,))


def test_concurrent_get_or_create_household():
    """Verify genealogy.get_or_create_household is idempotent and safe under concurrent calls."""
    session_id = 88776656
    try:
        with db.get_conn() as conn:
            conn.execute("DELETE FROM households WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (session_id,))

        contact = {
            "id": 991122,
            "npc_id": "sofia_anderson",
            "name": "Sofia Anderson",
            "session_id": session_id,
        }

        def _worker(idx):
            return genealogy.get_or_create_household(
                session_id, "Anderson", contact=contact, scenario="high_school_drama"
            )

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(_worker, range(16)))

        first_id = results[0]["id"]
        assert first_id > 0
        assert all(h["id"] == first_id for h in results)

    finally:
        with db.get_conn() as conn:
            conn.execute("DELETE FROM households WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (session_id,))
