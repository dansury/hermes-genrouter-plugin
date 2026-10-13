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


PORTAL = "https://genrouter.ru"
INFERENCE = "https://genrouter.ru/v1"
KEY_FIELDS = ("id", "name", "key_prefix", "is_active", "balance_micro",
              "reserved_micro", "spent_micro", "request_count", "created_at")


class GenRouterError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def redact(text):
    return re.sub(r"sk-[A-Za-z0-9_.-]+", "[redacted]", str(text))


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
    result["rate_limits"] = None  # This API exposes money, not RPM/TPM limits.
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
        headers = {"Accept": "application/json", "User-Agent": "hermes-genrouter-plugin/0.2.0"}
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
            # Do not echo a server-controlled body: it may contain credentials or account data.
            advice = {
                401: "Sign in with 'hermes genrouter login' or check the inference API key.",
                402: "Insufficient key balance or a billing restriction. Check key funding in the cabinet.",
                403: "Access denied. The cabinet API may require a changed authentication contract.",
                404: "Endpoint unavailable; the cabinet API may have changed or payments may be disabled.",
                409: "Conflict. Check existing account/key state before retrying.",
                429: "Rate limited. Wait before retrying; do not create keys to bypass limits.",
            }.get(error.code, "Request failed. Check the GenRouter cabinet for details.")
            raise GenRouterError(f"GenRouter HTTP {error.code}. {advice}", error.code) from None
        except (URLError, socket.timeout, TimeoutError):
            raise GenRouterError("Network request failed. A mutation may have completed; check the cabinet before retrying.") from None
        except (ValueError, UnicodeDecodeError):
            raise GenRouterError("GenRouter returned an unexpected response format") from None
        if cabinet and method != "GET":
            self._save()
        return data

    def request(self, path, method="GET", payload=None):
        if not path.startswith("/") or ".." in path or "?" in path:
            raise ValueError("Invalid API path")
        return self._http(PORTAL + "/dashboard/api" + path, method, payload)

    def register_account(self, nickname, password, accepted_terms=False):
        if not accepted_terms:
            raise ValueError("Accept GenRouter's terms before creating an account")
        if not nickname.strip() or len(password) < 8:
            raise ValueError("Provide a nickname and a password of at least eight characters")
        self._check_account(nickname)
        result = self.request("/auth/register", "POST", {"nickname": nickname.strip(), "password": password})
        self.state["nickname"] = nickname.strip()
        self._save()
        return result

    def _check_account(self, nickname):
        previous = self.state.get("nickname")
        if previous and previous != nickname.strip() and self.state.get("keys"):
            raise ValueError("This Hermes profile already stores another account's keys. Use a separate Hermes profile for a different account.")

    def login(self, nickname, password):
        self._check_account(nickname)
        result = self.request("/auth/login", "POST", {"nickname": nickname, "password": password})
        self.state["nickname"] = nickname.strip()
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
        if any(row.get("name") == name for row in self.profile()["keys"]):
            raise ValueError("A key with this name already exists; use another service-specific name")
        allocation = usd_to_micro(allocate_usd)
        operation_id = str(uuid.UUID(operation_id)) if operation_id else str(uuid.uuid4())
        # Save the id before the request so an ambiguous network failure can be investigated.
        self.state["last_key_operation"] = {"operation_id": operation_id, "name": name}
        self._save()
        data = self.request("/keys", "POST", {"name": name, "allocate_micro": allocation,
                                               "operation_id": operation_id})
        if not isinstance(data, dict) or not isinstance(data.get("key"), str) or not data["key"]:
            raise GenRouterError("Key creation response has no key. Check the cabinet before retrying.")
        self.state.setdefault("keys", {})[name] = data["key"]
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
        operation_id = str(uuid.UUID(operation_id)) if operation_id else str(uuid.uuid4())
        self.state["last_fund_operation"] = {"operation_id": operation_id, "key_id": identifier}
        self._save()
        self.request(f"/keys/{identifier}/fund", "POST", {"amount_micro": amount, "operation_id": operation_id})
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
