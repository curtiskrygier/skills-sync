#!/usr/bin/env python3
"""
sync_skills.py — Sync your local AI skills library to/from Google Shared Drive.

Supports incremental push (default), full push, pull, and dry-run modes.

Usage:
  skills-sync                # incremental push
  skills-sync --full         # force full push
  skills-sync --pull         # pull all skills
  skills-sync --dry-run      # preview push
  skills-sync --pull --dry-run  # preview pull

Configuration:
  Values are loaded automatically from .config in this script's directory
  (written by install.sh). Environment variables override the config file.

  SHARED_DRIVE_ID  — your Shared Drive ID
  DRIVE_FOLDER     — subfolder name within the Shared Drive to use as root
                     (optional; defaults to Drive root)
  SA_KEY_JSON      — full SA key as decoded JSON string, for zero-disk-footprint
                     operation (alternative to placing the key file on disk)
"""

__version__ = "1.0.0"

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# ── Config ────────────────────────────────────────────────────────────────────
CONTEXT_DIR = Path(__file__).parent.resolve()   # ~/.local/share/sync-skills/
SKILLS_DIR  = CONTEXT_DIR / "skills"            # ~/.local/share/sync-skills/skills/

def _load_config():
    """Load .config written by install.sh. Env vars take precedence."""
    config_file = CONTEXT_DIR / ".config"
    if not config_file.exists():
        return
    for line in config_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

_load_config()

SHARED_DRIVE_ID = os.environ.get("SHARED_DRIVE_ID", "YOUR_SHARED_DRIVE_ID")
DRIVE_FOLDER    = os.environ.get("DRIVE_FOLDER", "")        # optional subfolder
TIMESTAMP_FILE  = CONTEXT_DIR / ".last_sync"
SKIP_DIRS       = {"__pycache__", ".git", "venv", "node_modules"}
SKIP_EXTS       = {".pyc"}

SCOPES = ["https://www.googleapis.com/auth/drive"]

# ── Auth ──────────────────────────────────────────────────────────────────────
def _find_sa_key() -> Path:
    """Auto-discover the SA key JSON in the same directory as this script."""
    keys = sorted(CONTEXT_DIR.glob("*.json"))
    if not keys:
        raise FileNotFoundError(
            f"No SA key JSON found in {CONTEXT_DIR}. "
            "Place your key file there or set the SA_KEY_JSON env var."
        )
    if len(keys) > 1:
        names = ", ".join(k.name for k in keys)
        raise FileNotFoundError(
            f"Multiple JSON files found in {CONTEXT_DIR}: {names}\n"
            "Remove all but your SA key, or set the SA_KEY_JSON env var to avoid ambiguity."
        )
    return keys[0]

def get_service():
    try:
        key_json = os.environ.get("SA_KEY_JSON")
        if key_json:
            try:
                info = json.loads(key_json)
            except json.JSONDecodeError as e:
                print(f"ERROR: SA_KEY_JSON is not valid JSON — {e.msg} at position {e.pos}")
                sys.exit(1)
            creds = service_account.Credentials.from_service_account_info(
                info, scopes=SCOPES
            )
        else:
            creds = service_account.Credentials.from_service_account_file(
                str(_find_sa_key()), scopes=SCOPES
            )
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except FileNotFoundError:
        raise
    except Exception as e:
        print(f"ERROR: Failed to initialise Drive client — {e}")
        print("Check that your SA key is valid and you have network access.")
        sys.exit(1)

# ── Timestamp helpers ─────────────────────────────────────────────────────────
def load_last_sync() -> float:
    if TIMESTAMP_FILE.exists():
        try:
            return float(TIMESTAMP_FILE.read_text().strip())
        except ValueError:
            pass
    return 0.0

def save_last_sync(ts: float):
    try:
        TIMESTAMP_FILE.write_text(str(ts))
    except OSError as e:
        print(f"Warning: could not save sync timestamp — {e}. Next push will re-upload all files.")

# ── Drive helpers ─────────────────────────────────────────────────────────────
def get_or_create_folder(service, name, parent_id):
    safe_name = name.replace("'", "\\'")
    q = (
        f"name='{safe_name}' and mimeType='application/vnd.google-apps.folder' "
        f"and '{parent_id}' in parents and trashed=false"
    )
    res = service.files().list(
        q=q, fields="files(id)",
        supportsAllDrives=True, includeItemsFromAllDrives=True,
        driveId=SHARED_DRIVE_ID, corpora="drive"
    ).execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]
    meta = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    f = service.files().create(body=meta, fields="id", supportsAllDrives=True).execute()
    return f["id"]

def get_root_folder(service) -> str:
    """Return the Drive folder ID to use as the sync root."""
    if DRIVE_FOLDER:
        return get_or_create_folder(service, DRIVE_FOLDER, SHARED_DRIVE_ID)
    return SHARED_DRIVE_ID

def get_existing_file(service, name, parent_id):
    safe_name = name.replace("'", "\\'")
    q = f"name='{safe_name}' and '{parent_id}' in parents and trashed=false"
    res = service.files().list(
        q=q, fields="files(id)",
        supportsAllDrives=True, includeItemsFromAllDrives=True,
        driveId=SHARED_DRIVE_ID, corpora="drive"
    ).execute()
    files = res.get("files", [])
    return files[0]["id"] if files else None

def upload_file(service, local_path: Path, parent_id: str) -> bool:
    """Upload or update a file. Returns True on success, False on failure."""
    name = local_path.name
    try:
        media = MediaFileUpload(str(local_path), resumable=False)
        existing_id = get_existing_file(service, name, parent_id)
        if existing_id:
            service.files().update(
                fileId=existing_id, media_body=media, supportsAllDrives=True
            ).execute()
            print(f"  updated: {local_path.name}")
        else:
            meta = {"name": name, "parents": [parent_id]}
            service.files().create(
                body=meta, media_body=media, fields="id", supportsAllDrives=True
            ).execute()
            print(f"  created: {local_path.name}")
        return True
    except HttpError as e:
        print(f"  FAILED:  {local_path.name} — HTTP {e.status_code}: {e.reason}")
        return False
    except Exception as e:
        print(f"  FAILED:  {local_path.name} — {e}")
        return False

# ── Push ──────────────────────────────────────────────────────────────────────
def sync_dir(service, local_dir: Path, drive_parent_id: Optional[str], last_sync: float, full: bool, dry_run: bool) -> Tuple[int, int]:
    """Returns (succeeded, failed)."""
    ok, fail = 0, 0
    for item in sorted(local_dir.iterdir()):
        if item.name.startswith(".") or item.name in SKIP_DIRS:
            continue
        if item.is_dir():
            if dry_run:
                sub_ok, sub_fail = sync_dir(service, item, drive_parent_id, last_sync, full, dry_run)
            else:
                folder_id = get_or_create_folder(service, item.name, drive_parent_id)
                sub_ok, sub_fail = sync_dir(service, item, folder_id, last_sync, full, dry_run)
            ok += sub_ok; fail += sub_fail
        elif item.is_file() and item.suffix not in SKIP_EXTS:
            if full or item.stat().st_mtime > last_sync:
                if dry_run:
                    print(f"  [dry-run] would upload: {item.relative_to(SKILLS_DIR)}")
                    ok += 1
                elif upload_file(service, item, drive_parent_id):
                    ok += 1
                else:
                    fail += 1
    return ok, fail

# ── Pull ──────────────────────────────────────────────────────────────────────
def list_drive_items(service, folder_id):
    """Yield (name, id, is_folder) for all non-trashed items in folder_id."""
    page_token = None
    while True:
        res = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(id, name, mimeType)",
            supportsAllDrives=True, includeItemsFromAllDrives=True,
            driveId=SHARED_DRIVE_ID, corpora="drive",
            pageToken=page_token
        ).execute()
        for f in res.get("files", []):
            yield f["name"], f["id"], f["mimeType"] == "application/vnd.google-apps.folder"
        page_token = res.get("nextPageToken")
        if not page_token:
            break

def download_file(service, file_id, local_path: Path):
    local_path.parent.mkdir(parents=True, exist_ok=True)
    verb = "overwrite" if local_path.exists() else "pulled"
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    with open(local_path, "wb") as f:
        f.write(request.execute())
    print(f"  {verb}: {local_path.relative_to(SKILLS_DIR)}")

def pull_dir(service, drive_folder_id: str, local_dir: Path, dry_run: bool) -> Tuple[int, int]:
    """Returns (succeeded, failed)."""
    ok, fail = 0, 0
    try:
        items = list(list_drive_items(service, drive_folder_id))
    except HttpError as e:
        print(f"  FAILED: could not list Drive folder — HTTP {e.status_code}: {e.reason}")
        return 0, 1
    for name, item_id, is_folder in items:
        if name in SKIP_DIRS or name.startswith("."):
            continue
        local_path = local_dir / name
        if is_folder:
            if not dry_run:
                local_path.mkdir(parents=True, exist_ok=True)
            sub_ok, sub_fail = pull_dir(service, item_id, local_path, dry_run)
            ok += sub_ok; fail += sub_fail
        elif Path(name).suffix not in SKIP_EXTS:
            if dry_run:
                print(f"  [dry-run] would pull: {local_path.relative_to(SKILLS_DIR)}")
                ok += 1
            else:
                try:
                    download_file(service, item_id, local_path)
                    ok += 1
                except Exception as e:
                    print(f"  FAILED:  {name} — {e}")
                    fail += 1
    return ok, fail

# ── Main ──────────────────────────────────────────────────────────────────────
GITHUB_RAW_URL = "https://raw.githubusercontent.com/curtiskrygier/skills-sync/main/sync_skills.py"

def self_update():
    """Replace this script with the latest version from GitHub."""
    import urllib.request
    import hashlib
    this_file = Path(__file__).resolve()
    print(f"Fetching latest version from {GITHUB_RAW_URL} ...")
    try:
        with urllib.request.urlopen(GITHUB_RAW_URL, timeout=15) as r:
            latest = r.read()
    except Exception as e:
        print(f"ERROR: Could not fetch update — {e}")
        sys.exit(1)
    current_hash = hashlib.sha256(this_file.read_bytes()).hexdigest()[:12]
    latest_hash  = hashlib.sha256(latest).hexdigest()[:12]
    if current_hash == latest_hash:
        print("Already up to date.")
        return
    this_file.write_bytes(latest)
    print(f"Updated: {current_hash} → {latest_hash}")
    print(f"Installed: {this_file}")

USAGE = """\
Usage: sync_skills.py [--full] [--pull] [--dry-run] [--update] [--version]

  (no flags)          Incremental push — upload files changed since last sync
  --full              Force push all files regardless of modification time
  --pull              Pull all skills from Drive to local
  --dry-run           Preview what would be uploaded/pulled without making changes
  --pull --dry-run    Preview what would be pulled (requires credentials)
  --update            Replace installed script with latest version from GitHub
  --version           Print version and exit
"""

def main():
    if "--version" in sys.argv:
        print(__version__)
        sys.exit(0)

    if "--update" in sys.argv:
        self_update()
        sys.exit(0)

    known_flags = {"--pull", "--full", "--dry-run", "--version", "--update"}
    unknown = [a for a in sys.argv[1:] if a.startswith("-") and a not in known_flags]
    if unknown:
        print(f"ERROR: Unknown flag(s): {' '.join(unknown)}\n")
        print(USAGE)
        sys.exit(1)

    pull    = "--pull"    in sys.argv
    full    = "--full"    in sys.argv
    dry_run = "--dry-run" in sys.argv

    # Validate config — skip for dry-run push which needs no Drive access
    if not (dry_run and not pull) and SHARED_DRIVE_ID == "YOUR_SHARED_DRIVE_ID":
        print("ERROR: SHARED_DRIVE_ID is not configured. Set it in .config or via env var.")
        sys.exit(1)

    # dry-run push needs no Drive access — work purely from local state
    if dry_run and not pull:
        last_sync = 0.0 if full else load_last_sync()
        mode = "full" if full else (
            f"incremental (since {time.strftime('%Y-%m-%d %H:%M', time.localtime(last_sync))})"
            if last_sync else "incremental (first run)"
        )
        print(f"[dry-run] Would sync → Shared Drive{f' / {DRIVE_FOLDER}' if DRIVE_FOLDER else ''} [{mode}]")
        ok, _ = sync_dir(None, SKILLS_DIR, None, last_sync, full, dry_run=True)
        print(f"{ok} file(s) would be uploaded." if ok else "No changes to sync.")
        return

    try:
        service = get_service()
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    try:
        root = get_root_folder(service)
    except HttpError as e:
        print(f"ERROR: Could not access Drive folder — HTTP {e.status_code}: {e.reason}")
        sys.exit(1)

    if pull:
        label = "[dry-run] " if dry_run else ""
        print(f"{label}Pulling skills ← Shared Drive{f' / {DRIVE_FOLDER}' if DRIVE_FOLDER else ''}")
        ok, fail = pull_dir(service, root, SKILLS_DIR, dry_run)
        verb = "would be pulled" if dry_run else "pulled"
        if ok == 0 and fail == 0:
            print("[dry-run] Nothing would be pulled." if dry_run else "Nothing to pull.")
        elif fail > 0:
            print(f"Done — {ok} file(s) {verb}, {fail} failed. Check output above for details.")
            sys.exit(1)
        else:
            print(f"Done — {ok} file(s) {verb}.")
        return

    last_sync = 0.0 if full else load_last_sync()
    mode = "full" if full else (
        f"incremental (since {time.strftime('%Y-%m-%d %H:%M', time.localtime(last_sync))})"
        if last_sync else "incremental (first run)"
    )
    print(f"Syncing skills → Shared Drive{f' / {DRIVE_FOLDER}' if DRIVE_FOLDER else ''} [{mode}]")

    sync_start = time.time()
    ok, fail = sync_dir(service, SKILLS_DIR, root, last_sync, full, dry_run)

    if ok == 0 and fail == 0:
        print("No changes to sync.")
    else:
        if ok > 0:
            save_last_sync(sync_start)
        if fail > 0:
            print(f"Done — {ok} file(s) synced, {fail} failed. Check output above for details.")
            sys.exit(1)
        else:
            print(f"Done — {ok} file(s) synced.")


if __name__ == "__main__":
    main()
