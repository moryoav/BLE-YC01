"""The YC01 BLE integration with a persistent Bluetooth connection."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .coordinator import YC01Coordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Read initial measurements and keep the connection open until unload."""
    hass.data.setdefault(DOMAIN, {})
    coordinator = YC01Coordinator(hass, entry)

    try:
        await coordinator.async_config_entry_first_refresh()
        coordinator.connection.async_start()
        hass.data[DOMAIN][entry.entry_id] = coordinator

        @callback
        def _async_measurements_updated() -> None:
            """Keep the measurement schedule active even if sensors are disabled."""

        entry.async_on_unload(
            coordinator.async_add_listener(_async_measurements_updated)
        )
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await coordinator.async_shutdown()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload entities, stop reconnecting, and release the Bluetooth connection."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    return unload_ok
