"""Config flow for Trade Republic integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from .api import (
    AddonClient,
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
        self._addon_2fa_timed_out: bool = False

    async def async_step_hassio(  # type: ignore[override]
        self, discovery_info: HassioServiceInfo
    ) -> ConfigFlowResult:
        """Handle Home Assistant Supervisor auto-discovery."""
        _LOGGER.info(
            "Supervisor auto-discovered Trade Republic Addon: %s", discovery_info
        )
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
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
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
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

                if phone:
                    self._phone_number = phone

                # If token exists and Addon marks session active, create entry directly
                if token and is_logged_in:
                    clean_tok = token.strip().strip('"').strip("'")
                    entry = self.hass.config_entries.async_get_entry(
                        self.context.get("entry_id", "")
                    )
                    if entry:
                        self.hass.config_entries.async_update_entry(
                            entry,
                            data={
                                **entry.data,
                                CONF_PHONE_NUMBER: phone
                                or entry.data.get(CONF_PHONE_NUMBER, ""),
                                CONF_SESSION_TOKEN: clean_tok,
                                CONF_AUTH_MODE: AUTH_MODE_ADDON,
                                CONF_ADDON_HOST: candidate,
                                CONF_ADDON_PORT: port,
                            },
                        )
                        await self.hass.config_entries.async_reload(entry.entry_id)
                        return self.async_abort(reason="reauth_successful")

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

        errors["base"] = "cannot_connect_addon"

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
                            err_raw = str(data.get("error", "")).lower()
                            if (
                                "missing_required_header" in err_raw
                                or "header" in err_raw
                            ):
                                # Add-on is missing the X-aws-waf-token in its TR API call.
                                # This is an add-on-side bug — the integration cannot fix it.
                                errors["base"] = "addon_api_error"
                            elif (
                                "invalid" in err_raw
                                or "pin" in err_raw
                                or "number" in err_raw
                            ):
                                errors["base"] = "invalid_auth"
                            else:
                                errors["base"] = "invalid_auth"
                        elif resp.status == 426:
                            # TR returned 426 CLIENT_VERSION_OUTDATED for the v1 login endpoint.
                            # The add-on needs to be updated to use the v2 push-approval flow.
                            errors["base"] = "addon_api_outdated"
                        elif resp.status == 405:
                            # AWS WAF rejected the request (missing/invalid WAF token).
                            errors["base"] = "addon_api_error"
                        else:
                            _LOGGER.error(
                                "Trade Republic App returned unexpected status %s for login/init",
                                resp.status,
                            )
                            errors["base"] = "addon_api_error"
                except aiohttp.ClientConnectorError as exc:
                    _LOGGER.error(
                        "Cannot reach Trade Republic App at %s:%s: %s",
                        self._addon_host,
                        self._addon_port,
                        exc,
                    )
                    errors["base"] = "cannot_connect_addon"
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.error("Failed to init login on Trade Republic App: %s", exc)
                    errors["base"] = "cannot_connect_addon"

        return self.async_show_form(
            step_id="addon_login",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PHONE_NUMBER, default=self._phone_number or ""
                    ): str,
                    vol.Required(CONF_PIN, default=self._pin or ""): str,
                }
            ),
            errors=errors,
        )

    async def async_step_addon_2fa(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Wait for in-app approval on the Trade Republic smartphone app.

        Trade Republic deprecated the v1 4-digit-code flow (now returns 426
        CLIENT_VERSION_OUTDATED). The current flow is v2 push-approval only:
        the user must approve the login prompt in the TR mobile app. There is
        no code to enter.
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            import aiohttp

            if self._addon_2fa_timed_out:
                # Session expired — re-initiate login automatically and show the
                # 2FA waiting screen again so the user can approve the new prompt.
                self._addon_2fa_timed_out = False
                if self._phone_number and self._pin:
                    url_init = f"http://{self._addon_host}:{self._addon_port}/api/v1/login/init"
                    try:
                        async with (
                            aiohttp.ClientSession() as session,
                            session.post(
                                url_init,
                                json={
                                    "phone_number": self._phone_number,
                                    "pin": self._pin,
                                },
                                timeout=aiohttp.ClientTimeout(total=20),
                            ) as resp,
                        ):
                            if resp.status == 200:
                                data = await resp.json()
                                if data.get("success"):
                                    return self.async_show_form(
                                        step_id="addon_2fa",
                                        data_schema=vol.Schema({}),
                                        errors={},
                                    )
                                _LOGGER.warning(
                                    "Re-initiate login after timeout returned error: %s",
                                    data.get("error"),
                                )
                            elif resp.status == 426:
                                errors["base"] = "addon_api_outdated"
                                return self.async_show_form(
                                    step_id="addon_2fa",
                                    data_schema=vol.Schema({}),
                                    errors=errors,
                                )
                    except Exception as exc:  # noqa: BLE001
                        _LOGGER.error("Failed to restart login after timeout: %s", exc)
                return await self.async_step_addon_login()

            addon_client = AddonClient(
                default_host=self._addon_host, default_port=self._addon_port
            )
            candidate_hosts = addon_client.get_candidate_hosts(self._addon_host)
            try:
                async with aiohttp.ClientSession() as http_session:
                    token: str | None = None

                    # Poll the add-on's verify endpoint across candidate hosts.
                    # The add-on polls TR internally and returns the token once the
                    # user has approved the login in the TR mobile app.
                    for attempt in range(4):
                        for host in candidate_hosts:
                            url = (
                                f"http://{host}:{self._addon_port}/api/v1/login/verify"
                            )
                            session_url = (
                                f"http://{host}:{self._addon_port}/api/v1/session"
                            )
                            try:
                                async with http_session.post(
                                    url,
                                    json={"code": ""},
                                    timeout=aiohttp.ClientTimeout(total=5),
                                ) as resp:
                                    if resp.status == 200:
                                        data = await resp.json()
                                        token = data.get("session_token")
                                        if token:
                                            self._addon_host = host
                                            break
                                        err_msg = str(data.get("error", "")).lower()
                                        if (
                                            "timeout" in err_msg
                                            or "expired" in err_msg
                                            or "2 minutes" in err_msg
                                        ):
                                            self._addon_2fa_timed_out = True
                                            errors["base"] = "timeout_expired"
                                            break
                                        if (
                                            "missing_required_header" in err_msg
                                            or "header" in err_msg
                                        ):
                                            errors["base"] = "addon_api_error"
                                            break
                                    elif resp.status == 426:
                                        errors["base"] = "addon_api_outdated"
                                        break
                                    elif resp.status in (405, 422):
                                        errors["base"] = "addon_api_error"
                                        break
                            except Exception, asyncio.CancelledError:  # noqa: BLE001
                                pass

                            if token or errors:
                                break

                            # Fallback: check if the add-on already has an active session
                            try:
                                async with http_session.get(
                                    session_url,
                                    timeout=aiohttp.ClientTimeout(total=2),
                                ) as s_resp:
                                    if s_resp.status == 200:
                                        s_data = await s_resp.json()
                                        if s_data.get("session_token") and s_data.get(
                                            "is_logged_in", True
                                        ):
                                            token = s_data.get("session_token")
                                            self._addon_host = host
                                            break
                            except Exception, asyncio.CancelledError:  # noqa: BLE001
                                pass

                        if token or errors:
                            break

                        if attempt < 3:
                            await asyncio.sleep(1.5)

                    if token:
                        phone = self._phone_number or "+49_addon_user"
                        entry = self.hass.config_entries.async_get_entry(
                            self.context.get("entry_id", "")
                        )
                        if entry:
                            try:
                                from homeassistant.helpers import issue_registry as ir

                                ir.async_delete_issue(
                                    self.hass,
                                    DOMAIN,
                                    f"reauth_required_{entry.entry_id}",
                                )
                            except Exception:  # noqa: BLE001
                                pass

                            self.hass.config_entries.async_update_entry(
                                entry,
                                data={
                                    **entry.data,
                                    CONF_PHONE_NUMBER: phone,
                                    CONF_SESSION_TOKEN: token,
                                    CONF_AUTH_MODE: AUTH_MODE_ADDON,
                                    CONF_ADDON_HOST: self._addon_host,
                                    CONF_ADDON_PORT: self._addon_port,
                                },
                            )
                            await self.hass.config_entries.async_reload(entry.entry_id)
                            return self.async_abort(reason="reauth_successful")

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

                    if not errors:
                        errors["base"] = "approval_pending"
            except aiohttp.ClientConnectorError as exc:
                _LOGGER.error(
                    "Cannot reach Trade Republic App at %s:%s during 2FA: %s",
                    self._addon_host,
                    self._addon_port,
                    exc,
                )
                errors["base"] = "cannot_connect_addon"
            except Exception as exc:  # noqa: BLE001
                _LOGGER.error("Failed to verify 2FA on Trade Republic App: %s", exc)
                errors["base"] = "cannot_connect_addon"

        return self.async_show_form(
            step_id="addon_2fa",
            data_schema=vol.Schema({}),
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

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a reconfiguration flow initialized by the user."""
        entry = self.hass.config_entries.async_get_entry(
            self.context.get("entry_id", "")
        )
        if entry:
            self._phone_number = entry.data.get(CONF_PHONE_NUMBER)
        return await self.async_step_reauth_confirm(user_input)

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

                addon_client = AddonClient(
                    default_host=self._addon_host, default_port=self._addon_port
                )
                try:
                    candidate, data = await addon_client.fetch_session(
                        preferred_host=self._addon_host, port=self._addon_port
                    )
                    if candidate and data:
                        token = data.get("session_token")
                        is_logged_in = data.get("is_logged_in", True)
                        if token and is_logged_in and entry:
                            # In Add-on mode, the Add-on is the single source of truth and manages
                            # the WebSocket. We trust the Addon's validated session rather than
                            # opening a competing connection from HA that TR could reject/drop.
                            try:
                                from homeassistant.helpers import issue_registry as ir

                                ir.async_delete_issue(
                                    self.hass,
                                    DOMAIN,
                                    f"reauth_required_{entry.entry_id}",
                                )
                            except Exception:  # noqa: BLE001
                                pass

                            self.hass.config_entries.async_update_entry(
                                entry,
                                data={
                                    **entry.data,
                                    CONF_SESSION_TOKEN: token,
                                    CONF_ADDON_HOST: candidate,
                                },
                            )
                            await self.hass.config_entries.async_reload(entry.entry_id)
                            return self.async_abort(reason="reauth_successful")
                    # If no valid session in addon, forward user directly to in-HA login form
                    return await self.async_step_addon_login()
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.error(
                        "Failed to connect to Trade Republic App during reauth: %s", exc
                    )
                    return await self.async_step_addon_login()
                finally:
                    await addon_client.close()

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
        auth_mode = self.config_entry.data.get(CONF_AUTH_MODE, AUTH_MODE_ADDON)
        min_interval = 15 if auth_mode == AUTH_MODE_ADDON else MIN_SCAN_INTERVAL
        default_interval = 60 if auth_mode == AUTH_MODE_ADDON else DEFAULT_SCAN_INTERVAL

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
                        CONF_SCAN_INTERVAL, default_interval
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
                                CONF_SCAN_INTERVAL, default_interval
                            ),
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=min_interval)),
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
