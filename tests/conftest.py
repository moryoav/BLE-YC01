"""Mock Bluetooth transport while retaining the real Home Assistant lifecycle."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from bleak import BleakClient
from bleak.backends.device import BLEDevice
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ble_yc01.const import DOMAIN

ADDRESS = "AA:BB:CC:DD:EE:FF"
MEASUREMENT_FRAME = bytes.fromhex("fdaaff76f68aff0ffefbfebafdd9f756fb77")


@pytest.fixture(autouse=True)
def enable_integration(enable_custom_integrations, enable_bluetooth):
    """Enable integration discovery without real Bluetooth hardware."""


@pytest.fixture
def entry(hass):
    """An existing upstream entry."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDRESS, title=ADDRESS, data={})
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def transport():
    """Create a fresh client for each connection and expose disconnect callbacks."""
    transport = SimpleNamespace(
        clients=[],
        connect_errors=[],
        read_data=MEASUREMENT_FRAME,
        device=BLEDevice(ADDRESS, "BLE-YC01", {}),
    )

    def create_client(device, disconnected_callback):
        client = Mock(spec=BleakClient)
        client.is_connected = False
        client.disconnected_callback = disconnected_callback

        async def connect():
            client.is_connected = True
            if transport.connect_errors:
                raise transport.connect_errors.pop(0)

        async def disconnect():
            client.is_connected = False
            disconnected_callback(client)

        client.connect = AsyncMock(side_effect=connect)
        client.disconnect = AsyncMock(side_effect=disconnect)
        client.read_gatt_char = AsyncMock(return_value=transport.read_data)
        transport.clients.append(client)
        return client

    with (
        patch(
            "custom_components.ble_yc01.connection.BleakClient",
            side_effect=create_client,
        ) as factory,
        patch(
            "custom_components.ble_yc01.connection.bluetooth.async_ble_device_from_address",
            return_value=transport.device,
        ) as lookup,
    ):
        transport.factory = factory
        transport.lookup = lookup
        yield transport
