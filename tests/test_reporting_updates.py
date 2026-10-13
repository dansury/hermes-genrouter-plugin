import argparse
import base64
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from account import reports, updates
from account.cli import report_command, setup_parser
from account.client import GenRouterError, INFERENCE
from test_plugin import RecordedClient, MemoryStore, Client


class ContractTests(unittest.TestCase):
    def test_nickname_and_password_rules_reject_before_signup(self):
        for nick in ("abc", "a-bcd", "яname", "a" * 33):
            with self.assertRaises(ValueError):
                RecordedClient().register_account(nick, "Example123", True)
        for password in ("lettersOnly", "123456789", "Ab123", "A1" * 65):
            with self.assertRaises(ValueError):
                RecordedClient().register_account("good_name", password, True)

    def test_verified_email_login_keeps_canonical_owner(self):
        client = RecordedClient()
        client.state.update(nickname="example", keys={"Hermes": "private-key"})
        client.login("confirmed@example.test", "Example123")
        self.assertEqual(client.state["nickname"], "example")
        self.assertEqual(client.calls[0][2]["nickname"], "confirmed@example.test")

    def test_signup_lost_response_does_not_repeat_mutation(self):
        client = RecordedClient()
        with patch.object(client, "request", side_effect=GenRouterError("timeout")) as request:
            with self.assertRaises(GenRouterError):
                client.register_account("example", "Example123", True)
            with self.assertRaises(ValueError):
                client.register_account("example", "Example123", True)
        self.assertEqual(request.call_count, 1)

    def test_transfer_timeout_reuses_uuid_and_exact_body(self):
        client = RecordedClient()
        bodies = []
        def request(path, method="GET", payload=None):
            if path == "/profile":
                return {"user": {}, "keys": [{"id": 1, "is_active": True}]}
            bodies.append(payload)
            if len(bodies) == 1:
                raise GenRouterError("timeout")
            return {"ok": True}
        with patch.object(client, "request", side_effect=request):
            with self.assertRaises(GenRouterError):
                client.fund_key(1, "2.03")
            with self.assertRaises(ValueError):
                client.fund_key(1, "3")
            client.fund_key(1, "2.03")
        self.assertEqual(bodies[0], bodies[1])
        self.assertFalse(client.state["last_fund_operation"]["pending"])

    def test_key_creation_lost_response_blocks_another_key(self):
        client = RecordedClient()
        def request(path, method="GET", payload=None):
            if path == "/profile":
                return {"user": {}, "keys": []}
            raise GenRouterError("timeout")
        with patch.object(client, "request", side_effect=request) as request:
            with self.assertRaises(GenRouterError):
                client.create_key("Hermes")
            with self.assertRaises(ValueError):
                client.create_key("Hermes2")
        self.assertEqual(sum(c.args[0] == "/keys" for c in request.call_args_list), 1)

    def test_rotation_invalidates_only_with_confirmation_and_never_retries(self):
        client = RecordedClient()
        with self.assertRaises(ValueError):
            client.rotate_key(1)
        with patch.object(client, "profile", return_value={"keys": [{"id": 1, "name": "Hermes"}]}):
            with patch.object(client, "request", side_effect=GenRouterError("lost")) as request:
                with self.assertRaises(GenRouterError):
                    client.rotate_key(1, confirmed=True)
                with self.assertRaises(ValueError):
                    client.rotate_key(1, confirmed=True)
                self.assertEqual(request.call_count, 1)

    def test_402_keeps_reason_and_request_id_without_refill_advice(self):
        client = Client(MemoryStore())
        error = HTTPError(INFERENCE + "/chat/completions", 402, "upstream", {"x-request-id": "req-abc"},
                          io.BytesIO(b'{"error":{"code":"upstream_billing","message":"Supplier unavailable"}}'))
        with patch("account.client.build_opener") as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaises(GenRouterError) as caught:
                client._http(INFERENCE + "/chat/completions", cabinet=False)
        self.assertEqual(caught.exception.request_id, "req-abc")
        self.assertEqual(caught.exception.error_code, "upstream_billing")
        self.assertIn("Supplier unavailable", str(caught.exception))
        self.assertNotIn("Check key funding", str(caught.exception))


class ReportTests(unittest.TestCase):
    def test_capture_is_local_deduplicates_and_removes_secrets(self):
        with tempfile.TemporaryDirectory() as home, patch("account.reports.github_api") as api:
            with patch.dict(os.environ, {"SOME_API_KEY": "arbitrary-secret"}):
                message = 'password="private-password"; Bearer arbitrary-secret; user@example.test; genrouter_session=cookie123'
                first = reports.capture(GenRouterError(message, 402), "probe", home=home)
                second = reports.capture(GenRouterError(message, 402), "probe", home=home)
            api.assert_not_called()
            self.assertEqual(first["fingerprint"], second["fingerprint"])
            self.assertEqual(second["occurrences"], 2)
            text = reports.render(second)
            for secret in ("private-password", "arbitrary-secret", "user@example.test", "cookie123"):
                self.assertNotIn(secret, text)

    def test_distinct_validation_errors_have_different_fingerprints(self):
        with tempfile.TemporaryDirectory() as home:
            a = reports.capture(ValueError("Invalid nickname"), "setup", home=home)
            b = reports.capture(ValueError("Invalid password"), "setup", home=home)
            self.assertNotEqual(a["fingerprint"], b["fingerprint"])

    def test_submission_without_consent_never_calls_github(self):
        with tempfile.TemporaryDirectory() as home, patch("account.reports.github_api") as api:
            report = reports.capture(description="Manual issue", home=home)
            with self.assertRaises(ValueError):
                reports.submit(report, reports.render(report), home=home)
            api.assert_not_called()

    def test_duplicate_closed_issue_is_reused_without_post(self):
        with tempfile.TemporaryDirectory() as home:
            report = reports.capture(description="Manual issue", home=home)
            row = {"body": reports.render(report), "html_url": "https://github.com/example/issues/1", "state": "closed"}
            with patch("account.reports.github_api", return_value=[row]) as api:
                result = reports.submit(report, reports.render(report), consent=True, home=home)
            self.assertEqual(api.call_count, 1)
            self.assertEqual(result["issue_url"], row["html_url"])

    def test_timed_out_post_is_not_retried(self):
        with tempfile.TemporaryDirectory() as home:
            report = reports.capture(description="Manual issue", home=home)
            with patch("account.reports.github_api", side_effect=[[], TimeoutError()]) as api:
                with self.assertRaises(TimeoutError):
                    reports.submit(report, reports.render(report), consent=True, home=home)
            self.assertEqual(api.call_count, 2)

    def test_declined_cli_report_has_no_network_or_email(self):
        with tempfile.TemporaryDirectory() as home:
            report = reports.capture(description="Manual issue", home=home)
            parser = argparse.ArgumentParser()
            setup_parser(parser)
            args = parser.parse_args(["report", "send"])
            with patch("account.cli.load_report", return_value=report), patch("account.cli.submit") as send:
                with patch("account.cli.sys.stdin.isatty", return_value=True), patch("builtins.input", return_value="no"):
                    with patch("sys.stdout", new=io.StringIO()):
                        result = report_command(args)
            self.assertFalse(result["sent"])
            send.assert_not_called()

    def test_github_identity_offer_and_email_fallback(self):
        with tempfile.TemporaryDirectory() as home:
            report = reports.capture(description="Manual issue", home=home)
            parser = argparse.ArgumentParser()
            setup_parser(parser)
            args = parser.parse_args(["report", "send", "--confirm"])
            with patch("account.cli.load_report", return_value=report), patch("account.cli.personal_identity", return_value="myuser"):
                with patch("account.cli.sys.stdin.isatty", return_value=True), patch("builtins.input", return_value="yes"):
                    with patch("account.cli.submit", side_effect=TimeoutError()) as submit, patch("account.cli.email_draft", return_value={"sent": False, "hint": ""}):
                        with patch("sys.stdout", new=io.StringIO()):
                            result = report_command(args)
            self.assertEqual(submit.call_args.kwargs["identity"], "personal")
            self.assertTrue(result["github_failed"])
            self.assertFalse(result["sent"])

    def test_email_fallback_is_complete_draft_and_never_sends(self):
        with tempfile.TemporaryDirectory() as home:
            report = reports.capture(description="Manual issue", home=home)
            body = reports.render(report)
            result = reports.email_draft(report, body, home=home)
            self.assertFalse(result["sent"])
            self.assertIn("dansury@gmail.com", Path(result["email_draft"]).read_text())


class UpdateTests(unittest.TestCase):
    def test_default_daily_check_cached_and_disable_supported(self):
        source = base64.b64encode(b"version: 0.4.0\n").decode()
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {}, clear=True):
            with patch("account.updates.github_api", return_value={"content": source}) as api:
                result = updates.check_updates(home=home)
                self.assertTrue(result["update_available"])
                self.assertEqual(result["interval_hours"], 24)
                updates.check_updates(home=home)
                self.assertEqual(api.call_count, 2)
                with patch.dict(os.environ, {"GENROUTER_UPDATE_CHECK_HOURS": "0"}):
                    updates.check_updates(home=home)
                    self.assertEqual(api.call_count, 2)

    def test_update_failure_recorded_locally_without_report_submission(self):
        with tempfile.TemporaryDirectory() as home, patch("account.updates.github_api", side_effect=TimeoutError()):
            with patch("account.reports.github_api") as api:
                result = updates.check_updates(force=True, home=home)
                self.assertTrue(result["check_failed"])
                api.assert_not_called()
                self.assertEqual(len(reports.pending(home)), 1)
