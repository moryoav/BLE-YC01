"""The YC01 BLE keep-alive experiment."""

from __future__ import annotations

import logging
from datetime import timedelta

from bleak import BleakError
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .BLE_YC01 import YC01BluetoothDeviceData, YC01Device
from .const import CONF_KEEP_ALIVE_INTERVAL, DEFAULT_KEEP_ALIVE_INTERVAL, DOMAIN

PLATFORMS: list[Platform] = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up periodic connection-only keep-alive for a device."""
    hass.data.setdefault(DOMAIN, {})
    address = entry.unique_id
    assert address is not None
    yc01 = YC01BluetoothDeviceData(_LOGGER)

    async def _async_keep_alive() -> YC01Device:
        """Use the currently reachable adapter for each connection cycle."""
        ble_device = bluetooth.async_ble_device_from_address(
            hass, address, connectable=True
        )
        if ble_device is None:
            raise UpdateFailed(f"Could not find YC01 device with address {address}")
        try:
            return await yc01.keep_alive(ble_device)
        except (BleakError, TimeoutError, OSError) as err:
            raise UpdateFailed(f"Unable to complete keep-alive: {err}") from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        config_entry=entry,
        name=DOMAIN,
        update_method=_async_keep_alive,
        update_interval=timedelta(
            minutes=entry.options.get(
                CONF_KEEP_ALIVE_INTERVAL, DEFAULT_KEEP_ALIVE_INTERVAL
            )
        ),
    )
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    @callback
    def _async_keep_alive_updated() -> None:
        """Keep the timer subscribed even when every sensor is disabled."""

    entry.async_on_unload(coordinator.async_add_listener(_async_keep_alive_updated))
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply the new interval and dispose of the previous timer."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the entry and stop its keep-alive timer and connection tasks."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
