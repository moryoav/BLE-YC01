"""Connection status follows transport events instead of the polling clock."""

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.ble_yc01.const import DOMAIN

from .conftest import ADDRESS
from .test_connection import advance, drop, setup_entry


def connection_id(hass):
    return er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, f"{ADDRESS}_connection"
    )


@pytest.mark.parametrize("polling_disabled", [False, True])
async def test_immediate_disconnect_and_reconnect(
    hass, entry, transport, freezer, polling_disabled
):
    """Report off synchronously on disconnect and on before any recovery read."""
    hass.config_entries.async_update_entry(entry, pref_disable_polling=polling_disabled)
    await setup_entry(hass, entry)
    entity_id = connection_id(hass)
    state = hass.states.get(entity_id)
    assert state.state == "on"
    assert state.attributes["device_class"] == "connectivity"
    assert state.attributes["friendly_name"].endswith("Bluetooth connection")
    registry = er.async_get(hass)
    sensor = registry.async_get_entity_id("sensor", DOMAIN, f"{ADDRESS} _pH")
    assert (
        registry.async_get(entity_id).device_id == registry.async_get(sensor).device_id
    )
    assert registry.async_get(entity_id).entity_category is er.EntityCategory.DIAGNOSTIC
    transport.lookup.return_value = None
    drop(transport.clients[0])
    # No clock advance, event-loop wait, or measurement read is needed.
    assert hass.states.get(entity_id).state == "off"
    await hass.async_block_till_done()
    await advance(hass, freezer, 6)
    assert hass.states.get(entity_id).state == "off"
    transport.clients[0].read_gatt_char.assert_awaited_once()
    transport.lookup.return_value = transport.device
    await advance(hass, freezer, 6)
    assert hass.states.get(entity_id).state == "on"
    transport.clients[1].read_gatt_char.assert_not_awaited()


async def test_missed_callback_reports_off(hass, entry, transport, freezer):
    """The existing local state check catches a lost callback without polling."""
    await setup_entry(hass, entry)
    transport.lookup.return_value = None
    transport.clients[0].is_connected = False
    await advance(hass, freezer, 6)
    assert hass.states.get(connection_id(hass)).state == "off"
    transport.clients[0].read_gatt_char.assert_awaited_once()


async def test_invalid_measurement_stays_connected(hass, entry, transport, freezer):
    """Measurement failure cannot hide a healthy Bluetooth connection."""
    await setup_entry(hass, entry)
    transport.clients[0].read_gatt_char.return_value = b"short"
    await advance(hass, freezer, 1801)
    assert hass.states.get(connection_id(hass)).state == "on"
    registry = er.async_get(hass)
    sensor = registry.async_get_entity_id("sensor", DOMAIN, f"{ADDRESS} _pH")
    assert hass.states.get(sensor).state == "unavailable"
    transport.lookup.return_value = None
    drop(transport.clients[0])
    assert hass.states.get(connection_id(hass)).state == "off"


async def test_unload_connection_sensor(hass, entry, transport, freezer):
    """Unload removes the status entity and its coordinator listener."""
    await setup_entry(hass, entry)
    entity_id = connection_id(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state is None or state.state == "unavailable"
    await advance(hass, freezer, 1801)
    assert transport.factory.call_count == 1
    transport.clients[0].read_gatt_char.assert_awaited_once()
