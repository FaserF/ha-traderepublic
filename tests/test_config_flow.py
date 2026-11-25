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
            "custom_components.traderepublic.api.AddonClient.fetch_session",
            return_value=("127.0.0.1", {"session_token": None, "is_logged_in": False}),
        ),
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
            "custom_components.traderepublic.api.AddonClient.fetch_session",
            return_value=("127.0.0.1", {"session_token": None, "is_logged_in": False}),
        ),
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
    """Test reauth ingress action shows form with Ingress link."""
    from custom_components.traderepublic.config_flow import TradeRepublicConfigFlow

    flow = TradeRepublicConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._addon_host = "edfe50eb_traderepublic"
    flow._addon_port = 8095

    # Trigger ingress action
    res = await flow.async_step_reauth_ingress()
    assert res["type"] == "form"
    assert res["step_id"] == "reauth_ingress"
    assert (
        res["description_placeholders"]["ingress_url"]
        == "/hassio/ingress/edfe50eb_traderepublic"
    )


@pytest.mark.asyncio
async def test_config_flow_closes_addon_client_sessions(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Verify AddonClient.close() is always awaited on user, addon_scan, and reauth_confirm."""
    from unittest.mock import AsyncMock

    from custom_components.traderepublic.config_flow import TradeRepublicConfigFlow

    # 1. async_step_user closes AddonClient even if fetch_session raises
    flow = TradeRepublicConfigFlow()
    flow.hass = hass
    flow.context = {}
    with patch(
        "custom_components.traderepublic.config_flow.AddonClient"
    ) as mock_client_cls:
        client_inst = AsyncMock()
        client_inst.fetch_session.side_effect = RuntimeError("boom")
        mock_client_cls.return_value = client_inst
        with pytest.raises(RuntimeError):
            await flow.async_step_user()
        assert client_inst.close.await_count == 1

    # 2. async_step_addon_qr closes AddonClient on form render
    flow2 = TradeRepublicConfigFlow()
    flow2.hass = hass
    flow2.context = {}
    with (
        patch(
            "custom_components.traderepublic.config_flow.AddonClient"
        ) as mock_client_cls2,
        patch("asyncio.sleep", return_value=None),
    ):
        client_inst2 = AsyncMock()
        client_inst2.fetch_qr_code.return_value = ("127.0.0.1", None, False)
        mock_client_cls2.return_value = client_inst2
        res = await flow2.async_step_addon_qr()
        assert res["type"] == "form"
        assert client_inst2.close.await_count == 1

    # 3. async_step_reauth_confirm closes AddonClient when checking add-on status
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={**mock_config_entry.data, "auth_mode": "addon"},
    )
    flow3 = TradeRepublicConfigFlow()
    flow3.hass = hass
    flow3.context = {"entry_id": mock_config_entry.entry_id}
    with patch(
        "custom_components.traderepublic.config_flow.AddonClient"
    ) as mock_client_cls3:
        client_inst3 = AsyncMock()
        client_inst3.fetch_session.return_value = (
            "edfe50eb-traderepublic",
            {"session_token": "tok", "is_logged_in": True},
        )
        mock_client_cls3.return_value = client_inst3
        res3 = await flow3.async_step_reauth_confirm()
        assert res3["type"] == "form"
        assert res3["step_id"] == "reauth_confirm"
        assert (
            res3["description_placeholders"]["addon_host"] == "edfe50eb-traderepublic"
        )
        assert client_inst3.close.await_count == 1


@pytest.mark.asyncio
async def test_config_flow_addon_scan_qr_reauth_updates_entry(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Verify addon_scan completes reauth cleanly when QR fetch detects active session."""
    from unittest.mock import AsyncMock

    from custom_components.traderepublic.config_flow import TradeRepublicConfigFlow

    mock_config_entry.add_to_hass(hass)
    flow = TradeRepublicConfigFlow()
    flow.hass = hass
    flow.context = {"entry_id": mock_config_entry.entry_id}
    flow._addon_host = "127.0.0.1"
    flow._addon_port = 8095

    with (
        patch(
            "custom_components.traderepublic.config_flow.AddonClient"
        ) as mock_client_cls,
        patch.object(
            hass.config_entries, "async_reload", new=AsyncMock()
        ) as mock_reload,
    ):
        client_inst = AsyncMock()
        client_inst.fetch_qr_code.return_value = ("edfe50eb-traderepublic", None, True)
        client_inst.fetch_session.return_value = (
            "edfe50eb-traderepublic",
            {
                "session_token": "new_qr_token",
                "phone_number": "+49123456789",
                "is_logged_in": True,
            },
        )
        mock_client_cls.return_value = client_inst

        res = await flow.async_step_addon_qr()
        assert res["type"] == "abort"
        assert res["reason"] == "reauth_successful"
        assert mock_config_entry.data["session_token"] == "new_qr_token"
        assert mock_reload.await_count == 1
        assert client_inst.close.await_count == 1


@pytest.mark.asyncio
async def test_config_flow_addon_scan_prefills_phone_and_allows_qr_without_pin(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Verify addon_scan pre-fills phone number and triggers QR flow when PIN is omitted."""
    from unittest.mock import AsyncMock

    from custom_components.traderepublic.config_flow import TradeRepublicConfigFlow
    from custom_components.traderepublic.const import CONF_PHONE_NUMBER

    mock_config_entry.add_to_hass(hass)
    flow = TradeRepublicConfigFlow()
    flow.hass = hass
    flow.context = {"entry_id": mock_config_entry.entry_id}
    flow._phone_number = "+49123456789"
    flow._addon_host = "127.0.0.1"
    flow._addon_port = 8095

    res_form = await flow.async_step_addon_scan()
    assert res_form["type"] == "form"
    assert res_form["step_id"] == "addon_scan"
    phone_key = next(
        k
        for k in res_form["data_schema"].schema
        if getattr(k, "schema", None) == CONF_PHONE_NUMBER
    )
    assert phone_key.default() == "+49123456789"

    # Submit with pre-filled phone and empty PIN -> should check session then show addon_qr
    with (
        patch(
            "custom_components.traderepublic.config_flow.AddonClient"
        ) as mock_client_cls,
        patch("asyncio.sleep", return_value=None),
    ):
        client_inst = AsyncMock()
        client_inst.fetch_session.return_value = (
            "127.0.0.1",
            {"session_token": None, "is_logged_in": False},
        )
        client_inst.fetch_qr_code.return_value = (
            "127.0.0.1",
            "data:image/png;base64,abc",
            False,
        )
        mock_client_cls.return_value = client_inst

        res_qr = await flow.async_step_addon_scan(
            user_input={CONF_PHONE_NUMBER: "+49123456789", "pin": ""}
        )
        assert res_qr["type"] == "form"
        assert res_qr["step_id"] == "addon_qr"
        assert (
            res_qr["description_placeholders"]["qr_image"]
            == "data:image/png;base64,abc"
        )


@pytest.mark.asyncio
async def test_config_flow_reauth_manual_option_updates_entry(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Verify reauth_confirm manual option updates entry to manual mode with token."""
    from unittest.mock import AsyncMock

    from custom_components.traderepublic.config_flow import TradeRepublicConfigFlow
    from custom_components.traderepublic.const import (
        AUTH_MODE_MANUAL,
        CONF_AUTH_MODE,
        CONF_PHONE_NUMBER,
        CONF_SESSION_TOKEN,
    )

    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={**mock_config_entry.data, CONF_AUTH_MODE: "addon"},
    )
    flow = TradeRepublicConfigFlow()
    flow.hass = hass
    flow.context = {"entry_id": mock_config_entry.entry_id}

    res_manual_form = await flow.async_step_reauth_confirm(
        user_input={"reauth_action": "manual"}
    )
    assert res_manual_form["type"] == "form"
    assert res_manual_form["step_id"] == "manual"

    with (
        patch(
            "custom_components.traderepublic.config_flow.TradeRepublicAPIClient"
        ) as mock_api_cls,
        patch.object(hass.config_entries, "async_reload", new=AsyncMock()),
    ):
        api_inst = AsyncMock()
        api_inst.verify_session.return_value = True
        mock_api_cls.return_value = api_inst

        res_done = await flow.async_step_manual(
            user_input={
                CONF_PHONE_NUMBER: "+49123456789",
                "pin": "",
                CONF_SESSION_TOKEN: "manual_jwt_tok",
            }
        )
        assert res_done["type"] == "abort"
        assert res_done["reason"] == "reauth_successful"
        assert mock_config_entry.data[CONF_AUTH_MODE] == AUTH_MODE_MANUAL
        assert mock_config_entry.data[CONF_SESSION_TOKEN] == "manual_jwt_tok"


@pytest.mark.asyncio
async def test_config_flow_reauth_confirm_no_session_defaults_to_in_ha(
    hass: HomeAssistant,
) -> None:
    """Test reauth_confirm shows reauth_confirm_no_session and defaults to in_ha when addon has no active session."""
    from unittest.mock import AsyncMock

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.traderepublic.config_flow import TradeRepublicConfigFlow
    from custom_components.traderepublic.const import (
        AUTH_MODE_ADDON,
        CONF_ADDON_HOST,
        CONF_ADDON_PORT,
        CONF_AUTH_MODE,
        DOMAIN,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_AUTH_MODE: AUTH_MODE_ADDON,
            CONF_ADDON_HOST: "edfe50eb-traderepublic",
            CONF_ADDON_PORT: 8095,
        },
    )
    entry.add_to_hass(hass)

    flow = TradeRepublicConfigFlow()
    flow.hass = hass
    flow.context = {"entry_id": entry.entry_id}

    with patch(
        "custom_components.traderepublic.config_flow.AddonClient"
    ) as mock_client_cls:
        client_instance = AsyncMock()
        client_instance.fetch_session.return_value = (
            "edfe50eb-traderepublic",
            {"session_token": "expired_tok", "is_logged_in": False},
        )
        mock_client_cls.return_value = client_instance

        res = await flow.async_step_reauth_confirm()
        assert res["type"] == "form"
        assert res["step_id"] == "reauth_confirm_no_session"
        assert res["description_placeholders"] == {
            "addon_host": "edfe50eb-traderepublic",
            "addon_port": "8095",
        }
        schema_keys = list(res["data_schema"].schema.keys())
        assert schema_keys[0].default() == "in_ha"


@pytest.mark.asyncio
async def test_config_flow_reauth_confirm_active_session_syncs(
    hass: HomeAssistant,
) -> None:
    """Test reauth_confirm defaults to sync and updates entry when addon has an active session."""
    from unittest.mock import AsyncMock

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.traderepublic.config_flow import TradeRepublicConfigFlow
    from custom_components.traderepublic.const import (
        AUTH_MODE_ADDON,
        CONF_ADDON_HOST,
        CONF_ADDON_PORT,
        CONF_AUTH_MODE,
        CONF_SESSION_TOKEN,
        DOMAIN,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_AUTH_MODE: AUTH_MODE_ADDON,
            CONF_ADDON_HOST: "edfe50eb-traderepublic",
            CONF_ADDON_PORT: 8095,
            CONF_SESSION_TOKEN: "old_tok",
        },
    )
    entry.add_to_hass(hass)

    flow = TradeRepublicConfigFlow()
    flow.hass = hass
    flow.context = {"entry_id": entry.entry_id}

    with (
        patch(
            "custom_components.traderepublic.config_flow.AddonClient"
        ) as mock_client_cls,
        patch.object(hass.config_entries, "async_reload", new=AsyncMock()),
    ):
        client_instance = AsyncMock()
        client_instance.fetch_session.return_value = (
            "edfe50eb-traderepublic",
            {
                "session_token": "fresh_tok",
                "phone_number": "+491701234567",
                "is_logged_in": True,
            },
        )
        mock_client_cls.return_value = client_instance

        res = await flow.async_step_reauth_confirm()
        assert res["type"] == "form"
        assert res["step_id"] == "reauth_confirm"
        schema_keys = list(res["data_schema"].schema.keys())
        assert schema_keys[0].default() == "sync"

        res_sync = await flow.async_step_reauth_confirm(
            user_input={"reauth_action": "sync"}
        )
        assert res_sync["type"] == "abort"
        assert res_sync["reason"] == "reauth_successful"
        assert entry.data[CONF_SESSION_TOKEN] == "fresh_tok"
