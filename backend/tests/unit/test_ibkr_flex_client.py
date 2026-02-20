"""Unit tests for IBKRFlexClient provider protocol implementation."""

import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from ibflex import enums
from ibflex.Types import (
    AccountInformation,
    CashReportCurrency,
    CashTransaction,
    FlexQueryResponse,
    FlexStatement,
    OpenPosition,
    Trade,
)

from integrations.ibkr_flex_client import IBKRFlexClient
from integrations.provider_protocol import (
    ProviderAccount,
    ProviderHolding,
    ProviderSyncResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_empty_settings():
    """Fixture that mocks settings with empty IBKR credentials."""
    with patch("integrations.ibkr_flex_client.settings") as mock_settings:
        mock_settings.IBKR_FLEX_TOKEN = ""
        mock_settings.IBKR_FLEX_QUERY_ID = ""
        yield mock_settings


@pytest.fixture
def mock_configured_settings():
    """Fixture that mocks settings with configured IBKR credentials."""
    with patch("integrations.ibkr_flex_client.settings") as mock_settings:
        mock_settings.IBKR_FLEX_TOKEN = "test_token_123"
        mock_settings.IBKR_FLEX_QUERY_ID = "456789"
        yield mock_settings


@pytest.fixture
def sample_flex_response():
    """Build a realistic FlexQueryResponse using typed ibflex dataclasses."""
    acct_info = AccountInformation(
        accountId="U1234567",
        acctAlias="My Trading Account",
        name="John Doe",
    )

    positions = (
        OpenPosition(
            accountId="U1234567",
            symbol="AAPL",
            description="APPLE INC",
            position=Decimal("100"),
            markPrice=Decimal("175.50"),
            positionValue=Decimal("17550.00"),
            currency="USD",
            costBasisPrice=Decimal("145.00"),
        ),
        OpenPosition(
            accountId="U1234567",
            symbol="MSFT",
            description="MICROSOFT CORP",
            position=Decimal("50"),
            markPrice=Decimal("380.00"),
            positionValue=None,  # Test fallback calculation
            currency="USD",
        ),
    )

    cash_report = (
        CashReportCurrency(
            accountId="U1234567",
            currency="USD",
            endingCash=Decimal("5432.10"),
        ),
        CashReportCurrency(
            accountId="U1234567",
            currency="BASE_SUMMARY",
            endingCash=Decimal("5432.10"),
        ),
        CashReportCurrency(
            accountId="U1234567",
            currency="EUR",
            endingCash=Decimal("0"),
        ),
    )

    trades = (
        Trade(
            accountId="U1234567",
            tradeID="123456789",
            transactionID="T999",
            symbol="AAPL",
            description="APPLE INC",
            buySell=enums.BuySell.BUY,
            quantity=Decimal("100"),
            tradePrice=Decimal("170.00"),
            netCash=Decimal("-17000.00"),
            proceeds=Decimal("-17000.00"),
            ibCommission=Decimal("-1.00"),
            currency="USD",
            tradeDate=datetime.date(2024, 1, 15),
            tradeTime=datetime.time(10, 30, 0),
            dateTime=None,
            settleDateTarget=datetime.date(2024, 1, 17),
        ),
        Trade(
            accountId="U1234567",
            tradeID="123456790",
            transactionID="T1000",
            symbol="GOOGL",
            description="ALPHABET INC",
            buySell=enums.BuySell.SELL,
            quantity=Decimal("-25"),
            tradePrice=Decimal("140.00"),
            netCash=Decimal("3499.00"),
            proceeds=Decimal("3500.00"),
            ibCommission=Decimal("-1.00"),
            currency="USD",
            tradeDate=None,
            tradeTime=None,
            dateTime=datetime.datetime(2024, 2, 20, 14, 0, 0),
            settleDateTarget=datetime.date(2024, 2, 22),
        ),
    )

    stmt = FlexStatement(
        accountId="U1234567",
        fromDate=datetime.date(2024, 1, 1),
        toDate=datetime.date(2024, 12, 31),
        period="Last365CalendarDays",
        whenGenerated=datetime.datetime(2024, 6, 15, 12, 0, 0),
        AccountInformation=acct_info,
        OpenPositions=positions,
        CashReport=cash_report,
        Trades=trades,
    )

    return FlexQueryResponse(
        queryName="TestQuery",
        type="AF",
        FlexStatements=(stmt,),
    )


@pytest.fixture
def multi_account_response():
    """FlexQueryResponse with multiple accounts."""
    stmt1 = FlexStatement(
        accountId="U1234567",
        fromDate=datetime.date(2024, 1, 1),
        toDate=datetime.date(2024, 12, 31),
        period="Last365CalendarDays",
        whenGenerated=datetime.datetime(2024, 6, 15, 12, 0, 0),
        AccountInformation=AccountInformation(
            accountId="U1234567",
            acctAlias="Individual Account",
        ),
        OpenPositions=(
            OpenPosition(
                accountId="U1234567",
                symbol="AAPL",
                position=Decimal("100"),
                markPrice=Decimal("175.00"),
                positionValue=Decimal("17500.00"),
                currency="USD",
            ),
        ),
    )

    stmt2 = FlexStatement(
        accountId="U7654321",
        fromDate=datetime.date(2024, 1, 1),
        toDate=datetime.date(2024, 12, 31),
        period="Last365CalendarDays",
        whenGenerated=datetime.datetime(2024, 6, 15, 12, 0, 0),
        AccountInformation=AccountInformation(
            accountId="U7654321",
            acctAlias="IRA Account",
        ),
        OpenPositions=(
            OpenPosition(
                accountId="U7654321",
                symbol="VTI",
                position=Decimal("200"),
                markPrice=Decimal("220.00"),
                positionValue=Decimal("44000.00"),
                currency="USD",
            ),
        ),
    )

    return FlexQueryResponse(
        queryName="MultiAcct",
        type="AF",
        FlexStatements=(stmt1, stmt2),
    )


# ---------------------------------------------------------------------------
# TestIBKRFlexClientProtocol
# ---------------------------------------------------------------------------


class TestIBKRFlexClientProtocol:
    """Tests for IBKRFlexClient's ProviderClient protocol implementation."""

    def test_provider_name(self, mock_configured_settings):
        """IBKRFlexClient returns correct provider name."""
        ibkr = IBKRFlexClient()
        assert ibkr.provider_name == "IBKR"

    def test_is_configured_true(self, mock_configured_settings):
        """is_configured returns True when both token and query_id are present."""
        ibkr = IBKRFlexClient()
        assert ibkr.is_configured() is True

    def test_is_configured_false_no_token(self, mock_empty_settings):
        """is_configured returns False when token is missing."""
        ibkr = IBKRFlexClient(query_id="123456")
        assert ibkr.is_configured() is False

    def test_is_configured_false_no_query_id(self, mock_empty_settings):
        """is_configured returns False when query_id is missing."""
        ibkr = IBKRFlexClient(token="tok123")
        assert ibkr.is_configured() is False

    def test_is_configured_with_explicit_credentials(self, mock_empty_settings):
        """is_configured returns True when credentials passed to constructor."""
        ibkr = IBKRFlexClient(token="tok", query_id="qid")
        assert ibkr.is_configured() is True


# ---------------------------------------------------------------------------
# TestIBKRGetAccounts
# ---------------------------------------------------------------------------


class TestIBKRGetAccounts:
    """Tests for account extraction from Flex reports."""

    def test_get_accounts_maps_correctly(
        self, mock_configured_settings, sample_flex_response
    ):
        """get_accounts maps FlexStatements to ProviderAccount."""
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=sample_flex_response):
            accounts = ibkr.get_accounts()

        assert len(accounts) == 1
        assert isinstance(accounts[0], ProviderAccount)
        assert accounts[0].id == "U1234567"
        assert accounts[0].institution == "Interactive Brokers"
        assert accounts[0].account_number is None

    def test_get_accounts_uses_alias(
        self, mock_configured_settings, sample_flex_response
    ):
        """Account name prefers acctAlias from AccountInformation."""
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=sample_flex_response):
            accounts = ibkr.get_accounts()

        assert accounts[0].name == "My Trading Account"

    def test_get_accounts_uses_account_type_fallback(self, mock_configured_settings):
        """Account name uses accountType when alias is not set."""
        stmt = FlexStatement(
            accountId="U1111111",
            fromDate=datetime.date(2024, 1, 1),
            toDate=datetime.date(2024, 12, 31),
            period="Last365CalendarDays",
            whenGenerated=datetime.datetime(2024, 6, 15, 12, 0, 0),
            AccountInformation=AccountInformation(
                accountId="U1111111",
                acctAlias=None,
                accountType="Individual",
            ),
        )
        response = FlexQueryResponse(
            queryName="Test", type="AF", FlexStatements=(stmt,)
        )
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            accounts = ibkr.get_accounts()

        assert accounts[0].name == "Interactive Brokers Individual Account"

    def test_get_accounts_generic_fallback(self, mock_configured_settings):
        """Account name is generic when no AccountInformation at all."""
        stmt = FlexStatement(
            accountId="U9999999",
            fromDate=datetime.date(2024, 1, 1),
            toDate=datetime.date(2024, 12, 31),
            period="Last365CalendarDays",
            whenGenerated=datetime.datetime(2024, 6, 15, 12, 0, 0),
            AccountInformation=None,
        )
        response = FlexQueryResponse(
            queryName="Test", type="AF", FlexStatements=(stmt,)
        )
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            accounts = ibkr.get_accounts()

        assert accounts[0].name == "Interactive Brokers Account"

    def test_get_accounts_multi_statement(
        self, mock_configured_settings, multi_account_response
    ):
        """Multiple FlexStatements produce multiple accounts."""
        ibkr = IBKRFlexClient()

        with patch.object(
            ibkr, "_fetch_statement", return_value=multi_account_response
        ):
            accounts = ibkr.get_accounts()

        assert len(accounts) == 2
        ids = {a.id for a in accounts}
        assert ids == {"U1234567", "U7654321"}
        names = {a.name for a in accounts}
        assert "Individual Account" in names
        assert "IRA Account" in names


# ---------------------------------------------------------------------------
# TestIBKRGetHoldings
# ---------------------------------------------------------------------------


class TestIBKRGetHoldings:
    """Tests for holdings extraction from Flex reports."""

    def test_get_holdings_maps_correctly(
        self, mock_configured_settings, sample_flex_response
    ):
        """Holdings are correctly mapped from OpenPositions."""
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=sample_flex_response):
            holdings = ibkr.get_holdings()

        # Find AAPL holding (positions + cash, minus filtered ones)
        aapl = next(h for h in holdings if h.symbol == "AAPL")
        assert isinstance(aapl, ProviderHolding)
        assert aapl.account_id == "U1234567"
        assert aapl.quantity == Decimal("100")
        assert aapl.price == Decimal("175.50")
        assert aapl.market_value == Decimal("17550.00")
        assert aapl.currency == "USD"
        assert aapl.name == "APPLE INC"
        assert aapl.cost_basis == Decimal("145.00")
        assert aapl.raw_data is not None
        assert aapl.raw_data["symbol"] == "AAPL"

        # MSFT has no costBasisPrice set
        msft = next(h for h in holdings if h.symbol == "MSFT")
        assert msft.cost_basis is None

    def test_get_holdings_zero_cost_basis_treated_as_none(
        self, mock_configured_settings
    ):
        """Zero costBasisPrice is treated as None."""
        stmt = FlexStatement(
            accountId="U1234567",
            fromDate=datetime.date(2024, 1, 1),
            toDate=datetime.date(2024, 12, 31),
            period="Last365CalendarDays",
            whenGenerated=datetime.datetime(2024, 6, 15, 12, 0, 0),
            OpenPositions=(
                OpenPosition(
                    accountId="U1234567",
                    symbol="AAPL",
                    position=Decimal("10"),
                    markPrice=Decimal("175.00"),
                    positionValue=Decimal("1750.00"),
                    currency="USD",
                    costBasisPrice=Decimal("0"),
                ),
            ),
        )
        response = FlexQueryResponse(
            queryName="Test", type="AF", FlexStatements=(stmt,)
        )
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            holdings = ibkr.get_holdings()

        assert len(holdings) == 1
        assert holdings[0].cost_basis is None

    def test_get_holdings_filtered_by_account(
        self, mock_configured_settings, multi_account_response
    ):
        """Holdings are filtered by account_id when specified."""
        ibkr = IBKRFlexClient()

        with patch.object(
            ibkr, "_fetch_statement", return_value=multi_account_response
        ):
            holdings = ibkr.get_holdings(account_id="U7654321")

        assert len(holdings) == 1
        assert holdings[0].symbol == "VTI"
        assert holdings[0].account_id == "U7654321"

    def test_get_holdings_skips_none_symbol(self, mock_configured_settings):
        """Positions with None symbol are skipped."""
        stmt = FlexStatement(
            accountId="U1234567",
            fromDate=datetime.date(2024, 1, 1),
            toDate=datetime.date(2024, 12, 31),
            period="Last365CalendarDays",
            whenGenerated=datetime.datetime(2024, 6, 15, 12, 0, 0),
            OpenPositions=(
                OpenPosition(
                    accountId="U1234567",
                    symbol=None,
                    position=Decimal("100"),
                    markPrice=Decimal("50.00"),
                    positionValue=Decimal("5000.00"),
                    currency="USD",
                ),
                OpenPosition(
                    accountId="U1234567",
                    symbol="AAPL",
                    position=Decimal("10"),
                    markPrice=Decimal("175.00"),
                    positionValue=Decimal("1750.00"),
                    currency="USD",
                ),
            ),
        )
        response = FlexQueryResponse(
            queryName="Test", type="AF", FlexStatements=(stmt,)
        )
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            holdings = ibkr.get_holdings()

        assert len(holdings) == 1
        assert holdings[0].symbol == "AAPL"

    def test_get_holdings_position_value_fallback(self, mock_configured_settings):
        """When positionValue is None, market_value = position * markPrice."""
        stmt = FlexStatement(
            accountId="U1234567",
            fromDate=datetime.date(2024, 1, 1),
            toDate=datetime.date(2024, 12, 31),
            period="Last365CalendarDays",
            whenGenerated=datetime.datetime(2024, 6, 15, 12, 0, 0),
            OpenPositions=(
                OpenPosition(
                    accountId="U1234567",
                    symbol="TSLA",
                    position=Decimal("20"),
                    markPrice=Decimal("250.00"),
                    positionValue=None,
                    currency="USD",
                ),
            ),
        )
        response = FlexQueryResponse(
            queryName="Test", type="AF", FlexStatements=(stmt,)
        )
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            holdings = ibkr.get_holdings()

        assert len(holdings) == 1
        assert holdings[0].market_value == Decimal("5000.00")

    def test_get_holdings_includes_cash(
        self, mock_configured_settings, sample_flex_response
    ):
        """CashReportCurrency entries are mapped to _CASH:{currency} holdings."""
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=sample_flex_response):
            holdings = ibkr.get_holdings()

        cash_holdings = [h for h in holdings if h.symbol.startswith("_CASH:")]
        assert len(cash_holdings) == 1
        usd_cash = cash_holdings[0]
        assert usd_cash.symbol == "_CASH:USD"
        assert usd_cash.quantity == Decimal("5432.10")
        assert usd_cash.price == Decimal("1")
        assert usd_cash.market_value == Decimal("5432.10")
        assert usd_cash.currency == "USD"
        assert usd_cash.name == "USD Cash"

    def test_get_holdings_skips_zero_cash(self, mock_configured_settings):
        """Cash entries with zero endingCash are not included."""
        stmt = FlexStatement(
            accountId="U1234567",
            fromDate=datetime.date(2024, 1, 1),
            toDate=datetime.date(2024, 12, 31),
            period="Last365CalendarDays",
            whenGenerated=datetime.datetime(2024, 6, 15, 12, 0, 0),
            CashReport=(
                CashReportCurrency(
                    accountId="U1234567",
                    currency="USD",
                    endingCash=Decimal("0"),
                ),
                CashReportCurrency(
                    accountId="U1234567",
                    currency="EUR",
                    endingCash=None,
                ),
            ),
        )
        response = FlexQueryResponse(
            queryName="Test", type="AF", FlexStatements=(stmt,)
        )
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            holdings = ibkr.get_holdings()

        cash_holdings = [h for h in holdings if h.symbol.startswith("_CASH:")]
        assert len(cash_holdings) == 0

    def test_get_holdings_skips_base_summary_cash(
        self, mock_configured_settings, sample_flex_response
    ):
        """BASE_SUMMARY currency rows from CashReport are filtered out."""
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=sample_flex_response):
            holdings = ibkr.get_holdings()

        # Should not have a _CASH:BASE_SUMMARY holding
        symbols = {h.symbol for h in holdings}
        assert "_CASH:BASE_SUMMARY" not in symbols


# ---------------------------------------------------------------------------
# TestIBKRGetActivities
# ---------------------------------------------------------------------------


class TestIBKRGetActivities:
    """Tests for activity/trade extraction from Flex reports."""

    def test_get_activities_maps_buy(
        self, mock_configured_settings, sample_flex_response
    ):
        """BuySell.BUY is mapped to 'buy' activity type."""
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=sample_flex_response):
            activities = ibkr.get_activities()

        buy = next(a for a in activities if a.ticker == "AAPL")
        assert buy.type == "buy"
        assert buy.units == Decimal("100")
        assert buy.price == Decimal("170.00")
        assert buy.fee == Decimal("-1.00")
        assert buy.currency == "USD"

    def test_get_activities_maps_sell(
        self, mock_configured_settings, sample_flex_response
    ):
        """BuySell.SELL is mapped to 'sell' activity type."""
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=sample_flex_response):
            activities = ibkr.get_activities()

        sell = next(a for a in activities if a.ticker == "GOOGL")
        assert sell.type == "sell"
        assert sell.amount == Decimal("3499.00")

    def test_get_activities_uses_trade_id(
        self, mock_configured_settings, sample_flex_response
    ):
        """tradeID is used as external_id."""
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=sample_flex_response):
            activities = ibkr.get_activities()

        aapl_trade = next(a for a in activities if a.ticker == "AAPL")
        assert aapl_trade.external_id == "123456789"

    def test_get_activities_falls_back_to_transaction_id(
        self, mock_configured_settings
    ):
        """transactionID is used as external_id when tradeID is None."""
        stmt = FlexStatement(
            accountId="U1234567",
            fromDate=datetime.date(2024, 1, 1),
            toDate=datetime.date(2024, 12, 31),
            period="Last365CalendarDays",
            whenGenerated=datetime.datetime(2024, 6, 15, 12, 0, 0),
            Trades=(
                Trade(
                    accountId="U1234567",
                    tradeID=None,
                    transactionID="TXN_FALLBACK",
                    symbol="VTI",
                    buySell=enums.BuySell.BUY,
                    quantity=Decimal("10"),
                    tradePrice=Decimal("220.00"),
                    netCash=Decimal("-2200.00"),
                    currency="USD",
                    tradeDate=datetime.date(2024, 3, 1),
                    tradeTime=datetime.time(9, 30, 0),
                ),
            ),
        )
        response = FlexQueryResponse(
            queryName="Test", type="AF", FlexStatements=(stmt,)
        )
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert len(activities) == 1
        assert activities[0].external_id == "TXN_FALLBACK"

    def test_get_activities_date_from_trade_date_and_time(
        self, mock_configured_settings, sample_flex_response
    ):
        """Activity date combines tradeDate + tradeTime when dateTime is None."""
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=sample_flex_response):
            activities = ibkr.get_activities()

        aapl_trade = next(a for a in activities if a.ticker == "AAPL")
        assert aapl_trade.activity_date == datetime.datetime(
            2024, 1, 15, 10, 30, 0, tzinfo=datetime.timezone.utc
        )

    def test_get_activities_date_from_datetime(
        self, mock_configured_settings, sample_flex_response
    ):
        """Activity date uses trade.dateTime when available."""
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=sample_flex_response):
            activities = ibkr.get_activities()

        googl_trade = next(a for a in activities if a.ticker == "GOOGL")
        assert googl_trade.activity_date == datetime.datetime(
            2024, 2, 20, 14, 0, 0, tzinfo=datetime.timezone.utc
        )

    def test_get_activities_settlement_date(
        self, mock_configured_settings, sample_flex_response
    ):
        """Settlement date is converted from date to datetime."""
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=sample_flex_response):
            activities = ibkr.get_activities()

        aapl_trade = next(a for a in activities if a.ticker == "AAPL")
        assert aapl_trade.settlement_date == datetime.datetime(
            2024, 1, 17, 0, 0, 0, tzinfo=datetime.timezone.utc
        )

    def test_get_activities_raw_data(
        self, mock_configured_settings, sample_flex_response
    ):
        """raw_data contains stringified trade fields."""
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=sample_flex_response):
            activities = ibkr.get_activities()

        aapl_trade = next(a for a in activities if a.ticker == "AAPL")
        assert aapl_trade.raw_data is not None
        assert "tradeID" in aapl_trade.raw_data
        assert aapl_trade.raw_data["tradeID"] == "123456789"

    def test_get_activities_skips_no_id(self, mock_configured_settings):
        """Trades without tradeID or transactionID are skipped."""
        stmt = FlexStatement(
            accountId="U1234567",
            fromDate=datetime.date(2024, 1, 1),
            toDate=datetime.date(2024, 12, 31),
            period="Last365CalendarDays",
            whenGenerated=datetime.datetime(2024, 6, 15, 12, 0, 0),
            Trades=(
                Trade(
                    accountId="U1234567",
                    tradeID=None,
                    transactionID=None,
                    symbol="XYZ",
                    buySell=enums.BuySell.BUY,
                    tradeDate=datetime.date(2024, 1, 1),
                ),
            ),
        )
        response = FlexQueryResponse(
            queryName="Test", type="AF", FlexStatements=(stmt,)
        )
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert len(activities) == 0

    def test_get_activities_maps_cancel_buy(self, mock_configured_settings):
        """BuySell.CANCELBUY is mapped to 'buy' activity type."""
        stmt = FlexStatement(
            accountId="U1234567",
            fromDate=datetime.date(2024, 1, 1),
            toDate=datetime.date(2024, 12, 31),
            period="Last365CalendarDays",
            whenGenerated=datetime.datetime(2024, 6, 15, 12, 0, 0),
            Trades=(
                Trade(
                    accountId="U1234567",
                    tradeID="CB001",
                    symbol="TEST",
                    buySell=enums.BuySell.CANCELBUY,
                    tradeDate=datetime.date(2024, 1, 1),
                ),
            ),
        )
        response = FlexQueryResponse(
            queryName="Test", type="AF", FlexStatements=(stmt,)
        )
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert activities[0].type == "buy"

    def test_get_activities_maps_cancel_sell(self, mock_configured_settings):
        """BuySell.CANCELSELL is mapped to 'sell' activity type."""
        stmt = FlexStatement(
            accountId="U1234567",
            fromDate=datetime.date(2024, 1, 1),
            toDate=datetime.date(2024, 12, 31),
            period="Last365CalendarDays",
            whenGenerated=datetime.datetime(2024, 6, 15, 12, 0, 0),
            Trades=(
                Trade(
                    accountId="U1234567",
                    tradeID="CS001",
                    symbol="TEST",
                    buySell=enums.BuySell.CANCELSELL,
                    tradeDate=datetime.date(2024, 1, 1),
                ),
            ),
        )
        response = FlexQueryResponse(
            queryName="Test", type="AF", FlexStatements=(stmt,)
        )
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert activities[0].type == "sell"


# ---------------------------------------------------------------------------
# TestIBKRCashTransactions
# ---------------------------------------------------------------------------


class TestIBKRCashTransactions:
    """Tests for CashTransaction extraction from Flex reports."""

    def _make_response(self, cash_transactions, account_id="U1234567"):
        """Helper to build a FlexQueryResponse with CashTransactions."""
        stmt = FlexStatement(
            accountId=account_id,
            fromDate=datetime.date(2024, 1, 1),
            toDate=datetime.date(2024, 12, 31),
            period="Last365CalendarDays",
            whenGenerated=datetime.datetime(2024, 6, 15, 12, 0, 0),
            CashTransactions=tuple(cash_transactions),
        )
        return FlexQueryResponse(
            queryName="Test", type="AF", FlexStatements=(stmt,)
        )

    def test_cash_transaction_dividend(self, mock_configured_settings):
        """CashAction.DIVIDEND maps to 'dividend' activity type."""
        response = self._make_response([
            CashTransaction(
                accountId="U1234567",
                transactionID="CT001",
                type=enums.CashAction.DIVIDEND,
                amount=Decimal("25.50"),
                symbol="AAPL",
                currency="USD",
                description="AAPL(US0378331005) CASH DIVIDEND",
                dateTime=datetime.datetime(2024, 3, 15, 10, 0, 0),
            ),
        ])
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert len(activities) == 1
        assert activities[0].type == "dividend"
        assert activities[0].ticker == "AAPL"
        assert activities[0].amount == Decimal("25.50")

    def test_cash_transaction_deposit(self, mock_configured_settings):
        """CashAction.DEPOSITWITHDRAW with positive amount maps to 'deposit'."""
        response = self._make_response([
            CashTransaction(
                accountId="U1234567",
                transactionID="CT002",
                type=enums.CashAction.DEPOSITWITHDRAW,
                amount=Decimal("10000.00"),
                currency="USD",
                description="ELECTRONIC FUND TRANSFER",
                dateTime=datetime.datetime(2024, 4, 1, 9, 0, 0),
            ),
        ])
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert len(activities) == 1
        assert activities[0].type == "deposit"
        assert activities[0].amount == Decimal("10000.00")
        assert activities[0].ticker is None

    def test_cash_transaction_withdrawal(self, mock_configured_settings):
        """CashAction.DEPOSITWITHDRAW with negative amount maps to 'withdrawal'."""
        response = self._make_response([
            CashTransaction(
                accountId="U1234567",
                transactionID="CT003",
                type=enums.CashAction.DEPOSITWITHDRAW,
                amount=Decimal("-5000.00"),
                currency="USD",
                description="WIRE WITHDRAWAL",
                dateTime=datetime.datetime(2024, 5, 10, 14, 0, 0),
            ),
        ])
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert len(activities) == 1
        assert activities[0].type == "withdrawal"
        assert activities[0].amount == Decimal("-5000.00")

    def test_cash_transaction_interest(self, mock_configured_settings):
        """CashAction.BROKERINTRCVD maps to 'interest' activity type."""
        response = self._make_response([
            CashTransaction(
                accountId="U1234567",
                transactionID="CT004",
                type=enums.CashAction.BROKERINTRCVD,
                amount=Decimal("12.34"),
                currency="USD",
                description="USD CREDIT INT FOR FEB-2024",
                dateTime=datetime.datetime(2024, 3, 1, 0, 0, 0),
            ),
        ])
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert len(activities) == 1
        assert activities[0].type == "interest"
        assert activities[0].amount == Decimal("12.34")

    def test_cash_transaction_withholding_tax(self, mock_configured_settings):
        """CashAction.WHTAX maps to 'tax' activity type."""
        response = self._make_response([
            CashTransaction(
                accountId="U1234567",
                transactionID="CT005",
                type=enums.CashAction.WHTAX,
                amount=Decimal("-3.83"),
                symbol="AAPL",
                currency="USD",
                description="AAPL(US0378331005) CASH DIVIDEND - US TAX",
                dateTime=datetime.datetime(2024, 3, 15, 10, 0, 0),
            ),
        ])
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert len(activities) == 1
        assert activities[0].type == "tax"
        assert activities[0].amount == Decimal("-3.83")
        assert activities[0].ticker == "AAPL"

    def test_cash_transaction_fee(self, mock_configured_settings):
        """CashAction.FEES maps to 'fee' activity type."""
        response = self._make_response([
            CashTransaction(
                accountId="U1234567",
                transactionID="CT006",
                type=enums.CashAction.FEES,
                amount=Decimal("-10.00"),
                currency="USD",
                description="SNAPSHOT MARKET DATA FEE",
                dateTime=datetime.datetime(2024, 2, 1, 0, 0, 0),
            ),
        ])
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert len(activities) == 1
        assert activities[0].type == "fee"

    def test_cash_transaction_payment_in_lieu(self, mock_configured_settings):
        """CashAction.PAYMENTINLIEU maps to 'dividend' activity type."""
        response = self._make_response([
            CashTransaction(
                accountId="U1234567",
                transactionID="CT007",
                type=enums.CashAction.PAYMENTINLIEU,
                amount=Decimal("15.00"),
                symbol="MSFT",
                currency="USD",
                description="MSFT PAYMENT IN LIEU OF DIVIDEND",
                dateTime=datetime.datetime(2024, 6, 1, 10, 0, 0),
            ),
        ])
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert len(activities) == 1
        assert activities[0].type == "dividend"

    def test_cash_transaction_external_id_prefix(self, mock_configured_settings):
        """External ID is prefixed with 'CT:' to avoid collision with trades."""
        response = self._make_response([
            CashTransaction(
                accountId="U1234567",
                transactionID="999888777",
                type=enums.CashAction.DIVIDEND,
                amount=Decimal("10.00"),
                symbol="VTI",
                currency="USD",
                dateTime=datetime.datetime(2024, 7, 1, 10, 0, 0),
            ),
        ])
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert activities[0].external_id == "CT:999888777"

    def test_cash_transaction_skips_no_transaction_id(self, mock_configured_settings):
        """CashTransactions without transactionID are skipped."""
        response = self._make_response([
            CashTransaction(
                accountId="U1234567",
                transactionID=None,
                type=enums.CashAction.DIVIDEND,
                amount=Decimal("10.00"),
                symbol="VTI",
                currency="USD",
                dateTime=datetime.datetime(2024, 7, 1, 10, 0, 0),
            ),
        ])
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert len(activities) == 0

    def test_cash_transaction_skips_no_date(self, mock_configured_settings):
        """CashTransactions without dateTime and reportDate are skipped."""
        response = self._make_response([
            CashTransaction(
                accountId="U1234567",
                transactionID="CT_NODATE",
                type=enums.CashAction.DIVIDEND,
                amount=Decimal("10.00"),
                symbol="VTI",
                currency="USD",
                dateTime=None,
                reportDate=None,
            ),
        ])
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert len(activities) == 0

    def test_cash_transaction_skips_no_account_id(self, mock_configured_settings):
        """CashTransactions without accountId are skipped (IBKR emits duplicates)."""
        response = self._make_response(
            [
                CashTransaction(
                    accountId=None,
                    transactionID="CT_NOACCT",
                    type=enums.CashAction.FEES,
                    amount=Decimal("-5.00"),
                    currency="USD",
                    dateTime=datetime.datetime(2024, 8, 1, 0, 0, 0),
                ),
            ],
            account_id="U9999999",
        )
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert len(activities) == 0

    def test_cash_transaction_settlement_date(self, mock_configured_settings):
        """settleDate is converted to datetime."""
        response = self._make_response([
            CashTransaction(
                accountId="U1234567",
                transactionID="CT_SETTLE",
                type=enums.CashAction.DIVIDEND,
                amount=Decimal("20.00"),
                symbol="AAPL",
                currency="USD",
                dateTime=datetime.datetime(2024, 3, 15, 10, 0, 0),
                settleDate=datetime.date(2024, 3, 18),
            ),
        ])
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert activities[0].settlement_date == datetime.datetime(
            2024, 3, 18, 0, 0, 0, tzinfo=datetime.timezone.utc
        )

    def test_cash_transaction_date_fallback_to_report_date(self, mock_configured_settings):
        """reportDate is used when dateTime is None."""
        response = self._make_response([
            CashTransaction(
                accountId="U1234567",
                transactionID="CT_RPT",
                type=enums.CashAction.BROKERINTPAID,
                amount=Decimal("-2.00"),
                currency="USD",
                dateTime=None,
                reportDate=datetime.date(2024, 4, 1),
            ),
        ])
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert len(activities) == 1
        assert activities[0].activity_date == datetime.datetime(
            2024, 4, 1, 0, 0, 0, tzinfo=datetime.timezone.utc
        )
        assert activities[0].type == "interest"

    def test_cash_transaction_units_and_price_are_none(self, mock_configured_settings):
        """Cash transactions have units=None and price=None."""
        response = self._make_response([
            CashTransaction(
                accountId="U1234567",
                transactionID="CT_NOUNIT",
                type=enums.CashAction.DIVIDEND,
                amount=Decimal("50.00"),
                symbol="AAPL",
                currency="USD",
                dateTime=datetime.datetime(2024, 3, 15, 10, 0, 0),
            ),
        ])
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert activities[0].units is None
        assert activities[0].price is None
        assert activities[0].fee is None

    def test_cash_transaction_combined_with_trades(self, mock_configured_settings):
        """Both trades and cash transactions appear in get_activities()."""
        stmt = FlexStatement(
            accountId="U1234567",
            fromDate=datetime.date(2024, 1, 1),
            toDate=datetime.date(2024, 12, 31),
            period="Last365CalendarDays",
            whenGenerated=datetime.datetime(2024, 6, 15, 12, 0, 0),
            Trades=(
                Trade(
                    accountId="U1234567",
                    tradeID="T100",
                    symbol="AAPL",
                    buySell=enums.BuySell.BUY,
                    quantity=Decimal("10"),
                    tradePrice=Decimal("175.00"),
                    netCash=Decimal("-1750.00"),
                    currency="USD",
                    tradeDate=datetime.date(2024, 1, 15),
                ),
            ),
            CashTransactions=(
                CashTransaction(
                    accountId="U1234567",
                    transactionID="CT100",
                    type=enums.CashAction.DIVIDEND,
                    amount=Decimal("5.00"),
                    symbol="AAPL",
                    currency="USD",
                    dateTime=datetime.datetime(2024, 3, 15, 10, 0, 0),
                ),
                CashTransaction(
                    accountId="U1234567",
                    transactionID="CT101",
                    type=enums.CashAction.DEPOSITWITHDRAW,
                    amount=Decimal("10000.00"),
                    currency="USD",
                    dateTime=datetime.datetime(2024, 2, 1, 9, 0, 0),
                ),
            ),
        )
        response = FlexQueryResponse(
            queryName="Test", type="AF", FlexStatements=(stmt,)
        )
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert len(activities) == 3
        types = {a.type for a in activities}
        assert types == {"buy", "dividend", "deposit"}
        # Verify external_id prefixes
        ext_ids = {a.external_id for a in activities}
        assert "T100" in ext_ids
        assert "CT:CT100" in ext_ids
        assert "CT:CT101" in ext_ids

    def test_cash_transaction_unknown_type(self, mock_configured_settings):
        """Unknown/None CashAction maps to 'other'."""
        response = self._make_response([
            CashTransaction(
                accountId="U1234567",
                transactionID="CT_UNK",
                type=None,
                amount=Decimal("1.00"),
                currency="USD",
                dateTime=datetime.datetime(2024, 1, 1, 0, 0, 0),
            ),
        ])
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert len(activities) == 1
        assert activities[0].type == "other"

    def test_cash_transaction_commadj_maps_to_fee(self, mock_configured_settings):
        """CashAction.COMMADJ maps to 'fee' activity type."""
        response = self._make_response([
            CashTransaction(
                accountId="U1234567",
                transactionID="CT_COMMADJ",
                type=enums.CashAction.COMMADJ,
                amount=Decimal("0.50"),
                currency="USD",
                description="COMMISSION ADJUSTMENT",
                dateTime=datetime.datetime(2024, 2, 15, 0, 0, 0),
            ),
        ])
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert len(activities) == 1
        assert activities[0].type == "fee"

    def test_cash_transaction_bond_interest(self, mock_configured_settings):
        """CashAction.BONDINTRCVD and BONDINTPAID map to 'interest'."""
        response = self._make_response([
            CashTransaction(
                accountId="U1234567",
                transactionID="CT_BOND1",
                type=enums.CashAction.BONDINTRCVD,
                amount=Decimal("100.00"),
                currency="USD",
                dateTime=datetime.datetime(2024, 6, 1, 0, 0, 0),
            ),
            CashTransaction(
                accountId="U1234567",
                transactionID="CT_BOND2",
                type=enums.CashAction.BONDINTPAID,
                amount=Decimal("-50.00"),
                currency="USD",
                dateTime=datetime.datetime(2024, 6, 1, 0, 0, 0),
            ),
        ])
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert len(activities) == 2
        assert all(a.type == "interest" for a in activities)

    def test_cash_transaction_raw_data(self, mock_configured_settings):
        """raw_data contains stringified CashTransaction fields."""
        response = self._make_response([
            CashTransaction(
                accountId="U1234567",
                transactionID="CT_RAW",
                type=enums.CashAction.DIVIDEND,
                amount=Decimal("25.50"),
                symbol="AAPL",
                currency="USD",
                dateTime=datetime.datetime(2024, 3, 15, 10, 0, 0),
            ),
        ])
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert activities[0].raw_data is not None
        assert activities[0].raw_data["transactionID"] == "CT_RAW"
        assert activities[0].raw_data["symbol"] == "AAPL"

    def test_cash_action_string_dividend(self, mock_configured_settings):
        """Raw string 'Dividends' maps to 'dividend' (ibflex may not parse to enum)."""
        response = self._make_response([
            CashTransaction(
                accountId="U1234567",
                transactionID="CT_STR1",
                type="Dividends",
                amount=Decimal("25.00"),
                symbol="AAPL",
                currency="USD",
                dateTime=datetime.datetime(2024, 3, 15, 10, 0, 0),
            ),
        ])
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert len(activities) == 1
        assert activities[0].type == "dividend"

    def test_cash_action_string_deposit_withdrawal(self, mock_configured_settings):
        """Raw string 'Deposits/Withdrawals' maps correctly based on amount sign."""
        response = self._make_response([
            CashTransaction(
                accountId="U1234567",
                transactionID="CT_STR2",
                type="Deposits/Withdrawals",
                amount=Decimal("5000.00"),
                currency="USD",
                dateTime=datetime.datetime(2024, 4, 1, 9, 0, 0),
            ),
            CashTransaction(
                accountId="U1234567",
                transactionID="CT_STR3",
                type="Deposits/Withdrawals",
                amount=Decimal("-2000.00"),
                currency="USD",
                dateTime=datetime.datetime(2024, 4, 2, 9, 0, 0),
            ),
        ])
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert len(activities) == 2
        deposit = next(a for a in activities if a.external_id == "CT:CT_STR2")
        assert deposit.type == "deposit"
        withdrawal = next(a for a in activities if a.external_id == "CT:CT_STR3")
        assert withdrawal.type == "withdrawal"

    def test_cash_action_string_interest(self, mock_configured_settings):
        """Raw string 'Broker Interest Received' maps to 'interest'."""
        response = self._make_response([
            CashTransaction(
                accountId="U1234567",
                transactionID="CT_STR4",
                type="Broker Interest Received",
                amount=Decimal("12.34"),
                currency="USD",
                dateTime=datetime.datetime(2024, 3, 1, 0, 0, 0),
            ),
        ])
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert len(activities) == 1
        assert activities[0].type == "interest"

    def test_cash_action_string_withholding_tax(self, mock_configured_settings):
        """Raw string 'Withholding Tax' maps to 'tax'."""
        response = self._make_response([
            CashTransaction(
                accountId="U1234567",
                transactionID="CT_STR5",
                type="Withholding Tax",
                amount=Decimal("-3.00"),
                currency="USD",
                dateTime=datetime.datetime(2024, 3, 15, 10, 0, 0),
            ),
        ])
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert len(activities) == 1
        assert activities[0].type == "tax"

    def test_cash_action_string_other_fees(self, mock_configured_settings):
        """Raw string 'Other Fees' maps to 'fee'."""
        response = self._make_response([
            CashTransaction(
                accountId="U1234567",
                transactionID="CT_STR6",
                type="Other Fees",
                amount=Decimal("-10.00"),
                currency="USD",
                dateTime=datetime.datetime(2024, 2, 1, 0, 0, 0),
            ),
        ])
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            activities = ibkr.get_activities()

        assert len(activities) == 1
        assert activities[0].type == "fee"


# ---------------------------------------------------------------------------
# TestIBKRSyncAll
# ---------------------------------------------------------------------------


class TestIBKRSyncAll:
    """Tests for sync_all() orchestration."""

    def test_sync_all_returns_all_data(
        self, mock_configured_settings, sample_flex_response
    ):
        """sync_all returns holdings, accounts, activities, and balance_dates."""
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=sample_flex_response):
            result = ibkr.sync_all()

        assert isinstance(result, ProviderSyncResult)
        assert len(result.accounts) == 1
        assert result.accounts[0].id == "U1234567"
        assert len(result.holdings) > 0
        assert len(result.activities) == 2
        assert result.errors == []
        assert "U1234567" in result.balance_dates
        assert result.balance_dates["U1234567"] is not None

    def test_sync_all_handles_fetch_error(self, mock_configured_settings):
        """IbflexClientError during fetch is caught and returned in errors."""
        from ibflex.client import IbflexClientError

        ibkr = IBKRFlexClient()

        with patch.object(
            ibkr, "_fetch_statement", side_effect=IbflexClientError("Download failed")
        ):
            result = ibkr.sync_all()

        assert isinstance(result, ProviderSyncResult)
        assert len(result.errors) == 1
        assert "Download failed" in str(result.errors[0])
        assert result.holdings == []
        assert result.accounts == []
        assert result.activities == []

    def test_sync_all_activities_best_effort(self, mock_configured_settings):
        """Activity mapping failure doesn't fail the entire sync."""
        stmt = FlexStatement(
            accountId="U1234567",
            fromDate=datetime.date(2024, 1, 1),
            toDate=datetime.date(2024, 12, 31),
            period="Last365CalendarDays",
            whenGenerated=datetime.datetime(2024, 6, 15, 12, 0, 0),
            OpenPositions=(
                OpenPosition(
                    accountId="U1234567",
                    symbol="AAPL",
                    position=Decimal("10"),
                    markPrice=Decimal("175.00"),
                    positionValue=Decimal("1750.00"),
                    currency="USD",
                ),
            ),
        )
        response = FlexQueryResponse(
            queryName="Test", type="AF", FlexStatements=(stmt,)
        )
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response), patch.object(
            ibkr,
            "_extract_activities",
            side_effect=Exception("Activity parse error"),
        ):
            result = ibkr.sync_all()

        # Sync should succeed even though activities failed
        assert result.errors == []
        assert len(result.holdings) == 1
        assert len(result.accounts) == 1
        assert result.activities == []

    def test_sync_all_balance_dates_from_when_generated(
        self, mock_configured_settings, sample_flex_response
    ):
        """Balance dates use whenGenerated from the FlexStatement."""
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=sample_flex_response):
            result = ibkr.sync_all()

        bd = result.balance_dates["U1234567"]
        assert bd == datetime.datetime(
            2024, 6, 15, 12, 0, 0, tzinfo=datetime.timezone.utc
        )

    def test_sync_all_balance_dates_fallback_to_date(self, mock_configured_settings):
        """Balance dates fall back to toDate when whenGenerated is None."""
        stmt = FlexStatement(
            accountId="U1234567",
            fromDate=datetime.date(2024, 1, 1),
            toDate=datetime.date(2024, 12, 31),
            period="Last365CalendarDays",
            whenGenerated=None,
        )
        response = FlexQueryResponse(
            queryName="Test", type="AF", FlexStatements=(stmt,)
        )
        ibkr = IBKRFlexClient()

        with patch.object(ibkr, "_fetch_statement", return_value=response):
            result = ibkr.sync_all()

        bd = result.balance_dates["U1234567"]
        assert bd == datetime.datetime(
            2024, 12, 31, 0, 0, 0, tzinfo=datetime.timezone.utc
        )
