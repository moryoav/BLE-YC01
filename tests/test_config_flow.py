"""Exercise discovery and options through Home Assistant's flow manager."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResultType, InvalidData

from custom_components.ble_yc01.const import CONF_KEEP_ALIVE_INTERVAL, DOMAIN

from .conftest import ADDRESS


@pytest.mark.parametrize(
    "saved, expected", [({}, 4), ({CONF_KEEP_ALIVE_INTERVAL: 7}, 7)]
)
async def test_options_default_and_saved(hass, entry, saved, expected):
    """Configure displays the saved value or the four-minute default."""
    hass.config_entries.async_update_entry(entry, options=saved)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["data_schema"]({}) == {CONF_KEEP_ALIVE_INTERVAL: expected}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_KEEP_ALIVE_INTERVAL: 9}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_KEEP_ALIVE_INTERVAL] == 9


@pytest.mark.parametrize("value", [1.5, float("inf")])
async def test_invalid_interval(hass, entry, value):
    """Reject intervals that cannot safely define a whole-minute timer."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_KEEP_ALIVE_INTERVAL: value}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_KEEP_ALIVE_INTERVAL: "invalid_interval"}
    assert entry.options == {}


@pytest.mark.parametrize("value", [0, -1, "invalid", None])
async def test_selector_rejects_invalid_interval(hass, entry, value):
    """Home Assistant rejects invalid numeric input before calling the flow."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_KEEP_ALIVE_INTERVAL: value}
        )
    assert entry.options == {}


async def test_discovery_never_connects(hass, connection, client):
    """Bluetooth discovery and confirmation need only advertisement metadata."""
    discovery = SimpleNamespace(address=ADDRESS, name="BLE-YC01")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=discovery
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"

    with patch("custom_components.ble_yc01.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == ADDRESS
    connection.assert_not_awaited()
    assert client.method_calls == []


async def test_manual_discovery_never_connects(hass, connection, client):
    """The manual device picker does not probe or read any devices."""
    with patch(
        "custom_components.ble_yc01.config_flow.async_discovered_service_info",
        return_value=[
            SimpleNamespace(address=ADDRESS, name="BLE-YC01"),
            SimpleNamespace(address="11:22:33:44:55:66", name="Other device"),
        ],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    assert result["type"] is FlowResultType.FORM
    with patch("custom_components.ble_yc01.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: ADDRESS}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == ADDRESS
    connection.assert_not_awaited()
    assert client.method_calls == []


async def test_duplicate_discovery(hass, entry, connection):
    """Existing upstream entries keep their unique identity."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_BLUETOOTH},
        data=SimpleNamespace(address=ADDRESS, name="BLE-YC01"),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    connection.assert_not_awaited()
