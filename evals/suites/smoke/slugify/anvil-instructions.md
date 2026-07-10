# Anvil standing instructions

## Interface contracts are law

When the request pins an interface contract — file paths, module or file
names, function/class names, signatures, return types or shapes, CLI
commands, storage formats, environment variable names — reproduce it
**exactly** in the generated project. Never rename, relocate, restructure,
or "improve" a pinned interface.

- A pinned path like `src/convert.py` means exactly that single top-level
  file — not a package, not `src/converter/convert.py`, not `main.py`.
- A pinned return shape (e.g. "returns a dict with keys `score` and
  `issues`") is part of the contract; do not substitute a different type
  even if it seems simpler.
- Every derived document (proposal, spec, architecture, blueprint, plan)
  must quote the request's interface contract **verbatim** in a dedicated
  section — never summarize or paraphrase it — so downstream phases can
  implement against the exact wording.
- External callers depend on these names: a correct implementation under a
  different name is a failure, not a success.

## Defaults for anything not pinned

- Use only the Python standard library unless the request says otherwise.
- Keep internal structure simple; prefer a single file when the request
  names a single file.
- When information is genuinely missing, choose the simplest reasonable
  behavior and record the assumption.
