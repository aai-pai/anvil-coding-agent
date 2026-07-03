# Anvil Standing Instructions

Defaults, fallbacks, and conventions for every Anvil run. Injected into every
phase prompt; the intake step must not ask a question this file already
answers. Keep this file short — it costs tokens on every phase.

## Defaults when the request is underspecified

- **Language/stack**: web UI → single-file HTML/CSS/JS (no build tooling, no
  frameworks); CLI or data tool → Python 3, standard library only.
- **Project shape**: the smallest complete, runnable version of what was asked.
  One entry point; no configuration files unless required to run.
- **Persistence**: none unless asked. If state must survive restarts, prefer
  `localStorage` (web) or a JSON file next to the script (Python).
- **External services/APIs**: never call paid or authenticated services unless
  the request names one and how to authenticate.
- **Dependencies**: avoid them. If one is genuinely needed, pick the most
  common, permissively-licensed option and pin it.

## Fallback behaviors

- Ambiguous requirement → implement the simplest reading that a reasonable
  user would accept, and record the choice as an assumption; do not stall.
- Conflicting requirements → the more recent statement in
  `background-information.md` (including `## Clarifications`) wins.
- Missing non-functional detail (performance, scale, auth) → assume a
  single-user, local, low-volume context.
- A phase output that cannot fully satisfy its inputs → deliver the working
  subset and state what was cut, rather than an ambitious broken whole.

## Conventions

- Plain, readable code over cleverness; comments only where intent is not
  obvious from the code.
- Errors: fail with a clear message; never swallow exceptions silently.
- Naming: kebab-case files, descriptive identifiers, English throughout.
- Docs: each generated document states its decisions and assumptions
  explicitly; link sibling documents with relative markdown links.
- Tests (when the qa phase runs): pytest for Python; plain assertions in a
  `tests/` folder mirroring `src/`.
