"""Discovery must not open connections before a configuration entry owns them."""

from types import SimpleNamespace
from unittest.mock import patch

from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResultType

from custom_components.ble_yc01.const import DOMAIN

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
