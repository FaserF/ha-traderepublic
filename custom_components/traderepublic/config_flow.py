"""Config flow for Trade Republic integration."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback

from .const import (
    DOMAIN,
    CONF_PHONE_NUMBER,
    CONF_PIN,
    CONF_SESSION_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

from .api import (
    TradeRepublicAPIClient,
    CannotConnectError,
    InvalidAuthError,
    OTPRequiredError,
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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial user credentials step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._phone_number = user_input[CONF_PHONE_NUMBER]
            self._pin = user_input.get(CONF_PIN)
            session_token = user_input.get(CONF_SESSION_TOKEN)

            await self.async_set_unique_id(self._phone_number.lower())
            self._abort_if_unique_id_configured()

            # PIN validation check: must be 4-6 digits, only numbers
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
                        # Verify session token directly
                        if await self._client.verify_session():
                            return self.async_create_entry(
                                title=self._phone_number or "Trade Republic",
                                data={
                                    CONF_PHONE_NUMBER: self._phone_number,
                                    CONF_PIN: self._pin or "",
                                    CONF_SESSION_TOKEN: session_token,
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
                    # Proceed to 2FA verification step
                    return await self.async_step_mfa()
                except CannotConnectError:
                    errors["base"] = "cannot_connect"
                except InvalidAuthError:
                    errors["base"] = "invalid_auth"
                except Exception as exc:
                    _LOGGER.error("Unexpected error during login step 1: %s", exc)
                    errors["base"] = "unknown"
                else:
                    if not session_token:
                        # Directly authenticated (e.g. demo mode)
                        return self.async_create_entry(
                            title=self._phone_number or "Trade Republic",
                            data={
                                CONF_PHONE_NUMBER: self._phone_number,
                                CONF_PIN: self._pin or "",
                                CONF_SESSION_TOKEN: self._client.session_token,
                            },
                        )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PHONE_NUMBER): str,
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
                        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
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
                except Exception as exc:
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

        if user_input is not None:
            self._pin = user_input.get(CONF_PIN)
            session_token = user_input.get(CONF_SESSION_TOKEN)

            # PIN validation check: must be 4-6 digits, only numbers
            if self._pin:
                pin_stripped = self._pin.strip()
                if not pin_stripped.isdigit() or not (4 <= len(pin_stripped) <= 6):
                    errors[CONF_PIN] = "invalid_pin"

            if not errors:
                self._client = TradeRepublicAPIClient(
                    self._phone_number or "", self._pin or "", session_token
                )
                try:
                    await self._client.connect()
                    if session_token:
                        if await self._client.verify_session():
                            entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
                            if entry:
                                self.hass.config_entries.async_update_entry(
                                    entry,
                                    data={
                                        **entry.data,
                                        CONF_PIN: self._pin or "",
                                        CONF_SESSION_TOKEN: session_token,
                                    }
                                )
                                await self.hass.config_entries.async_reload(entry.entry_id)
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
                except Exception as exc:
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
                }
            ),
        )