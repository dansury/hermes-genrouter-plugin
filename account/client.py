"""GenRouter's observed cabinet API and its OpenAI-compatible inference API.

Cabinet endpoints are not a published compatibility contract. See docs/API.md.
No automatic retries: mutations can issue keys or move money.
"""

from decimal import Decimal, InvalidOperation
import http.cookiejar
import json
import os
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import build_opener, HTTPCookieProcessor, HTTPRedirectHandler, Request
import uuid

from .storage import SecretStore
from .sanitize import sanitize


PORTAL = "https://genrouter.ru"
INFERENCE = "https://api.genrouter.ru/v1"
KEY_FIELDS = ("id", "name", "key_prefix", "is_active", "balance_micro",
              "reserved_micro", "spent_micro", "request_count", "created_at")


class GenRouterError(RuntimeError):
    def __init__(self, message, status=None, *, request_id=None, error_code=None, retry_after=None, endpoint=None, method=None):
        super().__init__(message)
        self.status = status
        self.request_id = request_id
        self.error_code = error_code
        self.retry_after = retry_after
        self.endpoint = endpoint
        self.method = method


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def redact(text):
    return sanitize(text)


def usd_to_micro(value, positive=False):
    try:
        amount = Decimal(str(value)) * 1_000_000
    except InvalidOperation:
        raise ValueError("Use a decimal USD amount") from None
    if not amount.is_finite() or amount < 0 or amount != amount.to_integral_value():
        raise ValueError("Use a nonnegative USD amount with at most six decimal places")
    if positive and amount == 0:
        raise ValueError("Amount must be greater than zero")
    return int(amount)


def micro_to_usd(value):
    if value is None:
        return None
    return format(Decimal(str(value)) / 1_000_000, "f")


def safe_key(row):
    result = {field: row[field] for field in KEY_FIELDS if field in row}
    result["available_usd"] = micro_to_usd(row.get("balance_micro"))
    result["reserved_usd"] = micro_to_usd(row.get("reserved_micro"))
    result["spent_usd"] = micro_to_usd(row.get("spent_micro"))
    # Never infer a particular key's RPM from the default 60.
    result["rate_limits"] = {"rpm": row.get("rpm"), "tpm": None, "concurrency": None,
                             "daily_budget": None, "monthly_budget": None, "reset_at": None} if row.get("rpm") is not None else None
    return result


class Client:
    def __init__(self, store=None, timeout=15):
        self.store = store or SecretStore()
        self.timeout = timeout
        self.state = self.store.load()
        self.jar = http.cookiejar.CookieJar()
        for row in self.state.get("cookies", []):
            cookie = http.cookiejar.Cookie(**row)
            if cookie.domain.lstrip(".") == "genrouter.ru":
                self.jar.set_cookie(cookie)
        self.opener = build_opener(HTTPCookieProcessor(self.jar), NoRedirects())

    def _save(self):
        fields = ("version", "name", "value", "port", "port_specified", "domain",
                  "domain_specified", "domain_initial_dot", "path", "path_specified",
                  "secure", "expires", "discard", "comment", "comment_url", "rfc2109")
        self.state["cookies"] = [
            dict({name: getattr(cookie, name) for name in fields}, rest=cookie._rest)
            for cookie in self.jar if cookie.domain.lstrip(".") == "genrouter.ru"
        ]
        self.store.save(self.state)

    def _http(self, url, method="GET", payload=None, api_key=None, cabinet=True):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in {"genrouter.ru", "api.genrouter.ru"}:
            raise ValueError("Credentials may only be sent to HTTPS GenRouter endpoints")
        if parsed.username or parsed.password or parsed.port not in {None, 443}:
            raise ValueError("Invalid GenRouter endpoint")
        headers = {"Accept": "application/json", "User-Agent": "hermes-genrouter-plugin/0.3.0"}
        if cabinet:
            headers.update({"Origin": PORTAL, "Referer": PORTAL + "/dashboard/"})
        if api_key:
            headers["Authorization"] = "Bearer " + api_key
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
        request = Request(url, data=body, headers=headers, method=method)
        # Inference never receives a cabinet cookie; redirects never forward either credential.
        opener = self.opener if cabinet else build_opener(NoRedirects())
        try:
            with opener.open(request, timeout=self.timeout) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise GenRouterError("API response exceeds the 2 MB limit")
                data = json.loads(raw) if raw else None
        except HTTPError as error:
            # Retain only selected metadata; never store the raw body or request payload.
            request_id = error.headers.get("x-request-id") or error.headers.get("request-id")
            retry_after = error.headers.get("Retry-After")
            message, code = None, None
            try:
                parsed_error = json.loads(error.read(65536))
                detail = parsed_error.get("error", parsed_error) if isinstance(parsed_error, dict) else {}
                if isinstance(detail, dict):
                    message, code = detail.get("message"), detail.get("code")
                    request_id = request_id or detail.get("request_id") or parsed_error.get("request_id")
            except (ValueError, OSError, UnicodeDecodeError):
                pass
            finally:
                error.close()
            request_id = request_id if isinstance(request_id, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", request_id) else None
            code = code if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", code) else None
            retry_after = retry_after if isinstance(retry_after, str) and re.fullmatch(r"[A-Za-z0-9 ,:-]{1,80}", retry_after) else None
            advice = {
                401: "Session expired or inference key rejected. Check session or sign in again.",
                402: "Gateway or upstream billing error. The reason is not necessarily your key balance.",
                403: "Access denied; account API authentication/CSRF compatibility needs review.",
                404: "Endpoint unavailable; the experimental account contract may have changed.",
                409: "Conflict. Check existing account/key state before retrying.",
                429: "Rate limited. Observe Retry-After; do not create keys to bypass limits.",
            }.get(error.code, "Request failed. Check the cabinet for details.")
            if isinstance(message, str):
                secrets = [api_key] + list(self.state.get("keys", {}).values()) + [cookie.value for cookie in self.jar]
                if isinstance(payload, dict):
                    secrets += [payload.get(k) for k in ("password", "code", "email", "key")]
                advice += " Server: " + sanitize(message, secrets)[:2000]
            if request_id:
                advice += " Request ID: " + request_id
            raise GenRouterError(f"GenRouter HTTP {error.code}. {advice}", error.code,
                                 request_id=request_id, error_code=code, retry_after=retry_after,
                                 endpoint=parsed.path, method=method) from None
        except (URLError, socket.timeout, TimeoutError):
            raise GenRouterError("Network request failed. A mutation may have completed; check the cabinet before retrying.") from None
        except (ValueError, UnicodeDecodeError):
            raise GenRouterError("GenRouter returned an unexpected response format") from None
        if cabinet and method != "GET" and parsed.path != "/dashboard/api/auth/login":
            self._save()
        return data

    def request(self, path, method="GET", payload=None):
        if not path.startswith("/") or ".." in path or "?" in path:
            raise ValueError("Invalid API path")
        return self._http(PORTAL + "/dashboard/api" + path, method, payload)

    def register_account(self, nickname, password, accepted_terms=False):
        if not accepted_terms:
            raise ValueError("Accept GenRouter's terms before creating an account")
        if not re.fullmatch(r"[A-Za-z0-9_]{4,32}", nickname):
            raise ValueError("Nickname: 4–32 Latin letters, digits or underscores")
        if not 8 <= len(password) <= 128 or not re.search(r"[A-Za-z]", password) or not re.search(r"[0-9]", password):
            raise ValueError("Password: 8–128 characters, including a letter and a digit")
        self._check_account(nickname)
        pending = self.state.get("registration_pending")
        if pending:
            raise ValueError("A signup response was lost. Check session, then login by nickname; do not repeat signup.")
        self.state["registration_pending"] = nickname
        self._save()
        try:
            result = self.request("/auth/register", "POST", {"nickname": nickname, "password": password})
        except Exception:
            self._save()  # Preserve a session cookie even when the response body was lost.
            raise
        self.state["nickname"] = nickname
        self.state.pop("registration_pending", None)
        self._save()
        return result

    def _check_account(self, nickname):
        previous = self.state.get("nickname")
        if previous and previous != nickname.strip() and self.state.get("keys"):
            raise ValueError("This Hermes profile already stores another account's keys. Use a separate Hermes profile for a different account.")

    def login(self, nickname, password):
        if "@" not in nickname:
            self._check_account(nickname)
        old_cookies = list(self.jar)
        try:
            result = self.request("/auth/login", "POST", {"nickname": nickname, "password": password})
            canonical = self.profile()["user"].get("nickname") if "@" in nickname else nickname.strip()
            if not isinstance(canonical, str) or not canonical:
                raise GenRouterError("Login response has no canonical account nickname")
            self._check_account(canonical)
        except Exception:
            self.jar.clear()
            for cookie in old_cookies:
                self.jar.set_cookie(cookie)
            raise
        self.state["nickname"] = canonical
        self.state.pop("registration_pending", None)
        self._save()
        return result

    def request_email(self, email):
        if "@" not in email or any(c in email for c in "\r\n"):
            raise ValueError("Provide an email address")
        return self.request("/auth/email/request", "POST", {"email": email})

    def confirm_email(self, code):
        if not re.fullmatch(r"[0-9]{6}", code):
            raise ValueError("Enter the six-digit email confirmation code")
        return self.request("/auth/email/confirm", "POST", {"code": code})

    def logout(self):
        result = self.request("/auth/logout", "POST")
        self.jar.clear()
        self._save()
        return result

    def profile(self):
        data = self.request("/profile")
        if not isinstance(data, dict) or not isinstance(data.get("user"), dict) or not isinstance(data.get("keys"), list):
            raise GenRouterError("Unexpected profile schema; account API compatibility needs review")
        return data

    def session(self):
        data = self.request("/session")
        authenticated = data.get("authenticated") if isinstance(data, dict) else None
        if not isinstance(authenticated, bool):
            authenticated = None
        return {"session_checked": True, "authenticated": authenticated,
                "session_duration_days": 30, "automatic_renewal": False}

    def rotate_key(self, key_id, confirmed=False):
        if not confirmed:
            raise ValueError("Rotation immediately invalidates the old secret; explicitly confirm.")
        identifier = str(key_id)
        rows = self.profile()["keys"]
        row = next((r for r in rows if str(r.get("id")) == identifier), None)
        if row is None or not re.fullmatch(r"[A-Za-z0-9_-]+", identifier):
            raise ValueError("Select a key belonging to this account")
        if self.state.get("rotation_pending"):
            raise ValueError("A rotation response was lost. Inspect the cabinet; do not retry rotation blindly.")
        self.state["rotation_pending"] = identifier
        self._save()
        data = self.request(f"/keys/{identifier}/rotate", "POST")
        if not isinstance(data, dict) or not isinstance(data.get("key"), str) or not data["key"]:
            raise GenRouterError("Rotation returned no secret; inspect the cabinet before any further rotation.")
        name = row["name"]
        self.state.setdefault("keys", {})[name] = data["key"]
        self.state.pop("rotation_pending", None)
        if self.state.get("last_key_operation", {}).get("name") == name:
            self.state["last_key_operation"]["pending"] = False
        self._save()
        return {"rotated": True, "name": name, "secret_saved": True, "old_secret_invalidated": True}

    def status(self):
        profile = self.profile()
        user = profile["user"]
        return {"authenticated": True, "nickname": user.get("nickname"),
                "wallet_usd": micro_to_usd(user.get("wallet_micro")),
                "keys_count": len(profile["keys"]), "payments": self.payment_status()}

    def key_balances(self):
        return [safe_key(row) for row in self.profile()["keys"]]

    def create_key(self, name, allocate_usd="0", operation_id=None):
        if not name.strip() or len(name) > 64:
            raise ValueError("Key name must contain 1 to 64 characters")
        rows = self.profile()["keys"]
        if sum(row.get("is_active") is not False for row in rows) >= 10:
            raise ValueError("GenRouter permits at most ten active keys per account")
        if self.state.get("last_key_operation", {}).get("pending"):
            raise ValueError("A key creation response was lost. List keys first; recover its secret by confirmed rotation, not another creation.")
        if any(row.get("name") == name for row in rows):
            raise ValueError("A key with this name already exists; use another service-specific name")
        allocation = usd_to_micro(allocate_usd)
        operation_id = str(uuid.UUID(operation_id)) if operation_id else str(uuid.uuid4())
        # Save the id before the request so an ambiguous network failure can be investigated.
        self.state["last_key_operation"] = {"operation_id": operation_id, "name": name, "pending": True}
        self._save()
        data = self.request("/keys", "POST", {"name": name, "allocate_micro": allocation,
                                               "operation_id": operation_id})
        if not isinstance(data, dict) or not isinstance(data.get("key"), str) or not data["key"]:
            raise GenRouterError("Key creation response has no key. Check the cabinet before retrying.")
        self.state.setdefault("keys", {})[name] = data["key"]
        self.state["last_key_operation"]["pending"] = False
        self._save()  # One-time key is persisted before optional setup/export.
        return {"created": True, "name": name, "operation_id": operation_id,
                "allocated_usd": micro_to_usd(allocation), "secret_saved": True}

    def use_key(self, name):
        value = self.state.get("keys", {}).get(name)
        if not value:
            raise ValueError("This key was not issued by this plugin; use 'hermes auth add genrouter-ru' for an existing key")
        self.store.install_key(value)
        return {"installed": True, "name": name, "variable": "GENROUTER_API_KEY"}

    def reveal_key(self, name):
        value = self.state.get("keys", {}).get(name)
        if not value:
            raise ValueError("No locally stored key with this name")
        return value

    def fund_key(self, key_id, amount_usd, operation_id=None):
        amount = usd_to_micro(amount_usd, positive=True)
        rows = self.profile()["keys"]
        if not any(str(row.get("id")) == str(key_id) and row.get("is_active") is not False for row in rows):
            raise ValueError("Select an active key belonging to this account")
        identifier = str(key_id)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", identifier):
            raise ValueError("Invalid key id")
        previous = self.state.get("last_fund_operation", {})
        if previous.get("pending"):
            if previous.get("key_id") != identifier or previous.get("amount_micro") != amount or (operation_id and previous.get("operation_id") != operation_id):
                raise ValueError("Uncertain transfer: repeat the same key, amount and operation_id before starting another transfer.")
            operation_id = previous["operation_id"]
        operation_id = str(uuid.UUID(operation_id)) if operation_id else str(uuid.uuid4())
        if previous.get("operation_id") == operation_id and (previous.get("key_id") != identifier or previous.get("amount_micro") != amount):
            raise ValueError("An operation_id cannot be reused for another amount or key")
        self.state["last_fund_operation"] = {"operation_id": operation_id, "key_id": identifier, "amount_micro": amount, "pending": True}
        self._save()
        self.request(f"/keys/{identifier}/fund", "POST", {"amount_micro": amount, "operation_id": operation_id})
        self.state["last_fund_operation"]["pending"] = False
        self._save()
        return {"funded": True, "key_id": identifier, "amount_usd": micro_to_usd(amount), "operation_id": operation_id}

    def models(self):
        if self.jar:
            data = self.request("/models")
            rows = data.get("models") if isinstance(data, dict) else None
        else:
            key = os.environ.get("GENROUTER_API_KEY")
            if not key:
                raise GenRouterError("Sign in or configure GENROUTER_API_KEY to list models")
            data = self._http(INFERENCE + "/models", api_key=key, cabinet=False)
            rows = data.get("data") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise GenRouterError("Unexpected model catalog schema")
        return [{field: row[field] for field in ("id", "name", "owner", "kind", "context_length") if field in row}
                for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str)]

    def payment_status(self):
        data = self.request("/config")
        return {"server_enabled": data.get("payments_enabled") is True,
                "plugin_enabled": os.environ.get("GENROUTER_ENABLE_CHECKOUT") == "1",
                "processing_verified": False, "dashboard_url": PORTAL + "/dashboard/overview"}

    def checkout(self, amount_usd, method, confirmed=False):
        if not confirmed or os.environ.get("GENROUTER_ENABLE_CHECKOUT") != "1":
            raise ValueError("Checkout is experimental and disabled by default; explicitly enable it and confirm the amount")
        amount = usd_to_micro(amount_usd, positive=True)
        if method not in {"card", "crypto"}:
            raise ValueError("Choose card or crypto")
        if not self.payment_status()["server_enabled"]:
            raise GenRouterError("GenRouter has not enabled payments")
        data = self.request("/payments/topup", "POST", {"amount_micro": amount, "provider": "platega",
                                                       "method": 2 if method == "card" else 13})
        url = data.get("payment_url") if isinstance(data, dict) else None
        if not isinstance(url, str) or urlparse(url).scheme != "https" or not urlparse(url).hostname:
            raise GenRouterError("Checkout has no valid HTTPS payment URL; inspect the cabinet before retrying")
        if urlparse(url).username or urlparse(url).password:
            raise GenRouterError("Checkout returned an unsafe payment URL")
        return {"payment_url": url, "amount_usd": micro_to_usd(amount), "method": method,
                "payment_complete": False}

    def probe(self, model):
        key = os.environ.get("GENROUTER_API_KEY")
        if not key:
            raise GenRouterError("Configure GENROUTER_API_KEY before testing inference")
        data = self._http(INFERENCE + "/chat/completions", "POST", {
            "model": model, "messages": [{"role": "user", "content": "Reply only: GENROUTER_OK"}],
            "max_tokens": 16, "stream": False,
        }, api_key=key, cabinet=False)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise GenRouterError("Inference returned no assistant message") from None
        if not isinstance(content, str) or content.strip() != "GENROUTER_OK":
            raise GenRouterError("The endpoint responded, but did not return the expected GENROUTER_OK marker")
        return {"ok": True, "endpoint": INFERENCE, "requested_model": model,
                "returned_model": data.get("model"), "reply": "GENROUTER_OK", "fallback_used": False}
