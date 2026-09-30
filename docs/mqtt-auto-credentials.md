# Tự suy ra Tuya Mobile MQTT Credentials

Integration không nên hỏi người dùng thường về MQTT broker, username, password, uid hoặc client id. Các giá trị đó được suy ra từ phiên đăng nhập mobile Tuya bình thường.

## Nguồn sự thật

Luồng Android SDK liên quan:

```java
MqttConnectConfig mqttConnectConfig = new MqttConnectConfig();
mqttConnectConfig.setUid(iBaseUser.getUid());
mqttConnectConfig.setEcode(iBaseUser.getEcode());
mqttConnectConfig.setPartnerIdentity(iBaseUser.getPartnerIdentity());
mqttConnectConfig.setToken(iBaseUser.getSid());
```

Với các build Smart Life/Tuya Smart hiện tại:

- MQTT username là `MqttConnectConfig.token`.
- `MqttConnectConfig.token` chính là mobile login `sid`.
- MQTT password là `md5_hex(ecode)[8:24]`.
- MQTT uid là mobile login `uid`.
- MQTT client id được tạo deterministic từ package name, API device id và uid.
- MQTT broker nên lấy từ `domain.mobileMqttsUrl`/`domain.mqttsPort` nếu có; fallback là `mqtts://m1.tuyaus.com:8883`.

Response login Smart Life 7.x thường không có field riêng `token`, `mqttToken` hoặc `mqtt_token`. Đừng xem đó là thiếu MQTT credential nếu `sid`, `ecode` và `uid` có mặt.

## Thuật toán runtime

`custom_components/tuya_smart_life_local/mqtt_cloud.py` thực hiện suy ra credential:

```python
username = login_result.get("token") or login_result.get("mqttToken")
username = username or login_result.get("mqtt_token") or login_result["sid"]
password = md5_hex(login_result["ecode"])[8:24]
uid = login_result["uid"]
sdk_uid = f"{device_id}_{md5_hex(uid + 'sdkfasodifca')}"
client_id = f"{package_name}_mb_{sdk_uid}_DEFAULT"
broker = f"mqtts://{domain['mobileMqttsUrl']}:{domain.get('mqttsPort', 8883)}"
```

Các key config-entry MQTT cũ vẫn tồn tại chỉ như hidden/manual override để debug credential capture từ app:

- `mqtt_broker`
- `mqtt_username`
- `mqtt_password`
- `mqtt_uid`
- `mqtt_client_id`

Chúng không được hiện trong config/options flow bình thường.

## Luồng Home Assistant

1. Người dùng nhập tài khoản Smart Life/Tuya.
2. `TuyaSmartLifeMobileApi.login()` trả về `TuyaSession`.
3. Coordinator lưu session trong `coordinator.data.session`.
4. `async_setup_entry()` gọi `derive_mqtt_config(data, session, config)`.
5. `TuyaMqttCloudRuntime` kết nối Tuya cloud MQTT và subscribe:
   - `smart/mb/{uid}`
   - `smart/mb/in/{devId}`
   - `smart/mb/out/{devId}`
   - `m/w/{devId}`

Nếu thiếu `sid`, `ecode`, `uid` hoặc client id suy ra được, MQTT bị tắt và log có:

```text
Tuya cloud MQTT credentials are incomplete
```

Warning này không nên xuất hiện sau một lần login bình thường có đủ `sid`, `ecode`, `uid`.

## Kiểm tra

Sau khi deploy và restart Home Assistant, kiểm tra log:

```bash
grep -Ei \
  'tuya cloud mqtt|mqtt_cloud|credentials are incomplete|connect failed|paho' \
  /config/home-assistant.log
```

Kỳ vọng:

- Không có warning `credentials are incomplete`.
- Không có warning `paho-mqtt is not installed`.
- Không có warning `Tuya cloud MQTT connect failed rc=...`.
- `Tuya cloud MQTT connected` chỉ xuất hiện khi bật info log.

## Ví dụ standalone

Xem [docs/examples/mqtt_auto_credentials.py](examples/mqtt_auto_credentials.py) để có ví dụ không phụ thuộc thư viện, suy ra cùng các giá trị từ response login mobile đã lưu.

Chạy với JSON login response đã redact an toàn:

```bash
python3 docs/examples/mqtt_auto_credentials.py \
  --login-response /path/to/login-response.json \
  --email user@example.com
```

Mặc định script in output đã redact. Chỉ dùng `--show-secrets` trong shell debug riêng tư.
