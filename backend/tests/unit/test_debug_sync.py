"""Tests for the debug_sync script."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from integrations.provider_protocol import (
    ProviderAccount,
    ProviderActivity,
    ProviderHolding,
    ProviderSyncResult,
)
from models import Account, Activity, Holding, SyncSession
from models.sync_log import SyncLogEntry
from scripts.debug_sync import (
    DEBUG,
    SUMMARY,
    VERBOSE,
    get_provider_client,
    main,
    print_accounts,
    print_activities,
    print_balance_dates,
    print_errors,
    print_holdings,
    print_sync_result,
    run_db_sync,
)

# --- Sample test data ---

SAMPLE_ACCOUNTS = [
    ProviderAccount(
        id="acct-001",
        name="My 401k",
        institution="Brokerage Inc",
        account_number="****1234",
    ),
    ProviderAccount(
        id="acct-002",
        name="Roth IRA",
        institution="Brokerage Inc",
        account_number=None,
    ),
]

SAMPLE_HOLDINGS = [
    ProviderHolding(
        account_id="acct-001",
        symbol="AAPL",
        quantity=Decimal("150"),
        price=Decimal("198.50"),
        market_value=Decimal("29775.00"),
        currency="USD",
        name="Apple Inc.",
    ),
    ProviderHolding(
        account_id="acct-001",
        symbol="VTI",
        quantity=Decimal("1200"),
        price=Decimal("245.30"),
        market_value=Decimal("294360.00"),
        currency="USD",
        name="Vanguard Total Stock Market ETF",
    ),
    ProviderHolding(
        account_id="acct-002",
        symbol="BND",
        quantity=Decimal("500"),
        price=Decimal("72.50"),
        market_value=Decimal("36250.00"),
        currency="USD",
        name="Vanguard Total Bond Market ETF",
    ),
]

SAMPLE_ACTIVITIES = [
    ProviderActivity(
        account_id="acct-001",
        external_id="txn-001",
        activity_date=datetime(2025, 1, 15, tzinfo=timezone.utc),
        type="buy",
        amount=Decimal("-5000.00"),
        description="Buy 25 shares AAPL",
        ticker="AAPL",
        units=Decimal("25"),
        price=Decimal("200.00"),
        currency="USD",
        fee=Decimal("0.00"),
        raw_data={"order_id": "abc123"},
    ),
    ProviderActivity(
        account_id="acct-001",
        external_id="txn-002",
        activity_date=datetime(2025, 1, 20, tzinfo=timezone.utc),
        type="dividend",
        amount=Decimal("123.45"),
        description="VTI Dividend",
        ticker="VTI",
        units=None,
        price=None,
        currency="USD",
        fee=None,
    ),
    ProviderActivity(
        account_id="acct-002",
        external_id="txn-003",
        activity_date=datetime(2025, 2, 1, tzinfo=timezone.utc),
        type="buy",
        amount=Decimal("-10000.00"),
        description="Buy BND",
        ticker="BND",
        units=Decimal("138"),
        price=Decimal("72.46"),
        currency="USD",
        fee=Decimal("1.00"),
    ),
]

SAMPLE_BALANCE_DATES = {
    "acct-001": datetime(2025, 1, 20, 16, 0, 0, tzinfo=timezone.utc),
    "acct-002": None,
}


def _make_sync_result(
    accounts=None,
    holdings=None,
    activities=None,
    errors=None,
    balance_dates=None,
):
    """Helper to create a ProviderSyncResult with defaults."""
    return ProviderSyncResult(
        holdings=holdings or [],
        accounts=accounts or [],
        errors=errors or [],
        balance_dates=balance_dates or {},
        activities=activities or [],
    )


# --- get_provider_client tests ---


class TestGetProviderClient:
    """Tests for get_provider_client()."""

    def test_valid_snaptrade_case_insensitive(self):
        """Valid provider names should be resolved case-insensitively."""
        mock_client = MagicMock()
        mock_client.is_configured.return_value = True

        with patch(
            "integrations.snaptrade_client.SnapTradeClient",
            return_value=mock_client,
        ):
            result = get_provider_client("snaptrade")
            assert result is mock_client

    def test_valid_simplefin(self):
        """SimpleFIN should be resolved correctly."""
        mock_client = MagicMock()
        mock_client.is_configured.return_value = True

        with patch(
            "integrations.simplefin_client.SimpleFINClient",
            return_value=mock_client,
        ):
            result = get_provider_client("SIMPLEFIN")
            assert result is mock_client

    def test_valid_ibkr(self):
        """IBKR should be resolved correctly."""
        mock_client = MagicMock()
        mock_client.is_configured.return_value = True
        mock_cls = MagicMock(return_value=mock_client)

        # Create a fake module with IBKRFlexClient
        fake_module = MagicMock()
        fake_module.IBKRFlexClient = mock_cls
        with patch.dict("sys.modules", {"integrations.ibkr_flex_client": fake_module}):
            result = get_provider_client("ibkr")
            assert result is mock_client

    def test_valid_coinbase(self):
        """Coinbase should be resolved correctly."""
        mock_client = MagicMock()
        mock_client.is_configured.return_value = True
        mock_cls = MagicMock(return_value=mock_client)

        # Create a fake module with CoinbaseClient
        fake_module = MagicMock()
        fake_module.CoinbaseClient = mock_cls
        with patch.dict("sys.modules", {"integrations.coinbase_client": fake_module}):
            result = get_provider_client("Coinbase")
            assert result is mock_client

    def test_valid_schwab(self):
        """Schwab should be resolved correctly."""
        mock_client = MagicMock()
        mock_client.is_configured.return_value = True
        mock_cls = MagicMock(return_value=mock_client)

        # Create a fake module with SchwabClient
        fake_module = MagicMock()
        fake_module.SchwabClient = mock_cls
        with patch.dict("sys.modules", {"integrations.schwab_client": fake_module}):
            result = get_provider_client("Schwab")
            assert result is mock_client

    def test_invalid_provider_exits(self):
        """Invalid provider name should exit with error."""
        with pytest.raises(SystemExit) as exc_info:
            get_provider_client("NotAProvider")
        assert exc_info.value.code == 1

    def test_unconfigured_provider_exits(self):
        """Unconfigured provider should exit with error."""
        mock_client = MagicMock()
        mock_client.is_configured.return_value = False

        with patch(
            "integrations.snaptrade_client.SnapTradeClient",
            return_value=mock_client,
        ):
            with pytest.raises(SystemExit) as exc_info:
                get_provider_client("SnapTrade")
            assert exc_info.value.code == 1


# --- Print function tests ---


class TestPrintErrors:
    """Tests for print_errors()."""

    def test_no_errors_no_output(self, capsys):
        """No errors should produce no output."""
        print_errors([])
        assert capsys.readouterr().out == ""

    def test_errors_printed(self, capsys):
        """Errors should be printed with numbered list."""
        print_errors(["API timeout", "Rate limited"])
        out = capsys.readouterr().out
        assert "Provider Errors (2)" in out
        assert "[1] API timeout" in out
        assert "[2] Rate limited" in out


class TestPrintAccounts:
    """Tests for print_accounts() at each verbosity level."""

    def test_summary(self, capsys):
        """Summary mode shows count only."""
        print_accounts(SAMPLE_ACCOUNTS, SUMMARY)
        out = capsys.readouterr().out
        assert "Accounts (2)" in out
        # No per-account lines
        assert "acct-001" not in out

    def test_verbose(self, capsys):
        """Verbose mode shows one-line-per-account."""
        print_accounts(SAMPLE_ACCOUNTS, VERBOSE)
        out = capsys.readouterr().out
        assert "Accounts (2)" in out
        assert "acct-001" in out
        assert "Brokerage Inc" in out
        assert "My 401k" in out
        assert "****1234" in out
        assert "acct-002" in out

    def test_debug(self, capsys):
        """Debug mode shows all fields."""
        print_accounts(SAMPLE_ACCOUNTS, DEBUG)
        out = capsys.readouterr().out
        assert "Account 1:" in out
        assert "id: acct-001" in out
        assert "name: My 401k" in out
        assert "institution: Brokerage Inc" in out
        assert "account_number: ****1234" in out
        assert "Account 2:" in out
        assert "account_number: None" in out


class TestPrintHoldings:
    """Tests for print_holdings() at each verbosity level."""

    def test_summary(self, capsys):
        """Summary mode shows count and total value."""
        print_holdings(SAMPLE_HOLDINGS, SUMMARY)
        out = capsys.readouterr().out
        assert "Holdings (3)" in out
        assert "$360,385.00" in out
        # No per-holding lines
        assert "AAPL" not in out

    def test_verbose(self, capsys):
        """Verbose mode shows per-holding lines grouped by account."""
        print_holdings(SAMPLE_HOLDINGS, VERBOSE)
        out = capsys.readouterr().out
        assert "Holdings (3)" in out
        assert "acct-001" in out
        assert "AAPL" in out
        assert "VTI" in out
        assert "acct-002" in out
        assert "BND" in out

    def test_verbose_shows_cost_basis(self, capsys):
        """Verbose mode shows cost basis when present."""
        holdings_with_cost = [
            ProviderHolding(
                account_id="acct-001",
                symbol="AAPL",
                quantity=Decimal("100"),
                price=Decimal("198.50"),
                market_value=Decimal("19850.00"),
                currency="USD",
                name="Apple Inc.",
                cost_basis=Decimal("145.00"),
            ),
        ]
        print_holdings(holdings_with_cost, VERBOSE)
        out = capsys.readouterr().out
        assert "cost: $145.00" in out

    def test_verbose_shows_cost_na(self, capsys):
        """Verbose mode shows N/A when cost basis is missing."""
        print_holdings(SAMPLE_HOLDINGS, VERBOSE)
        out = capsys.readouterr().out
        assert "cost: N/A" in out

    def test_debug(self, capsys):
        """Debug mode shows all fields per holding."""
        print_holdings(SAMPLE_HOLDINGS, DEBUG)
        out = capsys.readouterr().out
        assert "Holding 1:" in out
        assert "symbol: AAPL" in out
        assert "quantity: 150" in out
        assert "currency: USD" in out
        assert "name: Apple Inc." in out
        assert "cost_basis:" in out

    def test_debug_shows_cost_basis_and_raw_data(self, capsys):
        """Debug mode shows cost_basis and raw_data fields."""
        holdings_with_raw = [
            ProviderHolding(
                account_id="acct-001",
                symbol="AAPL",
                quantity=Decimal("100"),
                price=Decimal("198.50"),
                market_value=Decimal("19850.00"),
                currency="USD",
                name="Apple Inc.",
                cost_basis=Decimal("145.00"),
                raw_data={"symbol": "AAPL", "averagePrice": "145.00"},
            ),
        ]
        print_holdings(holdings_with_raw, DEBUG)
        out = capsys.readouterr().out
        assert "cost_basis: 145.00" in out
        assert "raw_data:" in out
        assert "averagePrice" in out

    def test_empty_holdings(self, capsys):
        """Empty holdings list should show zero count and $0."""
        print_holdings([], SUMMARY)
        out = capsys.readouterr().out
        assert "Holdings (0)" in out
        assert "$0.00" in out


class TestPrintActivities:
    """Tests for print_activities() at each verbosity level."""

    def test_summary(self, capsys):
        """Summary mode shows count and type breakdown."""
        print_activities(SAMPLE_ACTIVITIES, SUMMARY)
        out = capsys.readouterr().out
        assert "Activities (3)" in out
        assert "buy: 2" in out
        assert "dividend: 1" in out
        # No per-activity lines
        assert "txn-001" not in out

    def test_verbose(self, capsys):
        """Verbose mode shows one-line-per-activity."""
        print_activities(SAMPLE_ACTIVITIES, VERBOSE)
        out = capsys.readouterr().out
        assert "[1]" in out
        assert "2025-01-15" in out
        assert "buy" in out
        assert "AAPL" in out
        assert "$-5,000.00" in out
        assert "[2]" in out
        assert "dividend" in out

    def test_debug(self, capsys):
        """Debug mode shows all fields including raw_data."""
        print_activities(SAMPLE_ACTIVITIES, DEBUG)
        out = capsys.readouterr().out
        assert "Activity 1:" in out
        assert "external_id: txn-001" in out
        assert "type: buy" in out
        assert "ticker: AAPL" in out
        assert "units: 25" in out
        assert "raw_data:" in out
        assert "abc123" in out

    def test_empty_activities(self, capsys):
        """Empty activities list should show zero count."""
        print_activities([], SUMMARY)
        out = capsys.readouterr().out
        assert "Activities (0)" in out


class TestPrintBalanceDates:
    """Tests for print_balance_dates()."""

    def test_no_balance_dates(self, capsys):
        """Empty balance dates should produce no output."""
        print_balance_dates({}, SUMMARY)
        assert capsys.readouterr().out == ""

    def test_with_balance_dates(self, capsys):
        """Balance dates should be printed with account IDs."""
        print_balance_dates(SAMPLE_BALANCE_DATES, SUMMARY)
        out = capsys.readouterr().out
        assert "Balance Dates (2)" in out
        assert "acct-001" in out
        assert "2025-01-20" in out
        assert "acct-002: None" in out


class TestPrintSyncResult:
    """Tests for print_sync_result() dispatch."""

    def test_dispatches_all_sections(self, capsys):
        """Should print all sections."""
        result = _make_sync_result(
            accounts=SAMPLE_ACCOUNTS,
            holdings=SAMPLE_HOLDINGS,
            activities=SAMPLE_ACTIVITIES,
            errors=["Some error"],
            balance_dates=SAMPLE_BALANCE_DATES,
        )
        print_sync_result(result, SUMMARY)
        out = capsys.readouterr().out
        assert "Provider Errors" in out
        assert "Accounts" in out
        assert "Holdings" in out
        assert "Balance Dates" in out
        assert "Activities" in out


# --- DB write tests ---


class TestRunDbSync:
    """Tests for run_db_sync() — uses in-memory DB fixture."""

    def test_creates_sync_session_and_accounts(self, db):
        """DB sync should create sync session, accounts, holdings, and activities."""
        result = _make_sync_result(
            accounts=SAMPLE_ACCOUNTS,
            holdings=SAMPLE_HOLDINGS,
            activities=SAMPLE_ACTIVITIES,
        )

        with patch("database.get_session_local", return_value=lambda: db):
            run_db_sync("SnapTrade", result, SUMMARY)

        # Verify sync session
        sync_sessions = db.query(SyncSession).all()
        assert len(sync_sessions) == 1
        assert sync_sessions[0].is_complete is True

        # Verify accounts
        accounts = db.query(Account).all()
        assert len(accounts) == 2
        names = {a.name for a in accounts}
        assert "My 401k" in names
        assert "Roth IRA" in names

        # Verify holdings
        holdings = db.query(Holding).all()
        assert len(holdings) == 3

        # Verify activities
        activities = db.query(Activity).all()
        assert len(activities) == 3

        # Verify sync log
        log_entries = db.query(SyncLogEntry).all()
        assert len(log_entries) == 1
        assert log_entries[0].provider_name == "SnapTrade"
        assert log_entries[0].status == "success"
        assert log_entries[0].accounts_synced == 2

    def test_deduplicates_activities(self, db):
        """Running DB sync twice should not duplicate activities."""
        result = _make_sync_result(
            accounts=SAMPLE_ACCOUNTS,
            holdings=SAMPLE_HOLDINGS[:1],
            activities=SAMPLE_ACTIVITIES[:1],
        )

        with patch("database.get_session_local", return_value=lambda: db):
            run_db_sync("SnapTrade", result, SUMMARY)
            run_db_sync("SnapTrade", result, SUMMARY)

        activities = db.query(Activity).all()
        assert len(activities) == 1

    def test_updates_existing_accounts(self, db):
        """Running DB sync twice should update existing accounts."""
        result1 = _make_sync_result(
            accounts=[
                ProviderAccount(
                    id="acct-001", name="Old Name", institution="Old Bank"
                )
            ],
            holdings=[],
        )
        result2 = _make_sync_result(
            accounts=[
                ProviderAccount(
                    id="acct-001", name="New Name", institution="New Bank"
                )
            ],
            holdings=[],
        )

        with patch("database.get_session_local", return_value=lambda: db):
            run_db_sync("SnapTrade", result1, SUMMARY)
            run_db_sync("SnapTrade", result2, SUMMARY)

        accounts = db.query(Account).filter_by(external_id="acct-001").all()
        assert len(accounts) == 1
        assert accounts[0].name == "New Name"
        assert accounts[0].institution_name == "New Bank"

    def test_output_includes_status_annotations(self, db, capsys):
        """Output should include CREATED/UPDATED annotations."""
        result = _make_sync_result(
            accounts=SAMPLE_ACCOUNTS[:1],
            holdings=SAMPLE_HOLDINGS[:1],
        )

        with patch("database.get_session_local", return_value=lambda: db):
            run_db_sync("SnapTrade", result, SUMMARY)

        out = capsys.readouterr().out
        assert "CREATED" in out
        assert "Committed. Sync session ID:" in out

    def test_output_shows_updated_on_second_run(self, db, capsys):
        """Second run should show UPDATED for existing accounts."""
        result = _make_sync_result(
            accounts=SAMPLE_ACCOUNTS[:1],
            holdings=SAMPLE_HOLDINGS[:1],
        )

        with patch("database.get_session_local", return_value=lambda: db):
            run_db_sync("SnapTrade", result, SUMMARY)
            _ = capsys.readouterr()  # Discard first run output
            run_db_sync("SnapTrade", result, SUMMARY)

        out = capsys.readouterr().out
        assert "UPDATED" in out


# --- main() integration tests ---


class TestMain:
    """Tests for main() argument parsing and orchestration."""

    def test_dry_run_no_db_session(self, capsys):
        """Dry-run mode should not open a DB session."""
        mock_client = MagicMock()
        mock_client.is_configured.return_value = True
        mock_client.sync_all.return_value = _make_sync_result(
            accounts=SAMPLE_ACCOUNTS[:1],
            holdings=SAMPLE_HOLDINGS[:1],
        )

        with (
            patch(
                "scripts.debug_sync.get_provider_client",
                return_value=mock_client,
            ),
            patch("scripts.debug_sync.run_db_sync") as mock_db_sync,
        ):
            main(["--provider", "SnapTrade"])

        mock_db_sync.assert_not_called()
        out = capsys.readouterr().out
        assert "Dry-run" in out or "dry-run" in out

    def test_write_mode_calls_db_sync(self, capsys):
        """Write mode should call run_db_sync."""
        mock_client = MagicMock()
        mock_client.is_configured.return_value = True
        result = _make_sync_result(
            accounts=SAMPLE_ACCOUNTS[:1],
            holdings=SAMPLE_HOLDINGS[:1],
        )
        mock_client.sync_all.return_value = result

        with (
            patch(
                "scripts.debug_sync.get_provider_client",
                return_value=mock_client,
            ),
            patch("scripts.debug_sync.run_db_sync") as mock_db_sync,
        ):
            main(["--provider", "SnapTrade", "--write"])

        mock_db_sync.assert_called_once_with("SnapTrade", result, SUMMARY)

    def test_verbose_flag(self, capsys):
        """--verbose flag should produce verbose output."""
        mock_client = MagicMock()
        mock_client.is_configured.return_value = True
        mock_client.sync_all.return_value = _make_sync_result(
            accounts=SAMPLE_ACCOUNTS,
            holdings=SAMPLE_HOLDINGS,
        )

        with patch(
            "scripts.debug_sync.get_provider_client",
            return_value=mock_client,
        ):
            main(["--provider", "SnapTrade", "-v"])

        out = capsys.readouterr().out
        assert "verbose" in out
        # Verbose should show per-account details
        assert "acct-001" in out

    def test_debug_flag(self, capsys):
        """--debug flag should produce debug output."""
        mock_client = MagicMock()
        mock_client.is_configured.return_value = True
        mock_client.sync_all.return_value = _make_sync_result(
            accounts=SAMPLE_ACCOUNTS[:1],
            holdings=SAMPLE_HOLDINGS[:1],
            activities=SAMPLE_ACTIVITIES[:1],
        )

        with patch(
            "scripts.debug_sync.get_provider_client",
            return_value=mock_client,
        ):
            main(["--provider", "SnapTrade", "-d"])

        out = capsys.readouterr().out
        assert "debug" in out
        # Debug should show full field details
        assert "Account 1:" in out
        assert "Holding 1:" in out
        assert "Activity 1:" in out

    def test_invalid_provider_exits(self):
        """Invalid provider should cause exit."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--provider", "BadProvider"])
        assert exc_info.value.code == 1

    def test_provider_api_error(self, capsys):
        """Provider API error should exit cleanly."""
        mock_client = MagicMock()
        mock_client.is_configured.return_value = True
        mock_client.sync_all.side_effect = Exception("API timeout")

        with patch(
            "scripts.debug_sync.get_provider_client",
            return_value=mock_client,
        ):
            with pytest.raises(SystemExit) as exc_info:
                main(["--provider", "SnapTrade"])

        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert "API timeout" in out

    def test_debug_overrides_verbose(self, capsys):
        """--debug should take precedence over --verbose."""
        mock_client = MagicMock()
        mock_client.is_configured.return_value = True
        mock_client.sync_all.return_value = _make_sync_result(
            accounts=SAMPLE_ACCOUNTS[:1],
            holdings=SAMPLE_HOLDINGS[:1],
        )

        with (
            patch(
                "scripts.debug_sync.get_provider_client",
                return_value=mock_client,
            ),
            patch("scripts.debug_sync.run_db_sync") as mock_db_sync,
        ):
            main(["--provider", "SnapTrade", "-v", "-d", "--write"])

        # run_db_sync should get DEBUG verbosity, not VERBOSE
        mock_db_sync.assert_called_once()
        assert mock_db_sync.call_args[0][2] == DEBUG
