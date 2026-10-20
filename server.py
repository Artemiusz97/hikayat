"""
Hikayat Web API & WebSocket Server Entrypoint.
Routes are modularized into FastAPI APIRouter modules under `api/`.
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if sys.platform.startswith("win"):
    # Windows IOCP Proactor resilience patch:
    # Prevents client disconnections / connection resets (WinError 64 / 10054)
    # from crashing uvicorn's socket accept loop.
    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport, BaseProactorEventLoop

        _orig_call_conn_lost = _ProactorBasePipeTransport._call_connection_lost
        def _safe_call_conn_lost(self, exc):
            try:
                _orig_call_conn_lost(self, exc)
            except (ConnectionResetError, OSError):
                pass
        _ProactorBasePipeTransport._call_connection_lost = _safe_call_conn_lost

        _orig_start_serving = BaseProactorEventLoop._start_serving
        def _resilient_start_serving(self, protocol_factory, sock, sslcontext=None, server=None, backlog=100, ssl_handshake_timeout=None, ssl_shutdown_timeout=None):
            def resilient_loop(f=None):
                try:
                    if f is not None:
                        try:
                            conn, addr = f.result()
                        except OSError:
                            # Client aborted / reset connection before handshake (e.g. WinError 64)
                            if not self.is_closed():
                                f = self._proactor.accept(sock)
                                f.add_done_callback(resilient_loop)
                            return
                        protocol = protocol_factory()
                        if sslcontext is not None:
                            self._make_ssl_transport(conn, protocol, sslcontext, server_side=True, extra={'peername': addr}, server=server, ssl_handshake_timeout=ssl_handshake_timeout, ssl_shutdown_timeout=ssl_shutdown_timeout)
                        else:
                            self._make_socket_transport(conn, protocol, extra={'peername': addr}, server=server)
                    if self.is_closed():
                        return
                    f = self._proactor.accept(sock)
                    f.add_done_callback(resilient_loop)
                except Exception:
                    if not self.is_closed():
                        try:
                            f = self._proactor.accept(sock)
                            f.add_done_callback(resilient_loop)
                        except Exception:
                            pass
            f = self._proactor.accept(sock)
            f.add_done_callback(resilient_loop)
        BaseProactorEventLoop._start_serving = _resilient_start_serving
    except Exception:
        pass


import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import config
import db
import game_engine
import skill_check
import scenario_data
import character_data as cd
from services.turn_service import TurnService
from mechanics.system.concurrency import distributed_session_lock, distributed_user_lock

from api.deps import (
    ConnectionManager,
    manager,
    logger,
    _serializable_action,
    enrich_choices_with_odds,
    enrich_session_party_members,
    GuestAuthRequest,
    DiscordAuthRequest,
    CharacterCreateRequest,
    CharacterSwitchRequest,
    SpendStatPointRequest,
    EquipRequest,
    UnequipRequest,
    ItemDropRequest,
    ItemUseRequest,
    JoinAdventureRequest,
    StartAdventureRequest,
    ActionRequest,
    MerchantBuyRequest,
    MerchantSellRequest,
    PhoneMessageRequest,
    SaveSlotRequest,
    LoadSlotRequest,
    SettingsUpdateRequest,
    DebugUpdateRequest,
)
from api import (
    auth_characters_router,
    inventory_merchant_router,
    adventure_router,
    codex_phone_router,
    settings_ws_router,
)

import argparse
import asyncio
import os
import sys
from contextlib import asynccontextmanager
import llm_client
from bin import tunnel

logging.basicConfig(level=logging.INFO)

# Ensure database is initialized and schema migrations are applied
db.init_db()


def _is_share_requested() -> bool:
    if "--share" in sys.argv:
        return True
    return os.getenv("HIKAYAT_SHARE", "").lower() in ("true", "1", "yes") or os.getenv("SHARE", "").lower() in ("true", "1", "yes")


def _get_share_provider() -> str:
    for i, arg in enumerate(sys.argv):
        if arg == "--share-provider" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if arg.startswith("--share-provider="):
            return arg.split("=", 1)[1]
    return os.getenv("HIKAYAT_SHARE_PROVIDER") or os.getenv("SHARE_PROVIDER") or "cloudflare"


def _get_port() -> int:
    for i, arg in enumerate(sys.argv):
        if arg in ("--port", "-p") and i + 1 < len(sys.argv):
            try:
                return int(sys.argv[i + 1])
            except ValueError:
                pass
        if arg.startswith("--port="):
            try:
                return int(arg.split("=", 1)[1])
            except ValueError:
                pass
    return int(os.getenv("PORT", "8000"))


def _launch_tunnel_sync(port: int, provider: str):
    try:
        pub_url = tunnel.start_tunnel(port=port, provider=provider)
        print("\n" + "=" * 72)
        print(f"  * Hikayat Local URL:   http://localhost:{port}")
        print(f"  * Hikayat Public URL:  {pub_url}")
        print("=" * 72)
        print("  Share this public link with anyone! They can join from any phone,")
        print("  PC, or network without needing to be on the same Wi-Fi.\n")
    except Exception as e:
        print(f"\n[WARNING] Failed to establish public tunnel: {e}\n")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    try:
        snapshot_path = db.create_database_snapshot(tag="server_startup")
        print(f"[Database Snapshot] Automatic backup created at: {snapshot_path}")
    except Exception as e:
        print(f"[Database Snapshot] Failed to create startup snapshot (non-fatal): {e}")
    if _is_share_requested():
        port = _get_port()
        provider = _get_share_provider()
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _launch_tunnel_sync, port, provider)

    # Pre-warm LLM model capability cache in background so turns have zero parameter mismatches
    asyncio.create_task(llm_client.probe_all_configured_models())

    yield

    tunnel.stop_tunnel()
    await llm_client.close_llm_clients()


app = FastAPI(title="Hikayat Web API", version=config.APP_VERSION, lifespan=lifespan)

# Register domain routers
app.include_router(auth_characters_router)
app.include_router(inventory_merchant_router)
app.include_router(adventure_router)
app.include_router(codex_phone_router)
app.include_router(settings_ws_router)


@app.get("/api/server/public-url")
async def get_server_public_url():
    """Returns the active public shareable link if enabled."""
    pub_url = tunnel.get_public_url()
    return {
        "is_shared": bool(pub_url),
        "public_url": pub_url,
    }


from starlette.websockets import WebSocketClose

class SafeStaticFiles(StaticFiles):
    """StaticFiles wrapper that gracefully rejects WebSocket requests instead of raising AssertionError."""
    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            await WebSocketClose()(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


# Serve locally saved generated scene images (shared across Discord & WebUI)
app.mount("/images", StaticFiles(directory=config.GENERATED_IMAGES_DIR), name="generated_images")

# Serve web frontend static bundle
app.mount("/", SafeStaticFiles(directory="web/dist", html=True), name="web")

if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="Hikayat Web RPG Server")
    parser.add_argument("--host", type=str, default=os.getenv("HOST", "0.0.0.0"), help="Host IP to bind to")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")), help="Port number")
    parser.add_argument("--share", action="store_true", help="Generate a public Automatic1111/Forge style link")
    parser.add_argument("--share-provider", type=str, default="cloudflare", choices=["cloudflare", "serveo", "localhost.run", "pinggy"], help="Tunnel provider")
    parser.add_argument("--no-reload", action="store_true", help="Disable auto-reload")
    args, _ = parser.parse_known_args()

    if args.share:
        os.environ["HIKAYAT_SHARE"] = "true"
        os.environ["HIKAYAT_SHARE_PROVIDER"] = args.share_provider

    reload_flag = not args.no_reload
    print(f"Starting Hikayat server on http://{args.host}:{args.port} (reload={reload_flag})...")
    try:
        uvicorn.run("server:app", host=args.host, port=args.port, reload=reload_flag)
    except OSError as err:
        win_err = getattr(err, "winerror", None)
        err_str = str(err).lower()
        if win_err in (10013, 10048) or "access permissions" in err_str or "already in use" in err_str:
            print("\n" + "=" * 72)
            print(f" [ERROR] Port {args.port} is already in use by an existing process!")
            print(f"   * If Hikayat is already running in the background, open:")
            print(f"     http://localhost:{args.port}")
            print(f"   * To launch on a different port, run:")
            print(f"     python server.py --port {args.port + 1}")
            print("=" * 72 + "\n")
            sys.exit(1)
        raise

