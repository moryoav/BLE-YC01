"""Fixtures for the BLE-YC01 keep-alive experiment."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from bleak import BleakClient
from bleak.backends.device import BLEDevice
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ble_yc01.const import DOMAIN

ADDRESS = "AA:BB:CC:DD:EE:FF"


@pytest.fixture(autouse=True)
def enable_integration(enable_custom_integrations, enable_bluetooth):
    """Load custom integrations with Bluetooth hardware mocked."""


@pytest.fixture
def entry(hass):
    """An existing upstream entry without the new options."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDRESS, title=ADDRESS, data={})
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def ble_device():
    """A device reachable through a Home Assistant Bluetooth adapter."""
    return BLEDevice(ADDRESS, "BLE-YC01", {})


@pytest.fixture
def client():
    """A client whose calls can be checked for any unexpected GATT activity."""
    client = Mock(spec=BleakClient)
    client.disconnect = AsyncMock()
    return client


@pytest.fixture
def connection(client, ble_device):
    """Mock only the transport, leaving Home Assistant lifecycle code real."""
    with (
        patch(
            "custom_components.ble_yc01.BLE_YC01.parser.establish_connection",
            return_value=client,
        ) as connect,
        patch(
            "custom_components.ble_yc01.bluetooth.async_ble_device_from_address",
            return_value=ble_device,
        ),
    ):
        yield connect
