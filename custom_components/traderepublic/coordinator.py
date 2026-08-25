"""Data Update Coordinator for the Trade Republic integration.

Enforces:
- Random jitter delay (5–30s) before requests.
- Domain-wide asyncio.Lock to serialise fetches.
- Exponential backoff on rate limits / 403 / 429.
- Restart-resistance: last_success persisted via HA Storage.
- Enforced minimum scan interval.
- Strictly read-only operation.
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import storage
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AddonClient, InvalidAuthError, TradeRepublicAPIClient
from .const import (
    AUTH_MODE_ADDON,
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
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class TradeRepublicDataUpdateCoordinator(DataUpdateCoordinator):
    """Manage fetching Trade Republic portfolio metrics."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        config = {**entry.data, **entry.options}
        self.phone_number: str = config[CONF_PHONE_NUMBER]
        self.config_entry = entry

        # Anti-ban state
        self._backoff_until: datetime | None = None
        self._consecutive_failures: int = 0
        self._last_success: datetime | None = None
        self._force_update: bool = False
        self._has_fetched_live: bool = False

        # Persistent storage
        self.store: storage.Store[Any] = storage.Store(
            hass, 1, f"{DOMAIN}_{self.phone_number.replace('+', '')}"
        )

        auth_mode = config.get(CONF_AUTH_MODE, AUTH_MODE_ADDON)
        if auth_mode == AUTH_MODE_ADDON:
            # In Add-on mode, queries are internal Docker network HTTP calls (0 API rate-limit risk)
            # Default to 60s (min 15s) so HA displays fresh live data from the Addon keeper
            configured_interval = config.get(CONF_SCAN_INTERVAL, 60)
            interval_seconds = max(15, configured_interval)
        else:
            # Direct API mode: enforce strict anti-ban intervals (min 10m, default 15m)
            interval_seconds = max(
                MIN_SCAN_INTERVAL,
                config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            )

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"Trade Republic {self.phone_number}",
            update_interval=timedelta(seconds=interval_seconds),
        )

    async def async_load_cache(self) -> None:
        """Load cached data from HA storage for restart-resistance."""
        cache = await self.store.async_load()
        if cache:
            self.data = cache
            if "last_success" in cache:
                try:
                    self._last_success = dt_util.parse_datetime(cache["last_success"])
                except ValueError, TypeError:
                    self._last_success = None
            _LOGGER.debug("Loaded cached Trade Republic data")

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch updated portfolio data."""
        # Check backoff
        if (
            not self._force_update
            and self._backoff_until
            and dt_util.now() < self._backoff_until
        ):
            _LOGGER.debug("Skipping update due to active backoff")
            return self.data

        # Auto-sync token from addon on every cycle/startup if in addon mode (or default)
        auth_mode = self.config_entry.data.get(CONF_AUTH_MODE, AUTH_MODE_ADDON)
        addon_host = self.config_entry.data.get(CONF_ADDON_HOST, DEFAULT_ADDON_HOST)
        addon_port = self.config_entry.data.get(CONF_ADDON_PORT, DEFAULT_ADDON_PORT)
        session_token = self.config_entry.data.get(CONF_SESSION_TOKEN)

        if auth_mode == AUTH_MODE_ADDON:
            addon_client = AddonClient(default_host=addon_host, default_port=addon_port)
            try:
                # Detect active/enabled entity categories in Home Assistant
                requested_categories: list[str] = ["portfolio", "cash"]
                try:
                    from homeassistant.helpers import entity_registry as er

                    registry = er.async_get(self.hass)
                    entry_entities = er.async_entries_for_config_entry(
                        registry, self.config_entry.entry_id
                    )
                    has_card = any(
                        not e.disabled and "card" in (e.unique_id or "").lower()
                        for e in entry_entities
                    )
                    has_savings = any(
                        not e.disabled and "savings" in (e.unique_id or "").lower()
                        for e in entry_entities
                    )
                    has_timeline = any(
                        not e.disabled
                        and (
                            "timeline" in (e.unique_id or "").lower()
                            or "transaction" in (e.unique_id or "").lower()
                        )
                        for e in entry_entities
                    )
                    if has_card:
                        requested_categories.append("card")
                    if has_savings:
                        requested_categories.append("savings")
                    if has_timeline:
                        requested_categories.append("timeline")
                except Exception as ent_err:  # noqa: BLE001
                    _LOGGER.debug("Could not inspect entity registry: %s", ent_err)
                    requested_categories = [
                        "portfolio",
                        "cash",
                        "savings",
                        "card",
                        "timeline",
                    ]

                # 1. Fetch live metrics directly from Addon /api/v1/data with requested categories
                cand, addon_data = await addon_client.fetch_data(
                    preferred_host=addon_host,
                    port=addon_port,
                    requested_categories=requested_categories,
                )
                if cand and addon_data:
                    is_addon_logged_in = addon_data.get("is_logged_in", True)
                    if not is_addon_logged_in:
                        _LOGGER.warning(
                            "Trade Republic Add-on reports session expired — "
                            "raising ConfigEntryAuthFailed to prompt re-authentication."
                        )
                        raise ConfigEntryAuthFailed(
                            "Trade Republic session expired in Add-on. "
                            "Please re-authenticate in the Add-on UI or via Reauth."
                        )

                    payload_data = addon_data.get("data")
                    if (
                        payload_data
                        and isinstance(payload_data, dict)
                        and (
                            payload_data.get("net_value", 0.0) > 0.0
                            or payload_data.get("available_cash", 0.0) > 0.0
                            or payload_data.get("holdings")
                            or "savings_plans_count" in payload_data
                        )
                    ):
                        _LOGGER.debug(
                            "Received complete live metrics directly from Add-on (%s)",
                            cand,
                        )
                        self._last_success = dt_util.now()
                        self._consecutive_failures = 0
                        self._backoff_until = None
                        self._has_fetched_live = True
                        payload_data["last_success"] = self._last_success.isoformat()
                        await self.store.async_save(payload_data)

                        # Clean up any lingering reauth repairs on successful live fetch
                        try:
                            from homeassistant.helpers import issue_registry as ir

                            ir.async_delete_issue(
                                self.hass,
                                DOMAIN,
                                f"reauth_required_{self.config_entry.entry_id}",
                            )
                        except Exception:  # noqa: BLE001
                            pass

                        return payload_data

                # If in Add-on mode, the Add-on is the single source of truth.
                # If cached data is available on HA restart, serve cached data while stream populates
                if self.data and (
                    self.data.get("net_value", 0.0) > 0.0
                    or self.data.get("available_cash", 0.0) > 0.0
                ):
                    _LOGGER.debug(
                        "Trade Republic Add-on stream populating — returning cached data in interim"
                    )
                    return self.data

                _LOGGER.warning(
                    "Trade Republic Add-on did not return metrics yet — waiting for Add-on stream"
                )
                raise UpdateFailed(
                    "Waiting for Trade Republic Add-on live stream to populate metrics."
                )
            except ConfigEntryAuthFailed, InvalidAuthError, UpdateFailed:
                raise
            except Exception as e:
                _LOGGER.warning("Could not reach Trade Republic Add-on: %s", e)
                raise UpdateFailed(
                    f"Failed to communicate with Trade Republic Add-on: {e}"
                ) from e
            finally:
                await addon_client.close()

        # Restart resistance (only if update is not forced and we already completed a live fetch in this lifecycle)
        if (
            not self._force_update
            and self._has_fetched_live
            and self._last_success is not None
            and self.data
            and (
                self.data.get("net_value", 0.0) > 0.0
                or self.data.get("available_cash", 0.0) > 0.0
            )
        ):
            time_since = dt_util.now() - self._last_success
            effective_interval = self.update_interval or timedelta(
                seconds=DEFAULT_SCAN_INTERVAL
            )
            if time_since < (effective_interval - timedelta(minutes=5)):
                _LOGGER.info(
                    "Skipping Trade Republic update: last success was recent (%s)",
                    self._last_success,
                )
                return self.data

        domain_data = self.hass.data.setdefault(DOMAIN, {})
        fetch_lock: asyncio.Lock = domain_data.setdefault("fetch_lock", asyncio.Lock())

        async with fetch_lock:
            is_first_fetch = self._last_success is None
            if not self._force_update and not is_first_fetch:
                jitter = random.uniform(5.0, 30.0)
                _LOGGER.debug(
                    "Waiting %.1f s jitter before Trade Republic API call", jitter
                )
                await asyncio.sleep(jitter)
            else:
                self._force_update = False

            pin = self.config_entry.data.get(CONF_PIN, "")
            client = TradeRepublicAPIClient(
                self.phone_number,
                pin,
                session_token,
            )
            try:
                data = await self._fetch_client_data(client, pin)

                # Save updated session token if a new token was issued
                if client.session_token and client.session_token != session_token:
                    _LOGGER.info("Updating config entry with new session token")
                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        data={
                            **self.config_entry.data,
                            CONF_SESSION_TOKEN: client.session_token,
                        },
                    )
            except InvalidAuthError as err:
                # If connected via Addon, attempt an immediate token refresh via browser before failing
                if auth_mode == AUTH_MODE_ADDON:
                    addon_client = AddonClient(
                        default_host=addon_host, default_port=addon_port
                    )
                    try:
                        rhost, refreshed_token = await addon_client.trigger_refresh(
                            preferred_host=addon_host, port=addon_port
                        )
                        if (
                            rhost
                            and refreshed_token
                            and refreshed_token != session_token
                        ):
                            _LOGGER.info(
                                "Successfully refreshed session token from Add-on (%s), retrying connection...",
                                rhost,
                            )
                            self.hass.config_entries.async_update_entry(
                                self.config_entry,
                                data={
                                    **self.config_entry.data,
                                    CONF_SESSION_TOKEN: refreshed_token,
                                    CONF_ADDON_HOST: rhost,
                                },
                            )
                            refreshed_client = TradeRepublicAPIClient(
                                self.phone_number,
                                pin,
                                refreshed_token,
                            )
                            return await self._fetch_client_data(refreshed_client, pin)
                    finally:
                        await addon_client.close()

                _LOGGER.error(
                    "Trade Republic authentication failed (%s). Re-authentication required.",
                    err,
                )
                try:
                    from homeassistant.helpers import issue_registry as ir

                    ir.async_create_issue(
                        self.hass,
                        DOMAIN,
                        f"reauth_required_{self.config_entry.entry_id}",
                        is_fixable=True,
                        is_persistent=True,
                        severity=ir.IssueSeverity.ERROR,
                        translation_key="reauth_required",
                    )
                except Exception as issue_err:  # noqa: BLE001
                    _LOGGER.debug("Could not create repair issue: %s", issue_err)

                self.config_entry.async_start_reauth(self.hass)
                raise ConfigEntryAuthFailed(
                    "Trade Republic authentication failed. Please re-authenticate."
                ) from err

            except Exception as err:
                self._consecutive_failures += 1
                # Calculate backoff
                err_str = str(err).lower()
                if "429" in err_str or "403" in err_str or "block" in err_str:
                    backoff_hours = min(24, self._consecutive_failures * 2)
                    self._backoff_until = dt_util.now() + timedelta(hours=backoff_hours)
                else:
                    backoff_minutes = min(240, self._consecutive_failures * 15)
                    self._backoff_until = dt_util.now() + timedelta(
                        minutes=backoff_minutes
                    )

                raise UpdateFailed(f"Trade Republic fetch failed: {err}") from err

            self._last_success = dt_util.now()
            self._consecutive_failures = 0
            self._has_fetched_live = True
            data["last_success"] = self._last_success.isoformat()
            await self.store.async_save(data)
            return data

    async def _fetch_client_data(
        self, client: TradeRepublicAPIClient, pin: str
    ) -> dict[str, Any]:
        """Connect and fetch portfolio data using client."""
        async with asyncio.timeout(60):
            await client.connect()
            if not client.session_token and pin:
                await client.login_step1()
            override_rate: float | None = None
            if CONF_INTEREST_RATE in self.config_entry.options:
                override_rate = float(self.config_entry.options[CONF_INTEREST_RATE])
            data = await client.fetch_portfolio_data(interest_rate=override_rate)
            await client.close()
            return data
