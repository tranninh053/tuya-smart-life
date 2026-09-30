from __future__ import annotations

import json
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    PERCENTAGE,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TuyaSmartLifeRuntime
from .const import DOMAIN
from .coordinator import TuyaSmartLifeCoordinator
from .models import TuyaDeviceDescription
from .mqtt_cloud import decode_lock_media_payload

LOCK_SENSOR_DPS = {
    "1": "Trạng thái khóa 1",
    "2": "Trạng thái khóa 2",
    "3": "Trạng thái khóa 3",
    "5": "Cách mở khóa 5",
    "6": "Cách mở khóa 6",
    "7": "Cách mở khóa 7",
    "8": "Lỗi cuối",
    "9": "Trạng thái khóa 9",
    "11": "Pin",
    "19": "Cạy phá",
    "45": "Trạng thái khóa 45",
    "46": "Cảnh báo 46",
    "47": "Cảnh báo 47",
    "49": "Dữ liệu khóa 49",
    "55": "Cảnh báo 55",
    "57": "Dữ liệu khóa 57",
    "58": "Cảnh báo 58",
    "63": "Dữ liệu khóa 63",
    "65": "Chiều motor",
    "68": "Cảnh báo 68",
    "69": "Trạng thái khóa 69",
    "102": "Chế độ",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime: TuyaSmartLifeRuntime = hass.data[DOMAIN][entry.entry_id]
    buttons = sorted(
        runtime.local.context_button_sensors(),
        key=lambda item: (item[0].is_child, item[0].name),
    )
    environment_sensors = sorted(
        runtime.local.environment_sensor_dps(),
        key=lambda item: (item[0].is_child, item[0].name, item[1]),
    )
    entities: list[SensorEntity] = [
        TuyaContextButtonSensor(runtime.coordinator, runtime, device, state, channels)
        for device, state, channels in buttons
    ]
    entities.extend(
        TuyaDpsSensor(runtime.coordinator, runtime, device, dp_id, value, kind, label)
        for device, dp_id, value, kind, label in environment_sensors
    )
    entities.extend(
        TuyaLocalIpSensor(runtime.coordinator, runtime, device)
        for device in sorted(runtime.local.wifi_ip_devices(), key=lambda item: item.name)
    )
    for device in sorted(runtime.local.devices.values(), key=lambda item: item.name):
        if not _is_wifi_lock(device):
            continue
        for dp_id in LOCK_SENSOR_DPS:
            if dp_id in device.dps:
                entities.append(
                    TuyaWifiLockDpsSensor(runtime.coordinator, runtime, device, dp_id)
                )
        entities.append(TuyaWifiLockEventSensor(runtime.coordinator, runtime, device))
        entities.append(TuyaWifiLockMediaSensor(runtime.coordinator, runtime, device))
    async_add_entities(entities)


class TuyaContextButtonSensor(
    CoordinatorEntity[TuyaSmartLifeCoordinator],
    SensorEntity,
):
    _attr_has_entity_name = True
    _attr_name = "Hành động"
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: TuyaSmartLifeCoordinator,
        runtime: TuyaSmartLifeRuntime,
        device: TuyaDeviceDescription,
        initial_state: str | None,
        channels: list[str],
    ) -> None:
        super().__init__(coordinator)
        self.runtime = runtime
        self.device = device
        self._state = initial_state
        self._remove_dps_listener: CALLBACK_TYPE | None = None
        self._attr_unique_id = f"{device.dev_id}_action"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device.dev_id)},
            "name": device.name,
            "manufacturer": "Tuya",
            "model": device.product_id,
        }
        self._attr_extra_state_attributes = {
            "channels": channels,
            "actions": [
                f"{channel}_{press_type}"
                for channel in channels
                for press_type in ("press", "double", "long")
            ],
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
    def native_value(self) -> str | None:
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
        for device, state, channels in self.runtime.local.context_button_sensors():
            if device.dev_id != dev_id:
                continue
            if state is None:
                return
            self._state = state
            self._attr_extra_state_attributes = {
                "channels": channels,
                "actions": [
                    f"{channel}_{press_type}"
                    for channel in channels
                    for press_type in ("press", "double", "long")
                ],
            }
            self.async_write_ha_state()
            return


class TuyaDpsSensor(
    CoordinatorEntity[TuyaSmartLifeCoordinator],
    SensorEntity,
):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: TuyaSmartLifeCoordinator,
        runtime: TuyaSmartLifeRuntime,
        device: TuyaDeviceDescription,
        dp_id: str,
        initial_value: float,
        kind: str,
        label: str,
    ) -> None:
        super().__init__(coordinator)
        self.runtime = runtime
        self.device = device
        self.dp_id = str(dp_id)
        self.kind = kind
        self._state = initial_value
        self._remove_dps_listener: CALLBACK_TYPE | None = None
        self._attr_unique_id = f"{device.dev_id}_{self.dp_id}_{kind}"
        self._attr_name = label
        self._attr_device_class = _device_class_for_kind(kind)
        self._attr_native_unit_of_measurement = _unit_for_kind(kind, device, self.dp_id)
        self._attr_state_class = _state_class_for_kind(kind, device, self.dp_id)
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
    def native_value(self) -> float:
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
        for device, dp_id, value, kind, _label in self.runtime.local.environment_sensor_dps():
            if device.dev_id == dev_id and str(dp_id) == self.dp_id and kind == self.kind:
                self._state = value
                self.async_write_ha_state()
                return


class TuyaLocalIpSensor(
    CoordinatorEntity[TuyaSmartLifeCoordinator],
    SensorEntity,
):
    _attr_has_entity_name = True
    _attr_name = "IP local"
    _attr_icon = "mdi:ip-network"
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
        self._attr_unique_id = f"{device.dev_id}_local_ip"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device.dev_id)},
            "name": device.name,
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
    def native_value(self) -> str | None:
        return self.runtime.local.local_ip_for_device(self.current_device)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.runtime.local.local_connection_attributes(self.current_device)


def _device_class_for_kind(kind: str) -> SensorDeviceClass | None:
    if kind == "temperature":
        return SensorDeviceClass.TEMPERATURE
    if kind == "humidity":
        return SensorDeviceClass.HUMIDITY
    if kind == "energy":
        return SensorDeviceClass.ENERGY
    if kind == "current":
        return SensorDeviceClass.CURRENT
    if kind == "power":
        return SensorDeviceClass.POWER
    if kind == "voltage":
        return SensorDeviceClass.VOLTAGE
    return None


def _unit_for_kind(
    kind: str,
    device: TuyaDeviceDescription,
    dp_id: str,
) -> str | None:
    schema = device.dp_schema.get(str(dp_id), {})
    prop = schema.get("property") if isinstance(schema, dict) else None
    unit = str(prop.get("unit") or "") if isinstance(prop, dict) else ""
    normalized = unit.replace("·", "").replace(" ", "").lower()
    if normalized in ("kwh", "kw*h"):
        return UnitOfEnergy.KILO_WATT_HOUR
    if normalized == "wh":
        return "Wh"
    if normalized == "ma":
        return "mA"
    if normalized == "a":
        return "A"
    if normalized == "v":
        return UnitOfElectricPotential.VOLT
    if normalized == "w":
        return UnitOfPower.WATT
    if unit in ("℃", "°C"):
        return UnitOfTemperature.CELSIUS
    if kind == "temperature":
        return UnitOfTemperature.CELSIUS
    if kind == "humidity":
        return PERCENTAGE
    if kind == "energy":
        return UnitOfEnergy.KILO_WATT_HOUR
    if kind == "current":
        schema_type = str(schema.get("type") or "").lower()
        code = str(schema.get("code") or "").lower()
        if schema_type == "raw" and code.startswith("phase_"):
            return "A"
        return "mA"
    if kind == "power":
        return UnitOfPower.WATT
    if kind == "voltage":
        return UnitOfElectricPotential.VOLT
    return unit or None


def _state_class_for_kind(
    kind: str,
    device: TuyaDeviceDescription,
    dp_id: str,
) -> SensorStateClass | None:
    if kind == "energy":
        code = str(device.dp_schema.get(str(dp_id), {}).get("code") or "")
        if "total" in code or code in {"add_ele", "forward_energy_total"}:
            return SensorStateClass.TOTAL_INCREASING
        return SensorStateClass.TOTAL
    if kind in ("current", "humidity", "power", "temperature", "voltage"):
        return SensorStateClass.MEASUREMENT
    return None


class TuyaWifiLockDpsSensor(
    CoordinatorEntity[TuyaSmartLifeCoordinator],
    SensorEntity,
):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: TuyaSmartLifeCoordinator,
        runtime: TuyaSmartLifeRuntime,
        device: TuyaDeviceDescription,
        dp_id: str,
    ) -> None:
        super().__init__(coordinator)
        self.runtime = runtime
        self.device = device
        self.dp_id = str(dp_id)
        self._state = _string_state(device.dps.get(self.dp_id))
        self._remove_dps_listener: CALLBACK_TYPE | None = None
        self._attr_unique_id = f"{device.dev_id}_lock_dp_{self.dp_id}"
        self._attr_name = LOCK_SENSOR_DPS.get(self.dp_id, f"DP khóa {self.dp_id}")
        self._attr_device_info = _lock_device_info(device)

    @property
    def native_value(self) -> str | int | float | None:
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
        if dev_id != self.device.dev_id or self.dp_id not in dps:
            return
        self._state = _string_state(dps.get(self.dp_id))
        self.async_write_ha_state()


class TuyaWifiLockEventSensor(
    CoordinatorEntity[TuyaSmartLifeCoordinator],
    SensorEntity,
):
    _attr_has_entity_name = True
    _attr_name = "Sự kiện MQTT cuối"
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: TuyaSmartLifeCoordinator,
        runtime: TuyaSmartLifeRuntime,
        device: TuyaDeviceDescription,
    ) -> None:
        super().__init__(coordinator)
        self.runtime = runtime
        self.device = device
        self._state: str | None = None
        self._remove_dps_listener: CALLBACK_TYPE | None = None
        self._attr_unique_id = f"{device.dev_id}_lock_last_mqtt_event"
        self._attr_device_info = _lock_device_info(device)

    @property
    def native_value(self) -> str | None:
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
    def _handle_dps_update(self, dev_id: str, _dps: dict[str, Any]) -> None:
        if dev_id != self.device.dev_id:
            return
        event = self.runtime.local.mqtt_events.get(dev_id)
        if not isinstance(event, dict):
            return
        self._state = _event_summary(event)
        self._attr_extra_state_attributes = {"event": event}
        self.async_write_ha_state()


class TuyaWifiLockMediaSensor(
    CoordinatorEntity[TuyaSmartLifeCoordinator],
    SensorEntity,
):
    _attr_has_entity_name = True
    _attr_name = "Sự kiện media cuối"
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: TuyaSmartLifeCoordinator,
        runtime: TuyaSmartLifeRuntime,
        device: TuyaDeviceDescription,
    ) -> None:
        super().__init__(coordinator)
        self.runtime = runtime
        self.device = device
        self._state: str | None = None
        self._remove_dps_listener: CALLBACK_TYPE | None = None
        self._attr_unique_id = f"{device.dev_id}_lock_last_media_event"
        self._attr_device_info = _lock_device_info(device)

    @property
    def native_value(self) -> str | None:
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
        payload = dps.get("212")
        if payload is None:
            event = self.runtime.local.mqtt_events.get(dev_id)
            event_dps = _event_dps(event)
            payload = event_dps.get("212")
        decoded = decode_lock_media_payload(payload)
        if not decoded:
            return
        self._state = str(decoded.get("cmd") or decoded.get("type") or "media")
        self._attr_extra_state_attributes = decoded
        self.async_write_ha_state()


def _lock_device_info(device: TuyaDeviceDescription) -> dict[str, Any]:
    return {
        "identifiers": {(DOMAIN, device.dev_id)},
        "name": device.name,
        "manufacturer": "Tuya",
        "model": device.product_id,
    }


def _string_state(value: Any) -> str | int | float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))[:255]


def _event_summary(event: dict[str, Any]) -> str:
    protocol = event.get("protocol")
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    dps = data.get("dps") if isinstance(data, dict) else None
    if isinstance(dps, dict) and dps:
        return "dps:" + ",".join(str(key) for key in sorted(dps))
    if data.get("warnLevel") is not None:
        return f"warn:{data.get('warnLevel')}"
    if event.get("type"):
        return str(event["type"])
    return f"protocol:{protocol}"


def _event_dps(event: Any) -> dict[str, Any]:
    if not isinstance(event, dict):
        return {}
    data = event.get("data")
    if not isinstance(data, dict):
        return {}
    dps = data.get("dps")
    if not isinstance(dps, dict):
        return {}
    return {str(key): value for key, value in dps.items()}


def _is_wifi_lock(device: TuyaDeviceDescription) -> bool:
    if device.is_child or device.is_hub:
        return False
    hay = " ".join(
        str(value or "")
        for value in (
            device.name,
            device.product_id,
            device.category,
            device.category_code,
        )
    ).lower()
    if any(marker in hay for marker in ("lock", "door lock", "khóa", "khoa", "eyecat")):
        return True
    return device.product_id in {"yqvgqnm90wrljrn0"}
