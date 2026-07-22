"""Tests for Trade Republic config flow."""

import pytest
from unittest.mock import patch
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from custom_components.traderepublic.const import DOMAIN, CONF_PHONE_NUMBER, CONF_PIN


@pytest.mark.asyncio
async def test_config_flow_demo(hass: HomeAssistant) -> None:
    """Test standard config flow with demo account."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    # Submit credentials
    with (
        patch(
            "custom_components.traderepublic.api.TradeRepublicAPIClient.connect",
            return_value=None,
        ),
        patch(
            "custom_components.traderepublic.api.TradeRepublicAPIClient.login_step1",
            return_value="demo_session",
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_PHONE_NUMBER: "+4912345",
                CONF_PIN: "1234",
            },
        )
    # Demo bypass config flow to success immediately
    assert result["type"] == "create_entry"
    assert result["title"] == "+4912345"
    assert result["data"][CONF_PHONE_NUMBER] == "+4912345"
    assert result["data"][CONF_PIN] == "1234"
