# Lệnh Tuya IR local DP201

Tài liệu này ghi lại đường gửi local đã hoạt động cho Tuya Smart IR remote, đặc biệt là remote điều hòa như `LG master`.

## Nguồn dữ liệu

Mobile API cung cấp IR keydata qua:

- `tuya.m.infrared.gateway.get`
- `tuya.m.infrared.keydata.get`

Với mỗi phím, integration build payload DP `201` giống panel IR của app Tuya:

```json
{
  "control": "send_ir",
  "head": "",
  "key1": "001%^...",
  "type": 0,
  "delay": 300
}
```

Payload được lưu trong `TuyaIrAction.action_dps`:

```json
{
  "201": "{\"control\":\"send_ir\",\"head\":\"\",\"key1\":\"001%^...\",\"type\":0,\"delay\":300}"
}
```

`report_dps` chỉ dùng để cập nhật state optimistic trong Home Assistant. Nó không được gửi tới hub.

## Đường publish local

Đường hoạt động đúng là:

```text
Home Assistant -> IP LAN hub Smart IR vật lý -> TinyTuya -> DP 201
```

Chi tiết quan trọng:

- Publish tới device id của hub IR vật lý, không gửi vào virtual remote child.
- Dùng local key, IP LAN và protocol version của hub.
- Gửi một write duy nhất cho DP `201`.
- Ưu tiên TinyTuya `set_value(201, payload, nowait=True)`.
- Response `None` là bình thường vì đây là lệnh local fire-and-forget.
- `Check device key or version` không được xem là gửi thành công. Caller cần retry hoặc hiển thị lỗi service thay vì cập nhật state optimistic. Một lỗi command đơn lẻ không làm IR climate thành unavailable; availability lấy từ cảm biến local connection của hub.

Code nằm trong `custom_components/tuya_smart_life_local/local.py`:

```python
target_dev_id = action.hub_dev_id
device.set_value(201, ir_payload, nowait=True)
```

Với TinyTuya cũ không có `set_value`, fallback là:

```python
device.set_status(ir_payload, switch=201, nowait=True)
```

## Vì sao đường cũ lỗi

Virtual IR remote là object phía app. Nó có `remote_id` và có thể trông như expose DP `201`, nhưng nó không phải thiết bị LAN phát hồng ngoại. Test thực tế cho thấy publish payload keydata DP `201` qua child LG ảo có thể hoàn tất nhưng điều hòa LG không nhận lệnh.

Cùng payload DP `201` đó publish tới hub Smart IR vật lý thì hoạt động. Test LAN trên Mac cho `LG master` dùng:

```text
hub dev_id: eb9969bdcc78902f55g8wu
hub IP:     192.168.2.181
remote id:  eb11a10fef0d481b6diuag
action:     M0_T25_S1
```

Điều hòa nhận lệnh khi `M0_T25_S1` được ghi vào hub bằng một payload DP `201`.

State IR climate là optimistic và có thể lệch với trạng thái thật của điều hòa. Để đổi nhiệt/mode/gió vẫn bật được máy khi máy thật đang tắt, Home Assistant gửi keydata `power on` DP `201` trước, chờ ngắn, rồi gửi full state yêu cầu như `M0_T25_S1`.

State stream realtime LAN của hub IR phải im trong lúc gửi các frame đó. Runtime đóng stream hub và pause reconnect ngắn trước lệnh IR; nếu không, stream có thể reconnect giữa `power on` và frame nhiệt độ, khiến hub trả `Check device key or version`.

Cũng cần tránh bug normalize DP: `_normalize_command_dps()` đổi DP id số thành integer, nên code phải so sánh DP id theo string:

```python
{str(dp_id) for dp_id in dps} == {"201"}
```

Cách này giữ key string/integer tương đương và bảo toàn đường publish single-DP.

## Debug

Export toàn bộ IR code cho một nhà:

```bash
python3 tools/tuya_mobile_login.py --action ir --home-id <home-id> --json
```

Không commit report export từ tài khoản thật. Chúng có thể chứa device id, tên remote và raw IR keydata của nhà riêng.

Với Home Assistant đã bật debug endpoint, xem runtime mapping tại:

```text
http://<home-assistant-host>:18435/devices
```

Sau khi Home Assistant restart, debug endpoint nên hiển thị action LG như sau:

```json
{
  "hub_dev_id": "eb9969bdcc78902f55g8wu",
  "publish_target_dev_id": "eb9969bdcc78902f55g8wu"
}
```

Nếu `publish_target_dev_id` là virtual remote id thì đường lệnh DP `201` đang sai.
