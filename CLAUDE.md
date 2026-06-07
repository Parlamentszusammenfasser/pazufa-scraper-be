# CLAUDE.md - pazufa-scraper-be

Scrapy-based scraper for the Berlin parliament (Abgeordnetenhaus von Berlin).
Extracts legislative data (Vorgänge, Dokumente) from PARDOK and submits it to the PaZuFa API.

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
