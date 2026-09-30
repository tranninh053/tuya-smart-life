# Cơ chế điều khiển local

Mobile/cloud API chỉ dùng để lấy metadata:

- phiên đăng nhập
- danh sách nhà
- danh sách thiết bị
- local key
- quan hệ hub/thiết bị con
- DPS ban đầu
- metadata action của IR remote

Lệnh điều khiển thông thường đi qua LAN:

```text
Home Assistant -> IP LAN thiết bị/hub -> TinyTuya -> Tuya local protocol
```

Thiết bị con sau hub dùng `parentDevId` và `node_id`/`cid` khi Tuya trả đủ topology metadata.

Integration lắng nghe UDP broadcast và LAN scan để học IP/protocol version. IP public/WAN từ mobile API bị bỏ qua; chỉ IP private LAN được dùng cho local control.

Thiết bị ở subnet/VLAN khác không ổn định nếu Home Assistant không nhận được Tuya UDP broadcast. Ping/TCP tới IP thiết bị chưa đủ.
