# Deauville Festival du Rire

A festival programme and scheduling service for the 10–13 June 2027 edition.
It provides a command-line interface, a FastAPI JSON API, a public programme
website, and an admin interface. The API and CLI share the same domain rules;
successful changes are validated and saved to `data/festival.json`.

## Install and run

Install Python 3.13 or newer and [uv](https://docs.astral.sh/uv/), then from
the repository root:

```bash
uv sync
```

The default sync installs the application and the development tools. Run the
CLI:

```bash
uv run python main.py
uv run python main.py day 2027-06-11
uv run python main.py artists
uv run python main.py now --at 2027-06-12T01:30
```

Omit `--at` to use the computer's local time. Start the website, admin and API
on one server with:

```bash
uv run uvicorn festival.api:app --reload
```

Open <http://127.0.0.1:8000/> for the public programme,
<http://127.0.0.1:8000/admin/> for administration, or
<http://127.0.0.1:8000/docs> for interactive API documentation. The route and
JSON contract is documented in [API.md](API.md).

## Tests and quality checks

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
```

The tests cover seed-data validation, slug generation, schedule conflicts,
workshop registration, persistence and API behavior. Mutations in the tests
use temporary JSON files and do not alter the checked-in festival data.

## Design

The domain lives in `festival/models.py`. `Venue` and `Artist` own their
normalized names and derived slugs. A frozen `Performance` value carries the
common schedule fields and a `kind` discriminator for solo shows, lineups and
workshops; its factory validates each kind's fields and its methods expose
the shared end time, festival day, identifier and cast. The `Festival` owns
these objects and is the only public route for adding, moving, removing or
registering performances. Its collections are exposed as tuples, while
mutations validate references, festival dates, venue/artist gaps, lineup
rules and workshop capacity before completing.

The API and CLI call the same model methods, so neither can bypass scheduling
rules. `festival/errors.py` gives callers explicit not-found, invalid-value,
conflict and storage errors; FastAPI translates these to the status codes in
the API contract. `FestivalRepository` in `festival/storage.py` applies each
change to a validated candidate, atomically saves it, and only then replaces
the in-memory festival. A failed validation or save leaves the previous
festival intact.

## Project structure

| Path | Responsibility |
| --- | --- |
| `festival/models.py` | Festival, venue, artist, performance, slugs and domain rules |
| `festival/errors.py` | Understandable domain and storage errors |
| `festival/storage.py` | JSON loading, validation, atomic writes and repository changes |
| `festival/api.py` | FastAPI routes, response shapes and static site serving |
| `festival/cli.py`, `main.py` | Programme, artists and current/next-show commands |
| `data/festival.json` | Festival data source |
| `web/public/` | Public festival website |
| `web/admin/` | Schedule and artist administration |
| `tests/` | Domain, persistence and API tests |

If JSON is replaced by a database, the storage and repository implementation
would change; the domain model, CLI and API can continue using the same
`Festival` operations. A SQLite storage implementation is not included.

## Implemented scope

The festival model enforces the rules in the original project brief, including
the 06:00 festival-day boundary, 30-minute venue and artist breaks, lineup
minimum duration, artist/venue references, and workshop registrations capped
by both the workshop limit and venue seats. The JSON file is revalidated when
loaded. The API supports the documented read and admin-write routes and serves
the supplied public and admin pages.

The optional SQLite storage extension is not implemented.
