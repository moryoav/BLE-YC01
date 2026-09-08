"""Verify the real Home Assistant lifecycle, timers, and sensor behavior."""

import asyncio
from datetime import timedelta
from unittest.mock import call, patch

import pytest
from bleak import BleakError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.ble_yc01.const import CONF_KEEP_ALIVE_INTERVAL, DOMAIN
from custom_components.ble_yc01.sensor import SENSORS_MAPPING_TEMPLATE

from .conftest import ADDRESS


async def setup_entry(hass, entry):
    """Load all real integration platforms and wait for entity creation."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return hass.data[DOMAIN][entry.entry_id]


async def advance(hass, freezer, seconds):
    """Advance both wall time and the coordinator's monotonic timer."""
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)


@pytest.mark.parametrize(
    "options, minutes", [({}, 4), ({CONF_KEEP_ALIVE_INTERVAL: 2}, 2)]
)
async def test_interval_and_unload(
    hass, entry, connection, client, freezer, options, minutes
):
    """The configured timer replaces 30-minute polling and stops on unload."""
    hass.config_entries.async_update_entry(entry, options=options)
    coordinator = await setup_entry(hass, entry)
    assert coordinator.update_interval == timedelta(minutes=minutes)
    assert connection.await_count == 1

    await advance(hass, freezer, minutes * 60 - 2)
    assert connection.await_count == 1
    await advance(hass, freezer, 3)
    assert connection.await_count == 2
    assert client.method_calls == [call.disconnect(), call.disconnect()]

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.entry_id not in hass.data[DOMAIN]
    await advance(hass, freezer, minutes * 60 + 2)
    assert connection.await_count == 2


async def test_sensors_preserve_ids_without_measurements(hass, entry, connection):
    """Old sensor identities survive, and only completed cycles have a value."""
    coordinator = await setup_entry(hass, entry)
    registry = er.async_get(hass)
    for key in SENSORS_MAPPING_TEMPLATE:
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{ADDRESS} _{key}")
        assert entity_id is not None
        assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{ADDRESS} _last_keep_alive"
    )
    assert (
        hass.states.get(entity_id).state
        == coordinator.data.last_keep_alive.replace(microsecond=0).isoformat()
    )


async def test_options_reload_replaces_timer(hass, entry, connection, freezer):
    """Saving a new interval leaves exactly one active timer."""
    old_coordinator = await setup_entry(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_KEEP_ALIVE_INTERVAL: 7}
    )
    await hass.async_block_till_done()
    new_coordinator = hass.data[DOMAIN][entry.entry_id]
    assert new_coordinator is not old_coordinator
    assert new_coordinator.update_interval == timedelta(minutes=7)
    assert connection.await_count == 2

    await advance(hass, freezer, 4 * 60 + 2)
    assert connection.await_count == 2
    await advance(hass, freezer, 3 * 60)
    assert connection.await_count == 3


async def test_timer_without_sensor_listeners(hass, entry, connection, freezer):
    """Keep-alive remains active when the sensor platform creates no entities."""
    with patch(
        "custom_components.ble_yc01.sensor.async_setup_entry", return_value=None
    ):
        await setup_entry(hass, entry)
    await advance(hass, freezer, 4 * 60 + 2)
    assert connection.await_count == 2


async def test_connection_failure_recovers(hass, entry, connection, client, freezer):
    """A failed scheduled attempt retries later without updating the success time."""
    coordinator = await setup_entry(hass, entry)
    original_time = coordinator.data.last_keep_alive
    connection.side_effect = BleakError("Device asleep")
    await advance(hass, freezer, 4 * 60 + 2)
    assert connection.await_count == 2
    assert not coordinator.last_update_success
    assert coordinator.data.last_keep_alive == original_time

    connection.side_effect = None
    await advance(hass, freezer, 4 * 60 + 2)
    assert connection.await_count == 3
    assert coordinator.last_update_success
    assert coordinator.data.last_keep_alive > original_time
    assert client.method_calls == [call.disconnect(), call.disconnect()]


async def test_missing_device_recovers(hass, entry, connection, freezer):
    """Losing a reachable adapter skips connection and retries on the next interval."""
    coordinator = await setup_entry(hass, entry)
    with patch(
        "custom_components.ble_yc01.bluetooth.async_ble_device_from_address",
        return_value=None,
    ):
        await advance(hass, freezer, 4 * 60 + 2)
    assert connection.await_count == 1
    assert not coordinator.last_update_success
    await advance(hass, freezer, 4 * 60 + 2)
    assert connection.await_count == 2
    assert coordinator.last_update_success


async def test_initial_failure_retries_setup(hass, entry, connection):
    """An unreachable device during startup follows Home Assistant setup retries."""
    connection.side_effect = BleakError("Device asleep")
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert entry.entry_id not in hass.data[DOMAIN]


async def test_unload_during_disconnect(hass, entry, connection, client, freezer):
    """Entry unload waits for the in-flight disconnect and cancels future cycles."""
    await setup_entry(hass, entry)
    started = asyncio.Event()
    release = asyncio.Event()

    async def disconnect():
        started.set()
        await release.wait()

    client.disconnect.side_effect = disconnect
    freezer.tick(timedelta(minutes=4, seconds=2))
    async_fire_time_changed(hass, dt_util.utcnow())
    await started.wait()
    unload = asyncio.create_task(hass.config_entries.async_unload(entry.entry_id))
    await asyncio.sleep(0)
    assert not unload.done()
    release.set()
    assert await unload
    await hass.async_block_till_done()
    await advance(hass, freezer, 4 * 60 + 2)
    assert connection.await_count == 2
    assert client.method_calls == [call.disconnect(), call.disconnect()]
