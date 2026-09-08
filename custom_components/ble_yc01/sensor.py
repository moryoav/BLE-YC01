"""Support for YC01 ble sensors."""

from __future__ import annotations

from datetime import datetime

from homeassistant import config_entries
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    UnitOfConductivity,
    UnitOfElectricPotential,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .BLE_YC01 import YC01Device
from .const import DOMAIN

SENSORS_MAPPING_TEMPLATE: dict[str, SensorEntityDescription] = {
    "EC": SensorEntityDescription(
        key="EC",
        name="Electrical Conductivity",
        native_unit_of_measurement=UnitOfConductivity.MICROSIEMENS_PER_CM,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:flash-triangle-outline",
    ),
    "salt": SensorEntityDescription(
        key="salt",
        name="Salt",
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:shaker-outline",
    ),
    "ORP": SensorEntityDescription(
        key="ORP",
        name="Oxidation-Reduction Potential",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.VOLTAGE,
        icon="mdi:alpha-v-circle",
    ),
    "TDS": SensorEntityDescription(
        key="TDS",
        name="Total Dissolved Solids",
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:dots-grid",
    ),
    "pH": SensorEntityDescription(
        key="pH",
        name="pH",
        device_class=SensorDeviceClass.PH,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:ph",
    ),
    "battery": SensorEntityDescription(
        key="battery",
        name="Battery",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
    ),
    "cloro": SensorEntityDescription(
        key="cloro",
        name="Free Chlorine",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        icon="mdi:chemical-weapon",
    ),
    "temperature": SensorEntityDescription(
        key="temperature",
        name="Temperature",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        icon="mdi:pool-thermometer",
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the YC01 BLE sensors."""
    coordinator: DataUpdateCoordinator[YC01Device] = hass.data[DOMAIN][entry.entry_id]
    # Keep the upstream entity IDs, but do not present old readings as fresh data.
    async_add_entities(
        [
            YC01Sensor(coordinator, coordinator.data, description)
            for description in SENSORS_MAPPING_TEMPLATE.values()
        ]
        + [
            YC01KeepAliveSensor(
                coordinator,
                coordinator.data,
                SensorEntityDescription(
                    key="last_keep_alive",
                    name="Last successful keep-alive",
                    device_class=SensorDeviceClass.TIMESTAMP,
                    entity_category=EntityCategory.DIAGNOSTIC,
                ),
            )
        ]
    )


class YC01Sensor(CoordinatorEntity[DataUpdateCoordinator[YC01Device]], SensorEntity):
    """YC01 BLE sensors for the device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        YC01_device: YC01Device,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Populate the YC01 entity with relevant data."""
        super().__init__(coordinator)
        self.entity_description = entity_description

        name = f"{YC01_device.name} {YC01_device.identifier}"

        self._attr_unique_id = f"{name}_{entity_description.key}"

        self._id = YC01_device.address
        self._attr_device_info = DeviceInfo(
            connections={
                (
                    CONNECTION_BLUETOOTH,
                    YC01_device.address,
                )
            },
            name=name,
            manufacturer="YC01",
            model="YC01",
            hw_version=YC01_device.hw_version,
            sw_version=YC01_device.sw_version,
        )

    @property
    def available(self) -> bool:
        """Measurements are unavailable while characteristic reads are disabled."""
        return False

    @property
    def native_value(self) -> StateType:
        """No measurement is collected by this experiment."""
        return None


class YC01KeepAliveSensor(YC01Sensor):
    """Report when a connection and disconnect both completed successfully."""

    @property
    def available(self) -> bool:
        """Reflect the outcome of the latest keep-alive attempt."""
        return self.coordinator.last_update_success

    @property
    def native_value(self) -> datetime | None:
        """Return the last completed cycle timestamp."""
        return self.coordinator.data.last_keep_alive
