# Celsius to Fahrenheit converter

Build a small Python tool that converts temperatures from Celsius to
Fahrenheit.

<!-- anvil:contract -->

## Interface contract (must be followed exactly)

- The source file must be `src/convert.py`.
- It must define a function `celsius_to_fahrenheit(celsius: float) -> float`
  that returns the Fahrenheit value (formula: `celsius * 9 / 5 + 32`).
- The function must raise `ValueError` for inputs below absolute zero
  (below -273.15).
- Running `python convert.py <celsius>` from the command line must print the
  Fahrenheit value as a plain number on a single line (nothing else on
  stdout), e.g. `python convert.py 100` prints `212.0`.

Keep it dependency-free (standard library only).
