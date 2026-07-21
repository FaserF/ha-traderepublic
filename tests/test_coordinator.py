"""Tests for Trade Republic coordinator."""

import pytest
from homeassistant.core import HomeAssistant
from custom_components.traderepublic.coordinator import TradeRepublicDataUpdateCoordinator

@pytest.mark.asyncio
async def test_coordinator_update(hass: HomeAssistant, mock_config_entry) -> None:
    """Test coordinator data fetch under mock conditions."""
    mock_config_entry.add_to_hass(hass)
    coordinator = TradeRepublicDataUpdateCoordinator(hass, mock_config_entry)
    
    # Force use demo credentials for deterministic testing
    coordinator.phone_number = "+4912345"

    from homeassistant import config_entries
    mock_config_entry.mock_state(hass, config_entries.ConfigEntryState.SETUP_IN_PROGRESS)
    
    await coordinator.async_config_entry_first_refresh()
    assert coordinator.data["net_value"] == 15420.50
    assert coordinator.data["available_cash"] == 1420.50
