# runs/

Holds the **output of Anvil's 13-phase lifecycle** — i.e. Anvil actually *building something*.

## Rules

- **One run = one folder.** Name it `<date>-<slug>` (e.g. `2026-06-26-calculator`).
- **Every run is independent and self-contained.** There are no shared inputs (no fixtures) —
  the request is written directly inside each run folder.
- This whole folder is `.gitignore`d (only this README is tracked). Runs are disposable.

## Run folder layout

```
runs/2026-06-26-calculator/
    domain-knowledge/
        background-information.md   <- write the "what to build" request here
    docs/   src/   tests/   logs/    <- filled in by Anvil, phase by phase
    .anvil/                          <- run-state.json, checkpoints, events (generated)
```

## Starting a new run

1. Create the folder: `runs/<date>-<slug>/domain-knowledge/`
2. Describe what to build in `background-information.md`
3. Point Anvil (`runtime/`) at that folder and run it

> Note: this replaces the old throwaway workspaces under `temp/`
> (anvil_live, calc_ws, test1, etc.). `temp/` is now only for one-off scripts.
