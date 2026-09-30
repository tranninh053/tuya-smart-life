from __future__ import annotations

import base64
import binascii
from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json
import logging
import os
import ssl
import struct
import threading
import time
from typing import Any
from urllib.parse import urlparse

from homeassistant.core import HomeAssistant

from .const import (
    CONF_MQTT_BROKER,
    CONF_MQTT_CLIENT_ID,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_UID,
    CONF_MQTT_USERNAME,
    DEFAULT_MQTT_BROKER,
)
from .local import TuyaLocalRuntime
from .models import TuyaDeviceDescription, TuyaMobileConfig, TuyaSession

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class TuyaMqttConfig:
    broker: str
    username: str
    password: str
    uid: str
    client_id: str


def derive_mqtt_config(
    data: dict[str, Any],
    session: TuyaSession | None,
    mobile_config: TuyaMobileConfig,
) -> TuyaMqttConfig | None:
    """Build Tuya mobile MQTT credentials from login session data.

    The Android SDK fills MqttConnectConfig from the logged-in IBaseUser:
    token = sid, ecode = ecode, uid = uid. That makes sid the MQTT username for
    current Smart Life/Tuya Smart builds even when the login response does not
    contain fields named token or mqttToken. The password is MD5(ecode)[8:24].
    """
    username = str(data.get(CONF_MQTT_USERNAME) or "")
    password = str(data.get(CONF_MQTT_PASSWORD) or "")
    uid = str(data.get(CONF_MQTT_UID) or "")
    client_id = str(data.get(CONF_MQTT_CLIENT_ID) or "")
    broker = str(data.get(CONF_MQTT_BROKER) or "")

    if session:
        username = username or _mqtt_token_from_session(session)
        password = password or _mqtt_password_from_session(session)
        uid = uid or str(session.uid or "")
        client_id = client_id or _mqtt_client_id(mobile_config, uid)
        broker = broker or _mqtt_broker_from_session(session)

    if not all((username, password, uid, client_id)):
        _LOGGER.warning("Tuya cloud MQTT credentials are incomplete")
        return None

    return TuyaMqttConfig(
        broker=broker or DEFAULT_MQTT_BROKER,
        username=username,
        password=password,
        uid=uid,
        client_id=client_id,
    )


class TuyaMqttCloudRuntime:
    def __init__(
        self,
        hass: HomeAssistant,
        local: TuyaLocalRuntime,
        config: TuyaMqttConfig | None,
    ) -> None:
        self.hass = hass
        self.local = local
        self.config = config
        self._client: Any | None = None
        self._connected = threading.Event()
        self._lock = threading.Lock()
        self._subscribed: set[str] = set()
        self._remove_metadata_listener: Callable[[], None] | None = None

    async def async_start(self) -> None:
        if not self.config:
            _LOGGER.debug("Tuya cloud MQTT missing credentials")
            return
        await self.hass.async_add_executor_job(self._start_client)
        self._remove_metadata_listener = self.local.async_add_metadata_listener(
            self._async_refresh_subscriptions
        )
        self._async_refresh_subscriptions()

    async def async_stop(self) -> None:
        if self._remove_metadata_listener:
            self._remove_metadata_listener()
            self._remove_metadata_listener = None
        await self.hass.async_add_executor_job(self._stop_client)

    def _start_client(self) -> None:
        if not self.config:
            return
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            _LOGGER.warning("paho-mqtt is not installed; cloud MQTT disabled")
            return

        parsed = urlparse(self.config.broker or DEFAULT_MQTT_BROKER)
        scheme = parsed.scheme or "mqtts"
        host = parsed.hostname or "m1.tuyaus.com"
        port = parsed.port or (8883 if scheme == "mqtts" else 1883)
        client = mqtt.Client(
            client_id=self.config.client_id,
            clean_session=True,
            protocol=mqtt.MQTTv311,
        )
        client.username_pw_set(self.config.username, self.config.password)
        if scheme in ("mqtts", "ssl", "tls"):
            client.tls_set(cert_reqs=ssl.CERT_NONE)
            client.tls_insecure_set(True)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message

        with self._lock:
            self._client = client
            self._subscribed.clear()
        client.connect_async(host, port, keepalive=60)
        client.loop_start()

    def _stop_client(self) -> None:
        with self._lock:
            client = self._client
            self._client = None
            self._subscribed.clear()
        self._connected.clear()
        if client:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:
                _LOGGER.debug("Unable to stop Tuya cloud MQTT client", exc_info=True)

    def _on_connect(self, client: Any, _userdata: Any, _flags: Any, rc: int) -> None:
        if rc != 0:
            _LOGGER.warning("Tuya cloud MQTT connect failed rc=%s", rc)
            return
        _LOGGER.info("Tuya cloud MQTT connected")
        self._connected.set()
        self._async_refresh_subscriptions()

    def _on_disconnect(self, _client: Any, _userdata: Any, rc: int) -> None:
        self._connected.clear()
        if rc:
            _LOGGER.debug("Tuya cloud MQTT disconnected rc=%s", rc)

    def _async_refresh_subscriptions(self) -> None:
        self.hass.loop.call_soon_threadsafe(
            self.hass.async_add_executor_job,
            self._refresh_subscriptions,
        )

    def _refresh_subscriptions(self) -> None:
        if not self.config:
            return
        with self._lock:
            client = self._client
        if not client or not self._connected.is_set():
            return

        topics = {f"smart/mb/{self.config.uid}"}
        for dev_id in self.local.devices:
            topics.add(f"smart/mb/in/{dev_id}")
            topics.add(f"smart/mb/out/{dev_id}")
            topics.add(f"m/w/{dev_id}")

        for topic in sorted(topics - self._subscribed):
            result, _mid = client.subscribe(topic, qos=1)
            if result == 0:
                self._subscribed.add(topic)
                _LOGGER.debug("Subscribed Tuya cloud MQTT topic %s", topic)
            else:
                _LOGGER.debug("Unable to subscribe Tuya cloud MQTT topic %s rc=%s", topic, result)

    def _on_message(self, _client: Any, _userdata: Any, message: Any) -> None:
        payload = bytes(message.payload or b"")
        dev_id = _dev_id_from_topic(message.topic)
        decoded = self._decode_payload(payload, dev_id)
        if not decoded:
            return
        _LOGGER.debug("Tuya cloud MQTT decoded topic=%s payload=%s", message.topic, decoded)
        event_dev_id = _event_dev_id(decoded) or dev_id
        if event_dev_id and event_dev_id in self.local.devices:
            dps = _event_dps(decoded)
            if dps:
                self.local.apply_mqtt_dps(event_dev_id, dps, decoded)
            else:
                self.local.apply_mqtt_event(event_dev_id, decoded)

    def _decode_payload(self, payload: bytes, dev_id: str | None) -> dict[str, Any] | None:
        if len(payload) < 4:
            return None
        prefix = payload[:3].decode("utf-8", errors="ignore")
        device = self.local.devices.get(dev_id or "")
        local_key = (device.local_key if device else None) or _key_for_payload(self.local.devices)
        if not local_key:
            return None
        try:
            if prefix == "2.2" and len(payload) > 15:
                plain = _aes_ecb_decrypt(payload[15:], local_key.encode())
            elif prefix == "2.3" and len(payload) > 40:
                header = payload[:12]
                rest = payload[12:]
                nonce = rest[:12]
                tag = rest[-16:]
                encrypted = rest[12:-16]
                plain = _aes_gcm_decrypt(encrypted, local_key.encode(), nonce, tag, header)
            else:
                return None
            return json.loads(plain.decode("utf-8"))
        except Exception:
            _LOGGER.debug("Unable to decode Tuya cloud MQTT payload for %s", dev_id, exc_info=True)
            return None

    async def async_publish_dps(self, device: TuyaDeviceDescription, dps: dict[str, Any]) -> None:
        if not self.config:
            raise RuntimeError("Tuya cloud MQTT is not configured")
        if not device.local_key:
            raise RuntimeError(f"Device {device.dev_id} does not have a local key")
        payload = await self.hass.async_add_executor_job(self._build_payload, device, dps)
        topic = f"smart/mb/out/{device.dev_id}"
        await self.hass.async_add_executor_job(self._publish, topic, payload)

    def _publish(self, topic: str, payload: bytes) -> None:
        with self._lock:
            client = self._client
        if not client or not self._connected.is_set():
            raise RuntimeError("Tuya cloud MQTT is not connected")
        info = client.publish(topic, payload, qos=1, retain=False)
        info.wait_for_publish(timeout=10)
        if not info.is_published():
            raise RuntimeError(f"Timed out publishing Tuya cloud MQTT topic {topic}")

    def _build_payload(self, device: TuyaDeviceDescription, dps: dict[str, Any]) -> bytes:
        pv = mqtt_pv(device)
        plain = json.dumps(
            {"data": {"dps": dps}, "protocol": 5, "t": int(time.time())},
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        seq = int(time.time() * 1000) & 0x7FFFFFFF
        origin = int.from_bytes(os.urandom(4), "big") & 0x7FFFFFFF
        key = device.local_key.encode()
        if pv == "2.2":
            encrypted = _aes_ecb_encrypt(plain, key)
            body = struct.pack(">II", seq, origin) + encrypted
            return b"2.2" + struct.pack(">I", binascii.crc32(body) & 0xFFFFFFFF) + body
        header = b"2.3" + struct.pack(">II", seq, origin) + b"\x00"
        nonce = os.urandom(12)
        encrypted, tag = _aes_gcm_encrypt(plain, key, nonce, header)
        return header + nonce + encrypted + tag


def mqtt_pv(device: TuyaDeviceDescription) -> str:
    raw = device.raw if isinstance(device.raw, dict) else {}
    communication = raw.get("communication")
    modes = communication.get("communicationModes") if isinstance(communication, dict) else None
    if isinstance(modes, list):
        for mode in modes:
            if isinstance(mode, dict) and mode.get("type") == 1 and mode.get("pv"):
                return str(mode["pv"])
    return "2.3"


def _dev_id_from_topic(topic: str) -> str | None:
    parts = topic.split("/")
    if len(parts) >= 4 and parts[:2] == ["smart", "mb"] and parts[2] in ("in", "out"):
        return parts[3]
    if len(parts) >= 3 and parts[:2] == ["m", "w"]:
        return parts[2]
    return None


def _event_dev_id(event: dict[str, Any]) -> str | None:
    data = event.get("data")
    if isinstance(data, dict):
        dev_id = data.get("devId") or data.get("gwId")
        if dev_id:
            return str(dev_id)
    return None


def _event_dps(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data")
    if not isinstance(data, dict):
        return {}
    dps = data.get("dps")
    if not isinstance(dps, dict):
        return {}
    return {str(key): value for key, value in dps.items()}


def _key_for_payload(devices: dict[str, TuyaDeviceDescription]) -> str | None:
    for device in devices.values():
        if device.local_key:
            return device.local_key
    return None


def _aes_ecb_encrypt(plain: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    pad_len = 16 - (len(plain) % 16)
    padded = plain + bytes([pad_len]) * pad_len
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def _aes_ecb_decrypt(encrypted: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    padded = decryptor.update(encrypted) + decryptor.finalize()
    pad_len = padded[-1]
    if pad_len < 1 or pad_len > 16:
        return padded
    return padded[:-pad_len]


def _aes_gcm_encrypt(plain: bytes, key: bytes, nonce: bytes, aad: bytes) -> tuple[bytes, bytes]:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    out = AESGCM(key).encrypt(nonce, plain, aad)
    return out[:-16], out[-16:]


def _aes_gcm_decrypt(
    encrypted: bytes,
    key: bytes,
    nonce: bytes,
    tag: bytes,
    aad: bytes,
) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    return AESGCM(key).decrypt(nonce, encrypted + tag, aad)


def decode_lock_media_payload(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, str):
        return None
    try:
        raw = base64.b64decode(value)
        decoded = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    return decoded if isinstance(decoded, dict) else None


def _mqtt_token_from_session(session: TuyaSession) -> str:
    raw = session.raw if isinstance(session.raw, dict) else {}
    # Keep sid here. The Android SDK's IThingGetBaseConfig implementation sets
    # MqttConnectConfig.token from IBaseUser.getSid(), and Smart Life 7.x login
    # responses usually do not include separate token/mqttToken fields.
    for key in ("token", "mqttToken", "mqtt_token", "sid"):
        token = raw.get(key)
        if token:
            return str(token)
    return str(session.sid or "")


def _mqtt_password_from_session(session: TuyaSession) -> str:
    ecode = session.ecode
    if not ecode:
        return ""
    return _md5_hex(ecode)[8:24]


def _mqtt_client_id(config: TuyaMobileConfig, uid: str) -> str:
    if not uid:
        return ""
    device_id = config.device_id or _stable_device_id(
        config.email,
        config.app_id,
        config.package_name,
    )
    sdk_uid = f"{device_id}_{_md5_hex(uid + 'sdkfasodifca')}"
    return f"{config.package_name}_mb_{sdk_uid}_DEFAULT"


def _mqtt_broker_from_session(session: TuyaSession) -> str:
    raw = session.raw if isinstance(session.raw, dict) else {}
    domain = raw.get("domain") if isinstance(raw.get("domain"), dict) else {}
    host = str(domain.get("mobileMqttsUrl") or domain.get("mobileMqttUrl") or "")
    if not host:
        return ""
    if "://" in host:
        return host
    use_tls = bool(domain.get("mobileMqttsUrl"))
    scheme = "mqtts" if use_tls else "mqtt"
    default_port = 8883 if use_tls else 1883
    port = domain.get("mqttsPort") if use_tls else domain.get("mqttPort")
    try:
        port_int = int(port or default_port)
    except (TypeError, ValueError):
        port_int = default_port
    return f"{scheme}://{host}:{port_int}"


def _stable_device_id(username: str, app_id: str, package_name: str) -> str:
    material = f"{package_name}|{app_id}|{username}".encode()
    return hashlib.sha256(material).hexdigest()[:44]


def _md5_hex(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode()
    return hashlib.md5(value).hexdigest()
