"""Config flow for Trade Republic integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback

from .api import (
    CannotConnectError,
    InvalidAuthError,
    OTPRequiredError,
    TradeRepublicAPIClient,
)
from .const import (
    AUTH_MODE_ADDON,
    AUTH_MODE_MANUAL,
    CONF_ADDON_HOST,
    CONF_ADDON_PORT,
    CONF_AUTH_MODE,
    CONF_INTEREST_RATE,
    CONF_PHONE_NUMBER,
    CONF_PIN,
    CONF_SCAN_INTERVAL,
    CONF_SESSION_TOKEN,
    DEFAULT_ADDON_HOST,
    DEFAULT_ADDON_PORT,
    DEFAULT_INTEREST_RATE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class TradeRepublicConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Trade Republic."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> TradeRepublicOptionsFlow:
        """Return the options flow handler."""
        return TradeRepublicOptionsFlow()

    def __init__(self) -> None:
        """Initialize the flow."""
        self._phone_number: str | None = None
        self._pin: str | None = None
        self._client: TradeRepublicAPIClient | None = None
        self._auth_mode: str = AUTH_MODE_MANUAL
        self._addon_host: str = DEFAULT_ADDON_HOST
        self._addon_port: int = DEFAULT_ADDON_PORT

    async def async_step_discovery(
        self, discovery_info: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle discovery of Trade Republic addon."""
        _LOGGER.info("Discovered Trade Republic Addon: %s", discovery_info)
        self._auth_mode = AUTH_MODE_ADDON
        self._addon_host = discovery_info.get("host", DEFAULT_ADDON_HOST)
        self._addon_port = int(discovery_info.get("port", DEFAULT_ADDON_PORT))
        return await self.async_step_addon_confirm()

    async def async_step_addon_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm setup via discovered Trade Republic Add-on."""
        errors: dict[str, str] = {}
        if user_input is not None:
            return await self._async_connect_addon(self._addon_host, self._addon_port)

        return self.async_show_form(
            step_id="addon_confirm",
            description_placeholders={"host": self._addon_host},
            errors=errors,
        )

    async def async_step_addon(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure via Trade Republic Add-on manually."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._addon_host = user_input.get(CONF_ADDON_HOST, DEFAULT_ADDON_HOST)
            self._addon_port = int(user_input.get(CONF_ADDON_PORT, DEFAULT_ADDON_PORT))
            return await self._async_connect_addon(self._addon_host, self._addon_port)

        return self.async_show_form(
            step_id="addon",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDON_HOST, default=DEFAULT_ADDON_HOST): str,
                    vol.Required(CONF_ADDON_PORT, default=DEFAULT_ADDON_PORT): int,
                }
            ),
            errors=errors,
        )

    async def _async_connect_addon(self, host: str, port: int) -> ConfigFlowResult:
        """Connect to the Trade Republic Addon and fetch session token."""
        errors: dict[str, str] = {}
        import aiohttp

        url = f"http://{host}:{port}/api/v1/session"
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp,
            ):
                if resp.status == 200:
                    data = await resp.json()
                    token = data.get("session_token")
                    phone = data.get("phone_number") or "+49_addon_user"

                    if token:
                        await self.async_set_unique_id(phone.lower())
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title=f"Trade Republic ({phone})",
                            data={
                                CONF_PHONE_NUMBER: phone,
                                CONF_PIN: "",
                                CONF_SESSION_TOKEN: token,
                                CONF_AUTH_MODE: AUTH_MODE_ADDON,
                                CONF_ADDON_HOST: host,
                                CONF_ADDON_PORT: port,
                            },
                        )
                    errors["base"] = "addon_no_session"
                else:
                    errors["base"] = "addon_no_session"

        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("Failed to connect to Trade Republic addon at %s: %s", url, exc)
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="addon",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDON_HOST, default=host): str,
                    vol.Required(CONF_ADDON_PORT, default=port): int,
                }
            ),
            errors=errors,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle initial step to choose authentication method or direct manual login."""
        errors: dict[str, str] = {}

        if user_input is not None:
            auth_mode = user_input.get(CONF_AUTH_MODE, AUTH_MODE_MANUAL)
            if auth_mode == AUTH_MODE_ADDON:
                return await self.async_step_addon()

            self._phone_number = user_input.get(CONF_PHONE_NUMBER)
            self._pin = user_input.get(CONF_PIN)
            session_token = user_input.get(CONF_SESSION_TOKEN)

            if not self._phone_number:
                errors[CONF_PHONE_NUMBER] = "invalid_phone"
            else:
                await self.async_set_unique_id(self._phone_number.lower())
                self._abort_if_unique_id_configured()

                if self._pin:
                    pin_stripped = self._pin.strip()
                    if not pin_stripped.isdigit() or not (4 <= len(pin_stripped) <= 6):
                        errors[CONF_PIN] = "invalid_pin"

                if not errors:
                    self._client = TradeRepublicAPIClient(
                        self._phone_number, self._pin or "", session_token
                    )
                    try:
                        await self._client.connect()
                        if session_token:
                            if await self._client.verify_session():
                                return self.async_create_entry(
                                    title=self._phone_number or "Trade Republic",
                                    data={
                                        CONF_PHONE_NUMBER: self._phone_number,
                                        CONF_PIN: self._pin or "",
                                        CONF_SESSION_TOKEN: session_token,
                                        CONF_AUTH_MODE: AUTH_MODE_MANUAL,
                                    },
                                )
                            else:
                                errors["base"] = "invalid_auth"
                        else:
                            if not self._pin:
                                errors["base"] = "invalid_auth"
                            else:
                                await self._client.login_step1()
                    except OTPRequiredError:
                        return await self.async_step_mfa()
                    except CannotConnectError:
                        errors["base"] = "cannot_connect"
                    except InvalidAuthError:
                        errors["base"] = "invalid_auth"
                    except Exception as exc:  # noqa: BLE001
                        _LOGGER.error("Unexpected error during login step 1: %s", exc)
                        errors["base"] = "unknown"
                    else:
                        if not session_token:
                            return self.async_create_entry(
                                title=self._phone_number or "Trade Republic",
                                data={
                                    CONF_PHONE_NUMBER: self._phone_number,
                                    CONF_PIN: self._pin or "",
                                    CONF_SESSION_TOKEN: self._client.session_token,
                                    CONF_AUTH_MODE: AUTH_MODE_MANUAL,
                                },
                            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_AUTH_MODE, default=AUTH_MODE_ADDON): vol.In(
                        {
                            AUTH_MODE_ADDON: "Trade Republic Add-on (Recommended, Keeps Session Alive)",
                            AUTH_MODE_MANUAL: "Manual Token / Credentials",
                        }
                    ),
                    vol.Optional(CONF_PHONE_NUMBER): str,
                    vol.Optional(CONF_PIN): str,
                    vol.Optional(CONF_SESSION_TOKEN): str,
                }
            ),
            errors=errors,
        )


    async def async_step_mfa(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the multi-factor/OTP code verification step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            code = user_input["code"]
            if self._client:
                try:
                    session_token = await self._client.login_step2(code)
                    await self._client.close()
                    if "entry_id" in self.context:
                        entry = self.hass.config_entries.async_get_entry(
                            self.context["entry_id"]
                        )
                        if entry:
                            self.hass.config_entries.async_update_entry(
                                entry,
                                data={
                                    **entry.data,
                                    CONF_PIN: self._pin or "",
                                    CONF_SESSION_TOKEN: session_token,
                                },
                            )
                            await self.hass.config_entries.async_reload(entry.entry_id)
                            return self.async_abort(reason="reauth_successful")
                    return self.async_create_entry(
                        title=self._phone_number or "Trade Republic",
                        data={
                            CONF_PHONE_NUMBER: self._phone_number,
                            CONF_PIN: self._pin or "",
                            CONF_SESSION_TOKEN: session_token,
                        },
                    )
                except InvalidAuthError:
                    errors["base"] = "invalid_code"
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.error("Unexpected error during MFA verification: %s", exc)
                    errors["base"] = "unknown"

        return self.async_show_form(
            step_id="mfa",
            data_schema=vol.Schema({vol.Required("code"): str}),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauthorization request from the user."""
        self._phone_number = entry_data.get(CONF_PHONE_NUMBER)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauth."""
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context.get("entry_id", ""))
        auth_mode = entry.data.get(CONF_AUTH_MODE, AUTH_MODE_MANUAL) if entry else AUTH_MODE_MANUAL
        addon_host = entry.data.get(CONF_ADDON_HOST, DEFAULT_ADDON_HOST) if entry else DEFAULT_ADDON_HOST
        addon_port = entry.data.get(CONF_ADDON_PORT, DEFAULT_ADDON_PORT) if entry else DEFAULT_ADDON_PORT

        # If in App mode, try auto-refreshing from App first or prompt user to log in to App Web UI
        if auth_mode == AUTH_MODE_ADDON:
            if user_input is not None:
                import aiohttp
                url = f"http://{addon_host}:{addon_port}/api/v1/session"
                try:
                    async with (
                        aiohttp.ClientSession() as session,
                        session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp,
                    ):
                        if resp.status == 200:
                            data = await resp.json()
                            token = data.get("session_token")
                            if token and entry:
                                self.hass.config_entries.async_update_entry(
                                    entry,
                                    data={**entry.data, CONF_SESSION_TOKEN: token},
                                )
                                await self.hass.config_entries.async_reload(entry.entry_id)
                                return self.async_abort(reason="reauth_successful")
                            errors["base"] = "addon_no_session"

                        else:
                            errors["base"] = "addon_no_session"
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.error("Failed to connect to Trade Republic App during reauth: %s", exc)
                    errors["base"] = "cannot_connect"

            return self.async_show_form(
                step_id="reauth_confirm",
                description_placeholders={"host": addon_host},
                errors=errors,
            )

        if user_input is not None:
            self._pin = user_input.get(CONF_PIN)
            session_token = user_input.get(CONF_SESSION_TOKEN)


            # PIN validation check: must be 4-6 digits, only numbers
            if self._pin:
                pin_stripped = self._pin.strip()
                if not pin_stripped.isdigit() or not (4 <= len(pin_stripped) <= 6):
                    errors[CONF_PIN] = "invalid_pin"

            if not errors:
                clean_token = (
                    session_token.strip().strip('"').strip("'")
                    if session_token
                    else None
                )
                self._client = TradeRepublicAPIClient(
                    self._phone_number or "", self._pin or "", clean_token
                )
                try:
                    await self._client.connect()
                    if clean_token:
                        if await self._client.verify_session():
                            entry = self.hass.config_entries.async_get_entry(
                                self.context["entry_id"]
                            )
                            if entry:
                                updated_data = {
                                    **entry.data,
                                    CONF_SESSION_TOKEN: clean_token,
                                }
                                if self._pin:
                                    updated_data[CONF_PIN] = self._pin
                                self.hass.config_entries.async_update_entry(
                                    entry,
                                    data=updated_data,
                                )
                                await self.hass.config_entries.async_reload(
                                    entry.entry_id
                                )
                                return self.async_abort(reason="reauth_successful")
                        else:
                            errors["base"] = "invalid_auth"
                    else:
                        if not self._pin:
                            errors["base"] = "invalid_auth"
                        else:
                            await self._client.login_step1()
                except OTPRequiredError:
                    return await self.async_step_mfa()
                except CannotConnectError:
                    errors["base"] = "cannot_connect"
                except InvalidAuthError:
                    errors["base"] = "invalid_auth"
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.error("Unexpected error during reauth: %s", exc)
                    errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_PIN): str,
                    vol.Optional(CONF_SESSION_TOKEN): str,
                }
            ),
            errors=errors,
        )


class TradeRepublicOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for changing settings."""

    def __init__(self) -> None:
        """Initialize options flow."""
        super().__init__()

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL,
                            self.config_entry.data.get(
                                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                            ),
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)),
                    vol.Optional(
                        CONF_INTEREST_RATE,
                        default=self.config_entry.options.get(
                            CONF_INTEREST_RATE,
                            self.config_entry.data.get(
                                CONF_INTEREST_RATE, DEFAULT_INTEREST_RATE
                            ),
                        ),
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=100.0)),
                }
            ),
        )
