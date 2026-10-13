"""Hermes account companion: terminal wizard, read-only agent tools and slash command."""

import json

from .client import Client, GenRouterError, redact


def _read(action):
    try:
        client = Client()
        return json.dumps(getattr(client, action)(), ensure_ascii=False)
    except (GenRouterError, ValueError, OSError) as error:
        return json.dumps({"error": redact(str(error)), "http_status": getattr(error, "status", None)})


def account_status(**kwargs):
    return _read("status")


def key_balances(**kwargs):
    return _read("key_balances")


def models(**kwargs):
    return _read("models")


def slash(raw_args):
    action = {"status": "status", "keys": "key_balances", "models": "models",
              "payments": "payment_status"}.get(raw_args.strip() or "status")
    if not action:
        return "Usage: /genrouter [status|keys|models|payments]. Account setup and changes: hermes genrouter --help in a local terminal."
    return _read(action)


def register(ctx):
    from .cli import setup_parser, handle

    ctx.register_cli_command(name="genrouter", help="GenRouter account, keys, models and billing",
                             setup_fn=setup_parser, handler_fn=handle)
    ctx.register_command("genrouter", slash, description="GenRouter models and account/key balances",
                         args_hint="[status|keys|models|payments]")
    for name, description, handler in (
        ("genrouter_account_status", "Read GenRouter account wallet and payment capability flags. Requires cabinet login.", account_status),
        ("genrouter_key_balances", "Read account API-key available/reserved USD balances and spend. Does not reveal secrets. RPM/TPM limits are unknown.", key_balances),
        ("genrouter_models", "List the live GenRouter model catalog. Requires cabinet login or GENROUTER_API_KEY.", models),
    ):
        ctx.register_tool(name=name, toolset="genrouter", handler=handler,
                          schema={"name": name, "description": description,
                                  "parameters": {"type": "object", "properties": {}, "additionalProperties": False}})
