# GenRouter API notes / Контракт GenRouter

Updated 2026-10-13 from the developer's reply supplied by the repository owner.
Account API stays experimental: no fixed external-plugin contract, management
token or OAuth/device flow. Automated registration needs separate agreement.

## Endpoints, session and CSRF

Cabinet: `https://genrouter.ru/dashboard/api`.
Inference: `https://api.genrouter.ru/v1`.
Anthropic SDK: `https://api.genrouter.ru` without `/v1`.

Cookie `genrouter_session` lasts 30 days without renewal.
`GET /session` checks login. POST has CSRF checks. The standalone client sends
same-origin Origin/Referer. Extension access on a different origin needs separate
verification. The plugin never bypasses CSRF.

| Route | Contract |
| --- | --- |
| POST /auth/register | nickname, password; email attached separately |
| POST /auth/login | nickname, password; confirmed email is sent in nickname too |
| POST /auth/email/request | email |
| POST /auth/email/confirm | six-digit code |
| POST /auth/logout | revoke session |
| GET /profile | wallet and current monetary key balances |
| GET /models | cabinet catalog: text, image and video |
| POST /keys | name, allocate_micro, operation_id; one-time secret |
| POST /keys/{id}/fund | amount_micro, operation_id |
| POST /keys/{id}/rotate | new secret; old one stops immediately |
| GET /config | flags do not prove payment processing works |

## Referral attribution

Public GenRouter links use `https://genrouter.ru/?ref=d97a170843`. The landing server sets a secure, same-site `linali_ref` cookie for this referral (observed on 2026-10-26). Before a new account registration, the client supplies that cookie for `genrouter.ru` and `/`; it does not add referral fields to account JSON or API endpoint URLs. Login and already-created accounts are not reassigned. The server decides whether attribution is eligible; account creation is never performed just to test it.

## Registration recovery

Nickname: 4–32 Latin letters, digits and underscores. Password: 8–128 characters,
at least one letter and digit. Email login requires confirmation. Terms acceptance
is local: the API has no terms field. Avoid email-only signup.

Email code: 15 minutes, five attempts; resend after a minute; five codes/hour per
account. Server enforces these limits; the plugin never automatically resends.

After failed email delivery or a lost signup response, check session, then login
by nickname and request email again. Never register blindly twice. An uncertain
signup marker is retained until successful login.

## Money, keys and retries

`1 USD = 1,000,000 micro`. Wallet and key balances are separate. Allocate wallet
funds to the key before generation. `balance_micro` is available money **after**
reserving in-flight funds; do not subtract `reserved_micro` again.

Ten active keys maximum; no separate scopes or expiry. Secrets are returned once
and cannot be retrieved later. Explicit rotation recovers a lost secret and
immediately invalidates the old one. Save the new secret privately first.

`GET /v1/key` still has legacy token fields. Do not use it for money: current sums
are in cabinet `/profile`. Default RPM is 60, but a key can differ. Display RPM
only if supplied. TPM, concurrency, daily/monthly budgets and reset dates stay
unknown when absent.

Funding replay uses the **same operation_id, amount and key**. After timeout
the plugin preserves all three and reuses the UUID for the identical transfer.
Changed transfers are blocked while uncertain. Writes are never auto-retried.

Creation accepts operation_id but cannot recover its original result. After
a lost response, list keys; if one exists without its secret, confirm rotation.
There is no operation-status API or recovery of old secrets. Uncertain rotation
is blocked from blind retries: inspect the cabinet and contact support.

## Models and errors

`Client.models()` retains the cabinet's live rate fields as allowlisted
`pricing` values in USD strings and a readable `price_display`. Token prices
use `input_micro_per_million`, `cached_input_micro_per_million`, and
`output_micro_per_million`; media prices use `media_micro_per_unit` with
`media_unit` (`image` or `second`). Divide microdollars by 1,000,000 without
rounding. Missing, invalid, or unsupported rates are unavailable, never free.
The inference catalog may omit prices; log into the cabinet rather than
assuming a tariff or a cache multiplier. See the
[price contract](../spec/modules/model-prices.md).

Use exact current IDs. Inference `/v1/models` lists text models. A video card in
the cabinet does not guarantee a working video flow. Protocol support depends
on model; Responses currently supports `openai/*` only. This plugin uses Chat
Completions. Tools, vision, reasoning and context need per-model verification.

Catalog access needs no money; generation needs sufficient key balance.
402 can come from GenRouter or its supplier, with non-unified codes. Display
the sanitized message and request_id rather than always recommending a deposit.
Retain error code and Retry-After. RPM uses `rate_limit_exceeded` and
`Retry-After`. Native Hermes errors are captured by its provider callback,
without SDK exception bodies, payloads or prompts.

## Payments and verification

Checkout stays disabled by default pending processing launch and API confirmation.
The experimental adapter requires `GENROUTER_ENABLE_CHECKOUT=1` and amount
confirmation; this is not a verified payment workflow.

Account mutations/recovery and report submissions have mock tests. No live signup,
transfer, rotation or payment was performed without a test account.
A catalog check is not proof of successful paid generation.
