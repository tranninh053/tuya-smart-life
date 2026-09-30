from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    hubs = sorted(runtime.local.hub_devices(), key=lambda device: device.name)
    devices = sorted(
        runtime.local.devices.values(),
        key=lambda device: (device.is_child, device.name),
    )
    dps_sensors = sorted(
        runtime.local.binary_sensor_dps(),
        key=lambda item: (item[0].is_child, item[0].name, item[1]),
    )
    entities = [
        TuyaLocalConnectedSensor(runtime.coordinator, runtime, device)
        for device in devices
    ]
    entities.extend(
        TuyaHubOnlineSensor(runtime.coordinator, runtime, device) for device in hubs
    )
    entities.extend(
        TuyaDpsBinarySensor(runtime.coordinator, runtime, device, dp_id, value, kind, label)
        for device, dp_id, value, kind, label in dps_sensors
    )
    async_add_entities(entities)


class TuyaHubOnlineSensor(
    CoordinatorEntity[TuyaSmartLifeCoordinator],
    BinarySensorEntity,
):
    _attr_has_entity_name = True
    _attr_name = "Kết nối remote"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: TuyaSmartLifeCoordinator,
        runtime: TuyaSmartLifeRuntime,
        device: TuyaDeviceDescription,
    ) -> None:
        super().__init__(coordinator)
        self.runtime = runtime
        self.device = device
        self._attr_unique_id = f"{device.dev_id}_online"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device.dev_id)},
            "name": device.name.strip() or device.dev_id,
            "manufacturer": "Tuya",
            "model": device.product_id,
        }

    @property
    def current_device(self) -> TuyaDeviceDescription | None:
        current = self.runtime.local.devices.get(self.device.dev_id)
        if current:
            self.device = current
        return current

    @property
    def available(self) -> bool:
        return self.current_device is not None

    @property
    def is_on(self) -> bool | None:
        device = self.current_device
        if not device:
            return None
        if device.online is not None:
            return bool(device.online)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        device = self.current_device
        return self.runtime.local.local_connection_attributes(device)


class TuyaLocalConnectedSensor(
    CoordinatorEntity[TuyaSmartLifeCoordinator],
    BinarySensorEntity,
):
    _attr_has_entity_name = True
    _attr_name = "Kết nối local"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: TuyaSmartLifeCoordinator,
        runtime: TuyaSmartLifeRuntime,
        device: TuyaDeviceDescription,
    ) -> None:
        super().__init__(coordinator)
        self.runtime = runtime
        self.device = device
        self._attr_unique_id = f"{device.dev_id}_local_connected"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device.dev_id)},
            "name": device.name.strip() or device.dev_id,
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
        return self.current_device is not None

    @property
    def is_on(self) -> bool | None:
        device = self.current_device
        if not device:
            return None
        return self.runtime.local.has_local_connection(device)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        device = self.current_device
        return self.runtime.local.local_connection_attributes(device)


class TuyaDpsBinarySensor(
    CoordinatorEntity[TuyaSmartLifeCoordinator],
    BinarySensorEntity,
):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: TuyaSmartLifeCoordinator,
        runtime: TuyaSmartLifeRuntime,
        device: TuyaDeviceDescription,
        dp_id: str,
        initial_value: bool,
        kind: str,
        label: str,
    ) -> None:
        super().__init__(coordinator)
        self.runtime = runtime
        self.device = device
        self.dp_id = str(dp_id)
        self._state = initial_value
        self._remove_dps_listener: CALLBACK_TYPE | None = None
        self._attr_unique_id = f"{device.dev_id}_{self.dp_id}_{kind}"
        self._attr_name = label
        self._attr_device_class = _device_class_for_kind(kind)
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
    def is_on(self) -> bool | None:
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
    def _handle_dps_update(self, dev_id: str, dps: dict[str, object]) -> None:
        if dev_id != self.device.dev_id:
            return
        if not dps:
            self.async_write_ha_state()
            return
        if self.dp_id not in dps:
            return
        for device, dp_id, value, _kind, _label in self.runtime.local.binary_sensor_dps():
            if device.dev_id == dev_id and str(dp_id) == self.dp_id:
                self._state = value
                self.async_write_ha_state()
                return


def _device_class_for_kind(kind: str) -> BinarySensorDeviceClass:
    if kind == "door":
        return BinarySensorDeviceClass.DOOR
    if kind == "motion":
        return BinarySensorDeviceClass.MOTION
    if kind == "occupancy":
        return BinarySensorDeviceClass.OCCUPANCY
    return BinarySensorDeviceClass.PROBLEM
