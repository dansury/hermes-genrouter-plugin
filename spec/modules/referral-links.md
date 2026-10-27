# Referral attribution

## Goal

All GenRouter accounts initiated by this plugin and all user-facing GenRouter
links use `https://genrouter.ru/?ref=d97a170843` as their referral source.
Inference and cabinet API endpoints remain unchanged.

## Contract

- `REFERRAL_CODE` and `REFERRAL_URL` are the canonical account-companion
  constants.
- Provider profiles expose the exact referral URL as `signup_url`.
- Programmatic registration supplies the secure referral cookie used by the
  GenRouter landing page; registration JSON and API endpoint URLs do not change.
- Human dashboard, legal and model-catalog links preserve their destination
  path and append `ref=d97a170843` (`&ref=` when a query already exists).
- `https://api.genrouter.ru` and the internal `/dashboard/api` base are service
  endpoints, not signup links, and are not rewritten.
- Referral URL construction rejects external hosts and traversal-like paths.

## Verification

- Provider contract tests assert the catalog profile signup URL.
- Account tests assert the registration cookie and canonical referral helper.
- Repository contract tests reject unattributed maintained user-facing links.
