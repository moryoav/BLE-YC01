"""Persistent connections, 30-minute reads, recovery, and lifecycle cleanup."""

import asyncio
from datetime import timedelta
from unittest.mock import patch

import pytest
from bleak import BleakError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.ble_yc01.BLE_YC01.parser import READ_UUID
from custom_components.ble_yc01.const import DOMAIN

from .conftest import ADDRESS


async def setup_entry(hass, entry):
    """Set up through the real config entry and sensor platforms."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


async def advance(hass, freezer, seconds):
    """Run scheduled callbacks after advancing both clocks."""
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


def drop(client):
    """Simulate a proxy reporting an unexpected disconnection."""
    client.is_connected = False
    client.disconnected_callback(client)


async def test_retains_connection_between_30_minute_reads(
    hass, entry, transport, freezer
):
    """Two scheduled measurements reuse one connection without disconnecting."""
    coordinator = await setup_entry(hass, entry)
    client = transport.clients[0]
    assert coordinator.update_interval == timedelta(minutes=30)
    client.connect.assert_awaited_once()
    client.read_gatt_char.assert_awaited_once_with(READ_UUID)
    client.disconnect.assert_not_awaited()

    await advance(hass, freezer, 1798)
    assert transport.factory.call_count == 1
    assert client.read_gatt_char.await_count == 1
    await advance(hass, freezer, 3)
    assert client.read_gatt_char.await_count == 2
    assert transport.factory.call_count == 1
    assert coordinator.connection.is_connected
    client.disconnect.assert_not_awaited()


async def test_original_measurements_and_entity_ids(hass, entry, transport):
    """A fixed synthetic frame preserves upstream measurement decoding and IDs."""
    await setup_entry(hass, entry)
    registry = er.async_get(hass)
    expected = {
        "pH": "7.5",
        "EC": "1200",
        "salt": "660.0",
        "TDS": "600",
        "ORP": "0.65",
        "cloro": "0.8",
        "temperature": "27.5",
        "battery": "100",
    }
    for key, value in expected.items():
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{ADDRESS} _{key}")
        assert entity_id is not None
        assert hass.states.get(entity_id).state == value


async def test_drop_reconnects_without_read_or_timer_reset(
    hass, entry, transport, freezer
):
    """Reconnect immediately, then read only at the original 30-minute deadline."""
    coordinator = await setup_entry(hass, entry)
    first = transport.clients[0]
    await advance(hass, freezer, 10)
    drop(first)
    assert not coordinator.connection.is_connected
    await hass.async_block_till_done()
    assert transport.factory.call_count == 2
    second = transport.clients[1]
    assert coordinator.connection.is_connected
    second.read_gatt_char.assert_not_awaited()
    second.disconnect.assert_not_awaited()

    await advance(hass, freezer, 1788)
    second.read_gatt_char.assert_not_awaited()
    await advance(hass, freezer, 3)
    second.read_gatt_char.assert_awaited_once_with(READ_UUID)
    assert first.read_gatt_char.await_count == 1


async def test_missed_disconnect_callback(hass, entry, transport, freezer):
    """Local connection state checks recover a missing callback without GATT reads."""
    coordinator = await setup_entry(hass, entry)
    transport.clients[0].is_connected = False
    await advance(hass, freezer, 6)
    assert transport.factory.call_count == 2
    assert coordinator.connection.is_connected
    transport.clients[1].read_gatt_char.assert_not_awaited()


async def test_failed_reconnect_retries_after_five_seconds(
    hass, entry, transport, freezer
):
    """A partial connection is cleaned up and retried independently of polling."""
    coordinator = await setup_entry(hass, entry)
    transport.connect_errors.append(BleakError("proxy temporarily unavailable"))
    drop(transport.clients[0])
    await hass.async_block_till_done()
    assert transport.factory.call_count == 2
    failed = transport.clients[1]
    failed.disconnect.assert_awaited_once()
    assert not coordinator.connection.is_connected

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{ADDRESS} _pH")
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE
    await advance(hass, freezer, 4)
    assert transport.factory.call_count == 2
    await advance(hass, freezer, 2)
    assert transport.factory.call_count == 3
    assert coordinator.connection.is_connected
    transport.clients[2].read_gatt_char.assert_not_awaited()
    assert hass.states.get(entity_id).state == "7.5"


async def test_missing_adapter_retries_with_current_device(
    hass, entry, transport, freezer
):
    """A replacement connection uses the newly available adapter/device object."""
    coordinator = await setup_entry(hass, entry)
    transport.lookup.return_value = None
    drop(transport.clients[0])
    await hass.async_block_till_done()
    assert not coordinator.connection.is_connected
    assert transport.factory.call_count == 1

    transport.lookup.return_value = transport.device
    await advance(hass, freezer, 6)
    assert coordinator.connection.is_connected
    assert transport.factory.call_count == 2
    assert transport.factory.call_args.args[0] is transport.device


async def test_read_failure_reconnects_without_extra_read(
    hass, entry, transport, freezer
):
    """Recover a failed transport without immediately repeating the measurement."""
    coordinator = await setup_entry(hass, entry)
    first = transport.clients[0]
    first.read_gatt_char.side_effect = BleakError("read failed")
    await advance(hass, freezer, 1801)
    assert not coordinator.last_update_success
    assert transport.factory.call_count == 2
    assert coordinator.connection.is_connected
    second = transport.clients[1]
    second.read_gatt_char.assert_not_awaited()

    await advance(hass, freezer, 1801)
    second.read_gatt_char.assert_awaited_once()
    assert coordinator.last_update_success


async def test_malformed_frame_keeps_connection(hass, entry, transport, freezer):
    """Invalid measurement data does not unnecessarily close a healthy link."""
    coordinator = await setup_entry(hass, entry)
    client = transport.clients[0]
    client.read_gatt_char.return_value = b"short"
    await advance(hass, freezer, 1801)
    assert not coordinator.last_update_success
    assert coordinator.connection.is_connected
    client.disconnect.assert_not_awaited()
    assert transport.factory.call_count == 1


@pytest.mark.parametrize("polling_disabled", [False, True])
async def test_connection_without_sensor_listeners(
    hass, entry, transport, freezer, polling_disabled
):
    """Connection maintenance does not depend on sensors or the polling preference."""
    hass.config_entries.async_update_entry(entry, pref_disable_polling=polling_disabled)
    with patch(
        "custom_components.ble_yc01.sensor.async_setup_entry", return_value=None
    ):
        coordinator = await setup_entry(hass, entry)
    drop(transport.clients[0])
    await hass.async_block_till_done()
    assert coordinator.connection.is_connected
    second = transport.clients[1]
    second.read_gatt_char.assert_not_awaited()
    await advance(hass, freezer, 1801)
    assert second.read_gatt_char.await_count == (0 if polling_disabled else 1)
    second.disconnect.assert_not_awaited()


async def test_unload_closes_connection_and_stops_retries(
    hass, entry, transport, freezer
):
    """Releasing the entry closes its one client and prevents future connections."""
    coordinator = await setup_entry(hass, entry)
    client = transport.clients[0]
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not coordinator.connection.is_connected
    client.disconnect.assert_awaited_once()
    await advance(hass, freezer, 1801)
    assert transport.factory.call_count == 1
    assert client.read_gatt_char.await_count == 1


async def test_reload_releases_old_client_before_connecting(hass, entry, transport):
    """An integration reload must never hold two proxy slots at the same time."""
    await setup_entry(hass, entry)
    first = transport.clients[0]
    original_create = transport.factory.side_effect

    def create_after_disconnect(*args, **kwargs):
        assert not first.is_connected
        return original_create(*args, **kwargs)

    transport.factory.side_effect = create_after_disconnect
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    first.disconnect.assert_awaited_once()
    assert transport.factory.call_count == 2
    assert transport.clients[1].is_connected


@pytest.mark.parametrize("failure", ["connect", "read"])
async def test_setup_failure_releases_client(hass, entry, transport, failure):
    """A failed first setup must not leave a proxy slot occupied."""
    if failure == "connect":
        transport.connect_errors.append(BleakError("connection failed"))
    else:
        transport.read_data = b"short"
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    transport.clients[0].disconnect.assert_awaited_once()
    assert entry.entry_id not in hass.data[DOMAIN]


async def test_cancelled_setup_cleans_partial_connection(hass, entry, transport):
    """Cancellation after the link opens still releases the client."""
    started = asyncio.Event()
    original_create = transport.factory.side_effect

    def slow_client(*args, **kwargs):
        client = original_create(*args, **kwargs)

        async def connect():
            client.is_connected = True
            started.set()
            await asyncio.Event().wait()

        client.connect.side_effect = connect
        return client

    transport.factory.side_effect = slow_client
    task = asyncio.create_task(hass.config_entries.async_setup(entry.entry_id))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    transport.clients[0].disconnect.assert_awaited_once()
    assert not transport.clients[0].is_connected


async def test_home_assistant_shutdown_disconnects(hass, entry, transport):
    """Stopping Home Assistant cancels the worker and releases the link."""
    await setup_entry(hass, entry)
    await hass.async_stop()
    transport.clients[0].disconnect.assert_awaited_once()
    assert not transport.clients[0].is_connected


async def test_unload_during_reconnect(hass, entry, transport):
    """Cancel a reconnect that has already opened the link and release its slot."""
    await setup_entry(hass, entry)
    started = asyncio.Event()
    original_create = transport.factory.side_effect

    def slow_client(*args, **kwargs):
        client = original_create(*args, **kwargs)

        async def connect():
            client.is_connected = True
            started.set()
            await asyncio.Event().wait()

        client.connect.side_effect = connect
        return client

    transport.factory.side_effect = slow_client
    drop(transport.clients[0])
    await started.wait()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert transport.factory.call_count == 2
    transport.clients[1].disconnect.assert_awaited_once()
    assert not transport.clients[1].is_connected


async def test_failed_disconnect_does_not_allocate_another_slot(
    hass, entry, transport, freezer
):
    """Retry cleanup before constructing another client if the old link is held."""
    coordinator = await setup_entry(hass, entry)
    first = transport.clients[0]
    first.read_gatt_char.side_effect = BleakError("read failed")
    disconnect = first.disconnect.side_effect
    first.disconnect.side_effect = BleakError("proxy did not disconnect")
    await advance(hass, freezer, 1801)
    assert not coordinator.last_update_success
    assert not coordinator.connection.is_connected
    assert first.is_connected
    assert transport.factory.call_count == 1

    first.disconnect.side_effect = disconnect
    await advance(hass, freezer, 6)
    assert not first.is_connected
    assert coordinator.connection.is_connected
    assert transport.factory.call_count == 2
    transport.clients[1].read_gatt_char.assert_not_awaited()
