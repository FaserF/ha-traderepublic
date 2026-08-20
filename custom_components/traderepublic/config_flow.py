"""Config flow for Trade Republic integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from .addon_client import AddonClient
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

    async def async_step_hassio(  # type: ignore[override]
        self, discovery_info: HassioServiceInfo
    ) -> ConfigFlowResult:
        """Handle Home Assistant Supervisor auto-discovery."""
        _LOGGER.info(
            "Supervisor auto-discovered Trade Republic Addon: %s", discovery_info
        )
        await self.async_set_unique_id("traderepublic_addon")
        self._abort_if_unique_id_configured()
        self._auth_mode = AUTH_MODE_ADDON
        self._addon_host = discovery_info.config.get("host", DEFAULT_ADDON_HOST)
        self._addon_port = int(discovery_info.config.get("port", DEFAULT_ADDON_PORT))
        return await self._async_connect_addon(self._addon_host, self._addon_port)

    async def async_step_discovery(
        self, discovery_info: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle generic discovery of Trade Republic addon."""
        _LOGGER.info("Discovered Trade Republic Addon: %s", discovery_info)
        await self.async_set_unique_id("traderepublic_addon")
        self._abort_if_unique_id_configured()
        self._auth_mode = AUTH_MODE_ADDON
        self._addon_host = discovery_info.get("host", DEFAULT_ADDON_HOST)
        self._addon_port = int(discovery_info.get("port", DEFAULT_ADDON_PORT))
        return await self._async_connect_addon(self._addon_host, self._addon_port)

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
        addon_client = AddonClient(default_host=host, default_port=port)
        try:
            candidate, data = await addon_client.fetch_session(
                preferred_host=host, port=port
            )
            if candidate and data:
                token = data.get("session_token")
                phone = data.get("phone_number") or ""
                is_logged_in = data.get("is_logged_in", True)
                token_verified = data.get("token_verified", False)

                if phone:
                    self._phone_number = phone

                # If token exists and Addon marks session active, test validity before creating entry
                if token and is_logged_in:
                    clean_tok = token.strip().strip('"').strip("'")
                    is_valid = token_verified
                    if not is_valid:
                        test_client = TradeRepublicAPIClient(phone, "", clean_tok)
                        try:
                            await test_client.connect()
                            is_valid = await test_client.verify_session()
                            await test_client.close()
                        except Exception as test_err:  # noqa: BLE001
                            _LOGGER.info(
                                "Addon token verification failed (%s) -> prompting login in HA",
                                test_err,
                            )
                            is_valid = False

                    if is_valid:
                        # Addon is logged in and session is verified -> complete setup!
                        await self.async_set_unique_id(
                            phone.lower() if phone else "traderepublic"
                        )
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title=f"Trade Republic ({phone})"
                            if phone
                            else "Trade Republic",
                            data={
                                CONF_PHONE_NUMBER: phone,
                                CONF_PIN: "",
                                CONF_SESSION_TOKEN: clean_tok,
                                CONF_AUTH_MODE: AUTH_MODE_ADDON,
                                CONF_ADDON_HOST: candidate,
                                CONF_ADDON_PORT: port,
                            },
                        )

                # Addon reachable but session missing or expired -> seamlessly forward to login prompt in HA
                self._addon_host = candidate
                self._addon_port = port
                return await self.async_step_addon_login()
        finally:
            await addon_client.close()

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

    async def async_step_addon_login(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Trigger login on Trade Republic App directly from HA integration."""
        errors: dict[str, str] = {}
        if user_input is not None:
            raw_phone = (
                user_input.get(CONF_PHONE_NUMBER, "")
                .strip()
                .replace(" ", "")
                .replace("-", "")
                .replace("/", "")
            )
            if raw_phone.startswith("00"):
                self._phone_number = "+" + raw_phone[2:]
            elif raw_phone.startswith("+"):
                self._phone_number = raw_phone
            elif raw_phone.startswith("0") and len(raw_phone) >= 9:
                self._phone_number = "+49" + raw_phone[1:]
            else:
                self._phone_number = "+" + raw_phone

            digits_only = "".join(filter(str.isdigit, self._phone_number))
            if not self._phone_number.startswith("+") or not (
                7 <= len(digits_only) <= 15
            ):
                errors[CONF_PHONE_NUMBER] = "invalid_phone"

            self._pin = (user_input.get(CONF_PIN) or "").strip()
            if not self._pin.isdigit() or not (4 <= len(self._pin) <= 6):
                errors[CONF_PIN] = "invalid_pin"

            if not errors:
                import aiohttp

                url = f"http://{self._addon_host}:{self._addon_port}/api/v1/login/init"
                try:
                    async with (
                        aiohttp.ClientSession() as session,
                        session.post(
                            url,
                            json={"phone_number": self._phone_number, "pin": self._pin},
                            timeout=aiohttp.ClientTimeout(total=20),
                        ) as resp,
                    ):
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("success"):
                                return await self.async_step_addon_2fa()
                            errors["base"] = "invalid_auth"
                        else:
                            errors["base"] = "cannot_connect"
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.error("Failed to init login on Trade Republic App: %s", exc)
                    errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="addon_login",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PHONE_NUMBER, default=self._phone_number or ""
                    ): str,
                    vol.Required(CONF_PIN): str,
                }
            ),
            errors=errors,
        )

    async def async_step_addon_2fa(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Verify 2FA or check In-App approval directly from HA integration."""
        errors: dict[str, str] = {}
        if user_input is not None:
            code = user_input.get("code", "").strip()
            import aiohttp

            url = f"http://{self._addon_host}:{self._addon_port}/api/v1/login/verify"
            try:
                async with (
                    aiohttp.ClientSession() as session,
                    session.post(
                        url,
                        json={"code": code},
                        timeout=aiohttp.ClientTimeout(total=20),
                    ) as resp,
                ):
                    if resp.status == 200:
                        data = await resp.json()
                        token = data.get("session_token")
                        if token:
                            phone = self._phone_number or "+49_addon_user"
                            await self.async_set_unique_id(phone.lower())
                            self._abort_if_unique_id_configured()
                            return self.async_create_entry(
                                title=f"Trade Republic ({phone})",
                                data={
                                    CONF_PHONE_NUMBER: phone,
                                    CONF_PIN: "",
                                    CONF_SESSION_TOKEN: token,
                                    CONF_AUTH_MODE: AUTH_MODE_ADDON,
                                    CONF_ADDON_HOST: self._addon_host,
                                    CONF_ADDON_PORT: self._addon_port,
                                },
                            )
                        errors["base"] = "invalid_code"
                    else:
                        errors["base"] = "invalid_code"
            except Exception as exc:  # noqa: BLE001
                _LOGGER.error("Failed to verify 2FA on Trade Republic App: %s", exc)
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="addon_2fa",
            data_schema=vol.Schema(
                {
                    vol.Optional("code", default=""): str,
                }
            ),
            errors=errors,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle Step 1: Select connection method."""
        if user_input is not None:
            self._auth_mode = user_input.get(CONF_AUTH_MODE, AUTH_MODE_ADDON)
            if self._auth_mode == AUTH_MODE_ADDON:
                return await self._async_connect_addon(
                    self._addon_host, self._addon_port
                )
            return await self.async_step_manual()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_AUTH_MODE, default=AUTH_MODE_ADDON): vol.In(
                        {
                            AUTH_MODE_ADDON: "Trade Republic Home Assistant App (Recommended - Auto Keep-Alive)",
                            AUTH_MODE_MANUAL: "Manual Credentials / Token (Classic Mode)",
                        }
                    ),
                }
            ),
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle Step 2 (Manual Mode): Enter phone, PIN and optional session token."""
        errors: dict[str, str] = {}

        if user_input is not None:
            raw_phone = (
                (user_input.get(CONF_PHONE_NUMBER) or "")
                .strip()
                .replace(" ", "")
                .replace("-", "")
                .replace("/", "")
            )
            if raw_phone.startswith("00"):
                self._phone_number = "+" + raw_phone[2:]
            elif raw_phone.startswith("+"):
                self._phone_number = raw_phone
            elif raw_phone.startswith("0") and len(raw_phone) >= 9:
                self._phone_number = "+49" + raw_phone[1:]
            else:
                self._phone_number = "+" + raw_phone

            self._pin = (user_input.get(CONF_PIN) or "").strip()
            session_token = user_input.get(CONF_SESSION_TOKEN)

            digits_only = "".join(filter(str.isdigit, self._phone_number))
            if not self._phone_number.startswith("+") or not (
                7 <= len(digits_only) <= 15
            ):
                errors[CONF_PHONE_NUMBER] = "invalid_phone"
            else:
                await self.async_set_unique_id(self._phone_number.lower())
                self._abort_if_unique_id_configured()

                if self._pin and (
                    not self._pin.isdigit() or not (4 <= len(self._pin) <= 6)
                ):
                    errors[CONF_PIN] = "invalid_pin"

                if not errors:
                    clean_token = (
                        session_token.strip().strip('"').strip("'")
                        if session_token
                        else None
                    )
                    self._client = TradeRepublicAPIClient(
                        self._phone_number, self._pin or "", clean_token
                    )
                    try:
                        await self._client.connect()
                        if clean_token:
                            if await self._client.verify_session():
                                return self.async_create_entry(
                                    title=self._phone_number or "Trade Republic",
                                    data={
                                        CONF_PHONE_NUMBER: self._phone_number,
                                        CONF_PIN: self._pin or "",
                                        CONF_SESSION_TOKEN: clean_token,
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
                        if not clean_token:
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
            step_id="manual",
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
        entry = self.hass.config_entries.async_get_entry(
            self.context.get("entry_id", "")
        )
        auth_mode = (
            entry.data.get(CONF_AUTH_MODE, AUTH_MODE_MANUAL)
            if entry
            else AUTH_MODE_MANUAL
        )
        self._addon_host = (
            entry.data.get(CONF_ADDON_HOST, DEFAULT_ADDON_HOST)
            if entry
            else DEFAULT_ADDON_HOST
        )
        self._addon_port = (
            entry.data.get(CONF_ADDON_PORT, DEFAULT_ADDON_PORT)
            if entry
            else DEFAULT_ADDON_PORT
        )

        # If in App mode, try auto-refreshing from App or forward directly to in-HA login flow
        if auth_mode == AUTH_MODE_ADDON:
            if user_input is not None:
                action = user_input.get("reauth_action", "refresh")
                if action == "login":
                    return await self.async_step_addon_login()

                import aiohttp

                url = f"http://{self._addon_host}:{self._addon_port}/api/v1/session"
                try:
                    async with (
                        aiohttp.ClientSession() as session,
                        session.get(
                            url, timeout=aiohttp.ClientTimeout(total=5)
                        ) as resp,
                    ):
                        if resp.status == 200:
                            data = await resp.json()
                            token = data.get("session_token")
                            if token and entry:
                                # Verify token is actually valid before accepting it
                                client = TradeRepublicAPIClient(
                                    phone_number=entry.data.get(CONF_PHONE_NUMBER, ""),
                                    pin=entry.data.get(CONF_PIN, ""),
                                    session_token=token,
                                )
                                try:
                                    valid = await client.verify_session()
                                except Exception:  # noqa: BLE001
                                    valid = False
                                if not valid:
                                    _LOGGER.warning(
                                        "Addon session token is present but invalid — prompting re-login"
                                    )
                                    return await self.async_step_addon_login()
                                self.hass.config_entries.async_update_entry(
                                    entry,
                                    data={**entry.data, CONF_SESSION_TOKEN: token},
                                )
                                await self.hass.config_entries.async_reload(
                                    entry.entry_id
                                )
                                return self.async_abort(reason="reauth_successful")
                        # If no valid session in addon, forward user directly to in-HA login form
                        return await self.async_step_addon_login()
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.error(
                        "Failed to connect to Trade Republic App during reauth: %s", exc
                    )
                    return await self.async_step_addon_login()

            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=vol.Schema(
                    {
                        vol.Required("reauth_action", default="refresh"): vol.In(
                            {
                                "refresh": "Check/Sync Session from Trade Republic App",
                                "login": "Log in again directly within Home Assistant",
                            }
                        ),
                    }
                ),
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
            if user_input.get("trigger_reauth"):
                return await self.hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={
                        "source": config_entries.SOURCE_REAUTH,
                        "entry_id": self.config_entry.entry_id,
                    },
                    data=self.config_entry.data,
                )
            return self.async_create_entry(
                title="",
                data={
                    CONF_SCAN_INTERVAL: user_input.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                    CONF_INTEREST_RATE: user_input.get(
                        CONF_INTEREST_RATE, DEFAULT_INTEREST_RATE
                    ),
                },
            )

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
                    vol.Optional("trigger_reauth", default=False): bool,
                }
            ),
        )
