"""Discovery and keep-alive options for YC01 BLE."""

from __future__ import annotations

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
from homeassistant.helpers import selector

from .const import CONF_KEEP_ALIVE_INTERVAL, DEFAULT_KEEP_ALIVE_INTERVAL, DOMAIN


def validate_interval(value: Any) -> int:
    """Accept positive whole minutes without silently truncating fractions."""
    try:
        interval = int(value)
        if isinstance(value, bool) or float(value) != interval or interval < 1:
            raise ValueError
    except (TypeError, ValueError, OverflowError) as err:
        raise vol.Invalid("Expected a positive whole number of minutes") from err
    return interval


class YC01ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Discover devices without opening a connection or reading FF02."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize discovered device choices."""
        self._discovered_devices: dict[str, str] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> YC01OptionsFlow:
        """Expose the keep-alive interval under Configure."""
        return YC01OptionsFlow()

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Discover the device using advertisement metadata only."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self.context["title_placeholders"] = {"name": discovery_info.address}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm Bluetooth discovery."""
        if user_input is not None:
            return self.async_create_entry(
                title=self.context["title_placeholders"]["name"], data={}
            )
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders=self.context["title_placeholders"],
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Choose a connectable device from cached advertisements."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=address, data={})

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
            data_schema=vol.Schema(
                {vol.Required(CONF_ADDRESS): vol.In(self._discovered_devices)}
            ),
        )


class YC01OptionsFlow(OptionsFlow):
    """Configure the interval in minutes for each device."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show and save the keep-alive interval."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                interval = validate_interval(user_input[CONF_KEEP_ALIVE_INTERVAL])
            except (vol.Invalid, KeyError):
                errors[CONF_KEEP_ALIVE_INTERVAL] = "invalid_interval"
            else:
                return self.async_create_entry(
                    title="",
                    data={
                        **self.config_entry.options,
                        CONF_KEEP_ALIVE_INTERVAL: interval,
                    },
                )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_KEEP_ALIVE_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_KEEP_ALIVE_INTERVAL, DEFAULT_KEEP_ALIVE_INTERVAL
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1, step=1, mode=selector.NumberSelectorMode.BOX
                        )
                    ),
                }
            ),
            errors=errors,
        )
