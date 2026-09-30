from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import time
import json
import logging
from typing import Any

from aiohttp import web
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .api import TuyaMobileApiError, TuyaSmartLifeMobileApi
from .config_flow import mobile_config_from_data
from .const import (
    DOMAIN,
    PLATFORMS,
)
from .coordinator import TuyaSmartLifeCoordinator, selected_home_ids_from_entry
from .local import TuyaLocalRuntime
from .mqtt_cloud import TuyaMqttCloudRuntime, derive_mqtt_config

_LOGGER = logging.getLogger(__name__)

DATA_HTTP_SERVER = f"{DOMAIN}_http_server"
DATAPOINT_HTTP_PORT = 18435
SERVICE_SET_TURN_OFF_COUNTDOWN = "set_turn_offf_countdown"
SERVICE_SET_TURN_OFF_COUNTDOWN_ALIAS = "set_turn_off_countdown"
SERVICE_CLEAR_COUNTDOWN = "clear_countdown"
TIMER_SCHEDULE_CATEGORY = "scheduleCategory"

DEVICE_ID_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("dev_id"): cv.string,
        vol.Optional("device_id"): cv.string,
        vol.Optional("id"): cv.string,
    }
)
SET_TURN_OFF_COUNTDOWN_SCHEMA = DEVICE_ID_SERVICE_SCHEMA.extend(
    {
        vol.Required("minutes"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    }
)


@dataclass(slots=True)
class TuyaSmartLifeRuntime:
    coordinator: TuyaSmartLifeCoordinator
    local: TuyaLocalRuntime
    mqtt: TuyaMqttCloudRuntime


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = {**entry.data, **entry.options}
    config = mobile_config_from_data(data)
    selected_home_ids = selected_home_ids_from_entry(entry)

    local_runtime = TuyaLocalRuntime(hass)
    await local_runtime.async_start()
    coordinator = TuyaSmartLifeCoordinator(
        hass,
        entry,
        local_runtime,
        config,
        selected_home_ids,
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await local_runtime.async_stop()
        raise
    mqtt_runtime = TuyaMqttCloudRuntime(
        hass,
        local_runtime,
        derive_mqtt_config(
            data,
            coordinator.data.session if coordinator.data else None,
            config,
        ),
    )
    await mqtt_runtime.async_start()

    _ensure_hub_registry_entries(hass, entry, local_runtime)
    _remove_stale_registry_entries(hass, entry, local_runtime)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = TuyaSmartLifeRuntime(
        coordinator=coordinator,
        local=local_runtime,
        mqtt=mqtt_runtime,
    )
    _async_register_services(hass)
    await _async_ensure_datapoint_http_server(hass)

    entry.async_on_unload(
        local_runtime.async_add_metadata_listener(
            lambda: _async_notify_coordinator_metadata_update(coordinator)
        )
    )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    runtime: TuyaSmartLifeRuntime | None = hass.data.get(DOMAIN, {}).pop(
        entry.entry_id,
        None,
    )
    if runtime:
        await runtime.mqtt.async_stop()
        await runtime.local.async_stop()
    if not hass.data.get(DOMAIN):
        await _async_stop_datapoint_http_server(hass)
        _async_unregister_services(hass)
    return unload_ok


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_CLEAR_COUNTDOWN):
        return

    async def async_set_turn_off_countdown(call: ServiceCall) -> None:
        runtime, device = _service_device(hass, call)
        minutes = int(call.data["minutes"])
        targets = _switch_timer_targets(runtime, device.dev_id)
        if not targets:
            raise HomeAssistantError(
                f"Thiết bị {device.name} ({device.dev_id}) không có switch DPS để hẹn tắt"
            )
        target_time = dt_util.now() + timedelta(minutes=minutes)
        time_text = target_time.strftime("%H:%M")
        timezone = _timezone_offset_text(target_time)
        await hass.async_add_executor_job(
            _set_turn_off_countdown,
            runtime,
            device.dev_id,
            device.name,
            targets,
            time_text,
            timezone,
            minutes,
        )

    async def async_clear_countdown(call: ServiceCall) -> None:
        runtime, device = _service_device(hass, call)
        fallback_categories = [TIMER_SCHEDULE_CATEGORY] + [
            category for category, _, _ in _switch_timer_targets(runtime, device.dev_id)
        ]
        await hass.async_add_executor_job(
            _clear_countdown,
            runtime,
            device.dev_id,
            fallback_categories,
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_TURN_OFF_COUNTDOWN,
        async_set_turn_off_countdown,
        schema=SET_TURN_OFF_COUNTDOWN_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_TURN_OFF_COUNTDOWN_ALIAS,
        async_set_turn_off_countdown,
        schema=SET_TURN_OFF_COUNTDOWN_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_COUNTDOWN,
        async_clear_countdown,
        schema=DEVICE_ID_SERVICE_SCHEMA,
    )


def _async_unregister_services(hass: HomeAssistant) -> None:
    for service in (
        SERVICE_SET_TURN_OFF_COUNTDOWN,
        SERVICE_SET_TURN_OFF_COUNTDOWN_ALIAS,
        SERVICE_CLEAR_COUNTDOWN,
    ):
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)


def _service_device(
    hass: HomeAssistant,
    call: ServiceCall,
) -> tuple[TuyaSmartLifeRuntime, Any]:
    dev_id = _service_dev_id(hass, call)
    if not dev_id:
        raise HomeAssistantError("Cần nhập dev_id, device_id hoặc id")

    for runtime in hass.data.get(DOMAIN, {}).values():
        device = runtime.local.devices.get(dev_id)
        if device:
            return runtime, device
    raise HomeAssistantError(f"Không tìm thấy thiết bị Tuya: {dev_id}")


def _service_dev_id(hass: HomeAssistant, call: ServiceCall) -> str | None:
    for key in ("dev_id", "id"):
        value = call.data.get(key)
        if value not in (None, ""):
            return str(value)

    device_id = call.data.get("device_id")
    if device_id in (None, ""):
        return None
    device_id = str(device_id)
    if any(
        device_id in runtime.local.devices
        for runtime in hass.data.get(DOMAIN, {}).values()
    ):
        return device_id

    registry = dr.async_get(hass)
    ha_device = registry.async_get(device_id)
    if not ha_device:
        return device_id
    for domain, identifier in ha_device.identifiers:
        if domain == DOMAIN:
            return identifier
    return device_id


def _switch_timer_targets(
    runtime: TuyaSmartLifeRuntime,
    dev_id: str,
) -> list[tuple[str, str, str]]:
    targets: list[tuple[str, str, str]] = []
    for device, dp_id, _, label in runtime.local.switch_button_dps():
        if device.dev_id != dev_id:
            continue
        schema = device.dp_schema.get(str(dp_id), {})
        category = str(schema.get("code") or f"switch_{dp_id}").strip()
        if category:
            targets.append((category, str(dp_id), label))
    return targets


def _set_turn_off_countdown(
    runtime: TuyaSmartLifeRuntime,
    dev_id: str,
    device_name: str,
    targets: list[tuple[str, str, str]],
    time_text: str,
    timezone: str,
    minutes: int,
) -> None:
    api = _service_api(runtime)

    def schedule(session: Any) -> None:
        schedule_category = _device_schedule_category(api, session, dev_id)
        for target_category, dp_id, label in targets:
            category = schedule_category or target_category
            api.add_device_turn_off_timer(
                session,
                dev_id,
                category,
                dp_id,
                time_text,
                timezone,
                f"HA tắt {device_name} {label} sau {minutes} phút",
            )

    _run_with_tuya_session_retry(runtime, api, schedule)
    _LOGGER.info(
        "Scheduled Tuya device %s turn-off at %s for %s switch DPS",
        dev_id,
        time_text,
        len(targets),
    )


def _device_schedule_category(
    api: TuyaSmartLifeMobileApi,
    session: Any,
    dev_id: str,
) -> str | None:
    try:
        categories = api.list_device_timer_categories(session, dev_id)
    except TuyaMobileApiError as err:
        _LOGGER.debug("Unable to list Tuya timer categories for %s: %s", dev_id, err)
        return None
    if TIMER_SCHEDULE_CATEGORY in categories:
        return TIMER_SCHEDULE_CATEGORY
    return None


def _timezone_offset_text(dt: Any) -> str:
    offset = dt.utcoffset()
    if offset is None:
        return "+00:00"
    seconds = int(offset.total_seconds())
    sign = "+" if seconds >= 0 else "-"
    seconds = abs(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    return f"{sign}{hours:02d}:{minutes:02d}"


def _clear_countdown(
    runtime: TuyaSmartLifeRuntime,
    dev_id: str,
    fallback_categories: list[str],
) -> None:
    api = _service_api(runtime)
    removed: list[tuple[str, str]] = []

    def clear(session: Any) -> None:
        nonlocal removed
        removed = api.clear_device_timer_groups(session, dev_id, fallback_categories)

    _run_with_tuya_session_retry(runtime, api, clear)
    _LOGGER.info("Removed %s Tuya timer groups for %s", len(removed), dev_id)


def _run_with_tuya_session_retry(
    runtime: TuyaSmartLifeRuntime,
    api: TuyaSmartLifeMobileApi,
    action: Any,
) -> None:
    try:
        action(_service_session(runtime))
        return
    except TuyaMobileApiError as err:
        if "USER_SESSION_INVALID" not in str(err):
            raise
        _LOGGER.debug("Tuya session expired during service call, logging in again")
    action(api.login())


def _service_session(runtime: TuyaSmartLifeRuntime) -> Any:
    data = runtime.coordinator.data
    if data is None:
        raise TuyaMobileApiError("Tuya session is not ready")
    return data.session


def _service_api(runtime: TuyaSmartLifeRuntime) -> TuyaSmartLifeMobileApi:
    api = TuyaSmartLifeMobileApi(runtime.coordinator.config)
    data = runtime.coordinator.data
    if data and data.session.endpoint:
        api.endpoint = data.session.endpoint
    return api


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _async_notify_coordinator_metadata_update(
    coordinator: TuyaSmartLifeCoordinator,
) -> None:
    if coordinator.data is not None:
        coordinator.async_set_updated_data(coordinator.data)


def _ensure_hub_registry_entries(
    hass: HomeAssistant,
    entry: ConfigEntry,
    local_runtime: TuyaLocalRuntime,
) -> None:
    device_registry = dr.async_get(hass)
    for device in local_runtime.hub_devices():
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, device.dev_id)},
            manufacturer="Tuya",
            model=device.product_id,
            name=device.name.strip() or device.dev_id,
        )


async def _async_ensure_datapoint_http_server(hass: HomeAssistant) -> None:
    if hass.data.get(DATA_HTTP_SERVER):
        return

    async def handle_datapoints(request: web.Request) -> web.Response:
        entry_id = request.query.get("entry_id")
        payload = _datapoint_mapping_payload(hass, entry_id)
        return web.json_response(
            payload,
            dumps=lambda data: json.dumps(data, ensure_ascii=False),
        )

    app = web.Application()
    app.router.add_get("/", handle_datapoints)
    app.router.add_get("/devices", handle_datapoints)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", DATAPOINT_HTTP_PORT)
    try:
        await site.start()
    except OSError as err:
        await runner.cleanup()
        _LOGGER.warning(
            "Unable to start Tuya datapoint debug HTTP server on port %s: %s",
            DATAPOINT_HTTP_PORT,
            err,
        )
        return

    hass.data[DATA_HTTP_SERVER] = {"runner": runner, "site": site}
    _LOGGER.info(
        "Started Tuya datapoint debug HTTP server on port %s",
        DATAPOINT_HTTP_PORT,
    )


async def _async_stop_datapoint_http_server(hass: HomeAssistant) -> None:
    server = hass.data.pop(DATA_HTTP_SERVER, None)
    if not isinstance(server, dict):
        return
    runner = server.get("runner")
    if isinstance(runner, web.AppRunner):
        await runner.cleanup()
        _LOGGER.info("Stopped Tuya datapoint debug HTTP server")


def _datapoint_mapping_payload(
    hass: HomeAssistant,
    entry_id: str | None,
) -> dict[str, Any]:
    runtimes = hass.data.get(DOMAIN, {})
    selected = {
        current_entry_id: runtime
        for current_entry_id, runtime in runtimes.items()
        if entry_id in (None, current_entry_id)
    }
    if entry_id and not selected:
        raise web.HTTPNotFound(text=f"entry_id not found: {entry_id}")

    homes: dict[str, dict[str, Any]] = {}
    for runtime in selected.values():
        _merge_entry_homes(homes, runtime.local)

    return {
        "generated_at": int(time.time()),
        "homes": [
            homes[home_id]
            for home_id in sorted(
                homes,
                key=lambda current_home_id: homes[current_home_id]["name"],
            )
        ],
    }


def _merge_entry_homes(
    homes: dict[str, dict[str, Any]],
    local_runtime: TuyaLocalRuntime,
) -> None:
    switch_map = {
        (device.dev_id, str(dp_id)): label
        for device, dp_id, _, label in local_runtime.switch_button_dps()
    }
    cover_map = {
        (device.dev_id, str(dp_id)): label
        for device, dp_id, label in local_runtime.cover_control_dps()
    }
    number_map = {
        (device.dev_id, str(dp_id)): {"kind": "travel_time", "label": label}
        for device, dp_id, _, label in local_runtime.cover_travel_time_dps()
    }
    select_map = {
        (device.dev_id, str(dp_id)): {"kind": "child_lock", "label": label}
        for device, dp_id, _, label in local_runtime.child_lock_dps()
    }
    binary_map = {
        (device.dev_id, str(dp_id)): {"kind": kind, "label": label}
        for device, dp_id, _, kind, label in local_runtime.binary_sensor_dps()
    }
    sensor_map: dict[tuple[str, str], list[dict[str, str]]] = {}
    for device, dp_id, _, kind, label in local_runtime.environment_sensor_dps():
        sensor_map.setdefault((device.dev_id, str(dp_id)), []).append(
            {"kind": kind, "label": label}
        )
    context_map = {
        device.dev_id: {"state": state, "channels": channels}
        for device, state, channels in local_runtime.context_button_sensors()
    }

    for dev_id, device in sorted(
        local_runtime.devices.items(),
        key=lambda item: (item[1].home_name, item[1].name, item[0]),
    ):
        home = homes.setdefault(
            device.home_id,
            {
                "id": device.home_id,
                "name": device.home_name,
                "devices": {},
                "ir_actions": [],
            },
        )
        home["devices"][dev_id] = _device_datapoint_mapping(
            local_runtime,
            device,
            switch_map,
            cover_map,
            number_map,
            select_map,
            binary_map,
            sensor_map,
            context_map,
        )

    for action in sorted(
        local_runtime.ir_actions.values(),
        key=lambda action: (
            action.home_name,
            action.remote_name,
            action.action_name,
            action.action_id,
        ),
    ):
        home = homes.setdefault(
            action.home_id,
            {
                "id": action.home_id,
                "name": action.home_name,
                "devices": {},
                "ir_actions": [],
            },
        )
        home["ir_actions"].append(_ir_action_mapping(action, local_runtime))


def _device_datapoint_mapping(
    local_runtime: TuyaLocalRuntime,
    device: Any,
    switch_map: dict[tuple[str, str], str],
    cover_map: dict[tuple[str, str], str],
    number_map: dict[tuple[str, str], dict[str, str]],
    select_map: dict[tuple[str, str], dict[str, str]],
    binary_map: dict[tuple[str, str], dict[str, str]],
    sensor_map: dict[tuple[str, str], list[dict[str, str]]],
    context_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    datapoints: dict[str, Any] = {}
    for dp_id, value in sorted(
        device.dps.items(),
        key=lambda item: _dp_sort_key(item[0]),
    ):
        dp_key = str(dp_id)
        mapped_as: list[str] = []
        details: dict[str, Any] = {}
        switch_label = switch_map.get((device.dev_id, dp_key))
        if switch_label:
            mapped_as.append("switch")
            details["switch_label"] = switch_label
        cover_label = cover_map.get((device.dev_id, dp_key))
        if cover_label:
            mapped_as.append("cover")
            details["cover_label"] = cover_label
        number = number_map.get((device.dev_id, dp_key))
        if number:
            mapped_as.append("number")
            details["number"] = number
        select = select_map.get((device.dev_id, dp_key))
        if select:
            mapped_as.append("select")
            details["select"] = select
        binary = binary_map.get((device.dev_id, dp_key))
        if binary:
            mapped_as.append("binary_sensor")
            details["binary_sensor"] = binary
        sensors = sensor_map.get((device.dev_id, dp_key))
        if sensors:
            mapped_as.append("sensor")
            details["sensors"] = sensors
            if len(sensors) == 1:
                details["sensor"] = sensors[0]
        datapoints[dp_key] = {
            "value": value,
            "value_type": type(value).__name__,
            "name": device.dp_names.get(dp_key),
            "schema": device.dp_schema.get(dp_key),
            "mapped_as": mapped_as,
            **details,
        }

    context = context_map.get(device.dev_id)
    if context:
        context = {
            **context,
            "actions": [
                f"{channel}_{press_type}"
                for channel in context.get("channels", [])
                for press_type in ("press", "double", "long")
            ],
        }

    return {
        "name": device.name,
        "home_id": device.home_id,
        "home_name": device.home_name,
        "kind": device.kind,
        "product_id": device.product_id,
        "category": device.category,
        "category_code": device.category_code,
        "category_code_2": device.category_code_2,
        "category_code_3": device.category_code_3,
        "uiid": device.uiid,
        "parent_dev_id": device.parent_dev_id,
        "node_id": device.node_id,
        "online": device.online,
        "ip": device.ip,
        "local_ip": local_runtime.local_ip_for_device(device),
        "local_key": "***hidden***" if device.local_key else None,
        "protocol_version": device.protocol_version,
        "local_connected": local_runtime.has_local_connection(device),
        "local_controllable": device.local_controllable,
        "dp_names": dict(
            sorted(device.dp_names.items(), key=lambda item: _dp_sort_key(item[0]))
        ),
        "dp_schema": dict(
            sorted(device.dp_schema.items(), key=lambda item: _dp_sort_key(item[0]))
        ),
        "dps": datapoints,
        "data_point_info": device.raw.get("dataPointInfo")
        if isinstance(device.raw, dict)
        else None,
        "context_button": context,
        "raw_keys": sorted(device.raw.keys()) if isinstance(device.raw, dict) else [],
    }


def _ir_action_mapping(action: Any, local_runtime: TuyaLocalRuntime) -> dict[str, Any]:
    return {
        "remote_id": action.remote_id,
        "remote_name": action.remote_name,
        "home_id": action.home_id,
        "home_name": action.home_name,
        "hub_dev_id": action.hub_dev_id,
        "publish_target_dev_id": local_runtime._ir_publish_target_dev_id(action),
        "action_id": action.action_id,
        "action_name": action.action_name,
        "action_dps": action.action_dps,
        "report_dps": action.report_dps,
        "product_id": action.product_id,
        "category": action.category,
        "remote_kind": action.remote_kind,
        "dev_type_id": action.dev_type_id,
        "source": action.raw.get("source") if isinstance(action.raw, dict) else None,
    }


def _dp_sort_key(dp_id: Any) -> tuple[int, str]:
    text = str(dp_id)
    return (int(text), text) if text.isdecimal() else (9999, text)


def _remove_stale_registry_entries(
    hass: HomeAssistant,
    entry: ConfigEntry,
    local_runtime: TuyaLocalRuntime,
) -> None:
    active_unique_ids = {
        f"{device.dev_id}_{dp_id}"
        for device, dp_id, _, _ in local_runtime.switch_button_dps()
    }
    active_unique_ids.update(
        f"{device.dev_id}_fan" for device in local_runtime.fan_devices()
    )
    active_unique_ids.update(
        f"{device.dev_id}_{dp_id}_cover"
        for device, dp_id, _ in local_runtime.cover_control_dps()
    )
    active_unique_ids.update(
        f"{device.dev_id}_{dp_id}_travel_time"
        for device, dp_id, _, _ in local_runtime.cover_travel_time_dps()
    )
    active_unique_ids.update(
        f"{device.dev_id}_{dp_id}_child_lock"
        for device, dp_id, _, _ in local_runtime.child_lock_dps()
    )
    active_unique_ids.update(remote.unique_id for remote in local_runtime.ir_fans())
    active_unique_ids.update(remote.unique_id for remote in local_runtime.ir_lights())
    active_unique_ids.update(
        remote.unique_id for remote in local_runtime.ir_media_players()
    )
    active_unique_ids.update(
        f"{device.dev_id}_online" for device in local_runtime.hub_devices()
    )
    active_unique_ids.update(
        f"{device.dev_id}_local_connected"
        for device in local_runtime.devices.values()
    )
    active_unique_ids.update(
        f"{device.dev_id}_local_ip" for device in local_runtime.wifi_ip_devices()
    )
    active_unique_ids.update(
        f"{device.dev_id}_{dp_id}_{kind}"
        for device, dp_id, _, kind, _ in local_runtime.binary_sensor_dps()
    )
    active_unique_ids.update(
        f"{device.dev_id}_{dp_id}_{kind}"
        for device, dp_id, _, kind, _ in local_runtime.environment_sensor_dps()
    )
    active_unique_ids.update(
        f"{device.dev_id}_action"
        for device, _, _ in local_runtime.context_button_sensors()
    )
    active_unique_ids.update(
        action.unique_id for action in local_runtime.ir_action_buttons()
    )
    active_unique_ids.update(
        climate.unique_id for climate in local_runtime.ir_climates()
    )
    entity_registry = er.async_get(hass)
    for entity in list(entity_registry.entities.values()):
        if entity.platform != DOMAIN or entity.config_entry_id != entry.entry_id:
            continue
        if entity.unique_id not in active_unique_ids:
            entity_registry.async_remove(entity.entity_id)

    active_device_ids = set(local_runtime.devices)
    active_device_ids.update(
        action.remote_id for action in local_runtime.ir_action_buttons()
    )
    active_device_ids.update(
        climate.remote_id for climate in local_runtime.ir_climates()
    )
    active_device_ids.update(remote.remote_id for remote in local_runtime.ir_fans())
    active_device_ids.update(remote.remote_id for remote in local_runtime.ir_lights())
    active_device_ids.update(
        remote.remote_id for remote in local_runtime.ir_media_players()
    )
    active_device_ids.update(
        device.dev_id for device in local_runtime.ir_hub_devices()
    )
    device_registry = dr.async_get(hass)
    remove_device = getattr(device_registry, "async_remove_device", None)
    if not callable(remove_device):
        return
    for device in list(device_registry.devices.values()):
        if entry.entry_id not in device.config_entries:
            continue
        tuya_ids = {
            identifier
            for domain, identifier in device.identifiers
            if domain == DOMAIN
        }
        if tuya_ids and tuya_ids.isdisjoint(active_device_ids):
            remove_device(device.id)
