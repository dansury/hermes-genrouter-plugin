"""Exercise the provider and tool interfaces without credentials or network calls."""
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

import account


class Profile:
    def __init__(self, **fields):
        self.__dict__.update(fields)


def load_catalog():
    providers, base = ModuleType("providers"), ModuleType("providers.base")
    providers.register_provider = Mock()
    base.ProviderProfile = Profile
    path = Path(__file__).resolve().parents[1] / "catalog" / "__init__.py"
    spec = importlib.util.spec_from_file_location("_catalog_compatibility", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"providers": providers, "providers.base": base}):
        spec.loader.exec_module(module)
    return module


class CompatibilityTests(unittest.TestCase):
    def test_live_catalog_formats_and_context(self):
        catalog = load_catalog()
        rows = [
            {"id": "anthropic/example", "type": "text"},
            {"id": "openai/example", "capabilities": {"type": "chat"}},
            {"id": "openai/example"},
            {"id": "image/example", "type": "image"},
            {"id": "audio/example", "capabilities": {"type": "audio"}},
            None, {"id": 42},
        ]
        for payload in ({"data": rows}, {"models": rows}, rows):
            opener = Mock()
            opener.open.return_value = io.BytesIO(json.dumps(payload).encode())
            with patch.object(catalog, "build_opener", return_value=opener):
                result = catalog.profile.fetch_models(api_key="test-only", task_id="context")
            self.assertEqual(result, ["anthropic/example", "openai/example",
                                      "image/example", "audio/example"])
            request = opener.open.call_args.args[0]
            self.assertEqual(request.full_url, "https://api.genrouter.ru/v1/models")
            self.assertEqual(request.get_header("Authorization"), "Bearer test-only")

    def test_failed_listing_falls_back_without_requesting_inference(self):
        catalog = load_catalog()
        with patch.object(catalog, "build_opener") as build:
            self.assertIsNone(catalog.profile.fetch_models())
            self.assertIsNone(catalog.profile.fetch_models(api_key="test", base_url="http://example.test"))
            build.assert_not_called()
            build.return_value.open.side_effect = OSError("offline")
            self.assertIsNone(catalog.profile.fetch_models(api_key="test"))
        self.assertIsNone(catalog._NoRedirects().redirect_request(None, None, 302, "", {}, "https://example.test"))
        for raw in (b"invalid-json", b'{"unexpected": []}', b"null", b"x" * 2_000_001):
            with patch.object(catalog, "build_opener") as build:
                build.return_value.open.return_value = io.BytesIO(raw)
                self.assertIsNone(catalog.profile.fetch_models(api_key="test"))

    def test_registered_tools_accept_hermes_positional_arguments(self):
        context = Mock()
        with patch("account.updates.start_checks"):
            account.register(context)
        for call, action in zip(context.register_tool.call_args_list, ("status", "key_balances", "models")):
            handler = call.kwargs["handler"]
            with patch("account._read", return_value="result") as read:
                self.assertEqual(handler({}, task_id="task", session_id="session"), "result")
                self.assertEqual(handler(), "result")
                read.assert_called_with(action)


if __name__ == "__main__":
    unittest.main()
