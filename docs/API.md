# Observed GenRouter API / Наблюдаемый API GenRouter

Inspected on **2026-10-13**. These routes and payloads are used by the public web cabinet; they are not a confirmed third-party compatibility contract.

Sources:

- [Cabinet API client](https://genrouter.ru/dashboard/api.js?v=14)
- [Registration/login frontend](https://genrouter.ru/dashboard/auth.js?v=10)
- [Cabinet frontend](https://genrouter.ru/dashboard/cabinet.js?v=47)
- [Registration page](https://genrouter.ru/dashboard/register)
- [Hermes provider SDK](https://hermes-agent.nousresearch.com/docs/developer-guide/model-provider-plugin)
- [Hermes plugin SDK](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins)

## Cabinet session

Origin: `https://genrouter.ru`. Base path: `/dashboard/api`. The browser uses an HttpOnly session cookie. The adapter maintains its own cookie jar, not a browser cookie database. It sends same-origin `Origin`/`Referer` headers. No public stable OAuth/device-code integration contract, session refresh rules, or CSRF specification was found in the inspected frontend. If GenRouter changes these requirements, authentication can fail; the plugin must be updated rather than bypassing them.

| Method + route | Request / observed shape | Implementation |
| --- | --- | --- |
| `POST /auth/register` | `{nickname, password}`; server creates a session | signup wizard |
| `POST /auth/login` | `{nickname, password}` | hidden-password login |
| `POST /auth/logout` | no JSON body | cabinet logout |
| `POST /auth/email/request` | `{email}` | request/resend verification |
| `POST /auth/email/confirm` | `{code}`; six digits | hidden-code confirmation |
| `GET /profile` | `{user, keys, operations}` | safe account/key summaries |
| `GET /models` | `{models, summary}`; rows have `id`, `name`, `owner`, `kind`, `context_length` | account model catalog |
| `POST /keys` | `{name, allocate_micro, operation_id}`; response includes one-time `key` | create service-specific key |
| `POST /keys/{id}/fund` | `{amount_micro, operation_id}` | confirmed wallet-to-key transfer |
| `GET /config` | includes `payments_enabled` | payment capability status |
| `POST /payments/topup` | `{amount_micro, provider, method}`; response may include `payment_url` | experimental hosted checkout |

The frontend also exposes key rename/rotate/delete routes. This release deliberately does not automate key revocation or rotation: those can invalidate another application's credentials. Use the cabinet.

## Money and limits

`user.wallet_micro` is the free account wallet. Key rows contain `balance_micro`, `reserved_micro`, `spent_micro`, `request_count`, `is_active`, `id`, `name`, `key_prefix`, and `created_at`. Amount fields can be JSON strings. The adapter converts exact decimal values without floating-point rounding.

`1_000_000` microdollars = USD `1`. `balance_micro` is available money; `reserved_micro` is in-flight reserved money. The website displays their sum, while the plugin exposes them separately to avoid treating reserved money as available.

RPM/TPM/concurrency limits, quota reset times, scoped management keys and a key-only balance endpoint were not present in the inspected client. Missing values are `null`/unknown, never zero, unlimited or invented token counts.

## Inference

`https://genrouter.ru/v1` accepts API-key Bearer authentication and `GET /models`. The website also publishes `https://api.genrouter.ru/v1`. The root plugin uses OpenAI Chat Completions; requests from `probe` go directly to `/chat/completions`, never through Hermes fallback providers.

The supplied key's model listing was live-checked: the catalog included `anthropic/claude-opus-5`. A successful catalog request does not establish funded inference. HTTP `402` is surfaced as a billing/funding failure and never reported as a passing probe.

## Payments

The cabinet offers provider `platega`, method `2` (card/RUB) and `13` (crypto). Its public config reported `payments_enabled: true` during inspection, but the user reported payment processing is not yet operational. No checkout/payment was created to verify settlement.

The adapter is therefore behind both `GENROUTER_ENABLE_CHECKOUT=1` and explicit amount confirmation. It returns a HTTPS checkout URL without following it. It never reads card data or declares settlement complete. Payment status polling, signed webhooks, idempotent checkout retry, refunds and automatic recharge need a confirmed contract and sandbox before implementation.

## Verification boundaries / Границы проверки

- Native Hermes discovery/manifest/import/registration: checked locally.
- Account workflows, key issuance, money precision, secret masking, redirects, payment gates: automated tests with simulated API responses.
- Models and public configuration: live read-only checks.
- Registration/email delivery/key writes/funding/checkout: **not live-tested**; no account credentials were supplied for these operations.
- Cabinet compatibility: provisional until GenRouter confirms these endpoints are supported for integrations.

Регистрация действительно состоит из создания аккаунта по нику и паролю, затем отдельной привязки почты. Плагин автоматизирует запросы, но пользователь вводит пароль, принимает условия и вводит код из письма. Для надёжной фоновой автоматизации нужен официальный API с ограниченными правами и понятной семантикой повторов.
