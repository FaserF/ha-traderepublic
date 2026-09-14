"""Diagnostics support for Trade Republic."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TO_REDACT = {
    "pin",
    "session_token",
    "phone_number",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)

    diagnostics_data: dict[str, Any] = {
        "entry": {
            "entry_id": entry.entry_id,
            "version": entry.version,
            "domain": entry.domain,
            "title": entry.title,
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": async_redact_data(entry.options, TO_REDACT),
        },
        "coordinator": {
            "consecutive_failures": coordinator._consecutive_failures
            if coordinator
            else None,
            "last_success": coordinator._last_success.isoformat()
            if coordinator and coordinator._last_success
            else None,
            "backoff_until": coordinator._backoff_until.isoformat()
            if coordinator and coordinator._backoff_until
            else None,
            "has_data": coordinator.data is not None if coordinator else False,
        }
        if coordinator
        else None,
    }

    return diagnostics_data
