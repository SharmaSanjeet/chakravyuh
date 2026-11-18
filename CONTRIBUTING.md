# Contributing to Chakravyuh AI

Thanks for your interest. This guide covers the development environment, the tests, and
the project conventions.

## Requirements

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node 20+ (for the React dashboard)

## Getting started

```bash
# Backend
uv venv .venv
uv pip install --python .venv -e . pytest ruff
.venv/bin/chakravyuh                 # honeypot :8080 + dashboard/API :5000

# Frontend (hot reload, proxy to :5000)
cd web && npm install && npm run dev
```

Per-environment configuration (prefix `CHAKRAVYUH_`): see [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md)
and [`.env.example`](.env.example).

## Tests and lint

```bash
.venv/bin/python -m pytest -q      # full suite
.venv/bin/ruff check chakravyuh tests  # lint
.venv/bin/ruff format chakravyuh tests # format
cd web && npm run build            # type-check + SPA build
```

CI (`.github/workflows/ci.yml`) runs exactly this on every push/PR.

## Agent binaries

The remote agent is distributed as a self-contained binary (PyInstaller). The per-platform
recipe is in [`chakravyuh/agent/BUILD.md`](chakravyuh/agent/BUILD.md); the `release.yml` workflow
builds them (linux amd64/arm64 + windows) when a `vX.Y.Z` tag is published.

## Structure

See the tree in the [README](README.md#architecture). In short: `chakravyuh/` is the
backend (engine + API + sensor ingestion), `web/` the dashboard, and `docs/` the guides.

- The **engine** (`maze`, `scenarios`, `detection`, `rng`) is pure and deterministic.
- **Detection is central**: `scoring.py` is shared by the local honeypot and remote
  ingestion — add rules there, not in two places.
- The **frontend contract** comes from `schemas.py` (Pydantic, camelCase); do not hand-build
  JSON in the routers.

## Conventions

- Code and comments in English (consistent with the repo); `ruff` must pass clean.
- Synchronous **SQLAlchemy** (FastAPI threadpool); `httpx` **async** only for outbound HTTP.
- Add tests for new logic; the tests isolate the DB via `tests/conftest.py`.
- Commit convention: a one-line summary + a body explaining the why.

## Security

Found a vulnerability? Do not open a public issue: see [`SECURITY.md`](SECURITY.md).
