from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TuyaSmartLifeRuntime
from .const import DOMAIN
from .coordinator import TuyaSmartLifeCoordinator
from .models import TuyaDeviceDescription


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime: TuyaSmartLifeRuntime = hass.data[DOMAIN][entry.entry_id]
    numbers = sorted(
        runtime.local.cover_travel_time_dps(),
        key=lambda item: (item[0].is_child, item[0].name, item[1]),
    )
    async_add_entities(
        TuyaTravelTimeNumber(runtime.coordinator, runtime, device, dp_id, value, label)
        for device, dp_id, value, label in numbers
    )


class TuyaTravelTimeNumber(
    CoordinatorEntity[TuyaSmartLifeCoordinator],
    NumberEntity,
):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = "s"

    def __init__(
        self,
        coordinator: TuyaSmartLifeCoordinator,
        runtime: TuyaSmartLifeRuntime,
        device: TuyaDeviceDescription,
        dp_id: str,
        initial_value: float | None,
        label: str,
    ) -> None:
        super().__init__(coordinator)
        self.runtime = runtime
        self.device = device
        self.dp_id = str(dp_id)
        self._state = initial_value
        self._remove_dps_listener: CALLBACK_TYPE | None = None
        self._attr_unique_id = f"{device.dev_id}_{self.dp_id}_travel_time"
        self._attr_name = label
        self._attr_native_min_value = _scaled_property_number(device, self.dp_id, "min", 1)
        self._attr_native_max_value = _scaled_property_number(
            device,
            self.dp_id,
            "max",
            86400,
        )
        self._attr_native_step = _scaled_property_number(device, self.dp_id, "step", 1)
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
    def native_value(self) -> float | None:
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
        if self.dp_id not in dps:
            return
        value = _normalize_schema_value(dps.get(self.dp_id), self.device, self.dp_id)
        if value is None:
            return
        self._state = value
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        device = self.current_device
        if not device:
            raise RuntimeError(f"Device {self.device.dev_id} is no longer available")
        raw_value = _raw_schema_value(value, device, self.dp_id)
        response = await self.runtime.local.async_set_dp(device, self.dp_id, raw_value)
        if isinstance(response, dict) and response.get("Error"):
            self._async_write_state_if_added()
            raise RuntimeError(
                f"Unable to set Tuya number DP {self.dp_id} for {device.dev_id}: "
                f"{response.get('Error')}"
            )
        device.dps[self.dp_id] = raw_value
        self._state = float(value)
        self.async_write_ha_state()

    def _async_write_state_if_added(self) -> None:
        if self.entity_id:
            self.async_write_ha_state()


def _schema_scale(device: TuyaDeviceDescription, dp_id: str) -> int:
    schema = device.dp_schema.get(str(dp_id), {})
    prop = schema.get("property") if isinstance(schema, dict) else None
    if not isinstance(prop, dict):
        return 0
    try:
        return max(0, int(prop.get("scale", 0)))
    except (TypeError, ValueError):
        return 0


def _scaled_property_number(
    device: TuyaDeviceDescription,
    dp_id: str,
    key: str,
    fallback: float,
) -> float:
    schema = device.dp_schema.get(str(dp_id), {})
    prop = schema.get("property") if isinstance(schema, dict) else None
    if not isinstance(prop, dict):
        return fallback
    try:
        number = float(prop.get(key, fallback))
    except (TypeError, ValueError):
        return fallback
    scale = _schema_scale(device, dp_id)
    if scale > 0:
        return number / (10**scale)
    return number


def _normalize_schema_value(
    value: Any,
    device: TuyaDeviceDescription,
    dp_id: str,
) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    scale = _schema_scale(device, dp_id)
    if scale > 0:
        return number / (10**scale)
    return number


def _raw_schema_value(value: float, device: TuyaDeviceDescription, dp_id: str) -> int:
    scale = _schema_scale(device, dp_id)
    return int(round(float(value) * (10**scale)))
