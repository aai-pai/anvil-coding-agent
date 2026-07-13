# Password strength checker

Build a Python library that scores password strength with a pytest suite of
its own (include tests — this is a quality-sensitive component).

<!-- anvil:contract -->

## Interface contract (must be followed exactly)

- The source file must be `src/password_strength.py`.
- It must define `assess(password: str) -> dict` returning a dict with exactly
  these keys:
  - `"score"`: an int from 0 to 4 — the number of the following four rules the
    password satisfies:
    1. at least 8 characters long
    2. contains at least one digit
    3. contains at least one uppercase letter
    4. contains at least one character that is not a letter or digit
  - `"issues"`: a list of human-readable strings, one per **failed** rule
    (empty list when all four pass).
- `assess` must raise `TypeError` when given a non-string.

Examples: `assess("abc")["score"]` is `0`; `assess("Tr0ub4dor&3")["score"]`
is `4` with `issues == []`.

Standard library only.
