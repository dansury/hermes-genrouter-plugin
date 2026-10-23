# Model catalog prices

## User story
A user listing models through the CLI, `/genrouter models`, or the
`genrouter_models` tool sees an approximate price beside each model, using
the rates and billing units shown by GenRouter's model catalog.

## Requirements
- FR-001: Preserve the existing model identity and selection contract.
- FR-002: Display USD input, cached input (when supplied), and output rates
  per one million tokens. Convert GenRouter's integer microdollars exactly;
  do not calculate a cache discount or embed a static price list.
- FR-003: Image and video rates use the server's `media_unit` (`image` or
  `second`) and `media_micro_per_unit`, never token units.
- FR-004: Every row includes a readable approximate price and structured
  prices. Missing or invalid rates are explicitly unavailable, never zero.
  An API-key-only catalog may omit prices; direct users to the cabinet or
  cabinet login without fetching a different account or guessing rates.
- FR-005: Model rows remain allowlisted; arbitrary response fields and
  credentials must not be exposed.

## Source and verification
The public cabinet frontend at
`https://genrouter.ru/dashboard/cabinet.js?v=50`, inspected on 2026-10-23,
uses `input_micro_per_million`, `cached_input_micro_per_million`,
`output_micro_per_million`, `media_micro_per_unit`, and `media_unit`.
These are observed frontend fields, not a versioned API guarantee.
Test token/media conversions, zero/missing/malformed prices, both catalog
authentication paths, and the CLI, slash-command and tool entry points with
offline responses. No account mutation or billable inference is needed.

## Plan and tasks
Keep conversion and response allowlisting in `account/client.py`; the
existing entry points share `Client.models()` and require no separate UI.
Use only the standard library. The minimal `catalog/` provider stays unchanged.

- [x] T001 [FR-001–005] Add model normalization in `account/client.py`.
- [x] T002 [FR-002–005] Add offline regression cases in `tests/test_model_prices.py`.
- [x] T003 [FR-004] Explain rates and unavailable prices in `README.md`,
  `README.ru.md`, and `docs/API.md`; link this contract from `spec/index.md`.
- [x] T004 Run the full Python suite and the Windows/Linux CI matrix.
