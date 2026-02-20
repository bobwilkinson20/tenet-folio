# CLAUDE.md

This file provides context for Claude when working on this codebase.

## Project Overview

Personal portfolio manager that syncs brokerage accounts via multiple data aggregation providers (SnapTrade and SimpleFIN) to track holdings, asset allocation, and net worth. Single-user app running locally.

## Architecture

- **Backend:** FastAPI (Python 3.13) on `localhost:8000`
- **Frontend:** React + TypeScript + Vite on `localhost:5173`
- **Database:** SQLite with SQLAlchemy ORM + Alembic migrations
- **Data Providers:** SnapTrade, SimpleFIN, Interactive Brokers, Coinbase, and Charles Schwab (any combination, credentials in `.env`)

## Key Design Decisions

1. **Multi-Provider Architecture:** Provider Registry pattern allows using SnapTrade, SimpleFIN, or both simultaneously. Accounts are scoped by provider with composite unique constraint `(provider_name, external_id)`.
2. **Provider Auth:** One-time setup via scripts (`setup_snaptrade.py`, `setup_simplefin.py`, `setup_ibkr.py`, `setup_coinbase.py`, `setup_schwab.py`). Credentials stored in macOS Keychain (preferred) with `.env` fallback. Setup scripts offer to store in keychain after validation.
3. **UUIDs:** Stored as `String(36)` in SQLite (no native UUID type).
4. **Sync Throttle:** Holdings sync limited to once per 24h unless forced.
5. **Classification Waterfall:** Account override → Security override → Unclassified.

## Common Commands

A root-level `Makefile` provides shortcuts for the most common operations:

```bash
make setup                              # Install deps + apply migrations
make dev                                # Run backend + frontend concurrently
make test                               # Run all tests (backend + frontend)
make lint                               # Ruff check + ESLint + type-check
make format                             # Auto-format backend code
make migrate                            # Apply pending Alembic migrations
make migration msg="description"        # Create a new migration
```

### Raw Commands (what the Makefile targets run)

```bash
# Backend (uses uv — https://docs.astral.sh/uv/)
cd backend
unset DATABASE_URL                                   # Clear if set from another project
uv run python -m uvicorn main:app --reload           # Run server
uv run pytest                                        # Run tests
uv run ruff check .                                  # Lint (required before commit)
uv run alembic upgrade head                          # Apply migrations
uv run alembic revision --autogenerate -m "msg"      # Create migration
uv run python -m scripts.backfill_securities         # Create Security records from existing holdings
uv run python -m scripts.migrate_env_to_keychain               # Migrate .env credentials to Keychain
uv run python -m scripts.migrate_env_to_keychain --clean        # Migrate and remove from .env
uv run python -m scripts.encrypt_database                       # Encrypt existing unencrypted DB with SQLCipher
uv run python -m scripts.db_shell                               # Interactive SQL shell (handles encrypted DBs)

# Frontend
cd frontend
npm run dev          # Dev server
npm run type-check   # TypeScript type checking (required before commit)
npm run build        # Type check + build
npm run test         # Run tests
npm run lint         # ESLint (required before commit)
```

## Code Patterns

### Backend

**Models** use `String(36)` for UUIDs with a generator:
```python
def generate_uuid() -> str:
    return str(uuid.uuid4())

id = Column(String(36), primary_key=True, default=generate_uuid)
```

**Timestamps** use timezone-aware UTC:
```python
created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
```

**Database sessions** are injected via FastAPI dependency:
```python
def my_endpoint(db: Session = Depends(get_db)):
    ...
```

**Logging:** All services must use Python's `logging` module. Every CRUD operation (create, update, delete) and sync lifecycle event should log at INFO level. Use `logger = logging.getLogger(__name__)` at module level. Centralized config is in `backend/logging_config.py`; noisy third-party loggers (SQLAlchemy, httpx, yfinance, etc.) are suppressed to WARNING.

### Frontend

**API calls** use the configured axios client:
```typescript
import { apiClient } from "@/api/client";
const response = await apiClient.get<Account[]>("/accounts");
```

**Types** mirror backend Pydantic schemas and live in `src/types/`.

**User Preferences** use the `usePreferences` hook for any UI state that should persist across page reloads:
```typescript
const { getPreference, setPreference } = usePreferences();
const hideInactive = getPreference("accounts.hideInactive", false);
// ...
setPreference("accounts.hideInactive", true);
```
Keys should be namespaced by page/feature (e.g., `accounts.hideInactive`). The hook loads all preferences on mount, applies optimistic updates, and rolls back on API errors. Prefer this over `useState` for any toggle, filter, or setting the user would expect to survive a refresh.

**Synthetic Tickers:** The backend generates synthetic ticker identifiers for holdings that aren't tradable securities (format: `_SF:{hash}` for SimpleFIN, `_MAN:{hash}` for manual "Other" holdings). These are internal identifiers and should NOT be displayed to users in UI views. Use the `isSyntheticTicker()` utility from `@/utils/ticker` to detect and hide them. Show only the security name for synthetic tickers. Exception: Admin/settings pages like SecurityList may show all tickers for management purposes.

## File Locations

| What | Where |
|------|-------|
| FastAPI app | `backend/main.py` |
| DB models | `backend/models/` |
| Pydantic schemas | `backend/schemas/` |
| API routes | `backend/api/` |
| Business logic | `backend/services/` |
| Provider protocol | `backend/integrations/provider_protocol.py` |
| Provider registry | `backend/integrations/provider_registry.py` |
| SnapTrade client | `backend/integrations/snaptrade_client.py` |
| SimpleFIN client | `backend/integrations/simplefin_client.py` |
| IBKR Flex client | `backend/integrations/ibkr_flex_client.py` |
| Schwab client | `backend/integrations/schwab_client.py` |
| IBKR setup script | `backend/scripts/setup_ibkr.py` |
| Coinbase setup script | `backend/scripts/setup_coinbase.py` |
| Schwab setup script | `backend/scripts/setup_schwab.py` |
| Schwab token refresh | `backend/scripts/refresh_schwab_token.py` |
| Schwab debug script | `backend/scripts/debug_schwab.py` |
| Credential manager | `backend/services/credential_manager.py` |
| Keychain migration | `backend/scripts/migrate_env_to_keychain.py` |
| DB encryption script | `backend/scripts/encrypt_database.py` |
| DB shell | `backend/scripts/db_shell.py` |
| React components | `frontend/src/components/` |
| TypeScript types | `frontend/src/types/` |
| API client | `frontend/src/api/client.ts` |

## Testing

- Backend uses pytest with in-memory SQLite fixture (`tests/conftest.py`)
- Frontend uses Vitest with React Testing Library
- Mock provider clients (`MockSnapTradeClient`, `MockSimpleFINClient`, `MockProviderRegistry`) for unit/integration tests

### SnapTrade Integration Tests

Real API tests against a paper trading account. These are excluded by default.

```bash
# Setup (one-time)
cp backend/.env.test.example backend/.env.test
# Edit .env.test with test account credentials

# Run SnapTrade integration tests
cd backend
uv run pytest -m snaptrade

# Run all tests including SnapTrade
uv run pytest -m ""
```

Test credentials should point to a dedicated test user with a paper trading connection.

### IBKR Flex Integration Tests

Real API tests against an IBKR account via the Flex Web Service. These are excluded by default.

```bash
# Setup (one-time)
cp backend/.env.test.example backend/.env.test
# Edit .env.test with your IBKR Flex Token and Query ID

# Run IBKR integration tests
cd backend
uv run pytest -m ibkr

# Run all tests including IBKR and SnapTrade
uv run pytest -m ""
```

The Flex Query must include Open Positions, Cash Report, and Trades sections. The setup script (`setup_ibkr.py`) will warn about missing sections.

### SimpleFIN Setup

To configure SimpleFIN:

```bash
cd backend
uv run python scripts/setup_simplefin.py
# Follow prompts to exchange your setup token for an access URL
# Add SIMPLEFIN_ACCESS_URL to your .env file
```

**Note:** The SimpleFIN setup token (base64 string from their web interface) is different from the access URL. The setup token is single-use and must be exchanged for a permanent access URL.

### Interactive Brokers Setup

To configure Interactive Brokers via the Flex Web Service:

```bash
cd backend
uv run python scripts/setup_ibkr.py
# Follow prompts to enter your Flex Token and Query ID
# Add IBKR_FLEX_TOKEN and IBKR_FLEX_QUERY_ID to your .env file
```

**Prerequisites:**
1. Generate a Flex Token in IBKR Client Portal (Settings > Flex Web Service Configuration)
2. Create a Flex Query (Reports > Flex Queries > Custom Flex Queries) with Open Positions, Cash Report, and Trades sections

### Coinbase Setup

To configure Coinbase via the Advanced Trade API:

```bash
cd backend
uv run python scripts/setup_coinbase.py
# Follow prompts to validate credentials
# Add COINBASE_KEY_FILE (or COINBASE_API_KEY + COINBASE_API_SECRET) to your .env file
```

**Prerequisites:**
1. Create a CDP API key at https://portal.cdp.coinbase.com/projects/api-keys
2. **Important:** Under Advanced Settings, select **ECDSA** as the key algorithm (the default Ed25519 is not compatible with the Advanced Trade SDK)
3. Grant "View" permission (read-only is sufficient)

**Two authentication options:**
- **JSON key file (recommended):** Download the key file from the CDP portal and provide its path
- **Inline key/secret:** Copy the API key and PEM private key directly. The secret must be double-quoted in `.env` to preserve newlines (e.g., `COINBASE_API_SECRET="-----BEGIN EC PRIVATE KEY-----\n..."`)

### Charles Schwab Setup

To configure Charles Schwab via the schwab-py library:

```bash
cd backend
uv run python scripts/setup_schwab.py
# Follow prompts to complete the OAuth flow
# Add SCHWAB_APP_KEY, SCHWAB_APP_SECRET, and SCHWAB_TOKEN_PATH to your .env file
```

**Prerequisites:**
1. Register at https://developer.schwab.com/ and create an app
2. Wait for the app status to change from "Approved - Pending" to "Ready for Use" (requires manual approval by Schwab)
3. Note your App Key, App Secret, and Callback URL from the app dashboard

**Token refresh:** Schwab refresh tokens expire after ~7 days. Re-authenticate by running:
```bash
cd backend
uv run python scripts/refresh_schwab_token.py
```

## Data Backfill Scripts

### Backfill Securities

If you have existing holdings but no Security records (happens when holdings were synced before the asset classification feature was added):

```bash
cd backend
unset DATABASE_URL
uv run python -m scripts.backfill_securities
```

This creates Security records for all tickers found in Holdings. Future syncs will automatically create Security records, so this is typically a one-time operation after upgrading to the asset classification feature.

## Testing Philosophy

**CRITICAL: All new features MUST include tests.** We practice Test-Driven Development (TDD) whenever possible.

### Test-Driven Development (TDD)

The ideal workflow for new features:

1. **Write tests first** - Define the expected behavior through tests
2. **See them fail** - Run tests to confirm they fail (red)
3. **Implement the feature** - Write the minimal code to pass tests
4. **See them pass** - Run tests to confirm they pass (green)
5. **Refactor** - Improve code while keeping tests green

### When TDD Isn't Practical

If you're prototyping or exploring, you may write code first. However:
- **Tests are still mandatory** before committing
- Add comprehensive tests covering all code paths
- Include edge cases discovered during development
- Test both success and failure scenarios

### What to Test

**Backend:**
- **Services:** All business logic, edge cases, validation rules
- **API endpoints:** Request/response handling, error cases, authentication
- **Models:** Relationships, constraints, default values
- **Integration:** Multi-component workflows (e.g., sync → holdings → securities)

**Frontend:**
- **Components:** Rendering, user interactions, state changes
- **API clients:** Request formatting, response handling, error cases
- **Hooks:** State management, side effects, cleanup
- **Integration:** User workflows across multiple components

### Test Coverage Requirements

- All new services must have >90% coverage
- All new API endpoints must have tests for success and error cases
- All bug fixes must include regression tests
- All edge cases discovered during development must be tested

### Running Tests

```bash
# Backend - must pass before committing
cd backend
uv run pytest                    # Run all tests
uv run pytest -v                 # Verbose output
uv run pytest tests/unit/        # Unit tests only
uv run pytest tests/integration/ # Integration tests only
uv run pytest -k "test_name"     # Run specific test

# Frontend - must pass before committing
cd frontend
npm run test              # Run all tests
npm run test:watch        # Watch mode during development
npm run test:coverage     # Generate coverage report
```

## Pre-Commit Requirements

**Always run these checks before committing.** All checks must pass with no errors.

```bash
make lint              # Ruff check + ESLint + type-check
make test              # All backend + frontend tests
```

Or run individually:

```bash
# Backend - run from backend/
uv run ruff check .        # Linting (use --fix for auto-fixes)
uv run pytest              # Run tests

# Frontend - run from frontend/
npm run type-check  # TypeScript compilation check
npm run lint        # ESLint
npm run test        # Run tests
```

**Critical:** The `type-check` command (included in `make lint`) catches import resolution errors, missing dependencies, and TypeScript compilation issues that would break the build. Always run it before committing frontend changes.

## Branch and PR Workflow

All enhancements should follow this branch/PR workflow:

1. **Create a feature branch** from `main`:
   ```bash
   git checkout main
   git pull origin main
   git checkout -b feature/123-short-description  # Include issue number
   ```

2. **Branch naming conventions** (include issue number to link to GitHub issues):
   - `feature/123-short-description` - New features or enhancements
   - `fix/456-bug-description` - Bug fixes
   - `refactor/789-description` - Code refactoring
   - `docs/012-description` - Documentation updates

3. **Make commits** on the feature branch with clear, descriptive messages.

4. **Before pushing**, ensure:
   - All tests pass (`uv run pytest` in backend, `npm run test` in frontend)
   - Linting passes (`uv run ruff check .` in backend, `npm run lint` in frontend)
   - TypeScript compiles (`npm run type-check` in frontend)
   - Build succeeds (`npm run build` in frontend - includes type-check)

5. **Push and create a PR:**
   ```bash
   git push -u origin feature/123-short-description
   gh pr create --title "Brief description" --body "Closes #123

   Details of changes"
   ```

   Including `Closes #123` (or `Fixes #123`) in the PR body will automatically close the issue when the PR is merged.

6. **Merge** the PR into `main` after review.

## Changelog

`CHANGELOG.md` follows the [Keep a Changelog](https://keepachangelog.com/) format. **Do not update CHANGELOG.md in pull requests** — it is maintained separately at release time to avoid merge conflicts across parallel PRs.

## Watch Out For

- **DATABASE_URL env var:** May be set from other projects; unset it or ensure `.env` is loaded
- **SimpleFIN setup token vs access URL:** The setup token (base64 string from SimpleFIN web interface) must be exchanged for an access URL using `setup_simplefin.py`. Don't put the setup token in `SIMPLEFIN_ACCESS_URL`.
- **Tailwind v4:** Uses `@import "tailwindcss"` not `@tailwind` directives
- **React 19:** Some patterns differ from React 18
- **Credential priority:** Settings loads credentials in this order: init args > macOS Keychain > env vars > `.env` file. Keychain values override `.env` for the 14 credential keys (see `CREDENTIAL_KEYS` in `credential_manager.py`). Non-secret settings (DATABASE_URL, ENVIRONMENT, etc.) skip keychain entirely.
- **SQLCipher key loss:** The `SQLCIPHER_KEY` in macOS Keychain is required to read an encrypted database. If the key is lost, the database is unrecoverable. The key is auto-generated on first run (fresh install) and stored in keychain. Back up the key if needed via `security find-generic-password -s tenet-folio -a SQLCIPHER_KEY -w`.

## Documentation

- [Architecture Overview](docs/ARCHITECTURE.md)
- [Sync & Valuation System](docs/sync-and-valuation.md)
