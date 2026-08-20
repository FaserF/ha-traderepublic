"""Tests for Trade Republic config flow."""

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from custom_components.traderepublic.const import CONF_PHONE_NUMBER, CONF_PIN, DOMAIN


@pytest.mark.asyncio
async def test_config_flow_addon(hass: HomeAssistant) -> None:
    """Test config flow via Trade Republic Add-on."""
    from custom_components.traderepublic.const import (
        AUTH_MODE_ADDON,
        CONF_ADDON_HOST,
        CONF_ADDON_PORT,
        CONF_AUTH_MODE,
        CONF_SESSION_TOKEN,
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    # Select Addon mode
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_AUTH_MODE: AUTH_MODE_ADDON,
        },
    )
    assert result2["type"] == "form"
    assert result2["step_id"] == "addon"

    with patch(
        "custom_components.traderepublic.config_flow.TradeRepublicConfigFlow._async_connect_addon",
        return_value={
            "type": "create_entry",
            "title": "Trade Republic (+491701234567)",
            "data": {
                CONF_PHONE_NUMBER: "+491701234567",
                CONF_PIN: "",
                CONF_SESSION_TOKEN: "mock_addon_token",
                CONF_AUTH_MODE: AUTH_MODE_ADDON,
                CONF_ADDON_HOST: "127.0.0.1",
                CONF_ADDON_PORT: 8095,
            },
        },
    ):
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {
                CONF_ADDON_HOST: "127.0.0.1",
                CONF_ADDON_PORT: 8095,
            },
        )
        assert result3["type"] == "create_entry"
        assert result3["title"] == "Trade Republic (+491701234567)"


@pytest.mark.asyncio
async def test_config_flow_discovery(hass: HomeAssistant) -> None:
    """Test discovery step for Trade Republic Add-on."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "discovery"},
        data={"host": "127.0.0.1", "port": 8095},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "addon_confirm"

