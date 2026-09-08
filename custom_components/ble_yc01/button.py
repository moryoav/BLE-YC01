"""Manually refresh YC01 measurements over the persistent connection."""

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import YC01Coordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add a refresh button to the existing YC01 device."""
    async_add_entities([YC01RefreshButton(hass.data[DOMAIN][entry.entry_id])])


class YC01RefreshButton(CoordinatorEntity[YC01Coordinator], ButtonEntity):
    """Read measurements and restart the polling countdown."""

    _attr_has_entity_name = True
    _attr_translation_key = "refresh"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: YC01Coordinator) -> None:
        """Associate the button with the same Bluetooth device as the sensors."""
        super().__init__(coordinator)
        address = coordinator.data.address
        self._attr_unique_id = f"{address}_refresh"
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, address)}
        )

    @property
    def available(self) -> bool:
        """Allow another read after a decoding failure while still connected."""
        return self.coordinator.connection.is_connected

    async def async_press(self) -> None:
        """Perform one read and report failures to the caller."""
        await self.coordinator.async_refresh_now()
        if not self.coordinator.last_update_success:
            raise HomeAssistantError("Unable to refresh YC01 measurements") from (
                self.coordinator.last_exception
            )
