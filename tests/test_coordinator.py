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
            "holdings": [
                {"isin": "US88160R1014", "name": "Tesla Inc.", "value": 4500.0}
            ],
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


@pytest.mark.asyncio
async def test_coordinator_connecting_state_and_interest_override(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Verify connecting state defers auth failure, categories include card/timeline/savings, and interest override applies."""
    from types import SimpleNamespace

    from homeassistant.helpers.update_coordinator import UpdateFailed

    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={"interest_rate": 3.5},
    )
    coordinator = TradeRepublicDataUpdateCoordinator(hass, mock_config_entry)
    coordinator.data = {"net_value": 5000.0, "available_cash": 1000.0}

    mock_config_entry.mock_state(
        hass, config_entries.ConfigEntryState.SETUP_IN_PROGRESS
    )

    # 1. Connecting state must NOT raise ConfigEntryAuthFailed and must serve cached data
    connecting_payload = {
        "is_logged_in": False,
        "is_connecting": True,
        "auth_expired": False,
        "data": {},
    }
    with patch(
        "custom_components.traderepublic.api.AddonClient.fetch_data",
        new_callable=AsyncMock,
        return_value=("edfe50eb-traderepublic", connecting_payload),
    ) as mock_fetch:
        data = await coordinator._async_update_data()
        assert data["net_value"] == 5000.0
        requested_cats = mock_fetch.call_args.kwargs["requested_categories"]
        assert set(requested_cats) == {"portfolio", "cash", "savings", "card", "timeline"}

    # 2. Connecting state with no cache raises UpdateFailed (not ConfigEntryAuthFailed)
    coordinator.data = {}
    with (
        patch(
            "custom_components.traderepublic.api.AddonClient.fetch_data",
            new_callable=AsyncMock,
            return_value=("edfe50eb-traderepublic", connecting_payload),
        ),
        pytest.raises(UpdateFailed),
    ):
        await coordinator._async_update_data()

    # 3. Registered net_value + available_cash entities still request savings, card, and timeline
    fake_entries = [
        SimpleNamespace(
            disabled=False, unique_id=f"traderepublic_net_value_{mock_config_entry.entry_id}"
        ),
        SimpleNamespace(
            disabled=False,
            unique_id=f"traderepublic_available_cash_{mock_config_entry.entry_id}",
        ),
    ]
    live_payload = {
        "is_logged_in": True,
        "is_connecting": False,
        "auth_expired": False,
        "data": {
            "net_value": 12000.0,
            "available_cash": 2000.0,
            "invested_capital": 10000.0,
            "savings_plans_count": 1,
        },
    }
    with (
        patch(
            "homeassistant.helpers.entity_registry.async_entries_for_config_entry",
            return_value=fake_entries,
        ),
        patch(
            "custom_components.traderepublic.api.AddonClient.fetch_data",
            new_callable=AsyncMock,
            return_value=("edfe50eb-traderepublic", live_payload),
        ) as mock_fetch2,
    ):
        result = await coordinator._async_update_data()
        cats = mock_fetch2.call_args.kwargs["requested_categories"]
        assert {"portfolio", "cash", "savings", "card", "timeline"}.issubset(set(cats))
        assert result["interest_rate"] == 3.5
        assert result["accrued_interest_daily"] == pytest.approx(2000.0 * (0.035 / 365.0))
