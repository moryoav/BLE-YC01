"""Read measurements on a configurable schedule while retaining the Bluetooth link."""

from __future__ import annotations

import logging
from datetime import timedelta

from bleak import BleakError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .BLE_YC01 import YC01Device
from .connection import YC01Connection
from .const import CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class YC01Coordinator(DataUpdateCoordinator[YC01Device]):
    """Separate measurement polling from connection maintenance."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                minutes=entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
            ),
        )
        self.connection = YC01Connection(hass, entry, self.async_update_listeners)

    async def async_refresh_now(self) -> None:
        """Read immediately and count the next interval from the button press."""
        pressed_at = self.hass.loop.time()
        # Bypass request debouncing so each press performs a read. The coordinator
        # still serializes refreshes and cancels the previous scheduled read.
        await self.async_refresh()
        if (
            self._shutdown_requested
            or self.hass.is_stopping
            or self.config_entry.pref_disable_polling
            or self.update_interval is None
        ):
            return
        self._unschedule_refresh()
        remaining = max(
            0,
            self.update_interval.total_seconds() - (self.hass.loop.time() - pressed_at),
        )
        self._unsub_refresh = async_call_later(
            self.hass, remaining, self._handle_refresh_interval
        )

    @callback
    def async_set_poll_interval(self, minutes: int) -> None:
        """Start the new interval now without reading or reconnecting."""
        interval = timedelta(minutes=minutes)
        if self.update_interval == interval or self._shutdown_requested:
            return
        self.update_interval = interval
        self._unschedule_refresh()
        self._schedule_refresh()

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
