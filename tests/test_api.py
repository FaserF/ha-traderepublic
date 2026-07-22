"""Tests for Trade Republic API client."""

import pytest
from custom_components.traderepublic.api import (
    TradeRepublicAPIClient,
)


@pytest.mark.asyncio
async def test_demo_login():
    """Test login with demo phone number."""
    client = TradeRepublicAPIClient("+4912345", "1234")
    # demo path does not require websocket for step 1
    session_id = await client.login_step1()
    assert session_id == "demo_session"

    token = await client.login_step2("123456")
    assert token == "demo_token_xyz"

    data = await client.fetch_portfolio_data()
    assert data["net_value"] == 15420.50
    assert data["available_cash"] == 1420.50
    assert data["interest_rate"] == 2.25
    assert round(data["accrued_interest_daily"], 4) == round(
        1420.50 * (0.0225 / 365.0), 4
    )
    assert data["card_status"] == "ACTIVE"
    assert data["card_saveback_earned"] == 14.50
    assert len(data["recent_transactions"]) == 1

    # Test custom interest rate override
    custom_data = await client.fetch_portfolio_data(interest_rate=3.5)
    assert round(custom_data["interest_rate"], 2) == 3.5
    assert round(custom_data["accrued_interest_daily"], 4) == round(
        1420.50 * (0.035 / 365.0), 4
    )
