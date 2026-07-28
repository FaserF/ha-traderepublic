"""Tests for Trade Republic coordinator."""

import pytest
from homeassistant.core import HomeAssistant
from custom_components.traderepublic.coordinator import (
    TradeRepublicDataUpdateCoordinator,
)


@pytest.mark.asyncio
async def test_coordinator_update(hass: HomeAssistant, mock_config_entry) -> None:
    """Test coordinator data fetch under mock conditions."""
    mock_config_entry.add_to_hass(hass)
    coordinator = TradeRepublicDataUpdateCoordinator(hass, mock_config_entry)

    # Force use demo credentials for deterministic testing
    coordinator.phone_number = "+4912345"

    from homeassistant import config_entries

    mock_config_entry.mock_state(
        hass, config_entries.ConfigEntryState.SETUP_IN_PROGRESS
    )

    await coordinator.async_config_entry_first_refresh()
    assert coordinator.data["net_value"] == 15420.50
    assert coordinator.data["available_cash"] == 1420.50


@pytest.mark.asyncio
async def test_coordinator_pin_fallback(hass: HomeAssistant, mock_config_entry) -> None:
    """Test that coordinator falls back to PIN re-auth when session token expires."""
    mock_config_entry.add_to_hass(hass)
    coordinator = TradeRepublicDataUpdateCoordinator(hass, mock_config_entry)
    coordinator.phone_number = "+4912345"

    from homeassistant import config_entries
    mock_config_entry.mock_state(
        hass, config_entries.ConfigEntryState.SETUP_IN_PROGRESS
    )

    # Force invalid session token initially to trigger fallback
    coordinator.config_entry.data = {
        **coordinator.config_entry.data,
        "session_token": "expired_token",
    }

    await coordinator.async_config_entry_first_refresh()
    assert coordinator.data["net_value"] == 15420.50
    assert coordinator.data["available_cash"] == 1420.50
