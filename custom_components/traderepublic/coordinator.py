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

from .api import InvalidAuthError, TradeRepublicAPIClient
from .const import (
    CONF_INTEREST_RATE,
    CONF_PHONE_NUMBER,
    CONF_PIN,
    CONF_SCAN_INTERVAL,
    CONF_SESSION_TOKEN,
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

        # Persistent storage
        self.store: storage.Store[Any] = storage.Store(
            hass, 1, f"{DOMAIN}_{self.phone_number.replace('+', '')}"
        )

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
                except (ValueError, TypeError):
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

        # Restart resistance
        if (
            not self._force_update
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

            # Run API call
            session_token = self.config_entry.data.get(CONF_SESSION_TOKEN)
            pin = self.config_entry.data.get(CONF_PIN, "")
            client = TradeRepublicAPIClient(
                self.phone_number,
                pin,
                session_token,
            )
            try:
                async with asyncio.timeout(60):
                    await client.connect()
                    if not client.session_token and pin:
                        await client.login_step1()
                    override_rate: float | None = None
                    if CONF_INTEREST_RATE in self.config_entry.options:
                        override_rate = float(
                            self.config_entry.options[CONF_INTEREST_RATE]
                        )
                    data = await client.fetch_portfolio_data(
                        interest_rate=override_rate
                    )
                    await client.close()

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
                _LOGGER.error(
                    "Trade Republic authentication failed (%s). Re-authentication required.",
                    err,
                )
                raise ConfigEntryAuthFailed(
                    "Trade Republic authentication failed"
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
            data["last_success"] = self._last_success.isoformat()
            await self.store.async_save(data)
            return data
