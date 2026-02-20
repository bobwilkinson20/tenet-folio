# Contributing to TenetFolio

Thank you for your interest in contributing! This guide will help you get started.

## Development Setup

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node.js 20+ (LTS)
- npm 10+

### Backend

```bash
cd backend
uv sync
cp .env.example .env   # Configure your settings
uv run alembic upgrade head
uv run python -m uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Branch Naming

Create branches from `main` with the issue number:

- `feature/123-short-description` — New features
- `fix/456-bug-description` — Bug fixes
- `refactor/789-description` — Refactoring
- `docs/012-description` — Documentation

## Development Workflow

We practice Test-Driven Development (TDD) whenever practical:

1. **Write tests first** — Define expected behavior through tests
2. **See them fail** — Run tests to confirm they fail (red)
3. **Implement** — Write minimal code to pass tests (green)
4. **Refactor** — Improve code while keeping tests green

If you write code first (prototyping, exploring), tests are still required before committing.

To check coverage:

```bash
# Backend
uv run pytest --cov=. --cov-report=html

# Frontend
npm run test:coverage
```

All new services should have >90% coverage. See the README's [Running Tests](README.md#running-tests) section for more options.

## Pre-Commit Checklist

All checks must pass before committing:

```bash
# Backend (from backend/)
uv run ruff check .        # Linting (use --fix for auto-fixes)
uv run pytest              # Tests

# Frontend (from frontend/)
npm run type-check         # TypeScript compilation
npm run lint               # ESLint
npm run test               # Tests
```

## Pull Request Process

1. Push your branch and create a PR:
   ```bash
   git push -u origin feature/123-description
   gh pr create --title "Brief description" --body "Closes #123"
   ```
2. Include `Closes #123` (or `Fixes #123`) in the PR body to auto-close the linked issue on merge.
3. Ensure CI checks pass.
4. **Do not update `CHANGELOG.md`** — it is maintained separately at release time to avoid merge conflicts.
5. PRs are merged into `main` after review.

## Code Style

- **Python:** Enforced by [Ruff](https://docs.astral.sh/ruff/)
- **TypeScript:** Enforced by ESLint

## Architecture Reference

See [CLAUDE.md](CLAUDE.md) for full architecture details, code patterns, file locations, and design decisions. It serves as both AI-assistant context and a comprehensive developer reference.

## Questions?

Open a [GitHub issue](https://github.com/bobwilkinson20/tenet-folio/issues) for bugs, feature requests, or questions.
