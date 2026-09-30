from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TuyaSmartLifeRuntime
from .const import DOMAIN
from .coordinator import TuyaSmartLifeCoordinator
from .models import TuyaDeviceDescription

CHILD_LOCK_OPTIONS = ["off", "on"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime: TuyaSmartLifeRuntime = hass.data[DOMAIN][entry.entry_id]
    selects = sorted(
        runtime.local.child_lock_dps(),
        key=lambda item: (item[0].is_child, item[0].name, item[1]),
    )
    async_add_entities(
        TuyaChildLockSelect(runtime.coordinator, runtime, device, dp_id, value, label)
        for device, dp_id, value, label in selects
    )


class TuyaChildLockSelect(
    CoordinatorEntity[TuyaSmartLifeCoordinator],
    SelectEntity,
):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = CHILD_LOCK_OPTIONS

    def __init__(
        self,
        coordinator: TuyaSmartLifeCoordinator,
        runtime: TuyaSmartLifeRuntime,
        device: TuyaDeviceDescription,
        dp_id: str,
        initial_value: bool | None,
        label: str,
    ) -> None:
        super().__init__(coordinator)
        self.runtime = runtime
        self.device = device
        self.dp_id = str(dp_id)
        self._state = None if initial_value is None else "on" if initial_value else "off"
        self._remove_dps_listener: CALLBACK_TYPE | None = None
        self._attr_unique_id = f"{device.dev_id}_{self.dp_id}_child_lock"
        self._attr_name = label
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device.dev_id)},
            "name": device.name,
            "manufacturer": "Tuya",
            "model": device.product_id,
        }
        if device.parent_dev_id:
            self._attr_device_info["via_device"] = (DOMAIN, device.parent_dev_id)

    @property
    def current_device(self) -> TuyaDeviceDescription | None:
        current = self.runtime.local.devices.get(self.device.dev_id)
        if current:
            self.device = current
        return current

    @property
    def available(self) -> bool:
        return self.runtime.local.has_local_connection(self.current_device)

    @property
    def current_option(self) -> str | None:
        return self._state

    async def async_added_to_hass(self) -> None:
        self._remove_dps_listener = self.runtime.local.async_add_dps_listener(
            self._handle_dps_update
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_dps_listener:
            self._remove_dps_listener()
            self._remove_dps_listener = None

    @callback
    def _handle_dps_update(self, dev_id: str, dps: dict[str, Any]) -> None:
        if dev_id != self.device.dev_id:
            return
        if not dps:
            self.async_write_ha_state()
            return
        value = dps.get(self.dp_id)
        if isinstance(value, bool):
            self._state = "on" if value else "off"
            self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        if option not in CHILD_LOCK_OPTIONS:
            raise ValueError(f"Unsupported child lock option: {option}")
        device = self.current_device
        if not device:
            raise RuntimeError(f"Device {self.device.dev_id} is no longer available")
        value = option == "on"
        response = await self.runtime.local.async_set_dp(device, self.dp_id, value)
        if isinstance(response, dict) and response.get("Error"):
            self._async_write_state_if_added()
            raise RuntimeError(
                f"Unable to set Tuya child lock DP {self.dp_id} for {device.dev_id}: "
                f"{response.get('Error')}"
            )
        device.dps[self.dp_id] = value
        self._state = option
        self.async_write_ha_state()

    def _async_write_state_if_added(self) -> None:
        if self.entity_id:
            self.async_write_ha_state()
