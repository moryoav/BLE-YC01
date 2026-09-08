"""Connection-only keep-alive experiment for YC01 BLE devices."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from logging import Logger

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection


@dataclass
class YC01Device:
    """Device identity and the last completed keep-alive cycle."""

    hw_version: str = ""
    sw_version: str = ""
    name: str = ""
    identifier: str = ""
    address: str = ""
    last_keep_alive: datetime | None = None


class YC01BluetoothDeviceData:
    """Connect and disconnect without reading any characteristics."""

    def __init__(self, logger: Logger) -> None:
        """Initialize a serialized connection manager."""
        self.logger = logger
        self._lock = asyncio.Lock()

    async def keep_alive(self, ble_device: BLEDevice) -> YC01Device:
        """Complete one connection cycle without GATT reads or writes."""
        async with self._lock:
            async with asyncio.timeout(30):
                client = await establish_connection(
                    BleakClient, ble_device, ble_device.address, max_attempts=1
                )

            # Finish the bounded disconnect even if an entry reload cancels us.
            # No characteristic reads, writes, or notification subscriptions occur.
            disconnect_task = asyncio.create_task(self._disconnect(client))
            try:
                await asyncio.shield(disconnect_task)
            except asyncio.CancelledError:
                await disconnect_task
                raise

            self.logger.debug("Keep-alive completed for %s", ble_device.address)
            return YC01Device(
                name=ble_device.address,
                address=ble_device.address,
                last_keep_alive=datetime.now(timezone.utc),
            )

    async def _disconnect(self, client: BleakClient) -> None:
        """Release the connection with a bounded cleanup time."""
        async with asyncio.timeout(10):
            await client.disconnect()
