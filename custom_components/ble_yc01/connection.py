"""Maintain one Bluetooth connection independently of measurement polling."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress

from bleak import BleakClient, BleakError
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .BLE_YC01 import YC01BluetoothDeviceData, YC01Device

_LOGGER = logging.getLogger(__name__)
RECONNECT_DELAY = 5
CONNECT_TIMEOUT = 20
READ_TIMEOUT = 20
DISCONNECT_TIMEOUT = 10


class YC01Connection:
    """Own a persistent client and serialize reads, reconnects, and cleanup."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        state_changed: Callable[[], None],
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.address = entry.unique_id
        assert self.address is not None
        self._state_changed = state_changed
        self._parser = YC01BluetoothDeviceData(_LOGGER)
        self._client: BleakClient | None = None
        self._ready = False
        self._closing = False
        self._lock = asyncio.Lock()
        self._disconnected = asyncio.Event()
        self._task: asyncio.Task | None = None

    @property
    def is_connected(self) -> bool:
        """Return whether a usable connection is currently held."""
        return bool(
            not self._closing
            and self._ready
            and self._client is not None
            and self._client.is_connected
        )

    @callback
    def async_start(self) -> None:
        """Monitor the connection even when no measurements are requested."""
        if self._task is None and not self._closing:
            self._task = self.entry.async_create_background_task(
                self.hass,
                self._maintain_connection(),
                f"BLE-YC01 {self.address} connection",
            )

    @callback
    def _on_disconnect(self, client: BleakClient) -> None:
        """Wake the reconnect worker without requesting a measurement."""
        if client is self._client and not self._closing:
            self._ready = False
            self._disconnected.set()
            self._state_changed()

    async def _connect_locked(self) -> BleakClient:
        """Reuse the current connection or establish one through a current adapter."""
        if self._closing:
            raise BleakError("YC01 connection is shutting down")
        if self.is_connected:
            assert self._client is not None
            return self._client

        # Release even a partially connected client before allocating another slot.
        await self._disconnect_locked()
        if self._closing:
            raise BleakError("YC01 connection is shutting down")
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise BleakError(f"No connectable adapter can reach YC01 {self.address}")

        self._disconnected.clear()
        client = self._client = BleakClient(
            device, disconnected_callback=self._on_disconnect
        )
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT):
                await client.connect()
            if self._closing:
                raise BleakError("YC01 connection is shutting down")
            if not client.is_connected:
                raise BleakError("YC01 disconnected while connecting")
        except BaseException:
            # Also clean up an interrupted or timed-out connection attempt.
            await self._disconnect_locked()
            raise

        self._ready = True
        self._state_changed()
        _LOGGER.info("Connected to YC01 %s; keeping the connection open", self.address)
        return client

    async def async_read_data(self) -> YC01Device:
        """Read FF02 on the retained connection without disconnecting afterward."""
        async with self._lock:
            client = await self._connect_locked()
            try:
                async with asyncio.timeout(READ_TIMEOUT):
                    return await self._parser.update_device(client, self.address)
            except (BleakError, TimeoutError, OSError):
                # Recover transport errors without adding another measurement read.
                self._disconnected.set()
                await self._disconnect_locked()
                raise

    async def _maintain_connection(self) -> None:
        """Reconnect immediately on disconnect and retry failed attempts every 5s."""
        failure_logged = False
        try:
            while not self._closing:
                try:
                    async with self._lock:
                        await self._connect_locked()
                    failure_logged = False
                except Exception as err:
                    if not failure_logged:
                        _LOGGER.warning(
                            "Unable to keep YC01 %s connected: %s", self.address, err
                        )
                        failure_logged = True
                    else:
                        _LOGGER.debug("YC01 %s reconnect failed: %s", self.address, err)
                    await asyncio.sleep(RECONNECT_DELAY)
                    continue

                # The timeout checks local connection state; it does not read GATT.
                try:
                    async with asyncio.timeout(RECONNECT_DELAY):
                        await self._disconnected.wait()
                except TimeoutError:
                    pass
        finally:
            self._closing = True
            await self._close_client()

    async def _disconnect_locked(self) -> None:
        """Release the current client, retaining it if cleanup fails while connected."""
        self._ready = False
        self._state_changed()
        if (client := self._client) is None:
            return
        try:
            async with asyncio.timeout(DISCONNECT_TIMEOUT):
                await client.disconnect()
        except (BleakError, TimeoutError, OSError):
            if client.is_connected:
                raise
        self._client = None

    async def _close_client(self) -> None:
        """Bound shutdown cleanup and report an adapter that fails to disconnect."""
        try:
            async with self._lock:
                await self._disconnect_locked()
        except (BleakError, TimeoutError, OSError) as err:
            _LOGGER.warning(
                "Could not disconnect YC01 %s during shutdown: %s", self.address, err
            )

    async def async_stop(self) -> None:
        """Stop reconnecting and release the occupied proxy connection."""
        self._closing = True
        if self._task is not None:
            if not self._task.done():
                self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self._close_client()
