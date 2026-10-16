# GenRouter for [Hermes Agent](https://github.com/NousResearch/hermes-agent)

[Русская инструкция](README.ru.md) · [API notes](docs/API.md) · [Hermes provider documentation](https://hermes-agent.nousresearch.com/docs/integrations/providers)

Independent [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugins for [GenRouter](https://genrouter.ru). This repository contains the provider code and an account-management companion, not just a configuration example.

## Hermes Agent integration

This is a third-party provider plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent). For Hermes installation, provider selection, and the built-in provider reference, see the official [LLM and Model Providers guide](https://hermes-agent.nousresearch.com/docs/integrations/providers). GenRouter is not affiliated with Nous Research.

## Features and status

| Feature | Status |
| --- | --- |
| GenRouter in the Hermes vendor picker | Implemented; native registration validated |
| Live models and selecting a text model | Implemented |
| Registration, login, email code request/confirmation | Implemented against the observed cabinet API |
| Issuing separate keys for applications | Implemented; secrets saved privately before setup continues |
| Key available/reserved balance, spend, request counts | Implemented |
| Moving wallet funds to a key | Implemented; explicit amount and confirmation |
| Agent tools and `/genrouter` | Read-only tools and slash command |
| Hosted payment checkout | Experimental, disabled by default; processing unverified |
| RPM/TPM limits and reset times | Not exposed by the observed API; reported as unknown |

The account API serves GenRouter's own public frontend. It is **not a published, versioned integration API**. Registration and key mutations were tested with simulated responses, not against a live account. See [API notes](docs/API.md).

## Install

Requires an installed Hermes Agent. Tested locally with Hermes **0.21.6**, Python **3.11**, Windows. CI tests the standalone account client on Windows/Linux with Python 3.11–3.13.

Install both parts:

```shell
hermes plugins install dansury/hermes-genrouter-plugin --enable
hermes plugins install https://github.com/dansury/hermes-genrouter-plugin/tree/main/account --enable
```

The root registers the `genrouter-ru` provider. The `account/` package adds `hermes genrouter`, `/genrouter`, and read-only tools. For another Hermes profile, prefix commands with `hermes -p <profile>`.

A prior manual `plugins/model-providers/genrouter-ru` installation registers the same provider with the same endpoint and key variable; it can be retained during migration. A legacy `providers.genrouter` custom entry is a separate endpoint.

## Existing API key

```shell
hermes auth add genrouter-ru --type api-key
hermes model
```

Enter the key privately, choose **GenRouter**, then a live catalog model. The fallback/default is `anthropic/claude-opus-5`. Plugin endpoint: `https://api.genrouter.ru/v1`. Anthropic SDK integrations use `https://api.genrouter.ru` without `/v1`.

Alternatively, put `GENROUTER_API_KEY=your-key` in the active profile's `.env`: `%LOCALAPPDATA%\hermes\.env` on Windows or `~/.hermes/.env` on Linux/macOS. Never commit it. Companion catalog/probe commands without cabinet login read this environment variable, not a Hermes pooled credential; use `.env` for those commands with an existing key.

## Account setup

Run in a local interactive terminal:

```shell
hermes genrouter setup --register --nickname your_nickname --email you@example.com
```

The wizard asks for acceptance of GenRouter's terms, prompts privately for a password, requests and confirms a six-digit email code, issues a `Hermes` key, installs it and selects the model. It does not access your mailbox. Currently GenRouter requires a **nickname and password**; email is attached and verified separately.

Existing account:

```shell
hermes genrouter setup --nickname your_nickname --key-name Hermes
```

An existing key is never silently replaced. Import its secret with `hermes auth add genrouter-ru`, or explicitly recover it using `hermes genrouter keys rotate --id KEY_ID --confirm`. Rotation immediately invalidates the old secret; an uncertain rotation is never automatically repeated.

If email delivery fails after signup, the account already exists. Resume verification instead of registering again:

```shell
hermes genrouter login --nickname your_nickname
hermes genrouter email-request --email you@example.com
hermes genrouter email-confirm
```

## Keys, balances and models

```shell
hermes genrouter status
hermes genrouter keys list
hermes genrouter models
hermes genrouter select anthropic/claude-opus-5
hermes genrouter keys create --name Cursor --confirm
hermes genrouter keys show --name Cursor --reveal
```

Full keys are revealed only by explicit `--reveal` in an interactive local terminal. Creating a `Cursor` key does not switch Hermes' key. `keys use --name Hermes` installs a locally stored key for Hermes.

New keys get **zero balance by default**. To allocate existing wallet funds:

```shell
hermes genrouter keys fund --id KEY_ID --amount-usd 5 --confirm
```

Amounts are USD with up to six decimals. The API uses integer microdollars: `1_000_000 = $1`. Available and reserved funds are shown separately. New keys do not refill the account wallet or bypass rate limits. Token limits cannot be inferred from money because model prices vary.

In chat: `/genrouter status`, `/genrouter keys`, `/genrouter models`, `/genrouter payments`. Tools: `genrouter_account_status`, `genrouter_key_balances`, `genrouter_models`. They read data; mutations use local CLI commands with confirmation. Passwords, codes and full keys are not model tool arguments/results.

## Honest inference check

```shell
hermes genrouter probe --model anthropic/claude-opus-5
```

This sends a small billable request directly to GenRouter with `max_tokens: 16` and no fallback. Success requires the exact reply `GENROUTER_OK`. `HTTP 402` can originate from GenRouter or its upstream supplier. The plugin displays the sanitized reason and retains `request_id`; it does not automatically recommend adding funds for every 402. Regular Hermes chat may return a fallback provider's answer after GenRouter fails.

During development the supplied key listed 26 models including the requested Opus model, but inference returned **HTTP 402**. A funded key is needed for a successful chat check. No live account, keys or payments were created during the extended plugin development.

## Future payments

```shell
hermes genrouter payments
```

The server's `payments_enabled` flag is separate from plugin readiness and does not prove processing works. Checkout is disabled unless `GENROUTER_ENABLE_CHECKOUT=1` is explicitly set and an amount confirmed:

```shell
hermes genrouter checkout --amount-usd 5 --method card --confirm
```

Use only after GenRouter confirms the checkout contract. The experimental adapter returns an HTTPS hosted checkout URL; the user pays on the payment provider's page. It never accepts card data or treats URL creation as payment success. Automatic charges, recharges and payment webhooks are not implemented. See [API notes](docs/API.md).

## ChatGPT subscription

```shell
hermes auth add openai-codex --type oauth --browser
```

Finish browser sign-in, then choose an account-offered Codex model through `hermes model` or add it using `hermes fallback add`, retaining GenRouter as primary. OAuth does not require an OpenAI API key and does not fund GenRouter.

## Credential storage and recovery

Passwords/codes are never persisted. Cabinet cookies and issued key secrets are saved outside the checkout at `plugin-data/genrouter-account/credentials.secrets` in the active profile. Windows uses current-user **DPAPI encryption**. Linux/macOS use a private file (`0600`, directory `0700`), without encryption at rest. The active inference key in `.env` remains a plaintext Hermes credential.

HTTPS requests use fixed GenRouter hosts, timeouts, response-size limits and no redirects. Inference never receives cabinet cookies. Only a sanitized error message and selected error metadata are retained; raw bodies are never logged. Writes are never automatically retried: after a lost response an operation may have succeeded. Inspect the cabinet first. After an uncertain funding result, repeat the same key and amount; the saved UUID is reused automatically. Key creation is not safely replayable: inspect the key list and recover a lost secret through explicitly confirmed rotation.

`hermes genrouter logout` revokes the cabinet session but retains issued keys and the inference key. Revoke unused keys in the cabinet.

## Updates and error reports

Both parts default to a **daily read-only update check** while Hermes runs.
Use `hermes genrouter updates --force` to check now; apply with
`hermes plugins update genrouter-ru` and `hermes plugins update genrouter-account`.
Set `GENROUTER_UPDATE_CHECK_HOURS` to an interval in hours (default 24, 0 disables).
Hermes's own `plugins.auto_update_check_hours` is also 24 by default.
Nothing is installed automatically.

Plugin errors are queued privately, including native inference errors via the
Hermes provider callback. Queue size is bounded to 100 distinct errors.
`/genrouter report` shows how to review and share them. In a local terminal:

```shell
hermes genrouter report list
hermes genrouter report preview
hermes genrouter report send
hermes genrouter report new --description "What happened and steps to reproduce"
```

Every send previews the report and asks permission; `--confirm` is explicit CLI
consent. An authenticated GitHub CLI user is offered submission under their
identity. Otherwise an owner-authorized, deliberately distributed issue-only
reporter token is used, with no setup. Its bundled encoding is **reversible
obfuscation, not secure encryption**. It must never receive code/admin rights;
its revocation affects all shared reporters. An optional local
`GENROUTER_ISSUE_TOKEN` overrides it.

Reports include plugin/Hermes/Python/OS versions, timestamps, operation, error
type, stack locations, HTTP status/code, request ID, retry delay and occurrence
count. Prompts, raw HTTP payloads, full config and credentials are not collected.
An optional `--log-file path` adds a bounded, sanitized excerpt from a chosen
text log. Inspect it: automated redaction cannot guarantee removal of all
personal information from arbitrary logs.

A stable fingerprint is checked against open and closed repository issues
before creating a new issue. Local sends are serialized and POST is never
automatically retried. GitHub cannot guarantee atomic deduplication across
simultaneous users; such rare duplicates may need maintainer consolidation.
On failure, the plugin creates a complete `.eml` addressed to
`dansury@gmail.com`; review and send it in your mail app. It never sends email
in the background.

## Development

```shell
python -m unittest discover -s tests -v
python -m account --help
hermes plugins validate .
hermes plugins validate ./account
hermes plugins doctor ./account --ci
```

The account client uses only Python's standard library; native loading requires Hermes. [MIT license](LICENSE). Not affiliated with GenRouter or Nous Research.
