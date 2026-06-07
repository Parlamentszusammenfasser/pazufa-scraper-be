# CLAUDE.md - pazufa-scraper-be

Scrapy-based scraper for the Berlin parliament (Abgeordnetenhaus von Berlin).
Extracts legislative data (Vorgänge, Dokumente) from PARDOK and submits it to the PaZuFa API.

## Project Overview

Parlamentszusammenfasser (PaZuFa) is a system consisting of several parts:

1. **Backend** – offers an API to submit parliamentary proceedings (Parlamentarische Vorgänge) and a read API to retrieve the submitted data.
2. **Website** – reads the backend API and presents the data.
3. **Scrapers** – several scrapers, each collecting data from a parliament. This project is the scraper for the Berliner Abgeordnetenhaus: it transforms the data into the PaZuFa format and submits it to the backend.

The backend runs quality checks on submitted data, merges/deduplicates it with existing data, and updates the database.

## Project Tooling

- **uv** as package manager
- **ruff** for linting and formatting
- **ty** for typechecking
- **prek** for git hooks
- **jj** for version control

## Common Commands

```sh
# Install dependencies
uv sync

# Run the scraper locally
uv run scrapy runspider -s WAHLPERIODE=19 pazufa_scraper_be/spiders/gesetz_vorgang.py

# Fullstack test: run the scraper against the local backend.
# Without an API token the submit step is skipped; setting the token enables it.
# The token can be passed as env var PAZUFA_API_TOKEN or via `-s API_TOKEN=...`.
# Run it twice to verify that the produced data is correctly shaped and that the
# backend can merge/deduplicate it.
# IMPORTANT: Tell the user you want to run a fullstack test BEFORE running it.
# The user starts the local backend in a clean state; do not run it without confirmation.
PAZUFA_API_TOKEN='pazufa-ABRAKADABRAHEXEN-DRACHENSCHUPPENHAARFAERBEMITTELVERORDNUNGSBLATTFASERSTRUKTURWASSERMINDESTAUFNAHMESTEMPELGESETZ1A6a3671b9' uv run scrapy runspider -s WAHLPERIODE=19 pazufa_scraper_be/spiders/gesetz_vorgang.py

# Run tests (no env vars needed)
uv run pytest

# Linting and formatting
uv run ruff check --fix .
uv run ruff format .

# Typechecking
uv run ty check
```

## Version Control (jj)

- Use `jj new` regularly — keep changes atomic and reorderable
- Add a description with `jj describe -m "..."` for each change
- Use bookmarks when sensible, but **never push**
- Conventional commit messages: `feat:`, `fix:`, `chore:`, etc.

## Conventions

- Google-style docstrings (configured in ruff)
- ruff is configured with `ALL` rules enabled minus a specific ignore list (see pyproject.toml)
- use blank line after `return`/`raise`/`else`/`elif` before next line
- when calling methods/function write out parameter names
- prefer easy testable code
