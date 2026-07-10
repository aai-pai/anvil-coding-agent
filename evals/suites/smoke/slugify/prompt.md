# URL slug generator

Build a Python utility that turns arbitrary titles into URL-safe slugs.

## Interface contract (must be followed exactly)

- The source file must be `src/slugger.py`.
- It must define `slugify(text: str) -> str` with these exact rules:
  - lowercase the text;
  - replace every run of characters that are not ASCII letters or digits
    (spaces, punctuation, underscores, etc.) with a single hyphen `-`;
  - strip leading and trailing hyphens;
  - return an empty string when nothing remains.
- It must also define `slugify(text, max_length=N)` (optional keyword
  argument): when given, truncate the slug to at most `N` characters without
  leaving a trailing hyphen.

Examples: `slugify("Hello, World!")` -> `"hello-world"`,
`slugify("  --Already--Slugged--  ")` -> `"already-slugged"`,
`slugify("Hello, World!", max_length=6)` -> `"hello"` (the truncated
`"hello-"` loses its trailing hyphen).

Standard library only.
