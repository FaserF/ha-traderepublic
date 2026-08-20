"""Central client for interacting with Trade Republic Home Assistant Add-on."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import ADDON_CONTAINER_HOSTS, DEFAULT_ADDON_HOST, DEFAULT_ADDON_PORT

_LOGGER = logging.getLogger(__name__)


class AddonClient:
    """HTTP helper for communicating with the Trade Republic Add-on."""

    def __init__(
        self,
        session: aiohttp.ClientSession | None = None,
        default_host: str = DEFAULT_ADDON_HOST,
        default_port: int = DEFAULT_ADDON_PORT,
    ) -> None:
        """Initialize AddonClient."""
        self._session = session
        self._owns_session = session is None
        self.default_host = default_host
        self.default_port = default_port

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create active aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        """Close owned session if open."""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()

    def get_candidate_hosts(self, preferred_host: str | None = None) -> list[str]:
        """Get ordered list of candidate hosts to try."""
        hosts: list[str] = []
        if preferred_host and preferred_host not in hosts:
            hosts.append(preferred_host)
        for cand in ADDON_CONTAINER_HOSTS:
            if cand not in hosts:
                hosts.append(cand)
        return hosts

    async def fetch_session(
        self, preferred_host: str | None = None, port: int | None = None
    ) -> tuple[str | None, dict[str, Any] | None]:
        """Find reachable host and fetch active session data.

        Returns:
            Tuple of (working_host, session_data_dict) or (None, None) if unreachable.
        """
        session = await self._get_session()
        target_port = port or self.default_port
        hosts = self.get_candidate_hosts(preferred_host or self.default_host)

        for host in hosts:
            url = f"http://{host}:{target_port}/api/v1/session"
            try:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=4)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return host, data
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("Could not reach addon at %s: %s", url, exc)
                continue

        return None, None

    async def trigger_refresh(
        self, preferred_host: str | None = None, port: int | None = None
    ) -> tuple[str | None, str | None]:
        """Trigger browser token refresh on the add-on.

        Returns:
            Tuple of (working_host, new_token) or (None, None) if failed.
        """
        session = await self._get_session()
        target_port = port or self.default_port
        hosts = self.get_candidate_hosts(preferred_host or self.default_host)

        for host in hosts:
            url = f"http://{host}:{target_port}/api/v1/refresh"
            try:
                _LOGGER.info(
                    "Attempting automatic session refresh via Trade Republic Add-on (%s)...",
                    host,
                )
                async with session.post(
                    url, timeout=aiohttp.ClientTimeout(total=8)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        token = data.get("session_token")
                        if token:
                            return host, token
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("Addon refresh attempt failed on %s: %s", host, exc)
                continue

        return None, None
