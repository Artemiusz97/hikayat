"""
Automatic1111 / SD-Forge style public link sharing for Hikayat.
Generates a secure, temporary public HTTPS/WSS link via Cloudflare Tunnel (trycloudflare.com)
or SSH reverse tunnel (pinggy / localhost.run) so anyone with the URL can play without
needing to be on the same Wi-Fi network.
"""
import atexit
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Optional

_active_process: Optional[subprocess.Popen] = None
_public_url: Optional[str] = None
_lock = threading.Lock()


def get_public_url() -> Optional[str]:
    """Returns the currently active public URL if link sharing is enabled."""
    global _public_url
    return _public_url


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


def _start_cloudflare_tunnel(port: int = 8000, timeout: float = 25.0) -> str:
    global _active_process, _public_url
    cf_bin = ensure_cloudflared()

    cmd = [cf_bin, "tunnel", "--url", f"http://127.0.0.1:{port}"]

    # Use creationflags on Windows to avoid opening extra cmd window
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

    # Cloudflare outputs quick tunnel url to stderr
    def monitor_stream():
        nonlocal url_found
        for line in iter(proc.stderr.readline, ''):
            if not line:
                break
            match = url_pattern.search(line)
            if match and not url_found:
                url_found = match.group(0)
                break

    t = threading.Thread(target=monitor_stream, daemon=True)
    t.start()

    while time.time() - start_time < timeout:
        if url_found:
            break
        if proc.poll() is not None:
            # Process exited prematurely
            err_output = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"Cloudflare tunnel exited with code {proc.returncode}: {err_output}")
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
        "-R", f"0:localhost:{port}",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=30",
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

    def monitor_stream():
        nonlocal url_found
        for line in iter(proc.stdout.readline, ''):
            if not line:
                break
            match = url_pattern.search(line)
            if match and not url_found:
                url_found = match.group(0)
                break

    t = threading.Thread(target=monitor_stream, daemon=True)
    t.start()

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


def start_tunnel(port: int = 8000, provider: str = "cloudflare") -> str:
    """
    Starts a public tunnel for the given local port.
    Returns the public HTTPS URL.
    """
    with _lock:
        global _public_url
        if _public_url and _active_process and _active_process.poll() is None:
            return _public_url

        provider = provider.lower().strip()
        print(f"[TUNNEL] Establishing public link sharing using {provider.capitalize()}...")

        if provider == "pinggy":
            try:
                return _start_pinggy_tunnel(port)
            except Exception as e:
                print(f"[WARNING] Pinggy tunnel failed: {e}. Trying Cloudflare tunnel...")
                return _start_cloudflare_tunnel(port)
        else:
            try:
                return _start_cloudflare_tunnel(port)
            except Exception as e:
                print(f"[WARNING] Cloudflare tunnel failed: {e}. Attempting SSH pinggy fallback...")
                try:
                    return _start_pinggy_tunnel(port)
                except Exception as e2:
                    raise RuntimeError(f"All tunnel providers failed: Cloudflare ({e}), Pinggy ({e2})")


def stop_tunnel():
    """Terminates the running tunnel process."""
    with _lock:
        global _active_process, _public_url
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
        _public_url = None


# Ensure tunnel process is terminated when Python exits
atexit.register(stop_tunnel)
