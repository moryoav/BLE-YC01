"""Advertisement RSSI diagnostics must not interfere with measurements."""

from datetime import timedelta
from time import monotonic
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from homeassistant.components import bluetooth
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.ble_yc01.const import DOMAIN

from .conftest import ADDRESS
from .test_connection import advance, setup_entry


def rssi_id(hass):
    return er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{ADDRESS}_rssi")


def report(rssi=-65, source="proxy-a", age=0):
    return SimpleNamespace(
        address=ADDRESS, rssi=rssi, source=source, time=monotonic() - age
    )


@pytest.fixture
def advertisements():
    cancel = Mock()
    with (
        patch(
            "custom_components.ble_yc01.signal_strength.bluetooth.async_last_service_info",
            return_value=None,
        ) as latest,
        patch(
            "custom_components.ble_yc01.signal_strength.bluetooth.async_register_callback",
            return_value=cancel,
        ) as subscribe,
    ):
        yield SimpleNamespace(latest=latest, subscribe=subscribe, cancel=cancel)


async def test_cached_rssi_preserves_timestamp(
    hass, entry, transport, freezer, advertisements
):
    advertisements.latest.return_value = report(age=120)
    await setup_entry(hass, entry)
    state = hass.states.get(rssi_id(hass))
    assert state.state == "-65"
    assert state.attributes["device_class"] == "signal_strength"
    assert state.attributes["unit_of_measurement"] == "dBm"
    assert state.attributes["source"] == "proxy-a"
    assert dt_util.parse_datetime(
        state.attributes["last_received"]
    ) == dt_util.utcnow() - timedelta(seconds=120)
    registry = er.async_get(hass)
    assert (
        registry.async_get(rssi_id(hass)).entity_category
        is er.EntityCategory.DIAGNOSTIC
    )
    chlorine = registry.async_get_entity_id("sensor", DOMAIN, f"{ADDRESS} _cloro")
    assert (
        registry.async_get(rssi_id(hass)).device_id
        == registry.async_get(chlorine).device_id
    )
    await advance(hass, freezer, 300)
    assert (
        hass.states.get(rssi_id(hass)).attributes["last_received"]
        == state.attributes["last_received"]
    )
    transport.clients[0].read_gatt_char.assert_awaited_once()


async def test_passive_updates_preserve_schedule(
    hass, entry, transport, freezer, advertisements
):
    await setup_entry(hass, entry)
    assert hass.states.get(rssi_id(hass)).state == "unavailable"
    args = advertisements.subscribe.call_args.args
    assert args[2] == {"address": ADDRESS, "connectable": True}
    assert args[3] is bluetooth.BluetoothScanningMode.PASSIVE
    callback = args[1]
    await advance(hass, freezer, 900)
    advertisements.latest.return_value = report(-50, "preferred-proxy")
    callback(report(-80, "other-proxy"), bluetooth.BluetoothChange.ADVERTISEMENT)
    state = hass.states.get(rssi_id(hass))
    assert state.state == "-50"
    assert state.attributes["source"] == "preferred-proxy"
    client = transport.clients[0]
    client.read_gatt_char.assert_awaited_once()
    await advance(hass, freezer, 901)
    assert client.read_gatt_char.await_count == 2
    assert transport.factory.call_count == 1
    client.disconnect.assert_not_awaited()
    assert await hass.config_entries.async_unload(entry.entry_id)
    advertisements.cancel.assert_called_once()


async def test_rssi_updates_with_polling_disabled(
    hass, entry, transport, advertisements
):
    hass.config_entries.async_update_entry(entry, pref_disable_polling=True)
    await setup_entry(hass, entry)
    callback = advertisements.subscribe.call_args.args[1]
    callback(report(-72), bluetooth.BluetoothChange.ADVERTISEMENT)
    assert hass.states.get(rssi_id(hass)).state == "-72"
    callback(report(127), bluetooth.BluetoothChange.ADVERTISEMENT)
    assert hass.states.get(rssi_id(hass)).state == "-72"
    transport.clients[0].read_gatt_char.assert_awaited_once()
