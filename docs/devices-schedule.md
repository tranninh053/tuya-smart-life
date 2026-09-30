# Lịch và hẹn tắt thiết bị

Tuya có timer riêng gắn với từng thiết bị/DP. Đây không phải automation của Home Assistant.

Integration hiện có hai action:

- `tuya_smart_life_local.set_turn_offf_countdown`: nhập `minutes` và `dev_id`/`device_id`/`id`. Integration lấy giờ hiện tại trong timezone của Home Assistant, cộng số phút, rồi tạo timer tắt toàn bộ switch DPS của thiết bị. Nếu thiết bị có category `scheduleCategory` như app Tuya thì integration sẽ dùng category này; nếu không có thì fallback về category của DPS như `switch`.
- `tuya_smart_life_local.clear_countdown`: xóa toàn bộ timer cloud của thiết bị.

`set_turn_off_countdown` cũng được đăng ký như alias đúng chính tả.

Ví dụ đang là `10:00`, gọi:

```yaml
action: tuya_smart_life_local.set_turn_offf_countdown
data:
  dev_id: n0kphfrgn3fd0iat
  minutes: 5
```

Tuya sẽ nhận lịch tắt lúc `10:05`.

Xóa toàn bộ timer/lịch cloud của thiết bị:

```yaml
action: tuya_smart_life_local.clear_countdown
data:
  dev_id: n0kphfrgn3fd0iat
```

Ví dụ automation: khi công tắc bật thì tự hẹn tắt sau 5 phút.

```yaml
alias: Công tắc tự tắt sau 5 phút
trigger:
  - platform: state
    entity_id: switch.cong_tac
    to: "on"
action:
  - action: tuya_smart_life_local.set_turn_offf_countdown
    data:
      dev_id: n0kphfrgn3fd0iat
      minutes: 5
mode: restart
```

Nếu muốn mỗi lần tạo countdown mới đều xóa lịch cũ trước:

```yaml
action:
  - action: tuya_smart_life_local.clear_countdown
    data:
      dev_id: n0kphfrgn3fd0iat
  - action: tuya_smart_life_local.set_turn_offf_countdown
    data:
      dev_id: n0kphfrgn3fd0iat
      minutes: 5
```

Nếu đang là `23:31` và nhập `60`, Tuya sẽ lưu thành `00:31` của ngày hôm sau. API không nhận giờ dạng `24:31`.

Timer dùng mobile cloud API của Tuya:

- Thêm timer: `thing.m.timer.group.add`
- Liệt kê timer: `thing.m.timer.all.list` / `thing.m.timer.group.list`
- Xóa timer: `thing.m.timer.group.remove`

Trường `timeZone` của API phải dùng offset như `+07:00`, không dùng tên timezone như `Asia/Ho_Chi_Minh`.

Thiết bị phải có DPS dạng switch như `switch`, `switch_1`, `switch_2`. Với thiết bị nhiều kênh, action hẹn tắt sẽ tạo timer cho từng kênh switch.
