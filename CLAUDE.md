# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

"Полка" is a server-rendered book blog built with FastAPI, Jinja2 and SQLite (stdlib `sqlite3`, no ORM). All user-facing text is in Russian.

## Commands

Windows, PowerShell. Use the interpreter in `.venv`: bare `python` may resolve to the Microsoft Store stub.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn main:app --reload    # http://127.0.0.1:8000
```

The repo has no test suite, linter or build step. To test without touching real data, set `database.DB_PATH` to a temporary file before entering `TestClient(main.app)`. `TestClient` needs `httpx`, which is not in `requirements.txt`.

## Architecture

- `main.py` holds routes, form validation and Jinja filters. `database.py` holds all SQL. Routes are sync `def`, and each database function opens and closes its own connection.
- Book columns are listed in `SCHEMA` and `BOOK_FIELDS` (`database.py`), and form fields in `book_form` and `validate` (`main.py`) and `templates/edit.html`. Adding a field means changing all of these. There are no migrations: `CREATE TABLE IF NOT EXISTS` will not alter an existing `books.db`.
- `init_db` runs at startup and seeds the example books only while `PRAGMA user_version` is 0, so deleted examples do not come back. `books.db` is gitignored.
- Search must use the custom SQL function `fold` (registered in `connect()`): SQLite's `LOWER` and `LIKE` do not fold Cyrillic case. `LIKE` wildcards in the query are escaped in `list_books`.
- Forms: every `Form` field is an optional string, so that invalid input reaches `validate()` and is re-rendered in `edit.html` with status 422. `edit.html` serves both create and edit, switching on `book.id`, and `book` can hold raw form strings (for example `year` and `rating`) rather than database types.
- Successful POSTs redirect with 303. Toasts are driven by query flags (`?saved=1`, `?deleted=1`).
- Because form fields never fail FastAPI validation, the `RequestValidationError` handler treats every such error as a bad URL and renders `404.html`. A new required parameter would be reported as a 404.
- Covers are pure CSS (`.cover` in `static/style.css`, `cover` macro in `templates/_macros.html`), coloured by the `cover_hue` filter from the book id. Their sizes use `cqi` units because percentage padding resolves against the parent, not the cover.
- The site has no authentication: anyone with access can edit or delete books.
