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
3. The catalog package contains no `os.environ` access, secret storage, network
   requests, report submission, or update-checking code.
4. The package can be pinned via `subdir: catalog` in a Hermes catalog entry.
