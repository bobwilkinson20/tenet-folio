"""Tests for the IBKR Flex Web Service setup script."""

import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from ibflex.Types import (
    CashReportCurrency,
    FlexQueryResponse,
    FlexStatement,
    OpenPosition,
    Trade,
)
from ibflex.client import IbflexClientError, ResponseCodeError

from scripts.setup_ibkr import validate_credentials, validate_query_sections, validate_trade_columns


class TestValidateCredentials:
    """Tests for the validate_credentials function."""

    @patch("scripts.setup_ibkr.client")
    def test_successful_validation(self, mock_client):
        """Successful download returns raw bytes."""
        mock_client.download.return_value = b"<FlexQueryResponse>...</FlexQueryResponse>"

        result = validate_credentials("valid_token", "123456")

        mock_client.download.assert_called_once_with("valid_token", "123456")
        assert result == b"<FlexQueryResponse>...</FlexQueryResponse>"

    @patch("scripts.setup_ibkr.client")
    def test_invalid_token(self, mock_client):
        """Invalid token raises ResponseCodeError with code 1015."""
        mock_client.download.side_effect = ResponseCodeError("1015", "Token is invalid.")

        with pytest.raises(ResponseCodeError, match="Token is invalid"):
            validate_credentials("bad_token", "123456")

    @patch("scripts.setup_ibkr.client")
    def test_expired_token(self, mock_client):
        """Expired token raises ResponseCodeError with code 1012."""
        mock_client.download.side_effect = ResponseCodeError("1012", "Token has expired.")

        with pytest.raises(ResponseCodeError, match="Token has expired"):
            validate_credentials("expired_token", "123456")

    @patch("scripts.setup_ibkr.client")
    def test_invalid_query_id(self, mock_client):
        """Invalid query ID raises ResponseCodeError with code 1014."""
        mock_client.download.side_effect = ResponseCodeError("1014", "Query is invalid.")

        with pytest.raises(ResponseCodeError, match="Query is invalid"):
            validate_credentials("valid_token", "000000")

    @patch("scripts.setup_ibkr.client")
    def test_generic_client_error(self, mock_client):
        """Other ibflex errors propagate as IbflexClientError."""
        mock_client.download.side_effect = IbflexClientError("Something went wrong")

        with pytest.raises(IbflexClientError, match="Something went wrong"):
            validate_credentials("token", "query")


class TestValidateQuerySections:
    """Tests for the validate_query_sections function."""

    def _make_response(self, positions=(), cash=(), trades=()):
        """Helper to build a FlexQueryResponse with specified sections."""
        stmt = FlexStatement(
            accountId="U1234567",
            fromDate=datetime.date(2024, 1, 1),
            toDate=datetime.date(2024, 12, 31),
            period="Last365CalendarDays",
            whenGenerated=datetime.datetime(2024, 6, 15, 12, 0, 0),
            OpenPositions=positions,
            CashReport=cash,
            Trades=trades,
        )
        return FlexQueryResponse(
            queryName="Test", type="AF", FlexStatements=(stmt,)
        )

    @patch("scripts.setup_ibkr.parser")
    def test_all_sections_present(self, mock_parser):
        """No missing sections when all are present."""
        response = self._make_response(
            positions=(
                OpenPosition(
                    accountId="U1234567",
                    symbol="AAPL",
                    position=Decimal("100"),
                    markPrice=Decimal("175.00"),
                    currency="USD",
                ),
            ),
            cash=(
                CashReportCurrency(
                    accountId="U1234567",
                    currency="USD",
                    endingCash=Decimal("1000"),
                ),
            ),
            trades=(
                Trade(
                    accountId="U1234567",
                    tradeID="T1",
                    symbol="AAPL",
                    tradeDate=datetime.date(2024, 1, 15),
                ),
            ),
        )
        mock_parser.parse.return_value = response

        missing = validate_query_sections(b"<xml>data</xml>")
        assert missing == []

    @patch("scripts.setup_ibkr.parser")
    def test_all_sections_missing(self, mock_parser):
        """All sections reported missing when query has none."""
        response = self._make_response()
        mock_parser.parse.return_value = response

        missing = validate_query_sections(b"<xml>data</xml>")
        assert "Open Positions" in missing
        assert "Cash Report" in missing
        assert "Trades" in missing

    @patch("scripts.setup_ibkr.parser")
    def test_only_positions_missing(self, mock_parser):
        """Only Open Positions reported missing when others are present."""
        response = self._make_response(
            cash=(
                CashReportCurrency(
                    accountId="U1234567",
                    currency="USD",
                    endingCash=Decimal("1000"),
                ),
            ),
            trades=(
                Trade(
                    accountId="U1234567",
                    tradeID="T1",
                    symbol="AAPL",
                    tradeDate=datetime.date(2024, 1, 15),
                ),
            ),
        )
        mock_parser.parse.return_value = response

        missing = validate_query_sections(b"<xml>data</xml>")
        assert missing == ["Open Positions"]

    @patch("scripts.setup_ibkr.parser")
    def test_only_trades_missing(self, mock_parser):
        """Only Trades reported missing when others are present."""
        response = self._make_response(
            positions=(
                OpenPosition(
                    accountId="U1234567",
                    symbol="AAPL",
                    position=Decimal("100"),
                    markPrice=Decimal("175.00"),
                    currency="USD",
                ),
            ),
            cash=(
                CashReportCurrency(
                    accountId="U1234567",
                    currency="USD",
                    endingCash=Decimal("1000"),
                ),
            ),
        )
        mock_parser.parse.return_value = response

        missing = validate_query_sections(b"<xml>data</xml>")
        assert missing == ["Trades"]


class TestValidateTradeColumns:
    """Tests for the validate_trade_columns function."""

    def _make_response(self, trades=()):
        """Helper to build a FlexQueryResponse with specified trades."""
        stmt = FlexStatement(
            accountId="U1234567",
            fromDate=datetime.date(2024, 1, 1),
            toDate=datetime.date(2024, 12, 31),
            period="Last365CalendarDays",
            whenGenerated=datetime.datetime(2024, 6, 15, 12, 0, 0),
            Trades=trades,
        )
        return FlexQueryResponse(
            queryName="Test", type="AF", FlexStatements=(stmt,)
        )

    @patch("scripts.setup_ibkr.parser")
    def test_all_columns_present(self, mock_parser):
        """No missing columns when trade has all required and recommended fields."""
        from ibflex import enums

        response = self._make_response(
            trades=(
                Trade(
                    accountId="U1234567",
                    tradeID="T1",
                    tradeDate=datetime.date(2024, 1, 15),
                    buySell=enums.BuySell.BUY,
                    netCash=Decimal("-1000"),
                    ibCommission=Decimal("-1.00"),
                    settleDateTarget=datetime.date(2024, 1, 17),
                    symbol="AAPL",
                ),
            ),
        )
        mock_parser.parse.return_value = response

        missing_req, missing_rec = validate_trade_columns(b"<xml>data</xml>")
        assert missing_req == []
        assert missing_rec == []

    @patch("scripts.setup_ibkr.parser")
    def test_missing_required_columns(self, mock_parser):
        """Reports missing required columns when trade lacks tradeID and tradeDate."""
        response = self._make_response(
            trades=(
                Trade(
                    accountId="U1234567",
                    tradeID=None,
                    tradeDate=None,
                    symbol="AAPL",
                ),
            ),
        )
        mock_parser.parse.return_value = response

        missing_req, _ = validate_trade_columns(b"<xml>data</xml>")
        assert "tradeID" in missing_req
        assert "tradeDate" in missing_req

    @patch("scripts.setup_ibkr.parser")
    def test_missing_recommended_columns(self, mock_parser):
        """Reports missing recommended columns."""
        response = self._make_response(
            trades=(
                Trade(
                    accountId="U1234567",
                    tradeID="T1",
                    tradeDate=datetime.date(2024, 1, 15),
                    symbol="AAPL",
                    # buySell, netCash, ibCommission, settleDateTarget all None
                ),
            ),
        )
        mock_parser.parse.return_value = response

        missing_req, missing_rec = validate_trade_columns(b"<xml>data</xml>")
        assert missing_req == []
        assert "buySell" in missing_rec
        assert "netCash" in missing_rec
        assert "ibCommission" in missing_rec
        assert "settleDateTarget" in missing_rec

    @patch("scripts.setup_ibkr.parser")
    def test_no_trades_returns_all_columns(self, mock_parser):
        """When no trades exist, all columns reported as missing."""
        response = self._make_response(trades=())
        mock_parser.parse.return_value = response

        missing_req, missing_rec = validate_trade_columns(b"<xml>data</xml>")
        assert len(missing_req) > 0
        assert len(missing_rec) > 0


class TestMainFlow:
    """Tests for the main() interactive flow."""

    @patch("scripts.setup_ibkr.validate_trade_columns")
    @patch("scripts.setup_ibkr.validate_query_sections")
    @patch("scripts.setup_ibkr.validate_credentials")
    @patch("builtins.input")
    def test_successful_flow(
        self, mock_input, mock_validate, mock_validate_sections,
        mock_validate_trades, capsys,
    ):
        """Successful flow prints section check results and env vars."""
        mock_input.side_effect = ["my_token", "12345", "n"]
        mock_validate.return_value = b"<xml>data</xml>"
        mock_validate_sections.return_value = []
        mock_validate_trades.return_value = ([], [])

        from scripts.setup_ibkr import main

        main()

        captured = capsys.readouterr()
        assert "Checking Flex Query sections..." in captured.out
        assert "Open Positions: found" in captured.out
        assert "Cash Report:    found" in captured.out
        assert "Trades:         found" in captured.out
        assert "IBKR_FLEX_TOKEN=my_token" in captured.out
        assert "IBKR_FLEX_QUERY_ID=12345" in captured.out
        mock_validate.assert_called_once_with("my_token", "12345")

    @patch("scripts.setup_ibkr.validate_trade_columns")
    @patch("scripts.setup_ibkr.validate_query_sections")
    @patch("scripts.setup_ibkr.validate_credentials")
    @patch("builtins.input")
    def test_missing_sections_prints_warning(
        self, mock_input, mock_validate, mock_validate_sections,
        mock_validate_trades, capsys,
    ):
        """Missing sections print a warning but still output env vars."""
        mock_input.side_effect = ["my_token", "12345", "n"]
        mock_validate.return_value = b"<xml>data</xml>"
        mock_validate_sections.return_value = ["Open Positions", "Trades"]
        mock_validate_trades.return_value = ([], [])

        from scripts.setup_ibkr import main

        main()

        captured = capsys.readouterr()
        assert "Warning" in captured.out
        assert "Open Positions" in captured.out
        assert "Trades" in captured.out
        # Env vars should still be printed
        assert "IBKR_FLEX_TOKEN=my_token" in captured.out
        assert "IBKR_FLEX_QUERY_ID=12345" in captured.out

    @patch("scripts.setup_ibkr.validate_trade_columns")
    @patch("scripts.setup_ibkr.validate_query_sections")
    @patch("scripts.setup_ibkr.validate_credentials")
    @patch("builtins.input")
    def test_missing_trade_columns_prints_warning(
        self, mock_input, mock_validate, mock_validate_sections,
        mock_validate_trades, capsys,
    ):
        """Missing trade columns print a warning with column names."""
        mock_input.side_effect = ["my_token", "12345", "n"]
        mock_validate.return_value = b"<xml>data</xml>"
        mock_validate_sections.return_value = []
        mock_validate_trades.return_value = (
            ["tradeID", "tradeDate"],
            ["buySell", "netCash"],
        )

        from scripts.setup_ibkr import main

        main()

        captured = capsys.readouterr()
        assert "Missing required Trades columns" in captured.out
        assert "tradeID" in captured.out
        assert "tradeDate" in captured.out
        assert "Missing recommended Trades columns" in captured.out
        assert "buySell" in captured.out
        assert "netCash" in captured.out
        # Env vars should still be printed
        assert "IBKR_FLEX_TOKEN=my_token" in captured.out

    @patch("builtins.input")
    def test_empty_token_exits(self, mock_input):
        """Empty token causes sys.exit(1)."""
        mock_input.side_effect = [""]

        from scripts.setup_ibkr import main

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    @patch("builtins.input")
    def test_empty_query_id_exits(self, mock_input):
        """Empty query ID causes sys.exit(1)."""
        mock_input.side_effect = ["valid_token", ""]

        from scripts.setup_ibkr import main

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    @patch("scripts.setup_ibkr.validate_credentials")
    @patch("builtins.input")
    def test_validation_failure_exits(self, mock_input, mock_validate, capsys):
        """Validation failure prints error and exits."""
        mock_input.side_effect = ["bad_token", "12345"]
        mock_validate.side_effect = ResponseCodeError("1015", "Token is invalid.")

        from scripts.setup_ibkr import main

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Token is invalid" in captured.out
        assert "Common issues:" in captured.out
