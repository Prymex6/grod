# Working on Gród

The rules below are what the existing code follows. They are short because
they are meant to be read once and then remembered.

## Getting set up

```bash
docker compose -f infra/docker-compose.yml up -d   # PostgreSQL, Valkey, Mailpit

cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn grod.main:app --port 8000

cd frontend
npm install
npm run dev
```

The tests need PostgreSQL and Valkey running. They use their own database and
their own Valkey namespace, and they create and drop it themselves, so they
never touch development data. If your services are somewhere else, point the
tests at them with `GROD_TEST_POSTGRES` and `GROD_TEST_VALKEY`.

## Before calling anything done

Both of these have to pass. CI runs exactly the same commands.

```bash
cd backend  && uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run pytest
cd frontend && npm run check
```

## Language

- **Everything in the code is English** — names, comments, log lines, error
  messages, commit messages. No diacritics in identifiers.
- **Nothing a user reads is written in the code.** Interface text goes through
  the translation files in `frontend/src/i18n/locales/`, which are typed, so a
  missing key is a compile error. Polish is the default, English is beside it.
- The module names shown in the console (Kuźnia, Skarbiec, …) are proper nouns
  and are not translated. They live in `frontend/src/modules.ts` and nowhere
  else; the code itself uses functional names such as `ci` and `artifacts`.

## Code

- Small functions and modules, one responsibility each. Clear names over
  short ones. No duplication, no dead code.
- Full typing: hints everywhere in Python, TypeScript in `strict` mode, no
  `any`.
- Validate at the edges — HTTP bodies, forms, configuration files. Handle
  errors explicitly; never swallow one quietly.
- Secure by default: no secrets in the code, parameterised queries only,
  permissions checked on the server every time, safe defaults.
- Comment the **why**, not the what.
- Tests for the logic, end-to-end tests for the paths that matter.
- Follow the conventions of the ecosystem: PEP 8 in Python, the usual React
  conventions in the console.

## Three modules are doors to the outside

Each external program is reached through exactly one module, so that it can
be replaced without touching anything above it:

| program | the only module that runs it |
|---|---|
| `git` | `backend/src/grod/repositories/git.py` |
| `docker` | `backend/src/grod/apps/containers.py` |
| administrative SQL | `backend/src/grod/databases/postgres.py` |

Nothing else calls them. This is the rule most worth keeping.

## Database changes

Every schema change is an Alembic revision in `backend/migrations/versions/`,
numbered in order, with both `upgrade` and `downgrade` written.

## Commits

One change per commit. Subject in the imperative, under about 70 characters,
then a paragraph saying *why* — not a list of the files touched. Look at the
existing history for the shape.
