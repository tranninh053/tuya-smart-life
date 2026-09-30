from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TuyaSmartLifeRuntime
from .api import TuyaSmartLifeMobileApi
from .const import (
    CONF_MQTT_UNLOCK_DPS,
    DOMAIN,
)
from .coordinator import TuyaSmartLifeCoordinator
from .models import TuyaDeviceDescription

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime: TuyaSmartLifeRuntime = hass.data[DOMAIN][entry.entry_id]
    entities = [
        TuyaWifiLock(runtime.coordinator, runtime, entry, device)
        for device in runtime.local.devices.values()
        if is_wifi_lock(device)
    ]
    async_add_entities(entities)


class TuyaWifiLock(CoordinatorEntity[TuyaSmartLifeCoordinator], LockEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: TuyaSmartLifeCoordinator,
        runtime: TuyaSmartLifeRuntime,
        entry: ConfigEntry,
        device: TuyaDeviceDescription,
    ) -> None:
        super().__init__(coordinator)
        self.runtime = runtime
        self.entry = entry
        self.device = device
        self._attr_unique_id = f"{device.dev_id}_wifi_lock"
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
        return bool(self.current_device)

    @property
    def is_locked(self) -> bool | None:
        device = self.current_device
        if not device:
            return None
        # Tuya lock products vary. Avoid claiming a lock state until a product
        # specific DP is mapped; event sensors expose the realtime details.
        return None

    async def async_unlock(self, **kwargs: Any) -> None:
        device = self.current_device
        if not device:
            raise RuntimeError(
                f"Tuya lock {self.device.dev_id} is no longer available"
            )
        await async_publish_lock_unlock(self.runtime, self.entry, device)


async def async_publish_lock_unlock(
    runtime: TuyaSmartLifeRuntime,
    entry: ConfigEntry,
    device: TuyaDeviceDescription,
) -> None:
    data = {**entry.data, **entry.options}
    try:
        await runtime.coordinator.hass.async_add_executor_job(
            _remote_unlock_lock,
            runtime,
            device,
        )
        return
    except Exception as err:
        dps = _unlock_dps_from_options(data)
        if not dps or not runtime.mqtt.config:
            raise RuntimeError(
                f"Unable to unlock Tuya lock {device.dev_id} through mobile API: {err}"
            ) from err
        _LOGGER.warning(
            "Tuya mobile API unlock failed for %s; falling back to MQTT DPS: %s",
            device.dev_id,
            err,
        )

    dps = _unlock_dps_from_options(data)
    _LOGGER.warning("Publishing Tuya MQTT unlock DPS to %s", device.dev_id)
    await runtime.mqtt.async_publish_dps(device, dps)


def mqtt_unlock_configured(entry: ConfigEntry) -> bool:
    data = {**entry.data, **entry.options}
    try:
        return bool(_unlock_dps_from_options(data))
    except Exception:
        return False


def _remote_unlock_lock(
    runtime: TuyaSmartLifeRuntime,
    device: TuyaDeviceDescription,
) -> bool:
    api = TuyaSmartLifeMobileApi(runtime.coordinator.config)
    session = runtime.coordinator.data.session if runtime.coordinator.data else None
    if session and session.endpoint:
        api.endpoint = session.endpoint
    if not session:
        session = api.login()
    src_dev_id = _remote_unlock_source_dev_id(device)
    _LOGGER.warning(
        "Calling Tuya mobile remote unlock API srcDevId=%s destDevId=%s",
        src_dev_id,
        device.dev_id,
    )
    return api.remote_unlock_lock(session, src_dev_id, device.dev_id)


def _remote_unlock_source_dev_id(device: TuyaDeviceDescription) -> str:
    raw = device.raw if isinstance(device.raw, dict) else {}
    for key in ("srcDevId", "sourceDevId", "cameraDevId", "doorbellDevId"):
        value = raw.get(key)
        if value:
            return str(value)
    return device.dev_id


def _unlock_dps_from_options(data: dict[str, Any]) -> dict[str, Any]:
    raw = data.get(CONF_MQTT_UNLOCK_DPS)
    if isinstance(raw, dict):
        return {str(key): value for key, value in raw.items()}
    if not isinstance(raw, str) or not raw.strip():
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError("mqtt_unlock_dps must be a JSON object")
    return {str(key): value for key, value in parsed.items()}


def is_wifi_lock(device: TuyaDeviceDescription) -> bool:
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
    if any(
        marker in hay for marker in ("lock", "door lock", "khóa", "khoa", "eyecat")
    ):
        return True
    return device.product_id in {"yqvgqnm90wrljrn0"}
