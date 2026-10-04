#!/usr/bin/env python3
"""
Hikayat Release Packaging Utility
Creates a clean, portable zip archive of the bot inside the releases/ directory.

Excludes:
- Virtual environments (venv, env, .venv)
- Compiled bytecode & caches (__pycache__, *.pyc, .pytest_cache)
- Dependency caches & binaries (node_modules, bin/cloudflared.exe)
- Runtime databases (*.db, *.db-wal, *.db-shm, etc.)
- Process locks (.bot.pid, .bot.lock) and secrets (.env)
- Temporary/scratch files and existing zip archives

Output is saved exclusively to:
  releases/hikayat-v{APP_VERSION}-clean.zip
"""
import os
import sys
import zipfile
import re

# Add project root to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from config import APP_VERSION

EXCLUDE_DIRS = {
    'venv', 'env', 'ENV', '.venv',
    '__pycache__', '.pytest_cache',
    'node_modules', '.git', '.idea', '.vscode',
    'bin', 'scratch', 'releases', 'icon'
}

EXCLUDE_EXTS = {
    '.pyc', '.pyo', '.pyd',
    '.db', '.db-wal', '.db-shm', '.db-journal', '.sqlite', '.sqlite3',
    '.zip', '.lock', '.pid', '.tmp', '.bak', '.log'
}

EXCLUDE_EXACT_FILES = {
    '.env', '.DS_Store', 'Thumbs.db'
}


def package_release(dry_run: bool = False) -> str:
    releases_dir = os.path.join(BASE_DIR, "releases")
    os.makedirs(releases_dir, exist_ok=True)
    target_zip = os.path.join(releases_dir, f"hikayat-v{APP_VERSION}-clean.zip")

    files_to_pack = []
    personal_info_pattern = re.compile(r'(aiman|c:[\\/]users)', re.IGNORECASE)
    violations = []

    for root, dirs, files in os.walk(BASE_DIR):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith('.')]
        for file in files:
            if file in EXCLUDE_EXACT_FILES:
                continue
            ext = os.path.splitext(file)[1].lower()
            if ext in EXCLUDE_EXTS:
                continue
            if file.startswith('.env') and file != '.env.example':
                continue
            if 'hikayat.db' in file:
                continue

            filepath = os.path.join(root, file)
            arcname = os.path.relpath(filepath, BASE_DIR).replace(os.sep, '/')

            # Check for personal path leaks in text files (skip packager script itself)
            if arcname != "scripts/package_release.py" and not file.endswith(('.png', '.jpg', '.jpeg', '.ico', '.exe')):
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        for line_idx, line in enumerate(f, 1):
                            if personal_info_pattern.search(line):
                                violations.append((arcname, line_idx))
                except Exception:
                    pass

            files_to_pack.append((filepath, arcname))

    if violations:
        print("[ERROR] Found potential personal info leaks in candidate files:")
        for v in violations:
            print(f"  {v[0]}:{v[1]}")
        sys.exit(1)

    print(f"[Hikayat] Identified {len(files_to_pack)} clean files for release v{APP_VERSION}.")

    if dry_run:
        print(f"[DRY-RUN] Target: {target_zip}")
        return target_zip

    if os.path.exists(target_zip):
        os.remove(target_zip)

    with zipfile.ZipFile(target_zip, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for fpath, arcname in files_to_pack:
            zf.write(fpath, arcname)

    size_mb = os.path.getsize(target_zip) / (1024 * 1024)
    print(f"[SUCCESS] Packaged: {target_zip} ({size_mb:.2f} MB)")
    return target_zip


if __name__ == "__main__":
    is_dry = "--dry-run" in sys.argv
    package_release(dry_run=is_dry)
