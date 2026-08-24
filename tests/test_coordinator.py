"""Tests for Trade Republic coordinator."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed

from custom_components.traderepublic.coordinator import (
    TradeRepublicDataUpdateCoordinator,
)


@pytest.mark.asyncio
async def test_coordinator_update(hass: HomeAssistant, mock_config_entry) -> None:
    """Test coordinator data fetch under mock conditions."""
    mock_config_entry.add_to_hass(hass)
    coordinator = TradeRepublicDataUpdateCoordinator(hass, mock_config_entry)

    mock_config_entry.mock_state(
        hass, config_entries.ConfigEntryState.SETUP_IN_PROGRESS
    )

    mock_addon_payload = {
        "is_logged_in": True,
        "data": {
            "net_value": 15420.50,
            "available_cash": 1420.50,
            "invested_capital": 14000.00,
            "total_profit": 1420.50,
            "total_profit_percent": 10.15,
            "holdings": [{"isin": "US88160R1014", "name": "Tesla Inc.", "value": 4500.0}],
            "card_status": "ACTIVE",
            "recent_transactions": [{"title": "Dividend", "amount": 25.0}],
        },
    }

    with patch(
        "custom_components.traderepublic.api.AddonClient.fetch_data",
        new_callable=AsyncMock,
        return_value=("traderepublic:8095", mock_addon_payload),
    ):
        await coordinator.async_config_entry_first_refresh()
        assert coordinator.data["net_value"] == 15420.50
        assert coordinator.data["available_cash"] == 1420.50
        assert coordinator.data["holdings"][0]["name"] == "Tesla Inc."


@pytest.mark.asyncio
async def test_coordinator_auth_failed_when_session_expired(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test that coordinator raises ConfigEntryAuthFailed when add-on reports logged out."""
    mock_config_entry.add_to_hass(hass)
    coordinator = TradeRepublicDataUpdateCoordinator(hass, mock_config_entry)

    mock_config_entry.mock_state(
        hass, config_entries.ConfigEntryState.SETUP_IN_PROGRESS
    )

    mock_addon_payload = {
        "is_logged_in": False,
        "data": None,
    }

    with (
        patch(
            "custom_components.traderepublic.api.AddonClient.fetch_data",
            new_callable=AsyncMock,
            return_value=("traderepublic:8095", mock_addon_payload),
        ),
        pytest.raises(ConfigEntryAuthFailed),
    ):
        await coordinator._async_update_data()

