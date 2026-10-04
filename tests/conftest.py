import os
import shutil
import random
import pytest
import db


@pytest.fixture(scope="session", autouse=True)
def configure_worker_db(tmp_path_factory, worker_id):
    """
    Ensures that test workers (both parallel xdist workers and single-process master)
    operate on their own isolated SQLite database file.
    This prevents database lock contention, cross-test pollution, and accidental
    modification of the production hikayat.db.
    """
    if worker_id == "master":
        master_tmp = tmp_path_factory.mktemp("db_master")
        worker_db_path = str(master_tmp / "hikayat_master.db")
    else:
        # In xdist, worker_id is 'gw0', 'gw1', 'gw2', etc.
        worker_tmp = tmp_path_factory.mktemp(f"db_{worker_id}")
        worker_db_path = str(worker_tmp / "hikayat_worker.db")

    # Point database path to the isolated temporary DB file
    db.DB_PATH = worker_db_path
    db.init_db()

    # Apply fast in-memory SQLite pragmas for tests on Windows
    try:
        with db.get_conn() as conn:
            conn.execute("PRAGMA synchronous = OFF;")
            conn.execute("PRAGMA temp_store = MEMORY;")
            conn.execute("PRAGMA cache_size = -64000;")
    except Exception:
        pass

    yield worker_db_path

    if hasattr(db, "close_all_connections"):
        db.close_all_connections()


@pytest.fixture(autouse=True)
def mock_llm_embeddings(monkeypatch):
    """Prevent live network calls and retry backoffs in llm_client.get_embedding during tests."""
    import llm_client

    async def _fast_dummy_embedding(text: str) -> list[float]:
        return []

    monkeypatch.setattr(llm_client, "get_embedding", _fast_dummy_embedding)

    async def _blocked_live_completion(*args, **kwargs):
        raise RuntimeError(
            "Unmocked live LLM HTTP call blocked by conftest.py! "
            "Mock call_llm_json / call_llm_json_stream or client.chat.completions.create in this test."
        )

    if getattr(llm_client, "_client", None) is not None:
        monkeypatch.setattr(llm_client._client.chat.completions, "create", _blocked_live_completion)
    if getattr(llm_client, "_nsfw_client", None) is not None:
        monkeypatch.setattr(llm_client._nsfw_client.chat.completions, "create", _blocked_live_completion)


def pytest_collection_modifyitems(config, items):
    """Auto-classify unmarked tests so marker filtering (-m unit, -m integration, -m api) covers all 158 test files."""
    known_markers = {"unit", "integration", "api", "contract", "slow"}
    for item in items:
        existing = {m.name for m in item.iter_markers()}
        if not (existing & known_markers):
            fspath = str(getattr(item, "fspath", "")).lower()
            if "web_api" in fspath:
                item.add_marker(pytest.mark.api)
            elif "contract" in fspath:
                item.add_marker(pytest.mark.contract)
            elif any(k in fspath for k in ("integration", "turn_service", "save_system", "world_forge", "memory_engine")):
                item.add_marker(pytest.mark.integration)
            else:
                item.add_marker(pytest.mark.unit)


@pytest.fixture(autouse=True)
def seed_test_randomness():
    """Ensures deterministic random seeds for all tests to prevent flakiness."""
    random.seed(42)


@pytest.fixture(autouse=True)
def close_db_connections_after_test(configure_worker_db):
    """Close only ad-hoc temporary DB connections created by individual tests, keeping the main worker DB pool warm."""
    yield
    worker_db_path = configure_worker_db
    db.DB_PATH = worker_db_path
    if hasattr(db, "core") and hasattr(db.core, "_POOL"):
        with db.core._POOL_LOCK:
            extra_paths = [p for p in db.core._POOL if p != worker_db_path]
            for path in extra_paths:
                q = db.core._POOL.pop(path, None)
                if q is not None:
                    while not q.empty():
                        try:
                            q.get_nowait().close()
                        except Exception:
                            break

