# To-do list CLI with JSON persistence

Build a command-line to-do list manager in Python with persistent storage and
input validation, including a pytest suite.

## Interface contract (must be followed exactly)

- The entry point must be `src/todo.py`, runnable as `python todo.py <command> ...`.
- The storage file path comes from the `TODO_DB_PATH` environment variable.
  When the file does not exist yet, treat the list as empty and create the
  file on the first write.
- **Storage format (critical):** the file must contain a JSON array of
  objects, each exactly `{"id": <int>, "title": <str>, "done": <bool>}`.
  Ids start at 1 and increase by 1 per added task.
- Commands:
  - `add <title>` — append a new task with `done: false`; print its id.
  - `list` — print one line per task in id order (any human-readable format
    that contains the title).
  - `done <id>` — mark that task's `done` field true. Unknown ids must exit
    with a non-zero exit code and print an error to stderr.
- All commands exit with code 0 on success.

Standard library only.
