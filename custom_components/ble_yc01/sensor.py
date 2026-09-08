"""Support for YC01 ble sensors."""

from __future__ import annotations

import logging

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
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from .BLE_YC01 import YC01Device
from .const import DOMAIN
from .coordinator import YC01Coordinator
from .signal_strength import YC01SignalStrengthSensor

_LOGGER = logging.getLogger(__name__)

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
    "estimated_bromine": SensorEntityDescription(
        key="estimated_bromine",
        name="Estimated Bromine",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        suggested_display_precision=3,
        icon="mdi:flask-outline",
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

    coordinator: YC01Coordinator = hass.data[DOMAIN][entry.entry_id]
    sensors_mapping = SENSORS_MAPPING_TEMPLATE.copy()
    entities = []
    _LOGGER.debug("got sensors: %s", coordinator.data.sensors)
    for sensor_type, sensor_value in coordinator.data.sensors.items():
        if sensor_type not in sensors_mapping:
            _LOGGER.debug(
                "Unknown sensor type detected: %s, %s",
                sensor_type,
                sensor_value,
            )
            continue
        entities.append(
            YC01Sensor(coordinator, coordinator.data, sensors_mapping[sensor_type])
        )

    entities.append(YC01SignalStrengthSensor(coordinator.data.address))
    async_add_entities(entities)


class YC01Sensor(CoordinatorEntity[YC01Coordinator], SensorEntity):
    """YC01 BLE sensors for the device."""

    # _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: YC01Coordinator,
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
        """Mark measurements unavailable while the Bluetooth connection is down."""
        return super().available and self.coordinator.connection.is_connected

    @property
    def native_value(self) -> StateType:
        """Return the value reported by the sensor."""
        try:
            return self.coordinator.data.sensors[self.entity_description.key]
        except KeyError:
            return None
