"""Interactive account management. Passwords and email codes stay off command lines."""

import argparse
import getpass
import json
import subprocess
import sys

from .client import Client, GenRouterError, referral_url, redact


from .reports import (CONSENT_TEXT, capture, safe_capture, load_report, pending, render,
                      submit, email_draft, personal_identity)
from .updates import check_updates, start_checks


def report_command(args):
    if args.report_action == "list":
        return [{"id": r["fingerprint"], "action": r["action"], "occurrences": r["occurrences"],
                 "issue_url": r.get("issue_url")} for r in pending()]
    if args.report_action == "new":
        description = args.description
        if not description:
            if not sys.stdin.isatty():
                raise ValueError("Provide --description for a manual report")
            description = input("Что произошло и как повторить ошибку? ")
        report = capture(description=description)
    else:
        report = load_report(getattr(args, "id", None))
    body = render(report, getattr(args, "description", "") or "", getattr(args, "log_file", None))
    print(body)
    if args.report_action == "preview":
        return {"report_id": report["fingerprint"], "sent": False}
    # Every send previews this exact body, even with explicit --confirm.
    if not getattr(args, "confirm", False):
        if not sys.stdin.isatty() or input(CONSENT_TEXT + " [y/N] ").strip().lower() not in {"y", "yes", "д", "да"}:
            return {"report_id": report["fingerprint"], "sent": False}
    identity = args.identity
    if identity == "ask":
        username = personal_identity()
        if username:
            if not sys.stdin.isatty():
                raise ValueError("GitHub is signed in; explicitly choose --identity personal or shared")
            identity = "personal" if input(f"Отправить issue от вашего имени ({username})? [Y/n] ").strip().lower() not in {"n", "no", "нет"} else "shared"
        else:
            identity = "shared"
    if identity == "email":
        return email_draft(report, body)
    try:
        return submit(report, body, consent=True, identity=identity)
    except Exception:
        result = email_draft(report, body)
        result["github_failed"] = True
        result["hint"] += " GitHub may have received the report; next attempt checks duplicates first."
        return result


def error_notice(error, action):
    report = safe_capture(error, action=action)
    if report:
        print("С вашей помощью мы быстрее сделаем продукт, который вам понравится. "
              "Диагностика сохранена локально. Просмотр и отправка с вашего согласия: "
              f"hermes genrouter report send --id {report['fingerprint']}", file=sys.stderr)
    if report and sys.stdin.isatty() and sys.stderr.isatty():
        from types import SimpleNamespace
        try:
            result = report_command(SimpleNamespace(report_action="send", id=report["fingerprint"],
                                                   description="", log_file=None, confirm=False, identity="ask"))
            print(json.dumps(result, ensure_ascii=False, indent=2))
        except Exception:
            pass  # Never replace the original error with a reporting failure.
    return report

def setup_parser(parser):
    commands = parser.add_subparsers(dest="genrouter_action", required=True)
    setup = commands.add_parser("setup", help="Sign in/register, confirm email, issue a key and choose a model")
    setup.add_argument("--register", action="store_true")
    setup.add_argument("--nickname")
    setup.add_argument("--email")
    setup.add_argument("--accept-terms", action="store_true")
    setup.add_argument("--key-name", default="Hermes")
    setup.add_argument("--model", default="anthropic/claude-opus-5")
    signup = commands.add_parser("signup", help="Create an account and request email verification")
    signup.add_argument("--nickname")
    signup.add_argument("--email")
    signup.add_argument("--accept-terms", action="store_true")
    login = commands.add_parser("login", help="Sign in with nickname and hidden password prompt")
    login.add_argument("--nickname")
    commands.add_parser("logout", help="Revoke this cabinet session")
    email = commands.add_parser("email-request", help="Request or resend an email code")
    email.add_argument("--email", required=True)
    commands.add_parser("email-confirm", help="Confirm email with a hidden six-digit code prompt")
    for name in ("status", "models", "payments"):
        commands.add_parser(name)
    select = commands.add_parser("select", help="Verify a live model id and select it in Hermes")
    select.add_argument("model")
    probe = commands.add_parser("probe", help="Direct paid inference test, without Hermes fallbacks")
    probe.add_argument("--model", default="anthropic/claude-opus-5")
    keys = commands.add_parser("keys", help="List, issue, fund, install or reveal service-specific keys")
    sub = keys.add_subparsers(dest="key_action", required=True)
    sub.add_parser("list")
    create = sub.add_parser("create")
    create.add_argument("--name", required=True)
    create.add_argument("--allocate-usd", default="0")
    create.add_argument("--operation-id")
    create.add_argument("--confirm", action="store_true")
    use = sub.add_parser("use")
    use.add_argument("--name", required=True)
    show = sub.add_parser("show")
    show.add_argument("--name", required=True)
    show.add_argument("--reveal", action="store_true", help="Print the full key to your local terminal")
    fund = sub.add_parser("fund")
    fund.add_argument("--id", required=True)
    fund.add_argument("--amount-usd", required=True)
    fund.add_argument("--operation-id")
    fund.add_argument("--confirm", action="store_true")
    checkout = commands.add_parser("checkout", help="Experimental hosted checkout; disabled by default")
    checkout.add_argument("--amount-usd", required=True)
    checkout.add_argument("--method", choices=("card", "crypto"), required=True)
    checkout.add_argument("--confirm", action="store_true")
    commands.add_parser("session", help="Check the 30-day cabinet session")
    updates = commands.add_parser("updates", help="Check plugin updates (daily by default)")
    updates.add_argument("--force", action="store_true")
    rotate = sub.add_parser("rotate", help="Recover a lost secret; immediately invalidates the old key")
    rotate.add_argument("--id", required=True)
    rotate.add_argument("--confirm", action="store_true")
    reports = commands.add_parser("report", help="Preview errors or report a problem with your consent")
    report_sub = reports.add_subparsers(dest="report_action", required=True)
    report_sub.add_parser("list")
    for verb in ("preview", "send", "new"):
        p = report_sub.add_parser(verb)
        p.add_argument("--id")
        p.add_argument("--description")
        p.add_argument("--log-file", help="Optional diagnostic text log; always preview before sharing")
        p.add_argument("--confirm", action="store_true", help="Explicit permission to send the displayed report")
        p.add_argument("--identity", choices=("ask", "personal", "shared", "email"), default="ask")
    parser.set_defaults(func=handle)


def hidden(prompt):
    if not sys.stdin.isatty():
        raise ValueError("Run this command in an interactive terminal to enter the password/email code privately")
    return getpass.getpass(prompt)


def confirmation(text, confirmed=False):
    if confirmed:
        return
    if not sys.stdin.isatty() or input(text + " Type yes to continue: ").strip().lower() != "yes":
        raise ValueError("Operation was not confirmed")


def signup(client, args):
    nickname = args.nickname or input("GenRouter nickname: ").strip()
    email = args.email or input("Email address: ").strip()
    confirmation(f"Create account {nickname}. Accept {referral_url('/legal/offer')} and "
                 f"{referral_url('/legal/privacy')}?", args.accept_terms)
    password = hidden("New password (at least 8 characters, a letter and a digit): ")
    if password != hidden("Repeat password: "):
        raise ValueError("Passwords do not match")
    client.register_account(nickname, password, accepted_terms=True)
    print("Account created; its session is saved. If email delivery fails, use email-request, not signup again.")
    client.request_email(email)
    return {"account_created": True, "email_verification": "pending", "next_command": "hermes genrouter email-confirm"}


def login(client, args):
    nickname = args.nickname or input("GenRouter nickname: ").strip()
    client.login(nickname, hidden("Password: "))
    return {"authenticated": True}


def select_model(client, model):
    rows = client.models()
    matching = next((row for row in rows if row["id"] == model), None)
    if not matching:
        raise ValueError("Model is absent from the current GenRouter catalog; run 'hermes genrouter models'")
    if matching.get("kind") not in {None, "text"}:
        raise ValueError("Hermes chat needs a text model; image/video models are not chat backends")
    # argv list, no shell interpolation; keep account credentials out of argv.
    for key, value in (("model.provider", "genrouter-ru"), ("model.default", model)):
        subprocess.run(["hermes", "config", "set", key, value], check=True)
    subprocess.run(["hermes", "config", "unset", "model.api_mode"], check=True)
    subprocess.run(["hermes", "config", "unset", "model.base_url"], check=True)
    return {"provider": "genrouter-ru", "model": model, "selected": True}


def execute(client, args):
    action = args.genrouter_action
    if action == "session":
        return client.session()
    if action == "signup":
        return signup(client, args)
    if action == "login":
        return login(client, args)
    if action == "email-request":
        client.request_email(args.email)
        return {"email_verification": "pending"}
    if action == "email-confirm":
        client.confirm_email(hidden("Six-digit email code: ").strip())
        return {"email_verified": True}
    if action == "logout":
        client.logout()
        return {"cabinet_logged_out": True, "inference_key_retained": True}
    if action == "status":
        return client.status()
    if action == "models":
        return client.models()
    if action == "payments":
        return client.payment_status()
    if action == "select":
        return select_model(client, args.model)
    if action == "probe":
        return client.probe(args.model)
    if action == "checkout":
        confirmation(f"Create a {args.method} checkout for USD {args.amount_usd}?", args.confirm)
        return client.checkout(args.amount_usd, args.method, confirmed=True)
    if action == "setup":
        if args.register:
            signup(client, args)
            client.confirm_email(hidden("Six-digit email code: ").strip())
        else:
            login(client, args)
        existing = next((row for row in client.key_balances() if row.get("name") == args.key_name), None)
        if existing:
            # Never rotate or silently replace another app's existing key.
            if args.key_name not in client.state.get("keys", {}):
                raise ValueError("A key with that name already exists but its secret is not stored here. Choose a new --key-name or import the existing key through 'hermes auth add genrouter-ru'.")
        else:
            client.create_key(args.key_name)
        client.use_key(args.key_name)
        return select_model(client, args.model)
    if action == "keys":
        if args.key_action == "rotate":
            confirmation("Rotate this key? Its old secret will immediately stop working.", args.confirm)
            return client.rotate_key(args.id, confirmed=True)
        if args.key_action == "list":
            return client.key_balances()
        if args.key_action == "create":
            confirmation(f"Create key {args.name!r} and allocate USD {args.allocate_usd} from the account wallet?", args.confirm)
            return client.create_key(args.name, args.allocate_usd, args.operation_id)
        if args.key_action == "use":
            return client.use_key(args.name)
        if args.key_action == "show":
            if not args.reveal:
                return {"name": args.name, "secret": "[hidden]", "hint": "Use --reveal in your private local terminal"}
            # Explicit terminal-only export; this command is never exposed as an LLM tool.
            if not sys.stdout.isatty():
                raise ValueError("Full keys may only be revealed in an interactive local terminal")
            print(client.reveal_key(args.name))
            return {"name": args.name, "revealed": True}
        if args.key_action == "fund":
            confirmation(f"Move USD {args.amount_usd} from the account wallet to key {args.id}?", args.confirm)
            return client.fund_key(args.id, args.amount_usd, args.operation_id)
    raise ValueError("Unknown GenRouter command")


def handle(args):
    try:
        if args.genrouter_action == "report":
            result = report_command(args)
        elif args.genrouter_action == "updates":
            result = check_updates(force=args.force)
        else:
            # Independent of cabinet login and never blocks the requested action on failure.
            start_checks()
            result = execute(Client(), args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        print(redact(str(error)), file=sys.stderr)
        error_notice(error, args.genrouter_action)
        raise SystemExit(1) from None


def main():
    parser = argparse.ArgumentParser(prog="genrouter", description="Manage GenRouter for Hermes")
    setup_parser(parser)
    return handle(parser.parse_args())


if __name__ == "__main__":
    main()
