# Thiết bị IR

Tuya quản lý IR theo hai lớp:

- Hub IR thật: có local key, IP LAN và nhận lệnh local.
- Remote IR ảo: TV, AC, fan... nằm sau hub, có `remote_id`.

Integration lấy remote/action từ mobile API, build payload IR, rồi gửi raw DPS tới hub IR vật lý trong LAN. Remote ảo chỉ dùng cho identity, tên và metadata.

## Entity được hỗ trợ

- Điều hòa/AC: `climate`.
- Quạt: `fan`.
- TV, set-top box, TV box, audio, projector, DVD: `media_player` và button raw key khi cần.
- Đèn: `light`.
- DIY/không nhận diện: `button`.

IR là điều khiển một chiều, nên state trong Home Assistant là optimistic.

## Điều hòa IR

Với AC như `LG master`, integration gửi DP `201` tới hub IR vật lý. Khi đổi nhiệt/mode/gió, integration có thể gửi `power on` trước rồi gửi full state mong muốn.

Chi tiết đường lệnh DP `201`: [Lệnh Tuya IR local DP201](ir-local-dp201.md).

## Debug

Export IR action cho một nhà:

```bash
python3 tools/tuya_mobile_login.py --action ir --home-id <home-id> --json
```

Không commit report export từ tài khoản thật vì có thể chứa device id, tên remote và raw IR keydata.
