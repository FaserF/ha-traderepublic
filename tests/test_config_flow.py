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


@pytest.mark.asyncio
async def test_config_flow_addon_scan_qr_check(hass: HomeAssistant) -> None:
    """Test unified addon_scan step checking QR code when fields are left blank."""
    from unittest.mock import AsyncMock

    from custom_components.traderepublic.config_flow import TradeRepublicConfigFlow

    flow = TradeRepublicConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._addon_host = "127.0.0.1"
    flow._addon_port = 8095

    # Mock AddonClient returning active session
    with patch(
        "custom_components.traderepublic.config_flow.AddonClient"
    ) as mock_client_cls:
        client_instance = AsyncMock()
        client_instance.fetch_session.return_value = (
            "127.0.0.1",
            {
                "session_token": "valid_token",
                "phone_number": "+491701112233",
                "is_logged_in": True,
            },
        )
        mock_client_cls.return_value = client_instance

        # Submitting with empty phone and pin -> triggers QR session polling
        res = await flow.async_step_addon_scan(
            user_input={"phone_number": "", "pin": ""}
        )
        assert res["type"] == "create_entry"
        assert res["title"] == "Trade Republic (+491701112233)"


@pytest.mark.asyncio
async def test_config_flow_addon_scan_credentials_flow(hass: HomeAssistant) -> None:
    """Test unified addon_scan step initiating credentials login when phone and PIN are entered."""
    from custom_components.traderepublic.config_flow import TradeRepublicConfigFlow

    flow = TradeRepublicConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._addon_host = "127.0.0.1"
    flow._addon_port = 8095

    class MockRespInit:
        status = 200

        async def json(self):
            return {"success": True}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    class MockSessionInit:
        def post(self, url, json=None, timeout=None):
            return MockRespInit()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("aiohttp.ClientSession", return_value=MockSessionInit()):
        res = await flow.async_step_addon_scan(
            user_input={"phone_number": "+491701234567", "pin": "1234"}
        )
        assert res["type"] == "form"
        assert res["step_id"] == "addon_2fa"


@pytest.mark.asyncio
async def test_config_flow_user_addon_detected(hass: HomeAssistant) -> None:
    """Test user step dynamically detecting running Add-on."""
    from unittest.mock import AsyncMock

    from custom_components.traderepublic.config_flow import TradeRepublicConfigFlow

    flow = TradeRepublicConfigFlow()
    flow.hass = hass
    flow.context = {}

    with patch(
        "custom_components.traderepublic.config_flow.AddonClient"
    ) as mock_client_cls:
        client_instance = AsyncMock()
        client_instance.fetch_session.return_value = (
            "127.0.0.1",
            {"session_token": None, "is_logged_in": False},
        )
        mock_client_cls.return_value = client_instance

        res = await flow.async_step_user()
        assert res["type"] == "form"
        assert res["step_id"] == "user"
        assert (
            "127.0.0.1:8095" in res["description_placeholders"]["addon_detection_info"]
        )


@pytest.mark.asyncio
async def test_config_flow_user_addon_not_detected(hass: HomeAssistant) -> None:
    """Test user step displaying recommendation and repo link when Add-on not found."""
    from unittest.mock import AsyncMock

    from custom_components.traderepublic.config_flow import TradeRepublicConfigFlow

    flow = TradeRepublicConfigFlow()
    flow.hass = hass
    flow.context = {}

    with patch(
        "custom_components.traderepublic.config_flow.AddonClient"
    ) as mock_client_cls:
        client_instance = AsyncMock()
        client_instance.fetch_session.return_value = (None, None)
        mock_client_cls.return_value = client_instance

        res = await flow.async_step_user()
        assert res["type"] == "form"
        assert res["step_id"] == "user"
        assert (
            "https://github.com/FaserF/hassio-addons"
            in res["description_placeholders"]["addon_detection_info"]
        )


@pytest.mark.asyncio
async def test_config_flow_reauth_ingress_flow(hass: HomeAssistant) -> None:
    """Test reauth ingress action opens external step in new tab."""
    from custom_components.traderepublic.config_flow import TradeRepublicConfigFlow

    flow = TradeRepublicConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._addon_host = "edfe50eb_traderepublic"
    flow._addon_port = 8095

    # Trigger ingress action
    res = await flow.async_step_reauth_ingress()
    assert res["type"] in ("external", "external_step")
    assert res["step_id"] == "reauth_ingress"
    assert res["url"] == "/hassio/ingress/edfe50eb_traderepublic"
