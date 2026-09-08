"""Read measurements every 30 minutes while retaining the Bluetooth link."""

from __future__ import annotations

import logging
from datetime import timedelta

from bleak import BleakError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .BLE_YC01 import YC01Device
from .connection import YC01Connection
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class YC01Coordinator(DataUpdateCoordinator[YC01Device]):
    """Separate measurement polling from connection maintenance."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.connection = YC01Connection(hass, entry, self.async_update_listeners)

    async def _async_update_data(self) -> YC01Device:
        """Fetch measurements over the existing connection."""
        try:
            return await self.connection.async_read_data()
        except (BleakError, TimeoutError, OSError, ValueError) as err:
            raise UpdateFailed(f"Unable to read YC01 measurements: {err}") from err

    async def async_shutdown(self) -> None:
        """Cancel measurement polling and close the persistent connection."""
        await super().async_shutdown()
        await self.connection.async_stop()
