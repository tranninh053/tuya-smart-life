from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "tuya_smart_life_local"
PLATFORMS = [
    Platform.SWITCH,
    Platform.COVER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.FAN,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.LOCK,
    Platform.CLIMATE,
    Platform.LIGHT,
    Platform.MEDIA_PLAYER,
    Platform.BUTTON,
]

CONF_APP_ID = "app_id"
CONF_APP_SECRET = "app_secret"
CONF_APP_RN_VERSION = "app_rn_version"
CONF_API_REGION = "api_region"
CONF_APP_VERSION = "app_version"
CONF_BMP_KEY = "bmp_key"
CONF_CERT_SHA256 = "cert_sha256"
CONF_CHANNEL = "channel"
CONF_CH_KEY = "ch_key"
CONF_COUNTRY_CODE = "country_code"
CONF_CP = "cp"
CONF_DEVICE_CORE_VERSION = "device_core_version"
CONF_ET = "et"
CONF_NATIVE_KEY_TEXT = "native_key_text"
CONF_ND = "nd"
CONF_OS_SYSTEM = "os_system"
CONF_PACKAGE_NAME = "package_name"
CONF_PLATFORM = "platform"
CONF_SELECTED_HOME_IDS = "selected_home_ids"
CONF_SDK_VERSION = "sdk_version"
CONF_TTID = "ttid"
CONF_MQTT_BROKER = "mqtt_broker"
CONF_MQTT_CLIENT_ID = "mqtt_client_id"
CONF_MQTT_PASSWORD = "mqtt_password"
CONF_MQTT_UID = "mqtt_uid"
CONF_MQTT_USERNAME = "mqtt_username"
CONF_MQTT_UNLOCK_DPS = "mqtt_unlock_dps"
CONF_MOBILE_APP = "mobile_app"

MOBILE_APP_TUYA = "tuya"
MOBILE_APP_SMART_LIFE = "smart_life"

DEFAULT_APP_ID = "3cxxt3au9x33ytvq3h9j"
DEFAULT_API_REGION = "auto"
DEFAULT_APP_VERSION = "7.8.6"
DEFAULT_MQTT_BROKER = "mqtts://m1.tuyaus.com:8883"
DEFAULT_APP_RN_VERSION = "5.84"
DEFAULT_CHANNEL = "oem"
DEFAULT_CH_KEY = "3f7060ea"
DEFAULT_COUNTRY_CODE = "84"
DEFAULT_CP = ""
DEFAULT_DEVICE_CORE_VERSION = "5.17.0"
DEFAULT_ET = "0"
DEFAULT_NATIVE_KEY_TEXT = (
    "com.tuya.smart_"
    "93:21:9F:C2:73:E2:20:0F:4A:DE:E5:F7:19:1D:C6:56:"
    "BA:2A:2D:7B:2F:F5:D2:4C:D5:5C:4B:61:55:00:1E:40_"
    "f3hd7pet4p83kemjdf5wqsa5tavrv579_"
    "5gdtanjtf38vyxkqh87cjwfcqjhvjjqa"
)
DEFAULT_ND = ""
DEFAULT_OS_SYSTEM = "15"
DEFAULT_PACKAGE_NAME = "com.tuya.smart"
DEFAULT_PLATFORM = "y"
DEFAULT_SDK_VERSION = "5.24.0"
DEFAULT_SCAN_INTERVAL_SECONDS = 1800
DEFAULT_TTID = "international"
DEFAULT_MOBILE_APP = MOBILE_APP_TUYA

SMART_LIFE_APP_ID = "ekmnwp9f5pnh3trdtpgy"
SMART_LIFE_APP_SECRET = "r3me7ghmxjevrvnpemwmhw3fxtacphyg"
SMART_LIFE_APP_VERSION = "7.9.0"
SMART_LIFE_APP_RN_VERSION = "7.8"
SMART_LIFE_BMP_KEY = "jfg5rs5kkmrj5mxahugvucrsvw43t48x"
SMART_LIFE_CERT_SHA256 = (
    "0F:C3:61:99:9C:C0:C3:5B:A8:AC:A5:7D:AA:55:93:A2:"
    "0C:F5:57:27:70:2E:A8:5A:D7:B3:22:89:49:F8:88:FE"
)
SMART_LIFE_CH_KEY = "ec9709a4"
SMART_LIFE_CP = ""
SMART_LIFE_DEVICE_CORE_VERSION = "7.9.0"
SMART_LIFE_ET = "0"
SMART_LIFE_NATIVE_KEY_TEXT = (
    "com.tuya.smartlife_"
    "0F:C3:61:99:9C:C0:C3:5B:A8:AC:A5:7D:AA:55:93:A2:"
    "0C:F5:57:27:70:2E:A8:5A:D7:B3:22:89:49:F8:88:FE_"
    "jfg5rs5kkmrj5mxahugvucrsvw43t48x_"
    "r3me7ghmxjevrvnpemwmhw3fxtacphyg"
)
SMART_LIFE_ND = ""
SMART_LIFE_OS_SYSTEM = "14"
SMART_LIFE_PACKAGE_NAME = "com.tuya.smartlife"
SMART_LIFE_PLATFORM = "SM-M115F"
SMART_LIFE_SDK_VERSION = "7.9.0"
SMART_LIFE_TTID = f"sdk_international@{SMART_LIFE_APP_ID}"

MOBILE_APP_PROFILES = {
    MOBILE_APP_TUYA: {
        CONF_APP_ID: DEFAULT_APP_ID,
        CONF_APP_RN_VERSION: DEFAULT_APP_RN_VERSION,
        CONF_APP_VERSION: DEFAULT_APP_VERSION,
        CONF_CHANNEL: DEFAULT_CHANNEL,
        CONF_CH_KEY: DEFAULT_CH_KEY,
        CONF_COUNTRY_CODE: DEFAULT_COUNTRY_CODE,
        CONF_CP: DEFAULT_CP,
        CONF_DEVICE_CORE_VERSION: DEFAULT_DEVICE_CORE_VERSION,
        CONF_ET: DEFAULT_ET,
        CONF_NATIVE_KEY_TEXT: DEFAULT_NATIVE_KEY_TEXT,
        CONF_ND: DEFAULT_ND,
        CONF_OS_SYSTEM: DEFAULT_OS_SYSTEM,
        CONF_PACKAGE_NAME: DEFAULT_PACKAGE_NAME,
        CONF_PLATFORM: DEFAULT_PLATFORM,
        CONF_SDK_VERSION: DEFAULT_SDK_VERSION,
        CONF_TTID: DEFAULT_TTID,
    },
    MOBILE_APP_SMART_LIFE: {
        CONF_APP_ID: SMART_LIFE_APP_ID,
        CONF_APP_SECRET: SMART_LIFE_APP_SECRET,
        CONF_APP_RN_VERSION: SMART_LIFE_APP_RN_VERSION,
        CONF_APP_VERSION: SMART_LIFE_APP_VERSION,
        CONF_BMP_KEY: SMART_LIFE_BMP_KEY,
        CONF_CERT_SHA256: SMART_LIFE_CERT_SHA256,
        CONF_CHANNEL: DEFAULT_CHANNEL,
        CONF_CH_KEY: SMART_LIFE_CH_KEY,
        CONF_COUNTRY_CODE: DEFAULT_COUNTRY_CODE,
        CONF_CP: SMART_LIFE_CP,
        CONF_DEVICE_CORE_VERSION: SMART_LIFE_DEVICE_CORE_VERSION,
        CONF_ET: SMART_LIFE_ET,
        CONF_NATIVE_KEY_TEXT: SMART_LIFE_NATIVE_KEY_TEXT,
        CONF_ND: SMART_LIFE_ND,
        CONF_OS_SYSTEM: SMART_LIFE_OS_SYSTEM,
        CONF_PACKAGE_NAME: SMART_LIFE_PACKAGE_NAME,
        CONF_PLATFORM: SMART_LIFE_PLATFORM,
        CONF_SDK_VERSION: SMART_LIFE_SDK_VERSION,
        CONF_TTID: SMART_LIFE_TTID,
    },
}


def mobile_app_profile(mobile_app: str | None) -> dict[str, str]:
    return MOBILE_APP_PROFILES.get(
        mobile_app or DEFAULT_MOBILE_APP,
        MOBILE_APP_PROFILES[DEFAULT_MOBILE_APP],
    )

MOBILE_API_ENDPOINTS = {
    "us": "https://a1.tuyaus.com/api.json",
    "sg": "https://a1-sg.iotbing.com/api.json",
    "eu": "https://a1.tuyaeu.com/api.json",
    "cn": "https://a1.tuyacn.com/api.json",
    "in": "https://a1.tuyain.com/api.json",
}

ENTRY_RUNTIME = "runtime"
