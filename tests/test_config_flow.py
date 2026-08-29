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

    async def mock_connect_addon(self, host, port):
        await self.async_set_unique_id("+491701234567")
        return self.async_create_entry(
            title="Trade Republic (+491701234567)",
            data={
                CONF_PHONE_NUMBER: "+491701234567",
                CONF_PIN: "",
                CONF_SESSION_TOKEN: "mock_addon_token",
                CONF_AUTH_MODE: AUTH_MODE_ADDON,
                CONF_ADDON_HOST: "127.0.0.1",
                CONF_ADDON_PORT: 8095,
            },
        )

    with (
        patch(
            "custom_components.traderepublic.config_flow.TradeRepublicConfigFlow._async_connect_addon",
            new=mock_connect_addon,
        ),
        patch(
            "custom_components.traderepublic.async_setup_entry",
            return_value=True,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "user"

        # Select Addon mode -> triggers mock_connect_addon directly
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_AUTH_MODE: AUTH_MODE_ADDON,
            },
        )
        assert result2["type"] == "create_entry"
        assert result2["title"] == "Trade Republic (+491701234567)"


@pytest.mark.asyncio
async def test_config_flow_discovery(hass: HomeAssistant) -> None:
    """Test discovery step for Trade Republic Add-on."""
    from custom_components.traderepublic.const import (
        AUTH_MODE_ADDON,
        CONF_ADDON_HOST,
        CONF_ADDON_PORT,
        CONF_AUTH_MODE,
        CONF_SESSION_TOKEN,
    )

    async def mock_connect_addon(self, host, port):
        await self.async_set_unique_id("+491701234567")
        return self.async_create_entry(
            title="Trade Republic (+491701234567)",
            data={
                CONF_PHONE_NUMBER: "+491701234567",
                CONF_PIN: "",
                CONF_SESSION_TOKEN: "mock_addon_token",
                CONF_AUTH_MODE: AUTH_MODE_ADDON,
                CONF_ADDON_HOST: host,
                CONF_ADDON_PORT: port,
            },
        )

    with (
        patch(
            "custom_components.traderepublic.config_flow.TradeRepublicConfigFlow._async_connect_addon",
            new=mock_connect_addon,
        ),
        patch(
            "custom_components.traderepublic.async_setup_entry",
            return_value=True,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "discovery"},
            data={"host": "127.0.0.1", "port": 8095},
        )
        assert result["type"] == "create_entry"
        assert result["title"] == "Trade Republic (+491701234567)"


@pytest.mark.asyncio
async def test_config_flow_addon_2fa_timeout_and_restart(hass: HomeAssistant) -> None:
    """Test addon 2FA timeout handling and restart on submit."""
    from custom_components.traderepublic.config_flow import TradeRepublicConfigFlow

    flow = TradeRepublicConfigFlow()
    flow.hass = hass
    flow._addon_host = "127.0.0.1"
    flow._addon_port = 8095
    flow._phone_number = "+491701234567"
    flow._pin = "1234"

    # Step 1: User verifies but challenge timed out
    class MockRespTimeout:
        status = 200

        async def json(self):
            return {"error": "The login challenge timed out (2 minutes exceeded)."}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    class MockSessionTimeout:
        def post(self, url, json=None, timeout=None):
            return MockRespTimeout()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("aiohttp.ClientSession", return_value=MockSessionTimeout()):
        res = await flow.async_step_addon_2fa(user_input={"code": ""})
        assert res["type"] == "form"
        assert res["step_id"] == "addon_2fa"
        assert res["errors"]["base"] == "timeout_expired"
        assert flow._addon_2fa_timed_out is True

    # Step 2: User clicks Submit again -> triggers login/init restart
    class MockRespRestartSuccess:
        status = 200

        async def json(self):
            return {"success": True}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    class MockSessionRestart:
        def post(self, url, json=None, timeout=None):
            return MockRespRestartSuccess()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("aiohttp.ClientSession", return_value=MockSessionRestart()):
        res2 = await flow.async_step_addon_2fa(user_input={"code": ""})
        assert res2["type"] == "form"
        assert res2["step_id"] == "addon_2fa"
        assert res2["errors"] == {}
        assert flow._addon_2fa_timed_out is False


@pytest.mark.asyncio
async def test_config_flow_addon_2fa_approval_pending(hass: HomeAssistant) -> None:
    """Test addon 2FA approval pending message when user submits without code."""
    from custom_components.traderepublic.config_flow import TradeRepublicConfigFlow

    flow = TradeRepublicConfigFlow()
    flow.hass = hass
    flow._addon_host = "127.0.0.1"
    flow._addon_port = 8095
    flow._phone_number = "+491701234567"
    flow._pin = "1234"

    class MockRespPending:
        status = 200

        async def json(self):
            return {"error": "Approval pending"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    class MockSessionPending:
        def post(self, url, json=None, timeout=None):
            return MockRespPending()

        def get(self, url, timeout=None):
            return MockRespPending()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with (
        patch("aiohttp.ClientSession", return_value=MockSessionPending()),
        patch("asyncio.sleep", return_value=None),
    ):
        res = await flow.async_step_addon_2fa(user_input={})
        assert res["type"] == "form"
        assert res["step_id"] == "addon_2fa"
        assert res["errors"]["base"] == "approval_pending"


@pytest.mark.asyncio
async def test_config_flow_mfa_invalid_code(hass: HomeAssistant) -> None:
    """Test manual MFA step with invalid code."""
    from unittest.mock import AsyncMock

    from custom_components.traderepublic.api import InvalidAuthError
    from custom_components.traderepublic.config_flow import TradeRepublicConfigFlow

    flow = TradeRepublicConfigFlow()
    flow.hass = hass
    flow._phone_number = "+491701234567"
    flow._pin = "1234"

    mock_client = AsyncMock()
    mock_client.login_step2.side_effect = InvalidAuthError("Invalid code")
    flow._client = mock_client

    res = await flow.async_step_mfa(user_input={"code": "9999"})
    assert res["type"] == "form"
    assert res["step_id"] == "mfa"
    assert res["errors"]["base"] == "invalid_code"

