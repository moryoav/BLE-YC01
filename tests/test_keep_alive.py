"""Verify connection-only behavior and cleanup."""

import asyncio
import logging
from unittest.mock import call

import pytest
from bleak import BleakError

from custom_components.ble_yc01.BLE_YC01 import YC01BluetoothDeviceData


async def test_connect_disconnect_without_gatt(connection, client, ble_device):
    """A successful cycle uses only connect and disconnect."""
    manager = YC01BluetoothDeviceData(logging.getLogger(__name__))
    result = await manager.keep_alive(ble_device)

    connection.assert_awaited_once()
    assert connection.call_args.kwargs["max_attempts"] == 1
    assert client.method_calls == [call.disconnect()]
    assert result.address == ble_device.address
    assert result.name == ble_device.address
    assert result.identifier == ""
    assert result.last_keep_alive.tzinfo is not None


@pytest.mark.parametrize("failure", [BleakError("offline"), TimeoutError()])
async def test_failed_connection(connection, client, ble_device, failure):
    """A failed connection is not reported as a successful cycle."""
    connection.side_effect = failure
    manager = YC01BluetoothDeviceData(logging.getLogger(__name__))
    with pytest.raises(type(failure)):
        await manager.keep_alive(ble_device)
    assert client.method_calls == []


@pytest.mark.parametrize("failure", [BleakError("disconnect failed"), TimeoutError()])
async def test_failed_disconnect(connection, client, ble_device, failure):
    """A disconnect failure does not produce a success timestamp."""
    client.disconnect.side_effect = failure
    manager = YC01BluetoothDeviceData(logging.getLogger(__name__))
    with pytest.raises(type(failure)):
        await manager.keep_alive(ble_device)
    assert client.method_calls == [call.disconnect()]


async def test_cancellation_waits_for_disconnect(connection, client, ble_device):
    """An unload cannot leave a successful connection without cleanup."""
    started = asyncio.Event()
    release = asyncio.Event()

    async def disconnect():
        started.set()
        await release.wait()

    client.disconnect.side_effect = disconnect
    manager = YC01BluetoothDeviceData(logging.getLogger(__name__))
    task = asyncio.create_task(manager.keep_alive(ble_device))
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.method_calls == [call.disconnect()]


async def test_connections_do_not_overlap(connection, client, ble_device):
    """A second refresh waits until the previous disconnect completes."""
    started = asyncio.Event()
    release = asyncio.Event()

    async def disconnect():
        started.set()
        await release.wait()

    client.disconnect.side_effect = disconnect
    manager = YC01BluetoothDeviceData(logging.getLogger(__name__))
    first = asyncio.create_task(manager.keep_alive(ble_device))
    await started.wait()
    second = asyncio.create_task(manager.keep_alive(ble_device))
    await asyncio.sleep(0)
    assert connection.await_count == 1
    release.set()
    await asyncio.gather(first, second)
    assert connection.await_count == 2
    assert client.method_calls == [call.disconnect(), call.disconnect()]
