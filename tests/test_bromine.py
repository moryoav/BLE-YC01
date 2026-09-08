"""Estimated bromine follows the existing chlorine measurement."""

from unittest.mock import patch

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.ble_yc01.BLE_YC01.parser import YC01BluetoothDeviceData
from custom_components.ble_yc01.const import DOMAIN

from .conftest import ADDRESS, MEASUREMENT_FRAME
from .test_button import press
from .test_connection import advance, setup_entry


def bromine_id(hass):
    """Find the estimated sensor without depending on the entity name slug."""
    return er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{ADDRESS} _estimated_bromine"
    )


@pytest.mark.parametrize(
    ("raw_chlorine", "expected_chlorine", "expected_bromine"),
    [(0, 0, 0), (-1, 0, 0), (1, 0.1, 0.225), (15, 1.5, 3.375)],
)
async def test_bromine_conversion(
    hass, entry, transport, raw_chlorine, expected_chlorine, expected_bromine
):
    """Use the final chlorine value, including its existing negative clamp."""
    original = YC01BluetoothDeviceData.decode_position

    def decode(self, data, index):
        return raw_chlorine if index == 11 else original(self, data, index)

    with patch.object(YC01BluetoothDeviceData, "decode_position", decode):
        coordinator = await setup_entry(hass, entry)
    assert coordinator.data.sensors["cloro"] == expected_chlorine
    state = hass.states.get(bromine_id(hass))
    assert float(state.state) == expected_bromine
    assert state.attributes["unit_of_measurement"] == "ppm"
    assert state.attributes["state_class"] == "measurement"
    assert state.attributes["friendly_name"].endswith("Estimated Bromine")
    registry = er.async_get(hass)
    chlorine = registry.async_get_entity_id("sensor", DOMAIN, f"{ADDRESS} _cloro")
    assert (
        registry.async_get(chlorine).device_id
        == registry.async_get(bromine_id(hass)).device_id
    )
    transport.clients[0].read_gatt_char.assert_awaited_once()


async def test_bromine_updates_with_reads(hass, entry, transport, freezer):
    """Scheduled and manual reads update the estimate without extra GATT reads."""
    await setup_entry(hass, entry)
    client = transport.clients[0]
    assert float(hass.states.get(bromine_id(hass)).state) == 1.8
    original = YC01BluetoothDeviceData.decode_position

    def decode(self, data, index):
        return 20 if index == 11 else original(self, data, index)

    with patch.object(YC01BluetoothDeviceData, "decode_position", decode):
        await advance(hass, freezer, 1801)
    assert float(hass.states.get(bromine_id(hass)).state) == 4.5
    assert client.read_gatt_char.await_count == 2
    await press(hass)
    assert float(hass.states.get(bromine_id(hass)).state) == 1.8
    assert client.read_gatt_char.await_count == 3
    client.disconnect.assert_not_awaited()


async def test_bromine_unavailable_on_failed_read(hass, entry, transport, freezer):
    """A failed measurement does not expose the previous estimate as current."""
    await setup_entry(hass, entry)
    client = transport.clients[0]
    client.read_gatt_char.return_value = b"short"
    await advance(hass, freezer, 1801)
    assert hass.states.get(bromine_id(hass)).state == "unavailable"
    client.read_gatt_char.return_value = MEASUREMENT_FRAME
    await press(hass)
    assert float(hass.states.get(bromine_id(hass)).state) == 1.8
