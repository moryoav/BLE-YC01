"""Report Bluetooth connection changes independently of measurement polling."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import YC01Coordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add connection status to the existing Bluetooth device."""
    async_add_entities([YC01ConnectionSensor(hass.data[DOMAIN][entry.entry_id])])


class YC01ConnectionSensor(CoordinatorEntity[YC01Coordinator], BinarySensorEntity):
    """Expose off during disconnects, including while reconnecting."""

    _attr_has_entity_name = True
    _attr_translation_key = "connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: YC01Coordinator) -> None:
        """Reuse the connection manager's existing state notifications."""
        super().__init__(coordinator)
        address = coordinator.connection.address
        self._attr_unique_id = f"{address}_connection"
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, address)}
        )

    @property
    def available(self) -> bool:
        """Keep status readable when disconnected or a measurement read fails."""
        return True

    @property
    def is_on(self) -> bool:
        """Return the current connection state, not the last read's success."""
        return self.coordinator.connection.is_connected
