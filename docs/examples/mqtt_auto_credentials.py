#!/usr/bin/env python3
"""Example: derive Tuya mobile MQTT credentials from a login response.

This file is intentionally dependency-free and mirrors the Home Assistant
integration logic in custom_components/tuya_smart_life_local/mqtt_cloud.py.

Input may be either the full mobile API response:

    {"success": true, "result": {"sid": "...", "ecode": "...", "uid": "..."}}

or just the nested result object:

    {"sid": "...", "ecode": "...", "uid": "..."}

The script prints redacted credentials by default. Use --show-secrets only in a
private debug shell.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
from pathlib import Path
from typing import Any

DEFAULT_APP_ID = "3cxxt3au9x33ytvq3h9j"
DEFAULT_BROKER = "mqtts://m1.tuyaus.com:8883"
DEFAULT_PACKAGE_NAME = "com.tuya.smart"
MQTT_UID_SALT = "sdkfasodifca"


def derive_mqtt_credentials(
    login_response: dict[str, Any],
    *,
    email: str,
    app_id: str = DEFAULT_APP_ID,
    package_name: str = DEFAULT_PACKAGE_NAME,
    device_id: str | None = None,
) -> dict[str, str]:
    """Return the Tuya mobile MQTT credentials derived from login data."""
    result = _login_result(login_response)
    username = _first_text(result, "token", "mqttToken", "mqtt_token", "sid")
    ecode = _text(result.get("ecode"))
    uid = _text(result.get("uid"))

    if not username:
        raise ValueError("login response does not contain sid/token")
    if not ecode:
        raise ValueError("login response does not contain ecode")
    if not uid:
        raise ValueError("login response does not contain uid")

    device_id = device_id or stable_device_id(email, app_id, package_name)
    uid_hash = md5_hex(uid + MQTT_UID_SALT)
    client_id = f"{package_name}_mb_{device_id}_{uid_hash}_DEFAULT"

    return {
        "TUYA_MQTT_BROKER": mqtt_broker_from_result(result) or DEFAULT_BROKER,
        "TUYA_MQTT_USER": username,
        "TUYA_MQTT_PASS": md5_hex(ecode)[8:24],
        "TUYA_MQTT_UID": uid,
        "TUYA_MQTT_CLIENT_ID": client_id,
    }


def mqtt_broker_from_result(result: dict[str, Any]) -> str:
    domain = result.get("domain") if isinstance(result.get("domain"), dict) else {}
    host = _text(domain.get("mobileMqttsUrl") or domain.get("mobileMqttUrl"))
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


def stable_device_id(email: str, app_id: str, package_name: str) -> str:
    material = f"{package_name}|{app_id}|{email}".encode()
    return hashlib.sha256(material).hexdigest()[:44]


def md5_hex(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode()
    return hashlib.md5(value).hexdigest()


def _login_result(login_response: dict[str, Any]) -> dict[str, Any]:
    result = login_response.get("result")
    if isinstance(result, dict):
        return result
    return login_response


def _first_text(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _text(data.get(key))
        if value:
            return value
    return ""


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _redact(value: str) -> str:
    if len(value) <= 8:
        return "<redacted>"
    return f"{value[:4]}...{value[-4:]}"


def _print_shell(values: dict[str, str], *, show_secrets: bool) -> None:
    secret_keys = {"TUYA_MQTT_USER", "TUYA_MQTT_PASS"}
    for key, value in values.items():
        if not show_secrets and key in secret_keys:
            value = _redact(value)
        print(f"export {key}={shlex.quote(value)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Derive Tuya mobile MQTT credentials from a login response."
    )
    parser.add_argument("--login-response", required=True, type=Path)
    parser.add_argument("--email", required=True)
    parser.add_argument("--app-id", default=DEFAULT_APP_ID)
    parser.add_argument("--package-name", default=DEFAULT_PACKAGE_NAME)
    parser.add_argument("--device-id")
    parser.add_argument("--show-secrets", action="store_true")
    args = parser.parse_args()

    login_response = json.loads(args.login_response.read_text())
    credentials = derive_mqtt_credentials(
        login_response,
        email=args.email,
        app_id=args.app_id,
        package_name=args.package_name,
        device_id=args.device_id,
    )
    _print_shell(credentials, show_secrets=args.show_secrets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
