"""The Trade Republic integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .api import AddonClient
from .const import (
    CONF_ADDON_HOST,
    CONF_ADDON_PORT,
    DEFAULT_ADDON_HOST,
    DEFAULT_ADDON_PORT,
    DOMAIN,
)
from .coordinator import TradeRepublicDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

SERVICE_GET_TRANSACTIONS = "get_transactions"

SERVICE_GET_TRANSACTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional("limit", default=50): cv.positive_int,
        vol.Optional("search"): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Trade Republic from a config entry."""
    coordinator = TradeRepublicDataUpdateCoordinator(hass, entry)

    # Load cache (anti-ban restart resistance)
    await coordinator.async_load_cache()

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register get_transactions service once per domain
    if not hass.services.has_service(DOMAIN, SERVICE_GET_TRANSACTIONS):

        async def async_handle_get_transactions(call: ServiceCall) -> dict[str, Any]:
            """Handle get_transactions service call."""
            limit = call.data.get("limit", 50)
            search = call.data.get("search")

            # Find active coordinator
            domain_entries = hass.data.get(DOMAIN, {})
            active_coord = None
            for item in domain_entries.values():
                if isinstance(item, TradeRepublicDataUpdateCoordinator):
                    active_coord = item
                    break

            if not active_coord:
                return {
                    "error": "No active Trade Republic coordinator found",
                    "transactions": [],
                }

            addon_host = active_coord.config_entry.data.get(
                CONF_ADDON_HOST, DEFAULT_ADDON_HOST
            )
            addon_port = active_coord.config_entry.data.get(
                CONF_ADDON_PORT, DEFAULT_ADDON_PORT
            )
            client = AddonClient(default_host=addon_host, default_port=addon_port)
            try:
                cand, result = await client.fetch_timeline(
                    preferred_host=addon_host,
                    port=addon_port,
                    limit=limit,
                    search=search,
                )
                if result and "transactions" in result:
                    return result
            finally:
                await client.close()

            # Fallback to in-memory recent transactions if addon timeline endpoint unavailable
            cached_data = active_coord.data or {}
            fallback_txs = cached_data.get("recent_transactions", [])
            if search:
                s_lower = search.strip().lower()
                fallback_txs = [
                    tx
                    for tx in fallback_txs
                    if s_lower in str(tx.get("title", "")).lower()
                    or s_lower in str(tx.get("subtitle", "")).lower()
                ]

            return {
                "transactions": fallback_txs[:limit],
                "total_count": len(fallback_txs),
                "count": min(len(fallback_txs), limit),
            }

        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_TRANSACTIONS,
            async_handle_get_transactions,
            schema=SERVICE_GET_TRANSACTIONS_SCHEMA,  # type: ignore[arg-type]
            supports_response=SupportsResponse.ONLY,
        )

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if (
        unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    ) and DOMAIN in hass.data:
        hass.data[DOMAIN].pop(entry.entry_id, None)

        # Unregister service if no coordinators remain
        remaining = [
            v
            for v in hass.data[DOMAIN].values()
            if isinstance(v, TradeRepublicDataUpdateCoordinator)
        ]
        if not remaining and hass.services.has_service(DOMAIN, SERVICE_GET_TRANSACTIONS):
            hass.services.async_remove(DOMAIN, SERVICE_GET_TRANSACTIONS)

    return unload_ok
