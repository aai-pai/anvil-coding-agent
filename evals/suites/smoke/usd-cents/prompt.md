# USD to cents converter

Build a small Python helper that converts US dollar amounts to integer cents,
suitable for money-safe arithmetic.

## Interface contract (must be followed exactly)

- The source file must be `src/currency.py`.
- It must define a function `usd_to_cents(amount: float) -> int` that converts
  a dollar amount to whole cents, rounding half up to the nearest cent
  (e.g. `1.005` dollars -> `101` cents, `2.675` -> `268`).
- Negative amounts must raise `ValueError`.
- It must also define `cents_to_usd(cents: int) -> str` returning the amount
  formatted with a dollar sign and two decimals, e.g. `cents_to_usd(101)`
  returns `"$1.01"`.

Use `decimal.Decimal` internally so float artifacts (like 2.675 binary
representation) do not produce off-by-one-cent results. Standard library only.
