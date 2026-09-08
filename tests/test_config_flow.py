"""Discovery must not open connections before a configuration entry owns them."""

from types import SimpleNamespace
from unittest.mock import patch

from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResultType

from custom_components.ble_yc01.const import CONF_POLL_INTERVAL, DOMAIN

from .conftest import ADDRESS


async def test_bluetooth_discovery(hass, transport):
    """Discovery and confirmation do not probe the device or read FF02."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_BLUETOOTH},
        data=SimpleNamespace(address=ADDRESS, name="BLE-YC01"),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"
    with patch("custom_components.ble_yc01.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == ADDRESS
    assert result["result"].options[CONF_POLL_INTERVAL] == 30
    transport.factory.assert_not_called()


async def test_manual_discovery(hass, transport):
    """The device picker uses advertisement metadata without connecting."""
    with patch(
        "custom_components.ble_yc01.config_flow.async_discovered_service_info",
        return_value=[SimpleNamespace(address=ADDRESS, name="BLE-YC01")],
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
    assert result["result"].options[CONF_POLL_INTERVAL] == 30
    transport.factory.assert_not_called()


async def test_duplicate_discovery(hass, entry, transport):
    """An existing entry keeps its identity and connection ownership."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_BLUETOOTH},
        data=SimpleNamespace(address=ADDRESS, name="BLE-YC01"),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    transport.factory.assert_not_called()


async def test_custom_setup_interval(hass, transport):
    """New devices save the chosen polling interval without a probe."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_BLUETOOTH},
        data=SimpleNamespace(address=ADDRESS, name="BLE-YC01"),
    )
    with patch("custom_components.ble_yc01.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_POLL_INTERVAL: 5}
        )
        await hass.async_block_till_done()
    assert result["result"].options[CONF_POLL_INTERVAL] == 5
    transport.factory.assert_not_called()


async def test_options_default_validation_and_preservation(hass, entry):
    """Old entries default to 30 and reject fractional minutes."""
    hass.config_entries.async_update_entry(entry, options={"unrelated": True})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["data_schema"]({})[CONF_POLL_INTERVAL] == 30
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_POLL_INTERVAL: 1.5}
    )
    assert result["errors"] == {CONF_POLL_INTERVAL: "invalid_interval"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_POLL_INTERVAL: 7}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"unrelated": True, CONF_POLL_INTERVAL: 7}
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["data_schema"]({})[CONF_POLL_INTERVAL] == 7
