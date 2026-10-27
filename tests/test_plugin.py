import argparse
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from account import register
from account.cli import execute, setup_parser
from account.client import (Client, GenRouterError, NoRedirects, REFERRAL_CODE,
                            REFERRAL_URL, referral_url, safe_key, usd_to_micro)
from account.storage import SecretStore


class MemoryStore:
    def __init__(self):
        self.state = {"cookies": [], "keys": {}}
        self.installed = None

    def load(self):
        return self.state

    def save(self, state):
        self.state = state

    def install_key(self, value):
        self.installed = value


class RecordedClient(Client):
    def __init__(self):
        super().__init__(MemoryStore())
        self.calls = []

    def request(self, path, method="GET", payload=None):
        self.calls.append((path, method, payload))
        if path == "/profile":
            return {"user": {"wallet_micro": "4000000", "nickname": "example"}, "keys": []}
        if path == "/keys":
            return {"key": "example-only-key-secret"}
        if path == "/config":
            return {"payments_enabled": True}
        if path == "/payments/topup":
            return {"payment_url": "https://payments.example.test/checkout/1"}
        return {"ok": True}


class ClientTests(unittest.TestCase):
    def test_signup_requires_terms_and_uses_nickname_contract(self):
        client = RecordedClient()
        with self.assertRaises(ValueError):
            client.register_account("example", "example-pass-123")
        self.assertEqual(client.calls, [])
        client.register_account("example", "example-pass-123", accepted_terms=True)
        self.assertEqual(client.calls[0], ("/auth/register", "POST", {"nickname": "example", "password": "example-pass-123"}))
        self.assertNotIn("password", json.dumps(client.state))
        cookie = next(cookie for cookie in client.jar if cookie.name == "linali_ref")
        self.assertEqual(cookie.value, "d97a170843")
        self.assertEqual(cookie.domain, "genrouter.ru")
        self.assertEqual(cookie.path, "/")
        self.assertTrue(cookie.secure)
        from urllib.request import Request
        request = Request("https://genrouter.ru/dashboard/api/auth/register")
        client.jar.add_cookie_header(request)
        self.assertIn("linali_ref=d97a170843", request.get_header("Cookie"))

    def test_referral_links_preserve_destination_and_reject_external_hosts(self):
        self.assertEqual(REFERRAL_CODE, "d97a170843")
        self.assertEqual(REFERRAL_URL, "https://genrouter.ru/?ref=d97a170843")
        self.assertEqual(referral_url(), REFERRAL_URL)
        self.assertEqual(referral_url("/legal/offer"),
                         "https://genrouter.ru/legal/offer?ref=d97a170843")
        self.assertEqual(referral_url("/dashboard/cabinet.js?v=50"),
                         "https://genrouter.ru/dashboard/cabinet.js?v=50&ref=d97a170843")
        for path in ("//attacker.example/path", "https://attacker.example/path", "/../path"):
            with self.assertRaises(ValueError):
                referral_url(path)

    def test_email_confirmation_is_separate(self):
        client = RecordedClient()
        client.request_email("user@example.test")
        client.confirm_email("123456")
        self.assertEqual(client.calls[0][2], {"email": "user@example.test"})
        self.assertEqual(client.calls[1][2], {"code": "123456"})
        with self.assertRaises(ValueError):
            client.confirm_email("１２３４５６")

    def test_key_secret_saved_but_not_returned(self):
        client = RecordedClient()
        result = client.create_key("Cursor", "1.25", "00000000-0000-4000-8000-000000000001")
        request = next(row for row in client.calls if row[0] == "/keys")
        self.assertEqual(request[2]["allocate_micro"], 1250000)
        self.assertNotIn("example-only-key-secret", json.dumps(result))
        self.assertEqual(client.state["keys"]["Cursor"], "example-only-key-secret")
        self.assertEqual(client.use_key("Cursor")["installed"], True)

    def test_duplicate_service_name_cannot_create_another_key(self):
        client = RecordedClient()
        with patch.object(client, "profile", return_value={"keys": [{"name": "Cursor"}]}):
            with self.assertRaises(ValueError):
                client.create_key("Cursor")
        self.assertFalse(any(row[0] == "/keys" for row in client.calls))

    def test_different_account_cannot_reuse_stored_application_keys(self):
        client = RecordedClient()
        client.state.update({"nickname": "first-account", "keys": {"Hermes": "example-only-key"}})
        with self.assertRaises(ValueError):
            client.login("second-account", "example-password")
        self.assertEqual(client.calls, [])

    def test_read_requests_do_not_overwrite_a_concurrent_new_key(self):
        client = Client(MemoryStore())
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, size):
                return b'{"payments_enabled": false}'
        with patch.object(client.opener, "open", return_value=Response()):
            with patch.object(client, "_save") as save:
                self.assertFalse(client.payment_status()["server_enabled"])
                save.assert_not_called()

    def test_money_precision_and_invalid_amounts(self):
        self.assertEqual(usd_to_micro("0.000001"), 1)
        self.assertEqual(usd_to_micro(Decimal("2.03")), 2030000)
        for value in ("NaN", "Infinity", "-1", "0.0000001"):
            with self.assertRaises(ValueError):
                usd_to_micro(value)

    def test_balances_do_not_invent_rate_limits_or_reveal_secrets(self):
        data = safe_key({"id": 12, "key": "example-only-secret", "balance_micro": "1234567", "reserved_micro": "100", "spent_micro": None})
        self.assertEqual(data["available_usd"], "1.234567")
        self.assertEqual(data["reserved_usd"], "0.0001")
        self.assertIsNone(data["spent_usd"])
        self.assertIsNone(data["rate_limits"])
        self.assertNotIn("key", data)

    def test_checkout_disabled_without_two_explicit_gates(self):
        client = RecordedClient()
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                client.checkout("5", "card", confirmed=True)
        with patch.dict(os.environ, {"GENROUTER_ENABLE_CHECKOUT": "1"}):
            with self.assertRaises(ValueError):
                client.checkout("5", "card", confirmed=False)
            result = client.checkout("5", "card", confirmed=True)
        self.assertFalse(result["payment_complete"])
        self.assertEqual(client.calls[-1][2], {"amount_micro": 5000000, "provider": "platega", "method": 2})

    def test_checkout_rejects_non_https_url(self):
        client = RecordedClient()
        with patch.dict(os.environ, {"GENROUTER_ENABLE_CHECKOUT": "1"}):
            with patch.object(client, "request", side_effect=[{"payments_enabled": True}, {"payment_url": "http://example.test"}]):
                with self.assertRaises(GenRouterError):
                    client.checkout("5", "card", confirmed=True)

    def test_http_errors_never_echo_server_secrets_or_fallback(self):
        client = Client(MemoryStore())
        error = HTTPError("https://api.genrouter.ru/v1/chat/completions", 402, "Payment", {}, io.BytesIO(b'private-body'))
        with patch.dict(os.environ, {"GENROUTER_API_KEY": "example-only-key"}):
            with patch("account.client.build_opener") as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaises(GenRouterError) as caught:
                    client.probe("example-model")
                self.assertEqual(opener.return_value.open.call_count, 1)
        self.assertEqual(caught.exception.status, 402)
        self.assertNotIn("private-body", str(caught.exception))

    def test_no_credential_redirects(self):
        self.assertIsNone(NoRedirects().redirect_request(None, None, 302, "", {}, "https://attacker.example.test"))
        client = Client(MemoryStore())
        for url in ("http://genrouter.ru/test", "https://genrouter.ru.attacker.test/v1", "https://user@genrouter.ru/test"):
            with self.assertRaises(ValueError):
                client._http(url, api_key="example-only-secret")

    def test_probe_checks_expected_reply_not_merely_http_status(self):
        client = Client(MemoryStore())
        with patch.dict(os.environ, {"GENROUTER_API_KEY": "example-only-key"}):
            with patch.object(client, "_http", return_value={"choices": [{"message": {"content": "wrong"}}]}):
                with self.assertRaises(GenRouterError):
                    client.probe("example-model")
            with patch.object(client, "_http", return_value={"model": "example-model", "choices": [{"message": {"content": "GENROUTER_OK"}}]}):
                self.assertFalse(client.probe("example-model")["fallback_used"])

    def test_unrecognized_profile_shape_fails_clearly(self):
        client = Client(MemoryStore())
        with patch.object(client, "request", return_value={"user": {}, "different_keys": []}):
            with self.assertRaises(GenRouterError):
                client.profile()


class StorageTests(unittest.TestCase):
    def test_store_roundtrip_and_windows_encryption(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SecretStore(directory)
            state = {"cookies": [], "keys": {"Hermes": "example-only-secret"}}
            store.save(state)
            self.assertEqual(store.load(), state)
            raw = store.path.read_text()
            self.assertNotIn("example-only-secret", raw)
            if os.name == "nt":
                self.assertEqual(json.loads(raw)["format"], "dpapi-v1")
            else:
                self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)

    def test_env_update_preserves_other_services(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SecretStore(directory)
            path = Path(directory) / ".env"
            path.write_text("# keep comment\nOTHER_SERVICE=example-only-other\nGENROUTER_API_KEY=old\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                store.install_key("example-only-new")
            data = path.read_text()
            self.assertIn("OTHER_SERVICE=example-only-other", data)
            self.assertIn("# keep comment", data)
            self.assertEqual(data.count("GENROUTER_API_KEY="), 1)
            self.assertNotIn("=old", data)


class IntegrationTests(unittest.TestCase):
    def test_companion_registers_cli_slash_and_only_read_tools(self):
        class Context:
            def __init__(self):
                self.tools, self.commands, self.cli = [], [], []
            def register_tool(self, **kwargs):
                self.tools.append(kwargs)
            def register_command(self, *args, **kwargs):
                self.commands.append(args[0])
            def register_cli_command(self, **kwargs):
                self.cli.append(kwargs["name"])
        context = Context()
        with patch("account.updates.start_checks"):
            register(context)
        self.assertEqual(context.cli, ["genrouter"])
        self.assertEqual(context.commands, ["genrouter"])
        self.assertEqual(len(context.tools), 3)
        self.assertFalse(any("create" in row["name"] for row in context.tools))

    def test_cli_confirm_flag_does_not_put_secrets_in_arguments(self):
        parser = argparse.ArgumentParser()
        setup_parser(parser)
        args = parser.parse_args(["keys", "create", "--name", "Cursor", "--confirm"])
        result = execute(RecordedClient(), args)
        self.assertTrue(result["created"])
        self.assertNotIn("password", vars(args))


if __name__ == "__main__":
    unittest.main()
