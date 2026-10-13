"""Hermes account companion: terminal wizard, read-only agent tools and slash command."""

import json

from .client import Client, GenRouterError, redact


def _read(action):
    try:
        client = Client()
        return json.dumps(getattr(client, action)(), ensure_ascii=False)
    except Exception as error:
        from .reports import safe_capture
        report = safe_capture(error, action=action)
        return json.dumps({"error": redact(str(error)), "http_status": getattr(error, "status", None),
                           "request_id": getattr(error, "request_id", None),
                           "report_id": report["fingerprint"] if report else None,
                           "report_hint": "Помогите сделать продукт лучше: /genrouter report. Отправка только после вашего согласия."},
                          ensure_ascii=False)


def account_status(**kwargs):
    return _read("status")


def key_balances(**kwargs):
    return _read("key_balances")


def models(**kwargs):
    return _read("models")


def slash(raw_args):
    if raw_args.strip() == "report":
        from .reports import pending
        rows = pending()
        return json.dumps({"reports": [{"id": r["fingerprint"], "occurrences": r["occurrences"]} for r in rows],
                           "hint": "Поделитесь ошибкой — с вашей помощью мы быстрее сделаем продукт, который вам понравится. "
                                   "Просмотр и отправка: hermes genrouter report send; "
                                   "своя жалоба: hermes genrouter report new. Перед отправкой покажем отчёт и спросим согласие."},
                          ensure_ascii=False)
    if raw_args.strip() == "updates":
        from .updates import check_updates
        return json.dumps(check_updates(), ensure_ascii=False)
    action = {"status": "status", "keys": "key_balances", "models": "models",
              "payments": "payment_status", "session": "session"}.get(raw_args.strip() or "status")
    if not action:
        return "Usage: /genrouter [status|keys|models|payments|session|updates|report]. Changes and report consent: hermes genrouter --help."
    return _read(action)


def register(ctx):
    from .cli import setup_parser, handle
    from .updates import start_checks
    start_checks()

    ctx.register_cli_command(name="genrouter", help="GenRouter account, keys, models and billing",
                             setup_fn=setup_parser, handler_fn=handle)
    ctx.register_command("genrouter", slash, description="GenRouter models and account/key balances",
                         args_hint="[status|keys|models|payments|session|updates|report]")
    for name, description, handler in (
        ("genrouter_account_status", "Read GenRouter account wallet and payment capability flags. Requires cabinet login.", account_status),
        ("genrouter_key_balances", "Read account API-key available/reserved USD balances and spend. Does not reveal secrets. RPM/TPM limits are unknown.", key_balances),
        ("genrouter_models", "List the live GenRouter model catalog. Requires cabinet login or GENROUTER_API_KEY.", models),
    ):
        ctx.register_tool(name=name, toolset="genrouter", handler=handler,
                          schema={"name": name, "description": description,
                                  "parameters": {"type": "object", "properties": {}, "additionalProperties": False}})
