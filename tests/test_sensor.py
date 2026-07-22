"""Tests for Trade Republic sensor platform."""

import pytest
from unittest.mock import patch
from homeassistant.core import HomeAssistant


@pytest.mark.asyncio
async def test_sensor_setup(hass: HomeAssistant, mock_config_entry) -> None:
    """Test successful setup of sensors and states."""
    mock_config_entry.add_to_hass(hass)

    # Force use demo credentials for deterministic testing
    hass.config_entries.async_update_entry(
        mock_config_entry, data={**mock_config_entry.data, "phone_number": "+4912345"}
    )

    with patch(
        "custom_components.traderepublic.coordinator.TradeRepublicDataUpdateCoordinator._async_update_data",
        return_value={
            "net_value": 15420.50,
            "available_cash": 1420.50,
            "invested_capital": 14000.00,
            "total_profit": 1420.50,
            "total_profit_percent": 10.15,
            "exemption_total": 1000.00,
            "exemption_used": 120.45,
            "holdings": [
                {"isin": "US88160R1014", "name": "Tesla Inc.", "value": 4500.0}
            ],
            "card_status": "ACTIVE",
            "card_saveback_earned": 14.50,
            "card_saveback_limit": 15.00,
            "recent_transactions": [{"title": "Dividend", "amount": 25.0}],
            "interest_rate": 2.25,
            "accrued_interest_daily": 0.087,
            "accrued_interest_monthly_est": 2.66,
        },
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        # Check states
        state = hass.states.get("sensor.trade_republic_portfolio_portfolio_value")
        assert state is not None
        assert state.state == "15420.5"
        assert "holdings" in state.attributes
        assert "recent_transactions" in state.attributes

        state_cash = hass.states.get("sensor.trade_republic_portfolio_cash_balance")
        assert state_cash is not None
        assert state_cash.state == "1420.5"
        assert state_cash.attributes.get("interest_rate") == 2.25
        assert state_cash.attributes.get("card_status") == "ACTIVE"
