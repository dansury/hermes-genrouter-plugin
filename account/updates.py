"""Daily, read-only checks for both plugin manifests; never auto-install."""
import base64
import json
import logging
import os
from pathlib import Path
import re
import threading
import time

from .reports import VERSION, REPOSITORY, github_api, safe_capture
from .storage import hermes_home, private_write

_LOCK = threading.Lock()
_WORKER = None


def interval_hours():
    try:
        hours = float(os.environ.get("GENROUTER_UPDATE_CHECK_HOURS", "24"))
        return hours if 0 <= hours <= 8760 else 24
    except ValueError:
        return 24


def check_updates(force=False, home=None):
    root = Path(home) if home else hermes_home()
    path = root / "plugin-data" / "genrouter-account" / "updates.json"
    with _LOCK:
        old = {}
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
        hours, now = interval_hours(), time.time()
        if not force and (hours == 0 or now - old.get("checked_at", 0) < hours * 3600):
            return dict(old, enabled=hours > 0, interval_hours=hours)
        result = {"checked_at": now, "interval_hours": hours, "installed_version": VERSION,
                  "update_available": False, "repository": "https://github.com/" + REPOSITORY}
        try:
            remote = {}
            for file in ("plugin.yaml", "account/plugin.yaml"):
                row = github_api("/repos/" + REPOSITORY + "/contents/" + file + "?ref=main", identity="public")
                source = base64.b64decode(row["content"], validate=False).decode("utf-8")
                match = re.search(r"^version:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$", source, re.M)
                if not match:
                    raise ValueError("Unexpected remote plugin version")
                remote[file] = match.group(1)
            result["remote_versions"] = remote
            result["update_available"] = any(tuple(map(int, v.split("."))) > tuple(map(int, VERSION.split("."))) for v in remote.values())
            result["commands"] = ["hermes plugins update genrouter-ru", "hermes plugins update genrouter-account"]
        except Exception as error:
            safe_capture(error, action="update_check", home=root)
            result["check_failed"] = True
        private_write(path, json.dumps(result, indent=2).encode())
        return result


def start_checks():
    global _WORKER
    if _WORKER is not None and _WORKER.is_alive():
        return
    root = hermes_home()
    def run():
        notified = None
        while True:
            try:
                result = check_updates(home=root)
                stamp = result.get("checked_at")
                if result.get("update_available") and stamp != notified:
                    logging.getLogger("genrouter").warning("GenRouter update available: hermes genrouter updates")
                    notified = stamp
            except Exception as error:
                safe_capture(error, action="update_check", home=root)
            time.sleep(3600)
    _WORKER = threading.Thread(target=run, name="genrouter-update-check", daemon=True)
    _WORKER.start()
