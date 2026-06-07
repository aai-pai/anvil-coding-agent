# Anvil Mac Testing Observations

**Tester:** Jay Wei
**Branch:** test_anvil_v0.1.0_jw
**Date:** June 7th, 2026

## Environment Note

- Primary platform: Mac M-series (Apple Silicon)
- Intended platform per docs: Windows + WSL + Docker
- Docker not configured in this testing environment

## Setup Issues

### pip install -e runtime command fails

- Error: bug in repo's pyproject.toml file, references ../README.md outside runtime folder
- Claude workaround command: pip install fastapi httpx uvicorn pydantic pyyaml

### PowerShell script is windows only

- scripts/start-anvil.ps1 commands are windows only
- Mac workaround: Mac workaround is to use manual exports command

### Path with spaces break pip install

- originally had a "Computer Science" folder that caused an error
- Solution: remove aai-pai folder out of there

### Requires 2 VS Code windows:

- Window 1: the server terminal with either root folder or extensions folder open in VS Code editor
- Window 2: the Extension Development Host itself (F5)

### OpenRouter API key must be set before starting server

- Key set in one terminal session doesn't carry over to another
- Use `echo $OPENROUTER_API_KEY` to verify key is set before starting server

## Runtime Observations

### Offline vs real mode

- Default mode is offline even if you did provide Open Router API Key
- Must explicitly put command in terminal:
  `export ANVIL_EXECUTION_MODE="real"`

### Build output overwrites repo documentation

- Output goes to `src/` and `docs/` instead of a separate `workspace/` folder as noted in QUICKSTART.md, _need to clarify with Sunil_
- Anvil writes generated artifacts to `docs/` — same folder as repo's own documentation
- Running a build overwrites files like `proposal.md`, `spec.md`, `architecture.md`
- Build output should go to separate `workspace/docs/` folder?

### No run separation between builds

- All builds write to same `src/`, `docs/`, `logs/` folders
- No isolated folder per run (e.g. `workspace/run-1/`, `workspace/run-2/`)
- Files from different builds mix together making it impossible to review individual runs cleanly

### Mac vs intended environment

- Anvil designed for Windows + WSL + Docker as mentioned in setup docs
- Docker not configured
- Despite this, builds completed successfully — suggests codebase is portable
- All HTML/CSS/JS builds outside intended scope (target languages: Python, Rust, C)

### Successful runs:

- build command:
    - **Build 1 - Simple Calculator app:** `@anvil make a basic calculator app with basic functionalities using html css js`
        - All 12 phases completed successfully
          Generated working HTML/CSS/JS calculator with functional UI
        - Output files: `index.html`, `calculator.js`, `styles.css`
        - **Bug:** Calculator UI rendered but buttons are non-functional, which means JS logic is broken
        - Run time: ~ 1-2 minutes
    - **Build 2 - Todo List app:** `@anvil build a basic todo list app with basic functionalities of adding tasks, removing tasks, editing tasks, etc using html css and js`
        - All 12 phases completed successfully
        - Output files: `index.html`, `storage.js`, `taskManager.js`, `ui.js`
        - Todo list app works fine, operational
          ![Todo List App](related_images/todo-list-with-anvil1.png)

    - **Build 3 - Simple Calculator (re-run):** `@anvil build a basic calculator app with basic functionalities like +-/* using html css js`
        - All 12 phases completed successfully
        - Different file structure than Build 1: modular now
            - `core/calculator.js`, `ui/buttons.js`, `ui/display.js`, `main.js`
        - **Bug:** Wrong file paths in `index.html` - CSS and JS paths wrong
        - **Bug:** Calculator non-functional even after manually tweaking paths
        - **Bug:** Inconsistent output structure across the runs, same prompt produces different file organization, low temperature?
        - **Bug:** Old files from Builds 1 and 2 still present in same `src/` folder alongside new files
          ![File Structure](related_images/Build3-file-structure-anvil-1.0.png)
          ![Broken App](related_images/calculator-build3-anvil-1.0.png)
          ![Fixed Calculator App](related_images/postfix-build3-calculator-anvil-1.0.png)
