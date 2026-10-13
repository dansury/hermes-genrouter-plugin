"""Local diagnostic queue and explicitly consented GitHub/email reports."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version, PackageNotFoundError
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import threading
import time
import traceback
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

from .reporter_credential import shared_token
from .sanitize import sanitize
from .storage import hermes_home, private_write

VERSION = "0.3.1"
REPOSITORY = "dansury/hermes-genrouter-plugin"
CONSENT_TEXT = ("С вашей помощью мы быстрее сделаем продукт, который вам понравится. "
                "Можно поделиться этой ошибкой и очищенной диагностикой? "
                "Отчёт будет публичным в GitHub. Проверьте его перед отправкой. "
                "Секреты удаляются; переписка автоматически не прикладывается. "
                "В выбранном вами файле лога могут оставаться личные данные — проверьте его.")
_LOCK = threading.RLock()
_DELIVERY_LOCK = threading.RLock()


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def github_api(path, payload=None, identity="shared"):
    """Fixed destination, no redirects or automatic retries of writes."""
    if not (path.startswith("/repos/" + REPOSITORY + "/") or path == "/user"):
        raise ValueError("Reporting is restricted to the plugin repository")
    if identity == "personal":
        cmd = ["gh", "api", "--hostname", "github.com", path]
        if payload is not None:
            cmd += ["--method", "POST", "--input", "-"]
        result = subprocess.run(cmd, input=json.dumps(payload) if payload is not None else None,
                                text=True, encoding="utf-8", capture_output=True, timeout=20)
        if result.returncode:
            raise RuntimeError("GitHub request failed; no write was automatically retried")
        return json.loads(result.stdout)
    if identity not in {"shared", "public"}:
        raise ValueError("Unknown GitHub identity")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "hermes-genrouter/" + VERSION,
               "X-GitHub-Api-Version": "2022-11-28"}
    if identity == "shared":
        headers["Authorization"] = "Bearer " + shared_token()
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request("https://api.github.com" + path, data=data, headers=headers)
    with build_opener(NoRedirects()).open(req, timeout=15) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("GitHub response too large")
    return json.loads(raw)


def personal_identity():
    if not shutil.which("gh"):
        return None
    try:
        return github_api("/user", identity="personal").get("login")
    except Exception:
        return None


def report_dir(home=None):
    return (Path(home) if home else hermes_home()) / "plugin-data" / "genrouter-account" / "reports"


@contextmanager
def report_lock(home=None, name=".queue.lock"):
    """OS-held locks release on process exit; delivery never locks error capture."""
    directory = report_dir(home)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    mutex = _LOCK if name == ".queue.lock" else _DELIVERY_LOCK
    with mutex:
        with path.open("a+b") as stream:
            if stream.seek(0, 2) == 0:
                stream.write(b"0")
                stream.flush()
            deadline = time.monotonic() + 3
            while True:
                try:
                    stream.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Diagnostic queue busy; retry later")
                    time.sleep(0.05)
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _known_secrets():
    secrets = [shared_token()]
    try:
        from .storage import SecretStore
        state = SecretStore().load()
        secrets += list(state.get("keys", {}).values())
        secrets += [c.get("value") for c in state.get("cookies", [])]
    except Exception:
        pass
    return secrets


def clean(value):
    return sanitize(value, _known_secrets())


def capture(error=None, action="manual", description="", home=None, metadata=None, message_override=None):
    """No network, no frame locals/source lines, no request/response payloads."""
    frames = []
    if error is not None:
        frames = [{"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
                  for f in traceback.extract_tb(getattr(error, "__traceback__", None))]
    message = clean(message_override) if message_override is not None else (clean(str(error)) if error is not None else clean(description))
    details = {k: getattr(error, k, None) for k in
               ("status", "request_id", "error_code", "retry_after", "endpoint", "method")}
    # Accept only explicitly allowed metadata from the native provider.
    details.update({k: clean(v) for k, v in (metadata or {}).items()
                    if k in {"status", "request_id", "error_code", "retry_after", "endpoint", "model"}
                    and isinstance(v, (str, int))})
    kind = getattr(error, "type_name", type(error).__name__) if error is not None else "UserReport"
    normalized = re.sub(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b|\b\d+\b", "#", message, flags=re.I)
    signature = [action, kind, details["status"], details["error_code"], details["endpoint"],
                 [(f["file"], f["function"]) for f in frames], re.sub(r"Request ID: [A-Za-z0-9_.:-]+", "Request ID: #", normalized)]
    fingerprint = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()[:24]
    try:
        hermes_version = version("hermes-agent")
    except PackageNotFoundError:
        hermes_version = "unknown"
    now = datetime.now(timezone.utc).isoformat()
    path = report_dir(home) / (fingerprint + ".json")
    with report_lock(home):
        old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        report = {"fingerprint": fingerprint, "plugin_version": VERSION,
                  "hermes_version": hermes_version, "python": platform.python_version(),
                  "os": platform.system(), "os_release": platform.release(),
                  "action": action, "exception": kind, "message": message[:4000],
                  "diagnostics": details, "stack": frames, "first_seen": old.get("first_seen", now),
                  "last_seen": now, "occurrences": old.get("occurrences", 0) + 1}
        if old.get("issue_url"):
            report["issue_url"] = old["issue_url"]
        private_write(path, json.dumps(report, ensure_ascii=False, indent=2).encode())
        files = sorted(report_dir(home).glob("*.json"), key=lambda p: p.stat().st_mtime)
        for stale in files[:-100]:
            stale.unlink()
    return report


def safe_capture(*args, **kwargs):
    """Reporting failures must never hide the original plugin error."""
    try:
        return capture(*args, **kwargs)
    except Exception:
        return None


def pending(home=None):
    rows = []
    for path in report_dir(home).glob("*.json"):
        try:
            rows.append(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            continue
    return sorted(rows, key=lambda r: r["last_seen"], reverse=True)


def load_report(fingerprint=None, home=None):
    rows = pending(home)
    if fingerprint is None and rows:
        return rows[0]
    if fingerprint and re.fullmatch(r"[a-f0-9]{24}", fingerprint):
        row = next((r for r in rows if r["fingerprint"] == fingerprint), None)
        if row:
            return row
    raise ValueError("No diagnostic report found")


def render(report, description="", log_path=None):
    report = dict(report)
    report.pop("issue_url", None)
    body = "GenRouter diagnostic report\n\n" + clean(description)[:4000]
    body += "\n\nReport ID: genrouter-error-" + report["fingerprint"]
    body += "\n\n" + clean(json.dumps(report, ensure_ascii=False, indent=2))
    if log_path:
        path = Path(log_path)
        if not path.is_file() or path.name.startswith(".env") or path.suffix in {".secrets", ".session"} or path.name in {"auth.json", "config.yaml"}:
            raise ValueError("Choose a diagnostic text log, never a credential/configuration file")
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - 12000))
            tail = stream.read(12000).decode("utf-8", errors="replace")
        body += "\n\nUser-selected log excerpt (review carefully):\n" + clean(tail)
    return body[:40000]


def submit(report, body, *, consent=False, identity="shared", home=None):
    if not consent:
        raise ValueError("Explicit consent after report preview is required")
    marker = "genrouter-error-" + report["fingerprint"]
    if marker not in body:
        raise ValueError("Report fingerprint missing")
    # Use paginated listing instead of eventually indexed search. Inspect closed
    # issues too. Never blindly retry a POST after a timeout or a failed scan.
    with report_lock(home, name=".delivery.lock"):
        for page in range(1, 21):
            rows = github_api("/repos/" + REPOSITORY + "/issues?" +
                              urlencode({"state": "all", "per_page": 100, "page": page}), identity=identity)
            if not isinstance(rows, list):
                raise ValueError("Unexpected GitHub issue list")
            for row in rows:
                if "pull_request" not in row and marker in (row.get("body") or ""):
                    url = row["html_url"]
                    break
            else:
                if len(rows) == 100:
                    continue
                result = github_api("/repos/" + REPOSITORY + "/issues",
                                    {"title": "[GenRouter] " + report["exception"] + " [" + report["fingerprint"] + "]",
                                     "body": body}, identity=identity)
                url = result["html_url"]
            break
        else:
            raise RuntimeError("Cannot complete duplicate check; use the email fallback")
        path = report_dir(home) / (report["fingerprint"] + ".json")
        with report_lock(home):
            current = json.loads(path.read_text(encoding="utf-8"))
            current["issue_url"] = url
            private_write(path, json.dumps(current, ensure_ascii=False, indent=2).encode())
    return {"issue_url": url, "identity": identity}


def email_draft(report, body, home=None):
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["To"] = "dansury@gmail.com"
    msg["Subject"] = "GenRouter report " + report["fingerprint"]
    msg.set_content(body)
    path = report_dir(home) / (report["fingerprint"] + ".eml")
    private_write(path, msg.as_bytes())
    return {"email_draft": str(path), "recipient": "dansury@gmail.com", "sent": False,
            "hint": "Open the .eml in your mail app, review and send with your own account."}
