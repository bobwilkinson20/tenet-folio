# Architecture Overview

This document provides a high-level overview of the portfolio manager's architecture, key design decisions, and system components.

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Technology Stack](#technology-stack)
3. [Data Model](#data-model)
4. [Multi-Provider Architecture](#multi-provider-architecture)
5. [Key Design Decisions](#key-design-decisions)
6. [Service Layer](#service-layer)
7. [Future Enhancements](#future-enhancements)

## System Architecture

The application follows a two-tier architecture running locally:

```
┌───────────────────────────────────────┐
│  React Frontend (TypeScript + Vite)   │
│  http://localhost:5173                │
└──────────────┬────────────────────────┘
               │ REST API (JSON)
               ▼
┌─────────────────────────────────────┐
│  FastAPI Backend (Python 3.13)      │
│  http://localhost:8000              │
└──────────────┬──────────────────────┘
               │
     ┌─────────┴──────────┬──────────────────┐
     ▼                    ▼                  ▼
  SQLite            Provider APIs      File System
  (portfolio.db)    (SnapTrade,        (.env, tokens)
                     SimpleFIN,
                     IBKR, etc.)
```

### Backend Structure

```
backend/
├── main.py                    # FastAPI app entry point
├── config.py                  # Environment configuration
├── database.py                # SQLAlchemy setup
├── models/                    # SQLAlchemy ORM models
├── schemas/                   # Pydantic request/response schemas
├── services/                  # Business logic layer
├── api/                       # API route handlers
├── integrations/              # External provider clients
├── scripts/                   # Setup and maintenance scripts
├── alembic/                   # Database migrations
└── tests/                     # Test suite
```

### Frontend Structure

```
frontend/src/
├── api/                       # API client layer
├── types/                     # TypeScript type definitions
├── components/                # React components
├── pages/                     # Page-level components
├── hooks/                     # Custom React hooks
├── context/                   # React context providers
└── utils/                     # Utility functions
```

## Technology Stack

### Backend

- **Web Framework:** FastAPI (async, auto-generated OpenAPI docs)
- **Database:** SQLite with SQLAlchemy ORM
- **Migrations:** Alembic
- **Validation:** Pydantic v2
- **Testing:** pytest with in-memory SQLite
- **Code Quality:** ruff (linting + formatting)

**Why FastAPI?**
- Automatic request/response validation via Pydantic
- Built-in OpenAPI (Swagger) documentation
- Async support for external API calls
- Type hints improve IDE support and catch errors early

**Why SQLite?**
- Zero configuration for local deployment
- Sufficient for single-user workload
- ACID compliance for data integrity
- Easy backup (single file)

### Frontend

- **Framework:** React 19
- **Language:** TypeScript (strict mode)
- **Build Tool:** Vite
- **Styling:** Tailwind CSS v4
- **HTTP Client:** Axios
- **Routing:** React Router
- **Charts:** Recharts
- **Testing:** Vitest + React Testing Library

**Why React 19?**
- Concurrent rendering for smooth UX
- Hooks-based composition
- Large ecosystem and community
- TypeScript first-class support

**Why Tailwind v4?**
- Utility-first CSS reduces custom CSS
- New `@import "tailwindcss"` syntax (no directives)
- JIT compiler for minimal bundle size
- Consistent design system

## Data Model

### Core Entities

```
Account (central entity — a linked brokerage account)
  ├─ provider_name (e.g., "SnapTrade", "SimpleFIN")
  ├─ external_id (provider's account ID)
  ├─ name
  ├─ institution_name (e.g., "Vanguard")
  ├─ account_type
  ├─ is_active
  ├─ include_in_allocation
  ├─ assigned_asset_class_id ─► AssetClass (optional override)
  ├─ balance_date (provider-reported)
  └─ last_sync_time, last_sync_status

AssetClass (user-defined allocation categories)
  ├─ name (e.g., "US Equities", "Bonds")
  ├─ color (hex, for charts)
  └─ target_percent (allocation target)

Security (ticker metadata and classification)
  ├─ ticker (unique)
  ├─ name
  └─ manual_asset_class_id ───► AssetClass (user override)

SyncSession (one per sync invocation)
  ├─ timestamp
  ├─ is_complete
  └─ error_message

SyncLogEntry (per-provider result within a sync)
  ├─ sync_session_id ─────────► SyncSession
  ├─ provider_name
  ├─ status ("success" | "failed" | "partial")
  ├─ error_messages (JSON list)
  ├─ accounts_synced
  └─ accounts_stale

AccountSnapshot (per-account result within a sync)
  ├─ account_id ──────────────► Account
  ├─ sync_session_id ─────────► SyncSession
  ├─ status ("success" | "failed")
  ├─ total_value
  └─ balance_date

Holding (position captured at snapshot time)
  ├─ account_snapshot_id ─────► AccountSnapshot
  ├─ security_id ─────────────► Security
  ├─ ticker (denormalized)
  ├─ quantity
  ├─ snapshot_price (provider-reported price at sync time)
  └─ snapshot_value (provider-reported value at sync time)

DailyHoldingValue (daily revaluation time series)
  ├─ valuation_date
  ├─ account_id ──────────────► Account
  ├─ account_snapshot_id ─────► AccountSnapshot (source of quantity)
  ├─ security_id ─────────────► Security
  ├─ ticker (denormalized)
  ├─ quantity (carried from snapshot)
  ├─ close_price (market closing price from yfinance)
  └─ market_value (quantity × close_price)

Activity (transaction history)
  ├─ account_id ──────────────► Account
  ├─ provider_name, external_id
  ├─ activity_date, settlement_date
  ├─ type ("buy" | "sell" | "dividend" | "transfer")
  ├─ description
  ├─ ticker, units, price, amount
  ├─ currency, fee
  └─ raw_data (JSON, provider debug data)
```

### Relationships

```
                        AssetClass
                       ▲          ▲
          (account     │          │  (security
           override)   │          │   override)
                       │          │
Account ──1:N──► AccountSnapshot ──1:N──► Holding ──N:1──► Security
   │                   │                                      ▲
   │ 1:N               │ N:1                                  │ N:1
   ▼                   ▼                                      │
Activity          SyncSession ──1:N──► SyncLogEntry           │
                                                              │
Account ──1:N──► DailyHoldingValue ───────────────────────────┘
                       │
                       │ N:1
                       ▼
                 AccountSnapshot (source of quantity)
```

- **Account** 1:N **AccountSnapshot** - Each sync creates a snapshot per account
- **Account** 1:N **Activity** - Transaction history per account
- **Account** 1:N **DailyHoldingValue** - Daily revaluations per account
- **AccountSnapshot** 1:N **Holding** - Holdings captured at sync time
- **AccountSnapshot** N:1 **SyncSession** - Grouped by sync invocation
- **SyncSession** 1:N **SyncLogEntry** - Per-provider result log
- **Holding** N:1 **Security** - Ticker metadata and classification
- **Account** N:1 **AssetClass** - Account-level classification override (takes precedence)
- **Security** N:1 **AssetClass** - Security-level classification override

### Unique Constraints

| Constraint | Columns | Purpose |
|---|---|---|
| Account | `(provider_name, external_id)` | Same account from different providers are distinct |
| AccountSnapshot | `(account_id, sync_session_id)` | One snapshot per account per sync |
| Holding | `(account_snapshot_id, security_id)` | One row per security per snapshot |
| DailyHoldingValue | `(valuation_date, account_id, security_id)` | One valuation per security per account per day |
| Security | `(ticker)` | One metadata record per ticker |
| Activity | `(provider_name, account_id, external_id)` | Prevents duplicate transaction imports |

### Schema Design Rationale

**Snapshot price vs. market price (Holding vs. DailyHoldingValue)**

This is the most important modeling distinction. Holdings store `snapshot_price` and `snapshot_value` - exactly what the provider reported at sync time. DailyHoldingValues store `close_price` and `market_value` - calculated from market closing prices fetched from yfinance. This separation serves several purposes:
- **Fidelity:** Snapshot data preserves the provider's reported values as an immutable record, even if they differ slightly from market close
- **Inter-sync tracking:** DailyHoldingValues revalue the portfolio using closing prices every day, so net worth charts reflect market movements even when the user hasn't synced in days
- **Auditability:** You can always compare "what the provider said" vs. "what the market said" for any given position

**DailyHoldingValue has both `account_id` and `account_snapshot_id`**

`account_snapshot_id` traces the source of the quantity data (which sync produced the position). `account_id` is denormalized for efficient querying - most time-series queries filter or group by account, and joining through AccountSnapshot on every chart query would be wasteful.

**DailyHoldingValue keyed by `(date, account_id, security_id)` not `(date, snapshot_id, security_id)`**

Valuations are logically per-account-per-day. When a new sync produces an updated snapshot, the old snapshot's quantities are superseded. Keying by account ensures exactly one valuation row per security per account per day, regardless of how many syncs occurred.

**Holding and DailyHoldingValue store both `security_id` and `ticker`**

`security_id` provides referential integrity (with `ondelete="RESTRICT"` to prevent orphaning). `ticker` is denormalized for human readability in queries and logs. Since tickers don't change for a given Security record, the denormalization is safe.

**`include_in_allocation` separate from `is_active`**

A user might want an account visible in their net worth (active) but excluded from allocation targets - for example, a house or an HSA they don't want distorting their equity/bond split. These are independent concerns.

**SyncSession → AccountSnapshot → Holding hierarchy**

Each sync creates one SyncSession, one AccountSnapshot per account, and Holdings within each snapshot. This enables per-account sync status tracking (one account can fail while others succeed) and creates a clean audit trail linking every holding back to the exact sync that produced it.

## Multi-Provider Architecture

The system supports multiple data aggregation providers simultaneously.

### Supported Providers

1. **SnapTrade** - Unified API for 20+ brokerages
2. **SimpleFIN** - Bank/brokerage aggregation ($15/year)
3. **Interactive Brokers** - Direct IBKR Flex Query integration
4. **Coinbase** - Advanced Trade API (crypto holdings)
5. **Charles Schwab** - Direct Schwab API via OAuth

### Provider Protocol

All providers implement a common interface:

```python
class ProviderProtocol(Protocol):
    def list_accounts(self, db: Session) -> list[ProviderAccount]:
        """Fetch accounts from provider."""

    def get_holdings(self, db: Session, account: Account) -> list[ProviderHolding]:
        """Fetch current holdings for an account."""
```

### Provider Registry

The `ProviderRegistry` dynamically selects enabled providers based on environment variables:

```python
registry = ProviderRegistry()
for provider in registry.get_enabled_providers():
    accounts = provider.list_accounts(db)
    # Sync accounts...
```

This allows users to configure any combination of providers by setting credentials in `.env`.

## Key Design Decisions

### 1. Asset Classification Waterfall

Securities are classified using a priority-based waterfall:

1. **Account Override** - If account has `assigned_asset_class_id`, use for entire account value
2. **Security Override** - If security has `manual_asset_class_id`, use it
3. **Unclassified** - Default if both above fail

**Rationale:** Gives users maximum control. The waterfall is designed to be extended with additional automated classification steps (see [Future Enhancements](#future-enhancements)) between user overrides and unclassified, without changing the user-facing override model.

### 2. Snapshot and Valuation Model

See [Schema Design Rationale](#schema-design-rationale) above for detailed discussion of the snapshot vs. daily valuation separation and the reasoning behind each modeling choice.

### 3. Synthetic Tickers

Non-tradable assets (SimpleFIN manual holdings, brokerage cash) get synthetic tickers:
- Format: `_SF:{hash}` (SimpleFIN), `_MAN:{hash}` (manual)
- Allows treating all holdings uniformly in the database
- Hidden from user in UI (detected via `isSyntheticTicker()` utility)

### 4. UUID Storage

UUIDs stored as `String(36)` rather than SQLite BLOB:
- Human-readable in database browser
- Works with any database (SQLite lacks native UUID type)
- Minor storage overhead (36 bytes vs 16 bytes)

**Tradeoff:** Slight storage cost for improved debuggability.

### 5. User Preferences API

UI state that should persist across sessions stored server-side:
- Dashboard allocation filter toggle
- Table sort/filter preferences
- Hidden accounts toggle

**Rationale:** Avoids localStorage complexity, enables cross-device sync in future.

### 6. Single-User Assumption

No authentication layer in MVP:
- Runs locally on `localhost`
- `.env` credentials are user-specific
- All database records belong to single user

## Service Layer

### Core Services

**SyncService** - Orchestrates provider syncs
- Calls provider clients to fetch data
- Creates snapshots and holdings
- Handles errors and logs results
- Triggers portfolio valuation after successful sync

**PortfolioService** - Portfolio calculations
- Current portfolio summary (best-available data per account)
- Allocation calculations with classification waterfall
- Net worth aggregation

**ClassificationService** - Asset classification
- Implements classification waterfall
- Batch classification for performance

**PortfolioValuationService** - Daily revaluation
- Fetches closing prices from yfinance
- Creates `DailyHoldingValue` records
- Backfills historical data when new holdings appear

**ProviderService** - Provider management
- Lists enabled providers
- Manages provider-specific settings
- Handles provider health checks

**AccountService** - Account CRUD operations
- List, retrieve, and update accounts
- Manage account properties (name, active status, asset class assignment)

**ActivityService** - Transaction history persistence
- Syncs activities from providers with deduplication by external ID
- Serializes raw provider data for debugging

**AssetTypeService** - Asset class management
- CRUD for asset classes with unique names and colors
- Target allocation percentage validation (must sum to 100%)
- Deletion guards when securities or accounts reference a class

**ManualHoldingsService** - User-created holdings
- Add, update, and delete holdings in manual accounts
- Atomic snapshot creation to preserve full account state history
- Generates synthetic tickers for non-tradable holdings

**MarketDataService** - Historical price data
- Delegates to pluggable market data providers (default: YahooFinance)
- Returns structured price results for portfolio valuation

**PreferenceService** - User preference CRUD
- Key-value store with JSON serialization
- Backs the User Preferences API (see [decision #5](#5-user-preferences-api))

### Service Patterns

**Dependency Injection:** Services receive `db: Session` as parameter (no global state)

**Batch Operations:** Services optimize for bulk operations where possible:
- `classify_holdings_batch()` - Classify multiple holdings in 2 queries
- `backfill_valuations()` - Batch insert valuations

**Error Handling:** Services raise specific exceptions; API layer converts to HTTP responses

**Logging:** All CRUD operations logged at INFO level for audit trail

## Future Enhancements

**External data feed for ETF/fund asset classification.** The classification waterfall currently relies on user overrides only. Integrating an external data source (e.g., Morningstar, ETF provider APIs) could automatically classify ETFs and mutual funds by their underlying asset allocation. This would slot into the waterfall between user overrides and unclassified, reducing the manual classification burden for users with many holdings.

**Remote deployment.** Related to multi-user support, the app could be deployed to a server for access from multiple devices. This would require authentication, HTTPS, and potentially swapping SQLite for PostgreSQL.

## Additional Resources

- [Sync & Valuation System](./sync-and-valuation.md) - Detailed sync workflow, DHV backfill, and edge cases
- [CLAUDE.md](../CLAUDE.md) - Development guidelines and patterns

## API Documentation

When the backend is running, interactive API docs are available at:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
