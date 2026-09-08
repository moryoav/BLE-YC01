"""Expose the last observed advertisement RSSI without touching the connection."""

from datetime import timedelta
from time import monotonic

from homeassistant.components import bluetooth
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT
from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util


class YC01SignalStrengthSensor(SensorEntity):
    """Last advertisement seen by Home Assistant's preferred connectable scanner."""

    _attr_has_entity_name = True
    _attr_name = "Bluetooth RSSI (last advertisement)"
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False
    _attr_available = False

    def __init__(self, address: str) -> None:
        """Link to the existing device without requiring a measurement read."""
        self._address = address
        self._attr_unique_id = f"{address}_rssi"
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, address)}
        )

    async def async_added_to_hass(self) -> None:
        """Seed from cached advertisements and subscribe to passive updates."""
        await super().async_added_to_hass()
        if info := bluetooth.async_last_service_info(
            self.hass, self._address, connectable=True
        ):
            self._update_info(info)
        self.async_on_remove(
            bluetooth.async_register_callback(
                self.hass,
                self._async_advertisement,
                {"address": self._address, "connectable": True},
                bluetooth.BluetoothScanningMode.PASSIVE,
            )
        )

    @callback
    def _async_advertisement(
        self,
        info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Use the preferred scanner's report, not whichever proxy called last."""
        latest = bluetooth.async_last_service_info(
            self.hass, self._address, connectable=True
        )
        self._update_info(latest or info)
        self.async_write_ha_state()

    @callback
    def _update_info(self, info: bluetooth.BluetoothServiceInfoBleak) -> None:
        """Keep the original observation time so cached RSSI is not shown as fresh."""
        if info.rssi == 127:  # Bluetooth's RSSI-not-available sentinel.
            return
        observed_at = dt_util.utcnow() - timedelta(
            seconds=max(0, monotonic() - info.time)
        )
        self._attr_native_value = info.rssi
        self._attr_available = True
        self._attr_extra_state_attributes = {
            "source": info.source,
            "last_received": observed_at.isoformat(),
        }
