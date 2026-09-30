# Khóa Wi-Fi

Khóa Wi-Fi được nhận diện là thiết bị khóa độc lập, không phải child sau gateway.

Integration expose:

- entity khóa
- cảm biến DPS khóa thường gặp
- sự kiện MQTT cuối
- media/alarm cuối

Payload media DP `212` được base64-decode vào attributes khi có.

## Mở khóa

Mở khóa dùng private mobile API:

```text
thing.m.device.lock.remote.host.unlock
```

Với khóa standalone, lock device id được dùng làm cả source và destination.

Entry cũ còn `mqtt_unlock_dps` có thể fallback publish DPS qua `smart/mb/out/{devId}`, nhưng setup mới không cần cấu hình unlock DPS thủ công.

## MQTT

Sự kiện khóa realtime phụ thuộc Tuya cloud MQTT khi Tuya trả đủ `sid`, `ecode`, `uid`. Chi tiết credential nằm ở [MQTT cloud tự suy ra credential](mqtt-auto-credentials.md).
