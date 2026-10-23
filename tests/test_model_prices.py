"""Offline catalog-price contracts based on the GenRouter cabinet fields."""

import argparse
import http.cookiejar
import json
import unittest
from unittest.mock import patch

from account import models, slash
from account.cli import execute, setup_parser
from account.client import Client, safe_model
from test_plugin import MemoryStore


class ModelPricesTests(unittest.TestCase):
    def test_token_prices_match_cabinet_units_without_rounding(self):
        row = safe_model({
            "id": "example/text", "kind": "text", "context_length": 100000,
            "input_micro_per_million": 21000,
            "cached_input_micro_per_million": "2100",
            "output_micro_per_million": 42000,
            "credential": "must-not-escape",
        })
        self.assertEqual(row["pricing"], {
            "currency": "USD", "approximate": True,
            "input_usd_per_million_tokens": "0.021",
            "cached_input_usd_per_million_tokens": "0.0021",
            "output_usd_per_million_tokens": "0.042",
        })
        self.assertEqual(row["price_display"],
                         "Input ≈ $0.021 / 1M tokens; Cache ≈ $0.0021 / 1M tokens; "
                         "Output ≈ $0.042 / 1M tokens")
        self.assertEqual(row["context_length"], 100000)
        self.assertNotIn("must-not-escape", json.dumps(row))

    def test_media_prices_are_per_image_or_second_not_tokens(self):
        for unit, value, expected in (("image", 30000, "0.03"),
                                      ("second", "150000", "0.15")):
            with self.subTest(unit=unit):
                row = safe_model({"id": "example/media", "media_unit": unit,
                                  "media_micro_per_unit": value,
                                  "input_micro_per_million": None,
                                  "output_micro_per_million": None})
                self.assertEqual(row["pricing"]["usd_per_" + unit], expected)
                self.assertEqual(row["price_display"], f"≈ ${expected} / {unit}")
                self.assertNotIn("tokens", row["price_display"])

    def test_zero_is_free_and_cache_price_is_not_invented(self):
        row = safe_model({"id": "example/free", "input_micro_per_million": 0,
                          "output_micro_per_million": "0"})
        self.assertEqual(row["pricing"]["input_usd_per_million_tokens"], "0")
        self.assertIn("Output ≈ $0 / 1M tokens", row["price_display"])
        self.assertNotIn("cached_input_usd_per_million_tokens", row["pricing"])

    def test_missing_or_invalid_rates_are_not_misrepresented_as_free(self):
        for value in (None, -1, True, False, "", "NaN", "Infinity", "1e30",
                      0.5, {}, [5], "secret-value"):
            with self.subTest(value=value):
                row = safe_model({"id": "example/unknown",
                                  "input_micro_per_million": value,
                                  "output_micro_per_million": value})
                self.assertEqual(row["pricing"], {"currency": "USD", "approximate": True})
                self.assertIn("Price unavailable", row["price_display"])
                self.assertNotIn("$0", row["price_display"])

    def test_partial_token_rates_and_unknown_media_units(self):
        row = safe_model({"id": "example/partial", "input_micro_per_million": 1})
        self.assertIn("Input ≈ $0.000001 / 1M tokens", row["price_display"])
        self.assertIn("Output: price unavailable", row["price_display"])
        for unit in (None, "request", "secret-value"):
            row = safe_model({"id": "example/media", "media_unit": unit,
                              "media_micro_per_unit": 10000})
            self.assertIn("Price unavailable", row["price_display"])
            self.assertNotIn("usd_per_" + str(unit), row["pricing"])

    def test_cabinet_catalog_cli_slash_and_tool_share_prices(self):
        client = Client(MemoryStore())
        client.jar.set_cookie(http.cookiejar.Cookie(
            0, "session", "example", None, False, "genrouter.ru", False,
            False, "/", True, True, None, True, None, None, {}))
        catalog = {"models": [{"id": "example/text", "kind": "text",
                               "input_micro_per_million": 3000000,
                               "output_micro_per_million": 15000000},
                              None, {"id": 42}]}
        with patch.object(client, "request", return_value=catalog) as request:
            expected = client.models()
            request.assert_called_once_with("/models")
            self.assertEqual(len(expected), 1)
            parser = argparse.ArgumentParser()
            setup_parser(parser)
            args = parser.parse_args(["models"])
            self.assertEqual(execute(client, args), expected)
            with patch("account.Client", return_value=client):
                self.assertEqual(json.loads(slash("models")), expected)
                self.assertEqual(json.loads(models()), expected)
        self.assertEqual(expected[0]["id"], "example/text")
        self.assertIn("Input ≈ $3 / 1M tokens", expected[0]["price_display"])

    def test_key_only_catalog_keeps_available_rates_and_marks_missing_prices(self):
        client = Client(MemoryStore())
        for extra in ({}, {"input_micro_per_million": 1000000,
                          "output_micro_per_million": 2000000}):
            with self.subTest(extra=extra), patch.dict(
                    "os.environ", {"GENROUTER_API_KEY": "example-key"}), patch.object(
                    client, "_http", return_value={"data": [{"id": "example/text", **extra}]}):
                row = client.models()[0]
                self.assertEqual(row["id"], "example/text")
                if extra:
                    self.assertIn("Input ≈ $1 / 1M tokens", row["price_display"])
                else:
                    self.assertIn("hermes genrouter login", row["price_display"])


if __name__ == "__main__":
    unittest.main()
