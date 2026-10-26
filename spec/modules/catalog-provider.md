# Catalog provider package

## Goal

Make GenRouter discoverable through the Hermes Plugin Catalog without changing
the independently installable account-management companion.

## Scope

- Ship a separate `catalog/` plugin directory with a GenRouter provider profile.
- Declare `GENROUTER_API_KEY` as the only required secret.
- Rely on Hermes' provider credential handling; do not read, write, cache, or
  report secrets from this package.
- Do not start background workers or perform update checks.

## Acceptance criteria

1. `catalog/plugin.yaml` identifies a `model-provider` plugin.
2. `catalog/__init__.py` registers `genrouter-ru` through `ProviderProfile`.
3. The catalog package contains no `os.environ` access, secret storage, report submission, or update-checking code. A provider-owned `fetch_models` hook performs only an explicit, credentialed HTTPS model-catalog read, never inference or network activity at import time. It accepts Hermes context keywords, understands both `data` and `models` catalog envelopes, and excludes explicitly non-chat rows. Redirects are refused and failed or malformed catalog reads return `None` for Hermes fallback behavior.
4. The full provider reuses the catalog profile and adds only its inference-error observer. Both distributions must offer the same live model listing. Account tool handlers accept the positional arguments mapping used by Hermes plus optional context keywords.
5. The package can be pinned via `subdir: catalog` in a Hermes catalog entry.
