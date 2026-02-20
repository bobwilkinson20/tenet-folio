# Sync & Valuation System

This document is the authoritative reference for the two connected subsystems that power portfolio data in TenetFolio:

1. **Sync System** — fetches holdings from external providers and records point-in-time snapshots
2. **Valuation System** — revalues those holdings at market close prices every calendar day, producing the time-series data that drives charts and net worth history

Together they answer: "What did I own, and what was it worth, on any given day?"

---

## Table of Contents

1. [Data Entities](#1-data-entities)
2. [Sync Workflow](#2-sync-workflow)
3. [Staleness Gating](#3-staleness-gating)
4. [Provider Abstraction](#4-provider-abstraction)
5. [Valuation & DHV System](#5-valuation--dhv-system)
6. [Backfill Algorithm](#6-backfill-algorithm)
7. [Price Resolution](#7-price-resolution)
8. [Manual Holdings](#8-manual-holdings)
9. [Classification Waterfall](#9-classification-waterfall)
10. [Timezone Handling](#10-timezone-handling)
11. [Startup Behavior](#11-startup-behavior)
12. [Edge Cases & Design Decisions](#12-edge-cases--design-decisions)
13. [Failure Modes & Resilience](#13-failure-modes--resilience)

---

## 1. Data Entities

For the high-level data model, entity relationships, and schema design rationale, see [ARCHITECTURE.md](./ARCHITECTURE.md#data-model). The field-level details below focus on columns relevant to sync and valuation behavior.

**SyncSession** — A single sync invocation. Wraps all provider results.

| Field | Type | Notes |
|-------|------|-------|
| id | UUID (String 36) | Primary key |
| timestamp | DateTime | Naive UTC (`datetime.now(timezone.utc)`) |
| is_complete | Boolean | True if at least one account synced successfully |
| error_message | Text | Set when entire sync fails (no accounts synced) |

**SyncLogEntry** — Per-provider result within a sync session.

| Field | Type | Notes |
|-------|------|-------|
| sync_session_id | FK → SyncSession | |
| provider_name | String | "SnapTrade", "SimpleFIN", "IBKR", "Coinbase", "Schwab" |
| status | String | "success" / "partial" / "failed" |
| error_messages | JSON | List of error strings from the provider |
| accounts_synced | Integer | Count of accounts that produced a snapshot |
| accounts_stale | Integer | Count of accounts skipped due to stale data |

**Account** — A linked brokerage account.

| Field | Type | Notes |
|-------|------|-------|
| provider_name | String | Provider that manages this account |
| external_id | String | Provider's identifier for this account |
| name | String | Display name (may be user-edited) |
| name_user_edited | Boolean | True if user customized the name (prevents overwrite on sync) |
| institution_name | String | E.g., "Vanguard", "Fidelity" |
| is_active | Boolean | Inactive accounts stop syncing |
| include_in_allocation | Boolean | Whether to include in asset allocation views |
| assigned_asset_class_id | FK → AssetClass | Account-level classification override |
| balance_date | DateTime | Provider-reported date of the data (for staleness gating) |
| last_sync_time | DateTime | When this account was last processed |
| last_sync_status | String | "success" / "failed" / "stale" / "error" / "syncing" / "skipped" |
| last_sync_error | String | Error message from last sync attempt |
| **Unique constraint** | | `(provider_name, external_id)` |

**AccountSnapshot** — Per-account result within a sync session.

| Field | Type | Notes |
|-------|------|-------|
| account_id | FK → Account | |
| sync_session_id | FK → SyncSession | |
| status | String | "success" / "failed" |
| total_value | Numeric(18,4) | Sum of all holdings' snapshot_value |
| balance_date | DateTime | Provider-reported balance date at time of snapshot |
| **Unique constraint** | | `(account_id, sync_session_id)` |

**Holding** — A position captured at snapshot time. Immutable after creation.

| Field | Type | Notes |
|-------|------|-------|
| account_snapshot_id | FK → AccountSnapshot | |
| security_id | FK → Security | `ondelete=RESTRICT` |
| ticker | String | Denormalized for readability |
| quantity | Numeric(18,8) | Number of shares/units |
| snapshot_price | Numeric(18,4) | Provider-reported price at sync time |
| snapshot_value | Numeric(18,2) | Provider-reported market value at sync time |
| **Unique constraint** | | `(account_snapshot_id, security_id)` |

**DailyHoldingValue (DHV)** — Daily revaluation of a holding at market close price.

| Field | Type | Notes |
|-------|------|-------|
| valuation_date | Date | Calendar date |
| account_id | FK → Account | Denormalized for efficient querying |
| account_snapshot_id | FK → AccountSnapshot | Traces which snapshot supplied the quantity |
| security_id | FK → Security | `ondelete=RESTRICT` |
| ticker | String | Denormalized for readability |
| quantity | Numeric(18,8) | Carried from the active snapshot |
| close_price | Numeric(18,6) | Market closing price (or snapshot price as fallback) |
| market_value | Numeric(18,2) | `quantity * close_price`, rounded to nearest cent |
| **Unique constraint** | | `(valuation_date, account_id, security_id)` |

**Security** — Ticker metadata and classification.

| Field | Type | Notes |
|-------|------|-------|
| ticker | String | Unique |
| name | String | Human-readable name |
| manual_asset_class_id | FK → AssetClass | Security-level classification override |

---

## 2. Sync Workflow

**Entry point:** `POST /api/sync` → `api/sync.py:trigger_sync()`

The endpoint returns **409 Conflict** if a sync is already in progress (see [Concurrent Sync Prevention](#concurrent-sync-prevention)). Otherwise it runs a two-phase process:

```
Phase 1: Valuation backfill (fill yesterday's gaps)
Phase 2: Main sync (fetch from providers, create snapshots)
```

### Phase 1: Valuation Backfill

Calls `PortfolioValuationService.backfill()` to fill any DHV gaps through yesterday. This ensures historical data is complete before new data arrives. Best-effort — failures are logged but don't block the sync. (The startup backfill in `main.py` provides a second safety net if this fails.)

### Phase 2: Main Sync

Orchestrated by `SyncService.trigger_sync()`:

#### Step 1: Create SyncSession

A new `SyncSession(is_complete=False)` is created and flushed to get its ID.

#### Step 2: Iterate Enabled Providers

The provider registry returns all configured providers. Each is synced independently.

#### Step 3: Per-Provider Sync

For each provider (SnapTrade, SimpleFIN, IBKR, Coinbase, Schwab):

**3a. Fetch data** — Call `provider.sync_all()` (preferred) or `provider.get_holdings()`. Returns a `ProviderSyncResult` containing accounts, holdings, activities, errors, and balance dates.

**3b. Upsert accounts** — For each account in the provider response:
- If `(provider_name, external_id)` exists: update `institution_name` only. If `name_user_edited=True`, preserve the user's custom name.
- If new: create Account with `is_active=True`.

**3c. Build holdings map** — Group holdings by account external_id. Build balance_dates dict. Track which accounts the provider actually returned ("responded IDs").

**3d. Apply provider errors** — Provider errors are now structured `ProviderSyncError` objects carrying `institution_name` and `account_id` fields (see [Provider Abstraction](#4-provider-abstraction)). Errors are matched directly to accounts by institution name or account ID. Set `last_sync_status="error"` for matched accounts.

**3e. Per-account sync** — For each active account from this provider:

```
┌─────────────────────────────────┐
│ 1. Staleness gate               │ ← Compare balance dates
│    (skip if stale)              │
├─────────────────────────────────┤
│ 2. Consolidate duplicate        │ ← Merge same-symbol holdings
│    holdings                     │
├─────────────────────────────────┤
│ 3. Mark account as "syncing"    │
├─────────────────────────────────┤
│ 4. Create AccountSnapshot       │ ← total_value = sum(holdings)
├─────────────────────────────────┤
│ 5. Create Holding records       │ ← One per security
│    (ensure Security exists)     │
├─────────────────────────────────┤
│ 6. Create DHV for today         │ ← Using snapshot prices
├─────────────────────────────────┤
│ 7. Update account status        │ ← last_sync_status = "success"
└─────────────────────────────────┘
```

If any step fails, the account gets an AccountSnapshot with `status="failed"` and `last_sync_status="failed"`.

**3f. Handle missing accounts** — Accounts in the database but NOT in the provider response are marked `last_sync_status="skipped"` with an error message indicating the connection may need attention.

**3g. Sync activities** — If the provider returned activities, sync them via `ActivityService`. Best-effort.

**3h. Create SyncLogEntry** — Records the overall provider result: how many accounts synced, how many were stale, and any error messages.

#### Step 4: Finalize SyncSession

- `is_complete = True` if at least one account synced successfully across all providers.
- `is_complete = False` with `error_message` if nothing synced.
- Commit the transaction.

---

## 3. Staleness Gating

**Problem:** Some providers (notably SimpleFIN) always return all holdings even if the underlying data hasn't changed. Without gating, every sync would create redundant snapshots.

**Solution:** Compare the incoming `balance_date` from the provider with the stored `Account.balance_date`.

```
incoming_date = provider's balance_date for this account
existing_date = account.balance_date (from last sync)

if incoming_date is None → proceed (provider doesn't supply dates)
if existing_date is None → proceed (first sync)
if incoming_date > existing_date → proceed (fresh data)
if incoming_date ≤ existing_date → SKIP (stale)
```

Both dates are normalized to naive UTC before comparison (SQLite strips timezone info).

**When an account is skipped as stale:**
- No AccountSnapshot or Holdings are created
- `last_sync_status = "stale"`
- `last_sync_time` still advances (the sync was attempted)
- The SyncLogEntry records `accounts_stale` count
- The SyncSession can still be `is_complete=True` (other accounts may have synced)

**Which providers use balance dates:**
- SimpleFIN: provides balance_dates
- SnapTrade: provides balance_dates
- IBKR, Coinbase, Schwab: don't provide balance_dates (always proceed)

---

## 4. Provider Abstraction

For the provider protocol, registry, supported providers, and exception hierarchy, see [ARCHITECTURE.md](./ARCHITECTURE.md#multi-provider-architecture).

The sync-relevant details: providers that support **balance dates** (SnapTrade, SimpleFIN) enable [staleness gating](#3-staleness-gating). Providers that support **activities** (SnapTrade, IBKR, Schwab) have transactions synced as a best-effort step after holdings. Each provider returns a `ProviderSyncResult` containing holdings, accounts, errors, balance dates, and activities.

---

## 5. Valuation & DHV System

### Purpose

The sync system captures what you own at the moment you sync. The valuation system fills in every day between syncs, using market closing prices, so charts reflect daily market movements without requiring the user to sync daily.

### How DHV Records Are Created

DHV records are created at **two distinct points**:

#### At Sync Time (immediate)

When a sync creates Holdings for an account, `PortfolioValuationService.create_daily_values_for_holdings()` immediately creates DHV rows for **today** using the **snapshot prices** from the provider.

This ensures current portfolio data is available immediately after sync, even before market close prices are fetched.

Uses upsert semantics: if a `(valuation_date, account_id, security_id)` row already exists (e.g., second sync today), it updates the existing row.

#### During Backfill (historical)

`PortfolioValuationService.backfill()` fills DHV gaps from the last valued day through yesterday, using **market closing prices** from Yahoo Finance (equities) or CoinGecko (crypto).

This runs:
- On application startup (`main.py` lifespan)
- Before every sync (`api/sync.py`)

Since backfill fills through yesterday and sync creates today's data, there is no need for a post-sync backfill — it would compute `start_date = today > end_date = yesterday` and return immediately.

When backfill runs and yesterday's DHV rows already exist (e.g., created during a previous sync with snapshot prices), it upserts them with end-of-day market closing prices.

### DHV Unique Key

```
(valuation_date, account_id, security_id)
```

This means exactly **one DHV row per security per account per day**, regardless of how many syncs occurred. The key is by account (not by snapshot) because when a new sync produces updated quantities, the old snapshot's data is superseded.

### Reading DHV Data

The portfolio service reads the most current data by querying for the latest `valuation_date` per account, joined to the most recent AccountSnapshot. This is the single source of truth for "what is my portfolio worth?"

---

## 6. Backfill Algorithm

### Incremental Backfill (`backfill()`)

Called on startup and before every sync. Fills from the last DHV date through yesterday.

**Important limitation:** Incremental backfill only fills from the frontier (max DHV date per account) forward. It cannot detect or fill **interior gaps** — e.g., if DHV rows exist for Days 1-3 and Day 7, but Days 4-6 are missing, incremental backfill starts from Day 7 and never revisits the gap. Interior gaps are handled by the startup gap repair (see [Startup Behavior](#11-startup-behavior)), which runs `diagnose_gaps()` + `full_backfill()`. This means interior gaps self-heal on the next app restart but persist during the current session.

```
1. Determine fill range
   ├── For each active account:
   │     └── Find max(DailyHoldingValue.valuation_date) + 1 day
   │         or first successful snapshot date if no DHV exists
   ├── start_date = min(per-account dates)  ← ensures no account left behind
   └── end_date = yesterday

2. If start_date > end_date → already current, return

3. Resolve snapshot timelines per account
   ├── Load all successful AccountSnapshots ordered by timestamp
   ├── Convert timestamps from naive UTC → local dates  (critical!)
   └── Build SnapshotWindow list: (effective_date, snapshot_id, holdings)

4. Collect all unique symbols across all timelines

5. Filter non-market symbols
   ├── Remove cash tickers (USD, CASH, CAD, SPAXX, etc.)
   ├── Remove synthetic tickers (_SF:*, _MAN:*, _ZERO_BALANCE)
   └── Detect crypto symbols (securities classified under "Crypto" asset class)

6. Fetch market data
   └── MarketDataService.get_price_history(symbols, start_date, end_date,
       crypto_symbols=...)
       ├── Crypto symbols → CoinGecko
       └── Equities → Yahoo Finance

7. Build price lookup with carry-forward
   ├── For each symbol, for each calendar day:
   │     ├── If market price exists → use it
   │     └── Else → carry forward most recent prior price
   └── Result: dict[symbol → dict[date → Decimal]]

8. Walk each day, calculate values
   ├── For each day from start_date to end_date:
   │     └── For each account:
   │           ├── Find active snapshot window (latest effective_date ≤ day)
   │           └── For each holding in that window:
   │                 ├── Get price from lookup (fallback: snapshot_price)
   │                 ├── market_value = quantity × price, rounded to $0.01
   │                 └── Upsert DailyHoldingValue row

9. Commit
```

### Per-Account Start Date Logic

This is the most important part of the backfill, and the source of a critical bug that has since been fixed.

**The bug:** The old code used `max(all_dhv_dates)` globally. If accounts A and B synced on Day N but account C didn't, the global max would be Day N — skipping C's gap entirely.

**The fix:** Calculate per-account max DHV dates, add 1 day (to skip the already-complete last day), and take the **minimum**:

```
Account A: last DHV = Day N+2  → start = Day N+3
Account B: last DHV = Day N+2  → start = Day N+3
Account C: last DHV = Day N    → start = Day N+1  ← behind!

start_date = min(N+3, N+3, N+1) = Day N+1
```

This ensures any account that's behind triggers backfill for the full range.

**Special cases:**
- Active account with no DHV at all → uses its first successful snapshot date
- Inactive accounts → excluded from start date calculation (don't hold back active accounts)

### Full Backfill (`full_backfill()`)

Used for historical gap repair. Ignores the `_get_start_date()` optimization entirely — it finds the earliest completed SyncSession, converts its timestamp to a local date, and backfills from that date through yesterday. This ensures every day since the first-ever sync is covered, regardless of what DHV rows already exist.

**`repair` parameter:**

The upsert logic in `_run_backfill` normally only updates `close_price` and `market_value` on existing rows — it preserves the original `quantity` and `account_snapshot_id`. When `repair=True`, it overwrites **all** fields, correcting rows where the snapshot reference or quantity is wrong (e.g., from a bug or data corruption).

| Caller | `repair` | What it does |
|--------|----------|--------------|
| Startup gap repair (`main.py`) | `False` | Fills missing rows and updates prices, but preserves quantity/snapshot on existing rows |
| CLI tool (`scripts/dhv_diagnostics.py --repair`) | `True` | Full rewrite of all fields — the nuclear option for fixing corrupted data |

**When full backfill runs at startup:**

The startup gap check is gated behind a cached date (`system.dhv_verified_through` in UserPreference) to avoid running the expensive `diagnose_gaps()` query on every restart:

1. Read `system.dhv_verified_through` from preferences
2. If already verified through yesterday → skip entirely
3. Otherwise, run `diagnose_gaps()` to count missing and **partial** DHV rows
4. If missing or partial gaps found → run `full_backfill(db)` (without repair)
5. Update `system.dhv_verified_through` to yesterday

This means the diagnostic only runs once per calendar day — the first startup after midnight local time.

**CLI tool (`scripts/dhv_diagnostics.py`):**

For manual investigation and repair, a standalone CLI tool is available:

```bash
cd backend

# Diagnose: print per-account gap analysis
uv run python -m scripts.dhv_diagnostics

# Repair: full backfill with repair=True (overwrites all fields)
uv run python -m scripts.dhv_diagnostics --repair
```

This is the only way to run `full_backfill(repair=True)`. Use it when you suspect DHV rows have wrong quantities or snapshot references, not just missing prices.

### Gap Diagnosis (`diagnose_gaps()`)

Analyzes DHV completeness for every account:

- **Expected range:** first successful snapshot date → yesterday (active accounts) or last snapshot date (inactive accounts)
- **Actual coverage:** count of distinct `valuation_date` rows for that account in the expected range
- **Missing days:** dates with zero DHV rows, with a list of specific missing dates (capped at 100)
- **Partial days:** dates where some but not all expected securities have DHV rows. Detected by comparing per-date DHV row counts against holding counts from the governing snapshot. Zero-balance sentinel rows (`_ZERO_BALANCE`) are excluded from this comparison.

Returns per-account: `account_id`, `account_name`, `expected_start`, `expected_end`, `expected_days`, `actual_days`, `missing_days`, `missing_dates`, `partial_days`, `partial_dates`.

Used by:
- Startup gap repair (to decide whether `full_backfill` is needed)
- `/api/portfolio/dhv-diagnostics` endpoint (for UI display)
- CLI tool `scripts/dhv_diagnostics.py` (for manual investigation)

---

## 7. Price Resolution

### Price Selection Priority

For each holding on each day, the system resolves a price using this cascade:

```
1. Cash equivalent?
   ├── Ticker in CASH_TICKERS (USD, CASH, CAD, SPAXX, FDRXX, SWVXX, VMFXX, FZFXX)
   └── Or _CASH: prefix (e.g., _CASH:USD from Coinbase)
   → Always $1.00

2. Synthetic ticker? (_SF:*, _MAN:*, _ZERO_BALANCE)
   → Use snapshot_price (no market data exists for these)

3. Market data available?
   → Use closing price from Yahoo Finance (equities) or CoinGecko (crypto)

4. No market data?
   → Fall back to snapshot_price from the active AccountSnapshot
```

**Note:** Cash detection uses explicit ticker matching only. An earlier `snapshot_price == $1.00` heuristic was removed because it caused false positives for securities trading at exactly $1.00.

### Carry-Forward Logic

Market data has gaps on weekends and holidays. The price lookup handles this:

```
Mon: $100.00 (market data)
Tue: $101.50 (market data)
Wed: $101.50 (holiday — carried forward from Tue)
Thu: $102.00 (market data)
Fri: $103.00 (market data)
Sat: $103.00 (carried forward from Fri)
Sun: $103.00 (carried forward from Fri)
```

### Market Data Providers

The `MarketDataService` routes symbol requests to the appropriate provider:

**Yahoo Finance** (`integrations/yahoo_finance_client.py`) — equities and fixed-income:
- For single-date requests, uses a 10-day lookback to handle weekends/holidays
- Returns empty list for unavailable or failed symbols (errors logged, not raised)

**CoinGecko** (`integrations/coingecko_client.py`) — crypto:
- Resolves symbols via a hardcoded top-30 mapping (BTC, ETH, SOL, etc.) with an on-demand `/search` fallback for unknown tokens
- Fetches daily prices via `/market_chart/range` with hourly-to-daily conversion
- Retries on 429 rate limits; optional `COINGECKO_API_KEY` env var for higher limits

Crypto symbols are detected automatically: `PortfolioValuationService._detect_crypto_symbols()` queries for securities classified under the "Crypto" `AssetClass`. This set is passed to `MarketDataService.get_price_history(crypto_symbols=...)` which splits the request accordingly.

---

## 8. Manual Holdings

Manual accounts (`provider_name = "Manual"`) allow users to add holdings that aren't managed by any provider (e.g., real estate, private investments).

### How Manual Holdings Differ from Provider Holdings

| Aspect | Provider Holdings | Manual Holdings |
|--------|------------------|-----------------|
| Created by | Sync from external provider | User via API |
| Frequency | On sync | On user action |
| Staleness gate | Balance date comparison | N/A (always creates new snapshot) |
| Ticker | Real market ticker | Real ticker or synthetic `_MAN:{hash}` |

### Manual Holding Operations

Every add/update/delete creates a **new SyncSession + AccountSnapshot** containing the full set of current holdings. This preserves complete history — you can always see what the account held at any point in time.

**Add:** Read current holdings → append new one → create new snapshot with all.

**Update:** Read current holdings → replace target → create new snapshot with all.

**Delete:** Read current holdings → remove target → create new snapshot with remaining.

SQLite's `BEGIN IMMEDIATE` transaction mode serializes these operations at the database level to prevent race conditions during the read-modify-write cycle. (An earlier `threading.Lock` was replaced because it failed silently in multi-worker scenarios where each worker got an independent lock instance.)

### Synthetic Tickers

Non-tradable "Other" holdings (described by name, not ticker) get synthetic tickers:

- Format: `_MAN:{12-hex-chars}` (SHA-256 of `description:unique_id`)
- Stored as quantity=1, price=market_value (since there's no per-share price)
- If a holding is deleted and re-added with the same description, the original ticker is reused (preserves asset classification history)
- Hidden from users in the UI via `isSyntheticTicker()` utility

### DHV for Manual Holdings

Manual holding operations immediately create DHV rows for today, just like provider syncs. The backfill system then fills subsequent days using snapshot prices (since synthetic tickers have no market data).

---

## 9. Classification Waterfall

See [ARCHITECTURE.md](./ARCHITECTURE.md#1-asset-classification-waterfall) for the full classification waterfall (Account Override → Security Override → Unclassified). The valuation system uses this classification to detect crypto symbols for CoinGecko routing (see [Price Resolution](#7-price-resolution)).

---

## 10. Timezone Handling

This is one of the most subtle parts of the system and a frequent source of bugs.

### Core Rule

All timestamps are stored as **naive UTC** in SQLite. SQLite has no native timezone type, so `datetime.now(timezone.utc)` produces a timezone-aware Python datetime, but SQLite strips the tzinfo on storage.

### The Danger: UTC Dates vs. Local Dates

```
User syncs at 5:00 PM Pacific on February 10th:
  UTC timestamp: 2025-02-11 01:00:00  (next day in UTC!)
  Local date:    2025-02-10            (same day locally)
```

If you call `.date()` on the UTC timestamp, you get February 11th — the wrong day. The sync happened on the user's February 10th.

### The Solution: `_utc_to_local_date()`

```python
def _utc_to_local_date(utc_dt: datetime) -> date:
    """Convert a naive UTC datetime to a local calendar date."""
    aware = utc_dt.replace(tzinfo=timezone.utc)
    return aware.astimezone().date()
```

This is used everywhere snapshot timestamps need to be mapped to calendar dates:
- Resolving snapshot timelines in backfill
- Determining backfill start dates
- Gap diagnosis

### Rules

1. **Never use `.date()` on a UTC timestamp** for local-date comparisons.
2. **Never use `func.date(SyncSession.timestamp)` in SQL** for local-date comparisons — load snapshots and convert in Python.
3. **Never use `date.today()` interchangeably with UTC dates** — they differ after 4 PM PT (or whenever local time crosses midnight UTC).
4. **In tests, use `time(12, 0)` (noon UTC)** for sync timestamps, not midnight UTC. Midnight UTC maps to the previous local day in Pacific time.

### Balance Date Normalization

Provider balance dates may arrive with or without timezone info. Before comparison in the staleness gate, both sides are normalized to naive UTC:

```python
if incoming.tzinfo is not None:
    incoming = incoming.replace(tzinfo=None)
```

---

## 11. Startup Behavior

On application startup (`main.py` lifespan), three things happen in order:

### 1. Incremental Backfill

`PortfolioValuationService.backfill()` fills DHV gaps from the last valued date through yesterday. This handles the common case where the app was stopped overnight and needs to catch up.

### 2. Historical Gap Check and Repair

The system checks for interior DHV gaps (completely missing days) and **partial gaps** (days with incomplete security coverage) that incremental backfill can't reach (see the [interior gap limitation](#incremental-backfill-backfill) above). This uses the `system.dhv_verified_through` preference cache to avoid running the expensive `diagnose_gaps()` query on every restart — see [Full Backfill](#full-backfill-full_backfill) for the detailed flow.

Note: startup calls `full_backfill(db)` **without** `repair=True`, so it fills missing rows and updates prices but preserves quantity/snapshot references on existing rows. The full `repair=True` mode is only accessible via the CLI tool (`python -m scripts.dhv_diagnostics --repair`).

### 3. Seed Default Asset Classes

`AssetTypeService.seed_default_asset_classes()` ensures the default asset class set exists. Idempotent.

All startup steps are wrapped in try/except — a failure in any step doesn't prevent the application from starting.

---

## 12. Edge Cases & Design Decisions

### Duplicate Holdings from Same Provider

**Problem:** Coinbase returns multiple `_CASH:USD` positions from different portfolio breakdowns, causing an IntegrityError on the `(account_snapshot_id, security_id)` unique constraint.

**Solution:** `SyncService._consolidate_holdings()` merges holdings with the same symbol before creating Holding records. Quantities and values are summed; price is recalculated as `total_value / total_quantity`. A warning is logged for each merge.

### Same-Day Multiple Syncs

**Problem:** If a user syncs twice in one day, DHV rows must be updated, not duplicated.

**Solution:** DHV creation uses upsert semantics — queries for `(valuation_date, account_id, security_id)` first. If found, updates `close_price` and `market_value`. The unique constraint `(valuation_date, account_id, security_id)` (not by snapshot) ensures exactly one row per security per account per day.

### Liquidated Accounts (Empty Holdings)

**Problem:** If a user sells all holdings, the provider returns an empty list. Without special handling, the account would disappear from time-series charts.

**Solution:** An AccountSnapshot is still created with `total_value=0` and `status="success"`. A **zero-balance sentinel** DHV row (`_ZERO_BALANCE` ticker, `market_value=0`) is written so the account shows $0 in net worth charts instead of vanishing. Sentinel rows are mutually exclusive with real holding rows for a given (account, date) — when real holdings return, the sentinel is automatically cleaned up and vice versa. The `_ZERO_BALANCE` security is hidden from the securities list and unassigned count in the UI.

### Accounts Missing from Provider Response

**Problem:** An account exists in the database but the provider didn't return it (connection may be broken).

**Solution:** These accounts are marked `last_sync_status="skipped"` with error message "Account not returned by provider — connection may need attention." No snapshot is created, preserving the last known state.

### Partial Provider Failure

**Problem:** One provider fails but others succeed.

**Solution:** Each provider syncs independently within the same SyncSession. A failure in SnapTrade doesn't block SimpleFIN. The SyncSession is `is_complete=True` as long as at least one account from any provider synced. SyncLogEntries record per-provider status.

### Per-Account Savepoints and Transaction Isolation

Each account sync runs within a database savepoint (`db.begin_nested()`). If one account fails, previously synced accounts in the same transaction are preserved.

Best-effort operations (activity sync, lot reconciliation) also run within their own savepoints, so a failure rolls back cleanly without tainting the main sync session. Each provider's `_sync_provider_accounts()` call is wrapped in a per-provider savepoint so a partial flush from a failed provider doesn't contaminate the next provider.

### Concurrent Sync Prevention

`SyncService` uses a class-level `threading.Lock` with non-blocking acquisition. If a sync is already running, the endpoint returns **409 Conflict** immediately. The lock is always released in a `finally` block. This is appropriate for the single-user, single-process deployment model; multi-worker setups would need external coordination.

### User-Edited Account Names

**Problem:** Provider sync would overwrite a user's custom account name.

**Solution:** `Account.name_user_edited` flag. If True, sync only updates `institution_name`, not `name`.

### DHV with `account_id` AND `account_snapshot_id`

`account_snapshot_id` traces which snapshot supplied the quantity (audit trail). `account_id` is denormalized because most time-series queries filter or group by account — joining through AccountSnapshot on every chart query would be wasteful.

### Holding and DHV Store Both `security_id` and `ticker`

`security_id` provides referential integrity (with `ondelete="RESTRICT"`). `ticker` is denormalized for human readability in queries and logs. Since tickers don't change for a given Security record, the denormalization is safe.

### `include_in_allocation` Separate from `is_active`

A user might want an account visible in net worth (active) but excluded from allocation targets — for example, a house or HSA that would distort their equity/bond split.

---

## 13. Failure Modes & Resilience

The system is designed to be resilient at every level:

| Failure | Impact | Recovery |
|---------|--------|----------|
| Provider API down | That provider's accounts get `status="failed"` | Other providers still sync. Retry on next sync. |
| One account errors | That account gets failed AccountSnapshot | Other accounts in same provider still sync (savepoint isolation). |
| Market data API down | DHV uses snapshot prices as fallback | Backfill retries on next run. |
| Pre-sync backfill fails | Warning logged | Sync proceeds. Startup backfill catches up. |
| Startup backfill fails | Warning logged | App still starts. Pre-sync backfill catches up. |
| Gap repair fails | Warning logged | Retries on next startup. |
| Stale data from provider | Account marked "stale", no snapshot created | Next sync with fresh data proceeds normally. |
| Duplicate holdings | Consolidated by symbol before insertion | Warning logged. |
| Same-day re-sync | DHV upserted (updated, not duplicated) | Transparent to user. |
| Concurrent sync request | 409 Conflict returned | User retries after current sync completes. |
| Activity/lot sync fails | Rolled back via savepoint, holdings preserved | Warning logged. Retry on next sync. |

### Error Propagation Rules

1. Provider-level errors are caught and logged per-provider — they never prevent other providers from syncing.
2. Account-level errors are caught per-account — they never prevent other accounts from syncing.
3. Best-effort operations (activity sync, lot reconciliation) run in savepoints — failures roll back cleanly without tainting the sync session.
4. Valuation errors (backfill, market data) are caught and logged — they never prevent sync from completing.
5. The sync endpoint returns 200 with a SyncSession on success. Success/failure details are communicated via `is_complete` and `sync_log` entries in the response.
6. Error HTTP codes: 409 for concurrent sync, 502 for provider auth/connection errors (safe message, no internal details leaked), 500 only for truly unexpected errors.
