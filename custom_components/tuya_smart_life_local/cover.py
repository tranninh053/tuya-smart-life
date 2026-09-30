from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TuyaSmartLifeRuntime
from .const import DOMAIN
from .coordinator import TuyaSmartLifeCoordinator
from .models import TuyaDeviceDescription

_LOGGER = logging.getLogger(__name__)

OPEN_COMMAND = "open"
CLOSE_COMMAND = "close"
STOP_COMMAND = "stop"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime: TuyaSmartLifeRuntime = hass.data[DOMAIN][entry.entry_id]
    covers = sorted(
        runtime.local.cover_control_dps(),
        key=lambda item: (item[0].is_child, item[0].name, item[1]),
    )
    async_add_entities(
        TuyaDpsCover(runtime.coordinator, runtime, device, dp_id, label)
        for device, dp_id, label in covers
    )


class TuyaDpsCover(CoordinatorEntity[TuyaSmartLifeCoordinator], CoverEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = CoverDeviceClass.GARAGE
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )

    def __init__(
        self,
        coordinator: TuyaSmartLifeCoordinator,
        runtime: TuyaSmartLifeRuntime,
        device: TuyaDeviceDescription,
        dp_id: str,
        label: str,
    ) -> None:
        super().__init__(coordinator)
        self.runtime = runtime
        self.device = device
        self.dp_id = str(dp_id)
        self._remove_dps_listener: CALLBACK_TYPE | None = None
        self._attr_unique_id = f"{device.dev_id}_{self.dp_id}_cover"
        self._attr_name = label
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
        return self.runtime.local.has_local_connection(self.current_device)

    @property
    def is_closed(self) -> bool | None:
        device = self.current_device
        if not device:
            return None
        state = str(device.dps.get(self.dp_id) or "").lower()
        if state in {"close", "closed"}:
            return True
        if state in {"open", "opened"}:
            return False
        return None

    @property
    def is_opening(self) -> bool | None:
        device = self.current_device
        return bool(device and str(device.dps.get(self.dp_id) or "").lower() == "open")

    @property
    def is_closing(self) -> bool | None:
        device = self.current_device
        return bool(device and str(device.dps.get(self.dp_id) or "").lower() == "close")

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
        if not dps or self.dp_id in dps:
            self.async_write_ha_state()

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._async_set_command(OPEN_COMMAND)

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._async_set_command(CLOSE_COMMAND)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self._async_set_command(STOP_COMMAND)

    async def _async_set_command(self, command: str) -> None:
        device = self.current_device
        if not device:
            raise RuntimeError(f"Device {self.device.dev_id} is no longer available")
        response = await self.runtime.local.async_set_dp(device, self.dp_id, command)
        if isinstance(response, dict) and response.get("Error"):
            self._async_write_state_if_added()
            raise RuntimeError(
                f"Unable to set Tuya cover DP {self.dp_id} for {device.dev_id}: "
                f"{response.get('Error')}"
            )
        device.dps[self.dp_id] = command
        self.async_write_ha_state()

    def _async_write_state_if_added(self) -> None:
        if self.entity_id:
            self.async_write_ha_state()
