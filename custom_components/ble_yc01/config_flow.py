"""Discover YC01 devices without opening temporary Bluetooth connections."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL, DOMAIN


def polling_schema(default: int = DEFAULT_POLL_INTERVAL) -> vol.Schema:
    """Show the measurement interval in minutes."""
    return vol.Schema(
        {
            vol.Required(CONF_POLL_INTERVAL, default=default): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="min",
                )
            )
        }
    )


def interval_errors(user_input: dict[str, Any]) -> dict[str, str]:
    """Reject fractional or unrepresentable intervals before saving."""
    value = user_input[CONF_POLL_INTERVAL]
    if not float(value).is_integer() or value < 1:
        return {CONF_POLL_INTERVAL: "invalid_interval"}
    try:
        timedelta(minutes=value)
    except OverflowError:
        return {CONF_POLL_INTERVAL: "invalid_interval"}
    return {}


class YC01ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Use advertisement metadata; the configured entry owns the connection."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> YC01OptionsFlow:
        """Allow existing entries to change their measurement interval."""
        return YC01OptionsFlow()

    def __init__(self) -> None:
        self._discovered_devices: dict[str, str] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle discovery without connecting or reading characteristics."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self.context["title_placeholders"] = {"name": discovery_info.address}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm Bluetooth discovery."""
        errors = {}
        if user_input is not None and not (errors := interval_errors(user_input)):
            return self.async_create_entry(
                title=self.context["title_placeholders"]["name"],
                data={},
                options={CONF_POLL_INTERVAL: int(user_input[CONF_POLL_INTERVAL])},
            )
        return self.async_show_form(
            step_id="bluetooth_confirm",
            data_schema=polling_schema(),
            errors=errors,
            description_placeholders=self.context["title_placeholders"],
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Choose a connectable device from cached advertisements."""
        errors = {}
        if user_input is not None and not (errors := interval_errors(user_input)):
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=address,
                data={},
                options={CONF_POLL_INTERVAL: int(user_input[CONF_POLL_INTERVAL])},
            )

        current_addresses = self._async_current_ids()
        for discovery_info in async_discovered_service_info(
            self.hass, connectable=True
        ):
            if (
                discovery_info.address not in current_addresses
                and discovery_info.name.startswith("BLE-YC01")
            ):
                self._discovered_devices[discovery_info.address] = (
                    discovery_info.address
                )
        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=polling_schema().extend(
                {vol.Required(CONF_ADDRESS): vol.In(self._discovered_devices)}
            ),
        )


class YC01OptionsFlow(OptionsFlow):
    """Change polling without reloading the entry or disconnecting."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure the measurement interval for an existing device."""
        errors = {}
        if user_input is not None and not (errors := interval_errors(user_input)):
            return self.async_create_entry(
                title="",
                data={
                    **self.config_entry.options,
                    CONF_POLL_INTERVAL: int(user_input[CONF_POLL_INTERVAL]),
                },
            )
        return self.async_show_form(
            step_id="init",
            errors=errors,
            data_schema=polling_schema(
                self.config_entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
            ),
        )
