"""Exercise manual reads through Home Assistant's button service."""

from datetime import timedelta

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.ble_yc01.const import CONF_POLL_INTERVAL, DOMAIN

from .conftest import ADDRESS, MEASUREMENT_FRAME
from .test_connection import advance, setup_entry


def button_id(hass):
    """Look up the button by its stable identity."""
    return er.async_get(hass).async_get_entity_id(
        "button", DOMAIN, f"{ADDRESS}_refresh"
    )


async def press(hass):
    """Use the same service as the device page button."""
    await hass.services.async_call(
        "button", "press", {"entity_id": button_id(hass)}, blocking=True
    )
    await hass.async_block_till_done()


@pytest.mark.parametrize("minutes", [30, 5])
async def test_refresh_restarts_interval(hass, entry, transport, freezer, minutes):
    """A mid-interval press replaces the old deadline and updates measurements."""
    hass.config_entries.async_update_entry(entry, options={CONF_POLL_INTERVAL: minutes})
    coordinator = await setup_entry(hass, entry)
    client = transport.clients[0]
    registry = er.async_get(hass)
    button = registry.async_get(button_id(hass))
    sensor = registry.async_get(
        registry.async_get_entity_id("sensor", DOMAIN, f"{ADDRESS} _pH")
    )
    assert button.device_id == sensor.device_id
    assert (
        hass.states.get(button.entity_id)
        .attributes["friendly_name"]
        .endswith("Refresh")
    )
    await advance(hass, freezer, minutes * 30)
    old_data = coordinator.data
    await press(hass)
    assert client.read_gatt_char.await_count == 2
    assert coordinator.data is not old_data
    await advance(hass, freezer, minutes * 30 + 1)
    assert client.read_gatt_char.await_count == 2
    await advance(hass, freezer, minutes * 30)
    assert client.read_gatt_char.await_count == 3
    await advance(hass, freezer, minutes * 60 + 1)
    assert client.read_gatt_char.await_count == 4
    assert transport.factory.call_count == 1
    client.disconnect.assert_not_awaited()


async def test_slow_read_counts_from_press(hass, entry, transport, freezer):
    """Read latency does not push the next deadline beyond the chosen interval."""
    await setup_entry(hass, entry)
    client = transport.clients[0]

    async def slow_read(_uuid):
        freezer.tick(timedelta(seconds=10))
        return MEASUREMENT_FRAME

    client.read_gatt_char.side_effect = slow_read
    await press(hass)
    client.read_gatt_char.side_effect = None
    await advance(hass, freezer, 1788)
    assert client.read_gatt_char.await_count == 2
    await advance(hass, freezer, 3)
    assert client.read_gatt_char.await_count == 3


async def test_repeated_presses_read_without_debouncing(
    hass, entry, transport, freezer
):
    """Each press reads immediately and the last press sets the deadline."""
    await setup_entry(hass, entry)
    client = transport.clients[0]
    await press(hass)
    await advance(hass, freezer, 5)
    await press(hass)
    assert client.read_gatt_char.await_count == 3
    await advance(hass, freezer, 1796)
    assert client.read_gatt_char.await_count == 3
    await advance(hass, freezer, 5)
    assert client.read_gatt_char.await_count == 4
    client.disconnect.assert_not_awaited()


async def test_manual_read_with_polling_disabled(hass, entry, transport, freezer):
    """A button press does not enable automatic polling."""
    hass.config_entries.async_update_entry(entry, pref_disable_polling=True)
    await setup_entry(hass, entry)
    await press(hass)
    await advance(hass, freezer, 1801)
    assert transport.clients[0].read_gatt_char.await_count == 2


async def test_failed_read_can_be_retried(hass, entry, transport):
    """Report a read failure and allow another press on a healthy connection."""
    await setup_entry(hass, entry)
    client = transport.clients[0]
    client.read_gatt_char.return_value = b"short"
    with pytest.raises(HomeAssistantError, match="Unable to refresh"):
        await press(hass)
    assert hass.states.get(button_id(hass)).state != "unavailable"
    client.read_gatt_char.return_value = MEASUREMENT_FRAME
    await press(hass)
    assert client.read_gatt_char.await_count == 3
    client.disconnect.assert_not_awaited()


async def test_unload_cancels_manual_deadline(hass, entry, transport, freezer):
    """The replacement timer cannot read or reconnect after unload."""
    await setup_entry(hass, entry)
    await press(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await advance(hass, freezer, 1801)
    assert transport.clients[0].read_gatt_char.await_count == 2
    assert transport.factory.call_count == 1
    transport.clients[0].disconnect.assert_awaited_once()
