"""
Automatic1111 / SD-Forge style link sharing for Hikayat.
Generates a temporary public HTTPS/WSS link via Cloudflare Tunnel (trycloudflare.com)
or SSH reverse tunnel (pinggy / localhost.run), or configures private remote access
over Tailscale.
"""
from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Optional

_active_process: Optional[subprocess.Popen] = None
_active_provider: Optional[str] = None
_public_url: Optional[str] = None
_lock = threading.Lock()


def get_public_url() -> Optional[str]:
    """Returns the currently active public URL if link sharing is enabled."""
    global _public_url
    return _public_url


def get_active_provider() -> Optional[str]:
    """Returns the currently active tunnel provider name, if any."""
    return _active_provider


def _get_bin_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def ensure_cloudflared() -> str:
    """
    Finds existing cloudflared binary or automatically downloads the official release.
    Returns path to cloudflared executable.
    """
    # 1. Check if cloudflared is installed system-wide in PATH
    found = shutil.which("cloudflared")
    if found:
        return found

    bin_dir = _get_bin_dir()
    is_windows = sys.platform.startswith("win")
    binary_name = "cloudflared.exe" if is_windows else "cloudflared"
    local_path = os.path.join(bin_dir, binary_name)

    if os.path.exists(local_path) and os.path.getsize(local_path) > 1000000:
        return local_path

    # 2. Download from official Cloudflare releases
    print("[Hikayat] Downloading Cloudflare Tunnel binary (one-time setup for link sharing)...")
    if is_windows:
        download_url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    elif sys.platform == "darwin":
        download_url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64"
    else:
        download_url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"

    # Try curl first if available (reliable SSL on Windows)
    curl_bin = shutil.which("curl")
    if curl_bin:
        try:
            res = subprocess.run(
                [curl_bin, "-L", "--fail", "--show-error", "-o", local_path, download_url],
                check=True,
                capture_output=True,
                text=True
            )
            if os.path.exists(local_path) and os.path.getsize(local_path) > 1000000:
                if not is_windows:
                    os.chmod(local_path, 0o755)
                return local_path
        except Exception as e:
            print(f"curl download failed: {e}, falling back to Python downloader...")

    # Fallback to python httpx with truststore
    try:
        try:
            import truststore
            truststore.inject_into_ssl()
        except ImportError:
            pass

        import httpx
        with httpx.Client(follow_redirects=True, timeout=60.0) as client:
            with client.stream("GET", download_url) as response:
                response.raise_for_status()
                with open(local_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=65536):
                        f.write(chunk)

        if not is_windows:
            os.chmod(local_path, 0o755)

        return local_path
    except Exception as err:
        raise RuntimeError(
            f"Failed to automatically download cloudflared: {err}. "
            f"Please download cloudflared manually from https://github.com/cloudflare/cloudflared/releases and place it in '{local_path}'."
        )


def _drain_stream_continuously(stream, pattern=None, on_match=None):
    """
    Continuously drains a process output stream until EOF.
    Optionally extracts a regex pattern (e.g. public URL) on first match.
    Crucial on Windows to prevent OS anonymous pipe buffers (4KB) from filling
    up and freezing the subprocess during active network forwarding.
    """
    if not stream:
        return
    try:
        for line in iter(stream.readline, ''):
            if not line:
                break
            if pattern and on_match:
                match = pattern.search(line)
                if match:
                    on_match(match.group(0))
    except Exception:
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _start_cloudflare_tunnel(port: int = 8000, timeout: float = 25.0) -> str:
    global _active_process, _public_url
    cf_bin = ensure_cloudflared()

    cmd = [cf_bin, "tunnel", "--edge-ip-version", "4", "--url", f"http://127.0.0.1:{port}"]

    creationflags = 0
    if sys.platform.startswith("win"):
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        creationflags=creationflags
    )
    _active_process = proc

    url_found = None
    start_time = time.time()
    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

    def on_match(u):
        nonlocal url_found
        if not url_found:
            url_found = u

    t_out = threading.Thread(target=_drain_stream_continuously, args=(proc.stdout, url_pattern, on_match), daemon=True)
    t_out.start()
    t_err = threading.Thread(target=_drain_stream_continuously, args=(proc.stderr, url_pattern, on_match), daemon=True)
    t_err.start()

    while time.time() - start_time < timeout:
        if url_found:
            break
        if proc.poll() is not None:
            raise RuntimeError(f"Cloudflare tunnel exited prematurely with code {proc.returncode}.")
        time.sleep(0.2)

    if not url_found:
        raise TimeoutError(f"Cloudflare tunnel timed out after {timeout} seconds without generating a public link.")

    _public_url = url_found
    return url_found


def _start_pinggy_tunnel(port: int = 8000, timeout: float = 20.0) -> str:
    """Zero-install SSH tunnel fallback using OpenSSH client."""
    global _active_process, _public_url
    ssh_bin = shutil.which("ssh") or "ssh"

    cmd = [
        ssh_bin,
        "-p", "443",
        "-R", f"0:127.0.0.1:{port}",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=3",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "TCPKeepAlive=yes",
        "a.pinggy.io"
    ]

    creationflags = 0
    if sys.platform.startswith("win"):
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        creationflags=creationflags
    )
    _active_process = proc

    url_found = None
    start_time = time.time()
    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.(?:free\.pinggy\.link|a\.pinggy\.io)")

    def on_match(u):
        nonlocal url_found
        if not url_found:
            url_found = u

    t_out = threading.Thread(target=_drain_stream_continuously, args=(proc.stdout, url_pattern, on_match), daemon=True)
    t_out.start()
    t_err = threading.Thread(target=_drain_stream_continuously, args=(proc.stderr, url_pattern, on_match), daemon=True)
    t_err.start()

    while time.time() - start_time < timeout:
        if url_found:
            break
        if proc.poll() is not None:
            break
        time.sleep(0.2)

    if not url_found:
        raise TimeoutError("Pinggy SSH tunnel timed out.")

    _public_url = url_found
    return url_found


def _start_localhost_run_tunnel(port: int = 8000, timeout: float = 20.0) -> str:
    """Zero-install SSH tunnel fallback using localhost.run."""
    global _active_process, _public_url
    ssh_bin = shutil.which("ssh") or "ssh"

    cmd = [
        ssh_bin,
        "-T",
        "-R", f"80:127.0.0.1:{port}",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=3",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "TCPKeepAlive=yes",
        "nokey@localhost.run"
    ]

    creationflags = 0
    if sys.platform.startswith("win"):
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        creationflags=creationflags
    )
    _active_process = proc

    url_found = None
    start_time = time.time()
    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.lhr\.life")

    def on_match(u):
        nonlocal url_found
        if not url_found:
            url_found = u

    t_out = threading.Thread(target=_drain_stream_continuously, args=(proc.stdout, url_pattern, on_match), daemon=True)
    t_out.start()
    t_err = threading.Thread(target=_drain_stream_continuously, args=(proc.stderr, url_pattern, on_match), daemon=True)
    t_err.start()

    while time.time() - start_time < timeout:
        if url_found:
            break
        if proc.poll() is not None:
            break
        time.sleep(0.2)

    if not url_found:
        raise TimeoutError("localhost.run SSH tunnel timed out.")

    _public_url = url_found
    return url_found


def _start_serveo_tunnel(port: int = 8000, timeout: float = 20.0) -> str:
    """Zero-install SSH reverse tunnel via Serveo (serveo.net)."""
    global _active_process, _public_url
    ssh_bin = shutil.which("ssh") or "ssh"

    cmd = [
        ssh_bin,
        "-R", f"80:127.0.0.1:{port}",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=3",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "TCPKeepAlive=yes",
        "serveo.net"
    ]

    creationflags = 0
    if sys.platform.startswith("win"):
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        creationflags=creationflags
    )
    _active_process = proc

    url_found = None
    start_time = time.time()
    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.serveousercontent\.com")

    def on_match(u):
        nonlocal url_found
        if not url_found:
            url_found = u

    t_out = threading.Thread(target=_drain_stream_continuously, args=(proc.stdout, url_pattern, on_match), daemon=True)
    t_out.start()
    t_err = threading.Thread(target=_drain_stream_continuously, args=(proc.stderr, url_pattern, on_match), daemon=True)
    t_err.start()

    while time.time() - start_time < timeout:
        if url_found:
            break
        if proc.poll() is not None:
            break
        time.sleep(0.2)

    if not url_found:
        raise TimeoutError("Serveo SSH tunnel timed out.")

    _public_url = url_found
    return url_found


def ensure_tailscale() -> str:
    """Locate the installed Tailscale CLI binary without hardcoding user-specific paths."""
    found = shutil.which("tailscale")
    if found:
        return found

    candidates: list[str] = []
    if sys.platform.startswith("win"):
        prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        prog_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        candidates.append(os.path.join(prog_files, "Tailscale", "tailscale.exe"))
        candidates.append(os.path.join(prog_files_x86, "Tailscale", "tailscale.exe"))
        if local_appdata:
            candidates.append(os.path.join(local_appdata, "Tailscale", "tailscale.exe"))
    elif sys.platform == "darwin":
        candidates.extend([
            "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
            "/opt/homebrew/bin/tailscale",
            "/usr/local/bin/tailscale",
        ])
    else:
        candidates.extend([
            "/usr/bin/tailscale",
            "/usr/local/bin/tailscale",
        ])

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate

    raise RuntimeError(
        "Tailscale CLI not found. Install Tailscale from https://tailscale.com/download and sign in first."
    )


def _start_tailscale_tunnel(port: int = 8000, timeout: float = 15.0) -> str:
    """Resolve a private Tailscale URL (HTTPS via Serve if CertDomains enabled, else direct HTTP)."""
    global _active_process, _active_provider, _public_url
    ts_bin = ensure_tailscale()

    creationflags = 0
    if sys.platform.startswith("win"):
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    res = subprocess.run(
        [ts_bin, "status", "--json"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
        creationflags=creationflags,
    )
    if res.returncode != 0:
        detail = (res.stderr or res.stdout or "").strip()
        raise RuntimeError(f"Tailscale status check failed (code {res.returncode}): {detail}")

    data = json.loads(res.stdout or "{}")
    backend_state = str(data.get("BackendState") or "")
    if backend_state != "Running":
        raise RuntimeError(
            f"Tailscale is not connected (state: {backend_state or 'unknown'}). Open Tailscale and sign in first."
        )

    self_info = data.get("Self") or {}
    dns_name = str(self_info.get("DNSName") or "").strip().rstrip(".")
    ipv4_ips = [
        str(ip).strip()
        for ip in (self_info.get("TailscaleIPs") or [])
        if ip and ":" not in str(ip)
    ]
    cert_domains = [str(d).strip().rstrip(".") for d in (data.get("CertDomains") or []) if d]
    host_label = dns_name or (ipv4_ips[0] if ipv4_ips else "")
    if not host_label:
        raise RuntimeError("Tailscale is running, but no MagicDNS name or IPv4 address was found.")

    resolved_url = f"http://{host_label}:{port}"
    if dns_name and cert_domains:
        try:
            serve_res = subprocess.run(
                [ts_bin, "serve", "--bg", "--yes", str(port)],
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=timeout,
                creationflags=creationflags,
            )
            if serve_res.returncode == 0:
                resolved_url = f"https://{dns_name}"
                print(f"[TUNNEL] Tailscale Serve HTTPS active: {resolved_url} -> http://127.0.0.1:{port}")
            else:
                detail = (serve_res.stderr or serve_res.stdout or f"exit {serve_res.returncode}").strip()
                print(
                    f"[WARNING] Tailscale Serve HTTPS was unavailable ({detail}); "
                    f"falling back to direct tailnet HTTP: {resolved_url}"
                )
        except Exception as serve_err:
            print(
                f"[WARNING] Tailscale Serve HTTPS was unavailable ({serve_err}); "
                f"falling back to direct tailnet HTTP: {resolved_url}"
            )
    else:
        print(f"[TUNNEL] Tailscale direct URL ready: {resolved_url}")
        if ipv4_ips and ipv4_ips[0] != host_label:
            print(f"[TUNNEL] Tailscale IPv4 fallback:    http://{ipv4_ips[0]}:{port}")
        if dns_name:
            print(
                "[TUNNEL] Tip: Enable HTTPS Certificates in Tailscale Admin Console -> DNS "
                f"to auto-upgrade to https://{dns_name}."
            )

    _active_process = None
    _active_provider = "tailscale"
    _public_url = resolved_url
    return resolved_url


_supervisor_thread: Optional[threading.Thread] = None
_supervisor_running: bool = False


def _supervise_tunnel(port: int, provider: str):
    """Background monitor that automatically resurrects dead tunnel connections."""
    global _active_process, _public_url, _supervisor_running
    while _supervisor_running:
        time.sleep(3)
        if not _supervisor_running:
            break
        if _active_process and _active_process.poll() is not None:
            exit_code = _active_process.poll()
            print(f"\n[TUNNEL] Background tunnel process disconnected (code {exit_code}). Automatically reconnecting...")
            time.sleep(2)
            if not _supervisor_running:
                break
            try:
                with _lock:
                    if provider == "serveo":
                        new_url = _start_serveo_tunnel(port)
                    elif provider == "localhost.run":
                        new_url = _start_localhost_run_tunnel(port)
                    elif provider == "pinggy":
                        new_url = _start_pinggy_tunnel(port)
                    else:
                        new_url = _start_cloudflare_tunnel(port)
                print(f"[TUNNEL] Reconnection successful! Active Public URL: {new_url}\n")
            except Exception as e:
                print(f"[TUNNEL] Reconnection failed: {e}. Will retry in 5s...\n")


def start_tunnel(port: int = 8000, provider: str = "cloudflare") -> str:
    """
    Starts a public tunnel or private Tailscale link for the given local port.
    Returns the accessible URL.
    """
    global _public_url, _active_provider, _supervisor_thread, _supervisor_running
    with _lock:
        if _public_url and (
            _active_provider == "tailscale"
            or (_active_process and _active_process.poll() is None)
        ):
            return _public_url

        provider = provider.lower().strip()
        if provider == "tailscale":
            print("[TUNNEL] Establishing private Tailscale access...")
            url = _start_tailscale_tunnel(port)
            return url

        print(f"[TUNNEL] Establishing public link sharing using {provider.capitalize()}...")

        if provider == "serveo":
            try:
                url = _start_serveo_tunnel(port)
            except Exception as e:
                print(f"[WARNING] Serveo tunnel failed: {e}. Trying Cloudflare tunnel...")
                url = _start_cloudflare_tunnel(port)
        elif provider == "localhost.run":
            try:
                url = _start_localhost_run_tunnel(port)
            except Exception as e:
                print(f"[WARNING] localhost.run tunnel failed: {e}. Trying Serveo tunnel...")
                url = _start_serveo_tunnel(port)
        elif provider == "pinggy":
            try:
                url = _start_pinggy_tunnel(port)
            except Exception as e:
                print(f"[WARNING] Pinggy tunnel failed: {e}. Trying Serveo tunnel...")
                url = _start_serveo_tunnel(port)
        else:
            # Default: try Cloudflare, fallback to Serveo, then localhost.run, then Pinggy
            try:
                url = _start_cloudflare_tunnel(port)
            except Exception as e:
                print(f"[WARNING] Cloudflare tunnel failed: {e}. Attempting Serveo fallback...")
                try:
                    url = _start_serveo_tunnel(port)
                except Exception as e2:
                    print(f"[WARNING] Serveo failed: {e2}. Attempting localhost.run fallback...")
                    try:
                        url = _start_localhost_run_tunnel(port)
                    except Exception as e3:
                        print(f"[WARNING] localhost.run failed: {e3}. Attempting Pinggy fallback...")
                        try:
                            url = _start_pinggy_tunnel(port)
                        except Exception as e4:
                            raise RuntimeError(f"All tunnel providers failed: Cloudflare ({e}), Serveo ({e2}), localhost.run ({e3}), Pinggy ({e4})")

        _active_provider = provider

        # Start supervisor thread if not already running
        if not _supervisor_running:
            _supervisor_running = True
            _supervisor_thread = threading.Thread(
                target=_supervise_tunnel,
                args=(port, provider),
                daemon=True
            )
            _supervisor_thread.start()

        return url


def stop_tunnel():
    """Terminates the running tunnel process and supervisor."""
    global _supervisor_running, _active_process, _active_provider, _public_url
    _supervisor_running = False
    with _lock:
        if _active_process:
            try:
                _active_process.terminate()
                _active_process.wait(timeout=2.0)
            except Exception:
                try:
                    _active_process.kill()
                except Exception:
                    pass
            _active_process = None
        _active_provider = None
        _public_url = None


# Ensure tunnel process is terminated when Python exits
atexit.register(stop_tunnel)

