import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


class ProviderTests(unittest.TestCase):
    def test_catalog_package_registers_provider_without_account_features(self):
        provider_module, base = ModuleType("providers"), ModuleType("providers.base")
        seen = []
        provider_module.register_provider = seen.append
        base.ProviderProfile = type("ProviderProfile", (), {"__init__": lambda self, **kwargs: self.__dict__.update(kwargs)})
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location("_genrouter_catalog_provider", root / "catalog" / "__init__.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"providers": provider_module, "providers.base": base}):
            spec.loader.exec_module(module)

        profile = seen[0]
        self.assertEqual(profile.name, "genrouter-ru")
        self.assertEqual(profile.env_vars, ("GENROUTER_API_KEY",))
        self.assertEqual(profile.base_url, "https://api.genrouter.ru/v1")
        self.assertFalse(hasattr(profile, "classify_api_error"))
        self.assertEqual(profile.signup_url, "https://genrouter.ru/?ref=d97a170843")

    def test_native_callback_preserves_debug_metadata_and_excludes_sdk_body(self):
        provider_module, base = ModuleType("providers"), ModuleType("providers.base")
        seen = []
        provider_module.register_provider = seen.append
        base.ProviderProfile = type("ProviderProfile", (), {"__init__": lambda self, **kwargs: self.__dict__.update(kwargs)})
        root = Path(__file__).resolve().parents[1]
        name = "_genrouter_test_provider"
        spec = importlib.util.spec_from_file_location(name, root / "__init__.py",
                                                     submodule_search_locations=[str(root)])
        module = importlib.util.module_from_spec(spec)
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HERMES_HOME": home}):
            with patch.dict(sys.modules, {"providers": provider_module, "providers.base": base, name: module}):
                spec.loader.exec_module(module)
                profile = seen[0]
                self.assertEqual(profile.base_url, "https://api.genrouter.ru/v1")
                error = RuntimeError("SENSITIVE_PROMPT_AND_SDK_RESPONSE")
                error.response = SimpleNamespace(headers={"x-request-id": "request-example", "retry-after": "60"})
                result = profile.classify_api_error(error, status_code=429, error_code="rate_limit_exceeded",
                                                   model="openai/example")
                self.assertIsNone(result)  # Generic Hermes classification/failover remains intact.
                paths = list((Path(home) / "plugin-data" / "genrouter-account" / "reports").glob("*.json"))
                self.assertEqual(len(paths), 1)
                raw = paths[0].read_text(encoding="utf-8")
                self.assertNotIn("SENSITIVE_PROMPT_AND_SDK_RESPONSE", raw)
                report = json.loads(raw)
                self.assertEqual(report["diagnostics"]["request_id"], "request-example")
                self.assertEqual(report["diagnostics"]["model"], "openai/example")

    def test_isolated_host_error_without_traceback_is_recorded(self):
        from account.reports import capture
        with tempfile.TemporaryDirectory() as home:
            opaque = SimpleNamespace(type_name="APIStatusError", text="SENSITIVE_SDK_BODY")
            report = capture(opaque, action="inference", home=home,
                             metadata={"status": 402, "request_id": "req-host"},
                             message_override="APIStatusError: GenRouter inference failed")
            self.assertEqual(report["exception"], "APIStatusError")
            self.assertEqual(report["stack"], [])
            self.assertEqual(report["diagnostics"]["request_id"], "req-host")
            self.assertNotIn("SENSITIVE_SDK_BODY", json.dumps(report))
