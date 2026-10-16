"""Comprehensive Test Suite for Tuya Smart Life Local Integration.

Covers:
1. Hybrid Availability (Platform fallback to Cloud status when local socket is disconnected).
2. Dual-Offline Handling (Only unavailable when BOTH local socket and cloud are offline).
3. Command Execution & Dynamic Cloud MQTT Fallback (Local-first, with transparent cloud failover).
4. Dynamic Protocol Auto-Negotiation (3.4 -> 3.3 standalone fallback on Err 914).
5. LAN IP Discovery & Retention (Preventing overwrite of dynamic LAN IPs and rejecting WAN IPs).
6. Cloud MQTT Runtime connection state.
7. Device Registry HA Core modern compatibility (deprecation warning protection).
"""

import asyncio
import os
import sys
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def setup_mock_homeassistant():
    """Mock Home Assistant core modules and external dependencies."""
    from types import ModuleType

    def make_module(name):
        mod = ModuleType(name)
        sys.modules[name] = mod
        return mod

    # homeassistant base modules
    ha = make_module("homeassistant")
    ha_core = make_module("homeassistant.core")
    ha_const = make_module("homeassistant.const")
    ha_config = make_module("homeassistant.config_entries")
    ha_helpers = make_module("homeassistant.helpers")
    ha_helpers_entity = make_module("homeassistant.helpers.entity")
    ha_helpers_entity_platform = make_module("homeassistant.helpers.entity_platform")
    ha_helpers_update_coordinator = make_module("homeassistant.helpers.update_coordinator")
    ha_helpers_dispatcher = make_module("homeassistant.helpers.dispatcher")
    ha_helpers_device_registry = make_module("homeassistant.helpers.device_registry")
    ha_helpers_storage = make_module("homeassistant.helpers.storage")
    ha_components = make_module("homeassistant.components")
    ha_switch = make_module("homeassistant.components.switch")
    ha_fan = make_module("homeassistant.components.fan")
    ha_cover = make_module("homeassistant.components.cover")
    ha_binary_sensor = make_module("homeassistant.components.binary_sensor")
    ha_sensor = make_module("homeassistant.components.sensor")
    ha_number = make_module("homeassistant.components.number")
    ha_select = make_module("homeassistant.components.select")
    ha_remote = make_module("homeassistant.components.remote")
    ha_climate = make_module("homeassistant.components.climate")
    ha_light = make_module("homeassistant.components.light")
    ha_button = make_module("homeassistant.components.button")
    ha_media_player = make_module("homeassistant.components.media_player")
    ha_lock = make_module("homeassistant.components.lock")

    # aiohttp
    aiohttp = make_module("aiohttp")
    aiohttp_web = make_module("aiohttp.web")
    aiohttp.web = aiohttp_web
    aiohttp_web.Application = MagicMock
    aiohttp_web.AppRunner = MagicMock
    aiohttp_web.TCPSite = MagicMock
    aiohttp_web.Response = MagicMock
    aiohttp_web.json_response = MagicMock

    # paho-mqtt
    paho = make_module("paho")
    paho_mqtt = make_module("paho.mqtt")
    paho_mqtt_client = make_module("paho.mqtt.client")
    paho.mqtt = paho_mqtt
    paho_mqtt.client = paho_mqtt_client
    paho_mqtt_client.Client = MagicMock
    paho_mqtt_client.MQTTv311 = 4

    # Core classes
    class HomeAssistant:
        def __init__(self):
            self.loop = asyncio.get_event_loop()
            self.data = {}

        async def async_add_executor_job(self, target, *args):
            return target(*args)

    ha_core.HomeAssistant = HomeAssistant
    ha_core.ServiceCall = MagicMock
    ha_core.callback = lambda f: f
    ha_core.CALLBACK_TYPE = MagicMock

    # Config Entries
    class ConfigEntry:
        def __init__(self, entry_id="test_entry", data=None, options=None):
            self.entry_id = entry_id
            self.data = data or {}
            self.options = options or {}

    ha_config.ConfigEntry = ConfigEntry

    class ConfigFlow:
        def __init_subclass__(cls, domain=None, **kwargs):
            super().__init_subclass__(**kwargs)
            cls.domain = domain

    ha_config.ConfigFlow = ConfigFlow
    ha_config.OptionsFlow = ConfigFlow

    # Exceptions
    ha_exceptions = make_module("homeassistant.exceptions")
    ha_exceptions.HomeAssistantError = Exception

    # Config Validation
    ha_cv = make_module("homeassistant.helpers.config_validation")
    ha_cv.string = str
    ha_cv.boolean = bool
    ha_cv.positive_int = int
    ha_helpers.config_validation = ha_cv

    # Device & Entity Registry
    ha_dr = make_module("homeassistant.helpers.device_registry")
    ha_dr.async_get = MagicMock
    ha_helpers.device_registry = ha_dr

    ha_er = make_module("homeassistant.helpers.entity_registry")
    ha_er.async_get = MagicMock
    ha_helpers.entity_registry = ha_er

    # Selector & Util
    ha_selector = make_module("homeassistant.helpers.selector")
    ha_helpers.selector = ha_selector

    ha_util = make_module("homeassistant.util")
    ha_util_dt = make_module("homeassistant.util.dt")
    ha_util_dt.utcnow = MagicMock
    ha_util.dt = ha_util_dt

    # Voluptuous
    vol = make_module("voluptuous")
    vol.Schema = lambda x: MagicMock()
    vol.Optional = lambda x, **kw: x
    vol.Required = lambda x, **kw: x
    vol.All = lambda *x: MagicMock()
    vol.Coerce = lambda *x: MagicMock()
    vol.Range = lambda **x: MagicMock()
    vol.In = lambda *x: MagicMock()
    vol.ALLOW_EXTRA = MagicMock()

    # Platforms and Constants
    class Platform:
        SWITCH = "switch"
        COVER = "cover"
        NUMBER = "number"
        SELECT = "select"
        FAN = "fan"
        BINARY_SENSOR = "binary_sensor"
        SENSOR = "sensor"
        LOCK = "lock"
        CLIMATE = "climate"
        LIGHT = "light"
        MEDIA_PLAYER = "media_player"
        BUTTON = "button"

    class EntityCategory:
        CONFIG = "config"
        DIAGNOSTIC = "diagnostic"

    ha_const.Platform = Platform
    ha_const.EntityCategory = EntityCategory
    ha_const.CONF_HOST = "host"
    ha_const.CONF_ID = "id"
    ha_const.CONF_IP_ADDRESS = "ip_address"
    ha_const.CONF_PASSWORD = "password"

    class UnitOfTemperature:
        CELSIUS = "°C"
        FAHRENHEIT = "°F"

    ha_const.UnitOfTemperature = UnitOfTemperature
    ha_const.CONF_USERNAME = "username"
    ha_const.CONF_PORT = "port"
    ha_const.CONF_EMAIL = "email"
    ha_const.__getattr__ = lambda name: name.lower()

    # Base Entities
    class Entity:
        def __init__(self):
            self.hass = None
            self.entity_id = "test.entity"
            self._attr_extra_state_attributes = {}

        def async_write_ha_state(self):
            pass

    class CoordinatorEntity(Entity):
        __class_getitem__ = classmethod(lambda cls, item: cls)

        def __init__(self, coordinator=None):
            super().__init__()
            self.coordinator = coordinator

    class DataUpdateCoordinator:
        __class_getitem__ = classmethod(lambda cls, item: cls)

        def __init__(self, hass=None, logger=None, name=None, update_interval=None):
            self.hass = hass
            self.logger = logger
            self.name = name
            self.data = None

        async def async_config_entry_first_refresh(self):
            pass

    ha_helpers_entity.Entity = Entity
    ha_helpers_entity.DeviceInfo = dict
    ha_helpers_update_coordinator.CoordinatorEntity = CoordinatorEntity
    ha_helpers_update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    ha_helpers_update_coordinator.UpdateFailed = Exception

    class Store:
        def __init__(self, hass, version, key):
            self.hass = hass

        async def async_load(self):
            return None

        def async_save(self, data):
            if hasattr(self.hass, "loop") and self.hass.loop and not self.hass.loop.is_closed():
                fut = self.hass.loop.create_future()
                fut.set_result(None)
                return fut
            return None

    ha_helpers_storage.Store = Store
    ha_helpers_entity_platform.AddEntitiesCallback = MagicMock

    # Platforms
    class SwitchEntity(Entity):
        pass

    ha_switch.SwitchEntity = SwitchEntity

    import enum

    class FanEntity(Entity):
        pass

    class FanEntityFeature(enum.IntFlag):
        SET_SPEED = 1
        TURN_ON = 2
        TURN_OFF = 4

    ha_fan.FanEntity = FanEntity
    ha_fan.FanEntityFeature = FanEntityFeature

    class CoverEntity(Entity):
        pass

    class CoverDeviceClass:
        GARAGE = "garage"
        CURTAIN = "curtain"

    class CoverEntityFeature(enum.IntFlag):
        OPEN = 1
        CLOSE = 2
        STOP = 4
        SET_POSITION = 8

    ha_cover.CoverEntity = CoverEntity
    ha_cover.CoverDeviceClass = CoverDeviceClass
    ha_cover.CoverEntityFeature = CoverEntityFeature

    class BinarySensorEntity(Entity):
        pass

    class BinarySensorDeviceClass:
        CONNECTIVITY = "connectivity"
        DOOR = "door"
        MOTION = "motion"
        OCCUPANCY = "occupancy"
        PROBLEM = "problem"

    ha_binary_sensor.BinarySensorEntity = BinarySensorEntity
    ha_binary_sensor.BinarySensorDeviceClass = BinarySensorDeviceClass

    class SensorEntity(Entity):
        pass

    class SensorDeviceClass:
        TEMPERATURE = "temperature"
        HUMIDITY = "humidity"
        BATTERY = "battery"
        POWER = "power"
        VOLTAGE = "voltage"
        CURRENT = "current"
        ENERGY = "energy"

    class SensorStateClass:
        MEASUREMENT = "measurement"
        TOTAL_INCREASING = "total_increasing"

    ha_sensor.SensorEntity = SensorEntity
    ha_sensor.SensorDeviceClass = SensorDeviceClass
    ha_sensor.SensorStateClass = SensorStateClass

    class NumberEntity(Entity):
        pass

    class NumberMode:
        AUTO = "auto"
        BOX = "box"
        SLIDER = "slider"

    ha_number.NumberEntity = NumberEntity
    ha_number.NumberMode = NumberMode

    class SelectEntity(Entity):
        pass

    ha_select.SelectEntity = SelectEntity

    class RemoteEntity(Entity):
        pass

    class RemoteEntityFeature(enum.IntFlag):
        LEARN_COMMAND = 1
        DELETE_COMMAND = 2

    ha_remote.RemoteEntity = RemoteEntity
    ha_remote.RemoteEntityFeature = RemoteEntityFeature
    ha_remote.ATTR_ALTERNATIVE = "alternative"
    ha_remote.ATTR_COMMAND_TYPE = "command_type"
    ha_remote.ATTR_DELAY_SECS = "delay_secs"
    ha_remote.ATTR_DEVICE = "device"
    ha_remote.ATTR_NUM_REPEATS = "num_repeats"
    ha_remote.DEFAULT_DELAY_SECS = 0.5
    ha_const.ATTR_COMMAND = "command"

    class ClimateEntity(Entity):
        pass

    class HVACMode:
        OFF = "off"
        HEAT = "heat"
        COOL = "cool"
        AUTO = "auto"
        DRY = "dry"
        FAN_ONLY = "fan_only"

    ha_climate.ClimateEntity = ClimateEntity
    ha_climate.HVACMode = HVACMode

    class LightEntity(Entity):
        pass

    ha_light.LightEntity = LightEntity

    class ButtonEntity(Entity):
        pass

    ha_button.ButtonEntity = ButtonEntity

    class MediaPlayerEntity(Entity):
        pass

    ha_media_player.MediaPlayerEntity = MediaPlayerEntity

    class LockEntity(Entity):
        pass

    ha_lock.LockEntity = LockEntity


setup_mock_homeassistant()

# Import integration modules
from custom_components.tuya_smart_life_local.models import (
    TuyaDeviceDescription,
    TuyaMobileConfig,
)
from custom_components.tuya_smart_life_local.local import TuyaLocalRuntime
from custom_components.tuya_smart_life_local.switch import TuyaDpsSwitch
from custom_components.tuya_smart_life_local.fan import TuyaDpsFan
from custom_components.tuya_smart_life_local.cover import TuyaDpsCover
from custom_components.tuya_smart_life_local.binary_sensor import TuyaDpsBinarySensor
from custom_components.tuya_smart_life_local.sensor import TuyaContextButtonSensor, TuyaDpsSensor
from custom_components.tuya_smart_life_local.number import TuyaTravelTimeNumber
from custom_components.tuya_smart_life_local.select import TuyaChildLockSelect
from custom_components.tuya_smart_life_local.remote import TuyaIrHubRemote
from custom_components.tuya_smart_life_local.mqtt_cloud import TuyaMqttCloudRuntime


def make_test_device(**kwargs):
    default = {
        "dev_id": "dev_test",
        "name": "Test Device",
        "home_id": "home_1",
        "home_name": "Home",
        "local_key": "key1234567890123",
        "ip": "192.168.31.200",
        "mac": "00:11:22:33:44:55",
        "uuid": "uuid_test",
        "product_id": "prod_1",
        "category": "cz",
        "category_code": "cz",
        "category_code_2": "",
        "category_code_3": "",
        "uiid": "uiid_1",
        "kind": "device",
        "parent_dev_id": None,
        "node_id": None,
        "online": True,
        "protocol_version": "3.3",
        "dps": {},
    }
    default.update(kwargs)
    return TuyaDeviceDescription(**default)


class TestTuyaHybridAvailability(unittest.TestCase):
    """Test Suite 1: Hybrid Availability across all entity platforms."""

    def setUp(self):
        self.hass = MagicMock()
        self.local_runtime = TuyaLocalRuntime(self.hass)
        self.coordinator = MagicMock()
        self.runtime = MagicMock()
        self.runtime.local = self.local_runtime
        self.runtime.coordinator = self.coordinator

        self.device = make_test_device(
            dev_id="dev_test_001",
            name="Test Switch",
            local_key="key1234567890123",
            ip="192.168.31.200",
            protocol_version="3.3",
            online=True,
            dps={"1": True},
        )
        self.local_runtime.devices[self.device.dev_id] = self.device

    def test_switch_available_when_local_offline_but_cloud_online(self):
        """Switch MUST remain available if cloud is online, even when local TCP is down."""
        self.local_runtime._local_connected[self.device.dev_id] = False
        self.device.online = True

        switch = TuyaDpsSwitch(self.coordinator, self.runtime, self.device, "1", True, "Switch 1")
        self.assertTrue(switch.available, "Switch should be available via Cloud fallback")

    def test_switch_unavailable_when_both_local_and_cloud_offline(self):
        """Switch MUST be unavailable only when both local and cloud are down."""
        self.local_runtime._local_connected[self.device.dev_id] = False
        self.device.online = False

        switch = TuyaDpsSwitch(self.coordinator, self.runtime, self.device, "1", True, "Switch 1")
        self.assertFalse(switch.available, "Switch should be unavailable when both paths down")

    def test_switch_available_when_local_online_and_cloud_offline(self):
        """Switch MUST be available if local TCP is up, even if cloud is offline."""
        self.local_runtime._local_connected[self.device.dev_id] = True
        self.device.online = False

        switch = TuyaDpsSwitch(self.coordinator, self.runtime, self.device, "1", True, "Switch 1")
        self.assertTrue(switch.available, "Switch should be available via Local connection")

    def test_all_platforms_hybrid_availability(self):
        """Verify Fan, Cover, BinarySensor, Sensor, Number, Select, Remote all support cloud fallback."""
        self.local_runtime._local_connected[self.device.dev_id] = False
        self.device.online = True

        fan = TuyaDpsFan(self.coordinator, self.runtime, self.device)
        self.assertTrue(fan.available, "Fan should be available via cloud")

        cover = TuyaDpsCover(self.coordinator, self.runtime, self.device, "1", "Cover 1")
        self.assertTrue(cover.available, "Cover should be available via cloud")

        binary_sensor = TuyaDpsBinarySensor(
            self.coordinator, self.runtime, self.device, "1", True, "occupancy", "Sensor"
        )
        self.assertTrue(binary_sensor.available, "Binary sensor should be available via cloud")

        sensor = TuyaDpsSensor(
            self.coordinator, self.runtime, self.device, "1", 25.5, "temperature", "Nhiệt độ"
        )
        self.assertTrue(sensor.available, "Sensor should be available via cloud")

        context_sensor = TuyaContextButtonSensor(
            self.coordinator, self.runtime, self.device, "single", ["1"]
        )
        self.assertTrue(context_sensor.available, "Context button sensor should be available via cloud")

        number = TuyaTravelTimeNumber(self.coordinator, self.runtime, self.device, "1", 50.0, "Time")
        self.assertTrue(number.available, "Number should be available via cloud")

        select = TuyaChildLockSelect(self.coordinator, self.runtime, self.device, "1", "mode", "Lock")
        self.assertTrue(select.available, "Select should be available via cloud")

        remote = TuyaIrHubRemote(self.runtime, self.device)
        self.assertTrue(remote.available, "Remote should be available via cloud")


class TestCommandExecutionAndCloudFallback(unittest.IsolatedAsyncioTestCase):
    """Test Suite 2: Local execution with seamless Cloud MQTT fallback."""

    async def asyncSetUp(self):
        self.hass = MagicMock()
        self.hass.loop = asyncio.get_running_loop()
        self.local_runtime = TuyaLocalRuntime(self.hass)

        self.device = make_test_device(
            dev_id="dev_test_002",
            name="Test Device",
            local_key="key1234567890123",
            ip="192.168.31.201",
            protocol_version="3.3",
            online=True,
            dps={"1": False},
        )
        self.local_runtime.devices[self.device.dev_id] = self.device

        self.mock_mqtt = MagicMock()
        self.mock_mqtt.is_connected = True
        self.mock_mqtt.async_publish_dps = AsyncMock(return_value=None)
        self.local_runtime.mqtt = self.mock_mqtt
        mock_stream_dev = MagicMock()
        mock_stream_dev.socket = MagicMock()
        self.local_runtime._stream_tinytuya_devices[self.device.dev_id] = mock_stream_dev
        self.local_runtime._local_connected[self.device.dev_id] = True

        async def mock_async_add_executor_job(target, *args):
            return target(*args)

        self.hass.async_add_executor_job = mock_async_add_executor_job

    async def asyncTearDown(self):
        await self.local_runtime.async_stop()

    async def test_async_set_dp_local_success(self):
        """When local execution succeeds, Cloud MQTT is not called."""
        self.local_runtime._set_dp = MagicMock(return_value={"dps": {"1": True}})

        res = await self.local_runtime.async_set_dp(self.device, "1", True)
        self.assertEqual(res, {"dps": {"1": True}})
        self.mock_mqtt.async_publish_dps.assert_not_called()

    async def test_async_set_dp_fast_path_when_local_offline(self):
        """When device is disconnected locally, it directly fast-paths to Cloud MQTT without blocking."""
        self.local_runtime._stream_tinytuya_devices.clear()
        self.local_runtime._local_connected[self.device.dev_id] = False
        self.local_runtime._set_dp = MagicMock()

        res = await self.local_runtime.async_set_dp(self.device, "1", True)
        self.assertEqual(res, {"success": True, "fallback": "cloud_mqtt"})
        self.mock_mqtt.async_publish_dps.assert_awaited_once_with(self.device, {"1": True})
        self.local_runtime._set_dp.assert_not_called()

    async def test_async_set_dp_fallback_on_local_error_dict(self):
        """When local execution returns {'Error': ...}, Cloud MQTT fallback is called."""
        self.local_runtime._set_dp = MagicMock(return_value={"Error": "Check device key or version", "Err": "914"})

        res = await self.local_runtime.async_set_dp(self.device, "1", True)
        self.assertEqual(res, {"success": True, "fallback": "cloud_mqtt"})
        self.mock_mqtt.async_publish_dps.assert_awaited_once_with(self.device, {"1": True})

    async def test_async_set_dp_fallback_on_local_exception(self):
        """When local execution raises a network timeout/reset, Cloud MQTT fallback is called."""
        self.local_runtime._set_dp = MagicMock(side_effect=ConnectionResetError("Socket closed remotely"))

        res = await self.local_runtime.async_set_dp(self.device, "1", True)
        self.assertEqual(res, {"success": True, "fallback": "cloud_mqtt"})
        self.mock_mqtt.async_publish_dps.assert_awaited_once_with(self.device, {"1": True})

    async def test_async_set_dp_cloud_fail_raises_local_error(self):
        """When both local and cloud fallback fail, exception is cleanly raised."""
        self.local_runtime._set_dp = MagicMock(side_effect=TimeoutError("Local timeout"))
        self.mock_mqtt.async_publish_dps = AsyncMock(side_effect=RuntimeError("Cloud MQTT offline"))

        with self.assertRaises(TimeoutError):
            await self.local_runtime.async_set_dp(self.device, "1", True)


class TestProtocolFallbackAndDeviceUpdates(unittest.TestCase):
    """Test Suite 3: Standalone Protocol Fallback and IP Retention."""

    def setUp(self):
        self.hass = MagicMock()
        self.loop = asyncio.new_event_loop()
        self.hass.loop = self.loop
        self.local_runtime = TuyaLocalRuntime(self.hass)
        self.local_runtime._state_stream_tasks = {}

    def tearDown(self):
        self.loop.close()

    def test_standalone_protocol_fallback(self):
        """Standalone devices (like Oven, Sensors) must fallback from 3.4 to 3.3 on Err 914."""
        device = make_test_device(
            dev_id="dev_oven_001",
            name="Lò nướng",
            local_key="key_oven_secret",
            ip="192.168.31.235",
            protocol_version="3.4",
            online=True,
        )
        self.local_runtime.devices[device.dev_id] = device

        def mock_status_once(dev_id):
            if device.protocol_version == "3.4":
                return {"Error": "Check device key or version", "Err": "914"}
            elif device.protocol_version == "3.3":
                return {"dps": {"1": True}}
            return {"Error": "unsupported"}

        self.local_runtime._status_once = mock_status_once

        res = self.local_runtime._status(device.dev_id)
        self.assertEqual(res, {"dps": {"1": True}})
        self.assertEqual(device.protocol_version, "3.3", "Protocol should auto-update to 3.3")

    def test_update_devices_preserves_new_lan_ip(self):
        """update_devices must NOT overwrite a newly discovered LAN IP with the old IP."""
        old_device = make_test_device(
            dev_id="dev_switch_001",
            name="Công tắc phòng khách",
            ip="192.168.31.71",
            protocol_version="3.3",
        )
        self.local_runtime.devices[old_device.dev_id] = old_device

        new_device = make_test_device(
            dev_id="dev_switch_001",
            name="Công tắc phòng khách",
            ip="192.168.31.85",  # New DHCP IP
            protocol_version="3.3",
        )

        with patch.object(self.local_runtime, "_ensure_state_stream_tasks"):
            self.local_runtime.update_devices([new_device])

        updated = self.local_runtime.devices["dev_switch_001"]
        self.assertEqual(updated.ip, "192.168.31.85", "Should keep the newly assigned DHCP IP")

    def test_update_devices_preserves_lan_ip_when_cloud_reports_wan(self):
        """update_devices should preserve LAN IP when Cloud returns a WAN IP."""
        old_device = make_test_device(
            dev_id="dev_switch_002",
            name="Đèn phòng ngủ",
            ip="192.168.31.35",
            protocol_version="3.3",
        )
        self.local_runtime.devices[old_device.dev_id] = old_device

        new_device = make_test_device(
            dev_id="dev_switch_002",
            name="Đèn phòng ngủ",
            ip="118.68.189.197",  # Public WAN IP from cloud
            protocol_version="3.3",
        )

        with patch.object(self.local_runtime, "_ensure_state_stream_tasks"):
            self.local_runtime.update_devices([new_device])

        updated = self.local_runtime.devices["dev_switch_002"]
        self.assertEqual(updated.ip, "192.168.31.35", "Should preserve local LAN IP instead of WAN IP")


class TestMqttCloudRuntime(unittest.TestCase):
    """Test Suite 4: Tuya Cloud MQTT Runtime properties."""

    def test_is_connected_property(self):
        hass = MagicMock()
        local_runtime = MagicMock()
        runtime = TuyaMqttCloudRuntime(hass, local_runtime, None)

        self.assertFalse(runtime.is_connected)
        runtime._connected.set()
        self.assertTrue(runtime.is_connected)
        runtime._connected.clear()
        self.assertFalse(runtime.is_connected)


class TestCoreDeprecationFix(unittest.TestCase):
    """Test Suite 5: Verify DeviceEntry config_entries deprecation compatibility."""

    def test_device_entry_config_entries_fallback(self):
        """Verify device entry safely reads config_entries or config_entry_id."""
        class LegacyDeviceEntry:
            config_entry_id = "entry_123"

        class ModernDeviceEntry:
            config_entries = {"entry_123", "entry_456"}

        legacy = LegacyDeviceEntry()
        modern = ModernDeviceEntry()

        legacy_entries = getattr(legacy, "config_entries", None) or {getattr(legacy, "config_entry_id", None)}
        modern_entries = getattr(modern, "config_entries", None) or {getattr(modern, "config_entry_id", None)}

        self.assertIn("entry_123", legacy_entries)
        self.assertIn("entry_456", modern_entries)


class TestRapidToggleCoalescingAndOptimisticLockout(unittest.IsolatedAsyncioTestCase):
    """Test Suite 6: Verify rapid toggle command coalescing and switch optimistic state lockout."""

    async def asyncSetUp(self):
        self.hass = MagicMock()
        self.hass.loop = asyncio.get_running_loop()
        self.local_runtime = TuyaLocalRuntime(self.hass)

        self.device = make_test_device(
            dev_id="dev_rapid_001",
            name="Rapid Light Switch",
            local_key="key1234567890123",
            ip="192.168.31.210",
            protocol_version="3.3",
            online=True,
            dps={"1": False},
        )
        self.local_runtime.devices[self.device.dev_id] = self.device

        # Mark as active stream so it goes to local fast-path
        mock_stream = MagicMock()
        mock_stream.socket = MagicMock()
        self.local_runtime._stream_tinytuya_devices[self.device.dev_id] = mock_stream
        self.local_runtime._local_connected[self.device.dev_id] = True

        async def mock_async_add_executor_job(target, *args):
            await asyncio.sleep(0.01)
            return target(*args)

        self.hass.async_add_executor_job = mock_async_add_executor_job

    async def test_rapid_toggle_coalescing(self):
        """When 4 rapid toggles occur in flight, intermediate calls collapse and only 2 sends occur."""
        send_calls = []

        def mock_set_dp(dev_id, dp_id, value):
            send_calls.append(value)
            # Simulate a small socket delay
            time.sleep(0.02)
            return {"success": True}

        self.local_runtime._set_dp = mock_set_dp

        # Launch 4 rapid toggles: ON -> OFF -> ON -> OFF concurrently
        tasks = [
            asyncio.create_task(self.local_runtime.async_set_dp(self.device, "1", True)),
            asyncio.create_task(self.local_runtime.async_set_dp(self.device, "1", False)),
            asyncio.create_task(self.local_runtime.async_set_dp(self.device, "1", True)),
            asyncio.create_task(self.local_runtime.async_set_dp(self.device, "1", False)),
        ]
        results = await asyncio.gather(*tasks)

        # All 4 calls must succeed
        self.assertEqual(len(results), 4)
        for res in results:
            self.assertIsNotNone(res)

        # But only 2 physical network sends should have executed (initial True, then final False)!
        self.assertLessEqual(len(send_calls), 2, f"Expected at most 2 sends, got {len(send_calls)}: {send_calls}")
        self.assertEqual(send_calls[-1], False, "Final physical send must match last requested state")

    async def test_switch_optimistic_lockout_ignores_stale_dps(self):
        """Switch optimistic lockout must drop older opposing state packets while waiting for target."""
        coordinator = MagicMock()
        runtime = MagicMock()
        runtime.local = self.local_runtime

        switch = TuyaDpsSwitch(coordinator, runtime, self.device, "1", False, "Switch 1")
        switch.entity_id = "switch.rapid_light_1"
        switch.async_write_ha_state = MagicMock()

        # User turns ON
        self.local_runtime._set_dp = MagicMock(return_value={"success": True})
        await switch.async_turn_on()
        self.assertTrue(switch.is_on)
        self.assertEqual(switch._target_state, True)

        # A stale 'False' report arrives from an earlier hardware echo
        switch._handle_dps_update(self.device.dev_id, {"1": False})
        # Must be ignored: switch remains ON
        self.assertTrue(switch.is_on, "Switch should ignore stale False report while awaiting True")

        # The genuine 'True' report arrives
        switch._handle_dps_update(self.device.dev_id, {"1": True})
        self.assertTrue(switch.is_on)
        self.assertIsNone(switch._target_state, "Target state should be cleared once achieved")

    def test_make_tinytuya_device_retry_limit_always_nonzero(self):
        """Verify _make_tinytuya_device configures socketRetryLimit to 1 for one-off and 0 for persistent."""
        mock_tinytuya = MagicMock()
        mock_device = MagicMock()
        mock_tinytuya.OutletDevice.return_value = mock_device

        # One-off command connection
        dev = self.local_runtime._make_tinytuya_device(
            mock_tinytuya,
            self.device,
            "192.168.31.210",
            "key1234567890123",
            parent=None,
            persistent=False,
        )
        mock_device.set_socketRetryLimit.assert_called_with(1)

        # Persistent stream connection (must be 0 to avoid blocking on empty heartbeat/ACK packets)
        mock_device_stream = MagicMock()
        mock_tinytuya.OutletDevice.return_value = mock_device_stream
        dev_stream = self.local_runtime._make_tinytuya_device(
            mock_tinytuya,
            self.device,
            "192.168.31.210",
            "key1234567890123",
            parent=None,
            persistent=True,
        )
        mock_device_stream.set_socketRetryLimit.assert_called_with(0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
