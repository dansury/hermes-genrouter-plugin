Subject: Supported GenRouter API for Hermes integration: accounts, keys, limits and payments

Hello GenRouter team,

We have built an open-source Hermes Agent plugin: https://github.com/dansury/hermes-genrouter-plugin. It registers GenRouter as an inference vendor, selects models and includes account/key-management commands. We want a reliable onboarding flow: registration → email verification → application-specific key → quota monitoring → funding when payments become operational.

On October 13, 2026, your public cabinet client exposed `/dashboard/api/auth/register`, `/auth/login`, `/auth/email/request`, `/auth/email/confirm`, `/profile`, `/models`, `/keys`, `/keys/{id}/fund`, `/config` and `/payments/topup`. Please confirm whether external integrations may rely on these endpoints, or provide their supported equivalents.

We need the following information or API additions:

1. **A stable contract and delegated authentication:** OpenAPI, API versioning/change policy, request/response/error examples, and scoped management tokens or OAuth/device flow. Separate read-only account/quota permissions from key creation and money movement. Document session expiry/refresh, CSRF requirements, anti-abuse/CAPTCHA rules and automated-signup policy.

2. **Registration and verification:** the current frontend creates an account with nickname/password, then attaches email separately. Please document required fields, password/terms rules, code expiry, attempt/resend limits, email login support and recovery after successful account creation but failed email delivery or a lost response.

3. **Key management and quotas:** confirm one-time key response fields, scopes, expiration and key-count limits. Provide a key-only read endpoint for its balance without granting account-wide access. Include available/reserved balances, spend, RPM/TPM/concurrency limits, daily/monthly budgets, remaining quota and reset timestamps. Clarify units and account-wallet versus key-balance behavior.

4. **Idempotency and recovery:** confirm the uniqueness scope, retention and replay behavior of `operation_id` for key creation and funding, including reusing a UUID with a different body. A status/recovery endpoint is needed after uncertain network failures. How can an integration recover a lost one-time key response without creating duplicates or charging twice?

5. **Models and inference errors:** confirm the canonical base URL (`genrouter.ru/v1` or `api.genrouter.ru/v1`), current model IDs, model types, context/tool/vision/reasoning capabilities and supported protocols. Please distinguish key/account funding failures, upstream billing/auth failures, invalid models and rate limiting through structured error codes. We observed HTTP 402 while model listing worked and need an unambiguous cause.

6. **Payments once available:** `/config.payments_enabled` was true, but working settlement has not been confirmed. Please supply a sandbox, test credentials, methods/currencies, min/max amounts, exchange-rate/fee rules, checkout idempotency, HTTPS URL, payment IDs/status and crediting semantics. Future automation needs signed webhooks with signature/retry/replay rules plus status polling. Document cancellation/refunds and explicit consent for any future recharge. The plugin must not collect card data or equate URL creation with settlement.

Checkout is currently disabled by default. Unknown rate limits remain unknown, and cabinet API compatibility is marked provisional. Passwords/email codes are not persisted; no credentials are included in source or public output. Registration and financial writes were tested with simulated responses, so we also need a test account/environment for end-to-end verification.

Please share the integration documentation, an engineering contact and confirmation of the supported workflow. We can then stabilize the integration and implement payments against a verified contract.

Thank you,
Hermes / GenRouter integration maintainer

---

Draft, not sent. A verified technical recipient address has not been supplied.
