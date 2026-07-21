"""Shared test fixtures for the Trade Republic integration."""

from __future__ import annotations

import asyncio
import sys

# Windows: mock fcntl and resource to prevent Home Assistant runner module errors
if sys.platform == "win32":
    import types
    sys.modules["fcntl"] = types.ModuleType("fcntl")
    sys.modules["resource"] = types.ModuleType("resource")
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry  # type: ignore[import-untyped]

from custom_components.traderepublic.const import (
    CONF_PHONE_NUMBER,
    CONF_PIN,
    CONF_SESSION_TOKEN,
    DOMAIN,
)

@pytest.fixture(autouse=True)
async def enable_custom_integrations(hass):
    """Enable custom integrations to be loaded in tests."""
    hass.data.pop("custom_components", None)

@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="+49123456789",
        data={
            CONF_PHONE_NUMBER: "+49123456789",
            CONF_PIN: "1234",
            CONF_SESSION_TOKEN: "valid_session_token",
        },
        options={},
        entry_id="test_entry_id",
    )
